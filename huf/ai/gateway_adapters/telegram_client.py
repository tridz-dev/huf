# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Bot API client: the single place that talks HTTP to ``api.telegram.org``.

No Frappe imports. HTTP is injected (``http_post`` / ``http_get``) so tests use an in-memory
fake Bot API. The bot token is redacted from every error message and log string produced here.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping

TELEGRAM_API_BASE = "https://api.telegram.org"
TEST_ENV_SEGMENT = "test"


def truthy_flag(value: Any) -> bool:
	"""Interpret a gateway/credential flag (``1``, ``"1"``, ``True``, ``"true"``) as a bool."""
	if isinstance(value, str):
		return value.strip().lower() in {"1", "true", "yes", "on"}
	return bool(value)


def bot_api_url(token: str, method: str, *, test_environment: bool = False) -> str:
	"""The one Bot API URL builder. Telegram's test servers add a ``/test/`` segment after the token."""
	segment = f"/{TEST_ENV_SEGMENT}" if test_environment else ""
	return f"{TELEGRAM_API_BASE}/bot{token}{segment}/{method}"


def bot_file_url(token: str, file_path: str, *, test_environment: bool = False) -> str:
	"""The one file-download URL builder (``/file/bot<token>[/test]/<path>``)."""
	segment = f"/{TEST_ENV_SEGMENT}" if test_environment else ""
	return f"{TELEGRAM_API_BASE}/file/bot{token}{segment}/{file_path}"


# Updates the gateway asks Telegram to deliver (setWebhook ``allowed_updates``).
ALLOWED_UPDATES: tuple[str, ...] = (
	"message",
	"edited_message",
	"callback_query",
	"inline_query",
	"chosen_inline_result",
	"chat_join_request",
	"chat_member",
	"my_chat_member",
	"message_reaction",
	"message_reaction_count",
	"channel_post",
	"business_connection",
	"business_message",
	"edited_business_message",
	"deleted_business_messages",
	"stopped_message_generation",
	"guest_message",
)


def redact_token(text: Any, token: str) -> str:
	"""Remove the bot token (and its secret half) from any string."""
	value = str(text)
	if token:
		value = value.replace(token, "<redacted-token>")
		secret = token.split(":", 1)[-1]
		if len(secret) >= 8:
			value = value.replace(secret, "<redacted>")
	return value


# Bot API error descriptions -> a stable ``kind``. First match wins; descriptions are matched lower-cased.
# Only the user-blocked/deactivated kinds mean "this person is unreachable"; only the room kinds mean "the bot is
# no longer in that chat". Everything about rights or markup is a configuration problem and never an opt-out.
_ERROR_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
	("blocked", ("bot was blocked by the user",)),
	("user_deactivated", ("user is deactivated",)),
	(
		"room_removed",
		(
			"bot was kicked from the",
			"bot is not a member of the",
			"the group chat was deleted",
		),
	),
	("cannot_initiate", ("bot can't initiate conversation", "bot can't send messages to bots")),
	(
		"missing_rights",
		(
			"not enough rights",
			"have no rights to",
			"chat_write_forbidden",
			"chat_send_plain_forbidden",
			"chat_send_media_forbidden",
			"chat_admin_required",
			"need administrator rights",
			"rights to send",
		),
	),
	("chat_not_found", ("chat not found", "peer_id_invalid", "chat_id is empty")),
	("button_url_invalid", ("button_url_invalid",)),
	("web_app_url_invalid", ("web_app_url_invalid",)),
	("button_type_invalid", ("button_type_invalid",)),
	("bot_domain_invalid", ("bot_domain_invalid",)),
	("reply_markup_too_long", ("reply_markup_too_long",)),
	("message_to_edit_not_found", ("message to edit not found",)),
	("message_too_long", ("message is too long", "message_too_long")),
	("caption_too_long", ("message caption is too long", "media_caption_too_long")),
	("parse_error", ("can't parse entities", "can't find end of the entity", "unsupported start tag")),
	("message_not_modified", ("message is not modified",)),
)

_OPERATOR_TEXT = {
	"blocked": "the user blocked the bot",
	"user_deactivated": "the user's account is deactivated",
	"room_removed": "the bot was removed from this chat (or the chat was deleted)",
	"cannot_initiate": "the bot cannot start this conversation; the user has to message the bot first",
	"missing_rights": (
		"the bot lacks a required right in this chat. Grant the bot the needed right "
		"(for example Post Messages, Send Media or admin rights) in the chat's administrator settings"
	),
	"chat_not_found": "chat not found",
	"button_url_invalid": "Telegram rejected a button URL (BUTTON_URL_INVALID); use a full https:// or tg:// URL",
	"web_app_url_invalid": "Telegram rejected a Web App URL (WEB_APP_URL_INVALID); it must be an https:// URL",
	"button_type_invalid": (
		"Telegram does not allow this button type in this chat (BUTTON_TYPE_INVALID); "
		"use callback or url buttons here"
	),
	"bot_domain_invalid": (
		"the login URL domain is not linked to the bot (BOT_DOMAIN_INVALID); set it with /setdomain in BotFather"
	),
	"reply_markup_too_long": (
		"the keyboard is too large (REPLY_MARKUP_TOO_LONG); use fewer buttons and callback data under 64 bytes"
	),
	"message_to_edit_not_found": "the message to edit no longer exists (deleted or too old)",
	"message_too_long": "the message is longer than Telegram allows (MESSAGE_TOO_LONG)",
	"caption_too_long": "the caption is longer than Telegram allows (1024 characters)",
	"rate_limited": "rate limited",
}


