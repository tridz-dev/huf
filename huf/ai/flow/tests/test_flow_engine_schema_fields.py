"""Engine executors read exactly the Flow schema field names (docs/flow/FIELD_CONTRACT.md).

Frappe-free: pure helpers and executors driven with fakes.
"""

import contextlib
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

if "frappe" not in sys.modules:
	sys.modules["frappe"] = MagicMock()

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext
from huf.ai.graph.templates import TemplateError


class _Run:
	name = "FR-1"
	flow_id = "f"
	conversation = None
	context_json = "{}"
	mode = "Normal"


class TestSelectEntryNode(unittest.TestCase):
	DEFN = {
		"entry": ["t_web", "t_cron", "t_doc"],
		"nodes": [
			{"id": "t_web", "type": "trigger.webhook", "config": {}},
			{"id": "t_cron", "type": "trigger.schedule", "config": {}},
			{"id": "t_doc", "type": "trigger.doc-event", "config": {}},
		],
	}

	def test_picks_the_trigger_matching_the_run_type(self):
		self.assertEqual(flow_engine.select_entry_node(self.DEFN, "Webhook"), "t_web")
		self.assertEqual(flow_engine.select_entry_node(self.DEFN, "Schedule"), "t_cron")
		self.assertEqual(flow_engine.select_entry_node(self.DEFN, "Doc Event"), "t_doc")

	def test_manual_and_gateway_use_first_entry(self):
		self.assertEqual(flow_engine.select_entry_node(self.DEFN, "Manual"), "t_web")
		self.assertEqual(flow_engine.select_entry_node(self.DEFN, "Gateway"), "t_web")

	def test_string_entry(self):
		defn = {"entry": "a", "nodes": [{"id": "a", "type": "transform", "config": {}}]}
		self.assertEqual(flow_engine.select_entry_node(defn, "Webhook"), "a")

	def test_missing_trigger_type_fails_closed(self):
		defn = {"entry": ["t"], "nodes": [{"id": "t", "type": "trigger.schedule", "config": {}}]}
		with self.assertRaises(ValueError):
			flow_engine.select_entry_node(defn, "Webhook")

	def test_no_entry_fails(self):
		with self.assertRaises(ValueError):
			flow_engine.select_entry_node({"entry": [], "nodes": []})


class TestEdgesFromNodes(unittest.TestCase):
	def test_schema_routing_fields(self):
		nodes = [
			{"id": "c", "type": "condition", "config": {"expression": "True", "on_true": "a", "on_false": "b"}},
			{
				"id": "r",
				"type": "router.llm",
				"config": {"prompt": "p", "options": [{"label": "x", "node_id": "a"}], "default": "b"},
			},
			{
				"id": "h",
				"type": "human.approval",
				"config": {"message": "m", "approve_next": "a", "reject_next": "b", "timeout_next": "c"},
			},
			{"id": "f", "type": "foreach", "config": {"body": ["a"]}, "next": "done"},
		]
		edges = flow_engine.edges_from_nodes(nodes)
		pairs = {(e["from"], e["to"]) for e in edges}
		self.assertTrue({("c", "a"), ("c", "b"), ("r", "a"), ("r", "b"), ("h", "a"), ("h", "b"), ("h", "c"), ("f", "done")} <= pairs)
		self.assertNotIn(("f", "a"), pairs)  # loop body is not an edge
		self.assertEqual(
			{e["meta"]["outcome"] for e in edges if e["from"] == "h"}, {"approved", "rejected", "timeout"}
		)

	def test_legacy_edges_key_is_ignored(self):
		defn = {"nodes": [{"id": "a", "type": "transform", "config": {}, "next": "b"}], "edges": [{"from": "x", "to": "y"}]}
		self.assertEqual([(e["from"], e["to"]) for e in flow_engine.effective_edges(defn)], [("a", "b")])


