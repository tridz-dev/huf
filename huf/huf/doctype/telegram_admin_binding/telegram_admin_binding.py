# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TelegramAdminBinding(Document):
	"""Telegram account <-> Frappe user link for the admin cockpit (see docs/gateways/telegram-admin-cockpit.md).

	Inserted only by ``huf.ai.telegram_admin.consume_bind_code`` after the Telegram user proved possession of a
	one-time code minted by the signed-in Frappe user. The bound user is never Administrator or Guest.
	"""

	def validate(self):
		if self.frappe_user in ("Administrator", "Guest"):
			frappe.throw(_("The admin cockpit cannot act as {0}.").format(self.frappe_user))
		if not self.is_new():
			before = self.get_doc_before_save()
			if before and (before.telegram_user_id, before.frappe_user, before.gateway) != (
				self.telegram_user_id,
				self.frappe_user,
				self.gateway,
			):
				frappe.throw(_("A binding's identity cannot be changed; unbind and bind again."))
