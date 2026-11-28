"""Engine wiring of the W5 nodes (WIRE-W5-engine): router.decision, knowledge.search, handoff, the AI switch on
router.llm, the handed-off guard hook, the graph IR schema, per-run guard batches and the App trigger."""

import ast
import json
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.flow import engine
from huf.ai.flow.nodes import adapters
from huf.ai.graph.executor import RoutingMode
from huf.ai.run_budget import AIDisabled, RunBudget

_HUF = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LLM_CONFIG = {"prompt": "pick", "options": [{"label": "A", "node_id": "a"}], "default": "d"}


def _hook_values(name: str):
	tree = ast.parse(open(os.path.join(_HUF, "hooks.py"), encoding="utf-8").read())
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
			return ast.literal_eval(node.value)
	return None


def _schema() -> dict:
	with open(os.path.join(_HUF, "ai", "graph", "graph_ir.schema.json"), encoding="utf-8") as fh:
		return json.load(fh)


def _budget(**kw) -> RunBudget:
	budget = RunBudget(datetime.now() + timedelta(seconds=60), 10, 0, [], kw.pop("cap", 0.0))
	for key, value in kw.items():
		setattr(budget, key, value)
	return budget


class TestDispatch(unittest.TestCase):
	def test_router_decision_adapter_calls_the_decision_node(self):
		with patch("huf.ai.flow.nodes.router_decision.exec_router_decision", return_value={"status": "success"}) as run, \
			patch.object(adapters, "_ctx", return_value="ctx"):
			out = adapters.exec_router_decision("run", {"id": "r"}, {"decision": {}}, {})
		self.assertEqual(out, {"status": "success"})
		run.assert_called_once_with("run", {"id": "r"}, {"decision": {}}, {}, "ctx")

	def test_router_decision_decision_mode_routes_to_uncertain_when_ai_off(self):
		config = {"decision": {"candidates": [{"node_id": "a"}, {"node_id": "b"}], "uncertain_next": "u"}}
		with patch("huf.ai.run_budget.assert_ai_enabled", side_effect=AIDisabled("ai_disabled")), \
			patch.object(adapters, "_ctx", return_value=None):
			out = engine._NODE_EXECUTORS["router.decision"](None, {"id": "r"}, config, {})
		self.assertEqual((out["next_node_id"], out["output"]["reason"]), ("u", "ai_disabled"))

	def test_knowledge_search_and_handoff_are_registered(self):
		self.assertIn("knowledge.search", engine._NODE_EXECUTORS)
		self.assertIn("handoff", engine._NODE_EXECUTORS)
		self.assertEqual(engine.NODE_ROUTING["handoff"], RoutingMode.SELF_ROUTED)
		self.assertNotIn("knowledge.search", engine.NODE_ROUTING)

	def test_knowledge_search_gets_the_run_context(self):
		run_ctx = engine.FlowRunContext({})
		with patch("huf.ai.flow.nodes.knowledge.exec_knowledge_search", return_value={"status": "success"}) as run:
			engine._NODE_EXECUTORS["knowledge.search"](None, {"id": "k"}, {"query": "q"}, run_ctx)
		args = run.call_args.args
		self.assertIs(args[2], run_ctx.context)
		self.assertIs(args[3], run_ctx)

	def test_handoff_adapter_delegates(self):
		with patch("huf.ai.flow.nodes.handoff.exec_handoff", return_value={"status": "parked"}) as run:
			out = engine._NODE_EXECUTORS["handoff"]("run", {"id": "h"}, {}, {})
		self.assertEqual(out, {"status": "parked"})
		run.assert_called_once_with("run", {"id": "h"}, {}, {})

	def test_run_context_carries_agent_and_budget(self):
		run_ctx = engine.FlowRunContext({}, flow_run=SimpleNamespace(name="R1", agent="Helper"))
		self.assertEqual(run_ctx.agent, "Helper")
		budget = _budget()
		with patch("huf.ai.run_budget.peek_current_budget", return_value=budget):
			self.assertIs(run_ctx.budget, budget)
		self.assertIsNone(engine.FlowRunContext({}).agent)


