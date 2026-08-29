# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MeetingChatMessage(Document):
	def on_trash(self):
		if self.is_system_owned and not (
			frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_uninstall
		):
			frappe.throw(
				_("System-owned meeting chat messages cannot be deleted."),
				title=_("Meeting Chat Message Protected"),
			)
