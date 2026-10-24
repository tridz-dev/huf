"""Load routing inputs (rules, solution states, gateway settings) from the DB in the shape
huf.ai.solutions.routing.decide_route expects."""

import frappe

_MULTI = ("Keyword", "Ad or link tag")


def _split(value):
	return [v.strip() for v in (value or "").split(",") if v.strip()]


def load_rules(gateway):
	rows = frappe.get_all(
		"Gateway Binding",
		filters={"gateway": gateway},
		fields=[
			"name", "priority", "match_type", "match_value", "target_type",
			"agent", "flow", "solution", "is_enabled",
		],
		order_by="priority asc, creation asc",
	)
	return [
		{
			"name": r.name,
			"priority": r.priority or 0,
			"match_type": r.match_type,
			"match_values": _split(r.match_value) if r.match_type in _MULTI else [],
			"target_type": r.target_type,
			"agent": r.agent,
			"flow": r.flow,
			"solution": r.solution,
			"is_enabled": bool(r.is_enabled),
		}
		for r in rows
	]


def load_solution_states(names=None):
	filters = {}
	if names is not None:
		names = [n for n in names if n]
		if not names:
			return {}
		filters["name"] = ["in", names]
	rows = frappe.get_all("Solution", filters=filters, fields=["name", "status", "test_mode", "title"])
	return {
		r.name: {"status": r.status, "test_mode": bool(r.test_mode), "title": r.title} for r in rows
	}


def load_gateway_settings(gateway):
	g = frappe.db.get_value(
		"Gateway",
		gateway,
		["pin_ttl_hours", "keyword_beats_pin", "default_target_type", "default_agent", "default_flow"],
		as_dict=True,
	)
	if not g:
		return {"pin_ttl_hours": 24, "keyword_beats_pin": False, "default": None}
	default = None
	if g.default_agent or g.default_flow:
		default = {
			"target_type": g.default_target_type,
			"agent": g.default_agent,
			"flow": g.default_flow,
		}
	return {
		"pin_ttl_hours": int(g.pin_ttl_hours or 24),
		"keyword_beats_pin": bool(g.keyword_beats_pin),
		"default": default,
	}
