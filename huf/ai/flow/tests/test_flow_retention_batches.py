"""Retention (flow state, flow members) deletes in bounded batches, and a parked run row stays narrow."""

import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow import state as flow_state
from huf.ai.flow.runs import member, park

OLD = "2000-01-01 00:00:00"
MAX_PARKED_ROW_BYTES = 4 * 1024


class TestFlowRetentionBatches(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = f"_test-retention-{frappe.generate_hash(length=8)}"

	def tearDown(self):
		frappe.db.delete("Flow State", {"flow_id": self.flow})
		frappe.db.delete("Flow Member State", {"flow": self.flow})
		frappe.db.commit()

	def _state(self, key, expires_at):
		flow_state.set_state(self.flow, key, 1)
		frappe.db.set_value("Flow State", flow_state.state_name(self.flow, key), "expires_at", expires_at)

	def _member(self, key, status="Active", last_event_at=OLD):
		member.upsert_member(self.flow, key, None)
		frappe.db.set_value(
			"Flow Member State",
			member.member_name(self.flow, key),
			{"status": status, "last_event_at": last_event_at},
		)

	def test_state_purge_commits_between_batches(self):
		for i in range(5):
			self._state(f"old{i}", OLD)
		self._state("future", "2999-01-01 00:00:00")
		self._state("forever", None)
		with (
			patch.object(flow_state, "PURGE_BATCH_SIZE", 2),
			patch.object(flow_state, "commit_if_background", wraps=flow_state.commit_if_background) as commit,
		):
			self.assertGreaterEqual(flow_state.purge_expired(), 5)
		self.assertGreaterEqual(commit.call_count, 3)
		left = frappe.get_all("Flow State", filters={"flow_id": self.flow}, pluck="state_key")
		self.assertEqual(sorted(left), ["forever", "future"])

	def test_member_purge_commits_between_batches(self):
		for i in range(5):
			self._member(f"old{i}")
		self._member("waiting", status="Waiting")
		self._member("recent", last_event_at=frappe.utils.now_datetime())
		with (
			patch.object(member, "PURGE_BATCH_SIZE", 2),
			patch.object(member, "commit_if_background", wraps=member.commit_if_background) as commit,
		):
			self.assertGreaterEqual(member.purge_inactive(30), 5)
		self.assertGreaterEqual(commit.call_count, 3)
		left = frappe.get_all("Flow Member State", filters={"flow": self.flow}, pluck="member_key")
		self.assertEqual(sorted(left), ["recent", "waiting"])

	def test_member_without_last_event_is_aged_by_creation(self):
		for key in ("never-old0", "never-old1", "never-old2", "never-new"):
			self._member(key, last_event_at=None)
			if key != "never-new":
				frappe.db.set_value(
					"Flow Member State", member.member_name(self.flow, key), "creation", OLD, update_modified=False
				)
		# more NULL rows than one batch: the purge must still end
		with patch.object(member, "PURGE_BATCH_SIZE", 1):
			self.assertGreaterEqual(member.purge_inactive(30), 3)
		left = frappe.get_all("Flow Member State", filters={"flow": self.flow}, pluck="member_key")
		self.assertEqual(left, ["never-new"])

	def test_parked_run_row_is_narrow(self):
		graph = {"nodes": [{"id": "w1", "type": "wait"}, {"id": "n2", "type": "output", "config": {}}]}
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow,
				"flow_name": "Retention Width Flow",
				"status": "Draft",
				"definition_json": json.dumps(graph),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		payload = {"order": "SO-0001", "amount": 1200}
		run = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": flow.name,
				"flow_id": flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
				"context_json": json.dumps(payload),
				"trigger_payload": json.dumps(payload),
				"pinned_definition": flow_engine.pinned_json(flow_engine.PinnedVersion.pin(graph)),
			}
		).insert(ignore_permissions=True)
		try:
			request = park.ParkRequest(reason="wait", resume_at=datetime(2030, 1, 1), member_key="m1")
			park.park_run(run, graph["nodes"][0], request)
			row = frappe.db.sql("select * from `tabAgent Flow Run` where name = %s", run.name, as_dict=True)[0]
			width = sum(len(str(value).encode()) for value in row.values() if value is not None)
			print(f"parked run row bytes: {width}")
			self.assertEqual(row["status"], park.WAIT_STATUS)
			self.assertLess(width, MAX_PARKED_ROW_BYTES)
		finally:
			frappe.delete_doc("Agent Flow Run", run.name, ignore_permissions=True, force=True)
			frappe.delete_doc("Flow Definition", flow.name, ignore_permissions=True, force=True)
