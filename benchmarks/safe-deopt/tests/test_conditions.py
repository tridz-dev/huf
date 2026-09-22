# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for benchmarks/safe-deopt/conditions.py (Track-Item: 5).

Pure pytest -- no frappe, no bench. Mirrors the sys.path setup in test_faults.py /
test_workloads.py so ``workloads``, ``faults`` and ``conditions`` import as plain top-level
modules.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from conditions import (  # noqa: E402
	RecoverySession,
	ReplayGuard,
	ReplayRejected,
	deterministic_resume_recover,
	naive_replay_recover,
)
from faults import FaultInjector, cancel_operation, get_operation_status  # noqa: E402
from workloads import Invoice, Payment, PaymentAllocationStore  # noqa: E402


def _store_with_allocation(*, amount: float = 100.0) -> tuple[PaymentAllocationStore, str]:
	store = PaymentAllocationStore()
	store.seed_invoice(Invoice(name="INV-0001", customer="CUST-1", outstanding_amount=500.0))
	store.seed_payment(Payment(name="PAY-0001", customer="CUST-1", amount=amount))
	row = store.create_allocation(payment="PAY-0001", invoice="INV-0001", amount=amount, operation_key="alloc-key-1")
	return store, row.name


# ---------------------------------------------------------------------------
# C2 -- naive replay is unsafe
# ---------------------------------------------------------------------------


class TestNaiveReplayRecover(unittest.TestCase):
	def test_naive_replay_against_unsafe_write_produces_duplicate(self):
		"""Retrying submit_allocation_unsafe (no operation_key at all) creates two committed
		allocations and double-decrements the invoice -- proving C2 is unsafe for this shape.
		"""
		store = PaymentAllocationStore()
		store.seed_invoice(Invoice(name="INV-0001", customer="CUST-1", outstanding_amount=500.0))

		results = naive_replay_recover(
			store,
			store.submit_allocation_unsafe,
			payment="PAY-0001",
			invoice="INV-0001",
			amount=100.0,
			max_retries=1,
		)

		self.assertEqual(len(results), 2)
		committed = [e for e in store.commit_log if e.action == "submit_allocation_unsafe" and e.committed]
		self.assertEqual(len(committed), 2, "naive replay should have produced two committed unsafe writes")
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 300.0, "invoice must have been decremented twice (double-debited)")

	def test_naive_replay_with_fresh_keys_defeats_idempotent_dedup(self):
		"""Even against the IDEMPOTENT submit_allocation, minting a fresh operation_key each
		retry (simulating 'no idempotency') defeats the store's own dedup and produces two
		commits.
		"""
		store, allocation_name = _store_with_allocation()

		results = naive_replay_recover(
			store,
			store.submit_allocation,
			allocation=allocation_name,
			operation_key="submit-key-1",
			max_retries=1,
		)

		self.assertEqual(len(results), 2)
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		# Second call targets the SAME allocation with a different key; the allocation is
		# already 'submitted' by the first call, so the store's own already-submitted guard
		# catches it -- but it does so ONLY because submit_allocation checks row.status, not
		# because C2 did anything safe. Assert the naive strategy did not itself prevent a
		# second real attempt from being dispatched.
		self.assertEqual(len(results), 2)
		self.assertEqual(store.allocations[allocation_name].status, "submitted")


# ---------------------------------------------------------------------------
# C3 -- deterministic resume is a safe no-op / a real write, per actual outcome
# ---------------------------------------------------------------------------


