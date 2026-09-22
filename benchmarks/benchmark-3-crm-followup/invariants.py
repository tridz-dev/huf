# RECONSTRUCTED / SYNTHETIC FIXTURE -- not a recovered original.
#
# The original benchmark-3-crm-followup/invariants.py referenced by huf/ai/tests/
# test_benchmark3_write_runtime.py and by huf/ai/graph/idempotency.py's docstring is not
# present anywhere on this machine. This file was built from scratch by reading that test
# file's exact import/usage contract (importlib.util.spec_from_file_location loads this
# module and the test calls ``ALL_INVARIANTS`` plus a handful of named functions directly)
# and reverse-engineering the required behaviour from the assertions the test makes against
# ``result`` (the procedure's ``output``) and ``store.rows`` (the fake ToDo store's rows).
#
# Contract this module must satisfy (from test_benchmark3_write_runtime.py):
#   - module-level ``ALL_INVARIANTS``: an iterable of callables. The test special-cases two
#     of them (``assert_customer_ids_preserved``, ``assert_no_unauthorized_records``) to be
#     called as ``fn(result, <set>)``; every other member of the list is called as
#     ``fn(result)``.
#   - ``assert_customer_ids_preserved(result, expected_customer_ids)``
#   - ``assert_no_unauthorized_records(result, unauthorized_customer_ids)``
#   - ``assert_no_duplicate_todos(rows)`` -- called directly on ``store.rows``.
#   - ``assert_idempotent_across_runs(rows_before, rows_after)`` -- called directly with two
#     snapshots of ``store.rows`` taken before/after a replay.
#   - ``assert_run_status_reflects_rows(result)`` -- called directly.
#
# ``result`` is the compute_summary tool's output: {"company", "status", "rows": [...]}
# where each row is {"customer_id", "invoice", "outcome"} and outcome is one of
# "created" | "already_existed" | "failed" | "skipped_not_qualified".

from __future__ import annotations


def _iter_customer_ids(result: dict):
	for row in result.get("rows", []):
		customer_id = row.get("customer_id")
		if customer_id is not None:
			yield customer_id


def assert_customer_ids_preserved(result: dict, expected_customer_ids: set) -> None:
	"""Every customer id the run touched is exactly the set expected -- no customer
	silently dropped from the output and no customer that was not part of the selection
	sneaking a row in.
	"""
	actual = set(_iter_customer_ids(result))
	assert actual == set(expected_customer_ids), (
		f"customer ids in output {actual} do not match expected selection {set(expected_customer_ids)}"
	)


def assert_no_unauthorized_records(result: dict, unauthorized_customer_ids: set) -> None:
	"""None of the given customer ids -- customers that were never part of the run's own
	``selected_customers`` input -- appear anywhere in the output rows.
	"""
	actual = set(_iter_customer_ids(result))
	overlap = actual & set(unauthorized_customer_ids)
	assert not overlap, f"unauthorized customer ids leaked into output: {overlap}"


def assert_no_duplicate_todos(rows: list) -> None:
	"""The fake ToDo store never holds two rows for the same (reference_type,
	reference_name, allocated_to) -- the real-world uniqueness constraint a genuine
	"insert-if-not-exists" ERPNext ToDo write must also honour.
	"""
	seen = set()
	for row in rows:
		key = (row["reference_type"], row["reference_name"], row["allocated_to"])
		assert key not in seen, f"duplicate ToDo for {key}"
		seen.add(key)


def assert_idempotent_across_runs(rows_before: list, rows_after: list) -> None:
	"""A replay (checkpoint-resume, or a fully redundant re-invocation) never loses or
	mutates a row that already existed -- it may only ever add new rows for genuinely new
	work.
	"""
	before_by_name = {row["name"]: row for row in rows_before}
	after_by_name = {row["name"]: row for row in rows_after}
	missing = set(before_by_name) - set(after_by_name)
	assert not missing, f"rows present before the replay went missing after it: {missing}"
	for name, row in before_by_name.items():
		assert after_by_name[name] == row, f"row {name} was mutated by a replay: {row} -> {after_by_name[name]}"
	assert len(after_by_name) >= len(before_by_name), "replay must never reduce the number of distinct ToDos"


def assert_run_status_reflects_rows(result: dict) -> None:
	"""The run's top-level ``status`` is an honest aggregate of its own ``rows`` --
	mirrors (independently) the aggregation rule compute_summary itself must apply, so this
	invariant would catch a compute_summary regression rather than merely echoing it.
	"""
	rows = result.get("rows", [])
	outcomes = [row["outcome"] for row in rows if row["outcome"] != "skipped_not_qualified"]
	if not outcomes:
		expected = "success"
	elif all(o in ("created", "already_existed") for o in outcomes):
		expected = "success"
	elif all(o == "failed" for o in outcomes):
		expected = "failure"
	else:
		expected = "partial_success"
	assert result.get("status") == expected, (
		f"result status {result.get('status')!r} does not reflect its own rows (expected {expected!r})"
	)


ALL_INVARIANTS = [
	assert_customer_ids_preserved,
	assert_no_unauthorized_records,
	assert_run_status_reflects_rows,
]
