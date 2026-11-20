# Track-Item: SEC-10
"""REAL-BENCH tests for run_agent_draft_test (Try it) and the draft purge job.

Only the model call (huf.ai.run.RunProvider.run, the provider/litellm boundary used by
integration._execute_agent_run) is mocked; the Agent Run insert, the run_kind Select
validation and the cleanup really execute.

Run: bench --site <site> run-tests --module huf.ai.tests.test_agent_draft_test_bench
(requires `bench migrate` so Agent Run.run_kind has the draft_test option)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.agent import agent_form_api
from huf.testing.factories import make_agent, make_agent_conversation, make_agent_run

REPLY = "mocked draft reply"


def _fake_result():
	return SimpleNamespace(new_items=[], final_output=REPLY, usage=None, cost=0)


def _draft_counts():
	return {
		"runs": frappe.db.count("Agent Run", {"run_kind": "draft_test"}),
		"convs": frappe.db.count("Agent Conversation", {"channel": "draft_test"}),
		"msgs": frappe.db.count(
			"Agent Message",
			{"conversation": ["in", frappe.get_all("Agent Conversation", {"channel": "draft_test"}, pluck="name") or ["__none__"]]},
		),
	}


class TestAgentDraftTestBench(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.cache.delete_value(frappe.cache.make_key("huf_draft_test_rl:Administrator"))
		self.agent = make_agent()
		self.before = _draft_counts()

	def tearDown(self):
		frappe.set_user("Administrator")
		convs = frappe.get_all("Agent Conversation", {"agent": self.agent.name}, pluck="name")
		for c in convs:
			runs = frappe.get_all("Agent Run", {"conversation": c}, pluck="name")
			if runs:
				frappe.db.delete("Agent Tool Call", {"agent_run": ["in", runs]})
			frappe.db.delete("Agent Message", {"conversation": c})
			frappe.db.delete("Agent Run", {"conversation": c})
			frappe.db.delete("Agent Conversation", {"name": c})
		frappe.db.delete("Agent Run", {"agent": self.agent.name})
		frappe.db.delete("Agent", {"name": self.agent.name})
		frappe.db.commit()

	def test_success_returns_reply_and_leaves_nothing(self):
		with patch("huf.ai.run.RunProvider.run", new=AsyncMock(return_value=_fake_result())):
			res = agent_form_api.run_agent_draft_test(self.agent.name, "hello")
		self.assertIn(REPLY, res["response"] or "")
		self.assertIsNone(res["agent_run_id"])
		self.assertEqual(_draft_counts(), self.before)
		self.assertFalse(frappe.db.exists("Agent Run", {"agent": self.agent.name}))
		self.assertFalse(frappe.db.exists("Agent Conversation", {"agent": self.agent.name}))

	def test_failure_inside_run_leaves_nothing(self):
		with patch("huf.ai.run.RunProvider.run", new=AsyncMock(side_effect=RuntimeError("boom"))):
			try:
				agent_form_api.run_agent_draft_test(self.agent.name, "hello")
			except Exception:
				pass
		self.assertEqual(_draft_counts(), self.before)
		self.assertFalse(frappe.db.exists("Agent Run", {"agent": self.agent.name}))
		self.assertFalse(frappe.db.exists("Agent Conversation", {"agent": self.agent.name}))

	def test_purge_removes_stale_draft_and_spares_normal(self):
		old = add_to_date(now_datetime(), hours=-3)
		stale = make_agent_conversation(agent=self.agent.name, channel="draft_test")
		stale_run = make_agent_run(conversation=stale.name, agent=self.agent.name, run_kind="draft_test")
		normal = make_agent_conversation(agent=self.agent.name, channel="Chat")
		normal_run = make_agent_run(conversation=normal.name, agent=self.agent.name)
		for dt, n in (
			("Agent Conversation", stale.name),
			("Agent Run", stale_run.name),
			("Agent Conversation", normal.name),
			("Agent Run", normal_run.name),
		):
			frappe.db.set_value(dt, n, "creation", old, update_modified=False)

		agent_form_api.purge_draft_test_records()

		self.assertFalse(frappe.db.exists("Agent Conversation", stale.name))
		self.assertFalse(frappe.db.exists("Agent Run", stale_run.name))
		self.assertTrue(frappe.db.exists("Agent Conversation", normal.name))
		self.assertTrue(frappe.db.exists("Agent Run", normal_run.name))

	def test_purge_never_deletes_non_draft_conversation_of_a_draft_run(self):
		old = add_to_date(now_datetime(), hours=-3)
		normal = make_agent_conversation(agent=self.agent.name, channel="Chat")
		run = make_agent_run(conversation=normal.name, agent=self.agent.name, run_kind="draft_test")
		frappe.db.set_value("Agent Run", run.name, "creation", old, update_modified=False)

		agent_form_api.purge_draft_test_records()

		self.assertFalse(frappe.db.exists("Agent Run", run.name))
		self.assertTrue(frappe.db.exists("Agent Conversation", normal.name))

	def test_purge_sweeps_orphan_draft_conversation(self):
		old = add_to_date(now_datetime(), hours=-3)
		conv = make_agent_conversation(agent=self.agent.name, channel="draft_test")
		frappe.db.set_value("Agent Conversation", conv.name, "creation", old, update_modified=False)
		agent_form_api.purge_draft_test_records()
		self.assertFalse(frappe.db.exists("Agent Conversation", conv.name))
