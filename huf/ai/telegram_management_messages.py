# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram management API for the Messages, Access, Bindings and Send tabs.

Gateway admins only (same permission pattern as ``telegram_management``). Thin wrappers over the
existing services: Gateway Events (message log), ``gateway_service`` access entries,
``telegram_admin`` bindings and the business connection store. The Send panel can reach only an
Approved sender, or the caller's own bound chat; it goes through ``TelegramSender`` and writes an
audit row without the message body. The bot token never leaves the server.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from typing import Any

import frappe
from frappe import _

from huf.ai.telegram_management import (
	TELEGRAM_PROVIDER,
	_client,
	_credentials,
	_error,
	_load_gateway,
	_safe_text,
)

MAX_LIMIT = 100
DEFAULT_LIMIT = 25
MAX_TEXT = 4096
MAX_CAPTION = 1024
MAX_BYTES = {"photo": 10 * 1024 * 1024, "document": 50 * 1024 * 1024, "voice": 20 * 1024 * 1024}
SEND_KINDS = ("text", "photo", "document", "voice")
MESSAGE_KINDS = ("text", "media", "voice", "callback", "reaction", "business", "inline", "guest", "join")
_MEDIA_FIELDS = ("photo", "document", "video", "audio", "video_note", "sticker", "animation")
_ALLOWED_MIME = {
	"photo": ("image/jpeg", "image/png", "image/webp"),
	"voice": ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/opus"),
}
_TYPE_HELP = {
	"photo": "A photo must be a JPG, PNG or WebP image.",
	"voice": "A voice message must be an OGG, MP3 or M4A audio file.",
}
_DENIED_EXT = (".exe", ".bat", ".cmd", ".sh", ".js", ".msi", ".scr", ".com", ".vbs", ".ps1")
_EVENT_FIELDS = [
	"name",
	"creation",
	"status",
	"sender_id",
	"message_text",
	"reply_status",
	"reply_message_id",
	"delivery_error",
	"error_message",
	"agent_run",
	"target_agent",
	"raw_payload",
	"conversation_id",
]


def _require_admin(gateway: str | None):
	"""Gateway row (dict) after the admin check, or an error dict."""
	return _load_gateway(gateway)


# -- classification (pure) -----------------------------------------------------------------------


def _raw_dict(raw: Any) -> dict[str, Any]:
	if isinstance(raw, dict):
		return raw
	try:
		value = json.loads(raw) if raw else {}
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


def classify_kind(raw: Any) -> str:
	"""One of ``MESSAGE_KINDS`` for a stored raw Update."""
	update = _raw_dict(raw)
	for key, kind in (
		("callback_query", "callback"),
		("message_reaction", "reaction"),
		("business_message", "business"),
		("edited_business_message", "business"),
		("inline_query", "inline"),
		("chosen_inline_result", "inline"),
		("guest_message", "guest"),
		("chat_join_request", "join"),
	):
		if key in update:
			return kind
	for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
		msg = update.get(key)
		if isinstance(msg, dict):
			if msg.get("voice"):
				return "voice"
			if any(msg.get(f) for f in _MEDIA_FIELDS):
				return "media"
			return "text"
	return "text"


def update_kind(raw: Any) -> str:
	"""The raw Update field name (e.g. ``message``, ``callback_query``)."""
	for key in _raw_dict(raw):
		if key != "update_id":
			return str(key)
	return ""


def _message_of(update: dict[str, Any]) -> dict[str, Any]:
	for key in (
		"message",
		"edited_message",
		"channel_post",
		"edited_channel_post",
		"business_message",
		"edited_business_message",
	):
		if isinstance(update.get(key), dict):
			return update[key]
	cq = update.get("callback_query")
	if isinstance(cq, dict):
		return cq
	return {}


