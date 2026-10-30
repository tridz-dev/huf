# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-14 (C): the End step's outcome (label and tone) is recorded on the run and served by the run APIs.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux14_outcome
"""

import json
import unittest

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.runs.outcome import resolve_outcome, stored_outcome
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out
from huf.ai.graph.validator import validate_flow_graph


def _ctx(data):
	return flow_engine.load_context(json.dumps(data))


class TestResolveOutcome(unittest.TestCase):
	def test_no_outcome_declared(self):
		self.assertIsNone(resolve_outcome(None))
		self.assertIsNone(resolve_outcome("Approved"))

	def test_label_and_tone(self):
		self.assertEqual(resolve_outcome({"label": "Rejected", "tone": "bad"}), {"label": "Rejected", "tone": "bad"})

	def test_defaults_are_finished_and_neutral(self):
		self.assertEqual(resolve_outcome({}), {"label": "Finished", "tone": "neutral"})
		self.assertEqual(resolve_outcome({"tone": "good"}), {"label": "Finished", "tone": "good"})
		self.assertEqual(resolve_outcome({"label": "Done", "tone": "red"}), {"label": "Done", "tone": "neutral"})

	def test_placeholders_are_filled_in_and_long_text_is_cut(self):
		out = resolve_outcome({"label": "Refund for {input.customer}", "tone": "good"}, _ctx({"customer": "Ada"}))
		self.assertEqual(out["label"], "Refund for Ada")
		self.assertEqual(len(resolve_outcome({"label": "x" * 200})["label"]), 60)

	def test_stored_outcome_reads_a_row_or_a_document(self):
		self.assertEqual(stored_outcome({"outcome_label": "Approved", "outcome_tone": "good"}), {"label": "Approved", "tone": "good"})
		self.assertIsNone(stored_outcome({"outcome_label": "", "outcome_tone": "good"}))
		self.assertEqual(stored_outcome(frappe._dict(outcome_label="Late", outcome_tone="")), {"label": "Late", "tone": "neutral"})


class TestSchema(unittest.TestCase):
	def _errors(self, outcome):
		graph = _graph([{"id": "end", "type": "output", "config": {"value": "x", "outcome": outcome}}], WEBHOOK)
		return [e.code for e in validate_flow_graph(graph).errors]

	def test_accepted(self):
		for outcome in ({"label": "Approved", "tone": "good"}, {"label": "Rejected"}, {"tone": "bad"}, {}):
			self.assertEqual(self._errors(outcome), [], outcome)

	def test_refused(self):
		for outcome in ({"label": ""}, {"label": "x" * 61}, {"tone": "red"}, {"colour": "red"}, "Approved"):
			self.assertNotEqual(self._errors(outcome), [], outcome)


class TestOnABench(WP11Base):
	def _graph(self, approve_outcome=None, reject_outcome=None):
		def end(node_id, text, outcome):
			config = {"value": text}
			if outcome:
				config["outcome"] = outcome
			return {"id": node_id, "type": "output", "config": config}

		ask = {
			"id": "ask",
			"type": "human.approval",
			"config": {"message": "ok?", "approver_type": "role", "approver_role": "System Manager", "approve_next": "yes", "reject_next": "no"},
		}
		return _graph([ask, end("yes", "approved", approve_outcome), end("no", "rejected", reject_outcome)], WEBHOOK)

	def _decided(self, decision, **outcomes):
		flow_id = self._save(self._graph(**outcomes))
		run = flow_engine.create_flow_run(flow_id, payload={"customer": "Ada"}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		flow_engine.approve_flow_run(run.name, decision)
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		return flow_id, run

	def test_a_rejected_run_records_the_outcome_of_the_end_it_reached(self):
		flow_id, run = self._decided("rejected", approve_outcome={"label": "Approved", "tone": "good"}, reject_outcome={"label": "Rejected for {input.customer}", "tone": "bad"})
		self.assertEqual((run.outcome_label, run.outcome_tone), ("Rejected for Ada", "bad"))
		self.assertEqual(flow_api.get_flow_run(run.name)["outcome"], {"label": "Rejected for Ada", "tone": "bad"})
		listed = {r["name"]: r for r in flow_api.list_flow_runs(flow_id=flow_id)}
		self.assertEqual(listed[run.name]["outcome"], {"label": "Rejected for Ada", "tone": "bad"})
		self.assertNotIn("outcome_label", listed[run.name])
		page = flow_api.list_flow_runs_page(flow_id=flow_id)
		self.assertEqual(page["items"][0]["outcome"], {"label": "Rejected for Ada", "tone": "bad"})

	def test_an_approved_run_records_its_own_end(self):
		_flow_id, run = self._decided("approved", approve_outcome={"label": "Approved", "tone": "good"}, reject_outcome={"label": "Rejected", "tone": "bad"})
		self.assertEqual((run.outcome_label, run.outcome_tone), ("Approved", "good"))

	def test_an_end_without_an_outcome_records_nothing_and_the_decision_still_names_the_result(self):
		_flow_id, run = self._decided("rejected")
		self.assertFalse(run.outcome_label)
		self.assertEqual(flow_api.get_flow_run(run.name)["outcome"], {"label": "Rejected", "tone": "bad"})

	def test_an_end_with_only_a_tone_says_finished(self):
		flow_id = self._save(_graph([{"id": "end", "type": "output", "config": {"value": "x", "outcome": {"tone": "good"}}}], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		self.assertEqual(flow_api.get_flow_run(run.name)["outcome"], {"label": "Finished", "tone": "good"})

	def test_a_plain_run_has_no_outcome(self):
		flow_id = self._save(_graph([_out("end", "x")], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		flow_engine.run_flow(run.name)
		self.assertIsNone(flow_api.get_flow_run(run.name)["outcome"])

	def test_a_test_run_records_it_too_and_a_failed_run_shows_none(self):
		flow_id = self._save(_graph([{"id": "end", "type": "output", "config": {"value": "x", "outcome": {"label": "Sent", "tone": "good"}}}], WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook", mode="test")
		flow_engine.run_flow(run.name)
		self.assertEqual(flow_api.get_flow_run(run.name)["outcome"], {"label": "Sent", "tone": "good"})
		run.reload()
		run.db_set("status", "Failed")
		self.assertIsNone(flow_api.get_flow_run(run.name)["outcome"])
