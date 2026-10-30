# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-14 (B): the approval card (title, labelled facts, note) every channel shows, and its ``details`` setting.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux14_card
"""

import copy
import json
import unittest
from unittest.mock import patch

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support import approval_card, approval_notifications
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out
from huf.ai.graph.validator import validate_flow_graph


def _ctx(data):
	return flow_engine.load_context(json.dumps(data))


DETAILS = [
	{"value": {"$from": "input.amount"}},
	{"label": "Who asked", "value": {"$from": "input.customer.name"}},
	{"value": {"$from": "input.note"}},
]


class TestDetailsFacts(unittest.TestCase):
	"""Pure: how the author's chosen details become labelled facts."""

	def setUp(self):
		self.ctx = _ctx({"amount": 120, "customer": {"name": "Ada Lovelace"}, "note": "", "paid": True})

	def test_label_value_pairs_in_the_authors_order(self):
		facts = approval_card.details_facts(DETAILS, self.ctx)
		self.assertEqual(facts, [{"label": "Amount", "value": "120"}, {"label": "Who asked", "value": "Ada Lovelace"}])

	def test_empty_and_unresolved_values_leave_no_row(self):
		facts = approval_card.details_facts([{"value": {"$from": "input.nothing"}}, {"value": {"$from": "input.note"}}], self.ctx)
		self.assertEqual(facts, [])

	def test_a_declared_label_wins_over_the_field_name(self):
		facts = approval_card.details_facts([{"value": {"$from": "input.amount"}}], self.ctx, {"amount": "Order amount"})
		self.assertEqual(facts, [{"label": "Order amount", "value": "120"}])

	def test_a_whole_record_reads_as_a_summary_and_nested_fields_use_their_parent(self):
		facts = approval_card.details_facts([{"value": {"$from": "input.customer"}}, {"value": {"$from": "input.customer.name"}}, {"value": {"$from": "input.paid"}}], self.ctx)
		self.assertEqual(facts, [{"label": "Customer", "value": "Ada Lovelace"}, {"label": "Customer", "value": "Ada Lovelace"}, {"label": "Paid", "value": "Yes"}])

	def test_at_most_six_rows(self):
		many = [{"label": f"L{i}", "value": i + 1} for i in range(10)]
		self.assertEqual(len(approval_card.details_facts(many, self.ctx)), approval_card.MAX_DETAILS)


class TestCardShape(unittest.TestCase):
	def test_api_card_has_exactly_title_facts_note_and_test_note(self):
		waiting = {"message": "Please check it.", "facts": [{"label": "Amount", "value": "120"}], "title": "Refund for Ada", "headline": "Refund for Ada"}
		card = approval_card.api_card("Refund review", waiting)
		self.assertEqual(card, {"title": "Refund for Ada", "facts": [{"label": "Amount", "value": "120"}], "note": "Please check it.", "test_note": None})

	def test_default_title_and_a_test_note(self):
		card = approval_card.api_card("Refund review", {"message": "ok?", "test_run": True, "test_note": "Test: you can approve this yourself"})
		self.assertEqual(card["title"], "Approval needed: Refund review")
		self.assertEqual(card["test_note"], "Test: you can approve this yourself")
		self.assertEqual(card["facts"], [])

	def test_a_test_runs_one_line_summary_carries_the_note_for_the_bell(self):
		card = approval_card.build_card("Refund review", {"message": "Check it", "test_run": True, "test_note": "Test: you can approve this yourself"})
		self.assertTrue(card["sentence"].endswith("Test: you can approve this yourself."))
		self.assertNotIn("Test:", card["note"])

	def test_a_flow_known_only_by_its_id_has_no_name_to_print(self):
		self.assertEqual(approval_card.api_card("flow-abc", {"message": "x"}, "flow-abc")["title"], "Approval needed")


class TestSchema(unittest.TestCase):
	def _graph(self, **config):
		cfg = {"message": "ok?", "approver_type": "role", "approver_role": "System Manager", "approve_next": "yes", "reject_next": "no", **config}
		graph = _graph([{"id": "ask", "type": "human.approval", "config": cfg}, _out("yes", "a"), _out("no", "b")], WEBHOOK)
		return graph

	def _errors(self, graph):
		return [e.code for e in validate_flow_graph(graph).errors]

	def test_title_and_details_are_accepted(self):
		self.assertEqual(self._errors(self._graph(title="Refund for {input.name}", details=copy.deepcopy(DETAILS))), [])

	def test_bad_shapes_are_refused(self):
		for bad in (
			{"title": ""},
			{"title": "x" * 121},
			{"details": [{"label": "No value"}]},
			{"details": [{"value": "a", "extra": 1}]},
			{"details": [{"value": "a"}] * 7},
			{"details": "amount"},
		):
			self.assertNotEqual(self._errors(self._graph(**bad)), [], bad)

	def test_a_detail_that_points_at_a_missing_step_is_refused(self):
		errors = self._errors(self._graph(details=[{"value": {"$from": "ghost.amount"}}]))
		self.assertTrue(errors, "a reference to a step that does not exist must not save")