def display_name(raw: Any) -> str:
	update = _raw_dict(raw)
	msg = _message_of(update)
	user = msg.get("from") if isinstance(msg.get("from"), dict) else {}
	if not user:
		for key in ("message_reaction", "chat_join_request", "inline_query"):
			if isinstance(update.get(key), dict):
				user = update[key].get("user") or update[key].get("from") or {}
				break
	name = " ".join(str(user.get(k)) for k in ("first_name", "last_name") if user.get(k))
	return name or (f"@{user['username']}" if user.get("username") else "")


def attachments_of(raw: Any) -> list[dict[str, Any]]:
	from huf.ai.gateway_adapters.telegram_inbound import media_refs

	msg = _message_of(_raw_dict(raw))
	refs = media_refs(msg) if msg else []
	# File ids are bot-scoped identifiers; the UI needs only the shape.
	return [{k: r.get(k) for k in ("kind", "mime_type", "filename", "file_size")} for r in refs]


def _clean_error(value: Any, gateway: str | None = None) -> str:
	import re

	text = str(value or "")
	text = re.sub(r"\d{6,}:[A-Za-z0-9_-]{30,}", "***", text)
	return text[:500]


def event_summary(row: dict[str, Any]) -> dict[str, Any]:
	raw = row.get("raw_payload")
	return {
		"name": row["name"],
		"received_at": str(row.get("creation") or ""),
		"kind": classify_kind(raw),
		"text": (row.get("message_text") or "")[:500],
		"sender_id": row.get("sender_id") or "",
		"sender_name": display_name(raw),
		"status": row.get("status") or "",
		"reply_status": row.get("reply_status") or "",
		"error": _clean_error(row.get("error_message") or row.get("delivery_error")),
		"agent_run": row.get("agent_run") or None,
		"agent": row.get("target_agent") or None,
	}


# -- cursor --------------------------------------------------------------------------------------


def _encode_cursor(creation: Any, name: str) -> str:
	return base64.urlsafe_b64encode(json.dumps([str(creation), name]).encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
	if not cursor:
		return None
	try:
		creation, name = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
		return str(creation), str(name)
	except Exception:
		return None


def _limit(value: Any) -> int:
	try:
		return max(1, min(int(value), MAX_LIMIT))
	except (TypeError, ValueError):
		return DEFAULT_LIMIT


def _filters(filters: Any) -> dict[str, Any]:
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except ValueError:
			filters = {}
	return filters if isinstance(filters, dict) else {}


@frappe.whitelist()
def list_messages(
	gateway: str | None = None, filters: Any = None, limit: Any = None, cursor: str | None = None
) -> dict[str, Any]:
	"""Inbound Gateway Events, newest first, with keyset pagination. Kind is derived from the raw Update."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	f = _filters(filters)
	kind = f.get("kind") or ""
	if kind and kind not in MESSAGE_KINDS:
		return _error("invalid_kind", "Unknown message kind.")
	n = _limit(limit)
	where: dict[str, Any] = {"gateway": row["name"]}
	if f.get("status"):
		where["status"] = str(f["status"])
	if f.get("reply_status"):
		where["reply_status"] = str(f["reply_status"])
	or_filters = None
	q = str(f.get("q") or "").strip()
	if q:
		or_filters = [["message_text", "like", f"%{q}%"], ["sender_id", "like", f"%{q}%"]]
	bound = _decode_cursor(cursor)
	items: list[dict[str, Any]] = []
	has_more = False
	batch = n * 3 if kind else n + 1
	for _round in range(20):
		flt = [["Gateway Event", k, "=", v] for k, v in where.items()]
		if bound:
			flt.append(["Gateway Event", "creation", "<=", bound[0]])
		rows = (
			frappe.get_all(
				"Gateway Event",
				filters=flt,
				or_filters=or_filters,
				fields=_EVENT_FIELDS,
				order_by="creation desc, name desc",
				limit_page_length=batch,
			)
			or []
		)
		fetched = len(rows)
		last_raw = rows[-1] if rows else None
		if bound:  # same-creation ties: keep strictly after the cursor row
			rows = [r for r in rows if (str(r["creation"]), r["name"]) < bound]
		for r in rows:
			if kind and classify_kind(r.get("raw_payload")) != kind:
				continue
			if len(items) == n:
				has_more = True
				break
			items.append(r)
		if has_more or fetched < batch or last_raw is None:
			break
		bound = (str(last_raw["creation"]), last_raw["name"])
	next_cursor = _encode_cursor(items[-1]["creation"], items[-1]["name"]) if has_more and items else None
	return {
		"success": True,
		"items": [event_summary(r) for r in items],
		"next_cursor": next_cursor,
		"has_more": has_more,
	}


@frappe.whitelist()
def get_message(gateway: str | None = None, event: str | None = None) -> dict[str, Any]:
	"""Detail of one event: raw update kind, attachments, reply parts, redacted errors."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	data = (
		frappe.db.get_value(
			"Gateway Event", event, _EVENT_FIELDS + ["gateway", "reply_message_id"], as_dict=True
		)
		if event
		else None
	)
	if not data or data.get("gateway") != row["name"]:
		return _error("not_found", "Message not found.")
	parts: list[int] = []
	try:
		from huf.ai.gateway_adapters.telegram_messages import sent_for_event

		parts = sent_for_event(row["name"], data["name"])
	except Exception:
		parts = []
	summary = event_summary(data)
	return {
		"success": True,
		"message": {
			**summary,
			"text": data.get("message_text") or "",
			"update_kind": update_kind(data.get("raw_payload")),
			"chat_id": data.get("conversation_id") or "",
			"attachments": attachments_of(data.get("raw_payload")),
			"reply": {
				"status": data.get("reply_status") or "",
				"message_id": data.get("reply_message_id") or None,
				"parts": [{"message_id": p} for p in parts],
				"error": _clean_error(data.get("delivery_error")),
			},
		},
	}


