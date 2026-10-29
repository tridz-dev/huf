"""Gateway routing rules pre-route hook (keyword / first_message / contact_attribute / fallback)."""

from __future__ import annotations

import re

import frappe

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
		return Decision("route", {"target_type": "Agent", "agent": target, "flow": None})
	if rule.target_type == "solution":
		from huf.ai.solutions import loader

		state = loader.load_solution_states([target]).get(target)
		if not state:
			return None
		agent, flow = state.get("primary_agent"), state.get("primary_flow")
		if state.get("primary_target_type") == "Agent" and agent:
			return Decision("route", {"target_type": "Agent", "agent": agent, "flow": None, "solution": target})
		if state.get("primary_target_type") == "Flow" and flow:
			return Decision("route", {"target_type": "Flow", "agent": None, "flow": flow, "solution": target})
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
