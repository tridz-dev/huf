# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import json


class MemoryProfile(Document):
    def validate(self):
        self._validate_json_fields()
        self._validate_system_profile()
    
    def _validate_json_fields(self):
        """Validate all JSON fields contain valid JSON."""
        json_fields = [
            ("default_schema_json", "Default Schema"),
            ("default_memory_type_mapping", "Default Memory Type Mapping"),
            ("ui_labels_json", "UI Labels"),
            ("example_memories_json", "Example Memories")
        ]
        
        for field_name, label in json_fields:
            value = getattr(self, field_name)
            if value:
                try:
                    json.loads(value)
                except json.JSONDecodeError as e:
                    frappe.throw(_("Invalid JSON in {0}: {1}").format(label, str(e)))
    
    def _validate_system_profile(self):
        """Validate system profile restrictions."""
        if not self.is_system_profile:
            return
        
        # System profiles require certain fields
        if not self.default_capture_prompt:
            frappe.msgprint(
                _("Warning: System profiles should typically include a default capture prompt"),
                alert=True
            )
    
    def before_insert(self):
        """Set default icon based on category if not provided."""
        if not self.icon:
            self.icon = self._get_default_icon()
    
    def _get_default_icon(self):
        """Get default icon emoji based on category."""
        icons = {
            "Programming": "💻",
            "Science/Research": "🔬",
            "Language Learning": "🗣️",
            "Reasoning/Mathematics": "🧮",
            "General Knowledge": "🧠",
            "Travel Planning": "✈️",
            "CRM/Customer Context": "👥",
            "Support Ticket": "🎫",
            "Documentation": "📚",
            "Custom": "⚙️"
        }
        return icons.get(self.category, "📝")
    
    def get_schema_dict(self):
        """Parse and return the default schema as a dictionary."""
        if not self.default_schema_json:
            return {}
        try:
            return json.loads(self.default_schema_json)
        except json.JSONDecodeError:
            frappe.log_error(f"Invalid JSON schema in Memory Profile {self.name}", "Memory Profile")
            return {}
    
    def get_memory_type_mapping(self):
        """Parse and return the memory type mapping as a dictionary."""
        if not self.default_memory_type_mapping:
            return {}
        try:
            return json.loads(self.default_memory_type_mapping)
        except json.JSONDecodeError:
            frappe.log_error(f"Invalid memory type mapping in Memory Profile {self.name}", "Memory Profile")
            return {}
    
    def get_ui_labels(self):
        """Parse and return UI labels as a dictionary."""
        if not self.ui_labels_json:
            return {}
        try:
            return json.loads(self.ui_labels_json)
        except json.JSONDecodeError:
            frappe.log_error(f"Invalid UI labels in Memory Profile {self.name}", "Memory Profile")
            return {}
    
    def get_example_memories(self):
        """Parse and return example memories as a list."""
        if not self.example_memories_json:
            return []
        try:
            data = json.loads(self.example_memories_json)
            if isinstance(data, list):
                return data
            return [data]
        except json.JSONDecodeError:
            frappe.log_error(f"Invalid example memories in Memory Profile {self.name}", "Memory Profile")
            return []
    
    def get_default_policy_settings(self):
        """Return a dictionary of default policy settings from this profile."""
        return {
            "capture_stage": self.default_capture_stage,
            "frequency": self.default_frequency,
            "scope_type": self.default_scope_type,
            "indexing_mode": self.default_indexing_mode,
            "retrieval_mode": self.default_retrieval_mode,
            "capture_prompt": self.default_capture_prompt,
            "schema_json": self.default_schema_json,
            "recommended_model": self.recommended_model,
            "recommended_provider": self.recommended_provider
        }
    
    def on_trash(self):
        """Prevent deletion of system profiles for non-System Managers."""
        if self.is_system_profile and "System Manager" not in frappe.get_roles():
            frappe.throw(_("System profiles can only be deleted by System Managers"))
    
    @staticmethod
    def get_profiles_by_category(category=None):
        """Get profiles filtered by category."""
        filters = {"enabled": 1} if hasattr(MemoryProfile, 'enabled') else {}
        if category:
            filters["category"] = category
        
        return frappe.get_all(
            "Memory Profile",
            filters=filters,
            fields=["name", "profile_name", "category", "icon", "description", "is_system_profile"]
        )
    
    @staticmethod
    def get_system_profiles():
        """Get all system profiles."""
        return frappe.get_all(
            "Memory Profile",
            filters={"is_system_profile": 1},
            fields=["name", "profile_name", "category", "icon", "description"]
        )