class TestOnABench(WP11Base):
	def _graph(self, **config):
		cfg = {"message": "Please check {input.customer.name}'s refund.", "approver_type": "role", "approver_role": "System Manager", "approve_next": "yes", "reject_next": "no", **config}
		graph = _graph([{"id": "ask", "type": "human.approval", "config": cfg}, _out("yes", "approved"), _out("no", "rejected")], WEBHOOK)
		graph["contract"]["input_schema"] = {"type": "object", "properties": {"amount": {"type": "number", "title": "Order amount"}}}
		return graph

	def _waiting_run(self, **config):
		flow_id = self._save(self._graph(**config))
		frappe.db.set_value("Flow Definition", flow_id, "flow_name", "Refund review")
		run = flow_engine.create_flow_run(flow_id, payload={"amount": 120, "customer": {"name": "Ada Lovelace"}, "note": "rush"}, trigger_type="Webhook")
		with patch.object(flow_engine, "_send_approval_notifications"), patch("huf.ai.gateways.slack.flow_hooks.notify_approvers"):
			flow_engine.run_flow(run.name)
		run.reload()
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		return run

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_the_chosen_details_and_title_end_up_on_the_pause(self):
		run = self._waiting_run(title="Refund for {input.customer.name}", details=[{"value": {"$from": "input.amount"}}, {"label": "Who", "value": {"$from": "input.customer.name"}}])
		waiting = json.loads(run.waiting)
		self.assertEqual(waiting["title"], "Refund for Ada Lovelace")
		self.assertEqual(waiting["facts"], [{"label": "Order amount", "value": "120"}, {"label": "Who", "value": "Ada Lovelace"}])

	def test_without_details_the_card_picks_the_telling_facts_as_before(self):
		run = self._waiting_run()
		waiting = json.loads(run.waiting)
		self.assertIsNone(waiting["title"])
		labels = [f["label"] for f in waiting["facts"]]
		self.assertIn("Customer", labels)
		self.assertIn("Order amount", labels)  # the flow declares that title for the field

	def test_get_flow_run_and_the_pending_list_serve_the_same_card(self):
		run = self._waiting_run(title="Refund for Ada", details=[{"value": {"$from": "input.amount"}}])
		detail = flow_api.get_flow_run(run.name)["approval_card"]
		pending = next(p for p in flow_api.get_pending_approvals() if p["flow_run_id"] == run.name)["approval_card"]
		self.assertEqual(detail, pending)
		self.assertEqual(set(detail), {"title", "facts", "note", "test_note"})
		self.assertEqual(detail["title"], "Refund for Ada")
		self.assertEqual(detail["facts"], [{"label": "Order amount", "value": "120"}])
		self.assertEqual(detail["note"], "Please check Ada Lovelace's refund.")

	def test_a_run_that_is_not_waiting_has_no_card(self):
		run = self._waiting_run()
		flow_engine.approve_flow_run(run.name, "approved")
		self.assertIsNone(flow_api.get_flow_run(run.name)["approval_card"])

	def test_the_bell_and_the_email_say_the_same_thing(self):
		run = self._waiting_run(title="Refund for Ada", details=[{"value": {"$from": "input.amount"}}])
		waiting = json.loads(run.waiting)
		sent = {}
		with (
			patch.object(approval_notifications, "enqueue_create_notification", side_effect=lambda email, doc: sent.setdefault("bell", doc)),
			patch.object(approval_notifications, "is_email_notifications_enabled", return_value=True),
			patch("frappe.sendmail", side_effect=lambda **kw: sent.setdefault("mail", kw)),
		):
			approval_notifications._send_approval_notifications(run, {}, {}, waiting)
		self.assertEqual(sent["bell"]["subject"], "Refund for Ada")
		self.assertEqual(sent["mail"]["subject"], "Refund for Ada")
		for text in (sent["bell"]["email_content"], sent["mail"]["message"]):
			self.assertIn("Order amount", text)
			self.assertIn("120", text)
			self.assertNotIn("$from", text)
			self.assertNotIn("input.", text)

	def test_the_slack_card_uses_the_same_title_and_facts(self):
		run = self._waiting_run(title="Refund for Ada", details=[{"value": {"$from": "input.amount"}}])
		waiting = json.loads(run.waiting)
		card = approval_card.build_card("Refund review", waiting)
		self.assertEqual(card["headline"], "Refund for Ada")
		details = approval_card.slack_details(card)
		self.assertIn("Order amount: 120", details)
		self.assertIn("Please check Ada Lovelace's refund.", details)
