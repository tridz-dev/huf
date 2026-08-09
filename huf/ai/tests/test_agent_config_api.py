from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_access import check_agent_access
from huf.ai.agent_config_api import get_agent_section, update_agent_section


class TestAgentConfigAPI(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		model = frappe.get_all("AI Model", fields=["name", "provider"], limit=1)
		if not model:
			self.skipTest("no AI Model records on this site")
		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"section-api-{frappe.generate_hash(length=8)}",
				"provider": model[0].provider,
				"model": model[0].name,
				"instructions": "Keep this instruction",
				"allow_chat": 0,
				"persist_conversation": 1,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		if getattr(self, "agent", None) and frappe.db.exists("Agent", self.agent.name):
			frappe.delete_doc("Agent", self.agent.name, ignore_permissions=True, force=True)

	def test_section_read_is_narrow(self):
		result = get_agent_section(self.agent.name, "general")

		self.assertEqual(result["name"], self.agent.name)
		self.assertIn("instructions", result["values"])
		self.assertNotIn("agent_tool", result["values"])
		self.assertNotIn("agent_knowledge", result["values"])

	def test_section_update_preserves_other_sections(self):
		before = get_agent_section(self.agent.name, "behavior")
		result = update_agent_section(
			self.agent.name,
			"behavior",
			{"allow_chat": 1, "persist_conversation": 1},
			before["modified"],
		)

		self.assertEqual(result["values"]["allow_chat"], 1)
		self.assertEqual(
			frappe.db.get_value("Agent", self.agent.name, "instructions"),
			"Keep this instruction",
		)

	def test_stale_revision_is_rejected(self):
		before = get_agent_section(self.agent.name, "behavior")
		frappe.db.set_value("Agent", self.agent.name, "description", "changed elsewhere")

		with self.assertRaises(frappe.TimestampMismatchError):
			update_agent_section(
				self.agent.name,
				"behavior",
				{"persist_conversation": 1},
				before["modified"],
			)

	def test_cross_section_field_is_rejected(self):
		before = get_agent_section(self.agent.name, "behavior")

		with self.assertRaises(frappe.ValidationError):
			update_agent_section(
				self.agent.name,
				"behavior",
				{"instructions": "not a behavior field"},
				before["modified"],
			)

	def test_general_section_can_rename_agent(self):
		before = get_agent_section(self.agent.name, "general")
		new_name = f"{self.agent.name}-renamed"

		result = update_agent_section(
			self.agent.name,
			"general",
			{"agent_name": new_name},
			before["modified"],
		)

		self.agent = frappe.get_doc("Agent", new_name)
		self.assertEqual(result["name"], new_name)
		self.assertEqual(self.agent.agent_name, new_name)


class TestAgentEditVsExecutionAccessAreSeparateAxes(IntegrationTestCase):
	"""Pins the intentional split documented in agent_config_api's module
	docstring: `agent.edit` (config-edit) and allowed_users/allowed_roles
	(execution access) are independent permission axes over the same Agent
	document. See Tracks/AgentPermissionsAudit/AGENT_PERMISSIONS_AUDIT.md,
	finding F13 / OQ7.
	"""

	EDITOR_USER = "editor-not-runner@example.com"
	RUNNER_USER = "runner-not-editor@example.com"

	def setUp(self):
		frappe.set_user("Administrator")
		model = frappe.get_all("AI Model", fields=["name", "provider"], limit=1)
		if not model:
			self.skipTest("no AI Model records on this site")

		for user in (self.EDITOR_USER, self.RUNNER_USER):
			if not frappe.db.exists("User", user):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": user,
						"first_name": user.split("@")[0],
						"send_welcome_email": 0,
					}
				).insert(ignore_permissions=True)

		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"axis-split-{frappe.generate_hash(length=8)}",
				"provider": model[0].provider,
				"model": model[0].name,
				"instructions": "Fixture agent for permission-axis split tests.",
				"allow_chat": 0,
				"persist_conversation": 1,
				# Non-empty allowlist so the "empty allowlist = anyone" fallback
				# in check_agent_access doesn't mask the test.
				"allowed_users": [{"user": self.RUNNER_USER}],
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		if getattr(self, "agent", None) and frappe.db.exists("Agent", self.agent.name):
			frappe.delete_doc("Agent", self.agent.name, ignore_permissions=True, force=True)

	def test_agent_edit_capability_does_not_grant_execution_access(self):
		"""A user who can edit the agent's config (agent.edit) but is not in
		allowed_users/allowed_roles must still be denied at run time."""
		agent_doc = frappe.get_doc("Agent", self.agent.name)

		frappe.set_user(self.EDITOR_USER)
		try:
			with patch("huf.permissions.has_capability", return_value=True):
				# Sanity: the mocked capability does grant the config-edit gate.
				self.assertTrue(agent_doc.has_permission("write"))
		finally:
			frappe.set_user("Administrator")

		self.assertFalse(check_agent_access(agent_doc, self.EDITOR_USER))

	def test_allowed_user_without_edit_capability_cannot_update_config(self):
		"""A user listed in allowed_users (so they CAN run the agent, and per
		the read/write asymmetry documented in this module's docstring can
		also read config sections) but who lacks agent.edit must still be
		denied when WRITING to config sections -- read and write are gated
		differently, this only tests the write side."""
		self.assertTrue(check_agent_access(self.agent, self.RUNNER_USER))

		frappe.set_user(self.RUNNER_USER)
		try:
			with patch("huf.permissions.has_capability", return_value=False):
				# Read is allowlist-gated (check_agent_access), not capability-gated --
				# this user IS in allowed_users, so read succeeds even without agent.edit.
				get_agent_section(self.agent.name, "general")
				# Write IS capability-gated and must be denied regardless of allowlist membership.
				self.assertRaises(
					frappe.PermissionError,
					update_agent_section,
					self.agent.name,
					"general",
					{"agent_name": "should-not-apply"},
					str(self.agent.modified),
				)
		finally:
			frappe.set_user("Administrator")
