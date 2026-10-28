# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Field-contract tests for the Flow profile of the graph IR (docs/flow/FIELD_CONTRACT.md).

Validates the canonical example extracted from the contract doc, a minimal example of every
trigger / node type, and negative cases (the legacy names the Flow UI used to emit).

Runs with plain pytest and no bench: ``frappe`` is replaced by an auto-stub only when the real
package is not importable, and ``classify_tool`` is always a fake, so the real
``validate_flow_graph`` (jsonschema + structural checks) is exercised end to end.

  python -m pytest huf/ai/graph/tests/test_flow_field_contract.py
"""

import copy
import importlib.abc
import importlib.machinery
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def _install_frappe_stub_if_missing():
	try:
		import frappe  # noqa: F401

		return
	except ImportError:
		pass

	class _Loader(importlib.abc.Loader):
		def create_module(self, spec):
			module = MagicMock(name=spec.name)
			module.__path__ = []
			module.__spec__ = spec
			module.__name__ = spec.name
			return module

		def exec_module(self, module):
			pass

	class _Finder(importlib.abc.MetaPathFinder):
		def find_spec(self, name, path, target=None):
			if name == "frappe" or name.startswith("frappe."):
				return importlib.machinery.ModuleSpec(name, _Loader(), is_package=True)
			return None

	sys.meta_path.insert(0, _Finder())


_install_frappe_stub_if_missing()

from huf.ai.graph.permissions import ToolPermission  # noqa: E402
from huf.ai.graph.validator import validate_flow_graph  # noqa: E402

DOC = Path(__file__).resolve().parents[4] / "docs" / "flow" / "FIELD_CONTRACT.md"

LIMITS = {
	"max_nodes": 50,
	"max_rows": 10000,
	"max_output_bytes": 1000000,
	"max_parallel_calls": 4,
	"max_foreach_iterations": 200,
	"max_external_calls": 100,
	"max_writes": 10,
	"max_wall_time_ms": 60000,
	"fail_closed": True,
}


def _classify(tool_id):
	return ToolPermission(
		ptype=None,
		doctype=None,
		http=tool_id == "http_request",
		code=tool_id == "run_python",
	)


def _validate(graph):
	return validate_flow_graph(graph, classify_tool=_classify)


def _canonical():
	text = DOC.read_text(encoding="utf-8")
	match = re.search(r"## 5\. Canonical example.*?```json\n(.*?)\n```", text, re.S)
	assert match, "canonical example not found in FIELD_CONTRACT.md"
	return json.loads(match.group(1))


def _graph(nodes, entry, http=(), code=(), write=()):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "b" * 64,
		"entry": entry,
		"nodes": nodes,
		"contract": {
			"input_schema": {},
			"output_schema": {},
			"applies_when": [],
			"permission_envelope": {
				"read": [],
				"write": [{"doctype": d} for d in write],
				"http": list(http) or "none",
				"code": list(code) or "none",
			},
			"limits": dict(LIMITS),
		},
	}


WEBHOOK = {"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "s3cret-value"}, "next": "x"}
OUT = {"id": "end", "type": "output", "config": {"value": "ok"}}


def _wrap(node, extra=(), **kw):
	"""webhook -> node(id x) -> end, plus any extra top-level nodes."""
	node = dict(node, id="x")
	if "next" not in node and node["type"] not in {"condition", "router.llm", "router.decision", "human.approval", "output"}:
		node["next"] = "end"
	return _graph([WEBHOOK, node, *extra, OUT], "t", **kw)


def _tool(tool_id, inp, **kw):
	return {"type": "tool.call", "config": {"tool_id": tool_id, "input": inp}, **kw}


# Minimal valid example per type: name -> graph
def _minimal_examples():
	ex = {}
	ex["trigger.webhook"] = _wrap(_tool("gmail_send_email", {}))
	ex["trigger.schedule"] = _graph(
		[{"id": "t", "type": "trigger.schedule", "config": {"cron": "0 9 * * 1"}, "next": "end"}, OUT], "t"
	)
	ex["trigger.doc-event"] = _graph(
		[{"id": "t", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "on_update"}, "next": "end"}, OUT],
		"t",
	)
	ex["agent.run"] = _wrap({"type": "agent.run", "config": {"agent": "a1", "prompt": "hi"}})
	ex["tool.call"] = _wrap(_tool("some_tool", {"a": 1}))
	ex["email"] = _wrap(_tool("gmail_send_email", {"to": "a@b.c", "subject": "s", "body": "b"}))
	ex["slack"] = _wrap(_tool("slack_send_message", {"channel": "#c", "text": "t"}))
	ex["sheets"] = _wrap(_tool("gsheets_read", {"spreadsheet_id": "1"}))
	ex["file"] = _wrap(_tool("gdrive_list_files", {}))
	ex["http"] = _wrap(_tool("http_request", {"url": "https://e.com"}), http=["http_request"])
	ex["code"] = _wrap(_tool("run_python", {"code": "print(1)"}), code=["run_python"])
	ex["transform"] = _wrap({"type": "transform", "config": {"op": "trim", "input": {"text": {"$from": "trigger"}}}})
	ex["condition"] = _wrap(
		{"type": "condition", "config": {"expression": "input['a'] > 1", "on_true": "end", "on_false": "end2"}},
		extra=[{"id": "end2", "type": "output", "config": {"value": "no"}}],
	)
	ex["router.llm"] = _wrap(
		{"type": "router.llm", "config": {"prompt": "pick", "options": [{"label": "a", "node_id": "end"}], "default": "end2"}},
		extra=[{"id": "end2", "type": "output", "config": {"value": "d"}}],
	)
	ex["router.decision"] = _wrap(
		{"type": "router.decision", "config": {"policy": "p1", "options": [{"label": "a", "node_id": "end"}], "default": "end2"}},
		extra=[{"id": "end2", "type": "output", "config": {"value": "d"}}],
	)
	ex["human.approval"] = _wrap(
		{
			"type": "human.approval",
			"config": {
				"message": "ok?",
				"approve_next": "end",
				"reject_next": "end2",
				"approver_type": "role",
				"approver_role": "Sales Manager",
			},
		},
		extra=[{"id": "end2", "type": "output", "config": {"value": "r"}}],
	)
	ex["human.approval+role"] = _wrap(
		{
			"type": "human.approval",
			"config": {
				"message": "ok?",
				"approve_next": "end",
				"reject_next": "end2",
				"approver_type": "role",
				"approver_role": "System Manager",
			},
		},
		extra=[{"id": "end2", "type": "output", "config": {"value": "r"}}],
	)
	ex["human.approval+users"] = _wrap(
		{
			"type": "human.approval",
			"config": {
				"message": "ok?",
				"approve_next": "end",
				"reject_next": "end2",
				"approver_type": "user",
				"approver_users": ["a@b.c"],
			},
		},
		extra=[{"id": "end2", "type": "output", "config": {"value": "r"}}],
	)
	ex["foreach"] = _wrap(
		{
			"type": "foreach",
			"config": {
				"items": {"$from": "input.rows"},
				"body": ["b1"],
				"max_iterations": 10,
				"on_item_error": "fail",
				"collect": {"$from": "b1"},
			},
		},
		extra=[{"id": "b1", **_tool("slack_send_message", {"channel": "c", "text": {"$from": "foreach.item"}})}],
	)
	ex["validate"] = _wrap(
		{"type": "validate", "config": {"assertions": [{"expression": "input['a'] == 1", "code": "C", "message": "m"}]}}
	)
	ex["state.get"] = _wrap({"type": "state.get", "config": {"key": "k"}})
	ex["state.set"] = _wrap({"type": "state.set", "config": {"key": "k", "value": 1}})
	ex["state.delete"] = _wrap({"type": "state.delete", "config": {"key": "k"}})
	ex["doc.create"] = _wrap({"type": "doc.create", "config": {"doctype": "ToDo", "fields": {"description": "d"}}}, write=["ToDo"])
	ex["output"] = _graph([WEBHOOK | {"next": "x"}, {"id": "x", "type": "output", "config": {"value": {"$from": "input.a"}}}], "t")
	ex["trigger.unset"] = _graph([{"id": "t", "type": "trigger.unset", "config": {}, "next": "end"}, OUT], "t")
	return ex


def _wrap_parallel():
	return _wrap(
		{"type": "parallel", "config": {"branches": [["p1"], ["p2"]], "join": "all"}},
		extra=[
			{"id": "p1", **_tool("slack_send_message", {"channel": "c", "text": "a"})},
			{"id": "p2", **_tool("slack_send_message", {"channel": "c", "text": "b"})},
		],
	)


def _errs(graph):
	result = _validate(graph)
	return result, "; ".join(str(e) for e in result.errors)


class TestFlowFieldContract(unittest.TestCase):
	def test_canonical_example_valid(self):
		result, msg = _errs(_canonical())
		self.assertTrue(result.ok, msg)

	def test_canonical_covers_every_ui_type(self):
		types = {n["type"] for n in _canonical()["nodes"]}
		self.assertTrue(
			{
				"trigger.webhook", "trigger.schedule", "trigger.doc-event", "agent.run", "tool.call", "router.llm",
				"condition", "foreach", "human.approval", "transform", "output",
			}
			<= types
		)
		tool_ids = {n["config"]["tool_id"] for n in _canonical()["nodes"] if n["type"] == "tool.call"}
		self.assertTrue(
			{"gmail_send_email", "http_request", "slack_send_message", "gsheets_read", "gdrive_list_files", "run_python"} <= tool_ids
		)

	def test_each_minimal_example_valid(self):
		for name, graph in _minimal_examples().items():
			with self.subTest(name):
				result, msg = _errs(graph)
				self.assertTrue(result.ok, msg)

	# -- negatives: legacy / UI-emitted shapes must be rejected --------------------------------

	def _mutate(self, example, fn):
		graph = copy.deepcopy(_minimal_examples()[example])
		fn(graph)
		return graph

	def _node(self, graph, node_id):
		return next(n for n in graph["nodes"] if n["id"] == node_id)

	def assertRejected(self, graph, fragment=None):
		result, msg = _errs(graph)
		self.assertFalse(result.ok, "expected rejection")
		if fragment:
			self.assertIn(fragment, msg)

	def test_webhook_negatives(self):
		def cfg(g):
			return self._node(g, "t")["config"]

		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).pop("secret")))
		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).update(secret="short")))
		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).update(method="PUT")))
		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).update(method="DELETE")))
		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).update(auth="x")))
		self.assertRejected(self._mutate("trigger.webhook", lambda g: cfg(g).update(apiKey="x")))

	def test_schedule_negatives(self):
		def cfg(g):
			return self._node(g, "t")["config"]

		self.assertRejected(self._mutate("trigger.schedule", lambda g: cfg(g).pop("cron")))
		self.assertRejected(self._mutate("trigger.schedule", lambda g: cfg(g).update(timezone="UTC")))
		self.assertRejected(
			self._mutate("trigger.schedule", lambda g: (cfg(g).pop("cron"), cfg(g).update(intervalType="hours", interval=2)))
		)

	def test_doc_event_negatives(self):
		def cfg(g):
			return self._node(g, "t")["config"]

		self.assertRejected(self._mutate("trigger.doc-event", lambda g: cfg(g).update(event="on_delete")))
		self.assertRejected(self._mutate("trigger.doc-event", lambda g: cfg(g).update(filters={"a": 1})))
		self.assertRejected(self._mutate("trigger.doc-event", lambda g: cfg(g).pop("doctype")))

	def test_tool_call_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("email", lambda g: cfg(g).update(tool_name="gmail_send_email")))
		self.assertRejected(self._mutate("email", lambda g: cfg(g).update(args={})))
		self.assertRejected(self._mutate("email", lambda g: cfg(g).pop("tool_id")))
		self.assertRejected(self._mutate("email", lambda g: cfg(g).update(output={"save_result_to_context": "r"})))
		self.assertRejected(self._mutate("email", lambda g: cfg(g).update(mcp_server="s")))
		self.assertRejected(self._mutate("email", lambda g: cfg(g).update(tool_id={"$from": "input.t"})))

	def test_legacy_node_types_rejected(self):
		for legacy in ("http_request", "loop", "end", "code", "email", "slack", "sheets", "file"):
			with self.subTest(legacy):
				self.assertRejected(self._mutate("email", lambda g, t=legacy: self._node(g, "x").update(type=t)))

	def test_condition_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(
			self._mutate("condition", lambda g: (cfg(g).pop("on_true"), cfg(g).update(true_node="end")))
		)
		self.assertRejected(self._mutate("condition", lambda g: cfg(g).update(on_true="missing")))
		self.assertRejected(self._mutate("condition", lambda g: self._node(g, "x").update(next="end")))
		self.assertRejected(self._mutate("condition", lambda g: cfg(g).update(expression="input.a == 1")))

	def test_router_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("router.llm", lambda g: cfg(g).pop("default")))
		self.assertRejected(self._mutate("router.llm", lambda g: cfg(g).update(router_agent_name="a")))
		self.assertRejected(self._mutate("router.llm", lambda g: cfg(g).update(options=[])))

	def test_loop_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("foreach", lambda g: cfg(g).pop("collect")))
		self.assertRejected(self._mutate("foreach", lambda g: cfg(g).update(iterate_over="items")))
		self.assertRejected(self._mutate("foreach", lambda g: cfg(g).update(items="input.rows")))
		self.assertRejected(self._mutate("foreach", lambda g: cfg(g).update(body=[])))
		# a back-edge from the body to the loop is a cycle
		self.assertRejected(self._mutate("foreach", lambda g: self._node(g, "b1").update(next="x")))

	def test_human_approval_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("human.approval", lambda g: cfg(g).pop("message")))
		self.assertRejected(self._mutate("human.approval", lambda g: cfg(g).pop("reject_next")))
		self.assertRejected(self._mutate("human.approval", lambda g: cfg(g).update(title="t", instructions="i")))
		self.assertRejected(self._mutate("human.approval+role", lambda g: cfg(g).pop("approver_role")))
		self.assertRejected(self._mutate("human.approval+role", lambda g: cfg(g).update(approver_users=["a@b.c"])))
		self.assertRejected(self._mutate("human.approval+users", lambda g: cfg(g).update(approver_users=[])))
		self.assertRejected(self._mutate("human.approval+users", lambda g: cfg(g).update(approver_role="Sales")))

	def test_human_approval_requires_approver_type(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("human.approval", lambda g: cfg(g).pop("approver_type")))
		self.assertRejected(self._mutate("human.approval", lambda g: cfg(g).update(approver_type=None)))
		result = _validate(self._mutate("human.approval", lambda g: (cfg(g).pop("approver_type"), cfg(g).pop("approver_role"))))
		self.assertFalse(result.ok)
		from huf.ai.graph.error_copy import describe_errors

		text = describe_errors(None, result.errors)
		self.assertIn("who can approve is required", text)
		self.assertNotIn("[SCHEMA]", text)

	def test_router_llm_model_is_optional_string(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		result, msg = _errs(self._mutate("router.llm", lambda g: cfg(g).update(model="gpt-4o-mini")))
		self.assertTrue(result.ok, msg)
		self.assertRejected(self._mutate("router.llm", lambda g: cfg(g).update(model="")))
		self.assertRejected(self._mutate("router.llm", lambda g: cfg(g).update(model={"provider": "OpenAI"})))

	def test_tool_call_recovery_removed(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("slack", lambda g: cfg(g).update(recovery="retry")))

	def test_parallel_node_removed(self):
		graph = _wrap_parallel()
		result = _validate(graph)
		self.assertFalse(result.ok)
		from huf.ai.graph.error_copy import describe_errors

		text = describe_errors(graph, result.errors)
		self.assertIn("flows do not support", text)
		self.assertNotIn("[", text)

	def test_unreachable_node_copy(self):
		graph = self._mutate("slack", lambda g: g["nodes"].append({"id": "orphan", "type": "output", "config": {"value": 1}}))
		result = _validate(graph)
		self.assertFalse(result.ok)
		from huf.ai.graph.error_copy import describe_errors

		text = describe_errors(graph, result.errors)
		self.assertIn("not connected to the start of the flow", text)
		self.assertNotIn("UNREACHABLE", text)

	def test_transform_negatives(self):
		def cfg(g):
			return self._node(g, "x")["config"]

		self.assertRejected(self._mutate("transform", lambda g: cfg(g).update(op="nope")), "nope")
		self.assertRejected(
			self._mutate("transform", lambda g: (cfg(g).pop("op"), cfg(g).pop("input"), cfg(g).update(transformations=[])))
		)

	def test_output_negatives(self):
		self.assertRejected(self._mutate("output", lambda g: self._node(g, "x").update(next=None)))
		self.assertRejected(self._mutate("output", lambda g: self._node(g, "x").update(config={})))

	def test_envelope_and_envelope_free_http(self):
		# http tool without declared envelope is rejected
		g = _minimal_examples()["http"]
		g["contract"]["permission_envelope"]["http"] = "none"
		self.assertRejected(g, "http")

	def test_document_level_negatives(self):
		g = _minimal_examples()["email"]
		g["edges"] = []
		self.assertRejected(g)
		g = _minimal_examples()["email"]
		g["schema_version"] = 1
		self.assertRejected(g)
		g = _minimal_examples()["email"]
		self._node(g, "x")["id"] = "bad-id"
		self.assertRejected(g)


if __name__ == "__main__":
	unittest.main()