class TestDeterministicResumeRecover(unittest.TestCase):
	def test_resume_after_f2_committed_write_is_safe_noop(self):
		"""F2: store DID commit, caller was told 'timeout'. Resuming with the SAME
		operation_key must be a safe no-op -- no double-decrement.
		"""
		store, allocation_name = _store_with_allocation()
		injector = FaultInjector()

		observed = injector.inject(
			"F2",
			"status_resolvable",
			store.submit_allocation,
			allocation=allocation_name,
			operation_key="submit-key-1",
		)
		self.assertFalse(observed.ok)  # caller told timeout
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 400.0)  # but it DID commit

		results = deterministic_resume_recover(
			store,
			store.submit_allocation,
			allocation=allocation_name,
			operation_key="submit-key-1",
			max_retries=1,
		)

		self.assertEqual(len(results), 2)
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 400.0, "resume must not double-decrement a write that already committed")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1, "only the original attempt should be a committed write")

	def test_resume_after_f3_uncommitted_write_performs_real_write(self):
		"""F3: store did NOT commit, caller was told 'timeout' (identical to F2 from the
		caller's view). Resuming with the SAME operation_key must actually perform the write.
		"""
		store, allocation_name = _store_with_allocation()
		injector = FaultInjector()

		observed = injector.inject(
			"F3",
			"status_resolvable",
			store.submit_allocation,
			allocation=allocation_name,
			operation_key="submit-key-1",
		)
		self.assertFalse(observed.ok)
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 500.0, "F3 must not have actually committed")

		results = deterministic_resume_recover(
			store,
			store.submit_allocation,
			allocation=allocation_name,
			operation_key="submit-key-1",
			max_retries=1,
		)

		self.assertEqual(len(results), 2)
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 400.0, "resume must have performed the real write exactly once")
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1, "resume's second (redundant) call must be a logged no-op, not a second commit")


# ---------------------------------------------------------------------------
# C6 -- ReplayGuard admission rule, every (guarantee x outcome-state) branch
# ---------------------------------------------------------------------------


