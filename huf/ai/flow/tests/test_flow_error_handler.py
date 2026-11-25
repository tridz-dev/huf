"""Flow-level ``error_handler``: runs once after an unrouted failure; the run still ends Failed."""

import unittest
from unittest.mock import patch

from huf.ai.flow import engine as flow_engine
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


if __name__ == "__main__":
	unittest.main()
