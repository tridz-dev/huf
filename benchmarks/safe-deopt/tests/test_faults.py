# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for benchmarks/safe-deopt/faults.py (Track-Item: 4).

Pure pytest -- no frappe, no bench. Mirrors the sys.path setup in test_workloads.py so
``workloads``, ``invariants_safedeopt`` and ``faults`` import as plain top-level modules.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from faults import (  # noqa: E402
	FAULT_IDS,
	GUARANTEE_LEVELS,
	FaultInjector,
	TimeoutFault,
	ValidationErrorFault,
	cancel_operation,
	demonstrate_server_idempotent_retry,
	get_operation_status,
)
from workloads import (  # noqa: E402
	CrmStore,
	Customer,
	Invoice,
	OpenItem,
	Payment,
	PaymentAllocationStore,
)


def _make_crm_store() -> CrmStore:
	store = CrmStore()
	store.seed_customer(Customer(customer_id="CUST-0001", name="Acme Retail", company="Huf Retail Pvt Ltd"))
	store.seed_open_item(
		OpenItem(reference_type="Sales Invoice", reference_name="SINV-2001", customer_id="CUST-0001", outstanding_amount=5000.0)
	)
	return store


def _make_payment_store() -> PaymentAllocationStore:
	store = PaymentAllocationStore()
	store.seed_invoice(Invoice(name="SINV-4001", customer="CUST-0001", outstanding_amount=5000.0))
	store.seed_payment(Payment(name="PE-4001", customer="CUST-0001", amount=5000.0))
	return store


def _prep_submitted_allocation(store: PaymentAllocationStore, *, op_key_a="a-key", allocation_amount=5000.0):
	alloc = store.create_allocation(payment="PE-4001", invoice="SINV-4001", amount=allocation_amount, operation_key=op_key_a)
	return alloc


# ---------------------------------------------------------------------------
# F0 - control
# ---------------------------------------------------------------------------


class F0ControlTests(unittest.TestCase):
	def test_real_write_happens_caller_told_success(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F0", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)

		self.assertTrue(observed.ok)
		self.assertEqual(observed.value.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)


# ---------------------------------------------------------------------------
# F1 - clean rejection before dispatch
# ---------------------------------------------------------------------------


class F1RejectionTests(unittest.TestCase):
	def test_no_real_write_caller_told_error(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F1", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)

		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, RuntimeError)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)
		self.assertEqual(alloc.status, "draft")


# ---------------------------------------------------------------------------
# F2 vs F3 indistinguishability
# ---------------------------------------------------------------------------


class F2F3IndistinguishableTests(unittest.TestCase):
	def test_f2_commits_but_reports_timeout(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F2", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)

		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, TimeoutFault)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)
		self.assertEqual(alloc.status, "submitted")

	def test_f3_does_not_commit_but_reports_identical_timeout(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F3", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)

		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, TimeoutFault)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)
		self.assertEqual(alloc.status, "draft")

	def test_f2_and_f3_caller_visible_errors_are_identical_shape(self):
		store_a = _make_payment_store()
		alloc_a = _prep_submitted_allocation(store_a)
		store_b = _make_payment_store()
		alloc_b = _prep_submitted_allocation(store_b)
		injector = FaultInjector()

		obs_f2 = injector.inject("F2", "none", store_a.submit_allocation, allocation=alloc_a.name, operation_key="submit-key-1")
		obs_f3 = injector.inject("F3", "none", store_b.submit_allocation, allocation=alloc_b.name, operation_key="submit-key-1")

		self.assertEqual(type(obs_f2.error), type(obs_f3.error))
		self.assertEqual(str(obs_f2.error), str(obs_f3.error))
		self.assertEqual(obs_f2.ok, obs_f3.ok)
		self.assertEqual(obs_f2.value, obs_f3.value)


# ---------------------------------------------------------------------------
# F4 - concurrent actor drift
# ---------------------------------------------------------------------------


class F4DriftTests(unittest.TestCase):
	def test_concurrent_mutation_then_validation_error_surfaced(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		def drift():
			# Simulate a concurrent actor submitting it first out from under us.
			store.submit_allocation(allocation=alloc.name, operation_key="concurrent-actor-key")

		observed = injector.inject(
			"F4",
			"none",
			store.submit_allocation,
			allocation=alloc.name,
			operation_key="submit-key-1",
			concurrent_mutation=drift,
		)

		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, ValidationErrorFault)


# ---------------------------------------------------------------------------
# F5 - lost result
# ---------------------------------------------------------------------------


class F5LostResultTests(unittest.TestCase):
	def test_real_write_commits_but_caller_gets_empty_payload(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F5", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)

		self.assertTrue(observed.ok)
		self.assertIsNone(observed.value)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)
		self.assertEqual(alloc.status, "submitted")


