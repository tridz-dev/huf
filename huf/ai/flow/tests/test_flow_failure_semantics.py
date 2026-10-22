# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Flow failure semantics, pinned end to end through the real Flow engine.

A failing node is a ``tool.call`` to a real registered tool whose invocation
returns ``success: False`` (the tool dispatcher is patched to that result), so
the node's own executor returns ``{"status": "failed"}``. The three cases:

  (a) failing node, no outgoing edge  -> Flow Run ends ``Failed`` with ``last_error``.
  (b) failing node with ``on_error``  -> the on_failure edge is followed, run ``Success``.
  (c) failing node with a ``next``    -> run ends ``Failed`` (the ``always`` edge is
      still followed, see (d), but does not handle the failure).
  (d) the downstream cleanup node still executes, and the run is ``Failed``.
  (e) failure handled by an ``on_failure`` edge -> run ``Success``.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_failure_semantics
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.engine import create_flow_run
from huf.ai.flow.engine import run_flow as engine_run_flow
from huf.testing.factories import make_agent_tool_function


class TestFlowFailureSemantics(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._names = {"Flow Definition": [], "Flow Run": [], "Agent Tool Function": []}

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Flow Run", "Flow Definition", "Agent Tool Function"):
			for name in self._names.get(doctype, []):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _limits(self):
		return {
			"max_nodes": 20,
			"max_rows": 1000,
			"max_output_bytes": 100_000,
			"max_parallel_calls": 1,
			"max_foreach_iterations": 1,
			"max_external_calls": 5,
			"max_writes": 0,
			"max_wall_time_ms": 5000,
			"fail_closed": True,
		}

	def _make_failing_tool(self):
		tool_name = f"_test_flow_failure_{frappe.generate_hash(length=8)}"
		doc = make_agent_tool_function(
			tool_name=tool_name,
			types="App Provided",
			description="Test tool: its invocation is forced to fail by the test.",
			function_path="huf.ai.tools.telegram.handle_action",
			params='{"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}',
			is_read_only=0,
		)
		self._names["Agent Tool Function"].append(doc.name)
		return doc.tool_name

	def _definition(self, tool_name, failing_node_extra, terminal_ids=()):
		"""entry -> fail (tool.call to a missing tool) -> routing given by failing_node_extra.

		Only the terminal nodes the case routes to are included: the validator rejects
		unreachable nodes.
		"""
		failing = {
			"id": "fail",
			"type": "tool.call",
			"config": {"tool_id": tool_name, "input": {"action": "send_message"}},
		}
		failing.update(failing_node_extra)
		return {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "fail"},
				failing,
				*(
					{"id": node_id, "type": "trigger.webhook", "config": {"method": "POST"}}
					for node_id in terminal_ids
				),
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": self._limits(),
			},
		}

	def _run(self, failing_node_extra, terminal_ids=()):
		tool_name = self._make_failing_tool()
		definition = self._definition(tool_name, failing_node_extra, terminal_ids)
		flow_id = f"_test-flow-failure-{frappe.generate_hash(length=8)}"
		saved = flow_api.save_flow_definition(flow_id, definition)
		self._names["Flow Definition"].append(saved["flow_id"])
		flow_run = create_flow_run(flow_id=flow_id, payload={}, trigger_type="Doc Event")
		self._names["Flow Run"].append(flow_run.name)
		failed_tool_result = {"success": False, "error": "simulated tool failure"}
		with patch("huf.ai.flow.engine.execute_tool", return_value=failed_tool_result):
			engine_run_flow(flow_run.name)
		flow_run.reload()
		return flow_run

	def test_a_failed_node_without_edge_fails_the_run(self):
		"""(a) A failing node with no outgoing edge ends the run Failed, with last_error set."""
		flow_run = self._run({})

		self.assertEqual(flow_run.status, "Failed")
		self.assertTrue(flow_run.last_error, "a failed run must carry last_error")
		self.assertIn("fail", flow_run.last_error)

	def test_b_failed_node_with_on_error_follows_on_failure_edge(self):
		"""(b) A failing node with an on_error route follows it and the run succeeds."""
		flow_run = self._run({"on_error": "recover"}, ["recover"])

		self.assertEqual(flow_run.status, "Success", f"unexpected: {flow_run.last_error}")

	def test_c_failed_node_with_normal_next_edge_does_not_report_success(self):
		"""(c) A failing node whose only outgoing edge is a normal ``next`` must not
		end the run Success as if the node had succeeded."""
		flow_run = self._run({"next": "after"}, ["after"])

		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("fail", flow_run.last_error)
		self.assertIn("simulated tool failure", flow_run.last_error)

	def test_d_always_edge_runs_cleanup_but_run_is_failed(self):
		"""(d) The always edge is still followed (cleanup runs) yet the run ends Failed."""
		flow_run = self._run({"next": "after"}, ["after"])

		self.assertEqual(flow_run.current_node_id, "after")
		self.assertEqual(flow_run.status, "Failed")
		self.assertTrue(flow_run.last_error)

	def test_e_failure_handled_by_on_failure_edge_succeeds(self):
		"""(e) A failure routed via an explicit on_failure edge is handled: run Success."""
		flow_run = self._run({"on_error": "recover"}, ["recover"])

		self.assertEqual(flow_run.current_node_id, "recover")
		self.assertEqual(flow_run.status, "Success", f"unexpected: {flow_run.last_error}")


if __name__ == "__main__":
	unittest.main()
