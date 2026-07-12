# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime

from huf.ai.orchestration.scheduler import JOB_TIMEOUT_SECONDS, process_orchestrations


class TestProcessOrchestrations(unittest.TestCase):
	def _make_step(self, status, modified=None):
		step = MagicMock()
		step.status = status
		step.modified = modified
		step.step_index = 1
		return step

	def _make_orch(self, steps, name="ORCH-TEST-1"):
		orch = MagicMock()
		orch.name = name
		orch.error_log = ""
		orch.agent_orchestration_plan = steps
		return orch

	def test_stuck_step_marked_failed_is_not_re_enqueued(self):
		# Regression test: process_orchestrations() used to set is_running =
		# False (rather than skip the orchestration outright) after marking a
		# stuck step failed, so it fell through to the unconditional
		# frappe.enqueue() call below and re-enqueued execute_next_step for an
		# orchestration it had just marked Failed.
		stuck_since = now_datetime() - timedelta(seconds=JOB_TIMEOUT_SECONDS + 60)
		step = self._make_step("in_progress", modified=stuck_since)
		orch = self._make_orch([step])

		with patch.object(frappe.db, "exists", return_value=True), \
				patch("frappe.get_all", return_value=[frappe._dict(name="ORCH-TEST-1")]), \
				patch("frappe.get_doc", return_value=orch), \
				patch("frappe.log_error"), \
				patch.object(frappe.db, "commit"), \
				patch("frappe.enqueue") as mock_enqueue:
			process_orchestrations()

		self.assertEqual(step.status, "failed")
		self.assertEqual(orch.status, "Failed")
		mock_enqueue.assert_not_called()


if __name__ == "__main__":
	unittest.main()
