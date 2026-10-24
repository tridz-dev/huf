"""Pure routing decision for the Solutions feature (A5). No frappe, DB, network or clock."""

from datetime import timedelta
from math import ceil

from huf.ai.solutions.triage import build_triage_prompt, is_live, parse_triage_answer, triage_options

REFERRAL = "Ad or link tag"
KEYWORD = "Keyword"
CATCH_ALL = "Catch-all"
TRIAGE = "Triage"
TRIAGE_WINDOW = timedelta(minutes=30)


def _title(solutions, name):
	return ((solutions or {}).get(name) or {}).get("title") or name


def _target(rule):
	return {
		"target_type": rule.get("target_type") if rule else None,
		"agent": rule.get("agent") if rule else None,
		"flow": rule.get("flow") if rule else None,
		"binding": rule.get("name") if rule else None,
	}


def decide_route(
	*,
	text,
	referral_tag,
	button_payload,
	now,
	rules,
	pin,
	triage_pending_until,
	solutions,
	keyword_beats_pin,
	gateway_default,
	include_inactive=False,
	pin_ttl_hours=24,
	brand=None,
):
	solutions = solutions or {}
	text = text or ""
	low = text.lower().strip()
	trace = []

	def live(sol):
		return bool(sol) and sol in solutions and is_live(solutions[sol], include_inactive)

	def title(sol):
		return _title(solutions, sol)

	enabled = sorted(
		(r for r in (rules or []) if r.get("is_enabled")),
		key=lambda r: (r.get("priority") or 0, r.get("name") or ""),
	)
	# a rule is usable when its solution (if any) is live
	usable = [r for r in enabled if not r.get("solution") or live(r["solution"])]

	def _answers(r):
		return r.get("target_type") != TRIAGE and bool(r.get("agent") or r.get("flow"))

	def target_for(sol):
		"""Answering target for a pin / triage answer / button payload: never a Triage rule.
		Prefer a message rule, then an ad-tag rule, then the solution's primary target."""
		mine = [r for r in usable if r.get("solution") == sol and _answers(r)]
		rule = next((r for r in mine if r.get("match_type") != REFERRAL), mine[0] if mine else None)
		if rule:
			return _target(rule)
		st = solutions.get(sol) or {}
		ptype = st.get("primary_target_type")
		agent = st.get("primary_agent") if ptype == "Agent" else None
		flow = st.get("primary_flow") if ptype == "Flow" else None
		if agent or flow:
			kind = "flow" if flow else "agent"
			trace.append({"k": "info", "t": f"Answered by {title(sol)}'s {kind}"})
			return {"target_type": ptype, "agent": agent, "flow": flow, "binding": None}
		trace.append(
			{"k": "skip", "t": f"{title(sol)} has no rule or primary agent/flow that can answer"}
		)
		return {"target_type": None, "agent": None, "flow": None, "binding": None}

	def decision(reason, solution=None, rule=None, reply_text=None, pending=None, legacy=False, target=None):
		tgt = target if target is not None else _target(rule)
		if solution:
			new_pin = {"solution": solution, "expires_at": now + timedelta(hours=pin_ttl_hours)}
			trace.append(
				{"k": "info", "t": f"Pinned this chat to {title(solution)} for {pin_ttl_hours}h"}
			)
		else:
			new_pin = pin if pin_alive else None
		return {
			"solution": solution,
			"target_type": tgt["target_type"],
			"agent": tgt["agent"],
			"flow": tgt["flow"],
			"binding": tgt["binding"],
			"reason": reason,
			"pin": new_pin,
			"trace": trace,
			"reply_text": reply_text,
			"triage_pending_until": pending,
			"legacy_fallthrough": legacy,
		}

	# pin state
	pin_alive = False
	if pin and pin.get("solution"):
		if pin.get("expires_at") and pin["expires_at"] > now:
			pin_alive = True
		else:
			trace.append({"k": "info", "t": "Earlier pin expired after 24h. Routing from scratch."})
	pin_sol = pin["solution"] if pin_alive and live(pin["solution"]) else None

	# 1. referral tag
	if referral_tag:
		tag = referral_tag.strip().lower()
		hit = next(
			(
				r
				for r in usable
				if r.get("match_type") == REFERRAL
				and r.get("solution")
				and tag in [str(v).strip().lower() for v in (r.get("match_values") or [])]
			),
			None,
		)
		if hit:
			trace.append({"k": "win", "t": f'Ad tag "{referral_tag}" → {title(hit["solution"])}'})
			return decision("referral", hit["solution"], hit)
		trace.append({"k": "skip", "t": f'Ad tag "{referral_tag}" matches nothing on this number'})

	# 1b. template button payload sol:<solution>|...
	if button_payload and str(button_payload).startswith("sol:"):
		sol = str(button_payload)[4:].split("|", 1)[0].strip()
		if live(sol):
			trace.append({"k": "win", "t": f"Template reply payload → {title(sol)}"})
			return decision("referral", sol, target=target_for(sol))
		trace.append({"k": "skip", "t": "Template reply payload points at a solution that is not live"})

	# 2. pending triage answer
	if triage_pending_until and triage_pending_until > now:
		options = triage_options(enabled, solutions, include_inactive)
		answer = parse_triage_answer(text, options)
		if answer:
			trace.append({"k": "win", "t": f'Menu answer "{low}" → {title(answer)}'})
			return decision("triage_answer", answer, target=target_for(answer))
		trace.append({"k": "info", "t": "Menu is open but the message is not a valid answer"})

	# keyword candidate (needed for steps 3 and 4)
	kw_hit = kw_val = None
	if low:
		for r in usable:
			if r.get("match_type") != KEYWORD or not r.get("solution"):
				continue
			val = next(
				(str(v) for v in (r.get("match_values") or []) if str(v).strip() and str(v).strip().lower() in low),
				None,
			)
			if val is not None:
				kw_hit, kw_val = r, val
				break

	# 3. pin
	if pin_sol:
		left = max(1, ceil((pin["expires_at"] - now).total_seconds() / 3600))
		if kw_hit and kw_hit["solution"] != pin_sol:
			trace.append(
				{"k": "skip", "t": f'Keyword "{kw_val}" would route to {title(kw_hit["solution"])}'}
			)
			if keyword_beats_pin:
				trace.append({"k": "win", "t": f"Rule: keyword beats the pin → {title(kw_hit['solution'])}"})
				return decision("keyword", kw_hit["solution"], kw_hit)
			trace.append({"k": "win", "t": f"Pinned to {title(pin_sol)} ({left}h left). Pinned chat wins."})
		else:
			trace.append({"k": "win", "t": f"Pinned to {title(pin_sol)} ({left}h left)"})
		return decision("pin", pin_sol, target=target_for(pin_sol))

	# 4. keyword
	if kw_hit:
		trace.append({"k": "win", "t": f'Keyword "{kw_val}" → {title(kw_hit["solution"])}'})
		return decision("keyword", kw_hit["solution"], kw_hit)

	# 5. catch-all
	ca = next(
		(
			r
			for r in usable
			if r.get("match_type") == CATCH_ALL and r.get("target_type") != TRIAGE and r.get("solution")
		),
		None,
	)
	if ca:
		trace.append({"k": "win", "t": f"No rule matched. Catch-all → {title(ca['solution'])}"})
		return decision("catch_all", ca["solution"], ca)

	# 6. legacy match types are handled by the caller's old resolver
	known = {REFERRAL, KEYWORD, CATCH_ALL}
	if any(r.get("match_type") not in known and r.get("target_type") != TRIAGE for r in usable):
		trace.append({"k": "info", "t": "Older rules exist on this number. Continuing with the old resolver."})
		return decision("unrouted", legacy=True, target=_target(None))

	# 7. gateway default
	if gateway_default and (gateway_default.get("agent") or gateway_default.get("flow")):
		trace.append({"k": "win", "t": "No rule matched. Default for this number applies"})
		tgt = {
			"target_type": gateway_default.get("target_type"),
			"agent": gateway_default.get("agent"),
			"flow": gateway_default.get("flow"),
			"binding": None,
		}
		return decision("default", None, target=tgt)

	# 8. triage
	tri = next((r for r in usable if r.get("target_type") == TRIAGE), None)
	if tri:
		options = triage_options(enabled, solutions, include_inactive)
		if options:
			trace.append({"k": "info", "t": "No rule matched. Triage assistant asks the customer."})
			return decision(
				"triage_prompt",
				None,
				tri,
				reply_text=build_triage_prompt(options, brand),
				pending=now + TRIAGE_WINDOW,
			)
		trace.append({"k": "skip", "t": "Triage is set up but no live solution can be offered"})

	# 9. unrouted
	trace.append({"k": "skip", "t": "No live solution answers on this number. The message gets no reply."})
	return decision("unrouted", None, target=_target(None))
