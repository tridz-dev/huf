"""Shared DB fixtures for the assignment/loader/service tests (rolled back per test)."""

import uuid

import frappe


def uid():
	return uuid.uuid4().hex[:8]


def make_gateway(**kw):
	fields = {
		"doctype": "Gateway",
		"gateway_name": f"sol-gw-{uid()}",
		"provider": "Telegram",
		"is_enabled": 0,
		"direct_policy": "Pairing",
	}
	fields.update(kw)
	return frappe.get_doc(fields).insert(ignore_permissions=True)


def make_solution(**kw):
	fields = {"doctype": "Solution", "title": f"Sol {uid()}", "purpose": "answer", "status": "Live"}
	fields.update(kw)
	return frappe.get_doc(fields).insert(ignore_permissions=True)


def make_binding(gateway, agent=None, **kw):
	fields = {
		"doctype": "Gateway Binding",
		"gateway": gateway,
		"priority": 10,
		"is_enabled": 1,
		"match_type": "Keyword",
		"target_type": "Agent",
		"agent": agent,
	}
	if kw.get("target_type") == "Triage":
		fields["agent"] = None
	fields.update(kw)
	return frappe.get_doc(fields).insert(ignore_permissions=True)


def make_agent():
	from huf.testing.factories import make_agent as _mk

	return _mk().name
