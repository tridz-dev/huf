from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import pipeline
from huf.ai.channels.pipeline import Decision, run_pre_route


def hook_reply(ctx):
	return Decision("reply", {"text": "hi"})


def hook_drop(ctx):
	return Decision("drop")


def hook_continue(ctx):
	return Decision("continue")


class TestPipeline(IntegrationTestCase):
	def test_noop_by_default(self):
		self.assertEqual(pipeline.PRE_ROUTE_HOOKS, ["huf.ai.channels.handoff_hooks.handed_off_hook"])
		self.assertIsNone(run_pre_route({}))

	def test_continue_falls_through(self):
		with patch.object(pipeline, "PRE_ROUTE_HOOKS", [f"{__name__}.hook_continue"]):
			self.assertIsNone(run_pre_route({}))

	def test_reply_short_circuits(self):
		with patch.object(pipeline, "PRE_ROUTE_HOOKS", [f"{__name__}.hook_reply", f"{__name__}.hook_drop"]):
			d = run_pre_route({})
		self.assertEqual((d.action, d.payload["text"]), ("reply", "hi"))

	def test_drop_short_circuits(self):
		with patch.object(pipeline, "PRE_ROUTE_HOOKS", [f"{__name__}.hook_drop", f"{__name__}.hook_reply"]):
			self.assertEqual(run_pre_route({}).action, "drop")

	def test_gateway_saves_with_child_tables(self):
		gw = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"pipe-{frappe.generate_hash(length=6)}",
				"provider": "Telegram",
				"is_enabled": 0,
				"business_hours": [{"weekday": "Monday", "start_time": "09:00:00", "end_time": "17:00:00"}],
				"routing_rules": [
					{"rule_type": "keyword", "match_value": "help", "target_type": "human", "priority": 1, "enabled": 1}
				],
			}
		).insert(ignore_permissions=True)
		gw.reload()
		self.assertEqual(len(gw.business_hours), 1)
		self.assertEqual(gw.routing_rules[0].rule_type, "keyword")
		self.assertEqual(gw.after_hours_mode, "agent_24_7")
		self.assertEqual(gw.handoff_target, "none")
		frappe.db.rollback()
