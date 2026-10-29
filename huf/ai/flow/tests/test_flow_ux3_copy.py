# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-3: plain-language text people read: error mapping, step titles, text placeholders and approval messages.

The first classes are table-driven and need no site; ``TestApprovalMessagesOnBench`` runs a real flow with a
nested payload to an approval and checks the pending-approvals API, the bell notification, the email and the
Slack card text.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux3_copy
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.code_node import error_text
from huf.ai.flow.integrations import friendly_tool_error
from huf.ai.flow.support import approval_card
from huf.ai.flow.support.router_text import render_text_refs, text_ref_warnings
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out
from huf.ai.graph import error_copy as ec
from huf.ai.graph.executor import GraphContext

# Words that must never reach a person: Python names and syntax, engine words, node ids.
JARGON = ("Traceback", "Error:", "Exception", "NoneType", "KeyError", "PermissionError", "ImportError", "node_", "Node '", "on_error")


class TestErrorMapping(unittest.TestCase):
	def test_plain_error_table(self):
		cases = [
			# integrations and credentials (WP12 wording kept)
			("Google Sheets is not connected. Connect it in Integrations.", "Google Sheets is not connected. Connect it in Integrations."),
			("Slack is not connected: add the bot token in Integrations.", "Slack is not connected. Connect it in Integrations."),
			("Google Drive rejected the saved credentials (token expired or revoked). Reconnect Google Drive in Integrations.", "Google Drive did not accept the saved connection. Reconnect it in Integrations."),
			("Gmail needs the gmail.send permission: reconnect with that scope.", "Gmail needs another permission. Reconnect it in Integrations and accept everything it asks for."),
			("slack error: invalid_auth", "Slack is not connected. Connect it in Integrations."),
			("channel_not_found", "Slack could not find that channel. Pick another channel in the step."),
			("Requests to private/internal addresses are not allowed", "That address is on a private network and cannot be reached from a flow. Use a public address, or ask your admin to allow it."),
			# python / engine noise
			("ValueError: bad input", "The code received a value it could not use. Check the data the step receives."),
			("state.set: another run was saving the same key", "another run was saving the same key"),
			("<b>Nope</b>   spaced", "Nope spaced"),
			("Traceback (most recent call last):\n  File x", "The step stopped with an unexpected error. Run it again, and ask an admin if it keeps happening."),
			("", ""),
			(None, ""),
		]
		for raw, expected in cases:
			with self.subTest(raw=raw):
				self.assertEqual(ec.plain_error(raw), expected)

	def test_friendly_tool_error_keeps_wp12_wording(self):
		raw = "Credential not found for service 'google_sheets': set GOOGLE_SHEETS_X"
		self.assertEqual(friendly_tool_error(raw), "Google Sheets is not connected. Connect it in Integrations.")
		self.assertEqual(friendly_tool_error("HTTP 500"), "HTTP 500")
		self.assertEqual(
			friendly_tool_error("Slack is not connected: add token in Integrations."),
			"Slack is not connected. Connect it in Integrations.",
		)

	def test_describe_exception_table(self):
		cases = [
			(PermissionError("x"), "You do not have permission to do this. Ask an admin for access."),
			(TimeoutError("x"), "The other side took too long to answer. Try again in a moment."),
			(ConnectionError("x"), "Could not reach the other side. Check the address and your connection, then try again."),
			(KeyError("order_id"), "A value this step needs is missing (order_id). Check the data coming into it."),
			(RuntimeError(""), "Something went wrong in this step and no reason was given. Run it again, and ask an admin if it keeps happening."),
			(ValueError("Google Sheets is not connected. Connect it in Integrations."), "Google Sheets is not connected. Connect it in Integrations."),
		]
		for exc, expected in cases:
			with self.subTest(exc=repr(exc)):
				self.assertEqual(ec.describe_exception(exc), expected)

	def test_describe_run_error_table(self):
		titles = {"n1": "Fetch page", "n2": "Send email"}
		cases = [
			("Node 'n1' of type 'tool.call' failed and declares no on_error successor: Google Sheets is not connected. Connect it in Integrations.", "Fetch page failed: Google Sheets is not connected. Connect it in Integrations."),
			("Node 'n2' of type 'tool.call' failed and declares no on_error successor", "Send email failed: The step did not finish."),
			("Node 'zz' of type 'tool.call' failed and declares no on_error successor: boom", "A step failed: boom"),
			("Node 'n1' of type 'condition' did not resolve a successor", "Fetch page has no next step. Connect it to one."),
			("Node 'n1' not found in definition", "The run reached a step that no longer exists. Reconnect the flow and run it again."),
			("Hop limit reached (100)", "The run took more than 100 steps, so it was stopped. Check for a loop that never ends."),
			("Unknown node type: x.y", "This flow has a step this version cannot run. Delete it and save again."),
			("Run is not advanceable (status: Success)", "This run can no longer continue."),
			("Send email failed: x", "Send email failed: x"),
			("", "The run did not finish."),
		]
		for raw, expected in cases:
			with self.subTest(raw=raw):
				self.assertEqual(ec.describe_run_error(raw, titles), expected)

	def test_no_title_repetition(self):
		self.assertEqual(ec.step_failed_sentence("Read sheet", "Read sheet needs a list"), "Read sheet needs a list")
		self.assertEqual(ec.step_failed_sentence("Loop", '"Loop" stopped at item 2: x'), '"Loop" stopped at item 2: x')


