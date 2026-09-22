# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for benchmarks/safe-deopt/workloads.py and invariants_safedeopt.py.

Pure pytest -- no frappe, no bench. Adds the parent directory to ``sys.path`` so
``workloads`` and ``invariants_safedeopt`` import as plain top-level modules, mirroring how
``huf/ai/tests/test_benchmark3_write_runtime.py`` loads ``benchmarks/benchmark-3-crm-followup/
invariants.py`` by path rather than assuming a package layout.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from invariants_safedeopt import (  # noqa: E402
	ledger_balances,
	no_duplicate_committed_write,
	no_unauthorized_commits,
	no_unsafe_write_duplicates,
	task_completed_or_escalated,
	valid_allocation_states,
	valid_todo_and_item_states,
)
from workloads import (  # noqa: E402
	CrmStore,
	Customer,
	Invoice,
	OpenItem,
	Payment,
	PaymentAllocationStore,
	PermissionDenied,
	classify_payment,
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
	store.seed_invoice(Invoice(name="SINV-4002", customer="CUST-0001", outstanding_amount=9000.0))
	store.seed_payment(Payment(name="PE-4001", customer="CUST-0001", amount=5000.0))
	return store


# ---------------------------------------------------------------------------
# W1 -- normal successful run
# ---------------------------------------------------------------------------


class W1NormalRunTests(unittest.TestCase):
	def test_full_flow_reads_then_writes_then_pending_notify(self):
		store = _make_crm_store()

		customer = store.read_customer("CUST-0001")
		self.assertIsNotNone(customer)
		open_items = store.read_open_items("CUST-0001")
		self.assertEqual(len(open_items), 1)

		op_key_a = "crm-followup:create_todo:CUST-0001:SINV-2001"
		todo = store.create_followup_todo(
			reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="collections@hufretail.example", operation_key=op_key_a
		)
		self.assertEqual(todo.name, "TODO-0001")

		op_key_b = "crm-followup:submit_linked_record:CUST-0001:SINV-2001"
		item = store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2001", operation_key=op_key_b)
		self.assertEqual(item.status, "submitted")

		# pending/non-critical: allowed to happen, doesn't affect ground truth
		store.notify(channel="slack", message="Follow-up created")
		self.assertEqual(len(store.pending_notifications), 1)

		committed_actions = {e.action for e in store.commit_log if e.committed}
		self.assertEqual(committed_actions, {"create_followup_todo", "submit_linked_record"})

		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_followup_todo", "submit_linked_record"], escalated=False
		)
		self.assertTrue(ok, reason)

	def test_second_create_with_same_operation_key_is_idempotent_no_op(self):
		store = _make_crm_store()
		op_key = "crm-followup:create_todo:CUST-0001:SINV-2001"
		first = store.create_followup_todo(
			reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="collections@hufretail.example", operation_key=op_key
		)
		second = store.create_followup_todo(
			reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="collections@hufretail.example", operation_key=op_key
		)
		self.assertEqual(first.name, second.name)
		self.assertEqual(len(store.todos), 1)

		ok, reason = no_duplicate_committed_write(store.commit_log, action="create_followup_todo")
		self.assertTrue(ok, reason)


# ---------------------------------------------------------------------------
# W2 -- normal successful run
# ---------------------------------------------------------------------------


