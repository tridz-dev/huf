"""Park / resume contract for Flow nodes that wait (timers, replies, child flows).

A node returns ``park_run(...)`` to put its run to sleep; something else later calls ``wake_run`` (timer sweeper,
resume endpoint, child completion) or ``cancel_run``. Nothing here ever sleeps in a worker.

Invariants: every wake / cancel is a conditional ``_transition_run`` under the run lock, so a loser no-ops; the
continuation is always enqueued (``queue="short"``), never run inline; a resume token is never stored: it is an HMAC
(site encryption key) of the run, the node and a per-park nonce, so editors can show it again and a re-park voids it.
The caller persists the run context (``_persist_context``) before parking, as the approval node does.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime

from huf.ai.graph.executor import Outcome, PauseRequest
from huf.ai.transaction import commit_if_background

WAIT_STATUS = "Waiting Timer"
MAX_WAIT_DAYS_DEFAULT = 365
MAX_PAYLOAD_BYTES = 64 * 1024


@dataclass
class ParkRequest:
	"""What a node returns to park."""

	reason: str  # "wait" | "retry" | "reply" | "timeout" | "child" | app-defined
	resume_at: datetime | None  # naive UTC; None = wait for an external resume only
	token: bool = False  # generate a single-use resume token
	member_key: str | None = None
	extra: dict = field(default_factory=dict)  # stored in ``waiting``


def max_wait_days() -> int:
	return int(frappe.conf.get("huf_flow_wait_max_days") or MAX_WAIT_DAYS_DEFAULT)


def _token_for(run_name: str, waiting: dict) -> str | None:
	from frappe.utils.password import get_encryption_key

	nonce = waiting.get("token_nonce")
	if not nonce:
		return None
	message = f"{run_name}:{waiting.get('node_id')}:{nonce}".encode()
	return hmac.new(get_encryption_key().encode(), message, hashlib.sha256).hexdigest()


def resume_token(flow_run) -> str | None:
	"""The resume token of a run parked with ``token=True`` (None otherwise). Callers must check access first."""
	return _token_for(flow_run.name, _waiting(flow_run))


def _waiting(flow_run) -> dict:
	raw = getattr(flow_run, "waiting", None)
	if isinstance(raw, dict):
		return raw
	try:
		data = json.loads(raw or "{}")
	except (TypeError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}


def park_run(flow_run, node: dict, req: ParkRequest) -> Outcome:
	"""Put the run to sleep at ``node``. With ``req.token`` the run can be woken by ``resume_token(flow_run)``."""
	from huf.ai.flow.engine import TERMINAL_STATUSES, _transition_run

	resume_at = req.resume_at
	waiting = {
		"type": "timer",
		"node_id": node.get("id"),
		"reason": req.reason,
		"resume_at": resume_at.isoformat() if resume_at else None,
		"mode": "timed" if resume_at else "external",
		"extra": req.extra or {},
	}
	if req.token:
		waiting["token_nonce"] = frappe.generate_hash(length=20)
	if _transition_run(
		flow_run,
		{
			"status": WAIT_STATUS,
			"resume_at": resume_at,
			"member_key": req.member_key,
			"waiting": json.dumps(waiting, default=str),
		},
		not_from_statuses=TERMINAL_STATUSES,
	):
		commit_if_background()
	return Outcome.paused(PauseRequest(kind="timer", status_label=WAIT_STATUS))


def is_reentry(flow_run, node: dict) -> dict | None:
	"""The waiting record for THIS node, only once the run was woken (status Running); never while still parked."""
	if getattr(flow_run, "status", None) != "Running":
		return None
	waiting = _waiting(flow_run)
	if waiting.get("node_id") != node.get("id") or not waiting.get("woke"):
		return None
	return waiting


def verify_token(flow_run, token: str) -> bool:
	expected = resume_token(flow_run)
	return bool(expected and token) and hmac.compare_digest(expected, str(token))


def wake_run(flow_run_name: str, reason: str, payload=None, *, enqueue: bool = True) -> bool:
	"""Move a ``Waiting Timer`` run back to Running and continue it. True only for the single winner."""
	from huf.ai.flow.engine import _acquire_run_lock, _release_run_lock, _transition_run, run_flow

	if payload is not None and len(json.dumps(payload, default=str).encode()) > MAX_PAYLOAD_BYTES:
		frappe.throw(f"Wake payload is larger than {MAX_PAYLOAD_BYTES // 1024} KB.")
	if not _acquire_run_lock(flow_run_name):
		return False
	try:
		flow_run = frappe.get_doc("Flow Run", flow_run_name)
		if flow_run.status != WAIT_STATUS:
			return False
		waiting = _waiting(flow_run)
		waiting["woke"] = {"reason": reason, "payload": payload, "at": datetime.now(timezone.utc).isoformat()}
		if not _transition_run(
			flow_run,
			{"status": "Running", "resume_at": None, "waiting": json.dumps(waiting, default=str)},
			from_statuses=(WAIT_STATUS,),
		):
			return False
		commit_if_background()
	finally:
		_release_run_lock(flow_run_name)
	if enqueue:
		frappe.enqueue("huf.ai.flow.engine.run_flow", queue="short", flow_run_name=flow_run_name)
	else:
		run_flow(flow_run_name)
	return True


def cancel_run(flow_run_name: str, by: str) -> bool:
	"""Cancel a Queued or waiting run. True only when this call moved it (a run that already finished is left alone)."""
	from huf.ai.flow import engine
	from huf.ai.flow.nodes import subflow
	from huf.ai.flow.support.approval_notifications import _clear_flow_notifications

	flow_run = frappe.get_doc("Flow Run", flow_run_name)
	message = f"Cancelled by {by}."
	if not engine._transition_run(
		flow_run,
		{"status": "Cancelled", "last_error": message, "completed_at": now_datetime()},
		from_statuses=("Queued", *engine.WAITING_STATUSES),
	):
		return False
	commit_if_background()
	try:
		_clear_flow_notifications(flow_run)  # best effort: approvers stop seeing a request that no longer exists
	except Exception:
		pass
	engine._sync_gateway_event(flow_run, "Cancelled", error=message)
	engine._publish_flow_event(flow_run, "flow_cancelled", {"error": message})
	subflow.cancel_waited_child(flow_run, by)
	subflow.on_child_finished(flow_run, "Cancelled", message)
	return True


def wake_due_waits(now: datetime | None = None, limit: int = 500) -> list[str]:
	"""Scheduler entry (every minute): wake every ``Waiting Timer`` run whose ``resume_at`` has passed.

	Each continuation is enqueued on the short queue, never run here, so a big tick cannot hold the scheduler.
	"""
	names = frappe.get_all(
		"Flow Run",
		filters={"status": "Waiting Timer", "resume_at": ["<=", now or datetime.now(timezone.utc).replace(tzinfo=None)]},
		order_by="resume_at asc",
		limit_page_length=limit,
		pluck="name",
	)
	woken: list[str] = []
	for name in names:
		try:
			if wake_run(name, "elapsed"):
				woken.append(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow wait wake: {name}")
	return woken
