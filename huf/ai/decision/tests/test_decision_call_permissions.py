"""Tests for Decision Call visibility permissions (D5).

Tests that Decision Call visibility follows its originating run (Agent Run / Flow Run / Automation),
and that calls with no origin (Playground, API) are visible to their owner and decision.admin.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tests.factories import (
	make_user,
	make_agent_run,
	make_automation,
)


class TestDecisionCallPermissions(IntegrationTestCase):
	"""Test Decision Call permission query and has_permission logic."""

	def setUp(self):
		"""Create test users and documents."""
		frappe.set_user("Administrator")

		# Create test users
		self.huf_manager = make_user(
			first_name="HUF Manager",
			roles=("Huf Manager",)
		).email
		self.huf_user = make_user(
			first_name="HUF User",
			roles=("Huf User",)
		).email
		self.other_user = make_user(
			first_name="Other User",
			roles=("Huf User",)
		).email

		# Create agent run and automation as huf_user by setting owner
		# We stay as Administrator for creating documents
		run = make_agent_run()
		# Update owner to huf_user
		frappe.db.set_value("Agent Run", run.name, "owner", self.huf_user)
		self.agent_run = run.name

		automation = make_automation()
		frappe.db.set_value("Automation", automation.name, "owner", self.huf_user)
		self.automation = automation.name

		# Create a test policy
		self._get_or_create_test_policy()

	def tearDown(self):
		"""Clean up test data."""
		frappe.set_user("Administrator")
		# Clean up Decision Calls created in tests
		# We don't need to explicitly delete as test framework handles it
		frappe.db.commit()

	def _get_or_create_test_policy(self):
		"""Get or create a test Decision Policy."""
		if not frappe.db.exists("Decision Policy", "test-policy-perms"):
			policy = frappe.get_doc({
				"doctype": "Decision Policy",
				"policy_name": "test-policy-perms",
				"title": "Test Policy Permissions",
				"status": "draft",
				"policy_class": "classifier",
				"definition": {"name": "test", "type": "classifier"},
			})
			policy.insert(ignore_permissions=True)
		return "test-policy-perms"

	def _make_call_id(self, prefix):
		"""Generate a unique call_id."""
		return f"{prefix}-{frappe.generate_hash(length=8)}"

	def test_admin_sees_all_calls(self):
		"""Test that System Manager can see all Decision Calls."""
		frappe.set_user(self.huf_user)
		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": self._make_call_id("test-admin-all"),
			"policy": self._get_or_create_test_policy(),
			"status": "success",
			"surface": "playground",
			"agent_run": self.agent_run,
		})
		call.insert(ignore_permissions=True)

		# System Manager should see it
		self.assertTrue(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user="Administrator")
		)

	def test_user_sees_own_no_origin_calls(self):
		"""Test that user can see their own Playground/API calls (no origin)."""
		frappe.set_user(self.huf_user)
		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": self._make_call_id("test-own-no-origin"),
			"policy": self._get_or_create_test_policy(),
			"status": "success",
			"surface": "api",
			"owner_user": self.huf_user,
		})
		call.insert(ignore_permissions=True)

		# User should see their own call
		self.assertTrue(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.huf_user)
		)

		# Other user should not see it
		self.assertFalse(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.other_user)
		)

	def test_user_sees_calls_from_own_agent_run(self):
		"""Test that user can see Decision Calls from Agent Runs they own."""
		frappe.set_user(self.huf_user)
		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": self._make_call_id("test-own-agent-run"),
			"policy": self._get_or_create_test_policy(),
			"status": "success",
			"surface": "playground",
			"agent_run": self.agent_run,
		})
		call.insert(ignore_permissions=True)

		# huf_user owns the agent_run, should see this call
		self.assertTrue(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.huf_user)
		)

		# other_user should not see it
		self.assertFalse(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.other_user)
		)

	def test_user_sees_calls_from_own_automation(self):
		"""Test that user can see Decision Calls from Automations they own."""
		frappe.set_user(self.huf_user)
		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": self._make_call_id("test-own-automation"),
			"policy": self._get_or_create_test_policy(),
			"status": "success",
			"surface": "playground",
			"automation": self.automation,
		})
		call.insert(ignore_permissions=True)

		# huf_user owns the automation, should see this call
		self.assertTrue(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.huf_user)
		)

		# other_user should not see it
		self.assertFalse(
			frappe.has_permission("Decision Call", doc=call.name, ptype="read", user=self.other_user)
		)
