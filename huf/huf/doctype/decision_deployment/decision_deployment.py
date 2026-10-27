# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
import frappe
from frappe.model.document import Document


class DecisionDeployment(Document):
    def validate(self):
        if self.provider_model_id and any(char.isspace() for char in self.provider_model_id):
            frappe.throw("Provider Model ID cannot contain whitespace.")
        if self.priority is not None and self.priority < 0:
            frappe.throw("Deployment priority cannot be negative.")
