# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Automation -> Agent Procedure target, and the Flow trigger API built on it.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.automation.tests.test_automation_procedure_target
"""

import datetime
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.automation import hooks as automation_hooks
from huf.ai.automation import scheduler as automation_scheduler
from huf.ai.flow import api as flow_api
from huf.ai.automation.runner import run_automation
from huf.testing.factories import make_agent, make_ai_model, make_ai_provider, make_automation

PREFIX = "_Test PrE"


def _limits(**overrides):
	limits = {
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
	limits.update(overrides)
	return limits


def _flow_definition(nodes=None):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": nodes
		or [
			{"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": "test-webhook-secret-0123456789abcdef"}, "next": "finish"},
			{"id": "finish", "type": "output", "config": {"value": {"ok": True}}},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": _limits(),
		},
	}


class _Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._flows = []
		self._automations = []
		self._agents = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._automations:
			for t in frappe.get_all("Automation Trigger", {"automation": name}, pluck="name"):
				frappe.db.set_value("Agent Procedure Run", {"automation_trigger": t}, "automation_trigger", None)
				frappe.delete_doc("Automation Trigger", t, force=1, ignore_permissions=True)
			frappe.db.set_value("Agent Procedure Run", {"automation": name}, "automation", None)
			frappe.delete_doc("Automation", name, force=1, ignore_permissions=True)
		for flow_id in self._flows:
			for p in frappe.get_all("Agent Procedure", {"procedure_id": f"{flow_id}-procedure"}, pluck="name"):
				frappe.db.delete("Agent Procedure Run", {"procedure": p})
				frappe.delete_doc("Agent Procedure", p, force=1, ignore_permissions=True)
			frappe.delete_doc("Flow Definition", flow_id, force=1, ignore_permissions=True)
		for name in self._agents:
			frappe.delete_doc("Agent", name, force=1, ignore_permissions=True)
		frappe.cache().delete_key(automation_hooks.CACHE_KEY)
		frappe.db.commit()

	def _flow(self, definition=None):
		flow_id = f"prE-flow-{frappe.generate_hash(length=6)}"
		frappe.flags.currently_saving = getattr(frappe.flags, "currently_saving", None) or []
		frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": flow_id,
				"flow_name": flow_id,
				"definition_json": json.dumps(definition or _flow_definition()),
			}
		).insert(ignore_permissions=True)
		self._flows.append(flow_id)
		return flow_id

	def _procedure_automation(self, flow_id=None, procedure_status="Active", **overrides):
		flow_id = flow_id or self._flow()
		procedure = flow_api.convert_flow_to_procedure(flow_id, procedure_id=f"{flow_id}-procedure")["name"]
		frappe.db.set_value("Agent Procedure", procedure, "status", procedure_status)
		fields = {
			"automation_name": f"{PREFIX} {frappe.generate_hash(length=8)}",
			"target_type": "Agent Procedure",
			"procedure": procedure,
			"status": "Active",
		}
		fields.update(overrides)
		doc = frappe.get_doc({"doctype": "Automation", **fields}).insert(ignore_permissions=True)
		self._automations.append(doc.name)
		return doc, procedure

	def _runs(self, automation):
		return frappe.get_all(
			"Agent Procedure Run",
			{"automation": automation},
			["name", "input_payload", "status", "automation_trigger"],
		)


class TestAutomationTargetValidation(_Base):
	def test_procedure_target_requires_procedure_and_forbids_agent(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Automation", "automation_name": f"{PREFIX} a", "target_type": "Agent Procedure"}
			).insert(ignore_permissions=True)

	def test_procedure_target_rejects_agent_alongside(self):
		flow_id = self._flow()
		procedure = flow_api.convert_flow_to_procedure(flow_id, procedure_id=f"{flow_id}-procedure")["name"]
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Automation",
					"automation_name": f"{PREFIX} b{frappe.generate_hash(length=5)}",
					"target_type": "Agent Procedure",
					"procedure": procedure,
					"agent": make_agent().name,
				}
			).insert(ignore_permissions=True)

	def test_agent_target_rejects_procedure(self):
		flow_id = self._flow()
		procedure = flow_api.convert_flow_to_procedure(flow_id, procedure_id=f"{flow_id}-procedure")["name"]
		with self.assertRaises(frappe.ValidationError):
			make_automation(procedure=procedure)

	def test_agent_target_still_needs_agent(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Automation", "automation_name": f"{PREFIX} c{frappe.generate_hash(length=5)}", "instruction": "x"}
			).insert(ignore_permissions=True)

	def test_active_automation_needs_runnable_procedure(self):
		flow_id = self._flow()
		procedure = flow_api.convert_flow_to_procedure(flow_id, procedure_id=f"{flow_id}-procedure")["name"]
		self.assertEqual(frappe.db.get_value("Agent Procedure", procedure, "status"), "Draft")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Automation",
					"automation_name": f"{PREFIX} d{frappe.generate_hash(length=5)}",
					"target_type": "Agent Procedure",
					"procedure": procedure,
					"status": "Active",
				}
			).insert(ignore_permissions=True)
		# A Draft automation may bind the Draft procedure ...
		doc = frappe.get_doc(
			{
				"doctype": "Automation",
				"automation_name": f"{PREFIX} e{frappe.generate_hash(length=5)}",
				"target_type": "Agent Procedure",
				"procedure": procedure,
			}
		).insert(ignore_permissions=True)
		self._automations.append(doc.name)
		# ... but cannot go Active until the procedure is Testing/Active.
		doc.status = "Active"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.db.set_value("Agent Procedure", procedure, "status", "Testing")
		doc.reload()
		doc.status = "Active"
		doc.save()

	def test_valid_procedure_target_inserts(self):
		doc, _ = self._procedure_automation()
		self.assertEqual(doc.target_type, "Agent Procedure")
		self.assertFalse(doc.agent)


class TestProcedureDispatch(_Base):
	def test_schedule_dispatch_creates_procedure_run_with_run_as_user(self):
		doc, procedure = self._procedure_automation()
		trigger = frappe.get_doc(
			{
				"doctype": "Automation Trigger",
				"trigger_name": f"{PREFIX} sched",
				"automation": doc.name,
				"trigger_type": "Schedule",
				"schedule_type": "Interval",
				"scheduled_interval": "Hourly",
				"interval_count": 1,
				"next_execution": frappe.utils.now_datetime() - datetime.timedelta(minutes=5),
			}
		).insert(ignore_permissions=True)

		automation_scheduler.run_due_automations()

		runs = self._runs(doc.name)
		self.assertEqual(len(runs), 1)
		self.assertEqual(runs[0].automation_trigger, trigger.name)
		self.assertEqual(json.loads(runs[0].input_payload)["type"], "schedule")
		self.assertEqual(frappe.db.get_value("Agent Procedure Run", runs[0].name, "procedure"), procedure)
		# next_execution advanced past now; bookkeeping written.
		self.assertGreater(frappe.db.get_value("Automation Trigger", trigger.name, "next_execution"), frappe.utils.now_datetime())
		self.assertEqual(frappe.db.get_value("Automation", doc.name, "total_runs"), 1)
		# A second tick does not re-fire (not due).
		automation_scheduler.run_due_automations()
		self.assertEqual(len(self._runs(doc.name)), 1)

	def test_cron_trigger_next_execution_is_in_the_future(self):
		doc, _ = self._procedure_automation()
		trigger = frappe.get_doc(
			{
				"doctype": "Automation Trigger",
				"trigger_name": f"{PREFIX} cron",
				"automation": doc.name,
				"trigger_type": "Schedule",
				"schedule_type": "Cron",
				"cron_expression": "*/15 * * * *",
			}
		).insert(ignore_permissions=True)
		self.assertGreater(trigger.next_execution, frappe.utils.now_datetime())
		self.assertLessEqual(trigger.next_execution, frappe.utils.now_datetime() + datetime.timedelta(minutes=15))

	def test_automatic_trigger_refuses_non_runnable_procedure(self):
		doc, procedure = self._procedure_automation()
		frappe.db.set_value("Agent Procedure", procedure, "status", "Disabled")
		with self.assertRaises(frappe.ValidationError):
			run_automation(doc.name, trigger_name="whatever", trigger_context={"type": "schedule"})
		self.assertEqual(self._runs(doc.name), [])

	def test_manual_run_uses_current_user_and_creates_run(self):
		doc, _ = self._procedure_automation()
		result = run_automation(doc.name, now=True, initiating_user="Administrator")
		self.assertIn("procedure_run_id", result)
		self.assertEqual(len(self._runs(doc.name)), 1)

	def test_doc_event_queues_after_commit_and_carries_reference(self):
		doc, _ = self._procedure_automation()
		frappe.get_doc(
			{
				"doctype": "Automation Trigger",
				"trigger_name": f"{PREFIX} docev",
				"automation": doc.name,
				"trigger_type": "Doc Event",
				"reference_doctype": "ToDo",
				"doc_event": "after_insert",
			}
		).insert(ignore_permissions=True)
		frappe.cache().delete_key(automation_hooks.CACHE_KEY)

		todo = None
		try:
			with patch("huf.ai.automation.hooks.enqueue") as mock_enqueue:
				# The real hooks.py doc_events registration fires on insert.
				todo = frappe.get_doc({"doctype": "ToDo", "description": "prE doc event"}).insert(
					ignore_permissions=True
				)
				# Nothing runs or is queued inline in the doc hook ...
				mock_enqueue.assert_not_called()
				self.assertEqual(self._runs(doc.name), [])
				# ... only once the surrounding transaction commits.
				frappe.db.after_commit.run()
				mock_enqueue.assert_called_once()
				kwargs = mock_enqueue.call_args.kwargs

			automation_hooks.run_automation_for_doc(
				kwargs["trigger"], kwargs["doc"], kwargs["event_name"], initiating_user=kwargs["initiating_user"]
			)
			runs = self._runs(doc.name)
			self.assertEqual(len(runs), 1)
			payload = json.loads(runs[0].input_payload)
			self.assertEqual(payload["type"], "doc_event")
			self.assertEqual(payload["reference_doctype"], "ToDo")
			self.assertEqual(payload["reference_name"], todo.name)
			self.assertEqual(payload["doc"]["description"], "prE doc event")
			self.assertNotIn("_doc_event_supplement", payload)
		finally:
			if todo:
				frappe.delete_doc("ToDo", todo.name, force=1, ignore_permissions=True)


class TestAgentTargetRegression(_Base):
	def test_agent_automation_still_runs_via_run_agent_sync(self):
		provider = make_ai_provider()
		model = make_ai_model(provider=provider.name)
		agent = make_agent(provider=provider.name, model=model.name)
		self._agents.append(agent.name)
		automation = make_automation(agent=agent.name, instruction="do the thing", status="Active")
		self._automations.append(automation.name)
		self.assertEqual(automation.target_type, "Agent")

		with patch("huf.ai.agent.integration.run_agent_sync") as mock_run:
			mock_run.return_value = {"success": True, "agent_run_id": None, "conversation_id": None}
			result = run_automation(automation.name, now=True, initiating_user="Administrator")

		self.assertTrue(result["success"])
		self.assertEqual(mock_run.call_args.kwargs["agent_name"], agent.name)
		self.assertIn("do the thing", mock_run.call_args.kwargs["prompt"])
		self.assertEqual(frappe.get_all("Agent Procedure Run", {"automation": automation.name}), [])
		self.assertEqual(frappe.db.get_value("Automation", automation.name, "total_runs"), 1)


class TestFlowTriggerNodes(_Base):
	def test_legacy_flow_scheduling_is_gone(self):
		for name in ("schedule_flow", "unschedule_flow", "get_flow_schedule", "execute_scheduled_flow", "set_flow_trigger", "get_flow_trigger", "clear_flow_trigger"):
			self.assertFalse(hasattr(flow_api, name), name)

	def _activate_with_trigger_node(self, trigger_node):
		"""Save a real Flow Definition whose trigger node holds exactly the panel's mirrored config, as Active."""
		from huf.huf.doctype.flow_definition.activation_rules import collect_activation_problems

		defn = _flow_definition(
			[
				{"id": "start", **trigger_node, "next": "finish"},
				{"id": "finish", "type": "output", "config": {"value": {"ok": True}}},
			]
		)
		self.assertEqual(collect_activation_problems(defn), [])
		flow_id = self._flow(defn)
		doc = frappe.get_doc("Flow Definition", flow_id)
		doc.status = "Active"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Flow Definition", flow_id, "status"), "Active")

	def test_panel_schedule_node_config_saves_and_activates(self):
		# Frontend summaryToNodeConfig('schedule', ...) -> { cron }
		self._activate_with_trigger_node({"type": "trigger.schedule", "config": {"cron": "*/5 * * * *"}})

	def test_panel_doc_event_node_config_saves_and_activates(self):
		# Frontend summaryToNodeConfig('doc-event', ...) -> { doctype, event }, event within the schema enum
		for event in ("after_insert", "on_update", "on_submit", "on_cancel", "on_trash"):
			self._activate_with_trigger_node(
				{"type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": event}}
			)

	def test_trigger_bound_marker_is_rejected(self):
		defn = _flow_definition(
			[
				{"id": "start", "type": "trigger.schedule", "config": {"trigger_bound": True}, "next": "finish"},
				{"id": "finish", "type": "output", "config": {"value": {"ok": True}}},
			]
		)
		with self.assertRaises(frappe.ValidationError):
			self._flow(defn)


