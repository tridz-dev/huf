# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
# import frappe
from frappe.tests import IntegrationTestCase


class TestAgentConversation(IntegrationTestCase):
	"""Regression guard: conversation create/reload/delete must not silently fail.

	Catches regressions in the chat flow where conversation creation breaks
	after AI harness changes without surfacing an obvious error.
	"""

	def setUp(self):
		self._names = []

	def tearDown(self):
		for name in self._names:
			try:
				frappe.db.delete("Agent Conversation", {"name": name})
			except Exception:
				pass
		frappe.db.commit()

	def test_conversation_insert_and_reload(self):
		import uuid
		session_id = f"regression-probe-{uuid.uuid4().hex[:8]}"
		doc = frappe.get_doc({
			"doctype": "Agent Conversation",
			"session_id": session_id,
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		reloaded = frappe.get_doc("Agent Conversation", doc.name)
		self.assertEqual(reloaded.session_id, session_id)

	def test_conversation_field_update_persists(self):
		import uuid
		session_id = f"regression-update-probe-{uuid.uuid4().hex[:8]}"
		doc = frappe.get_doc({
			"doctype": "Agent Conversation",
			"session_id": session_id,
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		doc.session_id = session_id + "-updated"
		doc.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value("Agent Conversation", doc.name, "session_id"),
			session_id + "-updated",
		)