class TestCodeStepErrors(unittest.TestCase):
	TRACE = 'Traceback (most recent call last):\n  File "<huf-exec>", line 3, in <module>\n{last}'

	def test_code_error_sentences(self):
		cases = [
			("PermissionError: absolute path '/etc/passwd' is outside the sandbox workspace", "The code tried to open a file outside its allowed folder ('/etc/passwd') (line 3). Keep file work inside the flow's own folder."),
			("ImportError: Import of module 'socket' is not permitted by execution profile policy", "The code tried to use 'socket', which this step is not allowed to use (line 3). Remove it from the code, or pick a different run mode for the step."),
			("ModuleNotFoundError: No module named 'pandas'", "The code needs 'pandas', which is not installed here (line 3). Use only the basics built into Python."),
			("KeyError: 'a'", "The code looked for 'a', which is not in its data (line 3). Check the data the step receives."),
			("NameError: name 'x' is not defined", "The code uses 'x' before giving it a value (line 3). Check the spelling or set it first."),
			("ZeroDivisionError: division by zero", "The code divided by zero (line 3). Check the numbers it works with."),
			("TypeError: unsupported operand", "The code mixed up kinds of values, such as text and numbers (line 3). Convert the values first."),
			("CustomError: weird", "The code stopped with an error (line 3): weird"),
		]
		for last, expected in cases:
			with self.subTest(last=last):
				got = error_text("Error", self.TRACE.format(last=last))
				self.assertEqual(got, expected)
				for word in ("Traceback", "Error:"):
					self.assertNotIn(word, got)

	def test_bare_exception_message_is_rewritten_too(self):
		got = error_text("Error", "PermissionError: absolute path '/etc/passwd' is outside the sandbox workspace")
		self.assertTrue(got.startswith("The code tried to open a file outside its allowed folder"))
		self.assertNotIn("PermissionError", got)

	def test_limits_unchanged(self):
		self.assertIn("ran longer than 30 seconds", error_text("Timeout", "", {"max_wall_time_s": 30}))
		self.assertIn("256 MB", error_text("OOM", "", {"max_memory_mb": 256}))
		self.assertEqual(error_text("Killed", ""), "The code was stopped before it finished.")