class TestRunAsEscalation(_Base):
	def _user(self, roles):
		from huf.testing.factories import make_user

		user = make_user(email=f"prE-{frappe.generate_hash(length=8)}@example.com", roles=roles)
		self._users = getattr(self, "_users", []) + [user.name]
		return user.name

	def tearDown(self):
		super().tearDown()
		for u in getattr(self, "_users", []):
			frappe.delete_doc("User", u, force=1, ignore_permissions=True)

	def test_manager_cannot_escalate_via_update_automation(self):
		from huf.ai.automation import service as automation_service

		doc, _p = self._procedure_automation()
		manager = self._user(("Huf Manager",))
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError):
			automation_service.update_automation(doc.name, run_as_user="Administrator")

	def test_fire_time_checks_who_set_run_as_user(self):
		from huf.ai.automation.runner import _check_run_as_user_permission

		doc, _p = self._procedure_automation()
		weak = self._user(("Huf Manager",))
		# Owner is privileged but the run_as_user was last set by a non-privileged user.
		doc.run_as_user = "Administrator"
		doc.run_as_set_by = weak
		with self.assertRaises(frappe.PermissionError):
			_check_run_as_user_permission(doc)
		doc.run_as_set_by = "Administrator"
		_check_run_as_user_permission(doc)


