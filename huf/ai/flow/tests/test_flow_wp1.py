# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""WP1 engine/scheduler behaviour: failed-step record, approval wording and lazy expiry, MCP wait bound,
stale-run sweeper, scheduler wiring.

Frappe-free (the engine is imported against stubs, as in test_flow_engine.py). Bench-only behaviour
(scheduler tick, enqueue) is verified through the UI journeys in flows/fix/wp1.

  python -m pytest huf/ai/flow/tests/test_flow_wp1.py
"""

import asyncio
import contextlib
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

if "frappe" not in sys.modules:
	sys.modules["frappe"] = MagicMock()
for _mod_name in () if not isinstance(sys.modules["frappe"], MagicMock) else (
	"frappe.utils",
	"frappe.desk",
	"frappe.desk.doctype",
	"frappe.desk.doctype.notification_log",
	"frappe.desk.doctype.notification_log.notification_log",
	"frappe.desk.doctype.notification_settings",
	"frappe.desk.doctype.notification_settings.notification_settings",
):
	if _mod_name not in sys.modules:
		sys.modules[_mod_name] = MagicMock()
if isinstance(sys.modules.get("frappe"), MagicMock):
	sys.modules["frappe"].whitelist = lambda *a, **k: (lambda f: f)

from huf.ai.flow import engine as flow_engine  # noqa: E402
from huf.ai.graph.executor import Outcome  # noqa: E402


class TestFailedNodeRecord(unittest.TestCase):
	def test_record_has_status_and_readable_error(self):
		rec = flow_engine.failed_node_record(Outcome.failed("Tool 'x' timed out"))
		self.assertEqual(rec, {"status": "failed", "error": "Tool 'x' timed out"})

	def test_keeps_partial_dict_output_and_wraps_other_output(self):
		self.assertEqual(
			flow_engine.failed_node_record(Outcome(status="failed", error="e", output={"rows": 1})),
			{"rows": 1, "status": "failed", "error": "e"},
		)
		self.assertEqual(flow_engine.failed_node_record(Outcome(status="failed", error="e", output="raw"))["result"], "raw")

	def test_missing_error_gets_a_generic_message(self):
		self.assertTrue(flow_engine.failed_node_record(Outcome(status="failed"))["error"])

	def test_handler_records_failure_and_converts_a_raised_exception(self):
		node = types.SimpleNamespace(id="n1", type="transform", raw={"id": "n1", "type": "transform"})
		handler = flow_engine._make_node_handler(MagicMock(), {})
		with patch.object(flow_engine, "_execute_node", side_effect=RuntimeError("boom")):
			out = Outcome.from_mapping(handler(node, None, None))
		self.assertEqual(out.status, "failed")
		self.assertEqual(out.output, {"status": "failed", "error": "boom"})


class TestToolCallTimeout(unittest.TestCase):
	def _run(self, timeout_ms):
		async def slow(**kwargs):
			await asyncio.sleep(5)
			return {"success": True, "result": "late"}

		fake_mcp = types.ModuleType("huf.ai.mcp_client")
		fake_mcp.find_unique_mcp_server_for_tool = lambda name: "srv"
		fake_mcp.execute_mcp_tool = slow
		run_doc = MagicMock()
		run_doc.name = "AR-1"
		with (
			patch.object(flow_engine, "frappe") as fake_frappe,
			patch.dict(sys.modules, {"huf.ai.mcp_client": fake_mcp}),
			patch.object(flow_engine, "_create_flow_agent_run", return_value=run_doc),
			patch.object(flow_engine, "commit_if_background"),
			patch.object(flow_engine, "_bound_gateway", lambda *a, **k: contextlib.nullcontext()),
		):
			fake_frappe.get_doc.return_value = MagicMock()
			flow_run = MagicMock()
			flow_run.conversation = None
			return flow_engine._exec_tool_call(
				flow_run, {"id": "t"}, {"tool_id": "slow_tool", "input": {}, "timeout_ms": timeout_ms}, {}
			)

	def test_mcp_tool_past_timeout_ms_fails_with_a_readable_message(self):
		out = self._run(50)
		self.assertEqual(out["status"], "failed")
		self.assertIn("timed out after 50 ms", out["error"])


class TestApprovalWording(unittest.TestCase):
	def test_timeout_record_uses_decided_fields(self):
		src = open(flow_engine.__file__).read()
		self.assertNotIn("approved_by", src)
		self.assertNotIn("approved_at", src)
		self.assertIn('"decided_by"', src)
		self.assertIn('"decided_at"', src)


class TestStaleRunSweeper(unittest.TestCase):
	def _sweep(self, names, locked=()):
		docs = {n: MagicMock(status="Running") for n in names}
		with patch.object(flow_engine, "frappe") as fake_frappe, patch.object(flow_engine, "_fail_flow_run") as fail:
			fake_frappe.get_all.return_value = list(names)
			fake_frappe.cache.return_value.get.side_effect = lambda key: 1 if key.endswith(tuple(locked)) and locked else None
			fake_frappe.get_doc.side_effect = lambda doctype, name: docs[name]
			result = flow_engine.sweep_stale_runs()
			return result, fail, fake_frappe

	def test_fails_runs_with_the_documented_reason(self):
		result, fail, _ = self._sweep(["FR-1", "FR-2"])
		self.assertEqual(result, ["FR-1", "FR-2"])
		self.assertEqual(fail.call_args.args[1], "Run did not complete (worker stopped)")

	def test_skips_a_run_whose_worker_holds_the_lock(self):
		result, fail, _ = self._sweep(["FR-1", "FR-2"], locked=("FR-1",))
		self.assertEqual(result, ["FR-2"])

	def test_only_queued_and_running_older_than_the_threshold_are_selected(self):
		_, _, fake_frappe = self._sweep([])
		filters = fake_frappe.get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["status"], ["in", ["Queued", "Running"]])
		self.assertEqual(filters["modified"][0], "<")
		self.assertEqual(flow_engine.STALE_RUN_SWEEP_MINUTES, 30)


class TestRunFlowSkipsWaitingRuns(unittest.TestCase):
	def test_a_queued_job_for_a_waiting_run_does_nothing(self):
		run = MagicMock(status="Waiting Approval")
		with (
			patch.object(flow_engine, "frappe") as fake_frappe,
			patch.object(flow_engine, "_acquire_run_lock", return_value=True),
			patch.object(flow_engine, "_release_run_lock") as release,
			patch.object(flow_engine, "_execute_loop") as loop,
		):
			fake_frappe.get_doc.return_value = run
			flow_engine.run_flow("FR-1")
		loop.assert_not_called()
		run.db_set.assert_not_called()
		release.assert_called_once_with("FR-1")


class TestSchedulerWiring(unittest.TestCase):
	def test_hooks_register_the_sweepers(self):
		hooks = importlib.import_module("huf.hooks")
		cron = hooks.scheduler_events["cron"]
		self.assertIn("huf.ai.flow.triggers.run_due_schedule_flows", cron["*/1 * * * *"])
		self.assertIn("huf.ai.flow.triggers.expire_due_approvals", cron["*/1 * * * *"])
		self.assertIn("huf.ai.flow.engine.sweep_stale_runs", cron["*/5 * * * *"])

	def test_old_trigger_api_is_gone(self):
		from huf.ai.flow import api as flow_api

		for name in ("set_flow_trigger", "get_flow_trigger", "clear_flow_trigger", "_flow_automation_name"):
			self.assertFalse(hasattr(flow_api, name), name)


if __name__ == "__main__":
	unittest.main()
