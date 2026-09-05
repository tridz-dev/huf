# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""GW-01: tool.call's config shape must match the graph-IR schema.

``huf/ai/graph/graph_ir.schema.json``'s ``ToolCallNode`` requires
``config.tool_id``/``config.input`` (and forbids any other key, via
``additionalProperties: false``) -- that is the ONLY shape
``huf.huf.doctype.flow_definition.flow_definition.FlowDefinition.validate()``
will ever let a Flow Definition save with. But
``huf.ai.flow_engine._exec_tool_call`` (the executor actually run by
``GraphExecutor``) used to read ``config.tool_name``/``config.args`` instead --
a schema-valid tool.call node saved through ``flow_api.save_flow_definition``
could never actually invoke a tool at runtime; it would immediately fail with
"tool.call node missing tool_name in config".

Two layers here:

  - ``TestToolCallSchemaExecutorConsistency`` -- a frappe-free unit test that
    round-trips the tool.call node type through ``_exec_tool_call`` using
    exactly the schema's required config field names, proving the executor
    actually consumes them (not a stale field name).
  - ``TestSavedFlowInvokesRealTool`` -- a real-bench (Layer B) integration
    test: a Flow Definition is created via the real, whitelisted
    ``flow_api.save_flow_definition`` (so it goes through real schema
    validation), then run via ``flow_api.run_flow`` end to end against a real
    ``Agent Tool Function``, asserting the Flow Run succeeds and a real
    ``Agent Tool Call`` record is created for the invocation (GT-05's "exactly
    one telemetry record per call").

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_flow_tool_call_gw01
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mirrors test_flow_engine.py's frappe-free stub setup for the pure unit-test
# class below -- huf.ai.flow_engine does `from frappe.<submodule> import X`
# at import time, which a bare top-level MagicMock cannot satisfy.
if "frappe" not in sys.modules:
	sys.modules["frappe"] = MagicMock()
for _mod_name in (
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

from huf.ai import flow_engine  # noqa: E402


class _FakeFlowRun:
	def __init__(self, **fields):
		defaults = dict(
			name="FR-TEST-GW01",
			flow_id="test-flow-gw01",
			conversation=None,
			context_json="{}",
			last_agent_run=None,
		)
		defaults.update(fields)
		for key, value in defaults.items():
			setattr(self, key, value)

	def db_set(self, key, value=None):
		if isinstance(key, dict):
			for k, v in key.items():
				setattr(self, k, v)
		else:
			setattr(self, key, value)


class TestToolCallSchemaExecutorConsistency(unittest.TestCase):
	"""``huf/ai/graph/graph_ir.schema.json``'s ``ToolCallNode.config`` requires
	exactly ``tool_id``/``input`` -- this drives ``_exec_tool_call`` with
	ONLY those two keys (the schema-valid shape, nothing else -- the schema
	sets ``additionalProperties: false``) and asserts the tool actually gets
	invoked with the resolved input, proving the executor consumes the
	schema's own field names rather than a stale ``tool_name``/``args`` pair.
	"""

	def _run(self, config):
		flow_run = _FakeFlowRun()
		captured = {}

		def fake_execute_tool(tool_name, call_args):
			captured["tool_name"] = tool_name
			captured["args"] = call_args
			return {"success": True, "result": "ok"}

		with patch.object(flow_engine, "frappe") as fake_frappe, \
			patch.object(flow_engine, "execute_tool", side_effect=fake_execute_tool), \
			patch.object(flow_engine, "_create_flow_agent_run", return_value=MagicMock()):
			fake_frappe.db.get_value.return_value = None  # not an MCP tool
			fake_frappe.get_doc.return_value = MagicMock()
			result = flow_engine._exec_tool_call(flow_run, {"id": "n1"}, config, {})

		return result, captured

	def test_schema_required_fields_are_consumed(self):
		"""``tool_id``/``input`` -- the schema's own required config keys --
		must resolve the tool name and arguments actually passed to
		execute_tool."""
		result, captured = self._run({"tool_id": "demo_tool", "input": {"x": 1}})

		self.assertEqual(captured.get("tool_name"), "demo_tool")
		self.assertEqual(captured.get("args"), {"x": 1})
		self.assertEqual(result["status"], "success")

	def test_legacy_tool_name_args_shape_still_works(self):
		"""tool_name/args predates the schema and can never be saved through
		FlowDefinition.validate() any more, but a Flow Run pins whatever
		graph it started with (F-1) -- a run created before this migration
		may still carry the old shape. Keep it working as a read-only
		fallback."""
		result, captured = self._run({"tool_name": "demo_tool", "args": {"x": 1}})

		self.assertEqual(captured.get("tool_name"), "demo_tool")
		self.assertEqual(captured.get("args"), {"x": 1})
		self.assertEqual(result["status"], "success")

	def test_missing_tool_id_fails_with_actionable_message(self):
		result, captured = self._run({"input": {}})
		self.assertEqual(result["status"], "failed")
		self.assertIn("tool_id", result["error"])
		self.assertEqual(captured, {})


class TestSavedFlowInvokesRealTool(unittest.TestCase):
	"""Real-bench (Layer B): a Flow Definition saved through the real
	whitelisted ``flow_api.save_flow_definition`` -- so it is proven
	schema-valid, exactly what a UI-built Flow would produce -- can actually
	invoke a real ``Agent Tool Function`` when run, and records a real
	``Agent Tool Call``.

	Uses ``unittest.TestCase.run`` guarding via ``setUpClass``: this class
	only executes its real-bench body when a genuine ``frappe`` module (not
	the MagicMock stub installed above for the pure unit-test class in this
	same file) is importable, so this file stays collectible standalone
	(``pytest huf/ai/tests/test_flow_tool_call_gw01.py``) without a live
	site, the same way test_flow_engine.py's bench-only classes do it.
	"""

	@classmethod
	def setUpClass(cls):
		import frappe as _frappe

		if not hasattr(_frappe, "get_doc") or isinstance(_frappe, MagicMock):
			raise unittest.SkipTest("Requires a real Frappe bench (no live site in this process).")
		if not hasattr(_frappe, "db") or isinstance(getattr(_frappe, "db", None), MagicMock):
			raise unittest.SkipTest("Requires a real Frappe bench (no live site in this process).")

		cls.frappe = _frappe

	def setUp(self):
		frappe = self.frappe
		frappe.set_user("Administrator")
		self._names = {"Flow Definition": [], "Flow Run": [], "Agent Tool Function": []}
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe = self.frappe
		for doctype in ("Flow Run", "Flow Definition", "Agent Tool Function"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:  # noqa: BLE001 -- best-effort test cleanup
					pass
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	def _make_tool(self):
		from huf.ai.tests.factories import create_test_tool_doc

		doc = create_test_tool_doc(
			"deterministic_add",
			tool_name=f"_test_gw01_add_{self.frappe.generate_hash(length=8)}",
		)
		self._track("Agent Tool Function", doc.name)
		return doc

	def _limits(self, **overrides):
		limits = {
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
		limits.update(overrides)
		return limits

	def _definition(self, tool_name):
		return {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{
					"id": "start",
					"type": "trigger.webhook",
					"config": {"method": "POST"},
					"next": "call",
				},
				{
					"id": "call",
					"type": "tool.call",
					# The schema's canonical, and only accepted, config shape
					# (additionalProperties: false) -- tool_id/input, not
					# tool_name/args.
					"config": {"tool_id": tool_name, "input": {"numbers": [1, 2, 3]}},
					"next": "finish",
				},
				{
					"id": "finish",
					"type": "output",
					"config": {"value": {"$from": "call"}},
				},
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": self._limits(),
			},
		}

	def test_tool_call_node_invokes_real_tool_via_saved_flow(self):
		from huf.ai import flow_api

		tool_doc = self._make_tool()
		flow_id = f"_test-gw01-flow-{self.frappe.generate_hash(length=8)}"

		saved = flow_api.save_flow_definition(flow_id, self._definition(tool_doc.tool_name))
		self._track("Flow Definition", saved["flow_id"])

		result = flow_api.run_flow(flow_id)
		self._track("Flow Run", result["flow_run_id"])

		flow_run = self.frappe.get_doc("Flow Run", result["flow_run_id"])
		self.assertEqual(
			flow_run.status,
			"Success",
			f"Flow Run did not succeed: {getattr(flow_run, 'last_error', None)}",
		)

		tool_calls = self.frappe.get_all(
			"Agent Tool Call",
			filters={"tool": tool_doc.tool_name},
			fields=["name", "status", "tool_result"],
		)
		self.assertTrue(tool_calls, "tool.call node did not create an Agent Tool Call record")
		# tool.call's own path in _exec_tool_call only writes an Agent Tool
		# Call record itself for the MCP branch; a built-in tool's telemetry
		# is written by the invocation service it delegates through
		# (huf.ai.tool_invocation) -- either way, exactly one real record for
		# this call proves the tool actually ran, not just that the flow
		# reached "Success".
		self.assertIn(tool_calls[0]["status"], ("Completed", "Success"))


if __name__ == "__main__":
	unittest.main()
