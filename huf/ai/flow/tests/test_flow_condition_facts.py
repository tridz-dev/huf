"""Condition nodes over app facts providers (H-W2-22).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_condition_facts
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow import preflight
from huf.ai.flow.runs.edges import edges_from_nodes
from huf.ai.flow.support import facts, reason_codes
from huf.ai.graph.expressions import ExpressionError, parse_expression
from huf.ai.graph.validator import validate_graph
from huf.ai.flow.tests.test_flow_draft_validation import _graph, _trigger

M = "huf.ai.flow.tests.test_flow_condition_facts"
CALLS = []
SECRET = "tier-value-7f3a"
BEHAVIOUR = {"mode": "ok"}


def tier_provider(member_keys, names, context):
	CALLS.append(("tier", list(member_keys), list(names), context))
	mode = BEHAVIOUR["mode"]
	if mode == "raise":
		raise RuntimeError(SECRET)
	if mode == "shape":
		return [SECRET]
	if mode == "missing":
		return {}
	return {key: {"tier": SECRET, "tier_rank": 2, "points": 999} for key in member_keys}


def points_provider(member_keys, names, context):
	CALLS.append(("points", list(member_keys), list(names), context))
	return {key: {"points": 50} for key in member_keys}


ENTRIES = [
	{"facts": ["tier", "tier_rank"], "handler": f"{M}.tier_provider"},
	{"facts": ["points", "tier"], "handler": f"{M}.points_provider"},  # "tier" is already taken
]

CONFIG = {
	"expression": f"facts.tier == '{SECRET}' and facts.points > 10",
	"on_true": "yes",
	"on_false": "no",
	"fallback_next": "unknown_step",
}


class _Run:
	flow_id = "f"
	member_key = "m0"
	name = "FR"
	context_json = "{}"


class TestFlowConditionFacts(IntegrationTestCase):
	def setUp(self):
		CALLS.clear()
		BEHAVIOUR["mode"] = "ok"
		real = frappe.get_hooks

		def fake(hook=None, *a, **k):
			if hook == facts.HOOK:
				return list(ENTRIES) if k.get("app_name") == "huf" else []
			return real(hook, *a, **k)

		patcher = patch("frappe.get_hooks", side_effect=fake)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _evaluate(self, member="m0", config=CONFIG, settings=None):
		run = _Run()
		run.member_key = member
		settings = settings or flow_engine.FlowRunContext()
		return flow_engine._exec_condition(run, {"id": "c"}, config, settings), settings

	def test_one_call_per_family_for_500_members(self):
		members = [f"m{i}" for i in range(500)]
		with facts.batch("f", members):
			results = [self._evaluate(member)[0]["next_node_id"] for member in members]
		self.assertEqual(set(results), {"yes"})
		self.assertEqual([c[0] for c in CALLS], ["tier", "points"])
		self.assertEqual(CALLS[0][1], members)
		self.assertEqual((CALLS[0][2], CALLS[1][2]), (["tier"], ["points"]))
		self.assertEqual(CALLS[0][3], {"flow_id": "f"})

	def test_nothing_is_cached_outside_a_batch(self):
		self._evaluate()
		self._evaluate()
		self.assertEqual(len(CALLS), 4)

	def test_failures_take_the_fallback_and_never_true(self):
		for mode in ("raise", "shape", "missing"):
			BEHAVIOUR["mode"] = mode
			result, settings = self._evaluate()
			self.assertEqual((result["next_node_id"], result["output"]), ("unknown_step", False), mode)
			self.assertEqual(result["reason_code"], "facts_error", mode)
			self.assertEqual(settings.context.data["_huf_reasons"], {"c": "facts_error"})
			self.assertNotIn(SECRET, json.dumps(result))
		result, _ = self._evaluate(member=None)
		self.assertEqual(result["next_node_id"], "unknown_step")
		BEHAVIOUR["mode"] = "ok"
		for expression in ("facts.nope == 1", "not facts['nope']", "facts[input['n']] == 1"):
			result, _ = self._evaluate(config={**CONFIG, "expression": expression})
			self.assertEqual(result["next_node_id"], "unknown_step", expression)

	def test_late_answer_is_discarded(self):
		with patch.object(facts.time, "monotonic", side_effect=[0.0, 6.0, 6.0, 6.0]):
			result, _ = self._evaluate()
		self.assertEqual((result["next_node_id"], result["reason_code"]), ("unknown_step", "facts_timeout"))
		self.assertLessEqual({"facts_error", "facts_timeout"}, reason_codes.HUF_CODES)

	def test_timeout_setting_is_clamped(self):
		for value, expected in ((None, 5), ("9", 5), (True, 5), (-1, 5), (0.2, 1), (12, 12), (99, 30)):
			with patch.dict(frappe.conf, {facts.TIMEOUT_KEY: value}):
				self.assertEqual(facts.timeout_seconds(), expected, value)

	def test_no_fallback_fails_the_step(self):
		BEHAVIOUR["mode"] = "raise"
		config = {k: v for k, v in CONFIG.items() if k != "fallback_next"}
		result, _ = self._evaluate(config=config)
		self.assertEqual(result["status"], "failed")
		self.assertNotIn("next_node_id", result)

	def test_facts_are_not_stored_on_the_run(self):
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-facts-{frappe.generate_hash(length=8)}",
				"flow_name": "Facts Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": []}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		run = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": flow.name,
				"flow_id": flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
				"member_key": "m0",
			}
		).insert(ignore_permissions=True)
		settings = flow_engine.FlowRunContext(flow_run=run)
		result = flow_engine._exec_condition(run, {"id": "c"}, CONFIG, settings)
		self.assertEqual(result["next_node_id"], "yes")
		settings.context.record_output("c", result["output"])
		settings.save_context()
		stored = json.dumps(frappe.get_doc("Agent Flow Run", run.name).as_dict(), default=str)
		self.assertNotIn(SECRET, stored + json.dumps(result))

	def test_attribute_access_is_only_allowed_on_facts(self):
		self.assertEqual(facts.names_used(parse_expression("facts.coupons['x'] == 'issued'")), (["coupons"], False))
		for expression in ("input.__class__", "facts.__class__", "facts.tier.upper"):
			with self.assertRaises(ExpressionError):
				parse_expression(expression)

	def test_preflight_and_graph(self):
		node = {"id": "c", "type": "condition", "config": {**CONFIG, "on_true": "a", "on_false": "a", "fallback_next": "b"}}
		graph = _graph([_trigger("c"), node, *({"id": i, "type": "output", "config": {"value": 1}} for i in "ab")])
		self.assertTrue(validate_graph(graph, "flow").ok, validate_graph(graph, "flow").errors)
		self.assertIn(("c", "b"), {(e["from"], e["to"]) for e in edges_from_nodes(graph["nodes"])})
		self.assertEqual(preflight._facts_checks(graph, None), [])

		node["config"]["expression"] = "facts.nope == 1"
		self.assertIn("CONDITION_FACT_UNKNOWN", [f.code for f in preflight.blocking(preflight.run_preflight(graph))])
		node["config"].pop("fallback_next")
		self.assertIn("CONDITION_FALLBACK_MISSING", [f.code for f in preflight._facts_checks(graph, None)])