class TelegramApiError(ValueError):
	"""A failed Bot API call, classified. Subclasses ValueError for adapter-contract compatibility."""

	def __init__(
		self,
		method: str,
		description: str,
		*,
		error_code: int | None = None,
		retry_after: int | None = None,
		migrate_to_chat_id: int | None = None,
	) -> None:
		self.method = method
		self.description = description
		self.error_code = error_code
		self.retry_after = retry_after
		self.migrate_to_chat_id = migrate_to_chat_id
		super().__init__(f"Telegram {method} failed: {description}")

	@property
	def _lower(self) -> str:
		return (self.description or "").lower()

	@property
	def kind(self) -> str | None:
		"""Stable classification of the description (``None`` = unclassified). Flood control is ``rate_limited``."""
		d = self._lower
		for kind, needles in _ERROR_KINDS:
			if any(n in d for n in needles):
				return kind
		if self.retry_after is not None or self.error_code == 429:
			return "rate_limited"
		return None

	@property
	def blocked_by_user(self) -> bool:
		"""The user blocked the bot or deactivated their account: that person is unsendable."""
		return self.kind in ("blocked", "user_deactivated")

	@property
	def room_removed(self) -> bool:
		"""The bot was kicked from / is not a member of the group or channel, or the group was deleted."""
		return self.kind == "room_removed"

	@property
	def missing_rights(self) -> bool:
		return self.kind == "missing_rights"

	@property
	def chat_not_found(self) -> bool:
		return self.kind == "chat_not_found"

	@property
	def parse_error(self) -> bool:
		return self.kind == "parse_error"

	@property
	def flood_control(self) -> bool:
		return self.retry_after is not None or self.error_code == 429

	@property
	def message_not_modified(self) -> bool:
		return self.kind == "message_not_modified"

	@property
	def message_too_long(self) -> bool:
		return self.kind == "message_too_long"

	@property
	def caption_too_long(self) -> bool:
		return self.kind == "caption_too_long"

	@property
	def code(self) -> str:
		"""Operator-facing error code (stable string)."""
		return "rate_limited" if self.flood_control else (self.kind or "telegram_error")

	@property
	def operator_message(self) -> str:
		"""Actionable, token-free text for the operator (descriptions are redacted when the error is built)."""
		text = _OPERATOR_TEXT.get(self.code)
		return (
			f"Telegram delivery failed: {text}" if text else f"Telegram delivery failed: {self.description}"
		)

	@property
	def retryable(self) -> bool:
		"""Safe to retry later: flood control and 5xx. Every classified permanent failure is not."""
		if self.flood_control:
			return True
		if self.kind is not None:
			return False
		return self.error_code is not None and self.error_code >= 500


def _requests_post(
	url: str,
	*,
	json_data: Mapping[str, Any] | None = None,
	data: Mapping[str, Any] | None = None,
	files: Mapping[str, Any] | None = None,
	timeout: int = 10,
) -> Any:
	"""Lazily import requests so the SDK itself has no import-time dependency."""
	import requests

	if files:
		return requests.post(url, data=data, files=files, timeout=timeout)
	return requests.post(url, json=json_data, timeout=timeout)


def _requests_get(url: str, *, timeout: int = 15) -> Any:
	import requests

	return requests.get(url, timeout=timeout)


