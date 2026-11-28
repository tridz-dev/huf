# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Hub delegate tool (huf.ai.tools.hub.delegate).

Pure unit tests: ``frappe`` inside the module under test is replaced by a small
fake, and the agent runtime modules are stubbed, so they run with or without a bench.
"""

import asyncio
import inspect
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

PARENT_CONV = "CONV-PARENT"
CHILD_CONV = "CONV-CHILD"
CHILD_RUN = "RUN-CHILD"


class _Exceeded(Exception):
	"""Stands in for frappe.ValidationError / RunBudgetExceeded."""


class _Env:
	"""Fake frappe + runtime modules wired for one test."""

	def __init__(self, *, exists=True, allowed=True, run_immediately=0, disabled=0, run_rows=None):
		self.allowed = allowed
		self.rows = list(run_rows or [{"status": "Success", "response": "42 rows", "error_message": None}])
		self.target = SimpleNamespace(
			name="Sales Agent", disabled=disabled, run_immediately=run_immediately, model="m", provider="p"
		)
		self.cache = MagicMock(name="cache")
		self.frappe = SimpleNamespace(
			session=SimpleNamespace(user="user@example.com"),
			DoesNotExistError=KeyError,
			PermissionError=PermissionError,
			ValidationError=_Exceeded,
			cache=self.cache,
			enqueue=MagicMock(name="enqueue"),
			get_doc=lambda *a, **k: self.target,
			db=SimpleNamespace(exists=lambda *a, **k: exists, get_value=self._get_value),
		)
		self.run_agent_sync = MagicMock(
			name="run_agent_sync",
			return_value={"conversation_id": CHILD_CONV, "agent_run_id": CHILD_RUN, "status": "Queued"},
		)
		self.budget = MagicMock(name="budget")

	def _get_value(self, doctype, filters=None, fieldname=None, as_dict=False):
		if doctype == "Agent Conversation":
			return CHILD_CONV
		if doctype == "Agent Run" and isinstance(filters, dict):
			return CHILD_RUN
		if doctype == "Agent Run":
			row = self.rows.pop(0) if len(self.rows) > 1 else self.rows[0]
			return SimpleNamespace(**row)
		return None

	def run(self, **kwargs):
		integration = types.ModuleType("huf.ai.agent.integration")
		integration._is_user_allowed = lambda doc, user: self.allowed
		integration.run_agent_sync = self.run_agent_sync
		run_budget = types.ModuleType("huf.ai.run_budget")
		run_budget.estimate_run_cost = lambda *a, **k: 0.01
		run_budget.get_current_budget = lambda: self.budget
		mods = {"huf.ai.agent.integration": integration, "huf.ai.run_budget": run_budget}
		from huf.ai.tools.hub import delegate

		args = {
			"target_agent_name": "Sales Agent",
			"prompt": "Give me the Sales Register report",
			"agent_run_id": "RUN-PARENT",
			"agent_name": "Hub Orchestrator",
		}
		args.update(kwargs)
		with (
			patch.dict(sys.modules, mods),
			patch.object(delegate, "frappe", self.frappe),
			patch.object(delegate, "safe_commit") as commit,
			patch.object(delegate.asyncio, "sleep", new=AsyncMock()) as sleep,
		):
			self.commit, self.sleep = commit, sleep
			return asyncio.run(delegate.delegate_to_agent(**args))


class TestHubDelegate(unittest.TestCase):
	def test_returns_child_result_in_new_conversation(self):
		env = _Env()
		out = env.run()
		self.assertTrue(out["success"])
		self.assertEqual(out["status"], "Success")
		self.assertEqual(out["result"], "42 rows")
		self.assertEqual(out["conversation_id"], CHILD_CONV)
		self.assertNotEqual(out["conversation_id"], PARENT_CONV)

	def test_new_conversation_never_the_parent_and_unique(self):
		env = _Env()
		env.run(agent_run_id=None)
		env.run(agent_run_id=None)
		first, second = (c.kwargs for c in env.run_agent_sync.call_args_list)
		for kw in (first, second):
			self.assertTrue(kw["external_id"].startswith("delegate-"))
			self.assertNotIn("conversation_id", kw)
			self.assertNotIn("parent_conversation_id", kw)
			self.assertNotIn("now", kw)  # queue-first, never direct execution
			self.assertEqual(kw["invoked_by_agent"], "Hub Orchestrator")
		self.assertNotEqual(first["external_id"], second["external_id"])

	def test_no_reentry_of_parent_conversation_lock(self):
		env = _Env()
		env.run()
		env.cache.assert_not_called()  # lock keys live in the cache; none is touched
		kw = env.run_agent_sync.call_args.kwargs
		self.assertNotIn(PARENT_CONV, str(kw))
		self.assertEqual(kw["parent_run_id"], "RUN-PARENT")

	def test_permission_denied(self):
		env = _Env(allowed=False)
		out = env.run()
		self.assertFalse(out["success"])
		self.assertIn("Permission Denied", out["error"])
		env.run_agent_sync.assert_not_called()

	def test_self_call_refused(self):
		env = _Env()
		out = env.run(agent_name="Sales Agent")
		self.assertFalse(out["success"])
		self.assertIn("Circular", out["error"])
		env.run_agent_sync.assert_not_called()

	def test_depth_limit_enforced(self):
		env = _Env()
		env.budget.check_depth.side_effect = _Exceeded("Recursion depth 5 exceeds ceiling 5")
		out = env.run()
		self.assertFalse(out["success"])
		self.assertIn("Recursion depth", out["error"])
		env.run_agent_sync.assert_not_called()

	def test_spend_limit_enforced(self):
		env = _Env()
		env.budget.check_spend.side_effect = _Exceeded("Spend 0.01 exceeds remaining budget")
		out = env.run()
		self.assertFalse(out["success"])
		env.run_agent_sync.assert_not_called()

	def test_no_matching_agent(self):
		env = _Env(exists=False)
		out = env.run(target_agent_name="Nope")
		self.assertFalse(out["success"])
		self.assertIn("does not exist", out["error"])
		env.run_agent_sync.assert_not_called()

	def test_disabled_agent_refused(self):
		env = _Env(disabled=1)
		self.assertFalse(env.run()["success"])
		env.run_agent_sync.assert_not_called()

	def test_cap_exceeded_returns_queued_with_link(self):
		env = _Env(run_rows=[{"status": "Started", "response": None, "error_message": None}])
		from huf.ai.tools.hub import delegate

		with patch.object(delegate, "WAIT_CAP_SECONDS", 0):
			out = env.run()
		self.assertTrue(out["success"])
		self.assertEqual(out["status"], "Queued")
		self.assertEqual(out["conversation_link"], f"/huf/chat/{CHILD_CONV}")
		self.assertIn("still running", out["message"])
		self.assertNotIn("result", out)

	def test_wait_is_capped_below_gateway_timeout(self):
		from huf.ai.tools.hub import delegate

		self.assertLessEqual(delegate.WAIT_CAP_SECONDS, 90)
		self.assertGreaterEqual(delegate.WAIT_CAP_SECONDS, 60)

	def test_polls_without_blocking_and_refreshes_snapshot(self):
		env = _Env(
			run_rows=[
				{"status": "Queued", "response": None, "error_message": None},
				{"status": "Started", "response": None, "error_message": None},
				{"status": "Success", "response": "done", "error_message": None},
			]
		)
		out = env.run()
		self.assertEqual(out["result"], "done")
		self.assertEqual(env.sleep.await_count, 2)  # asyncio.sleep, never time.sleep
		self.assertGreaterEqual(env.commit.call_count, 3)  # snapshot ended before each poll

	def test_failed_child_reports_error_and_link(self):
		env = _Env(run_rows=[{"status": "Failed", "response": None, "error_message": "boom"}])
		out = env.run()
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "boom")
		self.assertEqual(out["conversation_link"], f"/huf/chat/{CHILD_CONV}")

	def test_run_immediately_agent_is_enqueued_not_run_inline(self):
		env = _Env(run_immediately=1)
		env.run()
		env.run_agent_sync.assert_not_called()
		env.frappe.enqueue.assert_called_once()
		kw = env.frappe.enqueue.call_args.kwargs
		self.assertTrue(kw["enqueue_after_commit"])
		self.assertTrue(kw["external_id"].startswith("delegate-"))
		self.assertNotIn("now", kw)

	def test_handler_is_a_coroutine(self):
		from huf.ai.tools.hub import delegate

		self.assertTrue(inspect.iscoroutinefunction(delegate.delegate_to_agent))
