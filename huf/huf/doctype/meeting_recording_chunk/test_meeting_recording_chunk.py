# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestMeetingRecordingChunk(IntegrationTestCase):
	def setUp(self):
		self._chunk_names = []
		self._meeting_names = []

		meeting = frappe.get_doc({
			"doctype": "Meeting",
			"title": "__test_meeting_for_chunks__",
		})
		meeting.insert(ignore_permissions=True)
		self._meeting_names.append(meeting.name)
		self.meeting_name = meeting.name

	def tearDown(self):
		for name in self._chunk_names:
			frappe.db.delete("Meeting Recording Chunk", {"name": name})
		for name in self._meeting_names:
			frappe.db.delete("Meeting", {"name": name})
		frappe.db.commit()

	def test_create_chunk(self):
		doc = frappe.get_doc({
			"doctype": "Meeting Recording Chunk",
			"meeting": self.meeting_name,
			"sequence": 1,
			"upload_status": "Pending",
		})
		doc.insert(ignore_permissions=True)
		self._chunk_names.append(doc.name)

		self.assertTrue(frappe.db.exists("Meeting Recording Chunk", doc.name))

	def test_is_system_owned_defaults_to_one(self):
		doc = frappe.get_doc({
			"doctype": "Meeting Recording Chunk",
			"meeting": self.meeting_name,
			"sequence": 1,
		})
		doc.insert(ignore_permissions=True)
		self._chunk_names.append(doc.name)

		self.assertEqual(doc.is_system_owned, 1)

	def test_system_owned_chunk_delete_guard(self):
		"""Deleting a system-owned chunk should be blocked outside install/migrate/uninstall."""
		chunk = frappe.new_doc("Meeting Recording Chunk")
		chunk.meeting = self.meeting_name
		chunk.sequence = 1
		chunk.is_system_owned = 1

		with self.assertRaises(frappe.ValidationError):
			chunk.on_trash()

	def test_non_manager_role_cannot_delete(self):
		doc = frappe.get_doc({
			"doctype": "Meeting Recording Chunk",
			"meeting": self.meeting_name,
			"sequence": 1,
		})
		doc.insert(ignore_permissions=True)
		self._chunk_names.append(doc.name)

		self.assertFalse(
			frappe.has_permission(
				"Meeting Recording Chunk", ptype="delete", doc=doc.name, user="Guest"
			)
		)
