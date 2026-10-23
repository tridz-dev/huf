# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Settings tab API: read and update the editable Gateway fields.

Gateway admins only (same model as ``telegram_management``). Only the fields in ``FIELD_SPECS`` can be
changed, so credentials, the webhook secret and the integration link are unreachable here. Fields that
the Gateway doctype does not have yet are skipped with a clear message instead of failing. The pure
helpers (``coerce_value``, ``validate_updates``) take plain data so they can be unit tested.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.telegram_management import _error, _load_gateway

SENTINEL_MISSING = object()

# fieldname -> type, group and (for select) fallback options; int fields carry bounds.
FIELD_SPECS: dict[str, dict[str, Any]] = {
	# Replies
	"telegram_parse_mode": {"type": "select", "group": "replies", "options": ["Plain", "HTML", "MarkdownV2"]},
	"preview_url": {"type": "select", "group": "replies", "options": ["Default (off)", "On", "Off"]},
	"telegram_silent_replies": {"type": "check", "group": "replies"},
	"telegram_protect_content": {"type": "check", "group": "replies"},
	"voice_reply_mode": {"type": "select", "group": "replies", "options": ["Off", "Voice only", "Text and voice"]},
	"typing_indicator": {"type": "check", "group": "replies"},
	"retry_max_attempts": {"type": "int", "group": "replies", "min": 1, "max": 10},
	# Access
	"direct_policy": {"type": "select", "group": "access", "options": ["Disabled", "Pairing", "Allow list", "Open"]},
	"room_policy": {"type": "select", "group": "access", "options": ["Disabled", "Allow list", "Open"]},
	"room_sender_policy": {"type": "select", "group": "access", "options": ["Allow list", "Open"]},
	"mention_required": {"type": "check", "group": "access"},
	"pairing_ttl_minutes": {"type": "int", "group": "access", "min": 1, "max": 10080},
	"pairing_reply_enabled": {"type": "check", "group": "access"},
	"pairing_pending_limit": {"type": "int", "group": "access", "min": 0, "max": 10000},
	"pairing_reply_daily_limit": {"type": "int", "group": "access", "min": 0, "max": 10000},
	"telegram_bot_allowlist": {"type": "text", "group": "access", "max_len": 2000},
	"telegram_bot_max_hops": {"type": "int", "group": "access", "min": 0, "max": 20},
	"telegram_bot_rate_cap": {"type": "int", "group": "access", "min": 0, "max": 10000},
	# Agent permissions
	"agent_recipient_scope": {
		"type": "select",
		"group": "agent",
		"options": ["Current contact", "Allow-list", "Approved contacts", "Any number"],
	},
	"agent_recipient_allowlist": {"type": "text", "group": "agent", "max_len": 4000},
	"agent_send_cap_per_run": {"type": "int", "group": "agent", "min": 0, "max": 10000},
	"agent_send_cap_per_day": {"type": "int", "group": "agent", "min": 0, "max": 100000},
	"telegram_agent_allow_group_admin": {"type": "check", "group": "agent"},
	"telegram_agent_allow_business": {"type": "check", "group": "agent"},
	"telegram_agent_allow_profile": {"type": "check", "group": "agent"},
	# Modes
	"telegram_business_policy": {"type": "select", "group": "modes", "options": ["Ignore", "Observe", "Draft", "Reply"]},
	"telegram_join_policy": {"type": "select", "group": "modes", "options": ["Queue", "Decline", "Agent"]},
	"telegram_inline_enabled": {"type": "check", "group": "modes"},
	"telegram_test_environment": {"type": "check", "group": "modes"},
	"telegram_streaming": {"type": "check", "group": "modes"},
	"telegram_default_template": {"type": "link", "group": "modes", "doctype": "Telegram Message Template"},
	"telegram_welcome_template": {"type": "link", "group": "modes", "doctype": "Telegram Message Template"},
	"telegram_welcome_cooldown_seconds": {"type": "int", "group": "modes", "min": 0, "max": 86400},
	"telegram_guard_captcha": {"type": "select", "group": "modes", "options": ["Off", "Arithmetic", "Emoji"]},
	"telegram_guard_question_text": {"type": "text", "group": "modes", "max_len": 500},
	# Routing and run identity
	"default_target_type": {"type": "select", "group": "routing", "options": ["", "Agent", "Flow"], "allow_empty": True},
	"default_agent": {"type": "link", "group": "routing", "doctype": "Agent", "missing": "That agent doesn't exist."},
	"default_flow": {"type": "link", "group": "routing", "doctype": "Flow Definition", "missing": "That flow doesn't exist."},
	"execution_user": {"type": "link", "group": "routing", "doctype": "User", "missing": "That user doesn't exist."},
	"error_reply_text": {"type": "text", "group": "replies", "max_len": 500},
}

EDITABLE_FIELDS = tuple(FIELD_SPECS)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _split_options(raw: Any) -> list[str]:
	return [o.strip() for o in str(raw or "").split("\n") if o.strip()]


