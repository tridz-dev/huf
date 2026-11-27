"""AI kill switch, ``huf_ai_feature_map`` caps and memory retention purge (H-W5-05)."""

from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from huf.ai.memory.purge import purge_expired_memory
from huf.ai.run_budget import AIDisabled, RunBudget, ai_policy, assert_ai_enabled


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
