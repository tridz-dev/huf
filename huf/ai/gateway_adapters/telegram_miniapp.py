# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Mini App ``initData`` validation (https://core.telegram.org/bots/webapps).

Pure at module level (no Frappe import). Bot-token validation: ``secret = HMAC_SHA256(key="WebAppData",
msg=bot_token)``; ``hash == hex(HMAC_SHA256(key=secret, msg=data_check_string))`` where the
data-check-string is every field except ``hash`` sorted by key as ``key=value`` joined with ``\\n``.
Third-party validation (``validate_init_data_third_party``) checks the Ed25519 ``signature`` instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode

DEFAULT_MAX_AGE_SECONDS = 3600
FUTURE_SKEW_SECONDS = 60
# Ed25519 public keys published by Telegram for third-party validation.
TELEGRAM_PUBLIC_KEY_PROD = "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d"
TELEGRAM_PUBLIC_KEY_TEST = "40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec"


class MiniAppAuthError(Exception):
	"""initData failed validation."""


@dataclass(frozen=True)
class MiniAppUser:
	user_id: int
	username: str = ""
	first_name: str = ""
	last_name: str = ""
	language_code: str = ""
	start_param: str = ""
	chat_type: str = ""
	chat_instance: str = ""
	can_send_after: int | None = None
	query_id: str = ""
	auth_date: int = 0


def _parse(init_data: str) -> dict[str, str]:
	if not isinstance(init_data, str) or not init_data.strip():
		raise MiniAppAuthError("initData is empty")
	pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
	fields: dict[str, str] = {}
	for key, value in pairs:
		if key in fields:
			raise MiniAppAuthError(f"duplicate initData field: {key}")
		fields[key] = value
	return fields


def _data_check_string(fields: dict[str, str], exclude: tuple[str, ...]) -> str:
	return "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k not in exclude)


def _secret_key(bot_token: str) -> bytes:
	return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _compute_hash(fields: dict[str, str], bot_token: str) -> str:
	dcs = _data_check_string(fields, ("hash",)).encode("utf-8")
	return hmac.new(_secret_key(bot_token), dcs, hashlib.sha256).hexdigest()


def _check_age(fields: dict[str, str], max_age_seconds: int, now: float | None) -> int:
	raw = fields.get("auth_date", "")
	try:
		auth_date = int(raw)
	except ValueError:
		raise MiniAppAuthError("auth_date missing or invalid") from None
	current = time.time() if now is None else now
	if auth_date > current + FUTURE_SKEW_SECONDS:
		raise MiniAppAuthError("auth_date is in the future")
	if current - auth_date > max_age_seconds:
		raise MiniAppAuthError("initData expired")
	return auth_date


def _build_user(fields: dict[str, str], auth_date: int) -> MiniAppUser:
	try:
		user = json.loads(fields.get("user", ""))
		user_id = int(user["id"])
	except (ValueError, KeyError, TypeError):
		raise MiniAppAuthError("initData has no valid user") from None
	if not isinstance(user, dict):
		raise MiniAppAuthError("initData has no valid user")
	cas = fields.get("can_send_after")
	try:
		can_send_after = int(cas) if cas not in (None, "") else None
	except ValueError:
		can_send_after = None
	return MiniAppUser(
		user_id=user_id,
		username=str(user.get("username") or ""),
		first_name=str(user.get("first_name") or ""),
		last_name=str(user.get("last_name") or ""),
		language_code=str(user.get("language_code") or ""),
		start_param=fields.get("start_param", ""),
		chat_type=fields.get("chat_type", ""),
		chat_instance=fields.get("chat_instance", ""),
		can_send_after=can_send_after,
		query_id=fields.get("query_id", ""),
		auth_date=auth_date,
	)


def validate_init_data(
	init_data: str,
	bot_token: str,
	*,
	max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
	now: float | None = None,
) -> MiniAppUser:
	"""Validate ``initData`` against the bot token; raise ``MiniAppAuthError`` on any failure."""
	if not bot_token:
		raise MiniAppAuthError("bot token is not configured")
	fields = _parse(init_data)
	received = fields.get("hash", "")
	if not received:
		raise MiniAppAuthError("initData has no hash")
	if not hmac.compare_digest(_compute_hash(fields, bot_token).encode(), received.lower().encode()):
		raise MiniAppAuthError("initData hash mismatch")
	return _build_user(fields, _check_age(fields, max_age_seconds, now))


def validate_init_data_third_party(
	init_data: str,
	bot_id: int | str,
	*,
	public_key_hex: str = TELEGRAM_PUBLIC_KEY_PROD,
	max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
	now: float | None = None,
) -> MiniAppUser:
	"""Validate via Telegram's Ed25519 ``signature`` (no bot token needed). Needs ``cryptography``."""
	fields = _parse(init_data)
	sig = fields.get("signature", "")
	if not sig:
		raise MiniAppAuthError("initData has no signature")
	try:
		from cryptography.exceptions import InvalidSignature
		from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
	except ImportError:
		raise MiniAppAuthError("Ed25519 validation unavailable (cryptography not installed)") from None
	message = f"{bot_id}:WebAppData\n{_data_check_string(fields, ('hash', 'signature'))}".encode()
	try:
		raw_sig = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
		Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(raw_sig, message)
	except (InvalidSignature, ValueError):
		raise MiniAppAuthError("initData signature mismatch") from None
	return _build_user(fields, _check_age(fields, max_age_seconds, now))


def build_init_data_for_test(
	bot_token: str,
	*,
	user: dict[str, Any] | None = None,
	auth_date: int | None = None,
	extra: dict[str, str] | None = None,
) -> str:
	"""Generate a valid initData query string (tests / local dev only)."""
	fields: dict[str, str] = {
		"user": json.dumps(user or {"id": 12345, "first_name": "Test"}, separators=(",", ":"), ensure_ascii=False),
		"auth_date": str(int(time.time()) if auth_date is None else auth_date),
	}
	fields.update(extra or {})
	fields["hash"] = _compute_hash(fields, bot_token)
	return urlencode(fields)


def web_app_button(url: str, text: str) -> dict[str, Any]:
	"""InlineKeyboardButton opening a Mini App (delegates to telegram_keyboards)."""
	from huf.ai.gateway_adapters import telegram_keyboards

	return telegram_keyboards.web_app_button(text, url)


def menu_button_payload(url: str, text: str, chat_id: int | str | None = None) -> dict[str, Any]:
	"""``setChatMenuButton`` payload with a web_app menu button."""
	payload: dict[str, Any] = {"menu_button": {"type": "web_app", "text": text, "web_app": {"url": url}}}
	if chat_id is not None:
		payload["chat_id"] = chat_id
	return payload


def authenticate(init_data: str, gateway_name: str) -> MiniAppUser:
	"""Validate initData with the Telegram Gateway's bot token (not whitelisted here; WP-9 exposes it)."""
	import frappe
	from frappe import _

	from huf.ai.gateway_webhook import _gateway_credentials

	gateway = frappe.get_doc("Gateway", gateway_name)
	if gateway.provider != "Telegram":
		frappe.throw(_("Not a Telegram gateway."), frappe.ValidationError)
	token = (_gateway_credentials(gateway).get("token") or "").strip()
	try:
		return validate_init_data(init_data, token)
	except MiniAppAuthError as exc:
		frappe.throw(_("Mini App authentication failed: {0}").format(str(exc)), frappe.AuthenticationError)
