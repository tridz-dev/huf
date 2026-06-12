# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Skill(Document):
	def validate(self):
		if self.source_type == "App Provided" and not self.provider_app:
			frappe.throw(_("Provider App is required for App Provided skills."))
