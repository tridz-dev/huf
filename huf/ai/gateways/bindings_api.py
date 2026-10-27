"""Routing (Gateway Binding) editor API plus Slack channel/user pickers.

Every endpoint checks permission against the named Gateway explicitly; gateway
names supplied by the client are never trusted on their own.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from huf.ai.gateways.slack_api import SlackApiError

BINDING_DOCTYPE = "Gateway Binding"
MATCH_TYPES = ("Any conversation", "Direct message", "Room or channel", "Thread", "Sender")
TARGET_TYPES = ("Agent", "Flow")
BINDING_FIELDS = [
	"name", "gateway", "priority", "is_enabled", "match_type", "match_value",
	"target_type", "agent", "flow", "description",
]
SAMPLE_KEYS = ("conversation_id", "thread_id", "sender_id")
PICKER_PAGE_SIZE = 50  # stop collecting once this many matches are found
PICKER_MAX_PAGES = 5  # upper bound on Slack pages scanned per request
SLACK_PAGE_LIMIT = 200

_SCOPE_HINTS = {
	"channels": "channels:read and groups:read",
	"users": "users:read",
}


# ---- permission / loading helpers ------------------------------------------
def _is_system_manager() -> bool:
	return "System Manager" in (frappe.get_roles() or [])


def _load_gateway(gateway: str, ptype: str):
	"""Return the Gateway doc after checking the caller may `ptype` it."""
	if not gateway or not isinstance(gateway, str):
		frappe.throw(_("Choose a gateway."), frappe.ValidationError)
	if not frappe.db.exists("Gateway", gateway):
		frappe.throw(_("Gateway not found."), frappe.DoesNotExistError)
	allowed = _is_system_manager() or frappe.has_permission("Gateway", ptype, doc=gateway)
	if not allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return frappe.get_doc("Gateway", gateway)


def _clean(value: Any) -> str:
	return str(value).strip() if value is not None else ""


def _parse(value: Any) -> Any:
	return json.loads(value) if isinstance(value, str) else value


# ---- validation ------------------------------------------------------------
def validate_binding_payload(binding: dict, gateway=None) -> dict:
	"""Validate and normalise a binding payload; returns the cleaned field values."""
	if not isinstance(binding, dict):
		frappe.throw(_("Invalid rule."), frappe.ValidationError)
	match_type = _clean(binding.get("match_type")) or "Any conversation"
	if match_type not in MATCH_TYPES:
		frappe.throw(_("Choose what this rule applies to."), frappe.ValidationError)
	match_value = _clean(binding.get("match_value"))
	if match_type == "Any conversation":
		if match_value:
			frappe.throw(_("A rule for any conversation takes no value."), frappe.ValidationError)
	elif not match_value:
		frappe.throw(_("Enter a value for this rule."), frappe.ValidationError)

	target_type = _clean(binding.get("target_type"))
	if target_type not in TARGET_TYPES:
		frappe.throw(_("Choose an agent or a flow to handle matching messages."), frappe.ValidationError)
	agent = _clean(binding.get("agent"))
	flow = _clean(binding.get("flow"))
	if target_type == "Agent":
		if not agent:
			frappe.throw(_("Choose an agent."), frappe.ValidationError)
		if flow:
			frappe.throw(_("An agent rule cannot also have a flow."), frappe.ValidationError)
		if not frappe.db.exists("Agent", agent):
			frappe.throw(_("That agent no longer exists."), frappe.ValidationError)
		_check_agent_access(agent, gateway)
	else:
		if not flow:
			frappe.throw(_("Choose a flow."), frappe.ValidationError)
		if agent:
			frappe.throw(_("A flow rule cannot also have an agent."), frappe.ValidationError)
		if not frappe.db.exists("Flow Definition", flow):
			frappe.throw(_("That flow no longer exists."), frappe.ValidationError)

	return {
		"match_type": match_type,
		"match_value": match_value,
		"target_type": target_type,
		"agent": agent or None,
		"flow": flow or None,
		"is_enabled": 1 if binding.get("is_enabled", 1) in (1, True, "1", "true") else 0,
		"description": _clean(binding.get("description")),
	}


def _check_agent_access(agent: str, gateway) -> None:
	run_as = getattr(gateway, "execution_user", None) if gateway is not None else None
	if not run_as:
		return
	from huf.ai.agent_access import check_agent_access

	if not check_agent_access(frappe.get_doc("Agent", agent), run_as, for_execution=True):
		frappe.throw(_("The gateway's run-as user cannot use that agent."), frappe.ValidationError)


def _ordered_bindings(gateway: str) -> list[dict]:
	return frappe.get_all(
		BINDING_DOCTYPE, filters={"gateway": gateway}, fields=BINDING_FIELDS,
		order_by="priority asc, creation asc", limit_page_length=0,
	)


# ---- bindings --------------------------------------------------------------
@frappe.whitelist()
def list_bindings(gateway: str) -> list[dict]:
	_load_gateway(gateway, "read")
	return _ordered_bindings(gateway)


@frappe.whitelist()
def save_binding(gateway: str, binding: dict | str) -> dict:
	"""Create (no ``name``) or update (``name`` of a binding on this gateway) a rule."""
	gw = _load_gateway(gateway, "write")
	binding = _parse(binding)
	values = validate_binding_payload(binding, gw)
	name = _clean(binding.get("name"))
	if name:
		existing = frappe.db.get_value(BINDING_DOCTYPE, name, "gateway")
		if existing != gateway:
			frappe.throw(_("Rule not found on this gateway."), frappe.DoesNotExistError)
		doc = frappe.get_doc(BINDING_DOCTYPE, name)
		doc.update(values)
	else:
		rows = frappe.get_all(
			BINDING_DOCTYPE, filters={"gateway": gateway}, pluck="priority", limit_page_length=0,
		)
		priority = (max((int(p or 0) for p in rows), default=0)) + 1
		doc = frappe.get_doc({"doctype": BINDING_DOCTYPE, "gateway": gateway, "priority": priority, **values})
	doc.save()
	return {field: doc.get(field) for field in BINDING_FIELDS}


@frappe.whitelist()
def delete_binding(name: str) -> dict:
	gateway = frappe.db.get_value(BINDING_DOCTYPE, name, "gateway") if name else None
	if not gateway:
		frappe.throw(_("Rule not found."), frappe.DoesNotExistError)
	_load_gateway(gateway, "write")
	frappe.delete_doc(BINDING_DOCTYPE, name)
	return {"deleted": name}


@frappe.whitelist()
def reorder_bindings(gateway: str, ordered_names: list | str) -> list[dict]:
	"""Rewrite priorities 1..n in the given order. All-or-nothing."""
	_load_gateway(gateway, "write")
	ordered = _parse(ordered_names)
	if not isinstance(ordered, list) or not all(isinstance(n, str) for n in ordered):
		frappe.throw(_("Invalid order."), frappe.ValidationError)
	current = [row["name"] for row in _ordered_bindings(gateway)]
	if len(set(ordered)) != len(ordered) or set(ordered) != set(current):
		frappe.throw(_("The order must list every rule exactly once."), frappe.ValidationError)
	try:
		for index, name in enumerate(ordered, start=1):
			frappe.db.set_value(BINDING_DOCTYPE, name, "priority", index)
	except Exception:
		frappe.db.rollback()
		raise
	return _ordered_bindings(gateway)


@frappe.whitelist()
def test_route(gateway: str, sample: dict | str) -> dict:
	"""Read-only: which rule would handle a sample message."""
	_load_gateway(gateway, "read")
	sample = _parse(sample)
	if not isinstance(sample, dict):
		frappe.throw(_("Invalid sample."), frappe.ValidationError)
	context = {key: _clean(sample.get(key)) for key in SAMPLE_KEYS if sample.get(key) is not None}
	from huf.ai import gateway_service

	return gateway_service.preview_gateway_route(gateway, context)


# ---- Slack pickers ---------------------------------------------------------
def _slack_api(gateway: str):
	gw = _load_gateway(gateway, "read")
	if gw.provider != "Slack":
		return None, {"supported": False, "items": [], "next_cursor": None,
			"error": _("Pickers are only available for Slack gateways.")}
	from huf.ai.gateways.slack_context import get_slack_api

	try:
		return get_slack_api(gw), None
	except ValueError:
		return None, {"supported": True, "items": [], "next_cursor": None,
			"error": _("Connect a Slack bot token to this gateway first.")}


def _error_message(exc: SlackApiError, kind: str) -> str:
	if exc.error_code in ("missing_scope", "not_allowed_token_type", "no_permission"):
		return _("Slack needs the {0} permissions to list this. Add them to your Slack app and reinstall it.").format(
			_SCOPE_HINTS[kind]
		)
	if exc.error_code in ("invalid_auth", "token_revoked", "account_inactive", "not_authed"):
		return _("Slack rejected the connection. Reconnect the bot token.")
	return _("Slack could not be reached. Try again in a moment.")


def normalize_channel(raw: dict) -> dict:
	kind = "private" if raw.get("is_private") else "public"
	if raw.get("is_im"):
		kind = "dm"
	name = raw.get("name") or raw.get("id")
	return {
		"id": raw.get("id"),
		"label": f"#{name}" if kind != "dm" else str(name),
		"kind": kind,
		"is_member": bool(raw.get("is_member")),
	}


def normalize_user(raw: dict) -> dict:
	profile = raw.get("profile") or {}
	label = profile.get("display_name") or raw.get("real_name") or raw.get("name") or raw.get("id")
	return {"id": raw.get("id"), "label": label, "kind": "user", "is_member": True}


def _search(gateway: str, query, cursor, kind: str, fetch, key: str, normalize, skip=None) -> dict:
	api, failure = _slack_api(gateway)
	if failure:
		return failure
	needle = _clean(query).lower().lstrip("#@")
	items: list[dict] = []
	try:
		for _page in range(PICKER_MAX_PAGES):
			body = fetch(api, cursor)
			for raw in body.get(key) or []:
				if skip and skip(raw):
					continue
				item = normalize(raw)
				if not item["id"] or (needle and needle not in f"{item['label']} {item['id']}".lower()):
					continue
				items.append(item)
			cursor = (body.get("response_metadata") or {}).get("next_cursor") or None
			if not cursor or len(items) >= PICKER_PAGE_SIZE:
				break
	except SlackApiError as exc:
		return {"supported": True, "items": [], "next_cursor": None, "error": _error_message(exc, kind)}
	return {"supported": True, "items": items, "next_cursor": cursor, "error": None}


@frappe.whitelist()
def list_slack_channels(gateway: str, query: str | None = None, cursor: str | None = None) -> dict:
	return _search(
		gateway, query, cursor, "channels",
		lambda api, c: api.conversations_list("public_channel,private_channel", cursor=c, limit=SLACK_PAGE_LIMIT),
		"channels", normalize_channel, skip=lambda r: r.get("is_archived"),
	)


@frappe.whitelist()
def list_slack_users(gateway: str, query: str | None = None, cursor: str | None = None) -> dict:
	return _search(
		gateway, query, cursor, "users",
		lambda api, c: api.users_list(cursor=c, limit=SLACK_PAGE_LIMIT),
		"members", normalize_user,
		skip=lambda r: r.get("deleted") or r.get("is_bot") or r.get("id") == "USLACKBOT",
	)