class TestStepTitles(unittest.TestCase):
	def test_step_title(self):
		cases = [
			({"id": "n1", "type": "tool.call", "_label": "Email the customer"}, "Email the customer"),
			({"id": "n1", "type": "tool.call", "config": {"tool_id": "gmail_send_email"}}, "Send email"),
			({"id": "n1", "type": "tool.call", "_label": "n1", "config": {"tool_id": "slack_send_message"}}, "Send Slack message"),
			({"id": "node_1699", "type": "condition", "_label": "node_1699"}, "Condition"),
			({"id": "x", "type": "human.approval"}, "Wait for approval"),
			({"id": "x", "type": "nonsense"}, "this step"),
			(None, "this step"),
		]
		for node, expected in cases:
			with self.subTest(node=node):
				self.assertEqual(ec.step_title(node), expected)

	def test_validation_sentences_name_the_step_not_the_id(self):
		graph = {"nodes": [{"id": "node_77", "type": "human.approval", "_label": "Approve refund"}]}
		err = SimpleNamespace(code="UNREACHABLE_NODE", node_id="node_77", field=None, message="x")
		text = ec.describe_error(graph, err)
		self.assertEqual(text, 'The "Approve refund" step is not connected to the start of the flow. Connect it or delete it.')
		self.assertNotIn("node_77", text)
		untitled = {"nodes": [{"id": "node_77", "type": "condition"}]}
		self.assertEqual(ec.describe_error(untitled, err), 'The "Condition" step is not connected to the start of the flow. Connect it or delete it.')

	def test_every_code_has_a_sentence_without_ids(self):
		graph = {"nodes": [{"id": "n9", "type": "foreach", "_label": "Each order"}]}
		for code in ("DANGLING_TARGET", "DUPLICATE_NODE_ID", "CYCLE", "FORWARD_REFERENCE", "PROFILE_VIOLATION", "BAD_EXPRESSION", "SOMETHING_NEW"):
			text = ec.describe_error(graph, SimpleNamespace(code=code, node_id="n9", field=None, message="raw [CODE] n9"))
			with self.subTest(code=code):
				self.assertIn("Each order", text)
				self.assertNotIn("n9", text)
				self.assertNotIn("[", text)


class TestTextPlaceholders(unittest.TestCase):
	def _ctx(self):
		ctx = GraphContext({"order": {"customer": {"name": "Ada Lovelace"}, "total": 450, "lines": [{"name": "A"}, {"name": "B"}]}, "when": "2026-10-29T10:42:00Z", "paid": True})
		ctx.node_outputs["fetch"] = {"rows": [1, 2, 3]}
		return ctx

	def test_render_table(self):
		cases = [
			("Total {input.order.total}", "Total 450"),
			("Customer {input.order.customer}", "Customer Ada Lovelace"),
			("Customer {input.order.customer.name}", "Customer Ada Lovelace"),
			("Order {input.order}", "Order Customer: Ada Lovelace, Total: 450, Lines: 2 items: A and B"),
			("Lines {input.order.lines}", "Lines 2 items: A and B"),
			("When {input.when}", "When 29 Oct 2026, 10:42 UTC"),
			("Paid {input.paid}", "Paid Yes"),
			("Rows {fetch.rows}", "Rows 3 items: 1, 2 and 1 more"),
			# unresolved: an empty value, never the literal braces
			("Missing [{input.nothing}]", "Missing []"),
			("Unknown [{unknown.path}]", "Unknown []"),
			("Not run yet [{later.value}]", "Not run yet []"),
			# braces that are not placeholders stay
			("Keep {{input.order}} as is", "Keep {{input.order}} as is"),
			("A set {1, 2}", "A set {1, 2}"),
			("", ""),
		]
		for text, expected in cases:
			with self.subTest(text=text):
				out = render_text_refs(text, self._ctx())
				self.assertEqual(out, expected)

	def test_nothing_json_in_rendered_text(self):
		out = render_text_refs("{input.order} {fetch.rows}", self._ctx())
		for junk in ('{"', '":', "[{", "None"):
			self.assertNotIn(junk, out)

	def test_save_warnings(self):
		defn = {
			"nodes": [
				{"id": "start", "type": "trigger.webhook"},
				{"id": "ask", "type": "human.approval", "_label": "Approve refund", "config": {"message": "Refund {input.total} for {customer.name}?"}},
				{"id": "pick", "type": "router.llm", "config": {"prompt": "Decide on {input.text} and {ask.decision} and {ghost.value}"}},
				{"id": "end", "type": "output", "config": {"value": "{ignored.field}"}},
			]
		}
		self.assertEqual(
			text_ref_warnings(defn),
			[
				'Approve refund: the message uses {customer.name}, which has no data behind it, so it will be left empty. Insert data from an earlier step instead.',
				'Choose a path with AI: the instruction uses {ghost.value}, which has no data behind it, so it will be left empty. Insert data from an earlier step instead.',
			],
		)
		self.assertEqual(text_ref_warnings(None), [])
		self.assertEqual(text_ref_warnings({"nodes": "bad"}), [])


