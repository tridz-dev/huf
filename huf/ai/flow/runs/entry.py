"""Trigger entry policies: what a trigger firing for a member does (start, skip, or resume a waiting run)."""

import frappe

ENTRY_POLICIES = ("new_run_each_time", "resume_if_waiting", "once_per_member", "one_active_per_member")


def entry_policy_of(config) -> str:
	"""The trigger's entry policy (flat ``entry_policy`` or a gateway ``params`` entry); unknown -> new run each time."""
	from huf.ai.flow.gateways.gateway_triggers import param_map

	config = config if isinstance(config, dict) else {}
	value = config.get("entry_policy") or param_map(config).get("entry_policy")
	return value if value in ENTRY_POLICIES else "new_run_each_time"


def entry_decision(flow_id: str, policy: str, member_key: str | None, payload: dict | None = None) -> dict:
	"""What a trigger firing for ``member_key`` should do: ``{"action": "start"}``,
	``{"action": "skip", "code", "reason"}`` or ``{"action": "resume", "run"}`` (a run waiting for this member's reply
	was woken).

	For the once and one-active policies ``start`` is a claim: of concurrent calls for one member, one gets it.
	"""
	from huf.ai.flow.runs import member
	from huf.ai.flow.runs.park import wake_run

	start = {"action": "start"}
	if not member_key or policy == "new_run_each_time":
		return start
	if policy == "once_per_member":
		if member.get_member(flow_id, member_key) or not member.create_member(flow_id, member_key):
			return _skip("already_entered", "This person has already been through this flow.")
	elif policy == "one_active_per_member":
		if not member.claim_active_entry(flow_id, member_key):
			return _skip("run_in_progress", "This person already has a run in progress.")
	elif policy == "resume_if_waiting":
		run = member.find_waiting_reply_run(flow_id, member_key)
		if run:
			p = payload or {}
			reply = {k: p.get(k) for k in ("text", "message", "sender_id", "display_name") if p.get(k) is not None}
			if wake_run(run, "reply", reply):
				return {"action": "resume", "run": run}
			return _skip("reply_already_received", "This person's reply was already received.")
	return start


def _skip(code: str, reason: str) -> dict:
	return {"action": "skip", "code": code, "reason": reason}


def apply_entry_policy(flow_id: str, trigger_node_id: str, trigger_type: str, payload: dict | None):
	"""Apply the entry policy of the trigger node that fired. Returns ``None`` to start a new run, ``"skip"`` to
	start nothing, or the name of the waiting run that was resumed instead."""
	from huf.ai.flow.runs import member
	from huf.ai.flow.triggers import parse_definition

	node = next((n for n in parse_definition(frappe.db.get_value("Flow Definition", flow_id, "definition_json")).get("nodes", []) if n.get("id") == trigger_node_id), {})
	policy = entry_policy_of(node.get("config"))
	if policy == "new_run_each_time":
		return None
	decision = entry_decision(flow_id, policy, member.resolve_member_key(trigger_type, payload, frappe.session.user), payload)
	if decision["action"] == "skip":
		return "skip"
	if decision["action"] == "resume":
		return decision["run"]
	return None