def coerce_value(spec: dict[str, Any], raw: Any, options: list[str] | None = None) -> Any:
	"""Return the cleaned value for ``raw`` or raise ``ValueError`` with a plain message."""
	kind = spec["type"]
	if kind == "check":
		if isinstance(raw, bool):
			return 1 if raw else 0
		if isinstance(raw, (int, float)) and raw in (0, 1):
			return int(raw)
		text = str(raw).strip().lower()
		if text in _TRUE:
			return 1
		if text in _FALSE:
			return 0
		raise ValueError("must be on or off")
	if kind == "int":
		if isinstance(raw, bool) or raw is None or str(raw).strip() == "":
			raise ValueError("must be a whole number")
		try:
			number = int(str(raw).strip())
		except ValueError as exc:
			raise ValueError("must be a whole number") from exc
		lo, hi = spec.get("min", 0), spec.get("max")
		if number < lo:
			raise ValueError(f"must be at least {lo}")
		if hi is not None and number > hi:
			raise ValueError(f"must be at most {hi}")
		return number
	if kind == "select":
		text = "" if raw is None else str(raw)
		allowed = list(options or spec.get("options") or [])
		if spec.get("allow_empty") and "" not in allowed:
			allowed.append("")
		if text not in allowed:
			raise ValueError("is not one of the allowed choices")
		return text
	if kind == "link":
		return "" if raw is None else str(raw).strip()
	text = "" if raw is None else str(raw)
	if len(text) > spec.get("max_len", 2000):
		raise ValueError("is too long")
	return text


def validate_updates(
	values: dict[str, Any], field_info: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
	"""Split ``values`` into (clean, skipped, errors).

	``field_info`` maps the Gateway fieldnames that exist on the doctype to ``{"options": [...]}``.
	Names outside the allow-list are errors; allowed names the doctype lacks are skipped; bad values are errors.
	"""
	clean: dict[str, Any] = {}
	skipped: list[dict[str, str]] = []
	errors: list[dict[str, str]] = []
	for name, raw in (values or {}).items():
		spec = FIELD_SPECS.get(name)
		if spec is None:
			errors.append({"field": str(name), "message": "This setting can't be changed here."})
			continue
		info = field_info.get(name)
		if info is None:
			skipped.append({"field": name, "message": "This setting isn't available on this site yet."})
			continue
		try:
			clean[name] = coerce_value(spec, raw, info.get("options") or None)
		except ValueError as exc:
			errors.append({"field": name, "message": str(exc)})
	return clean, skipped, errors


def _field_info() -> dict[str, dict[str, Any]]:
	meta = frappe.get_meta("Gateway")
	info: dict[str, dict[str, Any]] = {}
	for name, spec in FIELD_SPECS.items():
		df = meta.get_field(name)
		if not df:
			continue
		info[name] = {"options": _split_options(df.options) if spec["type"] == "select" else []}
	return info


def build_settings(row: dict[str, Any], field_info: dict[str, dict[str, Any]]) -> dict[str, Any]:
	"""Settings payload from a gateway row: current values, choices and fields this site doesn't have."""
	values: dict[str, Any] = {}
	options: dict[str, list[str]] = {}
	for name, spec in FIELD_SPECS.items():
		info = field_info.get(name)
		if info is None:
			continue
		raw = row.get(name)
		if spec["type"] in ("check", "int"):
			values[name] = int(raw or 0)
		else:
			values[name] = raw or ""
		if spec["type"] == "select":
			options[name] = info.get("options") or spec["options"]
	return {
		"values": values,
		"options": options,
		"unavailable": [n for n in FIELD_SPECS if n not in field_info],
	}


def _plain(exc: Exception) -> str:
	from frappe.utils import strip_html

	return strip_html(str(exc)).strip() or "That change couldn't be saved."


def _execution_roles() -> list[str]:
	return list(frappe.get_hooks("huf_gateway_execution_roles") or ["Huf Gateway User"])


@frappe.whitelist()
def list_gateway_users(gateway: str | None = None) -> dict[str, Any]:
	"""Enabled users who may run a gateway's agents (role 'Huf Gateway User'; never Administrator)."""
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	holders = frappe.get_all(
		"Has Role",
		filters={"role": ["in", _execution_roles()], "parenttype": "User"},
		pluck="parent",
		limit_page_length=0,
	)
	users = []
	if holders:
		users = frappe.get_all(
			"User",
			filters={"name": ["in", sorted(set(holders))], "enabled": 1},
			fields=["name", "full_name"],
			order_by="full_name asc",
			limit_page_length=0,
		)
	return {
		"success": True,
		"users": [{"name": u["name"], "full_name": u.get("full_name") or u["name"]} for u in users if u["name"] != "Administrator"],
	}


def _read(gateway: str) -> dict[str, Any]:
	info = _field_info()
	doc = frappe.get_doc("Gateway", gateway)
	return build_settings({n: doc.get(n) for n in info}, info)


@frappe.whitelist()
def get_telegram_settings(gateway: str | None = None) -> dict[str, Any]:
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	return {"success": True, "gateway": row["name"], **_read(row["name"])}


@frappe.whitelist(methods=["POST"])
def update_telegram_settings(gateway: str | None = None, values: Any = None) -> dict[str, Any]:
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict) or not values:
		return _error("no_changes", "Nothing to save.")
	info = _field_info()
	clean, skipped, errors = validate_updates(values, info)
	for name, spec in FIELD_SPECS.items():
		if spec["type"] == "link" and clean.get(name) and not frappe.db.exists(spec["doctype"], clean[name]):
			errors.append({"field": name, "message": spec.get("missing", "That template doesn't exist.")})
			clean.pop(name)
	if errors:
		return {"success": False, "error": "invalid", "message": _("Some settings are not valid."), "errors": errors}
	if clean:
		doc = frappe.get_doc("Gateway", row["name"])
		doc.update(clean)
		try:
			doc.save()
		except frappe.ValidationError as exc:
			# The Gateway controller checks the run-as user's role and agent access; show its words.
			frappe.clear_last_message()
			return _error("invalid", _plain(exc))
	return {"success": True, "gateway": row["name"], "skipped": skipped, **_read(row["name"])}
