"""FIX5: endpoints outside ``huf.ai.flow`` that had no permission check refuse app-only users.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_open_endpoints
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import mcp_client
from huf.ai.agent import scheduler
from huf.ai.skills import api as skills_api
from huf.testing import tool_testing

APP_USER, HUF_USER = "fix5-apponly@example.com", "fix5-hufuser@example.com"
APP_ROLE = "FIX5 App Role"

TEST_TOOLS = (
	lambda: tool_testing.echo(a=1),
	lambda: tool_testing.deterministic_add(numbers=[1]),
	lambda: tool_testing.deterministic_fail(),
	lambda: tool_testing.permission_protected_mutation(record_id="X", value="v"),
	lambda: tool_testing.slow_or_timeout(duration=0),
)


def _user(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "fix5", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(role)
	# a new System User may be given a default Huf role: keep exactly the role under test
	frappe.db.delete("Huf User Role", {"user": email})
	frappe.db.delete("Has Role", {"parent": email, "role": ["!=", role]})
	frappe.clear_cache(user=email)
	frappe.cache().delete_value(f"huf_user_capabilities::{email}")


class TestOpenEndpoints(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", APP_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": APP_ROLE, "desk_access": 1}).insert()
		_user(APP_USER, APP_ROLE)
		_user(HUF_USER, "Huf User")
		self.addCleanup(frappe.set_user, "Administrator")

	def test_app_only_user_is_refused(self):
		frappe.set_user(APP_USER)
		with mock.patch.object(skills_api, "_sync_app_skills") as sync:
			for call in (skills_api.sync_app_skills, skills_api.get_skill_options, skills_api.get_skill_destinations):
				self.assertRaises(frappe.PermissionError, call)
		sync.assert_not_called()
		for new_runtime in (True, False):
			with mock.patch.object(scheduler, "automation_runtime_is_new", return_value=new_runtime):
				self.assertRaises(frappe.PermissionError, scheduler.run_scheduled_agents)
		for call in TEST_TOOLS:
			self.assertRaises(frappe.PermissionError, call)

	def test_huf_user_keeps_reads_and_test_tools(self):
		frappe.set_user(HUF_USER)
		self.assertIsInstance(skills_api.get_skill_options(), list)
		self.assertIsInstance(skills_api.get_skill_destinations(), list)
		self.assertEqual(tool_testing.deterministic_add(numbers=[1, 2])["sum"], 3)

	def test_scheduler_and_internal_callers_work(self):
		with mock.patch.object(skills_api, "_sync_app_skills", return_value={}) as sync:
			skills_api.sync_app_skills()
		sync.assert_called_once()
		with mock.patch.object(scheduler, "automation_runtime_is_new", return_value=True):
			scheduler.run_scheduled_agents()
		with mock.patch.object(mcp_client.frappe, "get_all", return_value=[]):
			mcp_client.auto_sync_mcp_server_tools()

	def test_mcp_auto_sync_is_not_an_endpoint(self):
		self.assertNotIn(mcp_client.auto_sync_mcp_server_tools, frappe.whitelisted)