# ---------------------------------------------------------------------------
# F6 - inconclusive verification
# ---------------------------------------------------------------------------


class F6InconclusiveReadTests(unittest.TestCase):
	def test_ambiguous_reads_then_clears(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F6",
			"none",
			store.submit_allocation,
			allocation=alloc.name,
			operation_key="submit-key-1",
			ambiguous_read_count=2,
		)
		self.assertIsInstance(observed.error, TimeoutFault)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

		read1 = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		read2 = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(read1, "PROCESSING")
		self.assertEqual(read2, "PROCESSING")

		read3 = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(read3, "submitted")


# ---------------------------------------------------------------------------
# F7 - late commit
# ---------------------------------------------------------------------------


class F7LateCommitTests(unittest.TestCase):
	def test_first_read_sees_pre_write_state_then_write_lands(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		observed = injector.inject(
			"F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)
		self.assertIsInstance(observed.error, TimeoutFault)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)
		self.assertEqual(alloc.status, "draft")

		first_read = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(first_read, "draft")

		committed_after_first_read = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed_after_first_read), 1)
		self.assertEqual(alloc.status, "submitted")

		second_read = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(second_read, "submitted")

	def test_cancel_before_first_read_prevents_late_commit(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()

		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1")

		cancelled = cancel_operation(store, "submit-key-1", injector=injector)
		self.assertTrue(cancelled)

		read = injector.wrap_read("submit-key-1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(read, "draft")

		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)
		self.assertEqual(alloc.status, "draft")


# ---------------------------------------------------------------------------
# server_idempotent guarantee demonstration
# ---------------------------------------------------------------------------


class ServerIdempotentGuaranteeTests(unittest.TestCase):
	def test_retry_with_same_operation_key_is_safe_no_op(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)

		first, second = demonstrate_server_idempotent_retry(
			store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1"
		)
		self.assertEqual(first.status, "submitted")
		self.assertEqual(second.status, "submitted")

		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)


# ---------------------------------------------------------------------------
# get_operation_status
# ---------------------------------------------------------------------------


