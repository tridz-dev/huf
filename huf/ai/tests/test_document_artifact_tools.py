# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for huf.ai.tools.document_artifact.handle_show_artifact.

show_artifact opens a document in the user's right-side preview pane by
publishing on the conversation's socket.io channel
(``conversation:<conversation_id>``). That channel name is guessable by
construction - any client that knows a conversation id could, in principle,
subscribe to it - so ``frappe.publish_realtime(..., user=...)`` is the ONLY
thing standing between "artifact opens for the owning user" and "artifact
opens for whoever happens to be listening on that channel". These tests
exist to pin two failure modes that would each be silent in normal use
(the tool still returns success=True, and nothing looks wrong until a user
reports someone else's document opening in their pane, or their own pane
never opening):

1. an agent pointing the tool at an artifact from a DIFFERENT conversation
   than the one it is actually running in must be rejected, not silently
   opened;
2. the realtime publish must always carry ``user=`` scoping.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_document_artifact_tools
"""

import json
import unittest
from unittest import mock

import frappe

from huf.ai.tools.document_artifact import handle_show_artifact


class TestShowArtifact(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conversations = []
		self._artifacts = []

		self.conversation_a = self._make_conversation()
		self.conversation_b = self._make_conversation()
		self.artifact_in_a = self._make_artifact(self.conversation_a)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._artifacts:
			frappe.delete_doc("Artifact", name, ignore_permissions=True, force=True)
		for name in self._conversations:
			frappe.delete_doc("Agent Conversation", name, ignore_permissions=True, force=True)

	def _make_conversation(self):
		conversation = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": f"show-artifact-test-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
			}
		)
		conversation.insert(ignore_permissions=True)
		self._conversations.append(conversation.name)
		return conversation.name

	def _make_artifact(self, conversation):
		artifact = frappe.get_doc(
			{
				"doctype": "Artifact",
				"conversation": conversation,
				"artifact_type": "document",
				"title": "Test Document",
				"content": "# Hello",
			}
		)
		artifact.insert(ignore_permissions=True)
		self._artifacts.append(artifact.name)
		return artifact.name

	# -- cross-conversation rejection --------------------------------------

	def test_artifact_from_another_conversation_is_rejected(self):
		"""The model only ever supplies artifact_id; conversation_id comes
		from the injected run context (huf.ai.sdk_tools._merge_run_context),
		reflecting the conversation the agent is actually running in - NOT
		something the model can override. If a run happened to be told about
		an artifact_id that belongs to a different conversation (e.g. a stale
		id from context, or a mistaken tool call), the pane must not open."""
		with mock.patch("frappe.publish_realtime") as mock_publish:
			result = json.loads(
				handle_show_artifact(artifact_id=self.artifact_in_a, conversation_id=self.conversation_b)
			)

		self.assertFalse(result["success"])
		self.assertIn("does not belong", result["error"])
		mock_publish.assert_not_called()

	def test_missing_artifact_fails_cleanly(self):
		"""A stale or mistyped id must come back as a structured error, not a
		raised DoesNotExistError surfacing as an opaque tool failure."""
		with mock.patch("frappe.publish_realtime") as mock_publish:
			result = json.loads(
				handle_show_artifact(artifact_id="Artifact-does-not-exist", conversation_id=self.conversation_a)
			)

		self.assertFalse(result["success"])
		mock_publish.assert_not_called()

	def test_missing_conversation_id_fails_cleanly(self):
		"""conversation_id is always injected by the run context, but the
		handler must not assume that and blow up if it is ever absent."""
		result = json.loads(handle_show_artifact(artifact_id=self.artifact_in_a))
		self.assertFalse(result["success"])

	# -- success path + user= scoping ---------------------------------------

	def test_matching_conversation_opens_the_pane(self):
		with mock.patch("frappe.publish_realtime") as mock_publish:
			result = json.loads(
				handle_show_artifact(artifact_id=self.artifact_in_a, conversation_id=self.conversation_a)
			)

		self.assertTrue(result["success"], result)
		self.assertEqual(result["artifact_id"], self.artifact_in_a)
		mock_publish.assert_called_once()

	def test_publish_is_scoped_with_user(self):
		"""The channel name (conversation:<id>) is guessable, so `user=` is
		the only thing that keeps this event private to the conversation's
		owner. Scoping by doctype/docname (the OTHER realtime pattern used
		elsewhere in this codebase) is NOT sufficient here and must not be
		substituted in - the spec calls this out explicitly."""
		with mock.patch("frappe.publish_realtime") as mock_publish:
			handle_show_artifact(artifact_id=self.artifact_in_a, conversation_id=self.conversation_a)

		mock_publish.assert_called_once()
		_, kwargs = mock_publish.call_args
		self.assertEqual(kwargs.get("user"), frappe.session.user)
		self.assertEqual(kwargs.get("event"), f"conversation:{self.conversation_a}")
		self.assertEqual(kwargs["message"]["type"], "open_artifact_pane")
		self.assertEqual(kwargs["message"]["artifact_id"], self.artifact_in_a)
		self.assertEqual(kwargs["message"]["conversation_id"], self.conversation_a)
