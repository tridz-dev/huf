"""Flow-level ``error_handler``: runs once after an unrouted failure; the run still ends Failed."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.runs import park
from huf.ai.graph.executor import GraphContext, NullListener, PinnedVersion


class _Run:
	flow_id = "f"
	name = "FR"
	context_json = "{}"
	status = "Running"
	hop_count = 0
	max_hops = None
	current_node_id = None

	def db_set(self, key, value=None, *a, **k):
		setattr(self, key, value)


def _stop(node_id, message):
	return {"id": node_id, "type": "stop", "config": {"message": message}}


def _graph(handler_ends="output", with_handler=True):
	graph = {
		"entry": "boom",
		"nodes": [
			_stop("boom", "Step blew up"),
			_stop("cleanup", "Cleaned up") if handler_ends == "stop" else {"id": "cleanup", "type": "output", "config": {"value": "Cleaned up"}},
		],
		"edges": [],
	}
	if with_handler:
		graph["error_handler"] = {"next": "cleanup"}
	return graph


def _run(graph):
	flow_run = _Run()
	flow_run.current_node_id = graph["entry"]
	version = PinnedVersion.pin(graph)
	ctx = flow_engine.FlowRunContext(
		{}, flow_run=flow_run, version=version, context=GraphContext({}, run_id="FR")
	)
	nodes_map = {n["id"]: n for n in graph["nodes"]}
	calls = {"fail": [], "complete": 0, "seen_error": None}
	origs = {t: flow_engine._NODE_EXECUTORS[t] for t in ("stop", "output")}

	def spy_for(node_type):
		def spy(fr, node, config, settings):
			if node["id"] == "cleanup":
				calls["seen_error"] = settings.context.data.get("error")
			return origs[node_type](fr, node, config, settings)

		return spy

	with (
		patch.object(flow_engine, "_fail_flow_run", lambda fr, msg: calls["fail"].append(msg)),
		patch.object(flow_engine, "_complete_flow_run", lambda *a, **k: calls.__setitem__("complete", 1)),
		patch.object(flow_engine, "_persist_context", lambda *a, **k: None),
		patch.object(flow_engine, "_publish_flow_event", lambda *a, **k: None),
		patch.dict(flow_engine._NODE_EXECUTORS, {"stop": spy_for("stop"), "output": spy_for("output")}),
		patch.object(flow_engine, "_FlowEventListener", lambda fr: NullListener()),
		patch.object(flow_engine, "_FlowStateStore", lambda fr: _MemStore()),
	):
		flow_engine._execute_loop(flow_run, nodes_map, flow_engine.effective_edges(graph), ctx)
	return calls


class _MemStore:
	def save_cursor(self, cursor):
		pass

	def save_hop_count(self, n):
		pass

	def __getattr__(self, name):
		return lambda *a, **k: None


class TestFlowErrorHandler(unittest.TestCase):
	def test_handler_runs_on_failure(self):
		calls = _run(_graph())
		self.assertEqual(calls["seen_error"], {"node_id": "boom", "message": calls["fail"][0]})
		self.assertIn("Step blew up", calls["seen_error"]["message"])

	def test_run_status_failed_after_handler(self):
		calls = _run(_graph("output"))
		self.assertEqual(len(calls["fail"]), 1)
		self.assertEqual(calls["complete"], 0)

	def test_handler_failure_not_recursive(self):
		calls = _run(_graph("stop"))
		self.assertEqual(len(calls["fail"]), 1)
		self.assertIn("Step blew up", calls["fail"][0])

	def test_no_handler_unchanged(self):
		calls = _run(_graph(with_handler=False))
		self.assertIsNone(calls["seen_error"])
		self.assertEqual(len(calls["fail"]), 1)


def _end(node_id, as_, message, nxt=None):
	"""A failing ``stop`` step (``as_="error"``) or an ``output`` step that lets the run finish."""
	if as_ == "error":
		node = {"id": node_id, "type": "stop", "config": {"message": message}}
	else:
		node = {"id": node_id, "type": "output", "config": {"value": message}}
	if nxt:
		node["next"] = nxt
	return node


_WAIT = {"mode": "resume", "resume": {"wait_for": "token"}}


class TestParkedErrorHandler(IntegrationTestCase):
	"""Real runs: a handler chain that parks and later resumes still ends the run Failed."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-errh-{frappe.generate_hash(length=8)}",
				"flow_name": "Error Handler Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "boom", "type": "stop"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.runs = []
		self.events = []
		real = flow_engine._publish_flow_event

		def spy(fr, event, data=None, *a, **k):
			self.events.append((event, data))
			return real(fr, event, data, *a, **k)

		p = patch.object(flow_engine, "_publish_flow_event", side_effect=spy)
		p.start()
		self.addCleanup(p.stop)

	def tearDown(self):
		for name in self.runs:
			frappe.delete_doc("Flow Run", name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _start(self, nodes, entry, handler="hw"):
		graph = {"entry": entry, "nodes": nodes, "edges": [], "error_handler": {"next": handler}}
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
				"current_node_id": entry,
				"pinned_definition": PinnedVersion.pin(graph).to_json(),
			}
		).insert(ignore_permissions=True)
		self.runs.append(run.name)
		return run.name

	def _row(self, name):
		return frappe.db.get_value("Flow Run", name, ["status", "last_error"], as_dict=True)

	def _go(self, name):
		flow_engine.run_flow(name)
		return self._row(name)

	def _wake_and_go(self, name):
		with patch("frappe.enqueue"):
			self.assertTrue(park.wake_run(name, "token"))
		return self._go(name)

	def _handler_graph(self, after="error"):
		return [
			_end("boom", "error", "Step blew up"),
			{"id": "hw", "type": "wait", "next": "hend", "config": _WAIT},
			_end("hend", after, "Handler ended"),
		]

	def test_parked_handler_ends_failed(self):
		name = self._start(self._handler_graph("success"), "boom")
		self.assertTrue(self._go(name).status.startswith("Waiting"))
		row = self._wake_and_go(name)
		self.assertEqual(row.status, "Failed")
		self.assertIn("Step blew up", row.last_error)
		self.assertNotIn("flow_completed", [e for e, _ in self.events])

	def test_handler_fails_after_park_keeps_original_error(self):
		name = self._start(self._handler_graph("error"), "boom")
		self._go(name)
		row = self._wake_and_go(name)
		self.assertEqual(row.status, "Failed")
		self.assertIn("Step blew up", row.last_error)
		self.assertNotIn("Handler ended", row.last_error)

	def test_handler_fails_first_pass_keeps_original_error(self):
		nodes = [_end("boom", "error", "Step blew up"), _end("hw", "error", "Handler ended")]
		row = self._go(self._start(nodes, "boom"))
		self.assertEqual(row.status, "Failed")
		self.assertIn("Step blew up", row.last_error)

	def test_cancel_while_handler_parked_stays_cancelled(self):
		name = self._start(self._handler_graph("success"), "boom")
		self._go(name)
		frappe.db.set_value("Flow Run", name, "status", "Cancelled")
		self.assertEqual(self._go(name).status, "Cancelled")

	def test_no_handler_wait_then_success_regression(self):
		nodes = [
			{"id": "w", "type": "wait", "next": "ok", "config": _WAIT},
			_end("ok", "success", "Done"),
		]
		graph = {"entry": "w", "nodes": nodes, "edges": []}
		name = self._start(nodes, "w", handler="none")
		frappe.db.set_value("Flow Run", name, "pinned_definition", PinnedVersion.pin(graph).to_json())
		self.assertTrue(self._go(name).status.startswith("Waiting"))
		self.assertEqual(self._wake_and_go(name).status, "Success")

	def test_user_error_variable_does_not_fail_run(self):
		nodes = [
			{"id": "s", "type": "transform", "next": "ok", "config": {}},
			_end("ok", "success", "Done"),
		]
		graph = {"entry": "s", "nodes": nodes, "edges": []}
		name = self._start(nodes, "s", handler="none")
		frappe.db.set_value("Flow Run", name, "pinned_definition", PinnedVersion.pin(graph).to_json())


		def writer(fr, node, config, settings):
			settings.context.set("error", "just a note")
			return {"status": "success", "output": {}, "next_node_id": "ok"}

		with patch.dict(flow_engine._NODE_EXECUTORS, {"transform": writer}):
			self.assertEqual(self._go(name).status, "Success")

	def test_parked_handler_flow_error_event_once(self):
		name = self._start(self._handler_graph("error"), "boom")
		self._go(name)
		row = self._wake_and_go(name)
		errors = [d["error"] for e, d in self.events if e == "flow_error"]
		self.assertTrue(errors)
		self.assertNotIn("Handler ended", row.last_error)
		self.assertIn("Step blew up", row.last_error)


if __name__ == "__main__":
	unittest.main()
