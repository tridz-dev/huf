"""Whitelisted member list/remove calls and the saved-data limit."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import member, members_api


class TestFlowMembersApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-members-api-{frappe.generate_hash(length=8)}",
				"flow_name": "Members Api",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "n1", "type": "output", "config": {}}]}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_id = flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_list_returns_members_of_this_flow_only(self):
		member.upsert_member(self.flow_id, "alice")
		rows = members_api.list_flow_members(self.flow_id)
		self.assertEqual([r["member_key"] for r in rows], ["alice"])
		self.assertEqual(rows[0]["status"], "Active")

	def test_remove_forgets_member(self):
		member.upsert_member(self.flow_id, "bob")
		self.assertEqual(members_api.remove_flow_member(self.flow_id, "bob"), {"removed": True})
		self.assertEqual(members_api.list_flow_members(self.flow_id), [])
		self.assertEqual(members_api.remove_flow_member(self.flow_id, "bob"), {"removed": False})

	def test_state_limit_follows_site_config(self):
		frappe.conf.huf_flow_state_max_ttl_days = 30
		try:
			self.assertEqual(members_api.get_flow_state_limits(), {"max_ttl_seconds": 30 * 86400})
			frappe.conf.huf_flow_state_max_ttl_days = 0
			self.assertEqual(members_api.get_flow_state_limits(), {"max_ttl_seconds": 0})
		finally:
			frappe.conf.pop("huf_flow_state_max_ttl_days", None)