class TestApprovalCard(unittest.TestCase):
	def test_card_from_stored_waiting(self):
		waiting = {
			"message": "Please check this refund.",
			"flow_name": "Refund review",
			"facts": [{"label": "Customer", "value": "Ada Lovelace"}, {"label": "Total", "value": "450"}],
		}
		card = approval_card.build_card(None, waiting)
		self.assertEqual(card["headline"], "Approval needed: Refund review")
		self.assertEqual(card["sentence"], "Please check this refund. Customer: Ada Lovelace, Total: 450.")
		self.assertEqual(approval_card.slack_details(card), "Please check this refund.\nCustomer: Ada Lovelace\nTotal: 450")

	def test_card_for_a_run_that_paused_before_facts_existed(self):
		card = approval_card.build_card("Refund review", {"message": ""})
		self.assertEqual(card["sentence"], "Refund review is waiting for your decision.")
		self.assertEqual(card["facts"], [])

	def test_html_is_escaped(self):
		html = approval_card.facts_html([{"label": "<b>x</b>", "value": "a & <script>"}])
		self.assertNotIn("<script>", html)
		self.assertIn("&amp;", html)

	def test_slack_details_capped(self):
		card = approval_card.build_card("F", {"message": "m" * 300, "facts": [{"label": "L", "value": "v" * 100}] * 3})
		self.assertLessEqual(len(approval_card.slack_details(card)), 400)


