"""Read models for the Solutions UI (API contract v1, WP B2).

Every function is whitelisted, read-only and accepts dict or JSON-string arguments. The caller
must pass ``_can_manage_integrations()`` (A11); data of a gateway is returned only when
``_gateway_read_allowed(gateway)`` also holds. Errors are ``{"error": {"code", "message"}}``.

Percent values (usage_pct, cap_share, share_pct) are on a 0-100 scale.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from huf.ai.solutions import loader, routing
from huf.ai.solutions.ceiling import ceiling_for_gateway
from huf.ai.solutions.intents import INTENTS
from huf.ai.solutions.usage import blame as usage_blame
from huf.ai.solutions.usage import sends_24h_by_solution, usage_pct
from huf.ai.whatsapp.management import _can_manage_integrations, _gateway_read_allowed

_PREVIEW_LEN = 80
_MULTI = ("Keyword", "Ad or link tag")
_QUALITY_STATE = {"GREEN": "ok", "YELLOW": "warn", "RED": "bad"}
_EVENT_LIMIT = 2000


def _error(code: str, message: str = "") -> dict[str, Any]:
	return {"error": {"code": code, "message": message}}


def _not_permitted() -> dict[str, Any]:
	return _error("not_permitted", "Not permitted to view solutions.")


def _arg(value):
	"""dict/list/None pass through; a JSON string is parsed."""
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return None
		try:
			return frappe.parse_json(text)
		except Exception:
			return text
	return value


def _text_arg(value) -> Optional[str]:
	"""A plain string argument; tolerates a JSON-quoted string or a {"name": ...} object."""
	value = _arg(value)
	if isinstance(value, dict):
		value = value.get("name") or value.get("solution") or value.get("gateway")
	return str(value).strip() if value else None


def _truncate(text, n=_PREVIEW_LEN) -> str:
	text = " ".join(str(text or "").split())
	return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _split(value) -> list[str]:
	return [v.strip() for v in (value or "").split(",") if v.strip()]


def _readable_gateways(candidates=None) -> list[str]:
	names = candidates if candidates is not None else frappe.get_all("Gateway", pluck="name")
	return [g for g in dict.fromkeys(names) if g and _gateway_read_allowed(g)]


# ---- gateway helpers -------------------------------------------------------------------------


def _cached_phone(gateway: str) -> dict:
	"""The ``phone`` block of the cached token check; cache only, never a network call."""
	try:
		from huf.ai.whatsapp.token_check import _result_key

		cached = frappe.cache().get_value(_result_key(gateway))
		phone = cached.get("phone") if isinstance(cached, dict) else None
		return phone if isinstance(phone, dict) else {}
	except Exception:
		return {}


def _quality(gateway: str) -> Optional[str]:
	rating = _cached_phone(gateway).get("quality")
	return str(rating).upper() if isinstance(rating, str) and rating else None


def _gateway_card(gateway: str) -> dict:
	row = frappe.db.get_value(
		"Gateway", gateway, ["gateway_name", "phone_number_id", "whatsapp_account"], as_dict=True
	)
	label = (row.gateway_name if row else None) or gateway
	phone = _cached_phone(gateway).get("display") or (row.phone_number_id if row else None) or ""
	return {"gateway": gateway, "label": label, "phone": phone}


def _target_label(target_type, agent, flow) -> Optional[str]:
	try:
		if target_type == "Agent" and agent:
			return frappe.db.get_value("Agent", agent, "agent_name") or agent
		if target_type == "Flow" and flow:
			return flow
	except Exception:
		pass
	return agent or flow


def _live(state: Optional[dict]) -> bool:
	return bool(state) and state.get("status") == "Live" and not state.get("test_mode")


_BINDING_FIELDS = [
	"name", "gateway", "priority", "is_enabled", "match_type", "match_value", "target_type",
	"agent", "flow", "solution", "cap_per_day", "scope_override", "allow_first_message",
]


def _bindings(filters) -> list:
	return frappe.get_all(
		"Gateway Binding", filters=filters, fields=_BINDING_FIELDS, order_by="priority asc, creation asc"
	)


def _summaries(rows, readable: set[str], states: dict, live_by_gateway: dict[str, set]) -> list[dict]:
	"""Build SolutionSummary dicts for Solution rows. ``rows`` come from frappe.get_all."""
	names = [r.name for r in rows]
	if not names:
		return []
	by_solution: dict[str, list] = {}
	for b in _bindings({"solution": ["in", names]}):
		by_solution.setdefault(b.solution, []).append(b)

	since = add_to_date(now_datetime(), days=-7)
	chats: dict[str, set] = {}
	if readable:
		events = frappe.get_all(
			"Gateway Event",
			filters={"solution": ["in", names], "gateway": ["in", list(readable)], "received_at": [">=", since]},
			fields=["solution", "conversation_id", "gateway"],
			limit_page_length=_EVENT_LIMIT * 5,
		)
		for e in events:
			if e.conversation_id:
				chats.setdefault(e.solution, set()).add((e.gateway, e.conversation_id))

	cards: dict[str, dict] = {}
	out = []
	for r in rows:
		mine = [b for b in by_solution.get(r.name, []) if b.gateway in readable]
		if by_solution.get(r.name) and not mine:
			continue  # every gateway of this solution is out of the caller's reach
		runs_on, seen = [], set()
		for b in mine:
			if b.gateway not in seen:
				seen.add(b.gateway)
				runs_on.append(cards.setdefault(b.gateway, _gateway_card(b.gateway)))
		shared = any(len(live_by_gateway.get(g, set())) > 1 for g in seen)
		primary = None
		if r.primary_target_type and (r.primary_agent or r.primary_flow):
			primary = {
				"type": r.primary_target_type,
				"name": r.primary_agent if r.primary_target_type == "Agent" else r.primary_flow,
				"label": _target_label(r.primary_target_type, r.primary_agent, r.primary_flow),
			}
		out.append(
			{
				"name": r.name,
				"title": r.title,
				"description": r.description or "",
				"purpose": r.purpose,
				"status": r.status,
				"test_mode": bool(r.test_mode),
				"runs_on": runs_on,
				"shared": bool(shared),
				"entry_count": len(mine),
				"primary": primary,
				"chats_7d": len(chats.get(r.name, set())),
			}
		)
	return out


_SOLUTION_FIELDS = [
	"name", "title", "purpose", "status", "test_mode", "description",
	"primary_target_type", "primary_agent", "primary_flow",
]


def _live_by_gateway(states: dict) -> dict[str, set]:
	out: dict[str, set] = {}
	for b in frappe.get_all("Gateway Binding", filters={"solution": ["is", "set"]}, fields=["gateway", "solution"]):
		if _live(states.get(b.solution)):
			out.setdefault(b.gateway, set()).add(b.solution)
	return out


# ---- whitelisted reads -----------------------------------------------------------------------


@frappe.whitelist()
def list_solutions(purpose=None):
	if not _can_manage_integrations():
		return _not_permitted()
	purpose = _text_arg(purpose)
	filters = {"purpose": purpose} if purpose else {}
	rows = frappe.get_all("Solution", filters=filters, fields=_SOLUTION_FIELDS, order_by="modified desc")
	readable = set(_readable_gateways())
	states = loader.load_solution_states()
	return _summaries(rows, readable, states, _live_by_gateway(states))


def _summary_for(name: str) -> Optional[dict]:
	rows = frappe.get_all("Solution", filters={"name": name}, fields=_SOLUTION_FIELDS)
	if not rows:
		return None
	readable = set(_readable_gateways())
	states = loader.load_solution_states()
	found = _summaries(rows, readable, states, _live_by_gateway(states))
	return found[0] if found else {}


@frappe.whitelist()
def get_solution_overview(name):
	if not _can_manage_integrations():
		return _not_permitted()
	name = _text_arg(name)
	if not name:
		return _error("invalid_payload", "name is required.")
	summary = _summary_for(name)
	if summary is None:
		return _error("not_found", "Solution not found.")
	if not summary:
		return _not_permitted()

	gateways = [r["gateway"] for r in summary["runs_on"]]
	since = add_to_date(now_datetime(), days=-7)

	# health: the first readable gateway; quality only when the cached token check reported one
	health_gw = gateways[0] if gateways else None
	rating = _quality(health_gw) if health_gw else None
	state = _QUALITY_STATE.get(rating, "ok") if health_gw else "warn"
	health = {
		"state": state,
		"gateway": health_gw,
		"quality": rating,
		"blame": usage_blame(health_gw) if health_gw else None,
	}

	# reach and activity
	contacts: set = set()
	if gateways:
		rows = frappe.get_all(
			"Gateway Event",
			filters={"solution": name, "gateway": ["in", gateways], "received_at": [">=", since]},
			fields=["gateway", "conversation_id"],
			limit_page_length=_EVENT_LIMIT * 5,
		)
		contacts = {(r.gateway, r.conversation_id) for r in rows if r.conversation_id}
	earlier = set()
	if contacts:
		prior = frappe.get_all(
			"Gateway Event",
			filters={"solution": name, "gateway": ["in", gateways], "received_at": ["<", since]},
			fields=["gateway", "conversation_id"],
			limit_page_length=_EVENT_LIMIT * 5,
		)
		earlier = {(r.gateway, r.conversation_id) for r in prior}
	reach = {"contacts_7d": len(contacts), "new_7d": len(contacts - earlier)}

	activity = []
	if gateways:
		recent = frappe.get_all(
			"Gateway Event",
			filters={"solution": name, "gateway": ["in", gateways]},
			fields=["received_at", "creation", "status", "message_text"],
			order_by="received_at desc, creation desc",
			limit_page_length=10,
		)
		activity = [
			{
				"ts": e.received_at or e.creation,
				"kind": (e.status or "event").lower(),
				"text": _truncate(e.message_text),
			}
			for e in recent
		]

	# cost: the gateway where this solution uses the biggest share of the ceiling
	sends = 0
	cap_share, ceiling = None, None
	for gw in gateways:
		count = sends_24h_by_solution(gw).get(name, 0)
		sends += count
		gw_ceiling, _source = ceiling_for_gateway(gw)
		if gw_ceiling:
			share = round(count / gw_ceiling * 100, 1)
			if cap_share is None or share > cap_share:
				cap_share, ceiling = share, gw_ceiling
	if ceiling is None and gateways:
		ceilings = [c for c in (ceiling_for_gateway(g)[0] for g in gateways) if c]
		ceiling = min(ceilings) if ceilings else None
	cost = {"sends_24h": sends, "cap_share": cap_share, "ceiling": ceiling}

	# limits: the tightest per-day cap among the solution's bindings
	capped = [b for b in _bindings({"solution": name, "gateway": ["in", gateways or [""]]}) if (b.cap_per_day or 0) > 0]
	tight = min(capped, key=lambda b: b.cap_per_day) if capped else None
	limits = {
		"per_day": int(tight.cap_per_day) if tight else None,
		"scope": (tight.scope_override or None) if tight else None,
	}
	return {**summary, "health": health, "reach": reach, "activity": activity, "cost": cost, "limits": limits}


@frappe.whitelist()
def list_entry_points(solution):
	if not _can_manage_integrations():
		return _not_permitted()
	solution = _text_arg(solution)
	if not solution:
		return _error("invalid_payload", "solution is required.")
	if not frappe.db.exists("Solution", solution):
		return _error("not_found", "Solution not found.")
	readable = set(_readable_gateways())
	ceilings: dict[str, tuple] = {}
	out = []
	for b in _bindings({"solution": solution}):
		if b.gateway not in readable:
			continue
		ceiling, source = ceilings.setdefault(b.gateway, ceiling_for_gateway(b.gateway))
		if b.match_type in _MULTI:
			values = _split(b.match_value)
		else:
			values = [b.match_value] if b.match_value else []
		out.append(
			{
				"name": b.name,
				"gateway": b.gateway,
				"priority": b.priority or 0,
				"match_type": b.match_type,
				"match_values": values,
				"target_type": b.target_type,
				"agent": b.agent,
				"flow": b.flow,
				"cap_per_day": int(b.cap_per_day) if b.cap_per_day else None,
				"scope_override": b.scope_override or None,
				"allow_first_message": bool(b.allow_first_message),
				"ceiling": ceiling,
				"ceiling_source": source,
			}
		)
	return out


def _rule_label(b) -> str:
	if b.target_type == "Triage":
		return "Ask the customer which service they want"
	if b.match_type in _MULTI:
		return f'{b.match_type}: {", ".join(_split(b.match_value))}'
	if b.match_type == "Catch-all":
		return "Everything else"
	return f'{b.match_type}: {b.match_value}' if b.match_value else b.match_type


@frappe.whitelist()
def get_number_summary(gateway):
	if not _can_manage_integrations():
		return _not_permitted()
	gateway = _text_arg(gateway)
	if not gateway:
		return _error("invalid_payload", "gateway is required.")
	if not frappe.db.exists("Gateway", gateway):
		return _error("not_found", "Gateway not found.")
	if not _gateway_read_allowed(gateway):
		return _not_permitted()

	card = _gateway_card(gateway)
	bindings = _bindings({"gateway": gateway})
	states = loader.load_solution_states([b.solution for b in bindings])
	counts = sends_24h_by_solution(gateway)

	solutions, seen = [], set()
	for b in bindings:
		if not b.solution or b.solution in seen or b.solution not in states:
			continue
		seen.add(b.solution)
		st = states[b.solution]
		solutions.append(
			{
				"name": b.solution,
				"title": st["title"],
				"status": st["status"],
				"usage_pct": usage_pct(b.solution, gateway),
				"sends_24h": counts.get(b.solution, 0),
			}
		)

	routing_order = []
	for b in (b for b in bindings if b.is_enabled):
		routing_order.append(
			{
				"rank": len(routing_order) + 1,
				"kind": "Triage" if b.target_type == "Triage" else b.match_type,
				"label": _rule_label(b),
				"solution": b.solution or None,
			}
		)

	rating = _quality(gateway)
	return {
		"gateway": gateway,
		"label": card["label"],
		"phone": card["phone"],
		"solutions": solutions,
		"routing_order": routing_order,
		"quality": {"rating": rating, "source": "meta" if rating else "unknown"},
		"blame": usage_blame(gateway),
	}


@frappe.whitelist()
def list_solution_conversations(solution=None):
	if not _can_manage_integrations():
		return _not_permitted()
	solution = _text_arg(solution)
	filters: dict[str, Any] = {}
	if solution:
		if not frappe.db.exists("Solution", solution):
			return _error("not_found", "Solution not found.")
		filters["solution"] = solution
		gateways = _readable_gateways(
			[b.gateway for b in _bindings({"solution": solution})]
			+ frappe.get_all("Gateway Event", filters={"solution": solution}, pluck="gateway", distinct=True)
		)
	else:
		gateways = _readable_gateways()
	if not gateways:
		return []
	filters["gateway"] = ["in", gateways]
	filters["conversation_id"] = ["is", "set"]
	events = frappe.get_all(
		"Gateway Event",
		filters=filters,
		fields=["gateway", "conversation_id", "message_text", "solution", "received_at", "creation"],
		order_by="received_at desc, creation desc",
		limit_page_length=_EVENT_LIMIT,
	)
	out, seen = [], set()
	for e in events:
		key = (e.gateway, e.conversation_id)
		if key in seen:
			continue
		seen.add(key)
		out.append(
			{
				"contact": e.conversation_id,
				"preview": _truncate(e.message_text),
				"solution": e.solution or None,
				"gateway": e.gateway,
				"ts": e.received_at or e.creation,
			}
		)
	return out


@frappe.whitelist()
def get_intents():
	if not _can_manage_integrations():
		return _not_permitted()
	return [
		{
			"id": i["id"],
			"name": i["name"],
			"desc": i["desc"],
			"icon": i["icon"],
			"sample_name": i["sample_name"],
			"entry": i["entry"],
			"keywords": list(i["keywords"]),
			"ref": i["ref"],
			"suggested_templates": list(i["suggested_templates"]),
			"policy": list(i["policy"]),
		}
		for i in INTENTS
	]


_DRAFT_PRIORITY = {"Keyword": 1, "Ad or link tag": 2, "Catch-all": 8, "Triage": 9}


def _draft_rules(draft: dict, gateway: str) -> list[dict]:
	"""Virtual routing rules for an unsaved solution (wizard test step). Never touches the DB."""
	title = str(draft.get("title") or "").strip()
	if not title or str(draft.get("gateway") or "").strip() != gateway or not draft.get("inbound", True):
		return []
	entries = [e for e in (_arg(draft.get("entries")) or []) if isinstance(e, dict)]
	if draft.get("catch_all") and not any(e.get("match_type") == "Catch-all" for e in entries):
		entries.append({"match_type": "Catch-all", "match_values": []})
	rules = []
	for i, e in enumerate(entries):
		mt = e.get("match_type")
		if mt not in _DRAFT_PRIORITY:
			continue
		values = e.get("match_values") or []
		if isinstance(values, str):
			values = _split(values)
		rules.append(
			{
				"name": f"draft:{i}",
				"priority": _DRAFT_PRIORITY[mt],
				"match_type": mt,
				"match_values": [str(v) for v in values] if mt in _MULTI else [],
				"target_type": "Triage" if mt == "Triage" else "Agent",
				"agent": None,
				"flow": None,
				"solution": None if mt == "Triage" else title,
				"is_enabled": True,
			}
		)
	return rules


@frappe.whitelist()
def simulate_route(request):
	"""Dry run of the router for one message. Pure read: no pin, assignment or event is written."""
	if not _can_manage_integrations():
		return _not_permitted()
	req = _arg(request)
	if not isinstance(req, dict):
		return _error("invalid_payload", "request must be an object.")
	gateway = str(req.get("gateway") or "").strip()
	if not gateway:
		return _error("invalid_payload", "gateway is required.")
	if not frappe.db.exists("Gateway", gateway):
		return _error("not_found", "Gateway not found.")
	if not _gateway_read_allowed(gateway):
		return _not_permitted()
	state = _arg(req.get("state")) or {}
	if not isinstance(state, dict):
		return _error("invalid_payload", "state must be an object.")

	now = now_datetime()
	settings = loader.load_gateway_settings(gateway)
	rules = loader.load_rules(gateway)

	pin = None
	pin_in = state.get("pin")
	if isinstance(pin_in, dict) and pin_in.get("solution"):
		try:
			hours = float(pin_in.get("hours_left", settings["pin_ttl_hours"]))
		except (TypeError, ValueError):
			return _error("invalid_payload", "state.pin.hours_left must be a number.")
		pin = {"solution": str(pin_in["solution"]), "expires_at": now + timedelta(hours=hours)}
	pending = now + routing.TRIAGE_WINDOW if state.get("triage_pending") else None

	names = {r["solution"] for r in rules if r.get("solution")}
	if pin:
		names.add(pin["solution"])
	solutions = loader.load_solution_states(names)

	draft = _arg(req.get("draft"))
	if isinstance(draft, dict):
		virtual = _draft_rules(draft, gateway)
		if virtual:
			title = str(draft["title"]).strip()
			rules = rules + virtual
			solutions[title] = {"status": "Live", "test_mode": False, "title": title}

	beats = req.get("keyword_beats_pin")
	beats = settings["keyword_beats_pin"] if beats is None else bool(beats)

	decision = routing.decide_route(
		text=str(req.get("text") or ""),
		referral_tag=str(req.get("ref") or ""),
		button_payload=str(req.get("button_payload") or ""),
		now=now,
		rules=rules,
		pin=pin,
		triage_pending_until=pending,
		solutions=solutions,
		keyword_beats_pin=beats,
		gateway_default=settings["default"],
		include_inactive=True,
		pin_ttl_hours=settings["pin_ttl_hours"],
	)
	return {
		k: decision.get(k)
		for k in ("solution", "target_type", "agent", "flow", "binding", "reason", "pin", "trace", "reply_text")
	}
