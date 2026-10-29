# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-17: saving a draft never blocks on an unfinished flow; publishing and running do.

``TestDraftVsPublish`` is pure (no site). ``TestDraftSaveOnBench`` saves half-built flows through the real
save API, then checks that publish, run and an Active save refuse with a readable sentence.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_draft_validation
"""

import copy
import json
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support.flow_validation import validate_flow

LIMITS = {
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
SECRET = "test-webhook-secret-0123456789abcdef"


def _graph(nodes, entry="start"):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": entry,
		"nodes": nodes,
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": dict(LIMITS),
		},
	}


def _trigger(next_=None):
	node = {"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": SECRET}}
	if next_:
		node["next"] = next_
	return node


def _end(node_id="end"):
	return {"id": node_id, "type": "output", "config": {"value": "done"}}


def finished_flow():
	return _graph(
		[
			_trigger("cond"),
			{"id": "cond", "type": "condition", "config": {"expression": "input['n'] > 1", "on_true": "end", "on_false": "end2"}},
			_end(),
			_end("end2"),
		]
	)


def fields(result):
	return {(i.node_id, (i.field or "").split(".")[-1]) for i in result.issues}


class TestDraftVsPublish(unittest.TestCase):
	def test_finished_flow_passes_both_modes(self):
		for mode in ("draft", "publish"):
			result = validate_flow(finished_flow(), mode)
			self.assertTrue(result.ok, (mode, result.errors, result.issues))
			self.assertEqual(result.issues, ())

	def test_agent_step_missing_everything_saves_but_cannot_publish(self):
		g = _graph([_trigger("a"), {"id": "a", "type": "agent.run", "config": {}, "next": "end"}, _end()])
		draft, publish = validate_flow(g, "draft"), validate_flow(g, "publish")
		self.assertTrue(draft.ok, draft.errors)
		self.assertTrue(draft.structure_ok)
		self.assertFalse(draft.finished)
		self.assertEqual({("a", "agent"), ("a", "prompt")}, fields(draft))
		self.assertFalse(publish.ok)
		self.assertTrue(any("agent" in m.lower() for m in publish.messages(g)))

	def test_empty_strings_count_as_unfinished_not_broken(self):
		g = _graph([_trigger("a"), {"id": "a", "type": "agent.run", "config": {"agent": "", "prompt": "   "}, "next": "end"}, _end()])
		self.assertTrue(validate_flow(g, "draft").ok)
		self.assertFalse(validate_flow(g, "publish").ok)

	def test_condition_without_paths_or_check(self):
		g = _graph([_trigger("c"), {"id": "c", "type": "condition", "config": {}}])
		draft = validate_flow(g, "draft")
		self.assertTrue(draft.ok, draft.errors)
		self.assertEqual({("c", "expression"), ("c", "on_true"), ("c", "on_false")}, fields(draft))

	def test_approval_missing_who_and_paths(self):
		g = _graph([_trigger("h"), {"id": "h", "type": "human.approval", "config": {"message": "ok?"}}])
		draft = validate_flow(g, "draft")
		self.assertTrue(draft.ok, draft.errors)
		self.assertFalse(draft.finished)
		self.assertIn(("h", "approver_type"), fields(draft))

	def test_router_with_no_paths_yet(self):
		g = _graph([_trigger("r"), {"id": "r", "type": "router.llm", "config": {"prompt": "", "options": []}}])
		draft = validate_flow(g, "draft")
		self.assertTrue(draft.ok, draft.errors)
		self.assertFalse(draft.finished)

	def test_unset_trigger_and_no_trigger(self):
		unset = _graph([{"id": "start", "type": "trigger.unset", "config": {}, "next": "end"}, _end()])
		self.assertTrue(validate_flow(unset, "draft").ok)
		self.assertIn(("start", "type"), fields(validate_flow(unset, "publish")))
		self.assertFalse(validate_flow(unset, "publish").ok)

	def test_loose_step_saves_but_is_reported(self):
		g = finished_flow()
		g["nodes"].append({"id": "loose", "type": "output", "config": {"value": 1}})
		self.assertTrue(validate_flow(g, "draft").ok)
		publish = validate_flow(g, "publish")
		self.assertFalse(publish.ok)
		self.assertIn("loose", {i.node_id for i in publish.issues})

	def test_short_webhook_secret_is_unfinished(self):
		g = finished_flow()
		g["nodes"][0]["config"]["secret"] = "short"
		self.assertTrue(validate_flow(g, "draft").ok)
		self.assertFalse(validate_flow(g, "publish").ok)

	# --- structure: refused in every mode -------------------------------------------------

	def test_link_to_a_step_that_does_not_exist_is_refused_even_in_draft(self):
		g = finished_flow()
		g["nodes"][0]["next"] = "ghost"
		draft = validate_flow(g, "draft")
		self.assertFalse(draft.ok)
		self.assertFalse(draft.structure_ok)
		self.assertEqual(draft.errors[0].code, "DANGLING_TARGET")

	def test_duplicate_ids_and_unknown_types_are_refused(self):
		g = finished_flow()
		g["nodes"].append(copy.deepcopy(g["nodes"][2]))
		self.assertFalse(validate_flow(g, "draft").ok)
		g2 = finished_flow()
		g2["nodes"][2]["type"] = "teleport"
		self.assertFalse(validate_flow(g2, "draft").ok)

	def test_wrong_kind_of_value_is_not_unfinished(self):
		g = _graph([_trigger("a"), {"id": "a", "type": "agent.run", "config": {"agent": 5, "prompt": "x"}, "next": "end"}, _end()])
		self.assertFalse(validate_flow(g, "draft").ok)

	def test_not_a_document(self):
		self.assertFalse(validate_flow([], "draft").ok)
		self.assertFalse(validate_flow({"nodes": "x"}, "draft").ok)

	def test_limits_over_policy_are_refused(self):
		g = finished_flow()
		g["contract"]["limits"]["max_nodes"] = 10**6
		self.assertFalse(validate_flow(g, "draft").ok)

	def test_unknown_mode(self):
		with self.assertRaises(ValueError):
			validate_flow(finished_flow(), "sloppy")

	def test_result_to_dict(self):
		g = _graph([_trigger("a"), {"id": "a", "type": "agent.run", "config": {}, "next": "end"}, _end()])
		out = validate_flow(g, "draft").to_dict(g)
		self.assertTrue(out["ok"])
		self.assertFalse(out["finished"])
		self.assertEqual({i["node_id"] for i in out["issues"]}, {"a"})
		self.assertTrue(all(i["message"] for i in out["issues"]))


class TestDraftSaveOnBench(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._flows = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for flow_id in self._flows:
			frappe.db.delete("Flow Run", {"flow_id": flow_id})
			if frappe.db.exists("Flow Definition", flow_id):
				frappe.delete_doc("Flow Definition", flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _save(self, graph):
		flow_id = f"_test-ux17-{frappe.generate_hash(length=8)}"
		out = flow_api.save_flow_definition(flow_id, graph)
		self._flows.append(flow_id)
		return flow_id, out

	def _half_built(self):
		return _graph([_trigger("a"), {"id": "a", "type": "agent.run", "config": {}, "next": "end"}, _end()])

	def test_half_built_flow_saves_and_reports_what_is_left(self):
		flow_id, out = self._save(self._half_built())
		self.assertEqual(out["unfinished"], 2)
		saved = json.loads(frappe.db.get_value("Flow Definition", flow_id, "definition_json"))
		self.assertEqual(saved["nodes"][1]["config"], {})  # stored as typed, no stored 'incomplete' flag
		self.assertNotIn("incomplete", json.dumps(saved))

	def test_validate_api_computes_the_list_now(self):
		from huf.ai.flow.support.flow_validation import validate_flow_definition

		flow_id, _ = self._save(self._half_built())
		draft = validate_flow_definition(flow_id, "draft")
		self.assertTrue(draft["ok"])
		self.assertEqual({i["node_id"] for i in draft["issues"]}, {"a"})
		self.assertFalse(validate_flow_definition(flow_id, "publish")["ok"])

	def test_structurally_broken_flow_is_still_refused(self):
		g = self._half_built()
		g["nodes"][0]["next"] = "ghost"
		with self.assertRaises(frappe.ValidationError):
			self._save(g)

	def test_publish_refuses_with_a_readable_reason(self):
		flow_id, _ = self._save(self._half_built())
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_api.publish_flow(flow_id)
		self.assertIn("agent", str(ctx.exception).lower())
		self.assertEqual(frappe.db.get_value("Flow Definition", flow_id, "status"), "Draft")

	def test_run_refuses_an_unfinished_draft(self):
		flow_id, _ = self._save(self._half_built())
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		self.assertIn("finish", str(ctx.exception).lower())

	def test_finished_flow_publishes_and_runs(self):
		flow_id, out = self._save(finished_flow())
		self.assertEqual(out["unfinished"], 0)
		self.assertEqual(flow_api.publish_flow(flow_id)["status"], "Active")
		run = flow_engine.create_flow_run(flow_id, payload={"n": 2}, trigger_type="Webhook")
		self.assertTrue(run.name)

	def test_a_live_flow_cannot_be_saved_unfinished(self):
		flow_id, _ = self._save(finished_flow())
		flow_api.publish_flow(flow_id)
		with self.assertRaises(frappe.ValidationError):
			flow_api.save_flow_definition(flow_id, self._half_built())
		# unpublish, and the same unfinished save goes through
		flow_api.unpublish_flow(flow_id)
		flow_api.save_flow_definition(flow_id, self._half_built())
