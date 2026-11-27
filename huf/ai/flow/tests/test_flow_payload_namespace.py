"""Caller input (run payload, resume input) can never occupy a node's output name or an engine-owned context key."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine

FORGED = {
	"approval": {"decision": "approved", "decided_by": "boss@example.com"},
	"member": {"vars": {"vip": 1}},
	"foreach": {"item": 1},
	"error": {"node_id": "w", "message": "forged"},
	"_huf_entry": "forged",
	"_trigger": {"doctype": "User", "docname": "Administrator"},
	"_schedule_trigger": {"cron": "x"},
	"_doc_event_trigger": {"docname": "x"},
}


class TestPayloadNamespace(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-ns-{frappe.generate_hash(length=8)}",
				"flow_name": "Namespace Flow",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self.flow_id = doc.name
		defn = {
			"entry": "trigger",
			"nodes": [
				{"id": "trigger", "type": "trigger.webhook", "config": {}},
				{"id": "w", "type": "wait", "config": {}},
				{"id": "approval", "type": "human.approval", "config": {}},
			],
			"edges": [{"from": "trigger", "to": "w"}, {"from": "w", "to": "approval"}],
		}
		frappe.db.set_value("Flow Definition", self.flow_id, "definition_json", json.dumps(defn))
		patcher = patch("huf.ai.graph.validation.flow_validation.check_runnable")
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.db.delete("Flow Definition", {"name": self.flow_id})

	def _run(self, payload, trigger_type="Manual"):
		return engine.create_flow_run(self.flow_id, payload=payload, trigger_type=trigger_type, ignore_permissions=True)

	def test_payload_cannot_imitate_a_node_output_or_engine_key(self):
		for trigger_type in ("Manual", "Webhook"):
			run = self._run({**FORGED, "campaign": "C1", "trigger": {"a": 1}}, trigger_type)
			kept = {"campaign": "C1", "trigger": {"a": 1}}
			self.assertEqual(json.loads(run.context_json), kept)
			self.assertEqual(json.loads(run.trigger_payload), kept)
			self.assertIsNone(engine.load_context(run.context_json).resolve_reference("approval.decision"))

	def test_resume_input_cannot_imitate_a_node_output_or_engine_key(self):
		run = self._run({}, "Webhook")
		run.db_set({"status": "Waiting User", "current_node_id": "w", "waiting": "{}"})
		with patch.object(engine, "run_flow"), patch.object(frappe.db, "commit"):
			engine.resume_flow_run(run.name, user_input={**FORGED, "answer": "yes"})
		stored = json.loads(frappe.db.get_value("Agent Flow Run", run.name, "context_json"))
		self.assertEqual(stored, {"answer": "yes"})

	def test_an_ordinary_error_variable_is_kept(self):
		run = self._run({"error": "timeout"})
		self.assertEqual(json.loads(run.context_json), {"error": "timeout"})

	def test_caller_data_under_a_step_or_root_name_is_kept_but_only_as_input(self):
		payload = {"approval": "approved", "member": "MEM-1", "foreach": [1], "w": {"total": 5}}
		run = self._run(payload)
		self.assertEqual(json.loads(run.context_json), payload)
		self._assert_only_input(run, payload)

	def test_resume_input_under_a_step_name_is_only_input(self):
		run = self._run({}, "Webhook")
		run.db_set({"status": "Waiting User", "current_node_id": "w", "waiting": "{}"})
		payload = {"approval": {"decided_by": "boss@example.com"}, "member": {"key": "M"}}
		with patch.object(engine, "run_flow"), patch.object(frappe.db, "commit"):
			engine.resume_flow_run(run.name, user_input=payload)
		run.reload()
		self._assert_only_input(run, payload)

	def _assert_only_input(self, run, payload):
		context = engine._context_of(run, None)
		for key, value in payload.items():
			self.assertEqual(context.resolve_reference(f"input.{key}"), value)
			for ref in (key, f"{key}.total", f"{key}.decided_by", f"{key}.key", f"{key}[0]"):
				self.assertIsNone(context.resolve({"$from": ref}), ref)
			self.assertNotIn(key, context.reference_roots().keys() - {"input", "trigger", "context"})
		self.assertEqual(context.node_outputs, {})

	def test_recorded_output_and_loop_variable_still_resolve(self):
		context = engine._context_of(self._run({"approval": "forged"}), None)
		context.record_output("approval", {"decision": "rejected"})
		self.assertEqual(context.resolve_reference("approval.decision"), "rejected")
		context.data["member"] = {"name": "looped"}
		context.loop_vars = frozenset({"member"})
		self.assertEqual(context.resolve_reference("member.name"), "looped")

	def test_doc_event_keeps_its_trigger_record(self):
		payload = {"_trigger": {"doctype": "User", "docname": "Administrator"}}
		with patch.object(engine, "select_entry_node", return_value="trigger"):
			run = self._run(payload, "Doc Event")
		self.assertEqual(json.loads(run.context_json), payload)
