# RECONSTRUCTED / SYNTHETIC FIXTURE -- not a recovered original.
#
# The original benchmark-4-reconciliation/invariants.py referenced by huf/ai/tests/
# test_procedure_runtime_benchmark4.py is not present anywhere on this machine. This file
# was built from scratch by reading that test file's exact usage contract (it loads this
# module via importlib.util.spec_from_file_location and iterates ``ALL_INVARIANTS``,
# special-casing four named functions by identity and calling every other member as
# ``fn(result)``) and by independently deriving the expected numbers (total_outstanding,
# classification counts) from the test's own seed data and its ``classify_payment``
# candidate-matching logic, rather than copying them from the test.
#
# Contract this module must satisfy (from test_procedure_runtime_benchmark4.py):
#   - module-level ``ALL_INVARIANTS``: an iterable of callables.
#   - ``assert_total_outstanding_preserved(result, expected_total=...)``
#   - ``assert_customer_ids_preserved(result, valid_customer_ids=...)``
#   - ``assert_no_unauthorized_records(result, excluded_ids=...)``
#   - ``assert_classification_counts(result, expected_resolved=, expected_ambiguous=,
#     expected_unmatched=)``
#   - any other member of ALL_INVARIANTS is called as ``fn(result)``.
#
# ``result`` is the procedure's ``out`` node value:
#   {"company", "currency", "total_outstanding", "resolved": [...], "ambiguous": [...],
#    "unmatched": [...]}
# where each row has at least {"payment", "customer", "amount", "classification"}, plus
# "matched_invoice" (resolved) or "candidates" (ambiguous).

from __future__ import annotations


def _all_rows(result: dict):
	for bucket in ("resolved", "ambiguous", "unmatched"):
		for row in result.get(bucket, []):
			yield row


def _walk_strings(value):
	"""Yield every string found anywhere inside a (possibly nested) JSON-ish value."""
	if isinstance(value, str):
		yield value
	elif isinstance(value, dict):
		for v in value.values():
			yield from _walk_strings(v)
	elif isinstance(value, (list, tuple, set)):
		for v in value:
			yield from _walk_strings(v)


def assert_total_outstanding_preserved(result: dict, expected_total: float) -> None:
	"""The run's reported ``total_outstanding`` matches the independently-computed sum of
	in-scope invoices -- not merely echoed from whatever the runtime happened to compute.
	"""
	actual = result.get("total_outstanding")
	assert actual is not None, "result is missing total_outstanding"
	assert abs(float(actual) - float(expected_total)) < 0.01, (
		f"total_outstanding {actual} does not match expected {expected_total}"
	)


def assert_customer_ids_preserved(result: dict, valid_customer_ids: set) -> None:
	"""Every customer id appearing in any classified row is one of the run's own
	in-scope customers -- nothing from an out-of-scope company leaked through classification.
	"""
	actual = {row["customer"] for row in _all_rows(result)}
	unexpected = actual - set(valid_customer_ids)
	assert not unexpected, f"unexpected customer ids in classified rows: {unexpected}"


def assert_no_unauthorized_records(result: dict, excluded_ids: set) -> None:
	"""None of the given ids (customers, payments, or invoices scoped out by the run's
	company filter) appear anywhere in the output, at any nesting level.
	"""
	found = set()
	for row in _all_rows(result):
		for s in _walk_strings(row):
			if s in excluded_ids:
				found.add(s)
	assert not found, f"excluded ids leaked into the output: {found}"


def assert_classification_counts(
	result: dict, expected_resolved: int, expected_ambiguous: int, expected_unmatched: int
) -> None:
	"""The three classification buckets have exactly the expected sizes -- a coarse but
	direct check that the candidate-matching algorithm classified every in-scope payment
	correctly, not just that the buckets are non-empty.
	"""
	assert len(result.get("resolved", [])) == expected_resolved, (
		f"resolved count {len(result.get('resolved', []))} != expected {expected_resolved}"
	)
	assert len(result.get("ambiguous", [])) == expected_ambiguous, (
		f"ambiguous count {len(result.get('ambiguous', []))} != expected {expected_ambiguous}"
	)
	assert len(result.get("unmatched", [])) == expected_unmatched, (
		f"unmatched count {len(result.get('unmatched', []))} != expected {expected_unmatched}"
	)


def assert_no_duplicate_allocation(result: dict) -> None:
	"""No single invoice is claimed as the ``matched_invoice`` of more than one resolved
	payment, and no invoice appears in more than one resolved/ambiguous combination as a
	single-invoice match -- the reconciliation-specific analogue of "never double-book the
	same invoice against two different payments."
	"""
	claimed: dict = {}
	for row in result.get("resolved", []):
		invoice = row.get("matched_invoice")
		if invoice is None:
			continue
		assert invoice not in claimed, (
			f"invoice {invoice} claimed by both {claimed[invoice]} and {row['payment']}"
		)
		claimed[invoice] = row["payment"]


ALL_INVARIANTS = [
	assert_total_outstanding_preserved,
	assert_customer_ids_preserved,
	assert_no_unauthorized_records,
	assert_classification_counts,
	assert_no_duplicate_allocation,
]
