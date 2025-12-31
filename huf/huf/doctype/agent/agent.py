# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from huf.ai.agent_hooks import clear_doc_event_agents_cache

try:
    from litellm.utils import supports_prompt_caching
except ImportError:
    supports_prompt_caching = None

def get_permission_query_conditions(user):
    if not user:
        user = frappe.session.user

    if "System Manager" in frappe.get_roles(user):
        return None

    user_roles = frappe.get_roles(user)
    user_roles_str = "', '".join([r.replace("'", "''") for r in user_roles])

    # The Logic:
    # 1. User is the Owner
    # 2. OR User is in the 'Agent User' table
    # 3. OR User has a role that is in the 'Agent Role' table
    # 4. OR (CRITICAL) If BOTH tables are empty, allow access (Public)
    
    conditions = f"""
        (
            `tabAgent`.owner = '{user}'
            OR
            `tabAgent`.name IN (
                SELECT parent FROM `tabAgent User` 
                WHERE user = '{user}'
            )
            OR
            `tabAgent`.name IN (
                SELECT parent FROM `tabAgent Role` 
                WHERE role IN ('{user_roles_str}')
            )
            OR
            (
                NOT EXISTS (SELECT 1 FROM `tabAgent User` WHERE parent = `tabAgent`.name)
                AND
                NOT EXISTS (SELECT 1 FROM `tabAgent Role` WHERE parent = `tabAgent`.name)
            )
        )
    """
    return conditions

class Agent(Document):
    def validate(self):
        if not self.instructions:
            frappe.throw(_("Please provide an instruction for this AI Agent."))

        if self.allow_chat == 1 and self.persist_conversation == 0:
            frappe.throw(_("An agent cannot be allowed in Agent Chat when persistent conversation is off."))
        
        # Validate prompt caching configuration
        if self.enable_prompt_caching:
            if not self.model:
                frappe.throw(_("Model must be selected to enable prompt caching."))
            
            # Check if model supports prompt caching
            if supports_prompt_caching:
                try:
                    model_doc = frappe.get_doc("AI Model", self.model)
                    model_name = model_doc.model_name
                    provider_doc = frappe.get_doc("AI Provider", self.provider)
                    provider_name = provider_doc.provide_name or provider_doc.name
                    
                    # Normalize model name (add provider prefix if needed)
                    normalized_model = model_name
                    if "/" not in model_name:
                        provider_prefix_map = {
                            "openai": "openai",
                            "anthropic": "anthropic",
                            "google": "gemini",
                            "gemini": "gemini",
                            "deepseek": "deepseek",
                        }
                        prefix = provider_prefix_map.get(provider_name.lower(), provider_name.lower())
                        normalized_model = f"{prefix}/{model_name}"
                    
                    if not supports_prompt_caching(model=normalized_model):
                        frappe.msgprint(
                            _("Warning: The selected model may not support prompt caching. "
                              "Caching will be disabled for this model."),
                            indicator="orange"
                        )
                except Exception as e:
                    frappe.log_error(
                        f"Error validating prompt caching support: {str(e)}",
                        "Agent Prompt Caching Validation"
                    )



    def get_indicator(doc):
        if doc.disabled:
            return _("Disabled"), "red", "disabled,=,Yes"
        else:
            return _("Enabled"), "green", "disabled,=,No"

    def on_update(self):
        clear_doc_event_agents_cache()

    def on_trash(self):
        clear_doc_event_agents_cache()

    def has_permission(self, permission_type=None, verbose=False):
        user = frappe.session.user

        # System Manager and Owner always have access
        if "System Manager" in frappe.get_roles(user) or self.owner == user:
            return True

        # Fetch the restrictions from the child tables
        allowed_users = [d.user for d in self.allowed_users]
        allowed_roles = [d.role for d in self.allowed_roles]

        # If both lists are empty, anyone can access.
        if not allowed_users and not allowed_roles:
            return True

        if user in allowed_users:
            return True

        my_roles = frappe.get_roles(user)
        if set(my_roles).intersection(allowed_roles):
            return True

        return False