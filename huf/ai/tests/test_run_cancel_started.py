"""Stop on Started runs that no stream loop drives (mocked; no DB)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.orchestration import cancel

ORCH = SimpleNamespace(name="ORCH-1", parent_run="PARENT")


def _get_all(active):
	def get_all(doctype, filters=None, fields=None):
		if doctype == "Agent Run":
			return [SimpleNamespace(agent_orchestration="ORCH-1")]
		if not active or ("parent_run" in filters and filters["parent_run"] != "PARENT"):
			return []
		return [ORCH]

	return get_all


class TestCancelStartedRuns(unittest.TestCase):
	def _patched(self, active=True):
		db = MagicMock()
		patches = (
			patch.object(cancel.frappe, "db", db, create=True),
			patch.object(cancel.frappe, "get_all", _get_all(active), create=True),
			patch.object(cancel, "mark_cancelled_tool_calls"),
			patch("huf.ai.agent.integration._guarded_fail_started_run", return_value=True),
		)
		mocks = [p.start() for p in patches]
		self.addCleanup(lambda: [p.stop() for p in patches])
		return db, mocks[3]

	def test_stopping_the_parent_run_cancels_the_plan_and_fails_the_run(self):
		db, fail = self._patched()
		self.assertTrue(cancel.cancel_orchestration_for_run("PARENT"))
		db.set_value.assert_called_once_with("Agent Orchestration", "ORCH-1", "status", "Cancelled")
		fail.assert_called_once_with("PARENT", cancel.CANCELLED_BY_USER)

	def test_stopping_a_step_run_cancels_the_plan_but_stays_cooperative(self):
		db, fail = self._patched()
		self.assertFalse(cancel.cancel_orchestration_for_run("STEP"))
		db.set_value.assert_called_once_with("Agent Orchestration", "ORCH-1", "status", "Cancelled")
		fail.assert_called_once_with("PARENT", cancel.CANCELLED_BY_USER)

	def test_run_without_an_active_plan_is_left_alone(self):
		db, fail = self._patched(active=False)
		self.assertFalse(cancel.cancel_orchestration_for_run("PARENT"))
		db.set_value.assert_not_called()
		fail.assert_not_called()

	def test_step_job_honours_a_cancel_marker_on_the_parent_run(self):
		db, fail = self._patched()
		db.get_value.return_value = "Running"
		with patch.object(cancel, "is_run_cancelled", return_value=True):
			self.assertTrue(cancel.honour_cancel(ORCH))
		fail.assert_called_once_with("PARENT", cancel.CANCELLED_BY_USER)

	def test_finished_provider_call_of_a_stopped_run_is_not_a_success(self):
		_db, fail = self._patched()
		run, conversation = SimpleNamespace(name="R1"), SimpleNamespace(name="C1")
		with (
			patch.object(cancel, "is_run_cancelled", return_value=True),
			patch.object(cancel, "now_datetime"),
			patch("huf.ai.agent.integration._emit_run_lifecycle_event") as emit,
		):
			result = cancel.finish_if_cancelled(run, conversation)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], cancel.CANCELLED_BY_USER)
		fail.assert_called_once_with("R1", cancel.CANCELLED_BY_USER)
		emit.assert_called_once()

	def test_run_that_was_not_stopped_continues(self):
		with patch.object(cancel, "is_run_cancelled", return_value=False):
			self.assertIsNone(cancel.finish_if_cancelled(SimpleNamespace(name="R1"), None))
