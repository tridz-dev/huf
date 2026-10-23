# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram management API for the Groups & joins tab.

Gateway admins only (same permission helper as ``telegram_management``). The join queue is the set of
Pending Gateway Access Entries with ``entry_type`` "Room" and ``external_id`` ``join:<chat>:<user>``
(recorded by ``telegram_groups.record_pending_join``). Decisions go through ``telegram_admin_actions``
and are audited. Known groups come from what ``telegram_groups`` stores: Room access entries and the
opted-out chat markers written when the bot is removed. The bot token never leaves the server.
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from huf.ai.gateway_adapters import telegram_admin_actions as admin
from huf.ai.telegram_management import _client, _credentials, _error, _load_gateway, _safe_text

JOIN_PREFIX = "join:"
JOIN_STATES = ("Pending", "Approved", "Revoked", "Expired")
_LABEL_RE = re.compile(r"^Join request:\s*(?P<user>.*?)\s*->\s*(?P<chat>.*)$")
_RIGHT_KEYS = (
	"can_invite_users",
	"can_delete_messages",
	"can_restrict_members",
	"can_pin_messages",
	"can_change_info",
	"can_promote_members",
	"can_manage_chat",
)
_FRIENDLY = {
	"not_enough_rights": "The bot is missing the right to invite users in that group. Grant it in the group's admin settings.",
	"not_admin": "The bot is no longer an administrator of that group.",
	"request_gone": "This join request was already handled or has been withdrawn.",
	"chat_not_found": "Telegram cannot find that group any more.",
}


def _require_admin(gateway: str | None):
	return _load_gateway(gateway)


def parse_join_entry(row: dict[str, Any]) -> dict[str, Any] | None:
	"""A queue item from a Room access entry, or None when it is not a join request."""
	parts = str(row.get("external_id") or "").split(":")
	if len(parts) != 3 or parts[0] != "join" or not parts[1] or not parts[2]:
		return None
	m = _LABEL_RE.match(str(row.get("display_label") or ""))
	user = (m.group("user") if m else "") or parts[2]
	chat = (m.group("chat") if m else "") or parts[1]
	return {
		"entry": row["name"],
		"state": row.get("state"),
		"chat_id": parts[1],
		"chat_title": "" if chat == parts[1] else chat,
		"user_id": parts[2],
		"user_name": "" if user == parts[2] else user,
		"requested_at": row.get("creation"),
		"expires_at": row.get("expires_at"),
	}


def _is_expired(row: dict[str, Any]) -> bool:
	if row.get("state") == "Expired":
		return True
	expires = row.get("expires_at")
	return bool(expires and frappe.utils.get_datetime(expires) < frappe.utils.now_datetime())


def _guard(row: dict[str, Any]) -> dict[str, Any]:
	from huf.ai import telegram_guard

	gw = frappe.get_doc("Gateway", row["name"])
	return {
		"join_policy": telegram_guard.join_policy_of(gw),
		"captcha": bool(telegram_guard.captcha_enabled(gw)),
	}


def _audit(gateway: str, op: str, chat: str, user: str, result: str, detail: str = "") -> None:
	try:
		from huf.ai.telegram_admin import write_audit

		write_audit(
			{"telegram_user_id": user, "frappe_user": frappe.session.user, "gateway": gateway},
			{"op": op, "chat_id": chat},
			result,
			detail=detail,
		)
	except Exception:
		frappe.logger("huf").warning("telegram groups audit write failed")


@frappe.whitelist()
def list_join_requests(gateway: str | None = None, state: str = "Pending") -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if state and state not in JOIN_STATES:
		return _error("bad_state", "Unknown state.")
	filters: dict[str, Any] = {
		"gateway": row["name"],
		"entry_type": "Room",
		"external_id": ["like", f"{JOIN_PREFIX}%"],
	}
	if state:
		filters["state"] = state
	rows = frappe.get_all(
		"Gateway Access Entry",
		filters=filters,
		order_by="creation desc",
		limit_page_length=200,
		fields=["name", "state", "external_id", "display_label", "expires_at", "creation"],
	)
	items = []
	for r in rows:
		item = parse_join_entry(r)
		if item:
			item["expired"] = r["state"] == "Pending" and _is_expired(r)
			items.append(item)
	return {"success": True, "items": items, "guard": _guard(row)}


