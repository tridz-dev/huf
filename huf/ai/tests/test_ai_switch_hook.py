"""AI kill switch, ``huf_ai_feature_map`` caps and memory retention purge (H-W5-05)."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from huf.ai.agent.integration import _run_queued_agent, run_agent_sync
from huf.ai.flow.engine import _exec_agent_run
from huf.ai.memory.purge import purge_expired_memory
from huf.ai.run_budget import (
	AIDisabled,
	RunBudget,
	ai_policy,
	assert_ai_enabled,
	get_current_budget,
	set_current_budget,
)


def _hooked(*providers):
	"""Register ``providers`` (callables) as the ``huf_ai_feature_map`` hook."""
	by_path = {f"fake.provider_{i}": fn for i, fn in enumerate(providers)}
	return (
		patch("huf.ai.run_budget.frappe.get_hooks", return_value=list(by_path)),
		patch("huf.ai.run_budget.frappe.get_attr", side_effect=by_path.__getitem__),
	)


class TestAISwitch(IntegrationTestCase):
	def policy(self, *providers, agent="a1"):
		hooks, attr = _hooked(*providers)
		with hooks, attr:
			return ai_policy(agent)

	def test_default_is_on_and_uncapped(self):
		self.assertEqual(self.policy(), {"enabled": True, "spend_cap_usd": 0.0})

	def test_site_switch_blocks_a_new_run_with_reason(self):
		with patch.dict(frappe.local.conf, {"huf_ai_disabled": 1}):
			with self.assertRaises(AIDisabled) as caught:
				RunBudget.from_agent(Mock(max_turns=5))
		self.assertEqual(str(caught.exception), "ai_disabled")

	def test_switch_off_stops_an_already_queued_run_before_the_provider_call(self):
		run = {"agent": "a1", "budget_deadline_at": add_days(now_datetime(), 1)}
		with patch.dict(frappe.local.conf, {"huf_ai_disabled": 1}):
			budget = RunBudget.from_run_doc(run)  # rebuilding must not raise
		with self.assertRaises(AIDisabled) as caught:
			budget.check_deadline()
		self.assertEqual(str(caught.exception), "ai_disabled")
		RunBudget.from_run_doc(run).check_deadline()  # switch back on: runs again

	def test_site_switch_stops_the_default_budget_used_by_streaming(self):
		set_current_budget(None)
		budget = get_current_budget()
		with patch.dict(frappe.local.conf, {"huf_ai_disabled": 1}), self.assertRaises(AIDisabled):
			budget.check_deadline()
		budget.check_deadline()

	def test_provider_switches_off_only_its_agents(self):
		def provider(agent=None):
			return {"enabled": False} if agent == "mine" else None

		self.assertFalse(self.policy(provider, agent="mine")["enabled"])
		self.assertTrue(self.policy(provider, agent="other")["enabled"])
		hooks, attr = _hooked(provider)
		with hooks, attr, self.assertRaises(AIDisabled):
			assert_ai_enabled("mine")

	def test_failing_provider_counts_as_off(self):
		def broken(agent=None):
			raise RuntimeError("boom")

		self.assertFalse(self.policy(broken)["enabled"])

	def test_lowest_programme_cap_wins(self):
		policy = self.policy(lambda agent=None: {"spend_cap_usd": 5}, lambda agent=None: {"spend_cap_usd": 2},
			lambda agent=None: {"spend_cap_usd": 0})
		self.assertEqual(policy["spend_cap_usd"], 2)

	def test_hook_cap_reaches_the_run_budget_and_never_loosens_the_site_cap(self):
		run = {"agent": "a1", "budget_deadline_at": now_datetime()}
		for site_cap, hook_cap, expected in ((0, 3, 3), (10, 3, 3), (2, 3, 2), (2, 0, 2), (0, 0, 0)):
			hooks, attr = _hooked(lambda agent=None, cap=hook_cap: {"spend_cap_usd": cap})
			with hooks, attr, patch("huf.ai.run_budget.frappe.db.get_single_value", return_value=site_cap):
				self.assertEqual(RunBudget.from_run_doc(run).spend_cap_usd, expected)


class TestAISwitchRuns(IntegrationTestCase):
	"""The switch against a real agent: the ``agent.run`` flow node and a run queued before the switch."""

	def setUp(self):
		tag = frappe.generate_hash(length=8)
		self.provider = self.insert(
			doctype="AI Provider", provider_name=f"switch-{tag}", api_key="test-key-not-used", provider_brand="openai"
		)
		self.model = self.insert(doctype="AI Model", model_name=f"switch-model-{tag}", provider=self.provider.name)
		self.agent = self.insert(
			doctype="Agent",
			agent_name=f"switch-agent-{tag}",
			instructions="x",
			provider=self.provider.name,
			model=self.model.name,
		)
		# the queued path commits
		self.addCleanup(self.remove)

	def insert(self, **values):
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def remove(self):
		runs = frappe.get_all("Agent Run", {"agent": self.agent.name}, ["name", "conversation"])
		for run in runs:
			frappe.db.delete("Agent Message", {"conversation": run.conversation})
			frappe.db.delete("Agent Run", {"name": run.name})
			frappe.db.delete("Agent Conversation", {"name": run.conversation})
		for doc in (self.agent, self.model, self.provider):
			frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_agent_run_node_fails_with_reason_and_calls_no_provider(self):
		flow_run = MagicMock(conversation=None, context_json=None, mode=None)
		flow_run.name = None
		with (
			patch.dict(frappe.local.conf, {"huf_ai_disabled": 1}),
			patch("huf.ai.providers.litellm.run", new_callable=AsyncMock) as provider_call,
		):
			result = _exec_agent_run(flow_run, {"id": "n1"}, {"agent": self.agent.name, "prompt": "hello"}, {})
		self.assertEqual(result["status"], "failed")
		self.assertIn("ai_disabled", result["error"].lower().replace(" ", "_"))
		provider_call.assert_not_awaited()

	def test_run_queued_before_the_switch_fails_in_the_worker(self):
		with patch("frappe.enqueue"):
			queued = run_agent_sync(agent_name=self.agent.name, prompt="hello", channel_id="test")
		self.assertTrue(queued["queued"])
		with (
			patch.dict(frappe.local.conf, {"huf_ai_disabled": 1}),
			patch("frappe.enqueue"),
			patch("huf.ai.providers.litellm.run", new_callable=AsyncMock) as provider_call,
		):
			_run_queued_agent(conversation_id=queued["conversation_id"])
		run = frappe.db.get_value("Agent Run", queued["agent_run_id"], ["status", "error_message"], as_dict=True)
		self.assertEqual((run.status, run.error_message), ("Failed", "ai_disabled"))
		provider_call.assert_not_awaited()


class TestMemoryPurge(IntegrationTestCase):
	def make(self, age_days):
		doc = frappe.get_doc(
			{"doctype": "Memory Record", "title": f"purge {age_days}", "scope_type": "Global", "summary_text": "x"}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Memory Record", doc.name, "modified", add_days(now_datetime(), -age_days), update_modified=False)
		return doc.name

	def test_only_records_past_retention_are_deleted(self):
		old, new = self.make(4000), self.make(1)
		self.assertGreaterEqual(purge_expired_memory(days=3650), 1)
		self.assertFalse(frappe.db.exists("Memory Record", old))
		self.assertTrue(frappe.db.exists("Memory Record", new))

	def test_no_retention_configured_keeps_everything(self):
		old = self.make(4000)
		with patch.dict(frappe.local.conf, {"huf_ai_memory_retention_days": 0}):
			self.assertEqual(purge_expired_memory(), 0)
		self.assertTrue(frappe.db.exists("Memory Record", old))
