"""Dispatch safety for a gateway message routed to a Flow.

Routes pick the Flow; this module decides whether the message may start it (Active, owner still allowed, trigger
filters, conversation order, rate cap) and where a skipped message goes (the Gateway's default agent, never back to the
same Flow). ``pick_gateway_entry`` is the entry-node rule used by ``engine.select_entry_node``.
"""

from __future__ import annotations

import json
import time

from huf.ai.flow.gateways.gateway_triggers import GATEWAY_NODE_TYPES, matches, over_rate_cap, param_map

SENSITIVE_CAPABILITY = "flows.publish_sensitive"
NOTE_NOT_LIVE = "Skipped: flow is not live"
NOTE_OWNER = "Skipped: the flow's owner can no longer run it from this channel"
NOTE_NO_MATCH = "Skipped: did not match the flow's filters"
NOTE_RATE = "Skipped: rate limit"
BUSY_WAIT_SECONDS = 2.0
BUSY_REQUEUE_LIMIT = 25  # same bound as gateway_service._REQUEUE_MAX


# -- entry selection ------------------------------------------------------------------------------


def pick_gateway_entry(defn: dict, entries: list[str], types: dict, event: dict | None) -> str:
	"""The entry node for a Gateway run.

	A flow with no gateway-type trigger starts at ``entries[0]`` as it always did. With gateway triggers, a real message
	(payload has ``gateway_event``) starts at the first one whose channel and filters match (OR across triggers);
	a payload without a real event (a test run) takes the trigger for the payload's channel, else the first one.
	Raises ``ValueError`` when triggers exist but none match; never raises otherwise.
	"""
	candidates = [e for e in entries if types.get(e) in GATEWAY_NODE_TYPES]
	if not candidates:
		return entries[0]
	payload = event if isinstance(event, dict) else {}
	nodes = {n.get("id"): n for n in defn.get("nodes", []) if isinstance(n, dict)}
	channel = str(payload.get("gateway") or "")
	if not payload.get("gateway_event"):
		for node_id in candidates:
			if channel and str((nodes[node_id].get("config") or {}).get("gateway") or "") == channel:
				return node_id
		return candidates[0]
	for node_id in candidates:
		node = nodes.get(node_id) or {}
		ok, _reason = matches(node.get("config"), payload, channel, node.get("type") or "trigger.gateway")
		if ok:
			return node_id
	raise ValueError("No gateway trigger of this flow matches the message.")


def _graph(raw) -> dict:
	try:
		defn = json.loads(raw) if isinstance(raw, str) else raw
	except ValueError:
		return {}
	return defn if isinstance(defn, dict) else {}


def _entries_and_types(defn: dict):
	entry = defn.get("entry")
	entries = [entry] if isinstance(entry, str) else [e for e in (entry or []) if isinstance(e, str)]
	return entries, {n.get("id"): n.get("type") for n in defn.get("nodes", []) if isinstance(n, dict)}


# -- checks -----------------------------------------------------------------------------------------


def owner_problem(owner: str, gateway_name: str) -> str | None:
	"""Why the flow's owner may no longer start a gateway-triggered run, or None when still fine."""
	import frappe

	from huf.permissions import has_capability

	if not owner or not frappe.db.get_value("User", owner, "enabled"):
		return "owner is disabled"
	if not has_capability(owner, SENSITIVE_CAPABILITY):
		return "owner lost the publish capability"
	if not frappe.has_permission("Gateway", "write", doc=gateway_name, user=owner):
		return "owner cannot write to the gateway"
	return None


def conversation_is_busy(gateway: str, conversation_id: str, this_event: str) -> bool:
	"""True while an earlier Flow Run of this conversation is Running (Waiting / approval does not count)."""
	import frappe

	if not conversation_id:
		return False
	runs = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway, "conversation_id": conversation_id, "name": ["!=", this_event], "flow_run": ["is", "set"]},
		pluck="flow_run",
		order_by="creation desc",
		limit=20,
	)
	return bool(runs) and bool(frappe.db.exists("Flow Run", {"name": ["in", runs], "status": "Running"}))


