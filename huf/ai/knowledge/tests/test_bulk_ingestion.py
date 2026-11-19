# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Pure-logic tests for the bulk ingestion contract math.

These run WITHOUT a bench (the repo pytest frappe stub kicks in via
pyproject.toml addopts). Anything that touches the database, Redis, or the
background queue -- bulk_runner.run_ingestion / materialize /
recover_stalled_ingestions, bulk_api.submit_files, and the DocType
controllers -- needs a live bench and is deliberately not covered here.
"""

from huf.ai.knowledge.bulk_runner import (
	compute_progress,
	decide_idempotency,
	load_manifest,
	needs_materialization,
	should_adopt_row,
	should_finalize,
	slice_job_id,
)


class TestProgressMath:
	"""Contract: progress = (indexed + error + skipped) / total, 0 when total=0."""

	def test_progress_contract_example(self):
		counts = {"pending": 210, "processing": 1, "indexed": 760, "error": 12, "skipped": 15, "total": 998}
		assert compute_progress(counts) == (760 + 12 + 15) / 998

	def test_progress_zero_when_total_zero(self):
		assert compute_progress({"pending": 0, "indexed": 0, "error": 0, "skipped": 0, "total": 0}) == 0

	def test_progress_empty_counts(self):
		assert compute_progress({}) == 0

	def test_progress_all_done(self):
		counts = {"pending": 0, "processing": 0, "indexed": 3, "error": 1, "skipped": 2, "total": 6}
		assert compute_progress(counts) == 1.0

	def test_progress_ignores_extra_keys(self):
		counts = {"indexed": 1, "total": 1, "chunks_written": 500}
		assert compute_progress(counts) == 1.0

	def test_progress_handles_int_strings(self):
		counts = {"indexed": "2", "error": "0", "skipped": "0", "total": "4"}
		assert compute_progress(counts) == 0.5


class TestSliceJobId:
	"""First slice uses the plain job id; the slice counter is required for
	enqueue deduplication on self-chained slices."""

	def test_first_slice_job_id(self):
		assert slice_job_id("ING-00007", 0) == "huf_ingest_ING-00007"

	def test_no_slice_job_id(self):
		assert slice_job_id("ING-00007", None) == "huf_ingest_ING-00007"

	def test_chained_slice_job_id(self):
		assert slice_job_id("ING-00007", 7) == "huf_ingest_ING-00007_7"

	def test_chained_slice_job_id_one(self):
		assert slice_job_id("ING-00007", 1) == "huf_ingest_ING-00007_1"


class TestIdempotencyDecisions:
	"""Contract 'Duplicate / idempotency rules' precedence order (rules 2-4).

	Rule 4 (in-batch checksum duplicate) needs the seen-checksum set and row
	creation, which touch the DB -- decided in materialize() on a bench, not here.
	"""

	def test_no_existing_row_creates(self):
		assert decide_idempotency(None, None, "a" * 64) == "create"

	def test_indexed_same_checksum_skips_unchanged(self):
		assert decide_idempotency("Indexed", "a" * 64, "a" * 64) == "skip_unchanged"

	def test_indexed_different_checksum_resets(self):
		assert decide_idempotency("Indexed", "a" * 64, "b" * 64) == "reset_pending"

	def test_indexed_entry_checksum_missing_resets(self):
		# Without an entry checksum the safe behavior is to re-index.
		assert decide_idempotency("Indexed", "a" * 64, None) == "reset_pending"

	def test_error_resets_to_pending(self):
		assert decide_idempotency("Error", "a" * 64, "a" * 64) == "reset_pending"
		assert decide_idempotency("Error", None, None) == "reset_pending"

	def test_pending_processing_leave_alone(self):
		assert decide_idempotency("Pending", "a" * 64, "a" * 64) == "leave_alone"
		assert decide_idempotency("Processing", "a" * 64, "b" * 64) == "leave_alone"

	def test_skipped_same_checksum_stays_skipped(self):
		# Skipped is treated like Indexed for change detection: same checksum
		# means nothing changed, so the row is not reset.
		assert decide_idempotency("Skipped", "a" * 64, "a" * 64) == "skip_unchanged"

	def test_skipped_different_checksum_resets(self):
		assert decide_idempotency("Skipped", "a" * 64, "b" * 64) == "reset_pending"

	def test_unknown_status_leave_alone(self):
		assert decide_idempotency("SomeFutureStatus", None, None) == "leave_alone"

	def test_checksum_comparison_is_exact(self):
		# 64-hex digests are compared verbatim (lowercased at the API boundary).
		assert decide_idempotency("Indexed", "A" * 64, "a" * 64) == "reset_pending"


class TestRowAdoptionRule:
	"""B1: a ``leave_alone`` row is adopted when unclaimed or when its current
	batch is terminal; never from a live (Queued/Running) batch.

	Without this, a cancelled batch leaves rows with ``ingestion=<cancelled
	header>`` and resubmitting the same external_keys materializes nothing.
	"""

	def test_unclaimed_row_is_adopted(self):
		assert should_adopt_row(None, None) is True

	def test_row_from_cancelled_batch_is_adopted(self):
		assert should_adopt_row("ING-00001", "Cancelled") is True

	def test_row_from_failed_batch_is_adopted(self):
		assert should_adopt_row("ING-00001", "Failed") is True

	def test_row_from_completed_batch_is_adopted(self):
		assert should_adopt_row("ING-00001", "Completed") is True
		assert should_adopt_row("ING-00001", "Completed with Errors") is True

	def test_row_from_live_batch_is_not_adopted(self):
		assert should_adopt_row("ING-00001", "Queued") is False
		assert should_adopt_row("ING-00001", "Running") is False

	def test_unknown_header_status_is_not_adopted(self):
		# Unknown status -> treat as live (conservative: never steal rows).
		assert should_adopt_row("ING-00001", None) is False
		assert should_adopt_row("ING-00001", "SomeFutureStatus") is False
