# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AgentPromptCategory(Document):
	def validate(self):
		if self.parent_category and self.parent_category == self.name:
			frappe.throw(_("A category cannot be its own parent."))