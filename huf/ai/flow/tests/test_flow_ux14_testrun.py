# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-14 on a bench: a test run reads for real and never sends or changes anything.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux14_testrun
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.testrun import gate
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out

BOGUS = "nobody@bogus-address.invalid"


def _tool(node_id, tool_id, input_, nxt):
	return {"id": node_id, "type": "tool.call", "config": {"tool_id": tool_id, "input": input_}, "next": nxt}


class Base(WP11Base):
	def _run(self, graph, mode, payload=None, trigger_type="Webhook"):
		flow_id = self._save(graph)
		run = flow_engine.create_flow_run(flow_id, payload=payload or {}, trigger_type=trigger_type, mode=mode)
		flow_engine.run_flow(run.name)
		run.reload()
		return run

	def _step_output(self, run, node_id):
		return json.loads(run.context_json or "{}").get(flow_engine.NODE_OUTPUTS_KEY, {}).get(node_id)


class TestTestRunSkipsSideEffects(Base):
	def _mail_graph(self):
		return _graph(
			[
				_tool("mail", "gmail_send_email", {"to": BOGUS, "subject": "Hello", "body": "Hi"}, "done"),
				_out("done", {"mail": {"$from": "mail"}}),
			],
			WEBHOOK,
		)

	def test_an_email_step_is_simulated_and_the_tool_is_never_called(self):
		with patch.object(flow_engine, "execute_tool") as tool:
			run = self._run(self._mail_graph(), "test")
		tool.assert_not_called()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(run.run_mode, "Test")
		out = self._step_output(run, "mail")
		self.assertTrue(out["simulated"])
		self.assertEqual(out["summary"], f"Would send email to {BOGUS}")

	def test_a_real_run_still_calls_the_tool(self):
		with patch.object(flow_engine, "execute_tool", return_value={"success": True, "result": {"id": "m1"}}) as tool:
			run = self._run(self._mail_graph(), "real")
		tool.assert_called_once()
		self.assertEqual(run.run_mode, "Real")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertNotIn("simulated", self._step_output(run, "mail") or {})

	def test_reads_run_for_real_in_a_test(self):
		graph = _graph(
			[_tool("look", "gsheets_read", {"spreadsheet_id": "abc"}, "done"), _out("done", {"rows": {"$from": "look"}})],
			WEBHOOK,
		)
		with patch.object(flow_engine, "execute_tool", return_value={"success": True, "result": {"values": [[1]]}}) as tool:
			run = self._run(graph, "test")
		tool.assert_called_once()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._step_output(run, "look"), {"values": [[1]]})

	def test_http_get_reads_and_post_is_simulated(self):
		graph = _graph(
			[
				_tool("get", "http_request", {"url": "https://example.com/a", "method": "GET"}, "post"),
				_tool("post", "http_request", {"url": "https://example.com/b", "method": "POST"}, "done"),
				_out("done", {"ok": True}),
			],
			WEBHOOK,
			http=["http_request"],
		)
		with patch.object(flow_engine, "execute_tool", return_value={"success": True, "result": {"status_code": 200}}) as tool:
			run = self._run(graph, "test")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(tool.call_count, 1)
		self.assertEqual(tool.call_args.args[1]["method"], "GET")
		self.assertTrue(self._step_output(run, "post")["simulated"])

	def test_creating_a_document_is_simulated(self):
		graph = _graph(
			[
				{"id": "todo", "type": "doc.create", "config": {"doctype": "ToDo", "fields": {"description": "{marker} x"}}, "next": "done"},
				_out("done", {"todo": {"$from": "todo"}}),
			],
			WEBHOOK,
		)
		graph["nodes"][1]["config"]["fields"]["description"] = f"{self.marker} test run"
		run = self._run(graph, "test")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertFalse(frappe.get_all("ToDo", filters={"description": ["like", f"{self.marker}%"]}))
		self.assertTrue(self._step_output(run, "todo")["simulated"])

	def test_a_real_run_creates_the_document(self):
		graph = _graph(
			[
				{"id": "todo", "type": "doc.create", "config": {"doctype": "ToDo", "fields": {"description": f"{self.marker} real"}}, "next": "done"},
				_out("done", {"ok": True}),
			],
			WEBHOOK,
		)
		run = self._run(graph, "real")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertTrue(frappe.get_all("ToDo", filters={"description": ["like", f"{self.marker}%"]}))

	def test_conditions_and_state_run_for_real(self):
		graph = _graph(
			[
				{"id": "cond", "type": "condition", "config": {"expression": "input['n'] > 1", "on_true": "yes", "on_false": "no"}},
				_out("yes", "big"),
				_out("no", "small"),
			],
			WEBHOOK,
		)
		run = self._run(graph, "test", payload={"n": 5})
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(run.current_node_id, "yes")

	def test_a_bad_mode_is_refused_by_the_api(self):
		graph = self._mail_graph()
		flow_id = self._save(graph)
		with self.assertRaises(frappe.ValidationError):
			flow_api.run_flow(flow_id, {}, mode="dry")

	def test_the_api_takes_a_mode_and_lists_it(self):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		result = flow_api.run_flow(flow_id, {}, mode="test")
		self.assertEqual(frappe.db.get_value("Flow Run", result["flow_run_id"], "run_mode"), "Test")
		self.assertEqual(flow_api.get_flow_run(result["flow_run_id"])["run_mode"], "Test")
		listed = flow_api.list_flow_runs(flow_id=flow_id, run_mode="test")
		self.assertEqual([r["name"] for r in listed], [result["flow_run_id"]])
		self.assertEqual(flow_api.list_flow_runs(flow_id=flow_id, run_mode="real"), [])


