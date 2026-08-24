# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMeetingChatMessage(FrappeTestCase):
	def test_system_owned_message_cannot_be_deleted(self):
		meeting = frappe.get_doc({"doctype": "Meeting", "title": "Chat delete guard", "status": "Draft"}).insert()
		message = frappe.get_doc({
			"doctype": "Meeting Chat Message",
			"meeting": meeting.name,
			"role": "user",
			"content": "Summarize the decisions.",
		}).insert(ignore_permissions=True)

		self.assertTrue(message.is_system_owned)
		with self.assertRaises(frappe.ValidationError):
			message.delete()

		frappe.flags.in_migrate = True
		try:
			message.delete()
		finally:
			frappe.flags.in_migrate = False
		meeting.delete()