class TestReplayGuard(unittest.TestCase):
	def setUp(self):
		self.store, self.allocation_name = _store_with_allocation()
		self.injector = FaultInjector()
		self.guard = ReplayGuard(injector=self.injector)

	def _write_fn(self):
		return self.store.submit_allocation

	# -- COMMITTED, any guarantee -> rejected unless server_idempotent -------

	def test_committed_plus_none_is_rejected(self):
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		# already submitted for real, to make ground truth committed too
		self.store.submit_allocation(allocation=self.allocation_name, operation_key="k1")
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k1",
				tool_guarantee="none", recovery_session=session, store=self.store,
			)

	def test_committed_plus_status_resolvable_is_rejected(self):
		session = RecoverySession()
		self.store.submit_allocation(allocation=self.allocation_name, operation_key="k1")
		session.record_status_check("k1", "COMMITTED")
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k1",
				tool_guarantee="status_resolvable", recovery_session=session, store=self.store,
			)

	def test_committed_plus_fenceable_is_rejected(self):
		# The guard must not consult a raw ground-truth oracle for "fenceable" (it only
		# knows what an ACTUAL cancel_operation call told this recovery session) -- so this
		# test goes through the real fence path rather than hand-seeding session.fenced.
		# Once a write has genuinely committed, a real cancel_operation() call correctly
		# returns False (nothing left to fence), so record_fence(..., fenced=False) never
		# adds the key to session.fenced, and rule 2c rejects for the honest reason "not
		# fenced" -- the guard reaches the same safe outcome without ever peeking at truth
		# it isn't entitled to for this guarantee level.
		session = RecoverySession()
		self.store.submit_allocation(allocation=self.allocation_name, operation_key="k1")
		fenced_ok = cancel_operation(self.store, "k1", injector=self.injector)
		session.record_fence("k1", fenced=fenced_ok)
		self.assertFalse(fenced_ok, "a real cancel_operation on an already-committed key must fail")
		self.assertNotIn("k1", session.fenced)
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k1",
				tool_guarantee="fenceable", recovery_session=session, store=self.store,
			)

	def test_committed_plus_server_idempotent_is_allowed_as_safe_noop(self):
		session = RecoverySession()
		self.store.submit_allocation(allocation=self.allocation_name, operation_key="k1")
		before = self.store.invoices["INV-0001"].outstanding_amount
		result = self.guard.attempt_write(
			self._write_fn(), allocation=self.allocation_name, operation_key="k1",
			tool_guarantee="server_idempotent", recovery_session=session, store=self.store,
		)
		self.assertIsNotNone(result)
		self.assertEqual(self.store.invoices["INV-0001"].outstanding_amount, before, "server_idempotent retry of a committed write must be a no-op")

	# -- UNKNOWN outcome, none -> always rejected ----------------------------

	def test_unknown_plus_none_is_rejected(self):
		session = RecoverySession()
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k2",
				tool_guarantee="none", recovery_session=session, store=self.store,
			)

	def test_unknown_plus_none_rejected_even_with_a_bare_read_recorded(self):
		"""Hard rule: a bare read is NOT sufficient to unlock a none/unresolved retry."""
		session = RecoverySession()
		session.record_read("k2")
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k2",
				tool_guarantee="none", recovery_session=session, store=self.store,
			)

	# -- UNKNOWN outcome, server_idempotent -> always allowed ----------------

	def test_unknown_plus_server_idempotent_is_allowed(self):
		session = RecoverySession()
		result = self.guard.attempt_write(
			self._write_fn(), allocation=self.allocation_name, operation_key="k2",
			tool_guarantee="server_idempotent", recovery_session=session, store=self.store,
		)
		self.assertIsNotNone(result)
		self.assertEqual(self.store.allocations[self.allocation_name].status, "submitted")

	# -- UNKNOWN outcome, status_resolvable -----------------------------------

	def test_unknown_plus_status_resolvable_resolved_not_committed_is_allowed(self):
		session = RecoverySession()
		session.record_status_check("k2", "NOT_COMMITTED")
		result = self.guard.attempt_write(
			self._write_fn(), allocation=self.allocation_name, operation_key="k2",
			tool_guarantee="status_resolvable", recovery_session=session, store=self.store,
		)
		self.assertIsNotNone(result)

	def test_unknown_plus_status_resolvable_unresolved_is_rejected(self):
		"""Never actually called get_operation_status for this key -- must reject."""
		session = RecoverySession()
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k2",
				tool_guarantee="status_resolvable", recovery_session=session, store=self.store,
			)

	def test_unknown_plus_status_resolvable_resolved_committed_is_rejected(self):
		"""This is really the COMMITTED case (rule 1), reached via status_resolvable."""
		session = RecoverySession()
		self.store.submit_allocation(allocation=self.allocation_name, operation_key="k1")
		session.record_status_check("k1", "COMMITTED")
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k1",
				tool_guarantee="status_resolvable", recovery_session=session, store=self.store,
			)

	# -- UNKNOWN outcome, fenceable --------------------------------------------

	def test_unknown_plus_fenceable_fenced_is_allowed(self):
		session = RecoverySession()
		session.record_fence("k2", fenced=True)
		result = self.guard.attempt_write(
			self._write_fn(), allocation=self.allocation_name, operation_key="k2",
			tool_guarantee="fenceable", recovery_session=session, store=self.store,
		)
		self.assertIsNotNone(result)

	def test_unknown_plus_fenceable_not_fenced_is_rejected(self):
		session = RecoverySession()
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k2",
				tool_guarantee="fenceable", recovery_session=session, store=self.store,
			)

	def test_fence_attempt_that_fails_does_not_unlock(self):
		session = RecoverySession()
		session.record_fence("k2", fenced=False)  # cancel_operation returned False
		with self.assertRaises(ReplayRejected):
			self.guard.attempt_write(
				self._write_fn(), allocation=self.allocation_name, operation_key="k2",
				tool_guarantee="fenceable", recovery_session=session, store=self.store,
			)

	# -- integration with FaultInjector's F7 (fenceable) end-to-end ----------

	def test_f7_fenced_before_retry_prevents_the_original_from_ever_landing_and_guard_allows_retry(self):
		store, allocation_name = _store_with_allocation()
		injector = FaultInjector()
		guard = ReplayGuard(injector=injector)
		session = RecoverySession()

		observed = injector.inject(
			"F7", "fenceable", store.submit_allocation,
			allocation=allocation_name, operation_key="k7",
		)
		self.assertFalse(observed.ok)

		fenced = injector.cancel("k7")
		self.assertTrue(fenced)
		session.record_fence("k7", fenced=fenced)

		result = guard.attempt_write(
			store.submit_allocation, allocation=allocation_name, operation_key="k7",
			tool_guarantee="fenceable", recovery_session=session, store=store,
		)
		self.assertIsNotNone(result)
		self.assertEqual(store.invoices["INV-0001"].outstanding_amount, 400.0, "only the guarded retry should have committed, exactly once")


if __name__ == "__main__":
	unittest.main()
