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
# A busy per-source lock means the SOURCE is busy (e.g. a killed worker left
# ``knowledge_index_<source>`` set for its 300s TTL), not that the item
# failed. Back off inside the job, then re-chain; give up on the pending rows
# only after the source stayed busy past the lock TTL plus a margin.
BUSY_BACKOFF_SECONDS = 10
BUSY_CAP_SECONDS = 360
BUSY_SINCE_PREFIX = "huf:ingest_busy_since:"
RUNNING_STALE_MINUTES = 3
QUEUED_STALE_MINUTES = 5
# Scan jobs heartbeat the header; silence this long means the worker is gone.
SCANNING_STALE_MINUTES = 20
# Must exceed the runner job timeout (1500s) so a slow-but-alive item is
# never reset and processed twice.
PROCESSING_STALE_MINUTES = 30

INGESTION_LOCK_PREFIX = "huf:ingest_lock:"

# Scanning = a source scan job is still building the manifest (File docs);
# it blocks new submits and cancels like Queued/Running.
ACTIVE_INGESTION_STATUSES = ("Scanning", "Queued", "Running")

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
					from .bulk_materialize import materialize

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
			_set_if_running(
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

		try:
			result = process_knowledge_input(row.name)
		except Exception as e:
			# One bad item must not fail the whole batch.
			frappe.db.rollback()
			frappe.db.set_value(
				"Knowledge Input", row.name, {"status": "Error", "error_message": str(e)[:500]}
			)
			frappe.db.commit()
			frappe.log_error(frappe.get_traceback(), f"Bulk ingestion item {row.name} failed")
			processed += 1
			continue

		if result.get("status") == "busy":
			# Source-level contention, not an item failure: undo the claim
			# (no attempt increment), stop the slice so the remaining rows
			# are not burned, and back off before the caller re-chains.
			frappe.db.set_value(
				"Knowledge Input", row.name, {"status": "Pending", "attempts": attempts - 1}
			)
			frappe.db.commit()
			_handle_source_busy(ingestion_name, lock_key)
			break

		_clear_busy(ingestion_name)

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
		# Heartbeat: the sweeper treats a Running header with stale
		# ``modified`` as orphaned.
		frappe.db.set_value("Knowledge Ingestion", ingestion_name, "modified", now_datetime(), update_modified=False)
		frappe.db.commit()

	return processed


def _clear_busy(ingestion_name: str) -> None:
	try:
		frappe.cache().delete(BUSY_SINCE_PREFIX + ingestion_name)
	except Exception:
		pass


def _handle_source_busy(ingestion_name: str, lock_key: str) -> None:
	"""Track how long the source has been busy; back off or fail the rest.

	The first-busy timestamp lives in the cache (no schema change); losing it
	only restarts the clock. Past BUSY_CAP_SECONDS the remaining Pending rows
	get a clear Error instead of being retried forever.
	"""
	key = BUSY_SINCE_PREFIX + ingestion_name
	now = time.time()
	since = frappe.cache().get(key)
	try:
		since = float(since) if since is not None else None
	except (TypeError, ValueError):
		since = None
	if since is None:
		frappe.cache().set(key, now, ex=BUSY_CAP_SECONDS * 4)
		since = now

	if now - since > BUSY_CAP_SECONDS:
		frappe.db.sql(
			"""
			UPDATE `tabKnowledge Input`
			SET status = 'Error', error_message = %s
			WHERE ingestion = %s AND status = 'Pending'
			""",
			(_("Another indexing job held this source for too long"), ingestion_name),
		)
		frappe.db.commit()
		_clear_busy(ingestion_name)
		return

	# Keep the ingestion lock alive while waiting, then let the source lock
	# expire/free before the next slice.
	try:
		frappe.cache().expire(lock_key, LOCK_TTL_SECONDS)
	except Exception:
		pass
	time.sleep(BUSY_BACKOFF_SECONDS)


def _finalize_or_self_chain(ingestion_name: str, slice: int) -> dict:
	"""Self-chain while Pending rows remain; otherwise finalize terminal status."""
	counts = count_ingestion_items(ingestion_name)
	header_status = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status")

	if header_status == "Cancelled":
		return {"status": "cancelled"}

	if counts["pending"] > 0:
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
		return {"status": "chained", "next_slice": next_slice, "remaining": counts["pending"]}

	if not should_finalize(counts):
		# Processing rows are crash markers. Finalizing now (with Pending==0
		# and processing>0) would strand them forever -- the sweeper resets
		# Processing rows independent of header status, then re-enqueues this
		# Running header. Leave the header Running and return without work.
		return {
			"status": "waiting",
			"reason": "Processing rows outstanding",
			"processing": counts["processing"],
		}

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

	_set_if_running(ingestion_name, updates)

	# process_knowledge_input flips the whole source to Error on any single
	# item failure; after a batch, per-item errors live on the rows, so a
	# source with indexed content is Ready.
	if counts.get("indexed"):
		source = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "knowledge_source")
		if frappe.db.get_value("Knowledge Source", source, "status") == "Error":
			frappe.db.set_value("Knowledge Source", source, {"status": "Ready", "error_message": None})
	frappe.db.commit()


def _set_if_running(ingestion_name: str, updates: dict) -> None:
	"""Terminal write guarded on an active status so a concurrent cancel is
	never overwritten by Completed/Failed."""
	cols = ", ".join(f"`{k}` = %s" for k in updates)
	frappe.db.sql(
		f"UPDATE `tabKnowledge Ingestion` SET {cols}, modified = %s "
		"WHERE name = %s AND status IN ('Scanning', 'Queued', 'Running')",
		(*updates.values(), now_datetime(), ingestion_name),
	)


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
