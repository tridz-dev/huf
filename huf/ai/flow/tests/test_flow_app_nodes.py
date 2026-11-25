"""App-registered Flow step types (``huf_flow_nodes``, flow/catalog/node_registry.py).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_app_nodes
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.catalog import node_registry
from huf.ai.flow.runs import park
from huf.ai.graph.validator import get_flow_node_types, validate_graph
from huf.ai.flow.tests.test_flow_draft_validation import _graph, _trigger

M = "huf.ai.flow.tests.test_flow_app_nodes"
CALLS = []


def echo(ctx):
	CALLS.append(ctx)
	return {"status": "success", "output": {"got": ctx.config.get("text")}, "next_node_id": None}


def boom(ctx):
	raise RuntimeError("kaboom")


def boom_plain(ctx):
	raise ValueError("boom")


def boom_timeout(ctx):
	raise TimeoutError("slow")


def boom_validation(ctx):
	raise frappe.ValidationError("Customer is required")


def boom_empty(ctx):
	raise RuntimeError()


def waiter(ctx):
	if ctx.is_resume:
		CALLS.append("resumed")
		return {"status": "success", "output": {"reason": ctx.waiting["woke"]["reason"]}}
	return ctx.park(resume_at=None, token=True)


def check(node):
	return ["bad text"] if node["config"].get("text") == "bad" else []


def _entry(type_id, handler=f"{M}.echo", **kw):
	return {
		"type": type_id,
		"label": "Demo",
		"handler": handler,
		"config_schema": {
			"type": "object",
			"required": ["text"],
			"properties": {"text": {"type": "string"}},
			"additionalProperties": False,
		},
		**kw,
	}


class TestAppNodes(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		CALLS.clear()
		self.entries = []
		real = frappe.get_hooks

		def fake(hook=None, *a, **k):
			if hook == "huf_flow_nodes":
				return list(self.entries) if k.get("app_name") == "huf" else []
			return real(hook, *a, **k)

		p = patch("frappe.get_hooks", side_effect=fake)
		p.start()
		self.addCleanup(p.stop)
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-app-{frappe.generate_hash(length=8)}",
				"flow_name": "App Node Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "n1", "type": "huf.demo"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.run_doc = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Agent Flow Run", self.run_doc.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _node(self, type_id="huf.demo", **config):
		return {"id": "n1", "type": type_id, "next": "n2", "config": config}

	def _exec(self, node):
		return flow_engine._execute_node(self.run_doc, node, {})

	def test_registered_type_runs_end_to_end(self):
		self.entries = [_entry("huf.demo")]
		self.assertIn("huf.demo", get_flow_node_types())
		out = self._exec(self._node(text="hi"))
		self.assertEqual(out["output"], {"got": "hi"})
		graph = _graph([_trigger("n1"), {"id": "n1", "type": "huf.demo", "config": {"text": "hi"}}])
		self.assertTrue(validate_graph(graph, "flow").ok)

	def test_undeclared_handler_refused(self):
		# a flow cannot name code: a type nobody declared is simply unknown, whatever its config says
		self.entries = [_entry("huf.demo")]
		node = self._node("huf.ghost", handler=f"{M}.boom", text="x")
		self.assertNotIn("huf.ghost", node_registry.registered_types())
		self.assertEqual(self._exec(node)["status"], "failed")
		self.assertEqual(CALLS, [])
		graph = _graph([_trigger("n1"), {"id": "n1", "type": "huf.ghost", "config": {"text": "x"}}])
		self.assertFalse(validate_graph(graph, "flow").ok)

	def test_unnamespaced_or_colliding_id_refused(self):
		self.entries = [_entry("demo"), _entry("other.demo"), _entry("tool.call"), _entry("huf.")]
		self.assertEqual(node_registry.registered_types(), {})

	def test_config_schema_violation_blocks_publish(self):
		self.entries = [_entry("huf.demo", validate=f"{M}.check")]
		for config in ({}, {"text": 5}, {"text": "ok", "extra": 1}, {"text": "bad"}):
			graph = _graph([_trigger("n1"), {"id": "n1", "type": "huf.demo", "config": config}])
			self.assertFalse(validate_graph(graph, "flow").ok, config)

	def test_can_wait_node_parks_and_resumes_once(self):
		self.entries = [_entry("huf.demo", handler=f"{M}.waiter", can_wait=True)]
		node = self._node(text="x")
		out = self._exec(node)
		self.assertTrue(out.is_paused)
		self.assertEqual(frappe.db.get_value("Agent Flow Run", self.run_doc.name, "status"), "Waiting Timer")
		with patch("frappe.enqueue"):
			self.assertTrue(park.wake_run(self.run_doc.name, "resumed"))
			self.assertFalse(park.wake_run(self.run_doc.name, "resumed"))
		self.run_doc.reload()
		out = self._exec(node)
		self.assertEqual(out["output"], {"reason": "resumed"})
		self.assertEqual(CALLS.count("resumed"), 1)

	def test_uninstalled_app_run_fails_clearly(self):
		self.entries = []
		out = self._exec(self._node("huf.demo", text="x"))
		self.assertEqual(out["status"], "failed")
		self.assertIn("no longer available", out["error"])

	def test_handler_exception_wrapped(self):
		self.entries = [_entry("huf.demo", handler=f"{M}.boom")]
		out = self._exec(self._node(text="x"))
		self.assertEqual(out["status"], "failed")
		self.assertIn("kaboom", out["error"])

	def _fail_text(self, fn):
		self.entries = [_entry("huf.demo", handler=f"{M}.{fn}")]
		return self._exec(self._node(text="x"))["error"]

	def test_app_step_valueerror_plain(self):
		err = self._fail_text("boom_plain")
		self.assertEqual(err, "Demo failed: boom")
		self.assertNotIn("ValueError", err)
		self.assertTrue(frappe.db.exists("Error Log", {"method": "Flow app step huf.demo raised"}))

	def test_app_step_timeout_standard_sentence(self):
		self.assertIn("took too long", self._fail_text("boom_timeout"))

	def test_app_step_validation_message_kept(self):
		self.assertIn("Customer is required", self._fail_text("boom_validation"))

	def test_app_step_empty_message_standard_sentence(self):
		err = self._fail_text("boom_empty")
		self.assertTrue(err.startswith("Demo failed:"))
		self.assertNotIn("RuntimeError", err)

	def test_self_routed_outputs(self):
		self.entries = [_entry("huf.demo", routing="self_routed", outputs=["a", "b"]), _entry("huf.term", routing="terminal")]
		builtin = flow_engine.NODE_ROUTING
		self.assertEqual(node_registry.routing_for("huf.demo", builtin), "self_routed")
		self.assertEqual(node_registry.routing_for("huf.term", builtin), "terminal")
		self.assertEqual(node_registry.routing_for("wait", builtin), "self_routed")
		self.assertEqual(node_registry.get_type("huf.demo").outputs, ["a", "b"])

	def test_flow_only_profile(self):
		self.entries = [_entry("huf.demo")]
		graph = _graph([_trigger("n1"), {"id": "n1", "type": "huf.demo", "config": {"text": "hi"}}])
		graph["profile"] = "procedure"
		self.assertFalse(validate_graph(graph, "procedure").ok)
		self.assertNotIn("huf.demo", validate_graph.__globals__["PROCEDURE_NODE_TYPES"])

	def test_test_run_skips_side_effects(self):
		self.entries = [_entry("huf.demo")]
		self.run_doc.run_mode = "Test"
		with patch("huf.ai.flow.testrun.gate.is_test_run", return_value=True):
			out = self._exec(self._node(text="x"))
		self.assertEqual(out["status"], "success")
		self.assertEqual(CALLS, [])
