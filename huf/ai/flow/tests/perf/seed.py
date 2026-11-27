"""Bulk seed data for the Flow load gates (H-W1-08, H-W2-21). Not a test: it asserts nothing.

Rows are written with ``frappe.db.bulk_insert`` (no controllers, hooks or link checks) and carry the
``perfseed-`` marker so :func:`cleanup` removes exactly them. Only fields that exist today are written.
All values are synthetic. See README.md in this folder.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import now_datetime

from huf.ai.flow.runs.member import member_name
from huf.ai.flow.runs.park import WAIT_STATUS
from huf.ai.gateway_service import _idempotency_key

PREFIX = "perfseed-"
GATEWAY = f"{PREFIX}gateway"
FLOW_COUNT = 8
# Running and Queued are left out so the stale-run sweeper has nothing to act on.
IDLE_STATUSES = ("Success", "Success", "Success", "Failed", "Cancelled", "Waiting User", WAIT_STATUS)
STANDARD_FIELDS = ("name", "creation", "modified", "owner", "modified_by", "docstatus", "idx")


def flow_name(i: int) -> str:
	return f"{PREFIX}flow-{i % FLOW_COUNT}"


def run_name(i: int) -> str:
	return f"{PREFIX}run-{i:08d}"


def member_key(i: int) -> str:
	return f"{PREFIX}member-{i:08d}"


def provider_event_id(i: int) -> str:
	return f"{PREFIX}msg-{i:08d}"


def replay_event_ids(total: int = 10_000, stored: int = 10_000, duplicate_every: int = 10):
	"""Inbound id stream for a replay: every ``duplicate_every``-th id is already stored, the rest are new."""
	for i in range(total):
		yield provider_event_id(i % stored if i % duplicate_every == 0 else stored + i)


def new_job() -> None:
	"""Forget per-job state before a job run inline here. A worker starts every job fresh; without this,
	``currently_saving`` and the unflushed realtime log grow over the whole load and slow the later jobs."""
	frappe.flags.currently_saving = []
	if hasattr(frappe.local, "_realtime_log"):
		del frappe.local._realtime_log


def _bulk_insert(doctype: str, rows: list[dict]) -> None:
	if not rows:
		return
	stamp = now_datetime()
	standard = {
		"creation": stamp,
		"modified": stamp,
		"owner": "Administrator",
		"modified_by": "Administrator",
	}
	standard.update(docstatus=0, idx=0)
	fields = list(dict.fromkeys((*STANDARD_FIELDS, *rows[0])))
	values = [tuple({**standard, **row}[field] for field in fields) for row in rows]
	frappe.db.bulk_insert(doctype, fields, values)


def seed_runs(total: int = 10_000, due: int = 1_000) -> int:
	"""``due`` timed waits whose ``resume_at`` has passed, then mixed-status rows (some waits in the future)."""
	utc_now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
	rows = []
	for i in range(total):
		status = WAIT_STATUS if i < due else IDLE_STATUSES[i % len(IDLE_STATUSES)]
		resume_at = None
		if status == WAIT_STATUS:
			offset = timedelta(seconds=1 + i % 3600)
			resume_at = utc_now - offset if i < due else utc_now + timedelta(days=30) + offset
		waiting = None
		if resume_at:
			waiting = json.dumps(
				{
					"type": "timer",
					"node_id": "wait",
					"reason": "wait",
					"resume_at": resume_at.isoformat(),
					"mode": "timed",
					"extra": {},
				}
			)
		rows.append(
			{
				"name": run_name(i),
				"flow_definition": flow_name(i),
				"flow_id": flow_name(i),
				"status": status,
				"resume_at": resume_at,
				"member_key": member_key(i),
				"current_node_id": "wait",
				"context_json": "{}",
				"waiting": waiting,
			}
		)
	_bulk_insert("Agent Flow Run", rows)
	return len(rows)


def seed_members(total: int = 10_000, due: int = 1_000, expired: int = 1_000) -> int:
	"""Members 0..due-1 wait on the due run of the same index; the last ``expired`` are past default retention."""
	now = now_datetime()
	rows = []
	for i in range(total):
		waits = i < due
		last_event_at = now - timedelta(days=400) if not waits and i >= total - expired else now
		rows.append(
			{
				"name": member_name(flow_name(i), member_key(i)),
				"flow": flow_name(i),
				"member_key": member_key(i),
				"status": "Waiting" if waits else "Completed",
				"current_node_id": "wait" if waits else None,
				"active_flow_run": run_name(i) if waits else None,
				"entered_at": last_event_at,
				"last_event_at": last_event_at,
				"completed_at": None if waits else last_event_at,
				"run_count": 1,
				"vars_json": "{}",
				"history_json": "[]",
			}
		)
	_bulk_insert("Flow Member State", rows)
	return len(rows)


def seed_gateway_events(total: int = 10_000) -> int:
	"""Stored events, keyed the same way ingest keys them, so a replayed id hits the existing row."""
	now = now_datetime()
	rows = [
		{
			"name": f"{PREFIX}event-{i:08d}",
			"gateway": GATEWAY,
			"idempotency_key": _idempotency_key(GATEWAY, provider_event_id(i)),
			"provider_event_id": provider_event_id(i),
			"status": "Succeeded",
			"received_at": now,
		}
		for i in range(total)
	]
	_bulk_insert("Gateway Event", rows)
	return len(rows)


def cleanup() -> None:
	"""Delete every seeded row."""
	for doctype, field in (
		("Agent Flow Run", "name"),
		("Flow Member State", "flow"),
		("Gateway Event", "name"),
	):
		frappe.db.delete(doctype, {field: ["like", f"{PREFIX}%"]})
	frappe.db.commit()


def seed_all(runs: int = 10_000, due: int = 1_000, members: int = 10_000, events: int = 10_000) -> dict:
	"""Replace any earlier seed and commit. Refuses to run on a site that does not allow tests."""
	if not frappe.conf.get("allow_tests"):
		frappe.throw("Load seed data only goes on a site with allow_tests enabled.")
	cleanup()
	counts = {
		"runs": seed_runs(runs, due),
		"members": seed_members(members, due, expired=members // 10),
		"events": seed_gateway_events(events),
	}
	frappe.db.commit()
	return counts