def _requeue_count(event_name: str) -> int:
	import frappe

	return int(frappe.cache().get_value(f"huf_gw_requeue:{event_name}") or 0)


def _flow_row(flow_id: str):
	import frappe

	return frappe.db.get_value("Flow Definition", flow_id, ["status", "owner", "definition_json"], as_dict=True)


def fall_through(event, gateway, note: str, svc=None) -> dict:
	"""A skipped message goes to the Gateway's default agent, else it is left Unrouted. Never to the same Flow."""
	if svc is None:
		from huf.ai import gateway_service as svc

	if getattr(gateway, "default_target_type", None) == "Agent" and getattr(gateway, "default_agent", None):
		event.db_set(
			{
				"target_type": "Agent",
				"target_agent": gateway.default_agent,
				"target_flow": None,
				"status": "Queued",
				"error_message": note,
			}
		)
		result = svc._process_gateway_event(event.name)
		return {**result, "skipped": True, "note": note}
	svc._reject_gateway_event(gateway, event, "Unrouted", note)
	return {"event_name": event.name, "status": "Unrouted", "skipped": True, "note": note}


def gate_flow_start(event, gateway, payload: dict) -> tuple[str | None, bool]:
	"""Run the dispatch checks in order. Returns ``(skip_note, wants_transcript)``; no note means start the Flow.

	May raise ``gateway_service.ConversationBusy`` (the caller requeues the event)."""
	row = _flow_row(event.target_flow)
	if not row or row.get("status") != "Active":
		return NOTE_NOT_LIVE, False
	defn = _graph(row.get("definition_json"))
	entries, types = _entries_and_types(defn)
	if not any(types.get(e) in GATEWAY_NODE_TYPES for e in entries):
		return None, False  # a plain route-bound flow: no trigger node, nothing to filter
	problem = owner_problem(row.get("owner"), gateway.name)
	if problem:
		return f"{NOTE_OWNER} ({problem})", False
	try:
		node_id = pick_gateway_entry(defn, entries, types, payload)
	except ValueError:
		return NOTE_NO_MATCH, False
	node = next((n for n in defn.get("nodes", []) if isinstance(n, dict) and n.get("id") == node_id), {})
	params = param_map(node.get("config"))
	if not params.get("allow_parallel") and conversation_is_busy(gateway.name, event.conversation_id, event.name):
		if _requeue_count(event.name) < BUSY_REQUEUE_LIMIT:
			from huf.ai.gateway_service import ConversationBusy

			time.sleep(BUSY_WAIT_SECONDS)
			raise ConversationBusy("An earlier run of this conversation is still running")
	if over_rate_cap(event.target_flow, gateway.name, payload.get("sender_id"), params.get("max_runs_per_sender_per_hour")):
		return NOTE_RATE, False
	return None, wants_voice(params)


def wants_voice(params: dict) -> bool:
	"""A trigger that asks for voice notes (or audio) wants them transcribed (Q7: opt-in)."""
	kinds = params.get("message_kinds")
	return isinstance(kinds, list) and any(k in ("voice", "audio") for k in kinds)


def add_transcript(payload: dict, gateway) -> None:
	"""Fill ``input.transcript`` from the saved voice file by speech to text. Best effort, never raises.

	Runs inside the enqueued job, never in the webhook. The text is customer-provided, so it is wrapped as untrusted."""
	if payload.get("message_type") not in ("voice", "audio") or not payload.get("attachments"):
		return
	try:
		import frappe

		from huf.ai.audio_service import transcribe_audio_file
		from huf.ai.gateways.safety import wrap_untrusted

		agent = getattr(gateway, "default_agent", None)
		file_name = frappe.db.get_value("File", {"file_url": payload["attachments"][0]}, "name")
		if not (agent and file_name):
			return
		out = transcribe_audio_file(file_id=file_name, agent_name=agent) or {}
		text = str(out.get("transcript") or "").strip() if out.get("success") else ""
		if text:
			payload["transcript"] = wrap_untrusted(text, "voice_transcript", max_chars=4000)
	except Exception:
		return