class TestAgentPrompt(unittest.TestCase):
	def test_prompt_bindings_fill_placeholders(self):
		ctx = GraphContext({"message": "hi"})
		ctx.record_output("n_prep", "HI")
		cfg = {"prompt": "Classify: {message} / {lit}", "prompt_bindings": {"message": {"$from": "n_prep"}, "lit": "x"}}
		self.assertEqual(flow_engine.render_agent_prompt(cfg, ctx), "Classify: HI / x")

	def test_unbound_placeholder_is_an_error(self):
		with self.assertRaises(TemplateError):
			flow_engine.render_agent_prompt({"prompt": "{nope}"}, GraphContext({}))

	def test_double_braces_are_not_variables(self):
		self.assertEqual(flow_engine.render_agent_prompt({"prompt": "{{name}}"}, GraphContext({})), "{name}")

	def test_agent_run_uses_agent_and_returns_response_as_output(self):
		captured = {}

		def fake_run_agent_sync(**kw):
			captured.update(kw)
			return {"success": True, "response": "done", "agent_run_id": "AR-1"}

		fake_mod = MagicMock(run_agent_sync=fake_run_agent_sync)
		run = MagicMock(name="run")
		run.name = "FR-1"
		with patch.dict(sys.modules, {"huf.ai.agent.integration": fake_mod}), \
			patch.object(flow_engine, "commit_if_background"):
			out = flow_engine._exec_agent_run(
				run, {"id": "n_agent"}, {"agent": "support", "prompt": "Hello {n}", "prompt_bindings": {"n": "Bob"}}, {}
			)
		self.assertEqual(captured["agent_name"], "support")
		self.assertEqual(captured["prompt"], "Hello Bob")
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["output"], "done")

	def test_agent_run_does_not_read_agent_name(self):
		out = flow_engine._exec_agent_run(_Run(), {"id": "n"}, {"agent_name": "x", "prompt": "p"}, {})
		self.assertEqual(out["status"], "failed")


class TestRouterLlm(unittest.TestCase):
	OPTIONS = [{"label": "urgent", "node_id": "n_human"}, {"label": "routine", "node_id": "n_loop"}]

	def test_choose_option_variants(self):
		pick = lambda t: (flow_engine.choose_option(t, self.OPTIONS) or {}).get("node_id")
		self.assertEqual(pick("urgent"), "n_human")
		self.assertEqual(pick("  Routine.\n"), "n_loop")
		self.assertEqual(pick('"urgent"'), "n_human")
		self.assertEqual(pick('{"label": "routine"}'), "n_loop")
		self.assertEqual(pick("I think this is urgent"), "n_human")
		self.assertIsNone(pick("urgent or routine"))  # ambiguous
		self.assertIsNone(pick("banana"))
		self.assertIsNone(pick(""))

	def _route(self, completion, config=None):
		cfg = {"prompt": "urgent?", "options": self.OPTIONS, "default": "n_loop"}
		cfg.update(config or {})
		with (
			patch.object(flow_engine, "resolve_router_model", side_effect=lambda m: ("OpenAI", m or "default-model")),
			patch.object(flow_engine, "_router_completion", side_effect=lambda p, prov, mod: completion(p)),
		):
			return flow_engine._exec_router_llm(_Run(), {"id": "r"}, cfg, {})

	def test_model_choice_routes_to_option_node(self):
		out = self._route(lambda p: "urgent")
		self.assertEqual(out["next_node_id"], "n_human")
		self.assertEqual(out["output"]["label"], "urgent")

	def test_no_match_goes_to_default(self):
		out = self._route(lambda p: "???")
		self.assertEqual(out["next_node_id"], "n_loop")
		self.assertEqual(out["status"], "success")

	def test_llm_failure_goes_to_default(self):
		def boom(p):
			raise RuntimeError("no provider")

		out = self._route(boom)
		self.assertEqual(out["next_node_id"], "n_loop")
		self.assertIn("no provider", out["output"]["reason"])

	def test_missing_default_or_options_fails(self):
		self.assertEqual(self._route(lambda p: "urgent", {"default": None})["status"], "failed")
		self.assertEqual(self._route(lambda p: "urgent", {"options": []})["status"], "failed")

	def test_text_refs_resolve_in_router_prompt_and_message(self):
		from huf.ai.graph.executor import GraphContext

		ctx = GraphContext({"amount": 150, "who": {"name": "Ada"}})
		ctx.node_outputs["n_prev"] = {"ok": True}
		render = flow_engine.render_text_refs
		self.assertEqual(render("Order {input.amount} by {input.who.name}", ctx), "Order 150 by Ada")
		self.assertEqual(render("Prev: {n_prev.ok}", ctx), "Prev: Yes")
		self.assertEqual(render("Keep {unknown.path} and {{input.amount}} as written", ctx), "Keep  and {{input.amount}} as written")  # unresolved: empty, never literal braces

	def test_router_agent_name_is_not_read(self):
		cfg = {"router_agent_name": "x", "options": self.OPTIONS, "default": "n_loop", "prompt": "p"}
		out = self._route(lambda p: "banana", cfg)
		self.assertEqual(out["next_node_id"], "n_loop")

	def test_explicit_model_is_used_and_recorded(self):
		out = self._route(lambda p: "urgent", {"model": "gpt-5.4-mini"})
		self.assertEqual(out["output"]["model"], "gpt-5.4-mini")
		self.assertEqual(out["output"]["provider"], "OpenAI")

	def test_no_model_uses_provider_default_and_records_it(self):
		out = self._route(lambda p: "urgent")
		self.assertEqual(out["output"]["model"], "default-model")

	def test_unusable_model_routes_to_default_with_reason(self):
		cfg = {"prompt": "p", "options": self.OPTIONS, "default": "n_loop", "model": "nope"}
		with patch.object(flow_engine, "resolve_router_model", side_effect=RuntimeError("AI model 'nope' was not found")):
			out = flow_engine._exec_router_llm(_Run(), {"id": "r"}, cfg, {})
		self.assertEqual(out["next_node_id"], "n_loop")
		self.assertIn("not found", out["output"]["reason"])
		self.assertEqual(out["output"]["model"], "nope")

	def test_empty_reply_is_reported_as_failure(self):
		out = self._route(lambda p: "")
		self.assertEqual(out["next_node_id"], "n_loop")
		self.assertIn("did not answer", out["output"]["reason"])

	def test_router_prompt_lists_labels(self):
		text = flow_engine.build_router_llm_prompt("is it?", self.OPTIONS, {"a": 1})
		self.assertIn("- urgent", text)
		self.assertIn("is it?", text)


