# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MemoryPolicy(Document):
    def validate(self):
        if self.auto_promote_to_knowledge and not self.knowledge_source:
            frappe.throw(_("Knowledge Source is required when Auto Promote to Knowledge is enabled"))

        self.validate_allowed_record_types()

        if self.agent and self.scope_type == "Agent" and not self.scope_key:
            self.scope_key = self.agent

        if self.scope_type == "Site" and not self.scope_key:
            self.scope_key = frappe.local.site

        if self.scope_type == "Global" and not self.scope_key:
            self.scope_key = "global"

    def validate_allowed_record_types(self):
        """Catch a misconfigured allow-list at save time, not at agent-runtime.

        `allowed_record_types` is free text with no schema link to Memory Record's
        `record_type` Select options, so a typo here previously caused every
        save_memory_record call to be silently rejected with no indication why.
        """
        if not self.allowed_record_types:
            return

        valid_types = (
            frappe.get_meta("Memory Record").get_field("record_type").options.split("\n")
        )
        entered_types = [line.strip() for line in self.allowed_record_types.split("\n") if line.strip()]
        invalid_types = [t for t in entered_types if t not in valid_types]

        if invalid_types:
            frappe.throw(
                _(
                    "Allowed Record Types contains values that don't match Memory Record's "
                    "Record Type options: {0}. Valid values are: {1}."
                ).format(", ".join(invalid_types), ", ".join(valid_types))
            )
