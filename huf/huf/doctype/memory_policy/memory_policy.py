# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MemoryPolicy(Document):
    def validate(self):
        if self.auto_promote_to_knowledge and not self.knowledge_source:
            frappe.throw(_("Knowledge Source is required when Auto Promote to Knowledge is enabled"))

        if self.agent and self.scope_type == "Agent" and not self.scope_key:
            self.scope_key = self.agent

        if self.scope_type == "Site" and not self.scope_key:
            self.scope_key = frappe.local.site

        if self.scope_type == "Global" and not self.scope_key:
            self.scope_key = "global"
