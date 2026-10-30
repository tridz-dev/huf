# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Security round 2 (DECISIONS 13): looking people up is for flow editors, rate limited, and tells only name + address.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux25_users
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.catalog import form_options_api as api
from huf.testing.factories import make_user

SHAPE = {"name", "email", "full_name", "label", "has_approver_role"}


class TestFlowUserLookup(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._users = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._users:
			if frappe.db.exists("User", name):
				frappe.delete_doc("User", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, *roles, **kw):
		user = make_user(roles=roles, **kw)
		self._users.append(user.name)
		return user.name

	def test_a_viewer_gets_a_403(self):
		frappe.set_user(self._user("Huf Viewer"))
		with self.assertRaises(frappe.PermissionError):
			api.search_flow_users("")
		with self.assertRaises(frappe.PermissionError):
			api.check_flow_users(["Administrator"])

	def test_someone_who_can_only_read_flows_gets_a_403(self):
		frappe.set_user(self._user("Huf User"))
		with self.assertRaises(frappe.PermissionError):
			api.search_flow_users("")

	def test_an_editor_can_look_people_up(self):
		editor = self._user("Huf Manager")
		frappe.set_user(editor)
		rows = api.search_flow_users(editor)
		self.assertTrue(any(r["name"] == editor for r in rows))
		self.assertEqual(api.check_flow_users([editor])[0]["found"], True)

	def test_only_a_name_and_an_address_come_back(self):
		frappe.set_user("Administrator")
		for row in api.search_flow_users(""):
			self.assertEqual(set(row), SHAPE)
			self.assertIn("@", row["email"]) if row["name"] != "Administrator" else None

	def test_a_disabled_person_is_not_listed_or_found(self):
		gone = self._user("Huf User")
		frappe.db.set_value("User", gone, "enabled", 0)
		self.assertNotIn(gone, [r["name"] for r in api.search_flow_users(gone)])
		self.assertFalse(api.check_flow_users([gone])[0]["found"])

	def test_who_holds_an_approver_role_is_marked(self):
		with_role = self._user("Huf User")
		without = self._user("Blogger")
		rows = {r["name"]: r for r in api.search_flow_users("")}
		# the list is capped; ask for each by name to be sure they are in it
		rows.update({r["name"]: r for r in api.search_flow_users(with_role)})
		rows.update({r["name"]: r for r in api.search_flow_users(without)})
		self.assertIs(rows[with_role]["has_approver_role"], True)
		self.assertIs(rows[without]["has_approver_role"], False)

	def test_the_61st_lookup_in_a_minute_is_refused(self):
		counts = iter(range(1, 200))
		with patch("frappe.cache") as cache:
			cache.return_value.incr.side_effect = lambda key: next(counts)
			for _ in range(60):
				api.search_flow_users("a")
			with self.assertRaises(frappe.ValidationError) as caught:
				api.search_flow_users("a")
		self.assertIn("very quickly", str(caught.exception))

	def test_the_limit_is_per_person(self):
		seen = []
		with patch("frappe.cache") as cache:
			cache.return_value.incr.side_effect = lambda key: (seen.append(key), 1)[1]
			api.search_flow_users("a")
			frappe.set_user(self._user("Huf Manager"))
			api.search_flow_users("a")
		self.assertEqual(len(set(seen)), 2)
		self.assertEqual(api.USER_LOOKUP_LIMIT, 60)