class W2NormalRunTests(unittest.TestCase):
	def test_full_flow_classify_allocate_submit_then_pending_followup(self):
		store = _make_payment_store()

		invoices = store.list_invoices()
		payments = store.list_payments()
		self.assertEqual(len(invoices), 2)
		self.assertEqual(len(payments), 1)

		payment = payments[0]
		classification = classify_payment(payment, invoices)
		self.assertEqual(classification["classification"], "resolved")
		self.assertEqual(classification["invoice"], "SINV-4001")

		alloc = store.create_allocation(
			payment=payment.name, invoice=classification["invoice"], amount=payment.amount, operation_key="alloc-create:PE-4001:SINV-4001"
		)
		self.assertEqual(alloc.status, "draft")

		submitted = store.submit_allocation(allocation=alloc.name, operation_key="alloc-submit:PE-4001:SINV-4001")
		self.assertEqual(submitted.status, "submitted")
		self.assertAlmostEqual(store.invoices["SINV-4001"].outstanding_amount, 0.0)

		store.update_followup_status(payment=payment.name, status="reconciled")
		self.assertEqual(len(store.pending_followup_updates), 1)

		for check in (ledger_balances, valid_allocation_states):
			ok, reason = check(store)
			self.assertTrue(ok, reason)

		ok, reason = task_completed_or_escalated(store.commit_log, required_actions=["create_allocation", "submit_allocation"], escalated=False)
		self.assertTrue(ok, reason)

	def test_classify_payment_needs_review_when_ambiguous_or_no_match(self):
		invoices = [
			Invoice(name="SINV-A", customer="CUST-1", outstanding_amount=100.0),
			Invoice(name="SINV-B", customer="CUST-1", outstanding_amount=100.0),
		]
		ambiguous_payment = Payment(name="PE-A", customer="CUST-1", amount=100.0)
		result = classify_payment(ambiguous_payment, invoices)
		self.assertEqual(result["classification"], "needs_review")

		no_match_payment = Payment(name="PE-B", customer="CUST-1", amount=999.0)
		result2 = classify_payment(no_match_payment, invoices)
		self.assertEqual(result2["classification"], "needs_review")
		self.assertEqual(result2["invoice"], None)


# ---------------------------------------------------------------------------
# Commit log records true outcome of every write attempt
# ---------------------------------------------------------------------------


class CommitLogGroundTruthTests(unittest.TestCase):
	def test_failed_write_is_logged_as_not_committed(self):
		store = _make_crm_store()

		def deny_submit(action, _payload):
			return action != "submit_linked_record"

		store.authorizer = deny_submit
		with self.assertRaises(PermissionDenied):
			store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2001", operation_key="op-denied")

		denied_entries = [e for e in store.commit_log if e.operation_key == "op-denied"]
		self.assertEqual(len(denied_entries), 1)
		self.assertFalse(denied_entries[0].committed)
		# the OpenItem itself must not have changed state
		self.assertEqual(store.open_items[("Sales Invoice", "SINV-2001")].status, "open")

	def test_duplicate_operation_key_logged_as_not_committed_not_silently_dropped(self):
		store = _make_crm_store()
		op_key = "dup-key"
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key=op_key)
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key=op_key)

		matching = [e for e in store.commit_log if e.operation_key == op_key]
		self.assertEqual(len(matching), 2)
		self.assertTrue(matching[0].committed)
		self.assertFalse(matching[1].committed)  # the true outcome of the 2nd attempt: no new write

	def test_commit_log_is_invisible_to_and_unaffected_by_a_lying_wrapper(self):
		"""A fault-injection wrapper can lie about the return value it hands to a caller, but
		it cannot rewrite the store's own commit_log -- this test simulates exactly that: a
		wrapper that reports failure to its caller even though the store committed.
		"""
		store = _make_payment_store()
		alloc = store.create_allocation(payment="PE-4001", invoice="SINV-4001", amount=5000.0, operation_key="op-1")

		def lying_wrapper_submit():
			try:
				store.submit_allocation(allocation=alloc.name, operation_key="op-2")
				return "reported: timeout (a lie -- it actually committed)"
			except Exception as exc:  # pragma: no cover - defensive
				return f"reported: error {exc}"

		reported = lying_wrapper_submit()
		self.assertIn("lie", reported)

		# ground truth still shows the true outcome regardless of what was reported
		committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.committed]
		self.assertEqual(len(committed), 1)
		self.assertEqual(store.allocations[alloc.name].status, "submitted")


# ---------------------------------------------------------------------------
# Non-idempotent W2 variant actually creates duplicates
# ---------------------------------------------------------------------------


