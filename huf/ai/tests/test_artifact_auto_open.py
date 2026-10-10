# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""A newly created document artifact (and an exported document file) announces itself so the
owner's client opens the right-hand pane without a click.

- an agent message that carries ``<artifact type="document">`` gets its Artifact row extracted;
  inserting that row publishes ``open_artifact_pane`` (same shape as ``show_artifact``) on
  ``conversation:<id>`` scoped with ``user=`` the conversation owner, after commit;
- types the pane renders from the streamed message (code, chart, ...) do NOT publish;
- re-saving the same message (an edit) does not announce again;
- ``export_document`` announces the file with ``open_file_artifact`` when the run's
  conversation is known, and stays silent when it is not.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_artifact_auto_open
"""

import json
import unittest
from unittest import mock

import frappe

from huf.ai.artifact_extraction import sync_message_artifacts
from huf.ai.tools.document_artifact import handle_export_document

DOC_TAG = '<artifact type="document" title="Board memo">\n# Board memo\n\nAll good.\n</artifact>'
CODE_TAG = '<artifact type="code" language="python" title="hi">\nprint(1)\n</artifact>'


def _pane_calls(publish):
	"""Only the pane announcements: Frappe itself publishes doc_update/list_update while saving Files."""
	return [c for c in publish.call_args_list if str(c.kwargs.get("event", "")).startswith("conversation:")]


class TestArtifactAutoOpen(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conversations = []
		self._messages = []
		self.conversation = self._make_conversation()

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._messages:
			for a in frappe.get_all("Artifact", filters={"message": name}, pluck="name"):
				frappe.delete_doc("Artifact", a, ignore_permissions=True, force=True)
			frappe.delete_doc("Agent Message", name, ignore_permissions=True, force=True)
		for name in self._conversations:
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Agent Conversation", "attached_to_name": name}, pluck="name"):
				frappe.delete_doc("File", f, ignore_permissions=True, force=True)
			frappe.delete_doc("Agent Conversation", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _make_conversation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": f"auto-open-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		self._conversations.append(doc.name)
		return doc.name

	def _message(self, content):
		msg = frappe.new_doc("Agent Message")
		msg.conversation = self.conversation
		msg.role = "agent"
		msg.content = content
		msg.flags.ignore_permissions = True
		# The doc_events hook extracts (and announces) on insert; keep that out of the way so each
		# test drives the sync by hand and observes exactly one publish.
		with mock.patch("frappe.publish_realtime"):
			msg.insert()
		self._messages.append(msg.name)
		return msg

	def _sync(self, msg):
		with mock.patch("frappe.publish_realtime") as publish:
			sync_message_artifacts(msg)
		return publish

	def test_document_artifact_creation_publishes_open_event(self):
		msg = self._message(DOC_TAG)
		frappe.db.delete("Artifact", {"message": msg.name})  # drop rows the insert hook made
		publish = self._sync(msg)

		row = frappe.get_all("Artifact", filters={"message": msg.name}, fields=["name", "artifact_type", "title"])
		self.assertEqual(len(row), 1)
		calls = _pane_calls(publish)
		self.assertEqual(len(calls), 1)
		kwargs = calls[0].kwargs
		self.assertEqual(kwargs["event"], f"conversation:{self.conversation}")
		self.assertEqual(kwargs["user"], frappe.db.get_value("Agent Conversation", self.conversation, "owner"))
		self.assertTrue(kwargs["after_commit"])
		self.assertEqual(
			kwargs["message"],
			{
				"type": "open_artifact_pane",
				"artifact_id": row[0].name,
				"conversation_id": self.conversation,
				"artifact_type": "document",
				"title": "Board memo",
			},
		)

	def test_code_artifact_does_not_publish(self):
		msg = self._message(CODE_TAG)
		frappe.db.delete("Artifact", {"message": msg.name})
		publish = self._sync(msg)
		self.assertEqual(frappe.db.count("Artifact", {"message": msg.name}), 1)
		self.assertEqual(_pane_calls(publish), [])

	def test_resaving_an_existing_artifact_does_not_announce_again(self):
		msg = self._message(DOC_TAG)
		publish = self._sync(msg)  # rows already exist from the insert hook
		self.assertEqual(frappe.db.count("Artifact", {"message": msg.name}), 1)
		self.assertEqual(_pane_calls(publish), [])

	def test_a_realtime_failure_never_blocks_the_save(self):
		msg = self._message(DOC_TAG)
		frappe.db.delete("Artifact", {"message": msg.name})
		def flaky(*args, **kwargs):
			if str(kwargs.get("event", "")).startswith("conversation:"):
				raise RuntimeError("redis down")

		with mock.patch("frappe.publish_realtime", side_effect=flaky):
			sync_message_artifacts(msg)
		self.assertEqual(frappe.db.count("Artifact", {"message": msg.name}), 1)

	def test_export_document_announces_the_file_with_a_conversation(self):
		with mock.patch("frappe.publish_realtime") as publish:
			result = json.loads(
				handle_export_document(
					content="# Plan\n\nText.", title="Plan", format="pdf", conversation_id=self.conversation
				)
			)
		self.assertTrue(result["success"], result)
		calls = _pane_calls(publish)
		self.assertEqual(len(calls), 1)
		kwargs = calls[0].kwargs
		self.assertEqual(kwargs["event"], f"conversation:{self.conversation}")
		self.assertEqual(kwargs["user"], frappe.session.user)
		msg = kwargs["message"]
		self.assertEqual(msg["type"], "open_file_artifact")
		self.assertEqual(msg["file_url"], result["file_url"])
		self.assertEqual(msg["file_name"], result["file_name"])
		self.assertEqual(msg["format"], "pdf")
		self.assertEqual(msg["conversation_id"], self.conversation)

	def test_export_document_without_a_conversation_is_silent_and_still_succeeds(self):
		with mock.patch("frappe.publish_realtime") as publish:
			result = json.loads(handle_export_document(content="# Plan", title="Plan", format="pdf"))
		self.assertTrue(result["success"], result)
		self.assertEqual(_pane_calls(publish), [])

	def test_failed_export_does_not_announce(self):
		with mock.patch("frappe.publish_realtime") as publish:
			result = json.loads(handle_export_document(format="pdf", conversation_id=self.conversation))
		self.assertFalse(result["success"])
		self.assertEqual(_pane_calls(publish), [])
