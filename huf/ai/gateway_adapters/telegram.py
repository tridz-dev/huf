# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Bot API adapter.

This adapter owns only Telegram's native webhook verification, update
normalization, and outbound ``sendMessage`` delivery. It has no Frappe
persistence and no knowledge of routing or admission policy.
"""

from __future__ import annotations

import json
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


TELEGRAM_API_BASE = "https://api.telegram.org"
WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# Telegram update keys that carry downloadable media, keyed by the
# GatewayAttachment.kind we report and whether the value is a list of
# progressively larger PhotoSize objects (photo) or a single File-ish object.
_MEDIA_FIELDS: tuple[tuple[str, str, bool], ...] = (
	("photo", "photo", True),
	("document", "document", False),
	("voice", "voice", False),
	("video", "video", False),
	("audio", "audio", False),
	("video_note", "video_note", False),
	("sticker", "sticker", False),
)


def _requests_post(url: str, *, json_data: Mapping[str, Any], timeout: int) -> Any:
	"""Lazily import requests so the SDK itself has no import-time dependency."""
	import requests

	return requests.post(url, json=json_data, timeout=timeout)


def _requests_get(url: str, *, timeout: int) -> Any:
	"""Lazily import requests so the SDK itself has no import-time dependency."""
	import requests

	return requests.get(url, timeout=timeout)


class TelegramGatewayAdapter(GatewayAdapter):
	"""Authenticate Telegram Bot API webhook updates and deliver text replies."""

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
		max_outbound_messages_per_second=30,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		http_get: Callable[..., Any] = _requests_get,
		download_attachments: bool = True,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError("Telegram adapter is missing required credentials: " + ", ".join(missing))
		self._token = credentials["token"]
		self._webhook_secret = credentials.get("webhook_secret", "")
		self._http_post = http_post
		self._http_get = http_get
		# Allows tests/tools that only need normalization (no Frappe context,
		# no network) to skip the download step and still get file_id-only
		# attachments.
		self._download_attachments = download_attachments

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify webhook secret token using constant-time comparison.

		Requires webhook_secret to be configured at Gateway creation (no fallback).
		Fails closed (returns False) if:
		- webhook_secret is not configured
		- X-Telegram-Bot-Api-Secret-Token header is missing
		- provided secret does not match configured secret

		Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
		"""
		# Fail closed: webhook_secret is mandatory (schema marks it required=True)
		if not self._webhook_secret:
			return False

		# Look for secret in header
		provided = request.headers.get(WEBHOOK_SECRET_HEADER, "").strip()

		# Fail closed if header is not provided
		if not provided:
			return False

		# Use constant-time comparison to prevent timing attacks
		import hmac
		return hmac.compare_digest(provided, self._webhook_secret)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Telegram webhook secret verification failed")

		try:
			update = json.loads(request.body.decode("utf-8")) if request.body else {}
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise ValueError("Invalid Telegram update payload") from exc

		message = update.get("message") or update.get("edited_message") or {}
		chat = message.get("chat") or {}
		sender = message.get("from") or {}

		provider_event_id = str(update.get("update_id") or "")
		sender_id = str(sender.get("id") or "")
		conversation_id = str(chat.get("id") or "")
		if not provider_event_id or not sender_id or not conversation_id:
			raise ValueError("Telegram update is missing update, sender, or chat identifiers")

		chat_type = str(chat.get("type") or "private")
		text = str(message.get("text") or message.get("caption") or "")
		mentioned = any(
			entity.get("type") in ("mention", "bot_command")
			for entity in (message.get("entities") or [])
		)

		username = str(sender.get("username") or "").strip()
		first_name = str(sender.get("first_name") or "").strip()
		display_name = f"@{username}" if username else first_name

		attachments = self._extract_attachments(message)

		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=text,
			thread_id=str(message["message_id"]) if message.get("message_id") is not None else None,
			is_room=chat_type in {"group", "supergroup"},
			mentioned=mentioned,
			raw_payload=update,
			display_name=display_name,
			attachments=tuple(attachments),
		)

	def _extract_attachments(self, message: Mapping[str, Any]) -> list[GatewayAttachment]:
		"""Build attachments for every media field present on a Telegram message.

		GW-30: at minimum records the provider ``file_id``/mime type/filename so
		attachment presence is never silently dropped. GW-31: for the largest
		(or only) file object per field, additionally attempts to download the
		content via Telegram's ``getFile``/file-server API and save it to
		Frappe's File doctype, populating ``file_doc`` on success. A download
		failure (network error, missing Frappe context, disabled downloads)
		degrades gracefully to a file_id-only attachment rather than raising --
		normalize_inbound must not fail just because media couldn't be fetched.
		"""
		attachments: list[GatewayAttachment] = []
		for kind, field_name, is_list in _MEDIA_FIELDS:
			value = message.get(field_name)
			if not value:
				continue
			# Telegram sends "photo" as a list of PhotoSize objects, smallest
			# first; the last entry is the highest resolution available.
			obj = value[-1] if is_list and isinstance(value, list) and value else value
			if not isinstance(obj, Mapping):
				continue
			file_id = str(obj.get("file_id") or "")
			if not file_id:
				continue
			mime_type = str(obj.get("mime_type") or ("image/jpeg" if kind == "photo" else ""))
			filename = str(obj.get("file_name") or "")
			file_doc = self._download_to_file_doc(file_id, filename, mime_type, kind) if self._download_attachments else None
			attachments.append(
				GatewayAttachment(
					mime_type=mime_type,
					filename=filename,
					file_id=file_id,
					file_doc=file_doc,
					kind=kind,
				)
			)
		return attachments

	def _download_to_file_doc(self, file_id: str, filename: str, mime_type: str, kind: str) -> str | None:
		"""Resolve a Telegram ``file_id`` to bytes and save it as a Frappe File.

		Best-effort: any failure (Telegram API error, network error, Frappe not
		available in the current process) returns None instead of raising, so
		callers always still get a usable file_id-only attachment.
		"""
		try:
			get_file_url = f"{TELEGRAM_API_BASE}/bot{self._token}/getFile"
			response = self._http_post(get_file_url, json_data={"file_id": file_id}, timeout=10)
			body = response.json() if hasattr(response, "json") else response
			if not isinstance(body, Mapping) or not body.get("ok"):
				return None
			file_path = (body.get("result") or {}).get("file_path")
			if not file_path:
				return None

			download_url = f"{TELEGRAM_API_BASE}/file/bot{self._token}/{file_path}"
			file_response = self._http_get(download_url, timeout=15)
			content = file_response.content if hasattr(file_response, "content") else file_response
			if not content:
				return None

			from frappe.utils.file_manager import save_file

			saved_filename = filename or file_path.rsplit("/", 1)[-1] or f"{kind}-{file_id}"
			saved = save_file(saved_filename, content, None, None, is_private=True)
			return getattr(saved, "name", None)
		except Exception:
			# Import errors (no Frappe context, e.g. unit tests exercising the
			# adapter standalone), network errors, and malformed responses all
			# degrade to "no File doc" rather than breaking event normalization.
			return None

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send a Telegram ``sendMessage`` text reply using the bot token."""
		url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
		data: dict[str, Any] = {
			"chat_id": reply.conversation_id,
			"text": reply.text,
		}
		if reply.reply_to_provider_message_id:
			try:
				data["reply_to_message_id"] = int(reply.reply_to_provider_message_id)
			except (TypeError, ValueError):
				pass

		response = self._http_post(url, json_data=data, timeout=10)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping) or not body.get("ok"):
			description = body.get("description") if isinstance(body, Mapping) else "Telegram API rejected reply"
			raise ValueError(f"Telegram sendMessage failed: {description}")

		result = body.get("result") or {}
		message_id = result.get("message_id")
		if message_id is None:
			raise ValueError("Telegram sendMessage response did not include a message_id")
		return OutboundDelivery(str(message_id), provider_response=body)
