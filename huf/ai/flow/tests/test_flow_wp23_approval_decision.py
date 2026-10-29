# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""WP23: a decision on an approval is either recorded or refused, never "approved" with the run still waiting.

The failure seen in UI passes: the approver pressed Approve right after the run paused, the server answered
success, the run stayed ``Waiting Approval``. Cause: the decision's transaction also marked the approvers'
notifications as read. Those rows are inserted by a background job at about the same moment; with MariaDB
snapshot isolation an UPDATE of a row written after the transaction's snapshot fails (error 1020) and the
database rolls back the WHOLE transaction, the decision included. The ``except: pass`` around the notification
update hid it, the commit committed nothing and the API answered with the unchanged run.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_wp23_approval_decision
"""

import json
import threading
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support import approval_notifications
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out


class TestApprovalDecisionIsNotLost(WP11Base):
	def _approval_graph(self, timeout_ms=None):
		def todo(node_id, text, nxt):
			return {
				"id": node_id,
				"type": "doc.create",
				"config": {"doctype": "ToDo", "fields": {"description": f"{self.marker} {text}"}},
				"next": nxt,
			}

		config = {
			"message": "ok?",
			"approver_type": "role",
			"approver_role": "System Manager",
			"approve_next": "yes_todo",
			"reject_next": "no_todo",
			"timeout_next": "late_todo",
		}
		if timeout_ms:
			config["timeout_ms"] = timeout_ms
		nodes = [
			{"id": "ask", "type": "human.approval", "config": config},
			todo("yes_todo", "approved", "yes"),
			todo("no_todo", "rejected", "no"),
			todo("late_todo", "timeout", "late"),
			_out("yes", "approved"),
			_out("no", "rejected"),
			_out("late", "timed out"),
		]
		return _graph(nodes, WEBHOOK)

	def setUp(self):
		super().setUp()
		self._runs = []

	def tearDown(self):
		frappe.db.rollback()
		for name in self._runs:
			frappe.db.delete("Notification Log", {"document_type": "Flow Run", "document_name": name})
		frappe.db.commit()
		super().tearDown()

	def _waiting_run(self, timeout_ms=None):
		flow_id = self._save(self._approval_graph(timeout_ms))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		self._runs.append(run.name)
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		frappe.db.commit()
		return run

	def _todos(self):
		return frappe.get_all("ToDo", filters={"description": ["like", f"{self.marker}%"]}, pluck="description")

	def _status(self, run):
		frappe.db.rollback()  # end this connection's snapshot: read what is really committed
		return frappe.db.get_value("Flow Run", run.name, "status")

	def _background_job_writes_notification(self, run):
		"""What the ``create_notification_log`` job does a moment after a run pauses: a new unread row, committed on another connection."""
		site = frappe.local.site

		def job():
			frappe.init(site=site)
			frappe.connect()
			try:
				doc = frappe.new_doc("Notification Log")
				doc.update(
					{
						"for_user": "Administrator",
						"type": "Alert",
						"subject": f"{self.marker} approval needed",
						"document_type": "Flow Run",
						"document_name": run.name,
						"read": 0,
					}
				)
				doc.name = frappe.generate_hash(length=10)
				doc.db_insert()
				frappe.db.commit()
			finally:
				frappe.destroy()

		t = threading.Thread(target=job)
		t.start()
		t.join(timeout=30)

	def _notification_read(self, run):
		frappe.db.rollback()
		return frappe.get_all("Notification Log", filters={"document_name": run.name}, pluck="read")

	# -- the reported failure ------------------------------------------------------------------

	def test_decision_holds_when_a_notification_row_appears_after_the_decision_began(self):
		run = self._waiting_run()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")  # this connection's snapshot starts here
		self._background_job_writes_notification(run)

		flow_engine.approve_flow_run(run.name, "approved", "fast approver")
		frappe.db.commit()

		self.assertEqual(self._status(run), "Success")
		self.assertEqual(self._todos(), [f"{self.marker} approved"])  # the approved route ran once
		record = json.loads(frappe.db.get_value("Flow Run", run.name, "context_json"))[flow_engine.NODE_OUTPUTS_KEY]["ask"]
		self.assertEqual(record["decision"], "approved")
		self.assertEqual(record["comment"], "fast approver")
		states = self._notification_read(run)  # the run's own approver notifications plus the late row: all cleared
		self.assertTrue(states and set(states) == {1}, states)

	def test_reject_holds_the_same_way(self):
		run = self._waiting_run()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")
		self._background_job_writes_notification(run)
		flow_engine.approve_flow_run(run.name, "rejected")
		frappe.db.commit()
		self.assertEqual(self._status(run), "Success")
		self.assertEqual(self._todos(), [f"{self.marker} rejected"])

	def test_timeout_holds_the_same_way(self):
		run = self._waiting_run(timeout_ms=60000)
		waiting = json.loads(frappe.db.get_value("Flow Run", run.name, "waiting"))
		waiting["timeout_at"] = (now_datetime() - timedelta(seconds=5)).isoformat()
		frappe.db.set_value("Flow Run", run.name, "waiting", json.dumps(waiting))
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")
		self._background_job_writes_notification(run)

		self.assertTrue(flow_engine.expire_approval(run.name))
		frappe.db.commit()
		self.assertEqual(self._status(run), "Success")
		self.assertEqual(self._todos(), [f"{self.marker} timeout"])

	def test_api_answers_the_moved_run_when_a_notification_row_appears_late(self):
		run = self._waiting_run()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")
		self._background_job_writes_notification(run)
		answer = flow_api.approve_flow_run(run.name)
		frappe.db.commit()
		self.assertEqual(answer["status"], "Success")
		self.assertEqual(self._status(run), "Success")

	# -- a decision that did not stick is an error, never a success ------------------------------

	def test_engine_refuses_a_decision_the_database_rolled_back(self):
		"""Any rollback between the claim and its commit (deadlock victim, snapshot conflict) must surface as an error."""
		run = self._waiting_run()
		real_build = flow_engine._build_run_context

		def build_then_lose_the_transaction(*args, **kwargs):
			ctx = real_build(*args, **kwargs)
			real_save = ctx.save_context

			def save_after_rollback():
				frappe.db.rollback()  # what the database does to a deadlock victim
				real_save()

			ctx.save_context = save_after_rollback
			return ctx

		with patch.object(flow_engine, "_build_run_context", build_then_lose_the_transaction):
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_engine.approve_flow_run(run.name, "approved")
		self.assertIn("could not be saved", str(ctx.exception))
		self.assertEqual(self._status(run), "Waiting Approval")  # still waiting, so the approver can try again
		self.assertEqual(self._todos(), [])
		# and the retry works
		flow_engine.approve_flow_run(run.name, "approved")
		frappe.db.commit()
		self.assertEqual(self._status(run), "Success")

	def test_api_refuses_a_decision_that_changed_nothing(self):
		run = self._waiting_run()
		with patch.object(flow_engine, "approve_flow_run", lambda *a, **k: None):
			for decide in (flow_api.approve_flow_run, flow_api.reject_flow_run):
				with self.assertRaises(frappe.ValidationError) as ctx:
					decide(run.name)
				self.assertIn("could not be saved", str(ctx.exception))
		self.assertEqual(self._status(run), "Waiting Approval")

	def test_loser_of_two_decisions_is_told_it_was_already_decided(self):
		run = self._waiting_run()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")  # stale snapshot
		site = frappe.local.site

		def winner():
			frappe.init(site=site)
			frappe.connect()
			frappe.set_user("Administrator")
			try:
				flow_engine.approve_flow_run(run.name, "approved", "winner")
				frappe.db.commit()
			finally:
				frappe.destroy()

		t = threading.Thread(target=winner)
		t.start()
		t.join(timeout=60)
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_engine.approve_flow_run(run.name, "rejected", "loser")
		self.assertIn("already decided", str(ctx.exception))

	# -- the notification tidy-up on its own ------------------------------------------------------

	def test_notification_tidy_up_never_raises(self):
		run = self._waiting_run()
		with patch.object(approval_notifications.frappe.db, "set_value", side_effect=frappe.QueryDeadlockError("conflict")):
			approval_notifications._clear_flow_notifications(run)  # retried once, then logged and dropped
		with patch.object(approval_notifications.frappe.db, "set_value", side_effect=RuntimeError("boom")):
			approval_notifications._clear_flow_notifications(run)

	def test_concurrent_state_write_conflict_is_a_plain_failed_step(self):
		"""Two runs saving the same state key at once: the loser's step fails in plain words, not with a raw database error."""
		run = self._waiting_run()
		with patch.object(flow_engine.flow_state, "set_state", side_effect=frappe.QueryDeadlockError("1020")):
			result = flow_engine._exec_state_set(run, {"id": "s"}, {"key": "k", "value": "v"}, {})
		self.assertEqual(result["status"], "failed")
		self.assertIn("another run was saving the same key", result["error"])
		self.assertNotIn("1020", result["error"])
