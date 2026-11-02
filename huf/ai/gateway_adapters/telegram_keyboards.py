# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Inline / reply keyboard builders and signed, short, stateless ``callback_data``.

Pure; no Frappe imports. Telegram limits ``callback_data`` to 1-64 bytes, so the signature is a
truncated HMAC-SHA256 (72 bits) and the payload budget is ``64 - 1 - SIG_LEN`` bytes. An optional
``context`` (e.g. the chat id) is mixed into the MAC but not transmitted, binding a button to the
chat it was issued in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Mapping, Sequence

CALLBACK_DATA_MAX_BYTES = 64
SIG_LEN = 12
SEPARATOR = "|"
MAX_PAYLOAD_BYTES = CALLBACK_DATA_MAX_BYTES - len(SEPARATOR) - SIG_LEN


def derive_callback_key(gateway_secret: str) -> bytes:
	"""Per-gateway HMAC key derived from a gateway secret (domain-separated)."""
	if not gateway_secret:
		raise ValueError("A gateway secret is required to sign callback data")
	return hashlib.sha256(b"huf-telegram-callback-v1:" + gateway_secret.encode("utf-8")).digest()


def _mac(key: bytes, payload: str, context: str) -> str:
	digest = hmac.new(key, f"{context}\x00{payload}".encode("utf-8"), hashlib.sha256).digest()
	return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:SIG_LEN]


def sign_callback(key: bytes, payload: str, *, context: str = "") -> str:
	"""Return ``payload|sig`` (<= 64 bytes) or raise ``ValueError`` if the payload is too long."""
	if not payload:
		raise ValueError("callback payload is required")
	if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
		raise ValueError(f"callback payload exceeds {MAX_PAYLOAD_BYTES} bytes")
	return f"{payload}{SEPARATOR}{_mac(key, payload, context)}"


def verify_callback(key: bytes, data: str, *, context: str = "") -> str | None:
	"""Return the payload when ``data`` carries a valid signature, else ``None`` (constant-time)."""
	if not isinstance(data, str) or SEPARATOR not in data:
		return None
	payload, _, sig = data.rpartition(SEPARATOR)
	if not payload or len(sig) != SIG_LEN:
		return None
	return payload if hmac.compare_digest(sig, _mac(key, payload, context)) else None


# -- inline keyboard ---------------------------------------------------------------------------


def callback_button(text: str, signed_data: str) -> dict[str, Any]:
	if not 1 <= len(signed_data.encode("utf-8")) <= CALLBACK_DATA_MAX_BYTES:
		raise ValueError("callback_data must be 1-64 bytes")
	return {"text": text, "callback_data": signed_data}


def url_button(text: str, url: str) -> dict[str, Any]:
	return {"text": text, "url": url}


def web_app_button(text: str, url: str) -> dict[str, Any]:
	return {"text": text, "web_app": {"url": url}}


def inline_keyboard(rows: Sequence[Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
	return {"inline_keyboard": [[dict(b) for b in row] for row in rows if row]}


# -- reply keyboard ----------------------------------------------------------------------------


def reply_keyboard(
	rows: Sequence[Sequence[str | Mapping[str, Any]]],
	*,
	resize: bool = True,
	one_time: bool = False,
	placeholder: str | None = None,
	persistent: bool = False,
	selective: bool = False,
) -> dict[str, Any]:
	markup: dict[str, Any] = {
		"keyboard": [[{"text": b} if isinstance(b, str) else dict(b) for b in row] for row in rows if row],
		"resize_keyboard": resize,
		"one_time_keyboard": one_time,
	}
	if placeholder:
		markup["input_field_placeholder"] = placeholder[:64]
	if persistent:
		markup["is_persistent"] = True
	if selective:
		markup["selective"] = True
	return markup


def remove_keyboard(*, selective: bool = False) -> dict[str, Any]:
	markup: dict[str, Any] = {"remove_keyboard": True}
	if selective:
		markup["selective"] = True
	return markup


def force_reply(*, placeholder: str | None = None, selective: bool = False) -> dict[str, Any]:
	markup: dict[str, Any] = {"force_reply": True}
	if placeholder:
		markup["input_field_placeholder"] = placeholder[:64]
	if selective:
		markup["selective"] = True
	return markup
