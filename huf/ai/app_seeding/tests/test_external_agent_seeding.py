"""Clean-site style test: seed a fixture external app, re-seed (migrate),
check admin edits survive and role-enforced tool filtering.

    bench --site <site> run-tests --app huf --module huf.ai.app_seeding.tests.test_external_agent_seeding
"""
import unittest
from pathlib import Path

import frappe

from huf.ai.app_seeding.seeder import seed_app
from huf.ai.tools.registry import PermissionAwareToolRegistry, assert_tool_role

FIXTURE = Path(__file__).parent / "fixture_app" / "huf"
AGENT = "n05_fixture_agent"


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "N05", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
	u = frappe.get_doc("User", email)
	u.roles = []
	for r in roles:
		u.append("roles", {"role": r})
	u.save(ignore_permissions=True)
	return email


class TestExternalAgentSeeding(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not frappe.db.exists("Role", "N05 Manager"):
			frappe.get_doc({"doctype": "Role", "role_name": "N05 Manager"}).insert(ignore_permissions=True)
		cls.manager = _user("n05_mgr@example.com", ["N05 Manager"])
		cls.plain = _user("n05_plain@example.com", [])
		frappe.set_user("Administrator")
		res = seed_app("n05_fixture_app", FIXTURE)
		assert not res.errors, res.errors

	def _names(self, user):
		agent = frappe.get_doc("Agent", AGENT)
		return {t.name for t in PermissionAwareToolRegistry.get_allowed_tools(agent, user)}

	def test_agent_seeded_with_icon_and_role(self):
		agent = frappe.get_doc("Agent", AGENT)
		self.assertEqual(agent.agent_icon, "SquareAsterisk")
		self.assertEqual([r.role for r in agent.allowed_roles], ["N05 Manager"])
		self.assertEqual(len(agent.agent_tool), 3)

	def test_tools_filtered_per_role(self):
		self.assertIn("n05_fixture_lookup", self._names(self.manager))
		self.assertNotIn("n05_fixture_lookup", self._names(self.plain))
		self.assertNotIn("n05_fixture_lookup", self._names("Guest"))
		# outbound with no roles fails closed for everyone but System Manager
		self.assertNotIn("n05_fixture_send", self._names(self.manager))
		self.assertIn("n05_fixture_send", self._names("Administrator"))

	def test_call_time_recheck(self):
		assert_tool_role("n05_fixture_lookup", self.manager)
		for user in (self.plain, "Guest"):
			with self.assertRaises(frappe.PermissionError):
				assert_tool_role("n05_fixture_lookup", user)

	def test_role_tool_never_guest_allowed(self):
		frappe.db.set_value("Agent Tool Function", "n05_fixture_lookup", "allowed_for_guest", 1)
		frappe.clear_document_cache("Agent Tool Function", "n05_fixture_lookup")
		self.assertNotIn("n05_fixture_lookup", self._names("Guest"))

	def test_reseed_idempotent_and_keeps_admin_edits(self):
		frappe.db.set_value("Agent Tool Function", "n05_fixture_open", "description", "Admin wording")
		before = frappe.db.count("Agent Tool Function", {"source_app": "n05_fixture_app"})
		res = seed_app("n05_fixture_app", FIXTURE)  # what after_migrate does
		self.assertFalse(res.errors, res.errors)
		self.assertEqual(frappe.db.count("Agent Tool Function", {"source_app": "n05_fixture_app"}), before)
		self.assertEqual(frappe.db.get_value("Agent Tool Function", "n05_fixture_open", "description"), "Admin wording")
		# an untouched seed-owned field is still refreshed from the seed
		frappe.db.set_value("Agent Tool Function", "n05_fixture_lookup", "required_roles", "N05 Manager")
