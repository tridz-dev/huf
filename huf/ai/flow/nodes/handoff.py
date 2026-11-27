"""``handoff`` node: hand the run's conversation to a human queue and park the run until a person releases it.

Config: ``conversation`` (Channel Conversation name, value or reference) or ``gateway`` + ``recipient`` (the
open conversation of that contact; ``"$member"`` is the run's member, resolved by the recipient binder and not
stored), ``reason`` (a registered reason code, stored on the run), optional
``target``, ``summary``, ``priority``, ``message`` (passed to :func:`huf.ai.channels.handoff.handoff_conversation`),
and ``timeout_ms`` + ``timeout_next`` (leave by that edge when nobody releases the conversation in time).

The node calls ``channels/handoff.py`` (idempotent), then parks with ``park.park_run`` (reason ``handoff``).
:func:`release_handoff` puts the conversation back to ``ai`` and wakes every run parked on it; the woken step is
entered again and only emits its output, so the handoff is never repeated. It is always self-routed.

A run that is not live (test run, step test, ``live_send`` off, unpublished or superseded flow: G3) hands nothing
over, sends nothing and goes on by ``next`` with output ``status: previewed``. The handoff message (config
``message``, else the gateway's ``handoff_message``) is sent only when the pre-send guard chain allows it (G5);
a blocked or deferred message is dropped and the handoff still happens.

:func:`handed_off_guard` is a ``huf_pre_send_hooks`` step: while a conversation is handed off, no automated
send reaches that contact on that gateway (block reason ``handed_off``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import frappe

from huf.ai.channels import guard, guard_steps, recipient_binder
from huf.ai.flow.runs import park
from huf.ai.flow.runs.park import ParkRequest
from huf.ai.flow.support import step_keys
from huf.ai.flow.testrun import gate as test_gate

PARK_REASON = "handoff"
BLOCK_REASON = "handed_off"
RELEASED = "released"


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _utc_now() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


def _refs(flow_run, node: dict) -> dict:
	return {
		"flow_id": getattr(flow_run, "flow_id", None),
		"flow_version": str(getattr(flow_run, "flow_version", "") or ""),
		"run_id": flow_run.name,
		"node_id": node.get("id") or "",
	}


def _find_conversation(ctx, config: dict, flow_run, node: dict) -> str | None:
	name = ctx.resolve(config.get("conversation")) if config.get("conversation") else None
	if name:
		return str(name) if frappe.db.exists("Channel Conversation", str(name)) else None
	gateway = ctx.resolve(config.get("gateway")) if config.get("gateway") else None
	recipient = config.get("recipient")
	if not gateway or not recipient:
		return None
	if recipient_binder.is_member_ref(recipient):  # the number is used for the lookup only (G4)
		try:
			recipient = recipient_binder.resolve(str(gateway), flow_run.member_key, _refs(flow_run, node))
		except recipient_binder.RecipientUnbound:
			return None
	else:
		recipient = ctx.resolve(recipient)
	return open_conversation(str(gateway), str(recipient)) if recipient else None


def contact_forms(contact: str) -> list[str]:
	"""The ways one contact may be written: as given, ``+<digits>`` and the provider's bare digits (``wa_id``)."""
	number = guard_steps.normalise_recipient(contact) or guard_steps.normalise_recipient(f"+{contact}")
	return list(dict.fromkeys([contact, number, number[1:]])) if number else [contact]


def _guarded_message(flow_run, node: dict, config: dict, conversation: str) -> str:
	"""The handoff message when the guard chain allows it, else "" (which also mutes the gateway default)."""
	from huf.ai.flow.nodes.send import channel_of

	row = frappe.db.get_value(
		"Channel Conversation", conversation, ["gateway", "contact_handle", "status"], as_dict=True
	)
	if not row or row.status == "handed_off":
		return ""
	text = config.get("message")
	if text is None:
		text = frappe.db.get_value("Gateway", row.gateway, "handoff_message")
	text = str(text or "")
	if not text.strip():
		return ""
	handle = str(row.contact_handle or "")
	result = guard.evaluate(
		{
			"member_key": getattr(flow_run, "member_key", None),
			"gateway": row.gateway,
			"channel": channel_of(row.gateway),
			"category": "service",
			"recipient": guard_steps.normalise_recipient(f"+{handle.lstrip('+')}") or handle,
			"template": None,
			"token_names": [],
			**_refs(flow_run, node),
			"step_key": step_keys.key_of(node),
			"live": True,
		}
	)
	return text if result.allowed else ""


