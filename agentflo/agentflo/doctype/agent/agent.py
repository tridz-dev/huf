# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Agent(Document):
	def validate(self):
		if  not self.instructions:
			frappe.throw(_("Please provide an instruction for this AI Agent."))

	def get_indicator(doc):
		if doc.disabled:
			return _("Disabled"), "red", "disabled,=,Yes"
		else:
			return _("Enabled"), "green", "disabled,=,No"