@frappe.whitelist(methods=["POST"])
def decide_join_request(
	gateway: str | None = None, entry: str | None = None, decision: str | None = None
) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if decision not in ("approve", "decline"):
		return _error("bad_decision", "Choose approve or decline.")
	data = (
		frappe.db.get_value(
			"Gateway Access Entry",
			entry,
			[
				"name",
				"gateway",
				"entry_type",
				"state",
				"external_id",
				"display_label",
				"expires_at",
				"creation",
			],
			as_dict=True,
		)
		if entry
		else None
	)
	item = (
		parse_join_entry(data) if data and data.gateway == row["name"] and data.entry_type == "Room" else None
	)
	if not item:
		return _error("not_found", "Join request not found.")
	if data.state != "Pending":
		return _error("already_handled", "This join request was already handled.")
	if _is_expired(data):
		_audit(row["name"], f"join:{decision}", item["chat_id"], item["user_id"], "refused", "expired")
		return _error("expired", "This join request has expired. Ask the person to request to join again.")
	creds = _credentials(row)
	fn = admin.approve_join_request if decision == "approve" else admin.decline_join_request
	from huf.ai import gateway_service

	try:
		fn(_client(creds), item["chat_id"], item["user_id"])
	except admin.AdminActionError as exc:
		detail = f"{exc.code}: {_safe_text(exc, creds)}"
		_audit(row["name"], f"join:{decision}", item["chat_id"], item["user_id"], "failed", detail)
		if exc.code == "request_gone":
			gateway_service.revoke_gateway_access_entry(data.name)
		return _error(exc.code, _FRIENDLY.get(exc.code) or _safe_text(exc, creds))
	if decision == "approve":
		gateway_service.approve_gateway_pairing(data.name, gateway=row["name"])
	else:
		gateway_service.revoke_gateway_access_entry(data.name)
	_audit(row["name"], f"join:{decision}", item["chat_id"], item["user_id"], "ok", "source=admin")
	return {"success": True, "entry": data.name, "decision": decision}


@frappe.whitelist()
def list_groups(gateway: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	groups: dict[str, dict[str, Any]] = {}
	rooms = frappe.get_all(
		"Gateway Access Entry",
		filters={"gateway": row["name"], "entry_type": "Room", "state": ["in", ["Approved", "Pending"]]},
		fields=["external_id", "display_label", "state", "creation"],
		limit_page_length=500,
	)
	for r in rooms:
		cid = str(r["external_id"] or "")
		if cid and not cid.startswith(JOIN_PREFIX):
			groups[cid] = {
				"chat_id": cid,
				"title": r.get("display_label") or "",
				"status": "member",
				"since": r.get("creation"),
			}
	removed = frappe.get_all(
		"Gateway Access Entry",
		filters={
			"gateway": row["name"],
			"entry_type": "Sender",
			"state": "Opted out",
			"display_label": ["like", "Chat %"],
		},
		fields=["external_id", "display_label", "modified"],
		limit_page_length=500,
	)
	for r in removed:
		cid = str(r["external_id"] or "")
		if cid.startswith("-"):
			groups[cid] = {"chat_id": cid, "title": "", "status": "removed", "since": r.get("modified")}
	items = sorted(groups.values(), key=lambda g: str(g.get("since") or ""), reverse=True)
	out: dict[str, Any] = {"success": True, "items": items, "guard": _guard(row)}
	if not items:
		out["note"] = (
			"No groups are recorded yet. Groups appear here after the bot is added to one and receives a message."
		)
	return out


def _rights(member: dict[str, Any]) -> dict[str, Any]:
	status = str(member.get("status") or "")
	rights = {k: bool(member.get(k)) for k in _RIGHT_KEYS} if status == "administrator" else {}
	if status == "creator":
		rights = {k: True for k in _RIGHT_KEYS}
	return {"status": status, "rights": rights}


@frappe.whitelist()
def get_group_settings(gateway: str | None = None, chat_id: str | None = None) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if not chat_id:
		return _error("chat_required", "Choose a group.")
	creds = _credentials(row)
	client = _client(creds)
	try:
		chat = client.call("getChat", {"chat_id": admin._id(chat_id)}) or {}
		admins = admin.get_admins(client, chat_id)
		me = client.call("getMe", {}) or {}
		bot = admin.get_chat_member(client, chat_id, me.get("id"))
	except admin.AdminActionError as exc:
		return _error(exc.code, _FRIENDLY.get(exc.code) or _safe_text(exc, creds))
	except Exception as exc:
		return _error("api_error", _safe_text(exc, creds))
	return {
		"success": True,
		"chat_id": str(chat_id),
		"title": chat.get("title") or "",
		"type": chat.get("type") or "",
		"admins": [
			{
				"user_id": str((a.get("user") or {}).get("id") or ""),
				"name": (a.get("user") or {}).get("first_name")
				or (a.get("user") or {}).get("username")
				or "",
				"is_bot": bool((a.get("user") or {}).get("is_bot")),
				"status": a.get("status") or "",
			}
			for a in admins
		],
		"bot": _rights(bot or {}),
	}


@frappe.whitelist(methods=["POST"])
def leave_group(gateway: str | None = None, chat_id: str | None = None, confirm: Any = 0) -> dict[str, Any]:
	row = _require_admin(gateway)
	if "success" in row:
		return row
	if not chat_id:
		return _error("chat_required", "Choose a group.")
	if str(confirm) not in ("1", "true", "True"):
		return _error("confirm_required", "Confirm that the bot should leave this group.")
	creds = _credentials(row)
	try:
		_client(creds).call("leaveChat", {"chat_id": admin._id(chat_id)})
	except Exception as exc:
		_audit(row["name"], "leave_group", str(chat_id), "", "failed", _safe_text(exc, creds)[:300])
		return _error("api_error", _safe_text(exc, creds))
	_audit(row["name"], "leave_group", str(chat_id), "", "ok", "source=admin")
	return {"success": True, "chat_id": str(chat_id)}
