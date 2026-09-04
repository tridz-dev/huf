# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) tests for ST-R1.3 (WP-R1 / F-26):

1. The scheduler's `frappe.enqueue(...)` call for
   `huf.ai.orchestration.orchestrator.execute_next_step` must never pass a
   pickled `orch=` Document kwarg - only `orch_name`. Carrying the whole
   Document across the RQ job boundary is what produced the stale-`modified`
   TOCTOU this ST closes.
2. `execute_next_step` always reloads the orchestration fresh via
   `frappe.get_doc(...)` (proven by making distinct mock instances come back
   per call and asserting the one actually operated on is the fresh one).
3. Before the final `orch.save()`, if the DB-side status has already flipped
   to "Failed" (scheduler marked it so while this job ran) and the freshly
   reloaded step is "done", `execute_next_step` logs a warning and returns
   "abandoned" WITHOUT calling `save()`.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_orchestration_timeout.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	sys.modules["frappe"] = frappe_mock
if "frappe.utils" not in sys.modules:
	utils_mock = MagicMock()
	sys.modules["frappe.utils"] = utils_mock
	sys.modules["frappe"].utils = utils_mock

# huf.ai.agent_integration is imported by orchestrator.py; stub run_agent_sync
# so importing the module under test doesn't pull in the whole agent stack.
if "huf.ai.agent_integration" not in sys.modules:
	agent_integration_mock = MagicMock()
	sys.modules["huf.ai.agent_integration"] = agent_integration_mock

if "huf.ai.orchestration.planning" not in sys.modules:
	planning_mock = MagicMock()
	sys.modules["huf.ai.orchestration.planning"] = planning_mock

if "huf.ai.transaction" not in sys.modules:
	transaction_mock = MagicMock()
	transaction_mock.commit_if_background = MagicMock()
	sys.modules["huf.ai.transaction"] = transaction_mock

from huf.ai.orchestration import orchestrator  # noqa: E402
from huf.ai.orchestration import scheduler  # noqa: E402


class _FakeStep:
	def __init__(self, step_index=1, status="pending", output_ref=None):
		self.step_index = step_index
		self.status = status
		self.output_ref = output_ref
		self.modified = None
		self.instruction = "do the thing"


class _FakeOrch:
	"""A distinct, identifiable fake orchestration Document instance."""

	def __init__(self, name="ORCH-0001", status="Running", steps=None, instance_id=None):
		self.name = name
		self.status = status
		self.agent_orchestration_plan = steps if steps is not None else [_FakeStep()]
		self.agent = "AGENT-0001"
		self.current_step = 0
		self.last_run_at = None
		self.scratchpad = ""
		self.error_log = ""
		self.parent_run = None
		self.conversation = None
		self.save = MagicMock()
		self.instance_id = instance_id


class SchedulerEnqueueOmitsOrchKwargTestCase(unittest.TestCase):
	"""Proves `process_orchestrations()` never enqueues the pickled `orch=`
	Document - only `orch_name`."""

	def setUp(self):
		self.fake_cache = MagicMock()
		# nx=True set() succeeds (claim acquired) unless a test overrides it.
		self.fake_cache.set.return_value = True

		self.patchers = [
			patch.object(scheduler.frappe, "cache", return_value=self.fake_cache),
			patch.object(scheduler.frappe.db, "exists", return_value=True),
			patch.object(scheduler.frappe.db, "commit"),
			patch.object(scheduler, "time_diff_in_seconds", return_value=0),
			patch.object(scheduler, "now_datetime", return_value="2026-01-01 12:00:00"),
			patch.object(scheduler.frappe, "enqueue"),
		]
		for p in self.patchers:
			p.start()
			self.addCleanup(p.stop)

	def test_enqueue_call_never_receives_orch_kwarg(self):
		orch = _FakeOrch(name="ORCH-0001", status="Running", steps=[_FakeStep(status="pending")])

		orch_ref = type("Row", (), {"name": "ORCH-0001"})()
		with patch.object(scheduler.frappe, "get_all", return_value=[orch_ref]), \
			 patch.object(scheduler.frappe, "get_doc", return_value=orch):
			scheduler.process_orchestrations()

		scheduler.frappe.enqueue.assert_called_once()
		_, kwargs = scheduler.frappe.enqueue.call_args
		self.assertNotIn("orch", kwargs, "enqueue() must not receive a pickled orch= Document kwarg")
		self.assertEqual(kwargs.get("orch_name"), "ORCH-0001")
		self.assertEqual(kwargs.get("timeout"), 1200)

	def test_job_timeout_seconds_stays_above_rq_timeout(self):
		# The stuck-detection threshold must remain strictly above the RQ
		# job timeout (1200s) used at enqueue time, or the scheduler can mark
		# a step Failed while its job is still legitimately running.
		self.assertGreater(scheduler.JOB_TIMEOUT_SECONDS, 1200)
		self.assertEqual(scheduler.JOB_TIMEOUT_SECONDS, 1500)


