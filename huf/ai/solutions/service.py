"""Glue between the DB and the pure router."""

from frappe.utils import get_datetime, now_datetime

from huf.ai.solutions import assignment, loader, routing

_SET_BY = {"referral": "referral", "triage_answer": "triage"}


def route_for_event(
	gateway,
	contact,
	text,
	referral_tag="",
	button_payload="",
	now=None,
	commit_pin=False,
	include_inactive=False,
):
	"""Decide the route for one inbound message and return the RouteDecision dict.

	Read-only unless commit_pin is True; then a chosen solution is upserted as the pin and an
	issued triage prompt is recorded as pending. Never commits the transaction itself.

	The CALLER must exclude STOP/START consent events and pairing messages before calling
	this (they must never create or refresh a pin), and must run it only after the sender
	rate limit, consent handling and admission checks (A5, R1c).
	"""
	now = get_datetime(now) if now else now_datetime()
	rules = loader.load_rules(gateway)
	settings = loader.load_gateway_settings(gateway)
	names = {r["solution"] for r in rules if r.get("solution")}
	pin = assignment.get_pin(gateway, contact, now=now)
	if pin:
		names.add(pin["solution"])
	solutions = loader.load_solution_states(names)
	pending = assignment.get_triage_pending(gateway, contact, now=now)

	decision = routing.decide_route(
		text=text,
		referral_tag=referral_tag or "",
		button_payload=button_payload or "",
		now=now,
		rules=rules,
		pin=pin,
		triage_pending_until=pending,
		solutions=solutions,
		keyword_beats_pin=settings["keyword_beats_pin"],
		gateway_default=settings["default"],
		include_inactive=include_inactive,
		pin_ttl_hours=settings["pin_ttl_hours"],
	)

	if commit_pin:
		if decision.get("solution"):
			assignment.set_pin(
				gateway,
				contact,
				decision["solution"],
				_SET_BY.get(decision["reason"], "rule"),
				source_binding=decision.get("binding"),
				ttl_hours=settings["pin_ttl_hours"],
				now=now,
			)
		elif decision.get("triage_pending_until"):
			assignment.mark_triage_pending(gateway, contact, decision["triage_pending_until"])
	return decision