class TestRouterLlmAiSwitch(unittest.TestCase):
	def _run(self, run_ctx=None, **patches):
		with patch.object(engine, "_router_completion") as completion, patch.object(
			engine, "resolve_router_model", return_value=("p", "m")
		):
			out = engine._exec_router_llm(None, {"id": "r"}, LLM_CONFIG, run_ctx or engine.FlowRunContext({}))
		return out, completion

	def test_switch_off_fails_with_ai_disabled_and_never_asks(self):
		with patch("huf.ai.run_budget.assert_ai_enabled", side_effect=AIDisabled("ai_disabled")):
			out, completion = self._run()
		self.assertEqual((out["status"], out["reason_code"]), ("failed", "ai_disabled"))
		completion.assert_not_called()

	def test_switch_check_error_fails_closed(self):
		with patch("huf.ai.run_budget.assert_ai_enabled", side_effect=RuntimeError("x")):
			out, completion = self._run()
		self.assertEqual(out["reason_code"], "ai_disabled")
		completion.assert_not_called()

	def test_spend_cap_used_up_fails(self):
		budget = _budget(cap=1.0, spend_so_far_usd=1.0)
		with patch("huf.ai.run_budget.assert_ai_enabled", return_value={}), patch(
			"huf.ai.run_budget.peek_current_budget", return_value=budget
		):
			out, completion = self._run()
		self.assertEqual(out["status"], "failed")
		completion.assert_not_called()

	def test_switch_on_asks_the_model(self):
		with patch("huf.ai.run_budget.assert_ai_enabled", return_value={}), patch(
			"huf.ai.run_budget.peek_current_budget", return_value=_budget(cap=5.0, spend_so_far_usd=1.0)
		), patch.object(engine, "_context_of") as ctx, patch.object(engine, "render_text_refs", return_value="p"), \
			patch.object(engine, "build_router_llm_prompt", return_value="prompt"):
			ctx.return_value.as_dict.return_value = {}
			with patch.object(engine, "_router_completion", return_value="A") as completion, patch.object(
				engine, "resolve_router_model", return_value=("p", "m")
			):
				out = engine._exec_router_llm(None, {"id": "r"}, LLM_CONFIG, engine.FlowRunContext({}))
		completion.assert_called_once()
		self.assertEqual((out["status"], out["next_node_id"]), ("success", "a"))


class TestHooks(unittest.TestCase):
	def test_handed_off_guard_is_a_pre_send_hook(self):
		self.assertIn("huf.ai.flow.nodes.handoff.handed_off_guard", _hook_values("huf_pre_send_hooks"))

	def test_handed_off_is_a_registered_reason_code(self):
		self.assertIn("handed_off", _hook_values("huf_flow_reason_codes"))
		from huf.ai.flow.nodes.handoff import BLOCK_REASON

		self.assertEqual(BLOCK_REASON, "handed_off")


class TestSchema(unittest.TestCase):
	def setUp(self):
		self.defs = _schema()["$defs"]

	def _flow_types(self) -> set:
		types = set()
		for entry in self.defs["FlowNode"]["oneOf"]:
			node_def = self.defs[entry["$ref"].rsplit("/", 1)[-1]]
			for part in node_def.get("allOf", []):
				const = ((part.get("properties") or {}).get("type") or {}).get("const")
				if const:
					types.add(const)
		return types

	def test_knowledge_search_and_handoff_are_flow_nodes(self):
		self.assertTrue({"knowledge.search", "handoff"} <= self._flow_types())

	def test_router_decision_accepts_decision_or_rules(self):
		config = self.defs["RouterDecisionNode"]["allOf"][1]["properties"]["config"]
		self.assertIn("decision", config["properties"])
		self.assertNotIn("required", config)
		self.assertIn({"required": ["decision"]}, config["anyOf"])
		self.assertIn({"required": ["options", "default"]}, config["anyOf"])

	def test_schema_validates_decision_only_config(self):
		try:
			import jsonschema
		except ImportError:
			self.skipTest("jsonschema not installed")
		config = self.defs["RouterDecisionNode"]["allOf"][1]["properties"]["config"]
		resolver_root = {"$defs": self.defs, **config}
		good = {"decision": {"candidates": [{"node_id": "a"}, {"node_id": "b"}], "uncertain_next": "u"}}
		jsonschema.validate(good, resolver_root)
		with self.assertRaises(jsonschema.ValidationError):
			jsonschema.validate({}, resolver_root)


class TestRunFlowBatch(unittest.TestCase):
	def test_execute_loop_runs_inside_a_guard_batch(self):
		from huf.ai.channels import guard_steps

		seen = []
		doc = SimpleNamespace(status="Queued", name="R1")
		with patch.object(engine, "_acquire_run_lock", return_value=True), patch.object(
			engine, "_release_run_lock"
		), patch.object(engine.frappe, "get_doc", return_value=doc), patch.object(
			engine, "_pinned_version", return_value=SimpleNamespace(graph={"nodes": []})
		), patch.object(engine, "effective_edges", return_value=[]), patch.object(
			engine, "_build_run_context", return_value=engine.FlowRunContext({})
		), patch.object(engine, "_transition_run", return_value=True), patch.object(
			engine, "commit_if_background"
		), patch.object(engine, "_execute_loop", side_effect=lambda *a: seen.append(guard_steps._BATCH.get())):
			engine.run_flow("R1")
		self.assertEqual(seen, [{}])
		self.assertIsNone(guard_steps._BATCH.get())


class TestAppTrigger(unittest.TestCase):
	def test_app_runs_start_at_the_app_trigger(self):
		self.assertEqual(engine.TRIGGER_NODE_TYPES["App"], "trigger.app")
		defn = {
			"entry": ["hook", "app"],
			"nodes": [{"id": "hook", "type": "trigger.webhook"}, {"id": "app", "type": "trigger.app"}],
		}
		self.assertEqual(engine.select_entry_node(defn, "App"), "app")

	def test_app_run_without_app_trigger_fails_closed(self):
		defn = {"entry": ["hook"], "nodes": [{"id": "hook", "type": "trigger.webhook"}]}
		with self.assertRaises(ValueError):
			engine.select_entry_node(defn, "App")
