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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import frappe
from frappe.utils import get_datetime, now_datetime

from huf.ai.graph.executor import Outcome, PauseRequest
from huf.ai.transaction import commit_if_background

WAIT_STATUS = "Waiting Timer"
MAX_WAIT_DAYS_DEFAULT = 365
MAX_PAYLOAD_BYTES = 64 * 1024
WAKE_PAGE_SIZE_DEFAULT = 500  # site config: huf_flow_wake_page_size
WAKE_CHUNK_SIZE = 100
WAKE_BUDGET_SECONDS = 40  # the sweeper ticks every minute
WAKE_LOCK_KEY = "huf:flow:wake_sweeper"
WAKE_LOCK_TTL_SECONDS = 55  # above the budget, below the tick: a killed sweeper never costs the next minute
SEND_WINDOW_REASON = "send_window"
SEND_MAX_DEFERS_DEFAULT = 24  # site config: huf_flow_send_max_defers


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


def max_send_defers() -> int:
	value = frappe.conf.get("huf_flow_send_max_defers")
	try:
		value = int(value)
	except (TypeError, ValueError):
		return SEND_MAX_DEFERS_DEFAULT
	return value if value >= 0 else SEND_MAX_DEFERS_DEFAULT


def defer_send(flow_run, node: dict, defer_until: datetime, member_key: str | None = None) -> Outcome | None:
	"""Park a send the guard deferred (``GuardResult.defer_until``, aware UTC) until then.

	None once the node has been deferred ``max_send_defers()`` times: the caller must then block the send with
	``window_defer_exhausted``. On wake the node runs again and must run the whole guard chain again.
	"""
	waiting = is_reentry(flow_run, node)
	defers = 0
	if waiting and waiting.get("reason") == SEND_WINDOW_REASON:
		defers = int((waiting.get("extra") or {}).get("defers") or 0)
	if defers >= max_send_defers():
		return None
	return park_run(
		flow_run,
		node,
		ParkRequest(
			reason=SEND_WINDOW_REASON,
			resume_at=defer_until.astimezone(timezone.utc).replace(tzinfo=None),
			member_key=member_key or getattr(flow_run, "member_key", None),
			extra={"defers": defers + 1},
		),
	)


def verify_token(flow_run, token: str) -> bool:
	expected = resume_token(flow_run)
	return bool(expected and token) and hmac.compare_digest(expected, str(token))


def wake_run(
	flow_run_name: str, reason: str, payload=None, *, enqueue: bool = True, due_by: datetime | None = None
) -> bool:
	"""Move a ``Waiting Timer`` run back to Running and continue it. True only for the single winner.

	With ``due_by`` (timer wakes) the run must also still be due then: a run re-parked for later is left alone.
	"""
	from huf.ai.flow.engine import _acquire_run_lock, _release_run_lock, _transition_run, run_flow

	if payload is not None and len(json.dumps(payload, default=str).encode()) > MAX_PAYLOAD_BYTES:
		frappe.throw(f"Wake payload is larger than {MAX_PAYLOAD_BYTES // 1024} KB.")
	if not _acquire_run_lock(flow_run_name):
		return False
	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
		if flow_run.status != WAIT_STATUS:
			return False
		if due_by and not (flow_run.resume_at and get_datetime(flow_run.resume_at) <= due_by):
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

	flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
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


def wake_due_waits(now: datetime | None = None, limit: int | None = None) -> list[str]:
	"""Scheduler entry (every minute): drain the ``Waiting Timer`` runs whose ``resume_at`` has passed.

	Due runs are read in pages of ``limit`` (site config, default 500) until none are left or the time budget is
	spent. The oldest chunk is woken here; every further chunk of 100 is enqueued as a ``wake_chunk`` job. Nothing is
	claimed until ``wake_run`` moves the run, so a lost job or an overlapping tick cannot strand or double-wake one.
	Returns the runs woken here plus those handed to a chunk job. Only one sweeper per site runs at a time; a tick
	that finds the sweeper lock held does nothing.
	"""
	if not _take_sweeper_lock():
		return []
	try:
		return _drain_due_waits(now, limit)
	finally:
		_drop_sweeper_lock()


def _take_sweeper_lock() -> bool:
	try:
		cache = frappe.cache()
		return bool(cache.set(cache.make_key(WAKE_LOCK_KEY), 1, ex=WAKE_LOCK_TTL_SECONDS, nx=True))
	except Exception:  # noqa: BLE001
		return True  # the lock only avoids overlap; ``wake_run`` is what prevents a double wake


def _drop_sweeper_lock() -> None:
	try:
		cache = frappe.cache()
		cache.delete(cache.make_key(WAKE_LOCK_KEY))
	except Exception:  # noqa: BLE001, S110
		pass


def _drain_due_waits(now: datetime | None, limit: int | None) -> list[str]:
	now = now or datetime.now(timezone.utc).replace(tzinfo=None)
	page_size = int(limit or frappe.conf.get("huf_flow_wake_page_size") or WAKE_PAGE_SIZE_DEFAULT)
	deadline = time.monotonic() + WAKE_BUDGET_SECONDS
	taken: list[str] = []
	last = None
	inline = True
	while True:
		rows = _due_page(now, last, page_size)
		names = [row.name for row in rows]
		for start in range(0, len(names), WAKE_CHUNK_SIZE):
			chunk = names[start : start + WAKE_CHUNK_SIZE]
			if inline:
				taken += wake_chunk(chunk, now)
				inline = False
			else:
				frappe.enqueue("huf.ai.flow.runs.park.wake_chunk", queue="short", names=chunk, due_by=now)
				taken += chunk
		if len(rows) < page_size or time.monotonic() >= deadline:
			return taken
		last = rows[-1]


def _due_page(now: datetime, after, page_size: int) -> list:
	"""One page of due runs, oldest first, strictly after the row ``after`` (keyset on ``resume_at, name``)."""
	filters = {"status": WAIT_STATUS, "resume_at": ["<=", now]}
	or_filters = None
	if after:
		filters = [
			["status", "=", WAIT_STATUS],
			["resume_at", "<=", now],
			["resume_at", ">=", after.resume_at],
		]
		or_filters = [["resume_at", ">", after.resume_at], ["name", ">", after.name]]
	return frappe.get_all(
		"Agent Flow Run",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "resume_at"],
		order_by="resume_at asc, name asc",
		limit_page_length=page_size,
	)


def wake_chunk(names: list[str], due_by: datetime) -> list[str]:
	"""Wake each still-due run and enqueue its continuation. Returns the runs this call won."""
	woken: list[str] = []
	for name in names:
		try:
			if wake_run(name, "elapsed", due_by=due_by):
				woken.append(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow wait wake: {name}")
	return woken
