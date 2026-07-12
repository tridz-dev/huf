# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentContextArtifact(HufTestSuite):
	"""Agent Context Artifact has no custom controller logic — tests cover
	creation with defaults, autonaming, select validation and the
	conversation link relationship."""

	def test_creation_applies_defaults_and_autoname(self):
		artifact = frappe.get_doc({
			"doctype": "Agent Context Artifact",
			"summary": "Test artifact",
		}).insert(ignore_permissions=True)

		self.assertTrue(artifact.name.startswith("ART-"))
		self.assertEqual(artifact.artifact_type, "JSON")
		self.assertEqual(artifact.visibility, "user_visible")
		self.assertEqual(artifact.context_policy, "include_full")

	def test_invalid_artifact_type_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Context Artifact",
				"artifact_type": "Bogus",
			}).insert(ignore_permissions=True)

	def test_invalid_context_policy_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Context Artifact",
				"context_policy": "Bogus",
			}).insert(ignore_permissions=True)

	def test_conversation_link(self):
		conversation = frappe.get_doc({
			"doctype": "Agent Conversation",
			"agent": self.bootstrap.agent.name,
			"session_id": "test-artifact-session",
		}).insert(ignore_permissions=True)

		artifact = frappe.get_doc({
			"doctype": "Agent Context Artifact",
			"conversation": conversation.name,
			"summary": "Linked artifact",
		}).insert(ignore_permissions=True)

		self.assertEqual(artifact.conversation, conversation.name)
		self.assertEqual(
			frappe.db.get_value("Agent Conversation", artifact.conversation, "agent"),
			self.bootstrap.agent.name,
		)
