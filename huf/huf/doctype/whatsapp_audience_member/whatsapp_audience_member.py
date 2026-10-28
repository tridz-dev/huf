# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppAudienceMember(Document):
	"""One contact in an audience. Name is ``<audience>-<recipient>``, so (audience, recipient) is unique."""

	def autoname(self):
		self.name = f"{self.audience}-{self.recipient}"[:140]

	def validate(self):
		if not getattr(frappe.flags, "in_audience_api", False):
			frappe.throw("Audience members can only be changed through the audience API.", frappe.PermissionError)

	def on_trash(self):
		if not getattr(frappe.flags, "in_audience_api", False):
			frappe.throw("Audience members can only be removed through the audience API.", frappe.PermissionError)