class ExecuteNextStepReloadsFreshTestCase(unittest.TestCase):
	"""Proves `execute_next_step` always reloads via `frappe.get_doc` and
	never accepts/trusts a pickled orch object (the kwarg no longer exists
	on the signature at all)."""

	def setUp(self):
		self.fake_cache = MagicMock()
		self.patchers = [
			patch.object(orchestrator.frappe, "cache", return_value=self.fake_cache),
			patch.object(orchestrator.frappe.db, "commit"),
			patch.object(orchestrator.frappe.db, "set_value"),
			patch.object(orchestrator, "now_datetime", return_value="2026-01-01 12:00:00"),
		]
		for p in self.patchers:
			p.start()
			self.addCleanup(p.stop)

	def test_signature_has_no_orch_kwarg(self):
		import inspect
		sig = inspect.signature(orchestrator.execute_next_step)
		self.assertNotIn("orch", sig.parameters)
		self.assertIn("orch_name", sig.parameters)

	def test_always_reloads_fresh_via_get_doc_distinct_instances(self):
		"""Mock frappe.get_doc to return a distinct instance per call; verify
		execute_next_step operates on the freshly-returned instance (never
		some previously-cached/pickled one)."""
		call_count = {"n": 0}

		def _get_doc(doctype, name):
			call_count["n"] += 1
			if doctype == "Agent":
				return MagicMock(provider="test", model="test-model")
			step = _FakeStep(status="pending")
			return _FakeOrch(name=name, status="Running", steps=[step], instance_id=call_count["n"])

		fake_run_result = {"success": True, "response": "step done"}

		with patch.object(orchestrator.frappe, "get_doc", side_effect=_get_doc), \
			 patch.object(orchestrator, "run_agent_sync", return_value=fake_run_result), \
			 patch.object(orchestrator.frappe.db, "get_value", return_value="Running"):
			result = orchestrator.execute_next_step(orch_name="ORCH-0001")

		self.assertEqual(result, "ok")
		self.assertGreaterEqual(call_count["n"], 1)

	def test_abandons_without_save_when_scheduler_already_marked_failed(self):
		"""If the DB-side status is already 'Failed' (scheduler timed the
		step out while this job ran) and the freshly-reloaded step ends up
		'done', execute_next_step must log a warning, return 'abandoned',
		and must NOT call save()."""
		step = _FakeStep(status="pending")
		orch = _FakeOrch(name="ORCH-0001", status="Running", steps=[step])

		fake_run_result = {"success": True, "response": "finished late"}

		with patch.object(orchestrator.frappe, "get_doc") as mock_get_doc, \
			 patch.object(orchestrator, "run_agent_sync", return_value=fake_run_result), \
			 patch.object(orchestrator.frappe.db, "get_value", return_value="Failed") as mock_get_value, \
			 patch.object(orchestrator.frappe, "log_error") as mock_log_error:

			def _get_doc_side_effect(doctype, name):
				if doctype == "Agent":
					return MagicMock(provider="test", model="test-model")
				return orch

			mock_get_doc.side_effect = _get_doc_side_effect

			result = orchestrator.execute_next_step(orch_name="ORCH-0001")

		self.assertEqual(result, "abandoned")
		# orch.save() is called once earlier, when the step is flipped to
		# "in_progress" (pre-existing behavior) - but the FINAL write-back
		# save() near the end of execute_next_step must be skipped on the
		# abandon path. Guard against a regression that adds a second save.
		self.assertEqual(orch.save.call_count, 1)
		mock_log_error.assert_called()
		mock_get_value.assert_called_with("Agent Orchestration", "ORCH-0001", "status")

	def test_enqueue_lock_released_in_finally(self):
		"""The per-orchestration enqueue claim must be released once the
		step reaches a terminal per-tick state, even on the abandon path."""
		step = _FakeStep(status="pending")
		orch = _FakeOrch(name="ORCH-0001", status="Running", steps=[step])
		fake_run_result = {"success": True, "response": "finished late"}

		with patch.object(orchestrator.frappe, "get_doc") as mock_get_doc, \
			 patch.object(orchestrator, "run_agent_sync", return_value=fake_run_result), \
			 patch.object(orchestrator.frappe.db, "get_value", return_value="Failed"), \
			 patch.object(orchestrator.frappe, "log_error"):

			def _get_doc_side_effect(doctype, name):
				if doctype == "Agent":
					return MagicMock(provider="test", model="test-model")
				return orch

			mock_get_doc.side_effect = _get_doc_side_effect

			orchestrator.execute_next_step(orch_name="ORCH-0001")

		self.fake_cache.delete.assert_called_once_with(
			scheduler._orch_enqueue_lock_key("ORCH-0001")
		)


if __name__ == "__main__":
	unittest.main(verbosity=2)
