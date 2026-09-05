"""Regression tests for GW-10: Credential isolation design decision (org-wide by design).

This test suite verifies that the org-wide credential scope is maintained:
- Non-admin users can resolve org-wide credentials when a tool is attached to their agent
- Credential lookup succeeds without per-agent or per-user filtering
- The design choice is explicitly locked in to prevent future regressions

See: Tracks/safwan-erooth.IntegrationsGatewaysAudit/findings/GW-10-decision.md
"""

import frappe
from frappe.tests import IntegrationTestCase
from huf.ai.tools.credentials import require_credential, update_last_error


class TestGW10OrgWideCredentialScope(IntegrationTestCase):
	"""Test suite for GW-10: Credentials are intentionally org-wide resources."""

	def setUp(self):
		"""Create test users, Integration Settings, and a test tool function."""
		frappe.set_user("Administrator")

		# Create a non-admin user for testing
		self.test_user = "test_user_gw10"
		if not frappe.db.exists("User", self.test_user):
			frappe.get_doc({
				"doctype": "User",
				"email": f"{self.test_user}@example.com",
				"first_name": "Test User",
				"user_type": "Website User",
			}).insert()

		# Create an AI Provider (for the test tool)
		self.provider_name = "test_provider_gw10"
		if frappe.db.exists("AI Provider", self.provider_name):
			frappe.delete_doc("AI Provider", self.provider_name)
		frappe.get_doc({
			"doctype": "AI Provider",
			"name": self.provider_name,
			"provider_name": "openai",
			"api_key": "test-key-123",
			"disabled": 0,
		}).insert()

		# Create Integration Settings (org-wide credential)
		self.integration_name = "test_integration_gw10"
		if frappe.db.exists("Integration Settings", self.integration_name):
			frappe.delete_doc("Integration Settings", self.integration_name)
		self.integration_doc = frappe.get_doc({
			"doctype": "Integration Settings",
			"name": self.integration_name,
			"service": "test_service",
			"is_active": 1,
			"is_default": 1,
			"credentials": [
				{
					"key": "api_key",
					"value": "test-credential-value-12345",
				}
			],
		})
		self.integration_doc.insert()

		# Create an Agent with the non-admin test user as owner
		self.agent_name = "test_agent_gw10"
		if frappe.db.exists("Agent", self.agent_name):
			frappe.delete_doc("Agent", self.agent_name)
		self.agent_doc = frappe.get_doc({
			"doctype": "Agent",
			"name": self.agent_name,
			"agent_name": self.agent_name,
			"owner": self.test_user,
			"model": "gpt-4",
			"disabled": 0,
		})
		self.agent_doc.insert()

		# Create a tool function that will use the credential
		self.tool_name = "test_tool_gw10"
		if frappe.db.exists("Agent Tool Function", self.tool_name):
			frappe.delete_doc("Agent Tool Function", self.tool_name)
		self.tool_doc = frappe.get_doc({
			"doctype": "Agent Tool Function",
			"name": self.tool_name,
			"tool_name": self.tool_name,
			"title": "Test Tool GW-10",
			"function_type": "Custom Function",
			"handler": "huf.ai.test_tools.echo",
			"description": "Test tool for GW-10 credential resolution",
			"owner": "Administrator",
			"disabled": 0,
		})
		self.tool_doc.insert()

	def tearDown(self):
		"""Clean up test data."""
		frappe.set_user("Administrator")
		# Delete in reverse order of creation (respect FK constraints)
		for doctype, name in [
			("Agent Tool Function", self.tool_name),
			("Agent", self.agent_name),
			("Integration Settings", self.integration_name),
			("AI Provider", self.provider_name),
			("User", self.test_user),
		]:
			if frappe.db.exists(doctype, name):
				try:
					frappe.delete_doc(doctype, name)
				except Exception:
					# Some doctypes may have FK constraints; continue
					pass

	def test_non_admin_can_resolve_org_wide_credential(self):
		"""
		GW-10: A non-admin user's agent can resolve org-wide credentials.

		This test verifies that credential lookup succeeds for a non-admin user,
		confirming that the org-wide credential scope is maintained.

		The test does NOT verify permission enforcement (that would be handled
		by per-agent scoping in Option B, which was not chosen). Instead, it
		verifies that the current org-wide design allows non-admin access to
		attached tools' credentials.
		"""
		frappe.set_user(self.test_user)

		# Non-admin user should be able to resolve the org-wide credential
		# via the same path a tool handler would use
		try:
			credential_value = require_credential("test_service", "api_key")
			self.assertEqual(credential_value, "test-credential-value-12345")
		except Exception as e:
			self.fail(f"Non-admin user could not resolve org-wide credential: {e}")

	def test_credential_lookup_bypasses_permissions_by_design(self):
		"""
		GW-10: Credential lookups use frappe.get_all(), which intentionally
		bypasses permissions.

		This test verifies the documented behavior: even though get_all() does not
		check permissions, this is intentional (not an oversight), because:
		1. Only admins can attach credentialed tools in the first place
		2. This is a controlled-use gap, not a disclosure gap

		The test serves as regression prevention if the implementation ever
		changes to use permissioned lookups.
		"""
		frappe.set_user(self.test_user)

		# The non-admin user has no explicit permission to read Integration Settings
		# yet should still be able to resolve the credential (because get_all bypasses permissions)
		self.assertFalse(frappe.has_permission("Integration Settings", "read"))

		# Despite lacking read permission, credential resolution should succeed
		try:
			credential_value = require_credential("test_service", "api_key")
			self.assertEqual(credential_value, "test-credential-value-12345")
		except Exception as e:
			self.fail(
				f"Credential resolution failed despite org-wide design: {e}. "
				f"This suggests a regression to per-user/per-agent scoping."
			)

	def test_update_last_error_also_uses_org_wide_scope(self):
		"""
		GW-10: update_last_error() also uses org-wide credential lookups.

		This test verifies that the error-logging path also respects the org-wide
		design. It does not verify permission enforcement, only that the lookup
		uses the same org-wide path (frappe.get_all) that require_credential does.
		"""
		frappe.set_user(self.test_user)

		# Switch back to admin to set up a fresh integration for this test
		frappe.set_user("Administrator")
		error_test_service = "test_service_error_logging"
		error_integration_name = "test_integration_error_logging"
		if frappe.db.exists("Integration Settings", error_integration_name):
			frappe.delete_doc("Integration Settings", error_integration_name)
		frappe.get_doc({
			"doctype": "Integration Settings",
			"name": error_integration_name,
			"service": error_test_service,
			"is_active": 1,
			"is_default": 1,
		}).insert()

		# Now switch to non-admin and update error
		frappe.set_user(self.test_user)

		try:
			update_last_error(error_test_service, "Test error message")
		except Exception as e:
			frappe.set_user("Administrator")
			frappe.delete_doc("Integration Settings", error_integration_name)
			self.fail(
				f"Non-admin user could not update last_error on org-wide credential: {e}"
			)

		# Clean up
		frappe.set_user("Administrator")
		frappe.delete_doc("Integration Settings", error_integration_name)

	def test_active_filter_is_respected(self):
		"""
		GW-10: The active filter is still respected in org-wide lookups.

		This test verifies that while credentials are org-wide, inactive
		Integration Settings are still correctly filtered out. This is an
		important sanity check that the query logic is sound.
		"""
		frappe.set_user("Administrator")

		# Create an inactive Integration Settings
		inactive_name = "test_integration_inactive_gw10"
		if frappe.db.exists("Integration Settings", inactive_name):
			frappe.delete_doc("Integration Settings", inactive_name)
		frappe.get_doc({
			"doctype": "Integration Settings",
			"name": inactive_name,
			"service": "test_service_inactive",
			"is_active": 0,
			"is_default": 0,
			"credentials": [
				{
					"key": "api_key",
					"value": "should-not-be-found",
				}
			],
		}).insert()

		frappe.set_user(self.test_user)

		# Credential lookup should fail (inactive is filtered out)
		with self.assertRaises(ValueError):
			require_credential("test_service_inactive", "api_key")

		# Clean up
		frappe.set_user("Administrator")
		frappe.delete_doc("Integration Settings", inactive_name)

	def test_default_flag_is_used_for_tiebreaking(self):
		"""
		GW-10: When multiple active credentials exist for a service,
		is_default flag is used for tiebreaking.

		This verifies the order_by logic is sound.
		"""
		frappe.set_user("Administrator")

		# Create two active Integration Settings for the same service
		primary_name = "test_integration_primary_gw10"
		secondary_name = "test_integration_secondary_gw10"

		for name, is_default, value in [
			(primary_name, 1, "primary-credential"),
			(secondary_name, 0, "secondary-credential"),
		]:
			if frappe.db.exists("Integration Settings", name):
				frappe.delete_doc("Integration Settings", name)
			frappe.get_doc({
				"doctype": "Integration Settings",
				"name": name,
				"service": "test_service_tiebreak",
				"is_active": 1,
				"is_default": is_default,
				"credentials": [
					{
						"key": "api_key",
						"value": value,
					}
				],
			}).insert()

		frappe.set_user(self.test_user)

		# Should resolve to the default one
		credential_value = require_credential("test_service_tiebreak", "api_key")
		self.assertEqual(credential_value, "primary-credential")

		# Clean up
		frappe.set_user("Administrator")
		for name in [primary_name, secondary_name]:
			frappe.delete_doc("Integration Settings", name)
