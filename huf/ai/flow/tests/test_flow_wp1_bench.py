# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""WP1 on a real bench: lazy approval expiry on read, the once-per-due-minute schedule dispatcher,
the stale-run sweeper and the failed-step record, all through the real engine and database.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_wp1_bench
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow import triggers

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
CONTRACT = {
	"input_schema": {"type": "object"},
	"output_schema": {"type": "object"},
	"applies_when": [],
	"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
	"limits": LIMITS,
}


def _out(node_id, value):
	return {"id": node_id, "type": "output", "config": {"value": value}}


def _graph(nodes, trigger):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": [{"id": "start", **trigger}, *nodes],
		"contract": CONTRACT,
	}


WEBHOOK = {"type": "trigger.webhook", "config": {"method": "POST", "secret": "test-webhook-secret-0123456789abcdef"}}


class TestFlowWp1(IntegrationTestCase):
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

	def _save(self, graph, active=False):
		flow_id = f"_test-wp1-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(flow_id, graph)
		self._flows.append(flow_id)
		if active:
			doc = frappe.get_doc("Flow Definition", flow_id)
			doc.status = "Active"
			doc.save(ignore_permissions=True)
		return flow_id

	def _approval_flow(self):
		graph = _graph(
			[
				{
					"id": "ask",
					"type": "human.approval",
					"config": {
						"message": "ok?",
						"approver_type": "role",
						"approver_role": "System Manager",
						"approve_next": "yes",
						"reject_next": "no",
						"timeout_next": "late",
						"timeout_ms": 60000,
					},
				},
				_out("yes", "approved"),
				_out("no", "rejected"),
				_out("late", "timed out"),
			],
			WEBHOOK,
		)
		graph["nodes"][0]["next"] = "ask"
		return self._save(graph)

	def _waiting_run(self):
		flow_id = self._approval_flow()
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval")
		return run

	def _expire_deadline(self, run):
		waiting = json.loads(run.waiting)
		waiting["timeout_at"] = (now_datetime() - timedelta(seconds=5)).isoformat()
		frappe.db.set_value("Flow Run", run.name, "waiting", json.dumps(waiting))
		frappe.db.commit()

	# -- approval expiry -------------------------------------------------

	def test_reading_an_overdue_approval_routes_it_on_the_timeout_edge(self):
		run = self._waiting_run()
		self._expire_deadline(run)
		got = flow_api.get_flow_run(run.name)  # lazy expiry; the continuation is queued
		run.reload()
		self.assertEqual((run.status, run.current_node_id), ("Running", "late"))
		flow_engine.run_flow(run.name)  # what the queued job does
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		record = json.loads(run.context_json)[flow_engine.NODE_OUTPUTS_KEY]["ask"]
		self.assertEqual(record["decision"], "timeout")
		self.assertIsNone(record["decided_by"])
		self.assertTrue(record["decided_at"].endswith("Z"))
		self.assertIn(got["status"], ("Running", "Success"))

	def test_an_approval_that_is_not_due_is_left_alone_on_read(self):
		run = self._waiting_run()
		self.assertEqual(flow_api.get_flow_run(run.name)["status"], "Waiting Approval")

	def test_lists_and_pending_approvals_also_expire_overdue_runs(self):
		run = self._waiting_run()
		self._expire_deadline(run)
		flow_api.get_pending_approvals()
		run.reload()
		self.assertEqual((run.status, run.current_node_id), ("Running", "late"))

	def test_expiry_twice_does_not_run_the_step_twice(self):
		run = self._waiting_run()
		self._expire_deadline(run)
		self.assertTrue(flow_engine.expire_approval(run.name))
		self.assertFalse(flow_engine.expire_approval(run.name))
		run.reload()
		self.assertEqual(run.hop_count, 3)

	def test_run_flow_ignores_a_run_that_is_waiting(self):
		run = self._waiting_run()
		before = run.waiting
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval")
		self.assertEqual(run.waiting, before)  # the paused step did not run again (no new deadline)

	def test_decision_record_uses_decided_fields(self):
		run = self._waiting_run()
		flow_engine.approve_flow_run(run.name, "approved", "fine")
		run.reload()
		record = json.loads(run.context_json)[flow_engine.NODE_OUTPUTS_KEY]["ask"]
		self.assertEqual(record["decided_by"], "Administrator")
		self.assertTrue(record["decided_at"].endswith("Z"))
		self.assertNotIn("approved_by", record)

	# -- schedule dispatcher ---------------------------------------------

	def test_a_due_minute_starts_exactly_one_run_even_if_dispatched_twice(self):
		graph = _graph([_out("done", "ok")], {"type": "trigger.schedule", "config": {"cron": "*/1 * * * *"}})
		graph["nodes"][0]["next"] = "done"
		flow_id = self._save(graph, active=True)
		now = datetime(2030, 1, 1, 10, 0, 5)
		def run_inline(method, queue=None, **kwargs):
			triggers.run_trigger_job(**kwargs)

		with patch("huf.ai.flow.triggers.frappe.enqueue", side_effect=run_inline):
			first = triggers.run_due_schedule_flows(now)
			second = triggers.run_due_schedule_flows(now + timedelta(seconds=30))
		self.assertIn(flow_id, first)
		runs = frappe.get_all("Flow Run", filters={"flow_id": flow_id, "trigger_type": "Schedule"}, pluck="name")
		self.assertEqual(len(runs), 1, (runs, second))

	# -- stale runs --------------------------------------------------------

	def test_sweeper_fails_a_stuck_run_but_not_a_fresh_or_waiting_one(self):
		graph = _graph([_out("done", "ok")], WEBHOOK)
		graph["nodes"][0]["next"] = "done"
		flow_id = self._save(graph)
		stuck = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		fresh = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		long_ago = add_to_date(now_datetime(), minutes=-45)
		frappe.db.set_value("Flow Run", stuck.name, {"status": "Running"}, update_modified=False)
		frappe.db.set_value("Flow Run", stuck.name, "modified", long_ago, update_modified=False)
		waiting = self._waiting_run()
		frappe.db.set_value("Flow Run", waiting.name, "modified", long_ago, update_modified=False)
		swept = flow_engine.sweep_stale_runs()
		self.assertIn(stuck.name, swept)
		self.assertNotIn(fresh.name, swept)
		self.assertNotIn(waiting.name, swept)
		stuck.reload()
		self.assertEqual(stuck.status, "Failed")
		self.assertEqual(stuck.last_error, "Run did not complete (worker stopped)")
		fresh.reload()
		self.assertEqual(fresh.status, "Queued")

	# -- failed step record ------------------------------------------------

	def test_a_failed_step_keeps_a_readable_error_in_its_stored_result(self):
		graph = _graph(
			[{"id": "bad", "type": "tool.call", "config": {"tool_id": "http_request", "input": {"url": "http://127.0.0.1:1/"}}}],
			WEBHOOK,
		)
		graph["contract"] = {**CONTRACT, "permission_envelope": {**CONTRACT["permission_envelope"], "http": ["http_request"]}}
		graph["nodes"][0]["next"] = "bad"
		flow_id = self._save(graph)
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Failed")
		record = json.loads(run.context_json)[flow_engine.NODE_OUTPUTS_KEY]["bad"]
		self.assertEqual(record["status"], "failed")
		self.assertTrue(record["error"])
