# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""WP14: the Data trigger's document type list for non-System-Manager editors, and the trigger metadata in the run payload.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_wp14
"""

from types import SimpleNamespace

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import triggers


class TestTriggerDoctypes(IntegrationTestCase):
	def setUp(self):
		self._users = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for email in self._users:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def _user(self, role):
		email = f"wp14-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Wp14", "send_welcome_email": 0, "roles": [{"role": role}]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email

	def test_huf_manager_who_is_not_a_system_manager_gets_a_list(self):
		frappe.set_user(self._user("Huf Manager"))
		names = [d["name"] for d in flow_api.get_trigger_doctypes()]
		self.assertIn("ToDo", names)
		self.assertEqual(names, sorted(names))

	def test_list_is_limited_to_what_the_user_can_read(self):
		frappe.set_user(self._user("Huf Manager"))
		names = {d["name"] for d in flow_api.get_trigger_doctypes()}
		self.assertNotIn("User", names)
		self.assertNotIn("DocType", names)
		frappe.set_user("Administrator")
		self.assertIn("User", {d["name"] for d in flow_api.get_trigger_doctypes()})

	def test_read_only_flow_viewer_can_still_list_approver_roles_and_tools(self):
		frappe.set_user(self._user("Huf User"))
		self.assertTrue(flow_api.get_approver_roles())
		self.assertTrue(flow_api.list_flow_tools())

	def test_internal_tables_and_huf_bookkeeping_are_left_out(self):
		frappe.set_user("Administrator")
		names = {d["name"] for d in flow_api.get_trigger_doctypes()}
		for hidden in ("Flow Run", "Flow Definition", "Agent Run", "Error Log", "Comment", "Version", "DocField", "System Settings"):
			self.assertNotIn(hidden, names)


class TestDocEventPayloadMeta(IntegrationTestCase):
	def test_payload_carries_what_happened_beside_the_document(self):
		doc = SimpleNamespace(
			doctype="ToDo", name="TD-1", as_dict=lambda: {"doctype": "ToDo", "name": "TD-1", "description": "d", "owner": "a@b.c"}
		)
		payload = triggers.build_doc_event_payload(doc, "Administrator", "after_insert")
		self.assertEqual(payload["description"], "d")
		meta = payload["_trigger"]
		self.assertEqual(meta["doctype"], "ToDo")
		self.assertEqual(meta["docname"], "TD-1")
		self.assertEqual(meta["event"], "after_insert")
		self.assertEqual(meta["owner"], "Administrator")
		self.assertTrue(meta["timestamp"])
