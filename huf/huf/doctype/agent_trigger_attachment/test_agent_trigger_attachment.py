# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentTriggerAttachment(HufTestSuite):
	"""`Agent Trigger Attachment` is a child table (istable=1) of the
	`file_attachments` field on `Agent Trigger`, so it is tested as rows on a
	parent Agent Trigger."""

	def _make_trigger(self, file_attachments):
		return frappe.get_doc({
			"doctype": "Agent Trigger",
			"trigger_name": "_Test Attachment Trigger",
			"agent": self.bootstrap.agent.name,
			"trigger_type": "Doc Event",
			"reference_doctype": "ToDo",
			"doc_event": "after_insert",
			"file_attachments": file_attachments,
		}).insert(ignore_permissions=True)

	def test_attachment_row_saved_on_trigger(self):
		trigger = self._make_trigger([
			{"doctype": "Agent Trigger Attachment", "field_name": "file"},
		])

		self.assertEqual(len(trigger.file_attachments), 1)
		row = trigger.file_attachments[0]
		self.assertEqual(row.field_name, "file")
		self.assertEqual(row.parenttype, "Agent Trigger")
		self.assertEqual(row.parent, trigger.name)

	def test_field_name_required(self):
		with self.assertRaises(frappe.MandatoryError):
			self._make_trigger([
				{"doctype": "Agent Trigger Attachment"},
			])

	def test_source_type_defaults_to_docfield(self):
		trigger = self._make_trigger([
			{"doctype": "Agent Trigger Attachment", "field_name": "file"},
		])

		self.assertEqual(trigger.file_attachments[0].source_type, "DocField")

	def test_child_table_field_row(self):
		trigger = self._make_trigger([
			{
				"doctype": "Agent Trigger Attachment",
				"source_type": "Child Table Field",
				"child_table": "items",
				"field_name": "image",
			},
		])

		row = trigger.file_attachments[0]
		self.assertEqual(row.source_type, "Child Table Field")
		self.assertEqual(row.child_table, "items")
		self.assertEqual(row.field_name, "image")