class NonIdempotentVariantTests(unittest.TestCase):
	def test_unsafe_submit_called_twice_creates_two_committed_allocations_and_double_decrements(self):
		store = _make_payment_store()
		first = store.submit_allocation_unsafe(payment="PE-4001", invoice="SINV-4001", amount=5000.0)
		second = store.submit_allocation_unsafe(payment="PE-4001", invoice="SINV-4001", amount=5000.0)

		self.assertNotEqual(first.name, second.name)
		committed = [e for e in store.commit_log if e.action == "submit_allocation_unsafe" and e.committed]
		self.assertEqual(len(committed), 2)

		# this is genuinely wrong: the invoice was only owed 5000, now shows -5000
		self.assertAlmostEqual(store.invoices["SINV-4001"].outstanding_amount, -5000.0)

		ok, reason = no_unsafe_write_duplicates(store, payment="PE-4001", expected_max=1)
		self.assertFalse(ok, "expected the non-idempotent variant to be caught as a duplicate-write violation")

		ok, reason = ledger_balances(store)
		self.assertFalse(ok, "expected the double-decrement to be caught as a negative-balance violation")


# ---------------------------------------------------------------------------
# Each invariant function catches at least one hand-constructed violation
# ---------------------------------------------------------------------------


class InvariantViolationTests(unittest.TestCase):
	def test_no_duplicate_committed_write_catches_hand_forged_duplicate(self):
		store = _make_crm_store()
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key="k1")
		# hand-forge a second COMMITTED entry with the same record_key, bypassing the store's
		# own dedup logic entirely, to prove the invariant catches this shape of bug even if
		# a future code change in the store itself broke idempotency.
		forged = store.commit_log[-1]
		store.commit_log.append(
			type(forged)(seq=forged.seq + 1, action=forged.action, operation_key="k2-different-key", committed=True, record_key=forged.record_key)
		)
		ok, reason = no_duplicate_committed_write(store.commit_log, action="create_followup_todo")
		self.assertFalse(ok, reason)

	def test_ledger_balances_catches_hand_forged_negative_balance(self):
		store = _make_payment_store()
		store.invoices["SINV-4001"].outstanding_amount = -10.0
		ok, reason = ledger_balances(store)
		self.assertFalse(ok, reason)

	def test_valid_allocation_states_catches_bad_status(self):
		store = _make_payment_store()
		alloc = store.create_allocation(payment="PE-4001", invoice="SINV-4001", amount=5000.0, operation_key="op-1")
		alloc.status = "half-submitted"  # impossible state, hand-forged
		ok, reason = valid_allocation_states(store)
		self.assertFalse(ok, reason)

	def test_valid_allocation_states_catches_orphaned_invoice_reference(self):
		store = _make_payment_store()
		alloc = store.create_allocation(payment="PE-4001", invoice="SINV-4001", amount=5000.0, operation_key="op-1")
		alloc.status = "submitted"
		alloc.invoice = "SINV-DOES-NOT-EXIST"
		ok, reason = valid_allocation_states(store)
		self.assertFalse(ok, reason)

	def test_valid_todo_and_item_states_catches_dangling_reference(self):
		store = _make_crm_store()
		todo = store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key="k1")
		todo.reference_name = "SINV-DOES-NOT-EXIST"
		ok, reason = valid_todo_and_item_states(store)
		self.assertFalse(ok, reason)

	def test_task_completed_or_escalated_catches_silent_incompleteness(self):
		store = _make_crm_store()
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key="k1")
		# write B never happened, and nobody escalated -- this is the violation
		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_followup_todo", "submit_linked_record"], escalated=False
		)
		self.assertFalse(ok, reason)
		# the same missing write, but correctly escalated, passes
		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_followup_todo", "submit_linked_record"], escalated=True
		)
		self.assertTrue(ok, reason)

	def test_no_unauthorized_commits_catches_a_commit_a_stricter_authorizer_would_have_denied(self):
		store = _make_crm_store()
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key="k1")

		def stricter_authorizer(action, _payload):
			return action != "create_followup_todo"  # retroactively, this action is disallowed

		ok, reason = no_unauthorized_commits(store.commit_log, authorizer=stricter_authorizer)
		self.assertFalse(ok, reason)

	def test_no_unauthorized_commits_passes_with_permissive_authorizer(self):
		store = _make_crm_store()
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="a@b.com", operation_key="k1")
		ok, reason = no_unauthorized_commits(store.commit_log, authorizer=lambda *_a: True)
		self.assertTrue(ok, reason)


if __name__ == "__main__":
	unittest.main()
