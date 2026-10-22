# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TelegramAdminAudit(Document):
	"""Append-only record of a confirmed Telegram admin cockpit action."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Telegram Admin Audit rows are append-only."))

	def on_trash(self):
		frappe.throw(_("Telegram Admin Audit rows cannot be deleted."))
