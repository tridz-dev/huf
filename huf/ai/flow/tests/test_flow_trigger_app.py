"""``trigger.app`` (H-W2-25): a flow only its app starts, through ``start_flow_for_member``."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.flow import triggers
from huf.ai.flow.catalog import node_registry
from huf.ai.flow.listing.cards import summarize_definition
from huf.ai.flow.support.node_schemas import build_node_schemas
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph
from huf.ai.flow.tests.test_flow_start_for_member import TestFlowStartForMember
from huf.ai.graph.validator import get_flow_node_types, validate_flow
from huf.huf.doctype.flow_definition.activation_rules import collect_activation_problems, entry_is_unset

TRIGGER = {"id": "start", "type": "trigger.app", "config": {"app": "happiol"}, "next": "cond"}


def app_flow():
	return _graph(
		[
			TRIGGER,
			{"id": "cond", "type": "condition", "config": {"expression": "input['n'] > 1", "on_true": "end", "on_false": "end2"}},
			_end(),
			_end("end2"),
		]
	)


class TestAppTriggerPure(unittest.TestCase):
	def test_validator_accepts_it_as_the_entry(self):
		self.assertIn("trigger.app", get_flow_node_types())
		for mode in ("draft", "publish"):
			result = validate_flow(app_flow(), mode)
			self.assertTrue(result.ok, (mode, result.errors, result.issues))

	def test_activatable_and_not_unset(self):
		self.assertEqual(collect_activation_problems(app_flow()), [])
		self.assertFalse(entry_is_unset(app_flow()))

	def test_blank_app_blocks_activation(self):
		defn = app_flow()
		defn["nodes"][0] = {**TRIGGER, "config": {"app": " "}}
		self.assertTrue(any("'app'" in p for p in collect_activation_problems(defn)))

	def test_palette_marks_it_app_only(self):
		schema = build_node_schemas()["trigger.app"]
		self.assertTrue(schema["app_only"])
		self.assertEqual(schema["category"], "trigger")
		self.assertEqual([f["name"] for f in schema["config_schema"] if f["required"]], ["app"])
		self.assertNotIn("app_only", build_node_schemas()["trigger.webhook"])
		self.assertIn("trigger.app", node_registry.EMBED_BUILTIN_TYPES)

	def test_card_names_the_app(self):
		self.assertEqual(summarize_definition(app_flow())["trigger"], {"type": "app", "app": "happiol"})

	def test_not_in_doc_event_index(self):
		row = ("f1", "Administrator", app_flow())
		self.assertEqual(triggers.build_doc_event_index([row]), {})


class TestAppTriggerExecutor(unittest.TestCase):
	def _run(self, trigger_type, run_mode="Real"):
		run = SimpleNamespace(trigger_type=trigger_type, run_mode=run_mode)
		with patch("huf.ai.flow.engine._context_of", return_value=SimpleNamespace(as_dict=lambda: {"input": {}})):
			return node_registry.executor_for("trigger.app")(run, TRIGGER, TRIGGER["config"], {})

	def test_app_run_passes_through(self):
		self.assertEqual(self._run("App")["status"], "success")

	def test_manual_and_other_starts_fail(self):
		for kind in ("Manual", "Webhook", "Schedule", "Doc Event", "Gateway"):
			out = self._run(kind)
			self.assertEqual(out["status"], "failed", kind)
			self.assertIn("happiol", out["error"])

	def test_dry_run_is_allowed(self):
		self.assertEqual(self._run("Manual", run_mode="Test")["status"], "success")


class TestAppTriggerStart(TestFlowStartForMember):
	"""The start_flow_for_member suite (incl. 20 parallel calls -> one run) against an app-trigger flow."""

	def setUp(self):
		super().setUp()
		defn = app_flow()
		self.trigger = defn["nodes"][0]
		frappe.db.set_value("Flow Definition", self.flow_id, "definition_json", json.dumps(defn))
		frappe.db.commit()
		frappe.cache().delete_value(triggers.DOC_EVENT_CACHE_KEY)

	def test_run_is_labelled_app_and_starts_at_the_trigger(self):
		name = self._start(trigger_node_id="start")
		run = frappe.get_doc("Agent Flow Run", name)
		self.assertEqual(run.trigger_type, "App")
		self.assertEqual(run.current_node_id, "start")

	def test_activation_passes_on_save(self):
		flow = frappe.get_doc("Flow Definition", self.flow_id)
		flow.status = "Active"
		flow.save(ignore_permissions=True)  # raises if activation rules reject it

	def test_document_events_start_nothing(self):
		self.assertNotIn(self.flow_id, json.dumps(triggers.get_doc_event_index()))
		doc = frappe.get_doc({"doctype": "ToDo", "description": "app trigger probe"})
		with patch("frappe.enqueue") as enqueue:
			doc.insert(ignore_permissions=True)
			doc.description = "changed"
			doc.save(ignore_permissions=True)
			for method in triggers.DOC_EVENT_MAP.values():  # every hooked event, incl. submit / cancel
				triggers.run_doc_event_flows(doc, method)
			doc.delete(ignore_permissions=True)
		flows = [c.kwargs.get("flow_id") for c in enqueue.call_args_list]
		self.assertNotIn(self.flow_id, flows)
		self.assertEqual(self._runs(), 0)
