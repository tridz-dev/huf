"""Whitelisted read/write of a Gateway's routing rules."""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.channels.rules import rule_errors
from huf.permissions import has_capability

_FIELDS = ("rule_type", "match_value", "attribute", "target_type", "target", "priority", "enabled")


def _check():
	if not has_capability(frappe.session.user, "system.integrations.manage"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_rules(gateway: str) -> list[dict]:
	_check()
	doc = frappe.get_doc("Gateway", gateway)
	return [{f: r.get(f) for f in _FIELDS} for r in (doc.get("routing_rules") or [])]


@frappe.whitelist()
def save_rules(gateway: str, rules) -> list[dict]:
	_check()
	if isinstance(rules, str):
		rules = json.loads(rules or "[]")
	problems = rule_errors(rules or [])
	if problems:
		frappe.throw("<br>".join(problems), frappe.ValidationError, title=_("Invalid routing rules"))
	doc = frappe.get_doc("Gateway", gateway)
	doc.set("routing_rules", [])
	for r in rules or []:
		doc.append("routing_rules", {f: r.get(f) for f in _FIELDS if f in r})
	doc.save(ignore_permissions=True)
	return get_rules(gateway)
