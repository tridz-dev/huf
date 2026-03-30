# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SiteVectorStoreSettings(Document):
    """Site Vector Store Settings - Global settings for vector store configuration.
    
    Controls site-wide defaults for vector database backends and fallback behavior.
    This is a singleton-style document that should only have one instance per site.
    """
    
    def validate(self):
        """Validate the settings configuration."""
        self._validate_health_check_interval()
        self._ensure_single_instance()
    
    def _validate_health_check_interval(self):
        """Ensure health check interval is reasonable."""
        if self.health_check_interval < 10:
            frappe.throw("Health Check Interval must be at least 10 seconds")
        if self.health_check_interval > 3600:
            frappe.throw("Health Check Interval cannot exceed 3600 seconds (1 hour)")
    
    def _ensure_single_instance(self):
        """Ensure only one settings document exists."""
        existing = frappe.db.exists(
            "Site Vector Store Settings",
            {"name": ("!=", self.name)}
        )
        if existing and self.is_new():
            frappe.throw(
                "Only one Site Vector Store Settings document is allowed. "
                "Please update the existing settings instead."
            )
    
    @staticmethod
    def get_settings() -> "SiteVectorStoreSettings":
        """Get the site settings, creating default if not exists.
        
        Returns:
            SiteVectorStoreSettings: The site settings document
        """
        settings = frappe.db.get_value("Site Vector Store Settings", {}, "name")
        if settings:
            return frappe.get_doc("Site Vector Store Settings", settings)
        
        # Create default settings
        doc = frappe.new_doc("Site Vector Store Settings")
        doc.default_backend = "pgvector"
        doc.fallback_enabled = 1
        doc.health_check_interval = 60
        doc.insert(ignore_permissions=True)
        return doc
    
    @staticmethod
    def get_default_backend() -> str:
        """Get the default backend type.
        
        Returns:
            str: The default backend type (e.g., 'pgvector')
        """
        try:
            settings = SiteVectorStoreSettings.get_settings()
            return settings.default_backend or "pgvector"
        except Exception:
            return "pgvector"
    
    @staticmethod
    def is_fallback_enabled() -> bool:
        """Check if fallback is enabled.
        
        Returns:
            bool: True if fallback is enabled
        """
        try:
            settings = SiteVectorStoreSettings.get_settings()
            return bool(settings.fallback_enabled)
        except Exception:
            return True