# -- access --------------------------------------------------------------------------------------


def _entry_in_gateway(entry: str | None, gateway: str) -> bool:
	if not entry:
		return False
	return frappe.db.get_value("Gateway Access Entry", entry, "gateway") == gateway


@frappe.whitelist()
def list_access(gateway: str | None = None, state: str = "Pending") -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	from huf.ai import gateway_service

	entries = gateway_service.list_gateway_access_entries(gateway=row["name"], state=state or "")
	return {"success": True, "items": entries}


@frappe.whitelist(methods=["POST"])
def approve_access(gateway: str | None = None, entry: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if not _entry_in_gateway(entry, row["name"]):
		return _error("not_found", "Access entry not found.")
	from huf.ai import gateway_service

	res = gateway_service.approve_gateway_pairing(entry, gateway=row["name"])
	return {"success": True, "name": res.get("name"), "state": res.get("state")}


@frappe.whitelist(methods=["POST"])
def revoke_access(gateway: str | None = None, entry: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if not _entry_in_gateway(entry, row["name"]):
		return _error("not_found", "Access entry not found.")
	from huf.ai import gateway_service

	res = gateway_service.revoke_gateway_access_entry(entry)
	return {"success": True, "name": res.get("name"), "state": res.get("state")}


# -- bindings ------------------------------------------------------------------------------------


@frappe.whitelist()
def list_bindings(gateway: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	rows = (
		frappe.get_all(
			"Telegram Admin Binding",
			filters={"gateway": row["name"]},
			fields=[
				"name",
				"frappe_user",
				"telegram_user_id",
				"telegram_username",
				"role_scope",
				"is_active",
				"paired_at",
				"last_seen_at",
			],
			order_by="creation desc",
			limit_page_length=200,
		)
		or []
	)
	return {
		"success": True,
		"items": [
			{
				**r,
				"is_active": bool(r.get("is_active")),
				"paired_at": str(r["paired_at"]) if r.get("paired_at") else None,
				"last_seen_at": str(r["last_seen_at"]) if r.get("last_seen_at") else None,
			}
			for r in rows
		],
	}


@frappe.whitelist(methods=["POST"])
def revoke_binding(gateway: str | None = None, name: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if not name or frappe.db.get_value("Telegram Admin Binding", name, "gateway") != row["name"]:
		return _error("not_found", "Binding not found.")
	from huf.ai import telegram_admin

	telegram_admin.revoke_binding(name)
	return {"success": True}


@frappe.whitelist(methods=["POST"])
def create_binding_code_for_me(gateway: str | None = None, role_scope: str = "Viewer") -> dict[str, Any]:
	"""Mint a one-time code for the caller. The code is shown once; it is not stored or logged here."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	from huf.ai import telegram_admin

	res = telegram_admin.create_binding_code(row["name"], role_scope)
	return {
		"success": True,
		"code": res["code"],
		"expires_in": res["expires_in"],
		"instructions": res["instructions"],
	}


# -- business connections -----------------------------------------------------------------------


@frappe.whitelist()
def list_business_connections(gateway: str | None = None) -> dict[str, Any]:
	"""Read-only view of the cached business connections (state and rights) of this gateway."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	items: list[dict[str, Any]] = []
	try:
		from huf.ai.gateway_adapters import telegram_business as biz

		prefix = biz._conn_key("")
		for key in frappe.cache().get_keys(prefix + "*") or []:
			key = key.decode() if isinstance(key, bytes) else str(key)
			conn = biz._get(key[key.index(prefix) :]) if prefix in key else None
			if isinstance(conn, dict) and conn.get("gateway") == row["name"]:
				items.append(
					{
						"id": conn.get("id"),
						"owner_id": conn.get("owner_id"),
						"owner_name": conn.get("owner_name"),
						"enabled": bool(conn.get("is_enabled", True)),
						"rights": conn.get("rights") or {},
					}
				)
	except Exception:
		items = []
	return {"success": True, "items": items}


# -- send panel ----------------------------------------------------------------------------------


def _own_bound_chat(gateway: str, user: str) -> set[str]:
	rows = (
		frappe.get_all(
			"Telegram Admin Binding",
			filters={"gateway": gateway, "frappe_user": user, "is_active": 1},
			fields=["chat_id"],
			limit_page_length=20,
		)
		or []
	)
	return {str(r["chat_id"]) for r in rows if r.get("chat_id")}


def chat_permitted(gateway: str, chat_id: Any, user: str) -> str:
	"""Normalised numeric chat id when it is an Approved sender or the caller's own bound chat, else ''."""
	from huf.ai import telegram_send_scope as scope

	chat = scope.normalize_chat(chat_id)
	if not chat or chat.startswith("@"):
		return ""
	if chat in {scope.normalize_chat(c) for c in _own_bound_chat(gateway, user)}:
		return chat
	return chat if scope._is_approved(gateway, chat) else ""


def validate_upload(kind: str, filename: str, content: bytes) -> str:
	"""Error message, or '' when the payload is acceptable for ``kind``."""
	if kind not in MAX_BYTES:
		return "Unsupported media kind."
	if not content:
		return "The file is empty."
	if len(content) > MAX_BYTES[kind]:
		return f"The file is larger than {MAX_BYTES[kind] // (1024 * 1024)} MB."
	name = (filename or "").lower()
	if name.endswith(_DENIED_EXT):
		return "This file type is not allowed."
	mime = mimetypes.guess_type(name)[0] or ""
	if kind in _ALLOWED_MIME and mime not in _ALLOWED_MIME[kind]:
		return _TYPE_HELP[kind]
	return ""


def _read_file(file_url: str) -> tuple[str, bytes]:
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		raise frappe.DoesNotExistError
	doc = frappe.get_doc("File", name)
	if not frappe.has_permission("File", "read", doc=doc):
		raise frappe.PermissionError
	return doc.file_name or "", doc.get_content()


def _audit(gateway: str, user: str, chat: str, kind: str, result: str, detail: str = "") -> None:
	try:
		from huf.ai.telegram_admin import write_audit

		write_audit(
			{"telegram_user_id": chat, "frappe_user": user, "gateway": gateway},
			{"op": "send_panel", "kind": kind, "chat": chat},
			result,
			detail=detail,
		)
	except Exception:
		frappe.logger("huf").warning("telegram send panel audit write failed")


@frappe.whitelist(methods=["POST"])
def send_message(
	gateway: str | None = None,
	chat_id: Any = None,
	text: str = "",
	kind: str = "text",
	file_url: str | None = None,
) -> dict[str, Any]:
	"""Send from the panel to an approved contact or the caller's own bound chat only."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	user = frappe.session.user
	if kind not in SEND_KINDS:
		return _error("invalid_kind", "Unsupported message type.")
	chat = chat_permitted(row["name"], chat_id, user)
	if not chat:
		_audit(row["name"], user, str(chat_id or "")[:40], kind, "refused", "recipient_not_permitted")
		return _error("recipient_not_permitted", "Send only to an approved contact or your own bound chat.")
	text = str(text or "")
	if kind == "text":
		if not text.strip():
			return _error("empty", "Write a message first.")
		if len(text) > MAX_TEXT:
			return _error("too_long", f"Text is limited to {MAX_TEXT} characters.")
	elif len(text) > MAX_CAPTION:
		return _error("too_long", f"Captions are limited to {MAX_CAPTION} characters.")
	media: tuple | None = None
	if kind != "text":
		if not file_url:
			return _error("file_required", "Attach a file.")
		try:
			filename, content = _read_file(file_url)
		except frappe.PermissionError:
			return _error("file_not_permitted", "You cannot read that file.")
		except Exception:
			return _error("file_not_found", "Uploaded file not found.")
		problem = validate_upload(kind, filename, content)
		if problem:
			return _error("invalid_file", problem)
		media = (
			filename or "upload",
			content,
			mimetypes.guess_type(filename or "")[0] or "application/octet-stream",
		)
	from huf.ai.gateway_adapters.telegram_client import TelegramApiError
	from huf.ai.gateway_adapters.telegram_outbound import TelegramSender

	credentials: dict[str, str] = {}
	try:
		credentials = _credentials(row)
		sender = TelegramSender(_client(credentials))
		if kind == "text":
			results = sender.send_text(chat, text)
		else:
			results = sender.send_media(kind, chat, media, caption=text)
	except TelegramApiError as exc:
		msg = _safe_text(exc.description, credentials)
		_audit(row["name"], user, chat, kind, "failed", msg)
		return _error("send_failed", msg)
	except Exception as exc:
		msg = _safe_text(exc, credentials)
		_audit(row["name"], user, chat, kind, "failed", msg)
		return _error("send_failed", msg)
	_audit(row["name"], user, chat, kind, "ok", f"chars={len(text)}")
	ids = [
		r.get("message_id")
		for r in (results if isinstance(results, list) else [results])
		if isinstance(r, dict)
	]
	return {"success": True, "message_ids": ids}


@frappe.whitelist()
def list_send_targets(gateway: str | None = None) -> dict[str, Any]:
	"""Chats the Send panel may use: the caller's bound chats and Approved senders."""
	row = _require_admin(gateway)
	if "success" in row:
		return row
	targets = [
		{"chat_id": c, "label": _("My bound chat"), "source": "binding"}
		for c in sorted(_own_bound_chat(row["name"], frappe.session.user))
	]
	entries = (
		frappe.get_all(
			"Gateway Access Entry",
			filters={"gateway": row["name"], "entry_type": "Sender", "state": "Approved"},
			fields=["external_id", "display_label"],
			limit_page_length=200,
		)
		or []
	)
	seen = {t["chat_id"] for t in targets}
	for e in entries:
		if e["external_id"] and e["external_id"] not in seen:
			targets.append(
				{
					"chat_id": e["external_id"],
					"label": e.get("display_label") or e["external_id"],
					"source": "approved",
				}
			)
	return {"success": True, "items": targets}
