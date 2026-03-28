# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MemoryPolicy(Document):
    def validate(self):
        self._validate_memory_agent()
        self._validate_frequency_value()
        self._validate_idle_timeout()
        self._validate_schema_json()
        self._load_profile_defaults()
    
    def _validate_memory_agent(self):
        """Validate memory agent is specified when capture_owner is memory_agent."""
        if self.capture_owner == "memory_agent" and not self.memory_agent:
            frappe.throw(_("Memory Agent is required when Capture Owner is set to 'memory_agent'"))
    
    def _validate_frequency_value(self):
        """Validate frequency value is provided for n-based frequency types."""
        if self.capture_frequency_type in ["every_n_runs", "every_n_turns"]:
            if not self.capture_frequency_value or self.capture_frequency_value < 1:
                frappe.throw(_("Capture Frequency Value must be at least 1 for n-based frequency types"))
    
    def _validate_idle_timeout(self):
        """Validate idle timeout is specified when strategy is idle_timeout."""
        if self.conversation_end_strategy == "idle_timeout":
            if not self.idle_timeout_minutes or self.idle_timeout_minutes < 1:
                frappe.throw(_("Idle Timeout Minutes must be at least 1 when using idle timeout strategy"))
    
    def _validate_schema_json(self):
        """Validate that capture_schema_json is valid JSON if provided."""
        if not self.capture_schema_json:
            return
        
        import json
        try:
            json.loads(self.capture_schema_json)
        except json.JSONDecodeError as e:
            frappe.throw(_("Invalid JSON in Capture Schema: {0}").format(str(e)))
    
    def _load_profile_defaults(self):
        """Load defaults from Memory Profile if specified and not already set."""
        if not self.memory_profile:
            return
        
        # Only load defaults on first creation
        if not self.is_new():
            return
        
        try:
            profile = frappe.get_doc("Memory Profile", self.memory_profile)
            
            # Load defaults only if not explicitly set
            if not self.capture_prompt and profile.default_capture_prompt:
                self.capture_prompt = profile.default_capture_prompt
            
            if not self.capture_schema_json and profile.default_schema_json:
                self.capture_schema_json = profile.default_schema_json
            
            if profile.default_capture_stage and self.capture_stage == "post_response_async":
                self.capture_stage = profile.default_capture_stage
            
            if profile.default_frequency and self.capture_frequency_type == "every_run":
                self.capture_frequency_type = profile.default_frequency
            
            if profile.default_scope_type:
                # This would be stored or used when creating memory records
                pass
            
            if profile.default_retrieval_mode and self.retrieval_mode_default == "hybrid":
                self.retrieval_mode_default = profile.default_retrieval_mode
                
        except frappe.DoesNotExistError:
            frappe.log_error(f"Memory Profile {self.memory_profile} not found", "Memory Policy")
    
    def should_capture(self, run_count=None, turn_count=None, conversation_ended=False, is_idle=False):
        """Determine if capture should occur based on frequency settings."""
        if not self.enabled:
            return False
        
        if self.capture_frequency_type == "every_run":
            return True
        
        if self.capture_frequency_type == "every_n_runs" and run_count is not None:
            return run_count % self.capture_frequency_value == 0
        
        if self.capture_frequency_type == "every_n_turns" and turn_count is not None:
            return turn_count % self.capture_frequency_value == 0
        
        if self.capture_frequency_type == "conversation_end" and conversation_ended:
            return True
        
        if self.capture_frequency_type == "manual":
            return False  # Manual capture doesn't trigger automatically
        
        return False
    
    def get_indexing_config(self):
        """Return the indexing configuration for this policy."""
        return {
            "enable_fts": self.enable_fts_index,
            "enable_vector": self.enable_vector_index,
            "vector_backend": self.vector_backend if self.enable_vector_index else None,
            "fts_backend": self.fts_backend if self.enable_fts_index else None
        }
