# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Pure-logic tests for the bulk ingestion contract math.

These run WITHOUT a bench (the repo pytest frappe stub kicks in via
pyproject.toml addopts). Anything that touches the database, Redis, or the
background queue -- bulk_runner.run_ingestion / materialize /
recover_stalled_ingestions, bulk_api.submit_files, and the DocType
controllers -- needs a live bench and is deliberately not covered here.
"""

import json

import pytest

from huf.ai.knowledge.bulk_runner import (
	compute_progress,
	decide_idempotency,
	load_manifest,
	needs_materialization,
	serialize_manifest,
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


class TestManifestPersistence:
	"""M1: the accepted manifest is persisted on the header at submit and the
	runner materializes whenever counts.total < total_items, so an interrupted
	first slice is recoverable without the enqueue args."""

	def test_explicit_entries_win_over_stored(self):
		entries = [{"external_key": "a"}]
		assert load_manifest(entries, '[{"external_key": "b"}]') is entries

	def test_stored_manifest_used_when_entries_none(self):
		manifest = [{"external_key": "a", "checksum": "a" * 64}]
		assert load_manifest(None, json.dumps(manifest)) == manifest

	def test_no_manifest_returns_none(self):
		assert load_manifest(None, None) is None
		assert load_manifest(None, "") is None

	def test_corrupt_stored_manifest_returns_none(self):
		assert load_manifest(None, "{not json") is None

	def test_non_list_stored_manifest_returns_none(self):
		assert load_manifest(None, '{"external_key": "a"}') is None

	def test_materialization_needed_when_short(self):
		assert needs_materialization(0, 5) is True
		assert needs_materialization(3, 5) is True

	def test_no_materialization_when_complete(self):
		assert needs_materialization(5, 5) is False
		# Over-materialized (should not happen) is also fine.
		assert needs_materialization(6, 5) is False

	def test_zero_declared_needs_no_materialization(self):
		assert needs_materialization(0, 0) is False

	def test_serialize_manifest_roundtrip(self):
		entries = [{"external_key": "a", "checksum": None, "file": "FILE-1", "file_url": "/files/a.pdf"}]
		assert json.loads(serialize_manifest(entries)) == entries

	def test_serialize_manifest_empty_is_json_list(self):
		assert json.loads(serialize_manifest([])) == []

	def test_serialize_manifest_capped(self):
		assert serialize_manifest([{"external_key": "a"}], max_bytes=4) is None

	def test_serialize_manifest_unserializable_is_none(self):
		assert serialize_manifest([{"external_key": object()}]) is None


class TestFinalizationGuard:
	"""M3: never finalize while Processing rows are stranded."""

	def test_finalizes_with_zero_processing(self):
		assert should_finalize({"pending": 0, "processing": 0, "indexed": 5}) is True

	def test_finalizes_all_terminal(self):
		assert should_finalize({"indexed": 3, "error": 1, "skipped": 1}) is True

	def test_never_finalizes_while_processing(self):
		assert should_finalize({"pending": 0, "processing": 1, "indexed": 5}) is False

	def test_processing_none_defaults_to_zero(self):
		assert should_finalize({}) is True


class _Deadlock(Exception):
	pass


class _Boom(Exception):
	pass


@pytest.fixture
def hdr():
	from unittest.mock import MagicMock, patch

	import huf.ai.knowledge.bulk_api as mod

	fake = MagicMock()
	fake.QueryDeadlockError = _Deadlock
	fake.throw.side_effect = lambda msg: (_ for _ in ()).throw(_Boom(str(msg)))
	fake.db.exists.return_value = None
	with patch.object(mod, "frappe", fake), patch.object(mod, "_", lambda m: m), patch.object(
		mod.time, "sleep"
	) as sleep:
		yield mod, fake, sleep


class TestHeaderSeriesRetry:
	def test_one_deadlock_then_success(self, hdr):
		mod, fake, sleep = hdr
		doc = fake.get_doc.return_value
		doc.insert.side_effect = [_Deadlock(), doc]
		assert mod.create_ingestion_header("KS-1") is doc
		assert doc.insert.call_count == 2
		fake.db.rollback.assert_called_once()
		sleep.assert_called_once()
		assert 0.05 <= sleep.call_args.args[0] <= 0.4

	def test_persistent_deadlock_raises_clear_error(self, hdr):
		mod, fake, sleep = hdr
		fake.get_doc.return_value.insert.side_effect = _Deadlock()
		with pytest.raises(_Boom, match="Another import is starting right now"):
			mod.create_ingestion_header("KS-1")
		assert fake.get_doc.return_value.insert.call_count == 5
		assert fake.db.rollback.call_count == 5
		assert sleep.call_count == 4

	def test_duplicate_check_runs_each_attempt(self, hdr):
		mod, fake, _ = hdr
		doc = fake.get_doc.return_value
		doc.insert.side_effect = [_Deadlock(), _Deadlock(), doc]
		mod.create_ingestion_header("KS-1")
		assert fake.db.exists.call_count == 3

	def test_active_ingestion_after_rollback_blocks_insert(self, hdr):
		mod, fake, _ = hdr
		doc = fake.get_doc.return_value
		doc.insert.side_effect = _Deadlock()
		fake.db.exists.side_effect = [None, "ING-7"]
		with pytest.raises(_Boom, match="already queued"):
			mod.create_ingestion_header("KS-1")
		assert doc.insert.call_count == 1