def open_conversation(gateway: str, contact: str) -> str | None:
	"""Name of the newest not-closed conversation of ``contact`` on ``gateway``, or None."""
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"gateway": gateway, "contact_handle": ["in", contact_forms(contact)], "status": ["!=", "closed"]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=1,
	)
	return rows[0] if rows else None


def exec_handoff(flow_run, node: dict, config: dict, settings: dict):
	from huf.ai.flow.engine import _context_of, _persist_context, _transition_run
	from huf.ai.flow.support import reason_codes

	waiting = park.is_reentry(flow_run, node)
	if waiting:
		woke = waiting.get("woke") or {}
		extra = waiting.get("extra") or {}
		_transition_run(flow_run, {"waiting": None}, from_statuses=("Running",))
		timed_out = woke.get("reason") in ("timeout", "elapsed")
		timeout_next = extra.get("timeout_next")
		return {
			"status": "success",
			"output": {
				"conversation": extra.get("conversation"),
				"reason": extra.get("reason"),
				"released": not timed_out,
				"woke_reason": woke.get("reason"),
				"woke_at": woke.get("at"),
			},
			"next_node_id": timeout_next if timed_out and timeout_next else node.get("next"),
		}

	if not test_gate.is_live(flow_run):  # G3: nothing is handed over or sent
		output = {"status": "previewed", "released": False}
		return {"status": "success", "output": output, "result": output, "next_node_id": node.get("next")}

	ctx = _context_of(flow_run, settings)
	conversation = _find_conversation(ctx, config, flow_run, node)
	if not conversation:
		return _failed(
			"No open conversation was found to hand to a person. Choose the conversation, or the channel and contact."
		)
	resume_at = None
	if config.get("timeout_ms"):
		try:
			resume_at = _utc_now() + timedelta(milliseconds=int(config["timeout_ms"]))
		except (TypeError, ValueError):
			return _failed("Set the handoff timeout as a whole number of milliseconds.")
		if resume_at - _utc_now() > timedelta(days=park.max_wait_days()):
			return _failed(f"This handoff waits longer than the {park.max_wait_days()} days a flow may wait.")

	from huf.ai.channels.handoff import handoff_conversation

	summary = str(ctx.resolve(config.get("summary")) or "") if config.get("summary") else ""
	_persist_context(flow_run, ctx, settings)  # a guard pass with a cap commits
	message = _guarded_message(flow_run, node, config, conversation)
	result = handoff_conversation(
		conversation,
		target=config.get("target"),
		summary=summary,
		priority=str(config.get("priority") or "normal"),
		message=message,
	)
	extra = {
		"conversation": conversation,
		"reason": reason_codes.normalize(config["reason"]) if config.get("reason") else None,
		"handoff_doctype": result.get("doctype"),
		"handoff_name": result.get("name"),
	}
	if config.get("timeout_next"):
		extra["timeout_next"] = config["timeout_next"]
	_persist_context(flow_run, ctx, settings)
	return park.park_run(
		flow_run,
		node,
		ParkRequest(reason=PARK_REASON, resume_at=resume_at, member_key=flow_run.member_key, extra=extra),
	)


def parked_runs(conversation: str) -> list[str]:
	"""Runs parked by a handoff step on ``conversation``."""
	rows = frappe.get_all(
		"Agent Flow Run",
		filters={"status": park.WAIT_STATUS, "waiting": ["like", f"%{conversation}%"]},
		fields=["name", "waiting"],
	)
	names = []
	for row in rows:
		try:
			waiting = json.loads(row.waiting or "{}")
		except (TypeError, ValueError):
			continue
		if (
			waiting.get("reason") == PARK_REASON
			and (waiting.get("extra") or {}).get("conversation") == conversation
		):
			names.append(row.name)
	return names


def release_handoff(conversation: str, *, enqueue: bool = True) -> list[str]:
	"""Give ``conversation`` back to the AI and wake the runs its handoff parked. Returns the woken run names."""
	doc = frappe.get_doc("Channel Conversation", conversation)
	if doc.status == "handed_off":
		doc.db_set("status", "ai")
	return [name for name in parked_runs(conversation) if park.wake_run(name, RELEASED, enqueue=enqueue)]


def handed_off_guard(request: dict) -> dict:
	"""Pre-send step: block an automated send to a contact whose conversation on that gateway is handed off."""
	gateway, recipient = request.get("gateway"), request.get("recipient")
	if not gateway or not recipient:
		return {"allow": True}
	handed = frappe.db.exists(
		"Channel Conversation",
		{"gateway": gateway, "contact_handle": ["in", contact_forms(str(recipient))], "status": "handed_off"},
	)
	return {"allow": False, "reason": BLOCK_REASON} if handed else {"allow": True}