class TestAgentToolsInATest(Base):
	def test_a_test_runs_agent_tool_that_would_send_is_simulated(self):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="test")
		agent_run = frappe.get_doc({"doctype": "Agent Run", "status": "Started", "prompt": "x", "flow_run": run.name, "flow_id": flow_id}).insert(ignore_permissions=True)
		ctx = {"agent_run_id": agent_run.name}
		sim = gate.agent_tool_gate("gmail_send_email", {"to": BOGUS}, ctx)
		self.assertIsNotNone(sim)
		self.assertEqual(json.loads(sim)["summary"], f"Would send email to {BOGUS}")
		self.assertIsNone(gate.agent_tool_gate("gmail_get_emails", {}, ctx))  # a read goes through
		self.assertIsNone(gate.agent_tool_gate("gmail_send_email", {"to": BOGUS}, {"agent_run_id": None}))
		self.assertIsNone(gate.agent_tool_gate("gmail_send_email", {"to": BOGUS}, SimpleNamespace(context={})))

	def test_a_real_runs_agent_tools_are_untouched(self):
		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="real")
		agent_run = frappe.get_doc({"doctype": "Agent Run", "status": "Started", "prompt": "x", "flow_run": run.name, "flow_id": flow_id}).insert(ignore_permissions=True)
		self.assertIsNone(gate.agent_tool_gate("gmail_send_email", {"to": BOGUS}, {"agent_run_id": agent_run.name}))

	def test_the_slack_tool_gate_uses_it(self):
		from huf.ai.gateways.slack import flow_hooks

		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="test")
		agent_run = frappe.get_doc({"doctype": "Agent Run", "status": "Started", "prompt": "x", "flow_run": run.name, "flow_id": flow_id}).insert(ignore_permissions=True)
		result = flow_hooks.tool_gate("slack_send_message", {"channel": "#x", "text": "hi"}, {"agent_run_id": agent_run.name}, False)
		self.assertIn("Would post a Slack message", result)


class TestApprovalInATest(Base):
	def _graph(self):
		return _graph(
			[
				{
					"id": "ask",
					"type": "human.approval",
					"config": {
						"message": "ok?",
						"approver_type": "user",
						"approver_users": ["someone.else@example.com"],
						"approve_next": "yes",
						"reject_next": "no",
					},
				},
				_out("yes", "approved"),
				_out("no", "rejected"),
			],
			WEBHOOK,
		)

	def test_pauses_for_real_with_a_note_and_sends_no_notifications(self):
		with (
			patch.object(flow_engine, "_send_approval_notifications") as email,
			patch("huf.ai.gateways.slack.flow_hooks.notify_approvers") as slack,
			patch("huf.ai.flow.testrun.gate.notify_test_owner") as bell,
		):
			run = self._run(self._graph(), "test")
		email.assert_not_called()
		slack.assert_not_called()
		bell.assert_called_once()
		self.assertEqual(run.status, "Waiting Approval")
		waiting = json.loads(run.waiting)
		self.assertTrue(waiting["test_run"])
		self.assertEqual(waiting["test_note"], "Test: you can approve this yourself")

	def test_a_real_run_still_notifies(self):
		with (
			patch.object(flow_engine, "_send_approval_notifications") as email,
			patch("huf.ai.gateways.slack.flow_hooks.notify_approvers") as slack,
		):
			run = self._run(self._graph(), "real")
		email.assert_called_once()
		slack.assert_called_once()
		self.assertNotIn("test_run", json.loads(run.waiting))

	def test_the_person_who_started_a_test_may_approve_it_but_a_real_run_still_refuses(self):
		test_run = self._run(self._graph(), "test")
		real_run = self._run(self._graph(), "real")
		for run, allowed in ((test_run, True), (real_run, False)):
			waiting = json.loads(run.waiting)
			reason = flow_engine.check_approver(waiting, "Administrator", {"Guest"})
			self.assertEqual(reason is None, allowed, waiting)
		# somebody else who is not an approver is still refused in a test
		waiting = json.loads(test_run.waiting)
		self.assertIsNotNone(flow_engine.check_approver(waiting, "other.person@example.com", {"Guest"}))

	def test_approving_a_test_continues_the_test(self):
		run = self._run(self._graph(), "test")
		flow_engine.approve_flow_run(run.name, "approved", "fine")
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(run.run_mode, "Test")

	def test_a_test_nobody_decides_notifies_only_the_owner_in_the_bell(self):
		with patch("frappe.desk.doctype.notification_log.notification_log.enqueue_create_notification") as create:
			run = self._run(self._graph(), "test")
		create.assert_called_once()
		self.assertEqual(create.call_args.args[1]["document_name"], run.name)
		self.assertTrue(create.call_args.args[1]["subject"].startswith("Test: "))


class TestTestRunsDoNotCount(Base):
	def test_the_flow_cards_last_run_ignores_tests(self):
		from huf.ai.flow.listing.cards import _last_runs

		flow_id = self._save(_graph([_out("done", "ok")], WEBHOOK))
		flow_engine.run_flow(flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="real").name)
		frappe.db.commit()
		real_name = frappe.get_all("Flow Run", filters={"flow_id": flow_id, "run_mode": "Real"}, pluck="name")[0]
		flow_engine.run_flow(flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="test").name)
		frappe.db.commit()
		last = _last_runs([flow_id], {})
		self.assertEqual(last[flow_id]["status"], "Success")
		# only one run counts: the real one
		rows = frappe.db.sql(
			"select r.name from `tabFlow Run` r inner join (select flow_id, max(creation) latest from `tabFlow Run` where flow_id = %s and run_mode != 'Test' group by flow_id) m on m.flow_id=r.flow_id and m.latest=r.creation",
			(flow_id,),
		)
		self.assertEqual([r[0] for r in rows], [real_name])
