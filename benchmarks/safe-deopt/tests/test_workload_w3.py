# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for W3 (``benchmarks/safe-deopt/workloads.py``'s ``OrderProcessingStore``).

Pure pytest -- no frappe, no bench. Mirrors ``test_workloads.py``'s style: adds the parent
directory to ``sys.path`` so ``workloads``/``invariants_safedeopt`` import as plain
top-level modules.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from invariants_safedeopt import no_duplicate_committed_write, task_completed_or_escalated  # noqa: E402
from workloads import (  # noqa: E402
	Account,
	OrderProcessingStore,
	PermissionDenied,
	PriorOrder,
	check_eligibility,
	compute_pricing,
)


def _make_store() -> OrderProcessingStore:
	store = OrderProcessingStore()
	store.seed_account(Account(account_id="ACC-0001", name="Acme Retail", loyalty_tier="gold"))
	store.seed_prior_order(PriorOrder(order_id="ORD-OLD-1", account_id="ACC-0001", amount=1200.0, status="fulfilled"))
	store.seed_prior_order(PriorOrder(order_id="ORD-OLD-2", account_id="ACC-0001", amount=800.0, status="fulfilled"))
	return store


class W3NormalRunTests(unittest.TestCase):
	def test_full_eight_step_flow(self):
		store = _make_store()

		# 1. read_account
		account = store.read_account("ACC-0001")
		self.assertIsNotNone(account)

		# 2. read_prior_orders
		prior_orders = store.read_prior_orders("ACC-0001")
		self.assertEqual(len(prior_orders), 2)

		# 3. check_eligibility (pure logic, no I/O)
		eligibility = check_eligibility(account, prior_orders)
		self.assertTrue(eligibility["eligible"])
		self.assertIsNone(eligibility["reason"])

		# 4. create_draft_order (write A)
		op_key_a = "w3-order:create_draft:ACC-0001:req-1"
		draft = store.create_draft_order(account_id="ACC-0001", items_subtotal=1000.0, operation_key=op_key_a)
		self.assertEqual(draft.status, "draft")
		self.assertEqual(draft.name, "ORDER-0001")

		# 5. compute_pricing (pure logic, no I/O)
		pricing = compute_pricing(account, draft.items_subtotal)
		self.assertAlmostEqual(pricing["discount_percent"], 10.0)
		self.assertAlmostEqual(pricing["total"], 900.0)
		store.apply_pricing(order=draft.name, discount_percent=pricing["discount_percent"], total=pricing["total"])
		self.assertAlmostEqual(store.draft_orders[draft.name].total, 900.0)

		# 6. submit_order (write B)
		op_key_b = "w3-order:submit_order:ACC-0001:req-1"
		submitted = store.submit_order(order=draft.name, operation_key=op_key_b)
		self.assertEqual(submitted.status, "submitted")

		# 7. update_fulfillment_status (pending/non-critical)
		store.update_fulfillment_status(order=draft.name, status="in_progress")
		self.assertEqual(len(store.pending_fulfillment_updates), 1)
		self.assertEqual(store.draft_orders[draft.name].fulfillment_status, "in_progress")

		# 8. notify (pending/non-critical)
		store.notify(channel="email", message="Order confirmed")
		self.assertEqual(len(store.pending_notifications), 1)

		committed_actions = {e.action for e in store.commit_log if e.committed}
		self.assertEqual(committed_actions, {"create_draft_order", "submit_order"})

		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_draft_order", "submit_order"], escalated=False
		)
		self.assertTrue(ok, reason)

	def test_second_create_with_same_operation_key_is_idempotent_no_op(self):
		store = _make_store()
		op_key = "w3-order:create_draft:ACC-0001:req-1"
		first = store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key=op_key)
		second = store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key=op_key)
		self.assertEqual(first.name, second.name)
		self.assertEqual(len(store.draft_orders), 1)

		ok, reason = no_duplicate_committed_write(store.commit_log, action="create_draft_order")
		self.assertTrue(ok, reason)

	def test_second_submit_with_same_operation_key_is_idempotent_no_op(self):
		store = _make_store()
		draft = store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key="create-1")
		store.submit_order(order=draft.name, operation_key="submit-1")
		store.submit_order(order=draft.name, operation_key="submit-1")

		submitted_committed = [e for e in store.commit_log if e.action == "submit_order" and e.committed]
		self.assertEqual(len(submitted_committed), 1)

		ok, reason = no_duplicate_committed_write(store.commit_log, action="submit_order")
		self.assertTrue(ok, reason)

	def test_submit_with_different_operation_key_after_already_submitted_does_not_double_submit(self):
		store = _make_store()
		draft = store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key="create-1")
		store.submit_order(order=draft.name, operation_key="submit-1")
		# a different (but logically equivalent) operation_key must still not re-submit
		result = store.submit_order(order=draft.name, operation_key="submit-2-different-key")
		self.assertEqual(result.status, "submitted")

		submitted_committed = [e for e in store.commit_log if e.action == "submit_order" and e.committed]
		self.assertEqual(len(submitted_committed), 1)


