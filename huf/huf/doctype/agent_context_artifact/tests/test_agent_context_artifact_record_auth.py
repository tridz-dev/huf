"""Test record-level authorization for Agent Context Artifact doctype.

Tests the has_permission hook for Agent Context Artifact, verifying
that only users who own the artifact's conversation, System Manager,
or users with chat.view_all can access an artifact.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestAgentContextArtifactRecordAuth(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

	def test_agent_context_artifact_conversation_owner_can_read(self):
		"""Owner of the artifact's conversation can read it."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test artifact in that conversation
		artifact_doc = frappe.new_doc("Agent Context Artifact")
		artifact_doc.conversation = conv_doc.name
		artifact_doc.artifact_type = "JSON"
		artifact_doc.payload_json = '{"test": "data"}'
		artifact_doc.insert()

		try:
			# Verify alice can read it
			from huf.ai.record_access import user_can_read_context_artifact
			assert user_can_read_context_artifact(artifact_doc, user="alice@example.com") is True
		finally:
			artifact_doc.delete()
			conv_doc.delete()

	def test_agent_context_artifact_non_conversation_owner_cannot_read(self):
		"""Non-owner of the conversation cannot read its artifacts."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test artifact in that conversation
		artifact_doc = frappe.new_doc("Agent Context Artifact")
		artifact_doc.conversation = conv_doc.name
		artifact_doc.artifact_type = "JSON"
		artifact_doc.payload_json = '{"test": "data"}'
		artifact_doc.insert()

		try:
			# Verify bob cannot read it
			from huf.ai.record_access import user_can_read_context_artifact
			assert user_can_read_context_artifact(artifact_doc, user="bob@example.com") is False
		finally:
			artifact_doc.delete()
			conv_doc.delete()

	def test_agent_context_artifact_system_manager_can_read(self):
		"""System Manager can read any artifact."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test artifact in that conversation
		artifact_doc = frappe.new_doc("Agent Context Artifact")
		artifact_doc.conversation = conv_doc.name
		artifact_doc.artifact_type = "JSON"
		artifact_doc.payload_json = '{"test": "data"}'
		artifact_doc.insert()

		try:
			# Verify System Manager can read it
			from huf.ai.record_access import user_can_read_context_artifact
			assert user_can_read_context_artifact(artifact_doc, user="Administrator") is True
		finally:
			artifact_doc.delete()
			conv_doc.delete()

	def test_agent_context_artifact_chat_view_all_capability_can_read(self):
		"""A non-owner with the chat.view_all capability can read any artifact."""
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		artifact_doc = frappe.new_doc("Agent Context Artifact")
		artifact_doc.conversation = conv_doc.name
		artifact_doc.artifact_type = "JSON"
		artifact_doc.payload_json = '{"test": "data"}'
		artifact_doc.insert()

		try:
			from huf.ai.record_access import user_can_read_context_artifact

			with patch("huf.permissions.has_capability", return_value=True):
				assert user_can_read_context_artifact(artifact_doc, user="carol@example.com") is True
		finally:
			artifact_doc.delete()
			conv_doc.delete()
