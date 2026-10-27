"""Generic proactive-send recipient resolver (server side).

Recipient spec grammar (one dict, or a list of dicts, or a JSON string of either):

- ``{"user": "<Frappe user>"}``                      DM; needs a Linked Gateway Identity Link.
- ``{"role": "<Role>"}``                             every enabled user with the role; unlinked are skipped.
- ``{"doc_field": {"doctype", "name", "field"}}``    Link-to-User field of a doc the CALLER can read.
- ``{"recipient_name": "<name>"}``                   Integration Settings recipients table (slack).
- ``{"channel": "<id>"}``                            only if approved for the gateway (enabled Gateway
                                                     Binding with match_type "Room or channel", or an
                                                     Approved Gateway Access Entry of type Room).
- ``{"slack_user": "<id>"}``                         only if it belongs to a Linked identity of the gateway.

Arbitrary raw channel ids and unlinked Slack user ids are refused.
"""

from __future__ import annotations

import json
import re

import frappe

MAX_RECIPIENTS = 50
IDENTITY_DOCTYPE = "Gateway Identity Link"
_SLACK_ID = re.compile(r"^[A-Z][A-Z0-9]{2,}$")
_UNSAFE_USERS = ("Guest", "Administrator")


def parse_specs(recipient) -> list[dict]:
	"""Normalise the LLM-provided value into a list of spec dicts (raises ValueError if unusable)."""
	value = recipient
	if isinstance(value, str):
		text = value.strip()
		if not text:
			raise ValueError("recipient is required")
		try:
			value = json.loads(text)
		except ValueError as exc:
			raise ValueError("recipient must be a JSON object such as {\"user\": \"a@b.com\"}") from exc
	if isinstance(value, dict):
		value = [value]
	if not isinstance(value, list) or not value or not all(isinstance(v, dict) for v in value):
		raise ValueError("recipient must be an object (or list of objects)")
	return value


def slack_id_for_user(gateway_name: str, user: str) -> str | None:
	"""Reverse identity lookup: Frappe user -> Slack user id (Linked, gateway-scoped)."""
	rows = frappe.get_all(
		IDENTITY_DOCTYPE,
		filters={"gateway": gateway_name, "user": user, "state": "Linked"},
		pluck="external_id",
		order_by="modified desc",
		limit=1,
	)
	return rows[0] if rows else None


def _linked_user_for_slack_id(gateway_name: str, slack_id: str) -> str | None:
	rows = frappe.get_all(
		IDENTITY_DOCTYPE,
		filters={"gateway": gateway_name, "external_id": slack_id, "state": "Linked"},
		pluck="user",
		limit=1,
	)
	return rows[0] if rows else None


def channel_is_approved(gateway_name: str, channel: str) -> bool:
	if frappe.db.exists(
		"Gateway Binding",
		{"gateway": gateway_name, "is_enabled": 1, "match_type": "Room or channel", "match_value": channel},
	):
		return True
	return bool(
		frappe.db.exists(
			"Gateway Access Entry",
			{"gateway": gateway_name, "entry_type": "Room", "state": "Approved", "external_id": channel},
		)
	)


def _usable_user(user) -> bool:
	return bool(user) and user not in _UNSAFE_USERS and bool(frappe.db.get_value("User", user, "enabled"))


def _user_target(gateway_name: str, user: str, targets: list, skipped: list) -> None:
	if not _usable_user(user):
		skipped.append({"recipient": user, "reason": "user not found or disabled"})
		return
	slack_id = slack_id_for_user(gateway_name, user)
	if not slack_id:
		skipped.append({"recipient": user, "reason": "no linked Slack identity"})
		return
	targets.append({"label": user, "slack_user": slack_id, "channel": None})


def _lookup_named(name: str) -> str | None:
	from huf.ai.tools.recipient import handle_get_recipient

	try:
		result = json.loads(handle_get_recipient(service="slack", recipient_name=name))
	except (TypeError, ValueError):
		return None
	return result.get("recipient_id") if result.get("success") else None


def resolve(gateway_name: str, specs: list[dict], caller: str | None = None):
	"""Return ``(targets, skipped)``. Each target: ``{label, slack_user|None, channel|None}``."""
	caller = caller or frappe.session.user
	targets: list[dict] = []
	skipped: list[dict] = []
	for spec in specs:
		if "user" in spec:
			_user_target(gateway_name, str(spec["user"] or "").strip(), targets, skipped)
		elif "role" in spec:
			role = str(spec["role"] or "").strip()
			users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
			if not users:
				skipped.append({"recipient": f"role:{role}", "reason": "no users with this role"})
			for user in sorted(set(users)):
				_user_target(gateway_name, user, targets, skipped)
		elif "doc_field" in spec:
			ref = spec["doc_field"] if isinstance(spec["doc_field"], dict) else {}
			dt, dn, field = ref.get("doctype"), ref.get("name"), ref.get("field")
			label = f"{dt}/{dn}.{field}"
			if not (dt and dn and field):
				skipped.append({"recipient": "doc_field", "reason": "doctype, name and field are required"})
				continue
			if not frappe.has_permission(dt, "read", dn, user=caller):
				skipped.append({"recipient": label, "reason": "no permission to read the document"})
				continue
			value = frappe.db.get_value(dt, dn, field)
			if not value:
				skipped.append({"recipient": label, "reason": "field is empty"})
				continue
			_user_target(gateway_name, str(value), targets, skipped)
		elif "recipient_name" in spec:
			name = str(spec["recipient_name"] or "").strip()
			rid = _lookup_named(name) if name else None
			if not rid or not _SLACK_ID.match(str(rid)):
				skipped.append({"recipient": name, "reason": "unknown recipient name"})
			elif str(rid).startswith(("U", "W")):
				targets.append({"label": name, "slack_user": str(rid), "channel": None})
			else:
				targets.append({"label": name, "slack_user": None, "channel": str(rid)})
		elif "channel" in spec:
			channel = str(spec["channel"] or "").strip()
			if _SLACK_ID.match(channel) and channel_is_approved(gateway_name, channel):
				targets.append({"label": channel, "slack_user": None, "channel": channel})
			else:
				skipped.append({"recipient": channel, "reason": "channel is not approved for this gateway"})
		elif "slack_user" in spec:
			sid = str(spec["slack_user"] or "").strip()
			if _SLACK_ID.match(sid) and _linked_user_for_slack_id(gateway_name, sid):
				targets.append({"label": sid, "slack_user": sid, "channel": None})
			else:
				skipped.append({"recipient": sid, "reason": "not a linked identity of this gateway"})
		else:
			skipped.append({"recipient": "?", "reason": "unknown recipient kind"})
	# de-duplicate identical destinations, then cap
	seen, unique = set(), []
	for t in targets:
		key = (t["slack_user"], t["channel"])
		if key not in seen:
			seen.add(key)
			unique.append(t)
	if len(unique) > MAX_RECIPIENTS:
		for t in unique[MAX_RECIPIENTS:]:
			skipped.append({"recipient": t["label"], "reason": f"over the {MAX_RECIPIENTS} recipient cap"})
		unique = unique[:MAX_RECIPIENTS]
	return unique, skipped
