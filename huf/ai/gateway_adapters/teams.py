"""Microsoft Teams gateway adapter (Bot Framework, direct mode inside Frappe).

* ``verify_inbound`` validates the Bot Framework bearer JWT via ``teams_auth``.
* ``normalize_inbound`` maps activities per the plan (D4); non-message kinds are tagged with
  ``raw_payload["huf_kind"]`` and dropped/handled by the pre-ingest hooks.
* ``send_reply`` / ``send_adaptive_card`` resolve the service URL and tenant from the stored
  ``Teams Conversation Reference`` (never from untrusted input), then enqueue to the outbox
  (default) or post directly (``direct=True``).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Callable, Mapping

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import (
	GatewayAttachment,
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
)
from huf.ai.gateways import teams_contract as tc

CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"
ROOM_TYPES = ("channel", "groupChat")
_THREAD_MARK = ";messageid="
_MD_SPACES = re.compile(r"[ \t ]+")


def _default_fetch_json(url: str) -> Mapping[str, Any]:
	"""GET JSON with a short timeout; https only and no redirects."""
	import requests

	if not str(url).lower().startswith("https://"):
		raise ValueError("metadata url must be https")
	response = requests.get(url, timeout=5, allow_redirects=False)
	response.raise_for_status()
	return response.json()


def _default_reference_lookup(conversation_id: str, gateway: str | None, app_id: str) -> dict | None:
	"""Reference lookup, always scoped to one gateway (never matches across gateways)."""
	import frappe

	from huf.ai.gateways import teams_refs

	if not gateway:
		return None  # fail closed: an unscoped lookup could cross-route between gateways
	rows = frappe.get_all(
		teams_refs.DOCTYPE,
		filters={"conversation_id": conversation_id.split(_THREAD_MARK, 1)[0], "gateway": gateway},
		fields=["*"],
		order_by="last_seen_at desc",
		limit=1,
	)
	return rows[0] if rows else None


def _s(value: Any) -> str:
	return str(value) if value else ""


class TeamsGatewayAdapter(GatewayAdapter):
	"""Handle Microsoft Teams Bot Framework activities, replies, and Adaptive Cards."""

	# NOTE: must equal provider_to_service_id("Microsoft Teams") == "microsoft_teams".
	provider_id = "microsoft_teams"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("app_id", "Microsoft App ID"),
			GatewayCredentialField("app_password", "Microsoft App Secret / Password"),
			GatewayCredentialField(
				"tenant_id",
				"Directory (tenant) ID",
				secret=False,
				description="The Microsoft Entra directory (tenant) ID of the bot's app registration.",
			),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=20,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] | None = None,  # legacy seam, unused
		jwks_fetcher: Callable[[str], Mapping[str, Any]] | None = None,
		token_fetcher: Callable[..., Any] | None = None,  # legacy seam, unused
		now: Callable[[], float] | None = None,
		fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
		http: Callable[..., Any] | None = None,
		gateway_name: str | None = None,
		direct: bool = False,
		reference_lookup: Callable[[str, str | None, str], dict | None] | None = None,
		outbox: Any = None,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"Microsoft Teams adapter is missing required credentials: {', '.join(missing)}")
		self._app_id = credentials["app_id"]
		self._app_password = credentials["app_password"]
		self._tenant_id = credentials["tenant_id"]
		self._http_post = http_post
		self._jwks_fetcher = jwks_fetcher
		self._token_fetcher = token_fetcher
		self._now = now
		self._fetch_json = fetch_json or jwks_fetcher or _default_fetch_json
		self._http = http
		self._gateway_name = gateway_name
		self._direct = direct
		self._reference_lookup = reference_lookup or _default_reference_lookup
		self._outbox = outbox
		# id(reply) -> (reply, nonce): a retry of the SAME GatewayReply object (send loop) keeps
		# its key and is deduped by the outbox; any other send gets a fresh nonce.
		self._reply_nonces: dict[int, tuple[Any, str]] = {}

	def __repr__(self) -> str:
		return f"TeamsGatewayAdapter(app_id={self._app_id!r}, direct={self._direct})"

	# ---- inbound -------------------------------------------------------------------

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""True only when the bearer JWT validates for this bot; fails closed, never raises."""
		try:
			from huf.ai.gateways import teams_auth

			headers = {str(k).lower(): v for k, v in (request.headers or {}).items()}
			auth_header = str(headers.get("authorization") or "").strip()
			if not auth_header:
				return False
			activity = json.loads(request.body.decode("utf-8")) if request.body else {}
			service_url = _s(activity.get("serviceUrl")) if isinstance(activity, dict) else ""
			result = teams_auth.verify_bearer(
				auth_header,
				app_id=self._app_id,
				activity_service_url=service_url,
				fetch_json=self._fetch_json,
				now=self._now or time.time,
				tenant_id=self._tenant_id,
			)
			return bool(result.ok)
		except Exception:
			return False

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		# Verification is done by the webhook before this is called; not repeated here.
		try:
			activity = json.loads(request.body.decode("utf-8")) if request.body else {}
		except Exception as exc:
			raise ValueError("Invalid Teams Activity JSON payload") from exc
		if not isinstance(activity, dict):
			raise ValueError("Invalid Teams Activity JSON payload")
		activity.pop("huf_kind", None)  # never trust a sender-supplied tag

		from huf.ai.gateways import teams_refs

		meta = teams_refs.parse_meta(activity)
		kind = self._kind(activity, teams_refs)
		from_account = activity.get("from") or {}
		conversation = activity.get("conversation") or {}
		conversation_id = _s(conversation.get("id"))
		ctype = meta.conversation_type

		sender_id = (
			_s(from_account.get("aadObjectId"))
			or _s(from_account.get("id"))
			or _s((activity.get("recipient") or {}).get("id"))
			or "teams-system"
		)
		event_id = _s(activity.get("id")) or "teams-" + hashlib.sha1(request.body or b"").hexdigest()[:20]

		is_room = ctype in ROOM_TYPES
		mentioned = ctype == "personal" or self._mentions_bot(activity, meta.bot_id)
		text = self._clean_text(activity, meta.bot_id) if kind == "message" else ""
		thread_id = meta.root_id or _s(activity.get("replyToId")) or None

		attachments = []
		for attachment in activity.get("attachments") or []:
			content_url = isinstance(attachment, dict) and attachment.get("contentUrl")
			if not content_url:
				continue
			attachments.append(
				GatewayAttachment(
					mime_type=str(attachment.get("contentType") or ""),
					filename=str(attachment.get("name") or ""),
					url=content_url,
					kind="file",
				)
			)

		raw = dict(activity)
		raw.update({"huf_kind": kind, "tenant_id": meta.tenant_id, "service_url": meta.service_url})
		return NormalizedGatewayEvent(
			provider_event_id=event_id,
			sender_id=sender_id,
			conversation_id=conversation_id or "unknown",
			message_text=text,
			thread_id=thread_id,
			is_room=is_room,
			mentioned=mentioned,
			raw_payload=raw,
			display_name=_s(from_account.get("name")),
			attachments=tuple(attachments),
		)

	@staticmethod
	def _kind(activity: dict, teams_refs: Any) -> str:
		if activity.get("type") == "invoke":
			if activity.get("name") == "adaptiveCard/action":
				return tc.TeamsActivityKind.CARD_ACTION.value
			return tc.TeamsActivityKind.IGNORED.value
		return teams_refs.classify(activity)

	@staticmethod
	def _mentions_bot(activity: dict, bot_id: str) -> bool:
		if not bot_id:
			return False
		for entity in activity.get("entities") or []:
			if not isinstance(entity, dict) or entity.get("type") != "mention":
				continue
			if _s((entity.get("mentioned") or {}).get("id")) == bot_id:
				return True
		return False

	@staticmethod
	def _clean_text(activity: dict, bot_id: str) -> str:
		text = _s(activity.get("text"))
		if bot_id:
			for entity in activity.get("entities") or []:
				if not isinstance(entity, dict) or entity.get("type") != "mention":
					continue
				if _s((entity.get("mentioned") or {}).get("id")) == bot_id and entity.get("text"):
					text = text.replace(str(entity["text"]), " ")
		lines = [_MD_SPACES.sub(" ", line).strip() for line in text.splitlines()]
		return "\n".join(line for line in lines if line).strip()

	# ---- outbound ------------------------------------------------------------------

	def _resolve(self, conversation_id: str, thread_id: str | None = None) -> dict:
		"""Reference-backed routing: service_url (validated), tenant, thread-aware conversation id."""
		from huf.ai.gateways import teams_api

		row = self._reference_lookup(conversation_id, self._gateway_name, self._app_id)
		if not row:
			raise ValueError("No Teams conversation reference for this conversation")
		service_url = teams_api.validate_service_url(_s(row.get("service_url")))
		base = conversation_id.split(_THREAD_MARK, 1)[0]
		target = conversation_id
		if _THREAD_MARK not in conversation_id and thread_id and row.get("conversation_type") == "channel":
			target = f"{base}{_THREAD_MARK}{thread_id}"
		return {
			"conversation_ref": row.get("name"),
			"conversation_id": target,
			"service_url": service_url,
			"tenant_id": _s(row.get("tenant_id")),
			"gateway": self._gateway_name or _s(row.get("gateway")),
		}

	def _dispatch(self, kind: str, activity: dict, snapshot: dict, key: str) -> OutboundDelivery:
		from huf.ai.gateways import teams_api

		if self._direct:
			provider = teams_api.make_token_provider(
				{
					"app_id": self._app_id,
					"app_password": self._app_password,
					"tenant_id": self._tenant_id,
				},
				gateway_name=snapshot.get("gateway") or None,
				http=self._http,
				now=self._now,
			)
			body = teams_api.post_activity(
				snapshot["service_url"],
				snapshot["conversation_id"],
				activity,
				token=provider,
				http=self._http,
				now=self._now,
			)
			pid = _s(body.get("id")) if isinstance(body, Mapping) else ""
			if not pid:
				raise ValueError("Microsoft Teams message delivery failed: no activity id")
			return OutboundDelivery(pid, provider_response=dict(body))

		outbox = self._outbox
		if outbox is None:
			from huf.ai.gateways import teams_outbox as outbox
		name = outbox.enqueue(snapshot.get("gateway"), snapshot, kind, {"activity": activity}, key)
		return OutboundDelivery(f"outbox:{name}", accepted=True)

	@staticmethod
	def _key(prefix: str, *parts: Any) -> str:
		raw = "\x1f".join(str(p) for p in parts)
		return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"

	def _reply_key(self, reply: GatewayReply, snapshot: dict) -> str:
		"""Unique per outbound event.

		A true inbound activity id (``reply_to_provider_message_id`` that is not just the thread
		root) gives a key derived from that id + the text hash, so a retry of the same event is
		deduped. Anything else (personal chats, thread roots, ad-hoc sends) gets a per-call nonce:
		identical text is NOT deduped; a retry of the same ``reply`` object reuses its nonce.
		"""
		text_hash = hashlib.sha256((reply.text or "").encode("utf-8")).hexdigest()[:16]
		event_id = reply.reply_to_provider_message_id
		if event_id and event_id != reply.thread_id:
			return self._key("reply", snapshot.get("gateway"), snapshot["conversation_id"], event_id, text_hash)
		cached = self._reply_nonces.get(id(reply))
		if cached is None or cached[0] is not reply:
			cached = (reply, uuid.uuid4().hex)
			self._reply_nonces[id(reply)] = cached
		return self._key("reply", snapshot.get("gateway"), snapshot["conversation_id"], cached[1], text_hash)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send a text reply via the outbox (or directly when ``direct=True``)."""
		snapshot = self._resolve(reply.conversation_id, reply.thread_id)
		activity: dict[str, Any] = {"type": "message", "text": reply.text, "textFormat": "markdown"}
		if reply.reply_to_provider_message_id:
			activity["replyToId"] = reply.reply_to_provider_message_id
		return self._dispatch("reply", activity, snapshot, self._reply_key(reply, snapshot))

	def send_adaptive_card(
		self,
		conversation_id: str,
		card_content: dict[str, Any],
		*,
		thread_id: str | None = None,
	) -> OutboundDelivery:
		"""Send an Adaptive Card; raises on failure and never fabricates an id."""
		snapshot = self._resolve(conversation_id, thread_id)
		activity = {
			"type": "message",
			"attachments": [{"contentType": CARD_CONTENT_TYPE, "content": card_content}],
		}
		key = self._key(
			"card",
			snapshot.get("gateway"),
			snapshot["conversation_id"],
			json.dumps(card_content, sort_keys=True, default=str),
		)
		return self._dispatch("card", activity, snapshot, key)
