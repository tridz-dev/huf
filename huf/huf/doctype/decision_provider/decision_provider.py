# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
import frappe
from frappe.model.document import Document
from huf.ai.provider_security import validate_api_base_url


class DecisionProvider(Document):
    def validate(self):
        if self.adapter_id and ("." in self.adapter_id or any(char.isspace() for char in self.adapter_id)):
            frappe.throw("Decision Provider Adapter ID must be a stable hook ID, not an import path.")
        validate_api_base_url(self.api_base_url)
