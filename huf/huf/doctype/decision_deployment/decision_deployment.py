# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
import frappe
from frappe.model.document import Document
from huf.ai.decision.registry import discover_backends


class DecisionDeployment(Document):
    def validate(self):
        self.validate_ai_model_modality()
        self.validate_endpoint_path()
        self.validate_adapter_override()
        self.validate_default_per_model()
        if self.provider_model_id and any(char.isspace() for char in self.provider_model_id):
            frappe.throw("Provider Model ID cannot contain whitespace.")
        if self.priority is not None and self.priority < 0:
            frappe.throw("Deployment priority cannot be negative.")

    def validate_ai_model_modality(self):
        """Ensure the selected AI Model has Decision modality."""
        if not self.ai_model:
            return

        ai_model_doc = frappe.get_doc("AI Model", self.ai_model)
        modalities = ai_model_doc.get("modalities") or ""
        # Parse comma-separated modalities
        modality_list = [m.strip() for m in modalities.split(",") if m and m.strip()]

        if "Decision" not in modality_list:
            frappe.throw(
                f"AI Model '{self.ai_model}' does not have 'Decision' modality. "
                f"Only Decision-modality models can be used for Decision Deployments.",
                title="Invalid AI Model"
            )

    def validate_endpoint_path(self):
        """Ensure endpoint_path starts with '/'."""
        if self.endpoint_path and not self.endpoint_path.startswith('/'):
            frappe.throw(
                f"Endpoint path must start with '/'. Got: '{self.endpoint_path}'",
                title="Invalid Endpoint Path"
            )

    def validate_adapter_override(self):
        """Validate adapter_override against the registry of installed decision backends."""
        if not self.adapter_override:
            return

        available_adapters = discover_backends()
        if self.adapter_override not in available_adapters:
            valid_ids = ", ".join(sorted(available_adapters.keys()))
            frappe.throw(
                f"Adapter ID '{self.adapter_override}' is not registered. "
                f"Valid adapter IDs are: {valid_ids}",
                title="Invalid Adapter ID"
            )

    def validate_default_per_model(self):
        """Ensure at most one deployment is marked as default per decision model."""
        if not self.is_default_for_model or not self.decision_model:
            return

        existing_defaults = frappe.db.count(
            "Decision Deployment",
            filters={
                "decision_model": self.decision_model,
                "is_default_for_model": 1,
                "name": ["!=", self.name]
            }
        )

        if existing_defaults > 0:
            frappe.throw(
                f"Another deployment is already marked as default for model '{self.decision_model}'. "
                f"Only one default deployment per model is allowed.",
                title="Duplicate Default Deployment"
            )
