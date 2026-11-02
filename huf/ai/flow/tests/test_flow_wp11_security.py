# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""WP11 on a real bench: approval / resume races, terminal-status protection, the publish guard for
document-event and web-request flows, and the document-event payload filter.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_wp11_security
"""

import inspect
import json
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow import publish_guard, triggers

LIMITS = {
	"max_nodes": 20,
	"max_rows": 1000,
	"max_output_bytes": 100_000,
	"max_parallel_calls": 1,
	"max_foreach_iterations": 1,
	"max_external_calls": 5,
	"max_writes": 5,
	"max_wall_time_ms": 5000,
	"fail_closed": True,
}


def _contract(http="none"):
	return {
		"input_schema": {"type": "object"},
		"output_schema": {"type": "object"},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [{"doctype": "ToDo"}], "http": http, "code": "none"},
		"limits": LIMITS,
	}


def _out(node_id, value):
	return {"id": node_id, "type": "output", "config": {"value": value}}


def _graph(nodes, trigger, http="none"):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": [{"id": "start", "next": nodes[0]["id"], **trigger}, *nodes],
		"contract": _contract(http),
	}


SECRET = "test-webhook-secret-0123456789abcdef"
WEBHOOK = {"type": "trigger.webhook", "config": {"method": "POST", "secret": SECRET}}
DOC_EVENT = {"type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "after_insert"}}


class WP11Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._flows = []
		self._users = []
		self.marker = f"_wp11 {frappe.generate_hash(length=8)}"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.commit()  # drop this connection's old snapshot: other connections changed rows meanwhile
		for flow_id in self._flows:
			frappe.db.delete("Flow Run", {"flow_id": flow_id})
			if frappe.db.exists("Flow Definition", flow_id):
				frappe.delete_doc("Flow Definition", flow_id, ignore_permissions=True, force=True)
		frappe.db.delete("ToDo", {"description": ["like", "_wp11 %"]})
		for email in self._users:
			frappe.db.delete("Huf User Role", {"user": email})
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _save(self, graph, active=False):
		flow_id = f"_test-wp11-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(flow_id, graph)
		self._flows.append(flow_id)
		if active:
			doc = frappe.get_doc("Flow Definition", flow_id)
			doc.status = "Active"
			doc.save(ignore_permissions=True)
		return flow_id


# ---------------------------------------------------------------------------
# Approval and resume races
# ---------------------------------------------------------------------------


class TestApprovalRaces(WP11Base):
	def _approval_graph(self, timeout_ms=60000):
		def todo(node_id, text, nxt):
			return {
				"id": node_id,
				"type": "doc.create",
				"config": {"doctype": "ToDo", "fields": {"description": f"{self.marker} {text}"}},
				"next": nxt,
			}

		nodes = [
			{
				"id": "ask",
				"type": "human.approval",
				"config": {
					"message": "ok?",
					"approver_type": "role",
					"approver_role": "System Manager",
					"approve_next": "yes_todo",
					"reject_next": "no_todo",
					"timeout_next": "late_todo",
					"timeout_ms": timeout_ms,
				},
			},
			todo("yes_todo", "approved", "yes"),
			todo("no_todo", "rejected", "no"),
			todo("late_todo", "timeout", "late"),
			_out("yes", "approved"),
			_out("no", "rejected"),
			_out("late", "timed out"),
		]
		return _graph(nodes, WEBHOOK)

	def _waiting_run(self):
		flow_id = self._save(self._approval_graph())
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		frappe.db.commit()
		return run

	def _todos(self):
		return frappe.get_all("ToDo", filters={"description": ["like", f"{self.marker}%"]}, pluck="description")

	def _expire_deadline(self, run):
		waiting = json.loads(frappe.db.get_value("Flow Run", run.name, "waiting"))
		waiting["timeout_at"] = (now_datetime() - timedelta(seconds=5)).isoformat()
		frappe.db.set_value("Flow Run", run.name, "waiting", json.dumps(waiting))
		frappe.db.commit()

	def test_two_concurrent_decisions_exactly_one_wins_and_downstream_runs_once(self):
		run = self._waiting_run()
		site = frappe.local.site
		barrier = threading.Barrier(2)
		results = {}

		def decide(label, decision):
			frappe.init(site=site)
			frappe.connect()
			frappe.set_user("Administrator")
			try:
				barrier.wait(timeout=10)
				flow_engine.approve_flow_run(run.name, decision, label)
				frappe.db.commit()
				results[label] = "won"
			except Exception as exc:  # the loser is refused
				frappe.db.rollback()
				results[label] = f"refused: {exc}"
			finally:
				frappe.destroy()

		threads = [
			threading.Thread(target=decide, args=("a", "approved")),
			threading.Thread(target=decide, args=("b", "rejected")),
		]
		for t in threads:
			t.start()
		for t in threads:
			t.join(timeout=60)

		self.assertEqual(sorted(v.split(":")[0] for v in results.values()), ["refused", "won"], results)
		frappe.db.rollback()  # end this connection's old snapshot
		fresh = frappe.get_doc("Flow Run", run.name)
		self.assertEqual(fresh.status, "Success", fresh.last_error)
		todos = self._todos()
		self.assertEqual(len(todos), 1, todos)  # the downstream step of the winning route ran exactly once
		record = json.loads(fresh.context_json)[flow_engine.NODE_OUTPUTS_KEY]["ask"]
		winner = [k for k, v in results.items() if v == "won"][0]
		self.assertEqual(record["comment"], winner)

	def test_loser_with_a_stale_snapshot_gets_a_clear_refusal(self):
		"""The loser read the run before the winner committed; its own re-read is stale, only the UPDATE tells."""
		run = self._waiting_run()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")  # snapshot taken
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
		frappe.db.rollback()
		self.assertEqual(self._todos(), [f"{self.marker} approved"])
		record = json.loads(frappe.db.get_value("Flow Run", run.name, "context_json"))[flow_engine.NODE_OUTPUTS_KEY]["ask"]
		self.assertEqual(record["comment"], "winner")

	def test_stale_loser_is_stopped_by_the_conditional_update(self):
		"""A caller that already read 'Waiting Approval' (stale snapshot) cannot move a run another caller decided."""
		run = self._waiting_run()
		stale = frappe.get_doc("Flow Run", run.name)  # read before the other decision
		flow_engine.approve_flow_run(run.name, "approved", "first")
		frappe.db.commit()
		self.assertEqual(stale.status, "Waiting Approval")  # the stale copy still believes it
		moved = flow_engine._transition_run(
			stale, {"status": "Running", "waiting": None}, from_statuses=("Waiting Approval",)
		)
		self.assertFalse(moved)
		self.assertEqual(len(self._todos()), 1)
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_engine.approve_flow_run(run.name, "rejected", "second")
		self.assertIn("not waiting for approval", str(ctx.exception))
		self.assertEqual(len(self._todos()), 1)

	def test_expired_approval_cannot_be_decided(self):
		run = self._waiting_run()
		self._expire_deadline(run)
		with self.assertRaises(frappe.ValidationError) as ctx:
			flow_engine.approve_flow_run(run.name, "approved", "too late")
		self.assertIn("This approval has expired", str(ctx.exception))
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Waiting Approval")
		self.assertEqual(self._todos(), [])
		# the timeout path still owns it
		self.assertTrue(flow_engine.expire_approval(run.name))
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._todos(), [f"{self.marker} timeout"])

	def test_decision_then_expiry_sweep_runs_downstream_once(self):
		run = self._waiting_run()
		flow_engine.approve_flow_run(run.name, "approved")
		frappe.db.commit()
		# the sweeper arrives later, even long after the original deadline
		self.assertFalse(flow_engine.expire_approval(run.name, now=now_datetime() + timedelta(days=2)))
		self.assertEqual(self._todos(), [f"{self.marker} approved"])

	def test_expiry_then_decision_runs_downstream_once(self):
		run = self._waiting_run()
		self._expire_deadline(run)
		self.assertTrue(flow_engine.expire_approval(run.name))
		frappe.db.commit()
		with self.assertRaises(frappe.ValidationError):
			flow_engine.approve_flow_run(run.name, "approved")
		self.assertEqual(self._todos(), [f"{self.marker} timeout"])

	def test_held_run_lock_refuses_a_second_decision(self):
		run = self._waiting_run()
		self.assertTrue(flow_engine._acquire_run_lock(run.name))
		try:
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_engine.approve_flow_run(run.name, "approved")
			self.assertIn("deciding this approval right now", str(ctx.exception))
		finally:
			flow_engine._release_run_lock(run.name)
		self.assertEqual(self._todos(), [])

	def _waiting_user_run(self):
		flow_id = self._save(self._approval_graph())
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		frappe.db.set_value(
			"Flow Run",
			run.name,
			{"status": "Waiting User", "current_node_id": "ask", "waiting": json.dumps({"resume_node": "yes_todo"})},
		)
		frappe.db.commit()
		return run

	def test_two_concurrent_resumes_advance_once(self):
		run = self._waiting_user_run()
		site = frappe.local.site
		barrier = threading.Barrier(2)
		results = []

		def resume():
			frappe.init(site=site)
			frappe.connect()
			frappe.set_user("Administrator")
			try:
				barrier.wait(timeout=10)
				flow_engine.resume_flow_run(run.name)
				frappe.db.commit()
				results.append("won")
			except Exception:
				frappe.db.rollback()
				results.append("refused")
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=resume) for _ in range(2)]
		for t in threads:
			t.start()
		for t in threads:
			t.join(timeout=60)
		self.assertEqual(sorted(results), ["refused", "won"])
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Success")
		self.assertEqual(self._todos(), [f"{self.marker} approved"])


# ---------------------------------------------------------------------------
# Terminal statuses and "Mark as failed"
# ---------------------------------------------------------------------------


class TestTerminalStatusProtection(WP11Base):
	def _run(self, status):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		frappe.db.set_value("Flow Run", run.name, "status", status)
		run.reload()
		return run

	def test_finished_runs_cannot_be_failed_or_completed_again(self):
		for status in ("Success", "Failed"):
			run = self._run(status)
			self.assertFalse(flow_engine._fail_flow_run(run, "late failure"))
			self.assertFalse(flow_engine._complete_flow_run(run))
			run.reload()
			self.assertEqual(run.status, status)
			self.assertNotEqual(run.last_error, "late failure")

	def test_cancelled_is_terminal_too(self):
		run = self._run("Running")
		self.assertTrue(flow_engine._transition_run(run, {"status": "Cancelled"}))
		self.assertFalse(flow_engine._complete_flow_run(run))
		self.assertFalse(flow_engine._fail_flow_run(run, "x"))
		run.reload()
		self.assertEqual(run.status, "Cancelled")

	def test_run_flow_does_not_revive_a_terminal_run(self):
		run = self._run("Failed")
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Failed")

	def test_worker_finishing_after_mark_as_failed_does_not_overwrite_it(self):
		run = self._run("Running")
		frappe.db.set_value("Flow Run", run.name, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		worker_copy = frappe.get_doc("Flow Run", run.name)
		out = flow_api.mark_flow_run_failed(run.name)
		self.assertEqual(out["status"], "Failed")
		self.assertFalse(flow_engine._complete_flow_run(worker_copy))
		run.reload()
		self.assertEqual(run.status, "Failed")
		self.assertIn("Marked as failed", run.last_error)

	def test_mark_failed_loses_to_a_worker_that_finished_meanwhile(self):
		run = self._run("Running")
		frappe.db.set_value("Flow Run", run.name, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)

		real_is_stale = flow_api._is_stale

		def finish_then_report_stale(status, modified):
			# the live worker completes the run between the staleness check and the write
			frappe.db.sql("update `tabFlow Run` set status='Success' where name=%s", run.name)
			return real_is_stale(status, modified)

		with patch.object(flow_api, "_is_stale", finish_then_report_stale):
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_api.mark_flow_run_failed(run.name)
		self.assertIn("already finished", str(ctx.exception))
		frappe.db.rollback()

	def test_mark_failed_refuses_while_a_worker_holds_the_run_lock(self):
		run = self._run("Running")
		frappe.db.set_value("Flow Run", run.name, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		self.assertTrue(flow_engine._acquire_run_lock(run.name))
		try:
			with self.assertRaises(frappe.ValidationError) as ctx:
				flow_api.mark_flow_run_failed(run.name)
			self.assertIn("being worked on right now", str(ctx.exception))
		finally:
			flow_engine._release_run_lock(run.name)
		run.reload()
		self.assertEqual(run.status, "Running")


# ---------------------------------------------------------------------------
# Webhook: header only, flow id required, minimum secret length
# ---------------------------------------------------------------------------


class TestWebhookHardening(WP11Base):
	def _call(self, endpoint, headers=None, args=None, flow_id=None, method="POST"):
		request = frappe._dict(
			args=args or {}, form={}, headers=headers or {}, method=method, get_data=lambda **kw: b"{}"
		)
		with patch.object(frappe, "request", request, create=True):
			with patch("huf.ai.flow.triggers.start_flow_run") as start:
				start.return_value = SimpleNamespace(name="FR-X", status="Queued")
				try:
					return inspect.unwrap(getattr(flow_api, endpoint))(flow_id), start
				except frappe.AuthenticationError as exc:
					return exc, start

	def test_header_secret_accepted_query_secret_rejected(self):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK), active=True)
		ok, start = self._call("flow_webhook", {"X-Huf-Secret": SECRET}, flow_id=flow_id)
		self.assertEqual(ok, {"flow_run_id": "FR-X", "status": "Queued"})
		denied, start = self._call("flow_webhook", {}, {"secret": SECRET}, flow_id=flow_id)
		self.assertIsInstance(denied, flow_api.WebhookDenied)
		self.assertEqual(denied.http_status_code, 403)
		start.assert_not_called()

	def test_clean_endpoint_needs_a_flow_id_and_does_not_search_by_secret(self):
		self._save(_graph([_out("done", "ok")], WEBHOOK), active=True)
		denied, start = self._call("flow_webhook_clean", {"X-Huf-Secret": SECRET})
		self.assertIsInstance(denied, flow_api.WebhookDenied)
		start.assert_not_called()

	def test_wrong_secret_and_unknown_flow_answer_identically(self):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK), active=True)
		wrong, _ = self._call("flow_webhook", {"X-Huf-Secret": "x" * 40}, flow_id=flow_id)
		unknown, _ = self._call("flow_webhook", {"X-Huf-Secret": SECRET}, flow_id="no-such-flow")
		self.assertEqual((type(wrong), str(wrong)), (type(unknown), str(unknown)))

	def test_endpoints_are_rate_limited_and_public(self):
		for fn in (flow_api.flow_webhook, flow_api.flow_webhook_clean):
			self.assertTrue(hasattr(fn, "__wrapped__"), "rate_limit wrapper missing")
		self.assertEqual((flow_api.WEBHOOK_RATE_LIMIT, flow_api.WEBHOOK_RATE_WINDOW_SECONDS), (60, 60))

	def test_secret_shorter_than_32_cannot_be_saved(self):
		bad = {"type": "trigger.webhook", "config": {"method": "POST", "secret": "x" * 31}}
		with self.assertRaises(frappe.ValidationError):
			flow_api.save_flow_definition(f"_test-wp11-{frappe.generate_hash(length=8)}", _graph([_out("d", "ok")], bad))


# ---------------------------------------------------------------------------
# Publish guard: document-event triggers and web request steps
# ---------------------------------------------------------------------------


class TestPublishGuard(WP11Base):
	def _editor(self, with_capability):
		"""A Frappe user who may write flows (Huf Manager) whose Huf role does or does not hold the capability."""
		email = f"wp11-{'cap' if with_capability else 'nocap'}-{frappe.generate_hash(length=6)}@example.com"
		role_name = f"_wp11 editor {frappe.generate_hash(length=5)}"
		caps = ["flows.use", "flows.create", "flows.manage"] + (["flows.publish_sensitive"] if with_capability else [])
		frappe.get_doc(
			{
				"doctype": "Huf Role",
				"role_name": role_name,
				"permissions": [{"capability": c} for c in caps],
			}
		).insert(ignore_permissions=True)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Wp11",
				"send_welcome_email": 0,
				"roles": [{"role": "Huf Manager"}],
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		frappe.db.delete("Huf User Role", {"user": email})
		frappe.get_doc({"doctype": "Huf User Role", "user": email, "huf_role": role_name, "enabled": 1}).insert(
			ignore_permissions=True
		)
		self._users.append(email)
		self.addCleanup(lambda: frappe.db.exists("Huf Role", role_name) and frappe.delete_doc("Huf Role", role_name, force=True, ignore_permissions=True))
		frappe.cache().delete_value(f"huf_user_capabilities::{email}")
		return email

	def _publish_as(self, email, flow_id):
		frappe.set_user(email)
		try:
			return flow_api.publish_flow(flow_id)
		finally:
			frappe.set_user("Administrator")

	def _http_graph(self):
		node = {
			"id": "call",
			"type": "tool.call",
			"config": {"tool_id": "http_request", "input": {"url": "https://example.com/hook"}},
			"next": "done",
		}
		return _graph([node, _out("done", "ok")], WEBHOOK, http=["example.com"])

	def test_pure_detection(self):
		self.assertEqual(publish_guard.sensitive_labels(_graph([_out("d", "ok")], WEBHOOK)), [])
		self.assertEqual(publish_guard.sensitive_labels(_graph([_out("d", "ok")], DOC_EVENT)), ["a document-event trigger"])
		self.assertEqual(publish_guard.sensitive_labels(self._http_graph()), ["a web request step"])

	def test_user_without_capability_cannot_publish_doc_event_flow(self):
		email = self._editor(False)
		flow_id = self._save(_graph([_out("d", "ok")], DOC_EVENT))
		with self.assertRaises(frappe.PermissionError) as ctx:
			self._publish_as(email, flow_id)
		self.assertIn("document-event trigger", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Flow Definition", flow_id, "status"), "Draft")

	def test_user_without_capability_cannot_publish_web_request_flow(self):
		email = self._editor(False)
		flow_id = self._save(self._http_graph())
		with self.assertRaises(frappe.PermissionError) as ctx:
			self._publish_as(email, flow_id)
		self.assertIn("web request step", str(ctx.exception))

	def test_user_without_capability_can_publish_a_plain_flow(self):
		email = self._editor(False)
		flow_id = self._save(_graph([_out("d", "ok")], WEBHOOK))
		self.assertEqual(self._publish_as(email, flow_id)["status"], "Active")

	def test_user_with_capability_can_publish_sensitive_flows(self):
		email = self._editor(True)
		for graph in (_graph([_out("d", "ok")], DOC_EVENT), self._http_graph()):
			flow_id = self._save(graph)
			self.assertEqual(self._publish_as(email, flow_id)["status"], "Active")

	def test_huf_manager_and_system_manager_hold_the_capability_by_default(self):
		from huf.permissions import DEFAULT_ROLE_CAPABILITIES, has_capability

		self.assertIn("flows.publish_sensitive", DEFAULT_ROLE_CAPABILITIES["Huf Manager"])
		self.assertNotIn("flows.publish_sensitive", DEFAULT_ROLE_CAPABILITIES["Huf User"])
		self.assertNotIn("flows.publish_sensitive", DEFAULT_ROLE_CAPABILITIES["Huf Viewer"])
		self.assertTrue(has_capability("Administrator", "flows.publish_sensitive"))

	def test_editing_an_unrelated_step_of_an_active_flow_needs_no_capability(self):
		email = self._editor(False)
		graph = _graph([_out("d", "ok")], DOC_EVENT)
		flow_id = self._save(graph, active=True)  # published by Administrator
		frappe.set_user(email)
		try:
			graph["nodes"][1]["config"]["value"] = "changed"
			flow_api.save_flow_definition(flow_id, graph)
			# but adding a web request step to the published flow is refused
			with self.assertRaises(frappe.PermissionError):
				flow_api.save_flow_definition(flow_id, self._http_graph_with(DOC_EVENT))
		finally:
			frappe.set_user("Administrator")

	def _http_graph_with(self, trigger):
		g = self._http_graph()
		g["nodes"][0] = {"id": "start", "next": "call", **trigger}
		return g

	def test_doc_event_dispatch_skips_an_owner_who_lost_the_capability(self):
		email = self._editor(False)
		flow_id = self._save(_graph([_out("d", "ok")], DOC_EVENT), active=True)
		frappe.db.set_value("Flow Definition", flow_id, "owner", email)
		triggers.clear_trigger_cache()
		todo = frappe.get_doc({"doctype": "ToDo", "description": f"{self.marker} src"})
		todo.insert(ignore_permissions=True)
		with patch("frappe.enqueue") as enqueue:
			triggers.run_doc_event_flows(todo, "after_insert")
		mine = [c for c in enqueue.call_args_list if c.kwargs.get("flow_id") == flow_id]
		self.assertEqual(mine, [])


# ---------------------------------------------------------------------------
# Document-event payload: only what the owner may read, never Password fields
# ---------------------------------------------------------------------------


class TestDocEventPayload(WP11Base):
	CHILD = "Wp11 Probe Row"
	PARENT = "Wp11 Probe Doc"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if not frappe.db.exists("DocType", cls.CHILD):
			frappe.get_doc(
				{
					"doctype": "DocType",
					"name": cls.CHILD,
					"module": "Huf",
					"custom": 1,
					"istable": 1,
					"fields": [
						{"fieldname": "note", "fieldtype": "Data", "label": "Note"},
						{"fieldname": "token", "fieldtype": "Password", "label": "Token"},
						{"fieldname": "finance", "fieldtype": "Data", "label": "Finance", "permlevel": 1},
					],
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("DocType", cls.PARENT):
			frappe.get_doc(
				{
					"doctype": "DocType",
					"name": cls.PARENT,
					"module": "Huf",
					"custom": 1,
					"fields": [
						{"fieldname": "title", "fieldtype": "Data", "label": "Title"},
						{"fieldname": "api_key", "fieldtype": "Password", "label": "Api Key"},
						{"fieldname": "salary", "fieldtype": "Data", "label": "Salary", "permlevel": 1},
						{"fieldname": "rows", "fieldtype": "Table", "label": "Rows", "options": cls.CHILD},
					],
					"permissions": [
						{"role": "Huf Manager", "read": 1, "permlevel": 0},
						{"role": "System Manager", "read": 1, "permlevel": 0},
						{"role": "System Manager", "read": 1, "permlevel": 1},
					],
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in (cls.PARENT, cls.CHILD):
			if frappe.db.exists("DocType", name):
				frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _doc(self):
		return SimpleNamespace(
			doctype=self.PARENT,
			name="P-1",
			as_dict=lambda: {
				"doctype": self.PARENT,
				"name": "P-1",
				"owner": "someone@example.com",
				"__unsaved": 1,
				"title": "visible",
				"api_key": "*****",
				"salary": "100000",
				"rows": [{"doctype": self.CHILD, "name": "r1", "note": "n", "token": "*****", "finance": "9"}],
			},
		)

	def _manager_only(self):
		email = f"wp11-mgr-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Wp11", "send_welcome_email": 0, "roles": [{"role": "Huf Manager"}]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email

	def test_owner_without_the_permission_level_loses_those_fields(self):
		payload = triggers.build_doc_event_payload(self._doc(), self._manager_only())
		self.assertEqual(payload["title"], "visible")
		self.assertNotIn("salary", payload)
		self.assertNotIn("api_key", payload)
		self.assertEqual(payload["name"], "P-1")
		self.assertNotIn("__unsaved", payload)
		row = payload["rows"][0]
		self.assertEqual(row["note"], "n")
		self.assertNotIn("token", row)
		self.assertNotIn("finance", row)

	def test_password_fields_are_removed_even_for_a_system_manager(self):
		payload = triggers.build_doc_event_payload(self._doc(), "Administrator")
		self.assertEqual(payload["salary"], "100000")  # readable at permlevel 1 for a System Manager
		self.assertEqual(payload["rows"][0]["finance"], "9")
		self.assertNotIn("api_key", payload)
		self.assertNotIn("token", payload["rows"][0])


# ---------------------------------------------------------------------------
# Document-event lookup cache
# ---------------------------------------------------------------------------


class TestDocEventCacheInvalidation(WP11Base):
	def _warm(self):
		"""Plant a recognisably stale lookup; a cleared cache is rebuilt from the database without it."""
		frappe.cache().set_value(triggers.DOC_EVENT_CACHE_KEY, json.dumps({"__stale__": {}}), expires_in_sec=300)
		self.assertIn("__stale__", triggers.get_doc_event_index())

	def _cold(self):
		return "__stale__" not in triggers.get_doc_event_index()

	def _user(self):
		email = f"wp11-cache-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Wp11", "send_welcome_email": 0, "roles": [{"role": "Huf User"}]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return user

	def test_hooks_are_registered(self):
		from huf import hooks

		def flat(value):
			return value if isinstance(value, list) else [value]

		target = "huf.ai.flow.triggers.clear_trigger_cache"
		self.assertIn(target, flat(hooks.doc_events["User"]["on_update"]))
		self.assertIn(target, flat(hooks.doc_events["User"]["on_trash"]))
		self.assertIn(target, flat(hooks.doc_events["Has Role"]["after_insert"]))
		self.assertIn(target, flat(hooks.doc_events["Has Role"]["on_trash"]))

	def test_disabling_a_user_clears_the_cache(self):
		user = self._user()
		self._warm()
		user.enabled = 0
		user.save(ignore_permissions=True)
		self.assertTrue(self._cold())

	def test_changing_a_users_roles_clears_the_cache(self):
		user = self._user()
		self._warm()
		user.add_roles("Huf Manager")
		self.assertTrue(self._cold())

	def test_publishing_and_unpublishing_clears_the_cache(self):
		flow_id = self._save(_graph([_out("d", "ok")], WEBHOOK))
		self._warm()
		flow_api.publish_flow(flow_id)
		self.assertTrue(self._cold())
		self._warm()
		flow_api.unpublish_flow(flow_id)
		self.assertTrue(self._cold())