class EligibilityTests(unittest.TestCase):
	def test_credit_hold_denies_eligibility(self):
		account = Account(account_id="ACC-X", name="Blocked Co", credit_hold=True)
		result = check_eligibility(account, [])
		self.assertFalse(result["eligible"])
		self.assertEqual(result["reason"], "account_on_credit_hold")

	def test_too_many_disputed_orders_denies_eligibility(self):
		account = Account(account_id="ACC-Y", name="Disputer Co")
		orders = [
			PriorOrder(order_id="O1", account_id="ACC-Y", amount=100.0, status="disputed"),
			PriorOrder(order_id="O2", account_id="ACC-Y", amount=100.0, status="disputed"),
			PriorOrder(order_id="O3", account_id="ACC-Y", amount=100.0, status="fulfilled"),
		]
		result = check_eligibility(account, orders)
		self.assertFalse(result["eligible"])
		self.assertEqual(result["reason"], "too_many_disputed_prior_orders")

	def test_eligible_account_with_no_prior_orders(self):
		account = Account(account_id="ACC-Z", name="New Co")
		result = check_eligibility(account, [])
		self.assertTrue(result["eligible"])


class PricingTests(unittest.TestCase):
	def test_gold_tier_discount(self):
		account = Account(account_id="ACC-1", name="Gold Co", loyalty_tier="gold")
		result = compute_pricing(account, 1000.0)
		self.assertAlmostEqual(result["discount_percent"], 10.0)
		self.assertAlmostEqual(result["total"], 900.0)

	def test_standard_tier_has_no_discount(self):
		account = Account(account_id="ACC-2", name="Standard Co", loyalty_tier="standard")
		result = compute_pricing(account, 1000.0)
		self.assertAlmostEqual(result["discount_percent"], 0.0)
		self.assertAlmostEqual(result["total"], 1000.0)

	def test_silver_tier_discount(self):
		account = Account(account_id="ACC-3", name="Silver Co", loyalty_tier="silver")
		result = compute_pricing(account, 1000.0)
		self.assertAlmostEqual(result["discount_percent"], 5.0)
		self.assertAlmostEqual(result["total"], 950.0)


class CommitLogGroundTruthTests(unittest.TestCase):
	def test_failed_write_is_logged_as_not_committed(self):
		store = _make_store()

		def deny_submit(action, _payload):
			return action != "submit_order"

		store.authorizer = deny_submit
		draft = store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key="create-1")
		with self.assertRaises(PermissionDenied):
			store.submit_order(order=draft.name, operation_key="op-denied")

		denied_entries = [e for e in store.commit_log if e.operation_key == "op-denied"]
		self.assertEqual(len(denied_entries), 1)
		self.assertFalse(denied_entries[0].committed)
		self.assertEqual(store.draft_orders[draft.name].status, "draft")

	def test_task_completed_or_escalated_catches_missing_submit(self):
		store = _make_store()
		store.create_draft_order(account_id="ACC-0001", items_subtotal=500.0, operation_key="create-1")
		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_draft_order", "submit_order"], escalated=False
		)
		self.assertFalse(ok, reason)
		ok, reason = task_completed_or_escalated(
			store.commit_log, required_actions=["create_draft_order", "submit_order"], escalated=True
		)
		self.assertTrue(ok, reason)


if __name__ == "__main__":
	unittest.main()