class TestFixE(_Base):
	def test_m1_next_execution_recomputed_when_schedule_changes(self):
		doc, _ = self._procedure_automation()
		trigger = frappe.get_doc(
			{
				"doctype": "Automation Trigger",
				"trigger_name": f"{PREFIX} m1",
				"automation": doc.name,
				"trigger_type": "Schedule",
				"schedule_type": "Cron",
				"cron_expression": "0 0 1 1 *",  # yearly: far in the future
			}
		).insert(ignore_permissions=True)
		far = trigger.next_execution
		self.assertGreater(far, frappe.utils.now_datetime() + datetime.timedelta(days=1))

		trigger.cron_expression = "*/5 * * * *"
		trigger.save(ignore_permissions=True)
		self.assertLessEqual(trigger.next_execution, frappe.utils.now_datetime() + datetime.timedelta(minutes=5))

		# An unrelated edit keeps the scheduler-managed next_execution.
		kept = trigger.next_execution
		trigger.trigger_name = f"{PREFIX} m1b"
		trigger.save(ignore_permissions=True)
		self.assertEqual(trigger.next_execution, kept)

	def test_m3_unset_entry_flow_is_not_convertible(self):
		from huf.ai.procedure.conversion import analyze_conversion

		defn = _flow_definition(
			[
				{"id": "start", "type": "trigger.unset", "config": {}, "next": "finish"},
				{"id": "finish", "type": "output", "config": {"value": {"ok": True}}},
			]
		)
		result = analyze_conversion(defn)
		self.assertFalse(result.convertible)
		self.assertIn("trigger", result.reason.lower())

	def _doc_event_context(self, automation):
		trigger = {"automation": automation.name, "name": "t-m5", "file_attachments": []}
		with patch("huf.ai.automation.runner.run_automation") as mock_run:
			automation_hooks.run_automation_for_doc(
				trigger, {"doctype": "ToDo", "name": "x1", "description": "d"}, "after_insert"
			)
		return mock_run.call_args.kwargs["trigger_context"]

	def test_m5_doc_in_context_only_for_procedure_targets(self):
		proc_auto, _ = self._procedure_automation()
		self.assertIn("doc", self._doc_event_context(proc_auto))

		provider = make_ai_provider()
		model = make_ai_model(provider=provider.name)
		agent = make_agent(provider=provider.name, model=model.name)
		self._agents.append(agent.name)
		agent_auto = make_automation(agent=agent.name, instruction="x", status="Active")
		self._automations.append(agent_auto.name)
		self.assertNotIn("doc", self._doc_event_context(agent_auto))