class TelegramBotClient:
	"""Thin, redacting, classifying wrapper over the Bot API."""

	def __init__(
		self,
		token: str,
		*,
		http_post: Callable[..., Any] = _requests_post,
		http_get: Callable[..., Any] = _requests_get,
		timeout: int = 10,
		max_flood_retries: int = 1,
		max_flood_wait: int = 5,
		on_chat_migrated: Callable[[str, str], None] | None = None,
		sleep: Callable[[float], None] = time.sleep,
		test_environment: bool = False,
	) -> None:
		if not token:
			raise ValueError("Telegram bot token is required")
		self._token = token
		self._test_environment = bool(test_environment)
		self._http_post = http_post
		self._http_get = http_get
		self._timeout = timeout
		self._max_flood_retries = max_flood_retries
		self._max_flood_wait = max_flood_wait
		self._sleep = sleep
		# Called as ``(old_chat_id, new_chat_id)`` when Telegram reports a group became a supergroup.
		self.on_chat_migrated = on_chat_migrated

	def redact(self, text: Any) -> str:
		return redact_token(text, self._token)

	def _url(self, method: str) -> str:
		return bot_api_url(self._token, method, test_environment=self._test_environment)

	@property
	def test_environment(self) -> bool:
		return self._test_environment

	def call(
		self,
		method: str,
		payload: Mapping[str, Any] | None = None,
		*,
		files: Mapping[str, Any] | None = None,
	) -> Any:
		"""Call a Bot API method and return ``result``. Raises ``TelegramApiError`` on failure.

		With ``files`` the request is multipart; non-scalar payload values are JSON-encoded.
		Flood control: one short in-client retry (``retry_after <= max_flood_wait``); longer waits are left to the
		caller's scheduled retry. Group -> supergroup migration: retried once with the new ``chat_id`` after
		``on_chat_migrated(old, new)`` has been told (so the caller can re-key its state).
		"""
		payload = dict(payload or {})
		flood_attempts = 0
		migrated = False
		while True:
			try:
				return self._call_once(method, payload, files)
			except TelegramApiError as exc:
				if (
					exc.retry_after is not None
					and flood_attempts < self._max_flood_retries
					and exc.retry_after <= self._max_flood_wait
				):
					flood_attempts += 1
					self._sleep(exc.retry_after)
					continue
				new_id = exc.migrate_to_chat_id
				if new_id is not None and not migrated and payload.get("chat_id") is not None:
					old_id = payload["chat_id"]
					if str(old_id) != str(new_id):
						migrated = True
						self._notify_migrated(old_id, new_id)
						payload["chat_id"] = new_id
						continue
				raise

	def _notify_migrated(self, old_id: Any, new_id: Any) -> None:
		if not self.on_chat_migrated:
			return
		try:
			self.on_chat_migrated(str(old_id), str(new_id))
		except Exception:  # persisting the migration must never block the delivery itself
			pass

	def _call_once(self, method: str, payload: Mapping[str, Any], files: Mapping[str, Any] | None) -> Any:
		try:
			if files:
				form = {
					k: (v if isinstance(v, (str, int, float)) else json.dumps(v))
					for k, v in payload.items()
					if v is not None
				}
				response = self._http_post(self._url(method), data=form, files=files, timeout=self._timeout)
			else:
				response = self._http_post(self._url(method), json_data=dict(payload), timeout=self._timeout)
		except TelegramApiError:
			raise
		except Exception as exc:  # network error text may embed the URL (and token)
			raise TelegramApiError(method, self.redact(f"network error: {exc}"), error_code=599) from None
		body = self._body(response)
		if isinstance(body, Mapping) and body.get("ok"):
			return body.get("result")
		status = getattr(response, "status_code", None)
		if isinstance(body, Mapping):
			params = body.get("parameters") or {}
			raise TelegramApiError(
				method,
				self.redact(body.get("description") or "Telegram API rejected the request"),
				error_code=body.get("error_code") or (status if isinstance(status, int) else None),
				retry_after=_int_or_none(params.get("retry_after")),
				migrate_to_chat_id=_int_or_none(params.get("migrate_to_chat_id")),
			)
		raise TelegramApiError(
			method, "non-JSON response from Telegram", error_code=status if isinstance(status, int) else None
		)

	@staticmethod
	def _body(response: Any) -> Any:
		if isinstance(response, Mapping):
			return response
		try:
			return response.json()
		except Exception:
			return None

	# -- files ---------------------------------------------------------------------------------

	def download_file(self, file_id: str, *, timeout: int = 15) -> tuple[bytes, str]:
		"""Resolve ``file_id`` via getFile and return ``(content, file_path)``."""
		info = self.call("getFile", {"file_id": file_id}) or {}
		file_path = info.get("file_path")
		if not file_path:
			raise TelegramApiError("getFile", "no file_path in response")
		url = bot_file_url(self._token, file_path, test_environment=self._test_environment)
		try:
			response = self._http_get(url, timeout=timeout)
		except Exception as exc:
			raise TelegramApiError(
				"getFile", self.redact(f"download failed: {exc}"), error_code=599
			) from None
		status = getattr(response, "status_code", None)
		if isinstance(status, int) and status >= 400:
			raise TelegramApiError("getFile", f"download failed: HTTP {status}", error_code=status)
		content = response.content if hasattr(response, "content") else response
		if not content:
			raise TelegramApiError("getFile", "empty file download")
		return content, file_path

	# -- bot / webhook administration ---------------------------------------------------------

	def get_me(self) -> Mapping[str, Any]:
		return self.call("getMe")

	def get_webhook_info(self) -> Mapping[str, Any]:
		return self.call("getWebhookInfo")

	def set_webhook(
		self,
		url: str,
		*,
		secret_token: str,
		allowed_updates: tuple[str, ...] | list[str] = ALLOWED_UPDATES,
		drop_pending_updates: bool = False,
		max_connections: int | None = None,
	) -> Any:
		payload: dict[str, Any] = {
			"url": url,
			"secret_token": secret_token,
			"allowed_updates": list(allowed_updates),
			"drop_pending_updates": drop_pending_updates,
		}
		if max_connections:
			payload["max_connections"] = max_connections
		return self.call("setWebhook", payload)

	def delete_webhook(self, *, drop_pending_updates: bool = False) -> Any:
		return self.call("deleteWebhook", {"drop_pending_updates": drop_pending_updates})


def _int_or_none(value: Any) -> int | None:
	try:
		return int(value) if value is not None else None
	except (TypeError, ValueError):
		return None
