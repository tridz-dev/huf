"""GW-12: generic /api/resource access to the Gateway/Integration doctype
family must be blocked for anyone but a System Manager.

None of Gateway, Gateway Access Entry, Gateway Event, Gateway Binding,
Integration Settings, Integration Service, or Integration Credential has a
row-level owner/share concept; the app only ever reads/writes them through
its own bespoke whitelisted methods (gateway pairing, adapter routing, the
Integrations UI). Before this fix none of them had `has_permission` /
`permission_query_conditions` hooks (unlike the Agent-run family, which
already does), so a plain "grant this Role generic read on DocType X" would
have been enough to list/get them through /api/resource -- exposing stored
credentials indirectly (Integration Credential) or routing/config data.

This test builds its own non-System-Manager user, grants that user's role a
completely generic Custom DocPerm read permission on each doctype in the
family (the scenario the acceptance criteria calls for -- a user who *does*
hold a generic DocType read role permission), and proves list/get through
frappe.get_list/frappe.get_doc is still refused for that user, exactly the
same way it is already refused for a user with no permission at all.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tests.factories import make_user

GATEWAY_INTEGRATION_DOCTYPES = (
	"Gateway",
	"Gateway Access Entry",
	"Gateway Event",
	"Gateway Binding",
	"Integration Settings",
	"Integration Service",
	"Integration Credential",
)


class TestGatewayIntegrationFamilyPermissions(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup_users = []
		self._cleanup_custom_perms = []
		self.role = "Test Gateway Generic Reader"
		if not frappe.db.exists("Role", self.role):
			frappe.get_doc({"doctype": "Role", "role_name": self.role, "desk_access": 1}).insert(
				ignore_permissions=True
			)

		# Grant this role a completely generic, doctype-level read permission
		# on every doctype in the family -- exactly the "has a generic DocType
		# read role permission" scenario the acceptance criteria requires,
		# constructed fresh rather than reusing audit.user (who has none).
		for doctype in GATEWAY_INTEGRATION_DOCTYPES:
			from frappe.permissions import add_permission

			add_permission(doctype, self.role, 0, "read")
			self._cleanup_custom_perms.append(doctype)

		self.reader = make_user(roles=(self.role,))
		self._cleanup_users.append(self.reader.name)

		# A minimal Gateway row to try to read/list. Its own required fields
		# are irrelevant to this test; only its existence and visibility
		# matter.
		self.gateway_name = None
		if frappe.db.exists("DocType", "Gateway"):
			gateway = frappe.get_doc(
				{
					"doctype": "Gateway",
					"gateway_name": f"Test Gateway Perm {frappe.generate_hash(length=6)}",
					"provider": "Slack",
					"is_enabled": 0,
				}
			)
			gateway.insert(ignore_permissions=True)
			self.gateway_name = gateway.name

	def tearDown(self):
		frappe.set_user("Administrator")
		if self.gateway_name and frappe.db.exists("Gateway", self.gateway_name):
			frappe.delete_doc("Gateway", self.gateway_name, ignore_permissions=True, force=True)
		for user in self._cleanup_users:
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		for doctype in self._cleanup_custom_perms:
			frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": self.role})
			frappe.clear_cache(doctype=doctype)
		frappe.db.commit()

	def test_generic_reader_cannot_list_any_family_doctype(self):
		"""frappe.get_list's initial permission gate calls frappe.has_permission
		without a doc, which only consults role permissions (we deliberately
		granted a generic read Custom DocPerm, so that gate alone passes);
		row visibility is then filtered by get_permission_query_conditions_gateway_family
		("1=0" for a non-System-Manager), so the list comes back empty rather
		than raising -- still "cannot list" as the acceptance criteria requires.
		"""
		frappe.set_user(self.reader.name)
		try:
			for doctype in GATEWAY_INTEGRATION_DOCTYPES:
				rows = frappe.get_list(doctype, limit_page_length=0)
				self.assertEqual(
					rows,
					[],
					f"{doctype} leaked rows to a non-System-Manager generic reader",
				)
		finally:
			frappe.set_user("Administrator")

	def test_generic_reader_cannot_get_a_known_gateway_row(self):
		assert self.gateway_name, "Gateway doctype must exist in this site for this assertion"
		frappe.set_user(self.reader.name)
		try:
			self.assertFalse(frappe.has_permission("Gateway", "read", doc=self.gateway_name))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Gateway", self.gateway_name).check_permission("read")
		finally:
			frappe.set_user("Administrator")

	def test_system_manager_is_unaffected(self):
		admin_reader = make_user(roles=(self.role, "System Manager"))
		self._cleanup_users.append(admin_reader.name)
		frappe.set_user(admin_reader.name)
		try:
			self.assertTrue(frappe.has_permission("Gateway", "read", doc=self.gateway_name))
		finally:
			frappe.set_user("Administrator")


if __name__ == "__main__":
	import unittest

	unittest.main()