class TestLegacyFlowScheduleCleanup(_Base):
	def test_patch_deletes_legacy_scheduled_job_types(self):
		from huf.patches.v1 import delete_legacy_flow_schedule_jobs

		# Scheduled Job Type names are derived from the method.
		frappe.db.delete("Scheduled Job Type", {"method": ["in", ["huf.ai.flow.api.execute_scheduled_flow", "huf.ai.prE_unrelated.job"]]})
		doc = frappe.get_doc(
			{
				"doctype": "Scheduled Job Type",
				"method": "huf.ai.flow.api.execute_scheduled_flow",
				"frequency": "Cron",
				"cron_format": "*/5 * * * *",
			}
		)
		doc.insert(ignore_permissions=True)
		keep = frappe.get_doc(
			{
				"doctype": "Scheduled Job Type",
				"method": "huf.ai.prE_unrelated.job",
				"frequency": "All",
			}
		).insert(ignore_permissions=True)
		try:
			delete_legacy_flow_schedule_jobs.execute()
			self.assertFalse(frappe.db.exists("Scheduled Job Type", doc.name))
			self.assertTrue(frappe.db.exists("Scheduled Job Type", keep.name))
		finally:
			frappe.delete_doc("Scheduled Job Type", keep.name, force=1, ignore_permissions=True)
			if frappe.db.exists("Scheduled Job Type", doc.name):
				frappe.delete_doc("Scheduled Job Type", doc.name, force=1, ignore_permissions=True)


class TestListFlowToolsHidesCodeExecution(_Base):
	def test_code_execution_tools_not_offered(self):
		from huf.testing.factories import make_agent_tool_function

		docs = {
			"code": make_agent_tool_function(types="Code Execution"),
			"plain": make_agent_tool_function(),
		}
		try:
			offered = {t["name"] for t in flow_api.list_flow_tools()}
			self.assertNotIn(docs["code"].tool_name, offered)
			self.assertIn(docs["plain"].tool_name, offered)
		finally:
			for doc in docs.values():
				frappe.delete_doc("Agent Tool Function", doc.name, force=1, ignore_permissions=True)
