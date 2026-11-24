"""Entry policies, resume-by-inbound and the member-reply wait."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, member, park, triggers
from huf.ai.flow.nodes.wait import exec_wait

KEY = "15550100100"


def _utc_now():
	return datetime.now(timezone.utc).replace(tzinfo=None)


class TestFlowMemberEntry(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-entry-{frappe.generate_hash(length=8)}",
				"flow_name": "Entry Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.flow_id = self.flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status="Running", key=KEY):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow_id,
				"flow_id": self.flow_id,
				"status": status,
				"trigger_type": "Gateway",
				"member_key": key,
			}
		).insert(ignore_permissions=True)
		if key:
			member.upsert_member(self.flow_id, key, run.name)
		return run

	def _park_reply(self, run, timeout_ms=None, **resume):
		node = {"id": "w1", "type": "wait", "next": "n2", "config": {"mode": "resume", "resume": {"wait_for": "member_reply", "timeout_ms": timeout_ms, **resume}}}
		run.reload()
		with patch.object(flow_engine, "_context_of"), patch.object(flow_engine, "_persist_context"):
			return node, exec_wait(run, node, node["config"], {})

	def _decide(self, policy):
		with patch("frappe.enqueue"):
			return triggers.entry_decision(self.flow_id, policy, KEY, {"text": "hi", "sender_id": KEY})

	def test_resume_if_waiting_wakes_existing_run(self):
		run = self._run()
		self._park_reply(run)
		self.assertEqual(frappe.db.get_value("Flow Member State", member.member_name(self.flow_id, KEY), "status"), "Waiting")
		decision = self._decide("resume_if_waiting")
		self.assertEqual(decision, {"action": "resume", "run": run.name})
		run.reload()
		self.assertEqual(run.status, "Running")
		self.assertEqual(json.loads(run.waiting)["woke"]["payload"]["text"], "hi")

	def test_new_run_when_not_waiting(self):
		self._run()  # running, not parked
		self.assertEqual(self._decide("resume_if_waiting"), {"action": "start"})
		self.assertEqual(self._decide("new_run_each_time"), {"action": "start"})

	def test_once_per_member_skips_second(self):
		self.assertEqual(self._decide("once_per_member"), {"action": "start"})
		self._run(status="Success")
		self.assertEqual(self._decide("once_per_member")["action"], "skip")

	def test_one_active_blocks_parallel(self):
		self._run(status="Success")
		self.assertEqual(self._decide("one_active_per_member"), {"action": "start"})
		self._run(status="Running")
		self.assertEqual(self._decide("one_active_per_member")["action"], "skip")

	def test_start_flow_run_applies_policy(self):
		defn = {"nodes": [{"id": "t1", "type": "trigger.webhook", "config": {"entry_policy": "one_active_per_member"}}]}
		frappe.db.set_value("Flow Definition", self.flow_id, "definition_json", json.dumps(defn))
		self._run(status="Running", key="Administrator")
		self.assertIsNone(triggers.start_flow_run(self.flow_id, {}, "Manual", "t1", user="Administrator", enqueue=True))

	def test_reply_timeout_next_nudge(self):
		run = self._run()
		node, _ = self._park_reply(run, timeout_ms=60000, timeout_next="nudge")
		self.assertIsNotNone(frappe.db.get_value("Flow Run", run.name, "resume_at"))
		with patch("frappe.enqueue"):
			self.assertTrue(park.wake_run(run.name, "elapsed"))
		run.reload()
		out = exec_wait(run, node, node["config"], {})
		self.assertEqual(out["next_node_id"], "nudge")
		self.assertEqual(frappe.db.get_value("Flow Member State", member.member_name(self.flow_id, KEY), "status"), "Active")

	def test_reply_wakes_to_normal_next(self):
		run = self._run()
		node, _ = self._park_reply(run, timeout_ms=60000, timeout_next="nudge")
		self._decide("resume_if_waiting")
		run.reload()
		out = exec_wait(run, node, node["config"], {})
		self.assertEqual(out["next_node_id"], "n2")
		self.assertEqual(out["output"]["reason"], "reply")

	def test_member_reply_wait_requires_member(self):
		run = self._run(key=None)
		_, out = self._park_reply(run)
		self.assertEqual(out["status"], "failed")
		self.assertIn("who it is about", out["error"])

	def test_inbound_dedupe_single_wake(self):
		run = self._run()
		self._park_reply(run)
		first = self._decide("resume_if_waiting")
		second = self._decide("resume_if_waiting")
		self.assertEqual(first["action"], "resume")
		# the run is no longer waiting, so the second message is not a second wake
		self.assertNotEqual(second.get("run"), run.name)
		self.assertTrue(frappe.db.get_value("Flow Run", run.name, "waiting"))
