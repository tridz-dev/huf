# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Bulk ingestion recovery: the 1-min cron safety net for lost enqueues,
dead workers and poison rows."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from .bulk_runner import (
	MAX_ATTEMPTS,
	RUNNING_STALE_MINUTES,
	QUEUED_STALE_MINUTES,
	PROCESSING_STALE_MINUTES,
	INGESTION_LOCK_PREFIX,
	slice_job_id,
	run_ingestion,
)

# --- Recovery --------------------------------------------------------------

def _lock_live(ingestion_name: str) -> bool:
	"""The runner takes its lock with raw redis SET (unprefixed key), so read it
	with raw GET too -- ``get_value`` looks up a site-prefixed key and would
	never see the live lock."""
	return bool(frappe.cache().get(INGESTION_LOCK_PREFIX + ingestion_name))


def _reschedule_first_slice(ingestion_name: str) -> None:
	"""Re-enqueue the runner for a lost/wedged enqueue on the first slice."""
	frappe.enqueue(
		run_ingestion,
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=slice_job_id(ingestion_name, 0),
		ingestion_name=ingestion_name,
		entries=None,
		slice=0,
	)


def _reschedule_next_slice(ingestion_name: str) -> None:
	"""Re-enqueue the runner for an orphaned Running header (next slice)."""
	next_slice = (
		frappe.db.get_value("Knowledge Ingestion", ingestion_name, "slice_seq") or 0
	) + 1
	frappe.db.set_value("Knowledge Ingestion", ingestion_name, {"slice_seq": next_slice})
	frappe.enqueue(
		run_ingestion,
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=slice_job_id(ingestion_name, next_slice),
		ingestion_name=ingestion_name,
		entries=None,
		slice=next_slice,
	)


def recover_stalled_ingestions() -> dict:
	"""1-min cron safety net for lost enqueues and workers that died mid-slice.

	- ``Queued`` header older than 5 min with no live lock -> re-enqueue the
	  first slice (stale Queued otherwise blocks its source forever, because
	  submit refuses while any Queued|Running ingestion exists).
	- ``Running`` header with stale ``modified`` (older than 3 min) and no live
	  lock -> re-enqueue the runner.
	- ``Processing`` rows older than 10 min -> ``Pending`` (crash markers),
	  regardless of header status (a finalized header may leave them stranded).
	"""
	from frappe.utils import add_to_date

	now = now_datetime()
	recovered = 0
	rescheduled = []

	# Crash-marked Processing rows -> Pending (older than 10 minutes),
	# independent of header status: a header may have finalized (Pending==0)
	# while rows were stranded Processing, and nothing else would ever
	# unstick them. Scoped to bulk rows (ingestion is set).
	stale_rows = frappe.get_all(
		"Knowledge Input",
		filters={
			"ingestion": ("is", "set"),
			"status": "Processing",
			"modified": ("<", add_to_date(now, minutes=-PROCESSING_STALE_MINUTES)),
		},
		fields=["name", "attempts"],
	)
	for row in stale_rows:
		if int(row.attempts or 0) >= MAX_ATTEMPTS:
			# Poison item (kills the worker every time): stop retrying it.
			frappe.db.set_value(
				"Knowledge Input",
				row.name,
				{
					"status": "Error",
					"error_message": _("Worker died while processing this item {0} times; giving up").format(
						MAX_ATTEMPTS
					),
				},
			)
		else:
			frappe.db.set_value("Knowledge Input", row.name, {"status": "Pending"})
		recovered += 1

	# Orphaned Queued header: lost enqueue or wedged queue. Use the
	# modified-time heuristic (the Running path's approach); enqueue
	# deduplication guards against a duplicate when the original job is
	# merely slow. The manifest persisted on the header makes the first
	# slice re-materializable.
	queued = frappe.get_all("Knowledge Ingestion", filters={"status": "Queued"}, pluck="name")
	for ingestion_name in queued:
		header_modified = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "modified")
		if not header_modified or header_modified >= add_to_date(now, minutes=-QUEUED_STALE_MINUTES):
			continue
		if _lock_live(ingestion_name):
			continue
		_reschedule_first_slice(ingestion_name)
		rescheduled.append(ingestion_name)

	running = frappe.get_all(
		"Knowledge Ingestion", filters={"status": "Running"}, pluck="name"
	)
	for ingestion_name in running:
		# Orphaned Running header: stale modified and no live lock.
		header_modified = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "modified")
		if header_modified and header_modified < add_to_date(now, minutes=-RUNNING_STALE_MINUTES):
			lock_live = _lock_live(ingestion_name)
			if not lock_live:
				_reschedule_next_slice(ingestion_name)
				rescheduled.append(ingestion_name)

	if recovered or rescheduled:
		frappe.db.commit()

	return {"recovered_rows": recovered, "rescheduled": rescheduled}
