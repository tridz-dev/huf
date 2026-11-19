# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Bulk knowledge ingestion runner (V1).

One self-chaining, slice-bounded job on the ``long`` queue that calls the
existing ``process_knowledge_input()`` per item, with the per-source lock in
play. See docs/bulk-ingestion-contract.md for the frozen contract.
"""

from __future__ import annotations

import json
import time

import frappe
from frappe import _
from frappe.utils import now_datetime

SLICE_LIMIT = 25
SLICE_DEADLINE_SECONDS = 600
LOCK_TTL_SECONDS = 120
MAX_ATTEMPTS = 5

INGESTION_LOCK_PREFIX = "huf:ingest_lock:"

TERMINAL_INGESTION_STATUSES = (
	"Cancelled",
	"Completed",
	"Completed with Errors",
	"Failed",
)


# --- Pure helpers (no frappe access; unit-tested bench-less) ---------------

def compute_progress(counts: dict) -> float:
	"""Contract progress: (indexed + error + skipped) / total, 0 when total=0."""
	total = int(counts.get("total") or 0)
	if total <= 0:
		return 0.0
	done = sum(int(counts.get(status) or 0) for status in ("indexed", "error", "skipped"))
	return done / total


def slice_job_id(ingestion_name: str, slice_seq: int) -> str:
	"""Job id per slice; slice counter required for enqueue deduplication."""
	if slice_seq and slice_seq > 0:
		return f"huf_ingest_{ingestion_name}_{slice_seq}"
	return f"huf_ingest_{ingestion_name}"


def decide_idempotency(existing_status: str | None, existing_checksum: str | None, entry_checksum: str | None) -> str:
	"""Idempotency decision for a (source, external_key) row, contract precedence order.

	Returns one of:
	  "create"         -- no existing row; caller may still mark Skipped/Duplicate
	                      for an in-batch checksum duplicate (rule 4)
	  "skip_unchanged" -- Indexed/Skipped + same checksum -> Skipped/Unchanged
	  "reset_pending"  -- Indexed/Skipped + different (or missing) checksum, or
	                      Error -> reset to Pending (re-index; rows are reused)
	  "leave_alone"    -- Pending/Processing (or unknown) -> idempotent replay

	Checksum comparison requires both values present; without a checksum the
	safe (conservative) behavior is to re-index.
	"""
	if not existing_status:
		return "create"
	if existing_status in ("Indexed", "Skipped"):
		if existing_checksum and entry_checksum and existing_checksum == entry_checksum:
			return "skip_unchanged"
		return "reset_pending"
	if existing_status == "Error":
		return "reset_pending"
	# Pending / Processing / anything unknown: idempotent replay.
	return "leave_alone"


def should_adopt_row(row_ingestion: str | None, row_ingestion_status: str | None) -> bool:
	"""Adoption rule for a ``leave_alone`` row being replayed into a new ingestion.

	Adopt when the row is unclaimed (no ``ingestion`` backref) or when the batch
	it currently belongs to is terminal (Cancelled/Failed/Completed/…): a
	cancelled batch must not orphan its rows forever. Never adopt from a live
	(Queued/Running) batch -- that would steal rows from another running slice.
	"""
	if not row_ingestion:
		return True
	return (row_ingestion_status or "") in TERMINAL_INGESTION_STATUSES


def should_finalize(counts: dict) -> bool:
	"""Never finalize while rows are still Processing.

	Processing rows are crash markers; a finalization while ``processing > 0``
	strands them forever (the sweeper only resets them while the header is
	still Running and recoverable). Leave the header Running so the sweeper can
	reset the rows and re-enqueue the runner.
	"""
	return int(counts.get("processing") or 0) == 0


def needs_materialization(materialized_total: int, declared_total: int) -> bool:
	"""Materialize whenever fewer rows exist than were accepted at submit.

	Submits that were interrupted mid-materialize (crash, lost enqueue) leave
	``counts.total < total_items``; the stored manifest makes that recoverable.
	"""
	return int(materialized_total or 0) < int(declared_total or 0)


def load_manifest(entries: list | None, manifest_json: str | None) -> list | None:
	"""Resolve the manifest for a runner slice: an explicit ``entries`` argument
	wins; otherwise fall back to the manifest persisted on the header."""
	if entries is not None:
		return entries
	if not manifest_json:
		return None
	try:
		loaded = json.loads(manifest_json)
	except (TypeError, ValueError):
		return None
	return loaded if isinstance(loaded, list) else None


def serialize_manifest(entries: list, max_bytes: int = 2_000_000) -> str | None:
	"""Persist the accepted manifest as JSON, capped sanely.

	Returns ``None`` (nothing persisted) when the serialized manifest exceeds
	``max_bytes``; the first slice still carries ``entries`` in its enqueue
	args, and finalize reports the shortfall if the crash was unrecoverable.
	"""
	try:
		serialized = json.dumps(entries, separators=(",", ":"))
	except (TypeError, ValueError):
		return None
	if len(serialized.encode("utf-8")) > max_bytes:
		return None
	return serialized


# --- Runner ----------------------------------------------------------------

def run_ingestion(ingestion_name: str, entries: list | None = None, slice: int = 0) -> dict:
	"""Process one bounded slice of a bulk ingestion, then self-chain or finalize."""
	header_status = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status")
	if header_status is None:
		frappe.log_error(
			f"Bulk ingestion {ingestion_name} no longer exists; slice {slice} abandoned",
			"Bulk Ingestion Runner Error",
		)
		return {"status": "error", "error": "Ingestion not found"}
	if header_status in TERMINAL_INGESTION_STATUSES:
		return {"status": "skipped", "reason": f"Ingestion already {header_status}"}

	lock_key = INGESTION_LOCK_PREFIX + ingestion_name
	if not frappe.cache().set(lock_key, 1, ex=LOCK_TTL_SECONDS, nx=True):
		# Another slice of this ingestion is already running.
		return {"status": "skipped", "reason": "Another slice is running"}

	try:
		try:
			# Materialize whenever fewer rows exist than were accepted at
			# submit: an interrupted first slice (crash mid-materialize, lost
			# enqueue) is recoverable from the manifest persisted on the
			# header. Rows already materialized are handled idempotently.
			manifest = load_manifest(
				entries,
				frappe.db.get_value("Knowledge Ingestion", ingestion_name, "manifest_json"),
			)
			if manifest is not None:
				declared = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "total_items") or 0
				if needs_materialization(
					frappe.db.count("Knowledge Input", {"ingestion": ingestion_name}), declared
				):
					materialize(ingestion_name, manifest)

			# Header -> Running, but only from Queued: a concurrent
			# cancel_ingestion() sets Cancelled and must not be overwritten
			# back to Running (conditional UPDATE acts as the status guard).
			frappe.db.sql(
				"""
				UPDATE `tabKnowledge Ingestion`
				SET status = 'Running',
					started_at = COALESCE(started_at, %s)
				WHERE name = %s AND status = 'Queued'
				""",
				(now_datetime(), ingestion_name),
			)
			frappe.db.commit()

			header_status = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status")
			if header_status != "Running":
				# Cancelled concurrently (or otherwise not startable).
				return {"status": "skipped", "reason": f"Ingestion is {header_status}"}

			_processed_slice(ingestion_name, lock_key)
			return _finalize_or_self_chain(ingestion_name, slice)
		except Exception as e:
			frappe.db.rollback()
			frappe.db.set_value(
				"Knowledge Ingestion",
				ingestion_name,
				{
					"status": "Failed",
					"finished_at": now_datetime(),
					"error_message": str(e)[:500],
				},
			)
			frappe.db.commit()
			frappe.log_error(
				f"Bulk Ingestion {ingestion_name} failed: {frappe.get_traceback()}",
				"Bulk Ingestion Runner Error",
			)
			return {"status": "error", "error": str(e)}
	finally:
		frappe.cache().delete(lock_key)


def _processed_slice(ingestion_name: str, lock_key: str) -> int:
	"""Process up to SLICE_LIMIT pending items within the slice deadline.

	Returns the number of items fully processed this slice (busy-deferred items
	are NOT counted; they stay Pending and are retried by the next slice).
	"""
	from .indexer import process_knowledge_input

	rows = frappe.get_all(
		"Knowledge Input",
		filters={"ingestion": ingestion_name, "status": "Pending"},
		fields=["name", "attempts"],
		order_by="creation asc",
		limit=SLICE_LIMIT,
	)

	start = time.monotonic()
	processed = 0
	for row in rows:
		if time.monotonic() - start > SLICE_DEADLINE_SECONDS:
			break
		# Cancel check at the slice boundary (runner checks header each item;
		# cancel_ingestion() sets Cancelled + finished_at on the header).
		if frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status") == "Cancelled":
			break

		# Claim: crash marker. If the worker dies here the row is left
		# Processing and the 1-min recovery cron resets it to Pending.
		attempts = int(row.attempts or 0) + 1
		frappe.db.set_value(
			"Knowledge Input",
			row.name,
			{"status": "Processing", "attempts": attempts},
		)
		frappe.db.commit()

		result = process_knowledge_input(row.name)

		if result.get("status") == "busy":
			# Per-source lock contention: defer, not error. The item counts as
			# NOT processed in this slice. Guard against infinite busy loops:
			# after MAX_ATTEMPTS attempts, mark Error with a clear message.
			if attempts >= MAX_ATTEMPTS:
				frappe.db.set_value(
					"Knowledge Input",
					row.name,
					{
						"status": "Error",
						"error_message": _(
							"Source indexing lock was busy for {0} consecutive attempts; item abandoned for this run"
						).format(MAX_ATTEMPTS),
					},
				)
			else:
				frappe.db.set_value("Knowledge Input", row.name, {"status": "Pending"})
			frappe.db.commit()
			continue

		if result.get("status") == "success" and not result.get("chunks_created"):
			# Honesty rule: a document yielding 0 chunks is Skipped / No Text.
			frappe.db.set_value(
				"Knowledge Input",
				row.name,
				{"status": "Skipped", "skip_reason": "No Text"},
			)
			frappe.db.commit()

		processed += 1
		# Refresh the ingestion lock between items so a slow slice is not
		# orphaned by the TTL.
		try:
			frappe.cache().expire(lock_key, LOCK_TTL_SECONDS)
		except Exception:
			pass

	return processed


def _finalize_or_self_chain(ingestion_name: str, slice: int) -> dict:
	"""Self-chain while Pending rows remain; otherwise finalize terminal status."""
	remaining = frappe.db.count("Knowledge Input", {"ingestion": ingestion_name, "status": "Pending"})
	header_status = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status")

	if header_status == "Cancelled":
		return {"status": "cancelled"}

	if remaining > 0:
		next_slice = (frappe.db.get_value("Knowledge Ingestion", ingestion_name, "slice_seq") or slice or 0) + 1
		frappe.db.set_value("Knowledge Ingestion", ingestion_name, {"slice_seq": next_slice})
		frappe.db.commit()
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
		return {"status": "chained", "next_slice": next_slice, "remaining": remaining}

	_finalize(ingestion_name)
	return {"status": "completed"}


def _finalize(ingestion_name: str) -> None:
	"""Terminal status: Completed / Completed with Errors; Failed only for
	job-level crashes (handled in run_ingestion)."""
	counts = count_ingestion_items(ingestion_name)
	declared = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "total_items") or 0

	updates = {"finished_at": now_datetime()}
	if counts["total"] < declared:
		updates["status"] = "Failed"
		updates["error_message"] = _(
			"Only {0} of {1} items were materialized; the batch was interrupted before materialization completed"
		).format(counts["total"], declared)
	elif counts["error"] > 0:
		updates["status"] = "Completed with Errors"
	else:
		updates["status"] = "Completed"

	frappe.db.set_value("Knowledge Ingestion", ingestion_name, updates)
	frappe.db.commit()


def count_ingestion_items(ingestion_name: str) -> dict:
	"""Single GROUP BY over tabKnowledge Input filtered on ingestion."""
	rows = frappe.db.sql(
		"""
		SELECT status, COUNT(*) AS cnt, SUM(chunks_created) AS chunks
		FROM `tabKnowledge Input`
		WHERE ingestion = %s
		GROUP BY status
		""",
		(ingestion_name,),
		as_dict=True,
	)
	counts = {"pending": 0, "processing": 0, "indexed": 0, "error": 0, "skipped": 0, "total": 0}
	chunks_written = 0
	for row in rows:
		key = (row.status or "").lower()
		chunks_written += int(row.chunks or 0)
		if key in counts:
			counts[key] = int(row.cnt or 0)
			counts["total"] += int(row.cnt or 0)
	counts["chunks_written"] = chunks_written
	return counts


# --- Materialization -------------------------------------------------------

def materialize(ingestion_name: str, entries: list) -> dict:
	"""Create/reuse Knowledge Input rows for the accepted manifest entries.

	Implements the contract's duplicate/idempotency rules. Rows are only ever
	created by the runner, sequentially, under the ingestion lock (single-writer
	invariant). Permission is enforced at submit time; bookkeeping here runs
	with ignore_permissions.
	"""
	frappe.flags.huf_bulk_ingestion = True
	source_name = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "knowledge_source")

	stats = {"created": 0, "reused": 0, "skipped_unchanged": 0, "skipped_duplicate": 0}
	seen_checksums = set()

	try:
		for entry in entries:
			external_key = entry.get("external_key")
			checksum = entry.get("checksum") or None
			existing_name = frappe.db.get_value(
				"Knowledge Input",
				{"knowledge_source": source_name, "external_key": external_key},
			)
			existing_status = existing_checksum = None
			if existing_name:
				existing_status, existing_checksum = frappe.db.get_value(
					"Knowledge Input", existing_name, ["status", "external_checksum"]
				)
			decision = decide_idempotency(existing_status, existing_checksum, checksum)

			if decision == "create":
				# Rule 4: within one ingestion, a second entry with identical
				# external_checksum -> Skipped / Duplicate.
				if checksum and checksum in seen_checksums:
					_insert_input(
						ingestion_name,
						source_name,
						entry,
						status="Skipped",
						skip_reason="Duplicate",
					)
					stats["skipped_duplicate"] += 1
				else:
					_insert_input(ingestion_name, source_name, entry)
					stats["created"] += 1
			elif decision == "skip_unchanged":
				frappe.db.set_value(
					"Knowledge Input",
					existing_name,
					{
						"ingestion": ingestion_name,
						"external_checksum": checksum,
						"status": "Skipped",
						"skip_reason": "Unchanged",
					},
				)
				stats["skipped_unchanged"] += 1
			elif decision == "reset_pending":
				frappe.db.set_value(
					"Knowledge Input",
					existing_name,
					{
						"ingestion": ingestion_name,
						"external_checksum": checksum,
						"status": "Pending",
						"skip_reason": None,
						"error_message": None,
					},
				)
				stats["reused"] += 1
			else:  # leave_alone: idempotent replay
				# Adopt the row into this ingestion only when it is unclaimed
				# or its current batch is terminal (Cancelled/Failed/…);
				# never steal a row from a live (Queued/Running) batch.
				row_ingestion = frappe.db.get_value("Knowledge Input", existing_name, "ingestion")
				header_status = None
				if row_ingestion:
					header_status = frappe.db.get_value(
						"Knowledge Ingestion", row_ingestion, "status"
					)
				if should_adopt_row(row_ingestion, header_status):
					frappe.db.set_value(
						"Knowledge Input",
						existing_name,
						{
							"ingestion": ingestion_name,
							"external_checksum": checksum or existing_checksum,
						},
					)
				stats["reused"] += 1

			if checksum:
				seen_checksums.add(checksum)

		frappe.db.commit()
		return stats
	finally:
		frappe.flags.huf_bulk_ingestion = False


def _insert_input(ingestion_name: str, source_name: str, entry: dict, status: str = "Pending", skip_reason: str | None = None) -> None:
	"""Create one bulk Knowledge Input row (no auto-enqueue under the flag)."""
	frappe.get_doc(
		{
			"doctype": "Knowledge Input",
			"knowledge_source": source_name,
			"input_type": "File",
			"file": entry.get("file_url"),
			"ingestion": ingestion_name,
			"external_key": entry.get("external_key"),
			"external_checksum": entry.get("checksum") or None,
			"status": status,
			"skip_reason": skip_reason,
		}
	).insert(ignore_permissions=True)


# --- Recovery --------------------------------------------------------------

def recover_stalled_ingestions() -> dict:
	"""1-min cron safety net for workers that died mid-slice.

	- ``Running`` header with stale ``modified`` (older than 3 min) and no live
	  lock -> re-enqueue the runner.
	- ``Processing`` rows older than 10 min -> ``Pending`` (crash markers).
	"""
	from frappe.utils import add_to_date

	now = now_datetime()
	recovered = 0
	rescheduled = []

	running = frappe.get_all(
		"Knowledge Ingestion", filters={"status": "Running"}, pluck="name"
	)
	for ingestion_name in running:
		# Crash-marked Processing rows -> Pending (older than 10 minutes).
		stale_rows = frappe.get_all(
			"Knowledge Input",
			filters={
				"ingestion": ingestion_name,
				"status": "Processing",
				"modified": ("<", add_to_date(now, minutes=-10)),
			},
			pluck="name",
		)
		for row_name in stale_rows:
			frappe.db.set_value("Knowledge Input", row_name, {"status": "Pending"})
			recovered += 1

		# Orphaned Running header: stale modified and no live lock.
		header_modified = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "modified")
		if header_modified and header_modified < add_to_date(now, minutes=-3):
			lock_live = frappe.cache().get_value(INGESTION_LOCK_PREFIX + ingestion_name)
			if not lock_live:
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
				rescheduled.append(ingestion_name)

	if recovered or rescheduled:
		frappe.db.commit()

	return {"recovered_rows": recovered, "rescheduled": rescheduled}