class GetOperationStatusTests(unittest.TestCase):
	def test_committed_after_real_write(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		store.submit_allocation(allocation=alloc.name, operation_key="submit-key-1")

		status = get_operation_status(store, "submit-key-1")
		self.assertEqual(status, "COMMITTED")

	def test_not_committed_when_nothing_happened(self):
		store = _make_payment_store()
		status = get_operation_status(store, "never-attempted")
		self.assertEqual(status, "NOT_COMMITTED")

	def test_unknown_during_f7_hold_window(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()
		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="submit-key-1")

		status = get_operation_status(store, "submit-key-1", injector=injector)
		self.assertEqual(status, "UNKNOWN")

		injector.flush_held_write("submit-key-1")
		status_after = get_operation_status(store, "submit-key-1", injector=injector)
		self.assertEqual(status_after, "COMMITTED")


# ---------------------------------------------------------------------------
# Cross F2/F3/F6/F7 x all 4 guarantee levels (16 combinations)
# ---------------------------------------------------------------------------


class CrossFaultGuaranteeMatrixTests(unittest.TestCase):
	"""One test per (fault, guarantee_level) combination among F2/F3/F6/F7 x the 4 levels.

	Checks: (a) caller-visible result matches the fault's spec, (b) ground-truth commit_log
	matches the fault's spec, (c) the guarantee mechanism resolves correctly when exercised.
	"""

	def _new(self):
		store = _make_payment_store()
		alloc = _prep_submitted_allocation(store)
		injector = FaultInjector()
		return store, alloc, injector

	def _assert_caller_told_timeout(self, observed):
		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, TimeoutFault)

	# -- F2 (commits) x each guarantee level --------------------------------

	def test_f2_server_idempotent(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F2", "server_idempotent", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(alloc.status, "submitted")
		# guarantee mechanism: retrying with the same key is a safe no-op (already committed)
		retried = store.submit_allocation(allocation=alloc.name, operation_key="k1")
		self.assertEqual(retried.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

	def test_f2_status_resolvable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F2", "status_resolvable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(get_operation_status(store, "k1", injector=injector), "COMMITTED")

	def test_f2_fenceable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F2", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		# already committed synchronously -- cancel is a no-op / returns False, write stands
		cancelled = cancel_operation(store, "k1", injector=injector)
		self.assertFalse(cancelled)
		self.assertEqual(alloc.status, "submitted")

	def test_f2_none(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F2", "none", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(alloc.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

	# -- F3 (does not commit) x each guarantee level -------------------------

	def test_f3_server_idempotent(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F3", "server_idempotent", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(alloc.status, "draft")
		# guarantee mechanism: retry with same key now actually performs the write, safely
		retried = store.submit_allocation(allocation=alloc.name, operation_key="k1")
		self.assertEqual(retried.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

	def test_f3_status_resolvable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F3", "status_resolvable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(get_operation_status(store, "k1", injector=injector), "NOT_COMMITTED")

	def test_f3_fenceable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F3", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		# nothing was held (write never happened / never dispatched), cancel finds nothing
		cancelled = cancel_operation(store, "k1", injector=injector)
		self.assertFalse(cancelled)
		self.assertEqual(alloc.status, "draft")

	def test_f3_none(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F3", "none", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(alloc.status, "draft")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)

	# -- F6 (timeout + inconclusive reads) x each guarantee level ------------

	def test_f6_server_idempotent(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F6", "server_idempotent", store.submit_allocation, allocation=alloc.name, operation_key="k1", ambiguous_read_count=1)
		self._assert_caller_told_timeout(observed)
		ambiguous = injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(ambiguous, "PROCESSING")
		# guarantee mechanism: retry with same key is safe even though verification was ambiguous
		retried = store.submit_allocation(allocation=alloc.name, operation_key="k1")
		self.assertEqual(retried.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

	def test_f6_status_resolvable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F6", "status_resolvable", store.submit_allocation, allocation=alloc.name, operation_key="k1", ambiguous_read_count=1)
		self._assert_caller_told_timeout(observed)
		ambiguous = injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(ambiguous, "PROCESSING")
		# status_resolvable bypasses the ambiguous read entirely -- ground truth already knows
		self.assertEqual(get_operation_status(store, "k1", injector=injector), "COMMITTED")

	def test_f6_fenceable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F6", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="k1", ambiguous_read_count=1)
		self._assert_caller_told_timeout(observed)
		cancelled = cancel_operation(store, "k1", injector=injector)
		self.assertFalse(cancelled)  # already committed synchronously, nothing to fence
		self.assertEqual(alloc.status, "submitted")

	def test_f6_none(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F6", "none", store.submit_allocation, allocation=alloc.name, operation_key="k1", ambiguous_read_count=1)
		self._assert_caller_told_timeout(observed)
		ambiguous = injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(ambiguous, "PROCESSING")
		resolved = injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(resolved, "submitted")

	# -- F7 (late commit) x each guarantee level ------------------------------

	def test_f7_server_idempotent(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F7", "server_idempotent", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(alloc.status, "draft")
		# an ungated retry BEFORE the first read would be a second real call; since write B is
		# idempotent by operation_key, retrying with the SAME key is still safe even though
		# the original is held -- it becomes a duplicate_operation_key no-op once resolved.
		# We first let the hold clear naturally via a read, then retry.
		injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		retried = store.submit_allocation(allocation=alloc.name, operation_key="k1")
		self.assertEqual(retried.status, "submitted")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)

	def test_f7_status_resolvable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F7", "status_resolvable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		self.assertEqual(get_operation_status(store, "k1", injector=injector), "UNKNOWN")
		injector.flush_held_write("k1")
		self.assertEqual(get_operation_status(store, "k1", injector=injector), "COMMITTED")

	def test_f7_fenceable(self):
		store, alloc, injector = self._new()
		observed = injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="k1")
		self._assert_caller_told_timeout(observed)
		cancelled = cancel_operation(store, "k1", injector=injector)
		self.assertTrue(cancelled)
		# the held write must never land, even after what would have been its trigger
		injector.wrap_read("k1", lambda: store.allocations[alloc.name].status)
		self.assertEqual(alloc.status, "draft")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 0)

	def test_f7_none_ungated_retry_produces_duplicate_on_unsafe_write(self):
		store = _make_payment_store()
		injector = FaultInjector()
		# Use the NON-idempotent write B variant to prove an ungated retry after F7/none
		# (no tooling at all) can produce a real duplicate.
		held = injector.inject(
			"F7", "none", store.submit_allocation_unsafe, payment="PE-4001", invoice="SINV-4001", amount=5000.0, operation_key="k1"
		)
		self._assert_caller_told_timeout(held)
		committed_before = [e for e in store.commit_log if e.action == "submit_allocation_unsafe" and e.committed]
		self.assertEqual(len(committed_before), 0)

		# Caller has "none" guarantee: nothing to consult, so it blindly retries immediately.
		store.submit_allocation_unsafe(payment="PE-4001", invoice="SINV-4001", amount=5000.0)

		# Now the held write from F7 lands too, once a read happens.
		injector.wrap_read("k1", lambda: store.allocations)

		committed_after = [e for e in store.commit_log if e.action == "submit_allocation_unsafe" and e.committed]
		self.assertEqual(len(committed_after), 2, "ungated retry against the unsafe write plus the late F7 commit produced a real duplicate")


if __name__ == "__main__":
	unittest.main()