class TestRouterDecision(unittest.TestCase):
	def test_disabled_provider_routes_to_default(self):
		cfg = {"policy": "p", "options": [{"label": "a", "node_id": "A"}], "default": "D"}
		out = flow_engine._exec_router_decision(_Run(), {"id": "r"}, cfg, {})
		self.assertEqual(out["next_node_id"], "D")


class TestTriggerExecutors(unittest.TestCase):
	def test_schedule_records_cron_only(self):
		run = _Run()
		run.db_set = lambda *a, **k: None
		with patch.object(flow_engine, "commit_if_background"):
			out = flow_engine._exec_trigger_schedule(run, {"id": "t"}, {"cron": "*/5 * * * *", "schedule_name": "legacy"}, {})
		self.assertEqual(out["schedule_info"]["cron"], "*/5 * * * *")
		self.assertNotIn("schedule_name", out["schedule_info"])
		self.assertNotIn("cron_expression", out["schedule_info"])


class TestNodeRegistry(unittest.TestCase):
	def test_legacy_node_types_are_gone(self):
		for legacy in ("loop", "end", "http_request"):
			self.assertNotIn(legacy, flow_engine._NODE_EXECUTORS)
		self.assertNotIn("loop", flow_engine.NODE_ROUTING)
		self.assertNotIn("end", flow_engine.NODE_ROUTING)

	def test_every_schema_flow_node_type_has_an_executor(self):
		for t in (
			"trigger.webhook", "trigger.schedule", "trigger.doc-event", "trigger.unset", "agent.run", "tool.call",
			"router.llm", "router.decision", "condition", "foreach", "human.approval", "transform", "output",
			"state.get", "state.set", "state.delete", "doc.create", "validate",
		):
			self.assertIn(t, flow_engine._NODE_EXECUTORS)

	def test_context_roundtrip_keeps_node_outputs_out_of_input(self):
		ctx = GraphContext({"a": 1})
		ctx.record_output("n", {"v": 2})
		back = flow_engine.load_context(flow_engine.dump_context(ctx))
		self.assertEqual(back.data, {"a": 1})
		self.assertEqual(back.resolve({"$from": "n.v"}), 2)


if __name__ == "__main__":
	unittest.main()
