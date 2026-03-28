# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MemoryRecord(Document):
    def validate(self):
        self._validate_scope_key()
        self._validate_dates()
        self._validate_supersedes()
    
    def _validate_scope_key(self):
        """Validate that scope_key matches the scope_type format."""
        if not self.scope_key:
            return
        
        if self.scope_type == "conversation" and not self.scope_key.startswith("conv-"):
            # Allow any format but warn in log
            frappe.logger().debug(f"Memory Record {self.name}: scope_key for conversation scope doesn't start with 'conv-'")
    
    def _validate_dates(self):
        """Validate effective date range."""
        if self.effective_from and self.effective_until:
            if self.effective_from > self.effective_until:
                frappe.throw(_("Effective From must be before Effective Until"))
    
    def _validate_supersedes(self):
        """Validate that supersedes doesn't create circular references."""
        if not self.supersedes_memory_record:
            return
        
        if self.supersedes_memory_record == self.name:
            frappe.throw(_("A memory record cannot supersede itself"))
        
        # Check if the superseded record exists
        superseded = frappe.db.exists("Memory Record", self.supersedes_memory_record)
        if not superseded:
            frappe.throw(_("Superseded memory record does not exist"))
    
    def on_update(self):
        """Handle status changes and cascading updates."""
        if self.has_value_changed("status") and self.status == "superseded":
            self._update_superseded_record()
    
    def _update_superseded_record(self):
        """Update the record that this one supersedes."""
        if self.supersedes_memory_record:
            frappe.db.set_value(
                "Memory Record",
                self.supersedes_memory_record,
                "status",
                "archived"
            )
    
    def increment_retrieval_count(self):
        """Increment the retrieval count when this record is accessed."""
        self.db_set("retrieval_count", self.retrieval_count + 1)
        self.db_set("last_retrieved_at", frappe.utils.now_datetime())
    
    def is_active_and_valid(self):
        """Check if this memory record is active and within its effective date range."""
        if self.status != "active":
            return False
        
        now = frappe.utils.now_datetime()
        
        if self.effective_from and now < self.effective_from:
            return False
        
        if self.effective_until and now > self.effective_until:
            return False
        
        return True
    
    def get_data_dict(self):
        """Parse and return the data_json as a dictionary."""
        import json
        if not self.data_json:
            return {}
        try:
            return json.loads(self.data_json)
        except json.JSONDecodeError:
            frappe.log_error(f"Invalid JSON in Memory Record {self.name}", "Memory Record")
            return {}
