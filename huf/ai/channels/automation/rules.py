"""Gateway routing rules pre-route hook (keyword / first_message / contact_attribute / fallback)."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint

from huf.ai.channels.pipeline import Decision


def _contact_key(context: dict) -> str:
	ctx = context.get("context") or {}
	return str(ctx.get("conversation_id") or ctx.get("sender_id") or "")


def _conversation(gateway: str, handle: str):
	if not handle:
		return None
	from huf.ai.channels.conversation import _open_name

	name = _open_name(gateway, handle)
	return frappe.get_doc("Channel Conversation", name) if name else None


def _is_pinned(gateway: str, handle: str) -> bool:
	if not handle:
		return False
	try:
		from huf.ai.solutions import assignment

		return bool(assignment.get_pin(gateway, handle))
	except Exception:
		return False


def _keyword_match(text: str, value: str) -> bool:
	text = (text or "").strip().lower()
	value = (value or "").strip().lower()
	if not text or not value:
		return False
	return bool(re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text)) or text.startswith(value)


def _attribute_match(conv, rule) -> bool:
	attr, want = (rule.attribute or "").strip(), str(rule.match_value or "").strip().lower()
	if not attr or conv is None:
		return False
	value = conv.get(attr)
	if value in (None, "") and conv.get("contact") and frappe.get_meta("Contact").has_field(attr):
		value = frappe.db.get_value("Contact", conv.contact, attr)
	return value not in (None, "") and str(value).strip().lower() == want


def _matches(rule, text: str, conv) -> bool:
	if rule.rule_type == "keyword":
		return _keyword_match(text, rule.match_value)
	if rule.rule_type == "first_message":
		return conv is None or (conv.message_count or 0) <= 1
	if rule.rule_type == "contact_attribute":
		return _attribute_match(conv, rule)
	return False


def _agent_live(name: str) -> bool:
	"""True when an Agent with this name exists and is not disabled."""
	if not name:
		return False
	row = frappe.db.get_value("Agent", name, ["name", "disabled"], as_dict=True)
	return bool(row) and not row.disabled


def _solution_route(target: str) -> dict | None:
	"""Route payload for a Solution's live primary target, or None if it has none."""
	from huf.ai.solutions import loader

	state = loader.load_solution_states([target]).get(target)
	if not state:
		return None
	agent, flow = state.get("primary_agent"), state.get("primary_flow")
	if state.get("primary_target_type") == "Agent" and agent and _agent_live(agent):
		return {"target_type": "Agent", "agent": agent, "flow": None, "solution": target}
	if state.get("primary_target_type") == "Flow" and flow:
		return {"target_type": "Flow", "agent": None, "flow": flow, "solution": target}
	return None


def rule_errors(rows) -> list[str]:
	"""Save-time problems for the enabled rows (empty list when all are usable)."""
	problems = []
	for idx, row in enumerate(rows or [], start=1):
		if not cint(row.get("enabled")):
			continue
		err = _rule_error(row)
		if err:
			problems.append(_("Row {0}: {1}").format(idx, err))
	return problems


def _rule_error(row) -> str | None:
	rule_type = row.get("rule_type")
	target_type = row.get("target_type")
	target = (row.get("target") or "").strip()
	match_value = (row.get("match_value") or "").strip()
	if rule_type == "keyword" and not match_value:
		return _("match value is required for {0} rules").format(rule_type)
	if rule_type == "contact_attribute":
		if not (row.get("attribute") or "").strip():
			return _("attribute is required for contact attribute rules")
		if not match_value:
			return _("match value is required for contact attribute rules")
	if target_type == "human":
		return None
	if not target:
		return _("target is required for {0} targets").format(target_type)
	if target_type == "agent":
		return None if _agent_live(target) else _("agent {0} does not exist or is disabled").format(target)
	if target_type == "solution":
		if _solution_route(target) is None:
			return _("solution {0} does not exist or has no live primary target").format(target)
		return None
	return _("unknown target type {0}").format(target_type)


def _skip(rule, reason: str) -> None:
	frappe.logger("huf.channels.rules").info(
		f"routing rule skipped: rule_type={rule.rule_type} target_type={rule.target_type} "
		f"target={rule.target} reason={reason}"
	)
	return None


def _decision(rule, gateway) -> Decision | None:
	target = (rule.target or "").strip()
	if rule.target_type == "human":
		return Decision(
			"handoff",
			{"text": gateway.get("handoff_message") or "", "target": gateway.get("handoff_target") or "none"},
		)
	if not target:
		return None
	if rule.target_type == "agent":
		if not _agent_live(target):
			return _skip(rule, "agent missing or disabled")
		return Decision("route", {"target_type": "Agent", "agent": target, "flow": None})
	if rule.target_type == "solution":
		payload = _solution_route(target)
		if payload is None:
			return _skip(rule, "solution has no live primary target")
		return Decision("route", payload)
	return None


def routing_rules_hook(context: dict) -> Decision | None:
	gateway_name = context.get("gateway")
	if not gateway_name:
		return None
	gateway = frappe.get_doc("Gateway", gateway_name)
	rules = [r for r in (gateway.get("routing_rules") or []) if r.enabled]
	if not rules:
		return None
	handle = _contact_key(context)
	conv = _conversation(gateway_name, handle)
	if (conv is not None and conv.status == "handed_off") or _is_pinned(gateway_name, handle):
		return None
	text = str((context.get("context") or {}).get("message_text") or "")
	rules.sort(key=lambda r: (r.priority or 0, r.idx or 0))
	for rule in (r for r in rules if r.rule_type != "fallback"):
		if _matches(rule, text, conv):
			decision = _decision(rule, gateway)
			if decision:
				return decision
	fallbacks = [r for r in rules if r.rule_type == "fallback"]
	if not fallbacks:
		return None
	from huf.ai.gateway_service import resolve_gateway_route

	if resolve_gateway_route(gateway_name, (context.get("context") or {}), commit_pin=False).get("status") != "Unrouted":
		return None
	for rule in fallbacks:
		decision = _decision(rule, gateway)
		if decision:
			return decision
	return None
