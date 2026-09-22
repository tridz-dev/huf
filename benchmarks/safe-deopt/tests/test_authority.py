# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for the authority sub-experiment (``authority_experiment.py``, Track-Item: 7).

Pure pytest -- no frappe, no bench, no LLM. Adds the parent directory to ``sys.path`` so
``authority_experiment`` and ``workloads`` import as plain top-level modules, mirroring
``test_workloads.py``'s own import pattern in this same directory.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from authority_experiment import run_authority_experiment  # noqa: E402
from workloads import CrmStore, Customer, OpenItem, PermissionDenied  # noqa: E402


class TestAuthorityExperimentReport(unittest.TestCase):
	"""Exercises the full ``run_authority_experiment`` report and asserts every check passes."""

	def setUp(self) -> None:
		self.report = run_authority_experiment()

	def test_overall_report_passes(self) -> None:
		failed = {name: c for name, c in self.report["checks"].items() if not c["passed"]}
		self.assertTrue(self.report["passed"], msg=f"failing checks: {failed}")

	def test_report_has_expected_checks_for_both_workloads(self) -> None:
		expected = {
			"w1_write_a_approved_under_admin_envelope",
			"w1_write_b_denied_for_low_priv_actor",
			"w1_no_partial_commit",
			"w1_handoff_payload_is_inert",
			"w1_recovery_agent_also_denied",
			"w1_no_commit_after_recovery_attempt",
			"w2_write_a_approved_under_admin_envelope",
			"w2_write_b_denied_for_low_priv_actor",
			"w2_no_partial_commit",
			"w2_handoff_payload_is_inert",
			"w2_recovery_agent_also_denied",
			"w2_no_commit_after_recovery_attempt",
		}
		self.assertEqual(expected, set(self.report["checks"].keys()))

	def test_each_check_has_bool_passed_and_string_detail(self) -> None:
		for name, check in self.report["checks"].items():
			self.assertIsInstance(check["passed"], bool, msg=name)
			self.assertIsInstance(check["detail"], str, msg=name)


class TestAuthorityDenialDirectly(unittest.TestCase):
	"""Sanity checks against the raw store, independent of the report module, confirming the
	core scenario: write B approved in principle under an admin envelope, denied at runtime
	for a lower-privileged invoker, with no partial commit and no smuggled re-authorization.
	"""

	def _low_priv_authorizer(self, action: str, _payload: dict) -> bool:
		return action != "submit_linked_record"

	def test_write_b_denied_and_no_partial_commit(self) -> None:
		store = CrmStore(authorizer=self._low_priv_authorizer)
		store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
		store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-1", customer_id="CUST-1", outstanding_amount=50.0))
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-1", allocated_to="clerk@example.com", operation_key="op-a")

		with self.assertRaises(PermissionDenied):
			store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-1", operation_key="op-b")

		item = store.open_items[("Sales Invoice", "SINV-1")]
		self.assertEqual(item.status, "open")
		self.assertFalse(any(e.action == "submit_linked_record" and e.committed for e in store.commit_log))

	def test_recovery_agent_same_restrictive_authorizer_still_denied(self) -> None:
		store = CrmStore(authorizer=self._low_priv_authorizer)
		store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
		store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-2", customer_id="CUST-1", outstanding_amount=50.0))
		store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2", allocated_to="clerk@example.com", operation_key="op-a-2")

		with self.assertRaises(PermissionDenied):
			store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2", operation_key="op-b-first")

		# A "recovery agent" retries via the SAME store under the SAME restrictive authorizer.
		with self.assertRaises(PermissionDenied):
			store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2", operation_key="op-b-retry")

		item = store.open_items[("Sales Invoice", "SINV-2")]
		self.assertEqual(item.status, "open")


if __name__ == "__main__":
	unittest.main()
