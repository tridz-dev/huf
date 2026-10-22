# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Bot API gateway adapter.

Thin composition of the Telegram modules: ``telegram_client`` (Bot API transport + error
classification), ``telegram_inbound`` (pure update parsing), ``telegram_outbound`` (senders),
``telegram_format`` (markdown rendering/splitting) and ``telegram_keyboards`` (buttons + signed
callback data). No Frappe persistence and no routing or admission policy; the only Frappe touch
is the best-effort ``File`` save for downloaded inbound media.
"""

from __future__ import annotations

import hmac
import json
from typing import Any, Callable, Mapping

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.telegram_client import (
	ALLOWED_UPDATES,
	TELEGRAM_API_BASE,
	TelegramApiError,
	TelegramBotClient,
	_requests_get,
	_requests_post,
)
from huf.ai.gateway_adapters.telegram_format import MODE_PLAIN
from huf.ai.gateway_adapters.telegram_inbound import TelegramUpdate, parse_update, to_event
from huf.ai.gateway_adapters.telegram_keyboards import derive_callback_key, sign_callback, verify_callback
from huf.ai.gateway_adapters.telegram_outbound import MEDIA_METHODS, TelegramSender
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

WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

__all__ = [
	"ALLOWED_UPDATES",
	"TELEGRAM_API_BASE",
	"WEBHOOK_SECRET_HEADER",
	"TelegramGatewayAdapter",
	"TelegramIgnoredUpdate",
]


class TelegramIgnoredUpdate(ValueError):
	"""A verified update that is not a Huf event (my_chat_member, reaction counts, ...).

	Callers that need those updates use ``TelegramGatewayAdapter.parse_update`` instead.
	"""

	def __init__(self, parsed: TelegramUpdate) -> None:
		self.update = parsed
		super().__init__(f"Telegram update '{parsed.kind}' does not produce a gateway event")


class TelegramGatewayAdapter(GatewayAdapter):
	"""Authenticate Telegram Bot API webhook updates and deliver replies."""

	provider_id = "telegram"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("token", "Telegram Bot Token"),
			GatewayCredentialField(
				"webhook_secret",
				"Webhook secret token",
				required=True,
				description=(
					"Value passed to Telegram's setWebhook secret_token; "
					"verified against the X-Telegram-Bot-Api-Secret-Token header."
				),
			),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		supports_media_reply=True,
		max_outbound_messages_per_second=30,
		supports_reactions=True,
		supports_typing=True,
		supports_buttons=True,
		supports_edit=True,
		supports_voice_reply=True,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		http_get: Callable[..., Any] = _requests_get,
		download_attachments: bool = True,
		parse_mode: str = MODE_PLAIN,
		max_flood_retries: int = 0,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError("Telegram adapter is missing required credentials: " + ", ".join(missing))
		self._token = credentials["token"]
		self._webhook_secret = credentials.get("webhook_secret", "")
		self._http_post = http_post
		self._http_get = http_get
		self._download_attachments = download_attachments
		self._callback_key = derive_callback_key(self._webhook_secret)
		# The client dispatches through the adapter attributes so swapping ``_http_post`` after
		# construction (tests, tools) keeps working.
		self.client = TelegramBotClient(
			self._token,
			http_post=lambda *a, **k: self._http_post(*a, **k),
			http_get=lambda *a, **k: self._http_get(*a, **k),
			max_flood_retries=max_flood_retries,
		)
		self.sender = TelegramSender(self.client, parse_mode=parse_mode)

	# -- inbound -------------------------------------------------------------------------------

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Constant-time check of the webhook secret header; fails closed when unconfigured/missing."""
		if not self._webhook_secret:
			return False
		provided = request.headers.get(WEBHOOK_SECRET_HEADER, "").strip()
		if not provided:
			return False
		return hmac.compare_digest(provided, self._webhook_secret)

	def parse_update(self, request: GatewayInboundRequest) -> TelegramUpdate:
		"""Verify and parse any update into the typed ``TelegramUpdate`` (no media download)."""
		if not self.verify_inbound(request):
			raise ValueError("Telegram webhook secret verification failed")
		try:
			update = json.loads(request.body.decode("utf-8")) if request.body else {}
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise ValueError("Invalid Telegram update payload") from exc
		if not isinstance(update, Mapping):
			raise ValueError("Invalid Telegram update payload")
		return parse_update(update)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		parsed = self.parse_update(request)
		if parsed.kind == "callback_query":
			payload = self.verify_callback_data(parsed.callback_data, parsed.chat_id)
			if payload is None:
				raise ValueError("Telegram callback data failed signature verification")
			parsed = _with_text(parsed, payload)
		attachments = tuple(self._attachments(parsed))
		event = to_event(parsed, attachments)
		if event is None:
			raise TelegramIgnoredUpdate(parsed)
		return event

	def _attachments(self, parsed: TelegramUpdate) -> list[GatewayAttachment]:
		"""One attachment per media field. GW-30: always keep the file_id. GW-31: best-effort download
		into a Frappe File; any failure degrades to a file_id-only attachment."""
		attachments = []
		for ref in parsed.attachments_meta:
			file_doc = None
			if self._download_attachments:
				file_doc = self._download_to_file_doc(ref["file_id"], ref["filename"], ref["kind"])
			attachments.append(
				GatewayAttachment(
					mime_type=ref["mime_type"],
					filename=ref["filename"],
					file_id=ref["file_id"],
					file_doc=file_doc,
					kind=ref["kind"],
				)
			)
		return attachments

	def _download_to_file_doc(self, file_id: str, filename: str, kind: str) -> str | None:
		try:
			content, file_path = self.client.download_file(file_id)
			from frappe.utils.file_manager import save_file

			saved_filename = filename or file_path.rsplit("/", 1)[-1] or f"{kind}-{file_id}"
			saved = save_file(saved_filename, content, None, None, is_private=True)
			return getattr(saved, "name", None)
		except Exception:
			# No Frappe context, network error, malformed response: normalization must not fail.
			return None

	# -- callback data -------------------------------------------------------------------------

	def sign_callback_data(self, payload: str, chat_id: Any = "") -> str:
		"""Signed ``callback_data`` (<= 64 bytes) bound to the chat it is sent in."""
		return sign_callback(self._callback_key, payload, context=str(chat_id))

	def verify_callback_data(self, data: str, chat_id: Any = "") -> str | None:
		return verify_callback(self._callback_key, data, context=str(chat_id))

	# -- outbound ------------------------------------------------------------------------------

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send attachments (if any) then the text (split at 4096), returning the first receipt."""
		chat_id = reply.conversation_id
		results: list[Mapping[str, Any]] = []
		first = True
		for att in reply.attachments:
			kind = att.kind if att.kind in MEDIA_METHODS else "document"
			media = att.file_id or att.url
			results.extend(
				self.sender.send_media(kind, chat_id, media, reply_to=reply.reply_to_provider_message_id if first else None)
			)
			first = False
		results.extend(
			self.sender.send_text(chat_id, reply.text, reply_to=reply.reply_to_provider_message_id if first else None)
		)
		ids = [r.get("message_id") for r in results if isinstance(r, Mapping) and r.get("message_id") is not None]
		if not ids:
			raise ValueError("Telegram sendMessage response did not include a message_id")
		if len(results) == 1:
			response: Mapping[str, Any] = {"ok": True, "result": results[0]}
		else:
			response = {"ok": True, "result": results[0], "message_ids": ids}
		return OutboundDelivery(str(ids[0]), provider_response=response)

	def send_typing(self, chat_id: Any, action: str = "typing", thread_id: Any = None) -> bool:
		"""Best-effort chat action; never raises (a typing indicator must not fail a run)."""
		try:
			self.sender.send_chat_action(chat_id, action, thread_id=thread_id)
			return True
		except (TelegramApiError, ValueError):
			return False

	def react(self, chat_id: Any, message_id: Any, emoji: str | None) -> bool:
		try:
			self.sender.set_reaction(chat_id, message_id, emoji)
			return True
		except TelegramApiError:
			return False

	def answer_callback(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
		"""Always answer callback queries to stop the client spinner; swallow expiry errors."""
		try:
			self.sender.answer_callback_query(callback_query_id, text, show_alert=show_alert)
			return True
		except TelegramApiError:
			return False


def _with_text(parsed: TelegramUpdate, text: str) -> TelegramUpdate:
	from dataclasses import replace

	return replace(parsed, text=text)