class TestApprovalMessagesOnBench(WP11Base):
	"""A nested-object payload to an approval step: bell API, run page data, notification log, email and Slack text."""

	PAYLOAD = {
		"order": {"id": 1042, "customer": {"name": "Ada Lovelace", "email": "ada@example.com"}, "total": 450, "status": "pending", "notes": None},
		"items": [{"name": "Widget"}, {"name": "Gadget"}, {"name": "Gizmo"}],
		"api_token": "sk-should-never-appear",
	}

	def _graph_with_approval(self, message):
		nodes = [
			{
				"id": "ask",
				"_label": "Approve refund",
				"type": "human.approval",
				"config": {
					"message": message,
					"approver_type": "role",
					"approver_role": "System Manager",
					"approve_next": "yes",
					"reject_next": "no",
				},
			},
			_out("yes", "approved"),
			_out("no", "rejected"),
		]
		return _graph(nodes, WEBHOOK)

	def _waiting_run(self, message="Refund {input.order} to the customer?"):
		flow_id = self._save(self._graph_with_approval(message))
		frappe.db.set_value("Flow Definition", flow_id, "flow_name", "Refund review")
		run = flow_engine.create_flow_run(flow_id, payload=self.PAYLOAD, trigger_type="Webhook")
		self._runs = getattr(self, "_runs", []) + [run.name]
		flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		frappe.db.commit()
		return run

	def tearDown(self):
		frappe.db.rollback()
		for name in getattr(self, "_runs", []):
			frappe.db.delete("Notification Log", {"document_type": "Flow Run", "document_name": name})
		super().tearDown()

	def assertPlain(self, text):
		for junk in JARGON + ('{"', '":', "[{", "sk-should-never-appear", "None", "null"):
			self.assertNotIn(junk, text)

	def test_waiting_data_is_sentence_and_facts(self):
		run = self._waiting_run()
		waiting = json.loads(run.waiting)
		self.assertEqual(waiting["headline"], "Approval needed: Refund review")
		self.assertNotIn("title", waiting)  # "title" is a retired name; the heading is "headline"
		self.assertEqual(waiting["step_title"], "Approve refund")
		self.assertEqual(waiting["flow_name"], "Refund review")
		labels = [f["label"] for f in waiting["facts"]]
		self.assertEqual(labels[:3], ["Customer", "Order ID", "Total"])
		self.assertIn({"label": "Customer", "value": "Ada Lovelace"}, waiting["facts"])
		self.assertIn("Customer: Ada Lovelace", waiting["message"] + " " + waiting["context_summary"])
		self.assertPlain(waiting["message"] + waiting["context_summary"])
		# the whole object in the message is a summary, not JSON
		self.assertEqual(waiting["message"], "Refund Customer: Ada Lovelace, Total: 450, Status: pending to the customer?")

	def test_pending_approvals_api_reads_as_a_sentence_with_facts(self):
		run = self._waiting_run()
		rows = [r for r in flow_api.get_pending_approvals() if r["flow_run_id"] == run.name]
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(row["title"], "Approval needed: Refund review")
		self.assertEqual(row["flow_name"], "Refund review")
		self.assertIn("Customer: Ada Lovelace", row["message"])
		self.assertIn("Total: 450", row["message"])
		self.assertEqual(row["message"], row["instructions"])
		self.assertTrue(row["facts"])
		self.assertPlain(row["message"])
		self.assertNotIn(run.flow_id, row["message"])
		self.assertNotIn(run.name, row["message"])

	def test_old_waiting_without_new_keys_still_reads_well(self):
		run = self._waiting_run()
		frappe.db.set_value("Flow Run", run.name, "waiting", json.dumps({"type": "approval", "node_id": "ask", "message": "ok?", "approver_type": "role", "approver_role": "System Manager"}))
		row = [r for r in flow_api.get_pending_approvals() if r["flow_run_id"] == run.name][0]
		self.assertEqual(row["title"], "Approval needed: Refund review")
		self.assertEqual(row["message"], "ok?")

	def _capture_notifications(self, run):
		sent = {"log": [], "mail": []}
		approvers = [frappe.session.user]
		with patch("huf.ai.flow.support.approval_notifications.enqueue_create_notification", side_effect=lambda u, d: sent["log"].append((u, d))), \
			patch("huf.ai.flow.support.approval_notifications.is_email_notifications_enabled", return_value=True), \
			patch("huf.ai.flow.support.approval_notifications.frappe.sendmail", side_effect=lambda **kw: sent["mail"].append(kw)), \
			patch("huf.ai.flow.support.approval_notifications.frappe.get_all", side_effect=lambda dt, **kw: approvers if dt == "User" else approvers):
			flow_engine._send_approval_notifications(run, {"id": "ask"}, {}, json.loads(run.waiting))
		return sent

	def test_bell_and_email_text(self):
		run = self._waiting_run()
		sent = self._capture_notifications(run)
		self.assertEqual(len(sent["log"]), 1)
		self.assertEqual(len(sent["mail"]), 1)
		(_user, doc), mail = sent["log"][0], sent["mail"][0]
		for subject in (doc["subject"], mail["subject"]):
			self.assertEqual(subject, "Approval needed: Refund review")
			self.assertNotIn("Approval Required", subject)
		for body in (doc["email_content"], mail["message"]):
			self.assertIn("Ada Lovelace", body)
			self.assertIn("450", body)
			self.assertIn("Review and decide", body)
			self.assertNotIn(run.name, body.replace(f"run={run.name}", ""))  # the run id only inside the link
			self.assertNotIn("Run ID", body)
			self.assertNotIn("Flow:", body)
			self.assertPlain(body.replace("&quot;", ""))
		self.assertIn(f"run={run.name}", doc["email_content"])

	def test_slack_card_text(self):
		run = self._waiting_run()
		from huf.ai.gateways import approvals as ap
		from huf.ai.gateways.slack import blocks as bk

		captured = {}
		with patch.object(ap, "_notify", side_effect=lambda kind, name, users, title, details, ttl: captured.update(title=title, details=details, name=name) or 1), \
			patch.object(ap, "_role_users", return_value=["Administrator"]):
			ap.notify_flow_run_approvers(run)
		self.assertEqual(captured["title"], "Approval needed: Refund review")
		self.assertIn("Customer: Ada Lovelace", captured["details"])
		self.assertIn("Total: 450", captured["details"])
		self.assertPlain(captured["details"])
		self.assertNotIn(run.name, captured["details"])
		card = bk.approval_card(captured["title"], captured["details"], "session-1")
		labels = [e["text"]["text"] for e in card.blocks[1]["elements"]]
		self.assertEqual(labels, ["Approve", "Reject"])
