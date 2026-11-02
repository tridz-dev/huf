"""get_approver_roles: automatic and desk-only roles are never offered."""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.api import get_approver_roles


class TestApproverRoles(IntegrationTestCase):
	def test_filters_and_ordering(self):
		roles = get_approver_roles()
		names = [r["name"] for r in roles]
		for hidden in ("All", "Guest", "Administrator", "Desk User", "Report Manager", "Huf Admin"):
			self.assertNotIn(hidden, names)
		huf = [r["name"] for r in roles if r["group"] == "Huf"]
		self.assertIn("System Manager", huf)
		self.assertEqual(names[: len(huf)], huf)  # Huf roles first

	def test_custom_role_is_offered(self):
		if not frappe.db.exists("Role", "WP2 Custom Approver"):
			frappe.get_doc({"doctype": "Role", "role_name": "WP2 Custom Approver", "is_custom": 1}).insert()
		self.assertIn("WP2 Custom Approver", [r["name"] for r in get_approver_roles()])
