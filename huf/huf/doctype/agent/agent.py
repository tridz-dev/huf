# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from huf.ai.agent_hooks import clear_doc_event_agents_cache
from frappe.utils import now_datetime
from huf.ai.agent_integration import run_agent_sync 
import random

from huf.ai.prompt_cache_capabilities import model_supports_prompt_caching

from huf.ai.orchestration.planning import run_planning
from huf.ai.orchestration.orchestrator import parse_plan_steps, create_orchestration

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


def _check_model_supports_caching(model_name: str, provider_name: str) -> bool:
    """Thin wrapper — delegates to the shared capabilities module."""
    return model_supports_prompt_caching(model_name, provider_name)

def _get_cacheable_models_for_provider(
    provider_doc_name: str, provider_name: str, exclude_model: str = None
) -> list:
    try:
        all_models = frappe.get_all(
            "AI Model",
            filters={"provider": provider_doc_name},
            fields=["name", "model_name"],
        )
    except Exception:
        return []

    cacheable = []
    for m in all_models:
        mn = m.get("model_name") or m.get("name")
        if exclude_model and mn == exclude_model:
            continue
        if _check_model_supports_caching(mn, provider_name):
            cacheable.append(mn)

    return cacheable


@frappe.whitelist()
def get_cacheable_models(provider: str, model: str = None) -> dict:
    if not provider:
        return {"supported": False, "alternatives": []}

    model_name = None
    if model:
        model_name = frappe.db.get_value("AI Model", model, "model_name") or model

    provider_name = frappe.db.get_value("AI Provider", provider, "provider_name") or provider

    supported = False
    if model_name:
        supported = _check_model_supports_caching(model_name, provider_name)

    alternatives = _get_cacheable_models_for_provider(
        provider_doc_name=provider,
        provider_name=provider_name,
        exclude_model=model_name,
    )

    return {"supported": supported, "alternatives": alternatives}

class Agent(Document):
    def validate(self):
        self._validate_prompt()

        if self.allow_chat == 1 and self.persist_conversation == 0:
            frappe.throw(_("An agent cannot be allowed in Agent Chat when persistent conversation is off."))
        
        # Validate prompt caching configuration
        if self.enable_prompt_caching:
            self._validate_prompt_caching()

        self._validate_advanced_models()
        self._validate_skills()

    def _validate_skills(self):
        """Prevent duplicate skills from being attached to an agent."""
        seen = set()
        for row in self.get("agent_skill", []):
            if row.skill in seen:
                frappe.throw(_("Skill {0} is attached more than once.").format(row.skill))
            seen.add(row.skill)

    def _validate_advanced_models(self):
        def _has_modality(model_docname: str, required: str) -> bool:
            if not model_docname:
                return True
            modalities = frappe.db.get_value("AI Model", model_docname, "modalities") or ""
            # MultiSelect is stored as CSV
            items = {m.strip() for m in modalities.split(",") if m and m.strip()}
            return required in items

        # Image generation model
        if getattr(self, "image_generation_model", None):
            if not _has_modality(self.image_generation_model, "Image"):
                frappe.throw(
                    _("Selected Image Generation Model does not support modality: Image"),
                    title=_("Invalid Model Capability"),
                )

        # TTS model
        if getattr(self, "tts_model", None):
            if not _has_modality(self.tts_model, "Text-to-Speech"):
                frappe.throw(
                    _("Selected TTS Model does not support modality: Text-to-Speech"),
                    title=_("Invalid Model Capability"),
                )

        # STT model (audio transcription)
        if getattr(self, "stt_model", None):
            if not _has_modality(self.stt_model, "Transcription"):
                frappe.throw(
                    _("Selected STT Model does not support modality: Transcription"),
                    title=_("Invalid Model Capability"),
                )

    def _validate_prompt_caching(self):
        if not self.model:
            frappe.throw(_("A model must be selected before enabling prompt caching."))
        try:
            model_doc = frappe.get_doc("AI Model", self.model)
            model_name = model_doc.model_name or model_doc.name
            provider_name = (
                frappe.db.get_value("AI Provider", self.provider, "provider_name")
                or self.provider
            )
        except Exception as e:
            frappe.log_error(
                f"Error loading model/provider for caching validation: {e}",
                "Agent Prompt Caching Validation",
            )
            return
        if _check_model_supports_caching(model_name, provider_name):
            return  
        alternatives = _get_cacheable_models_for_provider(
            provider_doc_name=self.provider,
            provider_name=provider_name,
            exclude_model=model_name,
        )

        msg = _(
            "The selected model <b>{model}</b> does not support prompt caching."
        ).format(model=model_name)

        if alternatives:
            shown = alternatives[:5]
            alt_html = ", ".join(f"<b>{a}</b>" for a in shown)
            msg += "<br><br>"
            msg += _("Supported models from <b>{provider}</b>: {models}.").format(
                provider=provider_name,
                models=alt_html,
            )
            if len(alternatives) > 5:
                msg += " " + _("(and {n} more)").format(n=len(alternatives) - 5)
        else:
            msg += "<br><br>"
            msg += _(
                "No other models from <b>{provider}</b> currently support prompt caching. "
                "Please disable prompt caching or switch to a different provider."
            ).format(provider=provider_name)

        frappe.throw(msg, title=_("Prompt Caching Not Supported"))


    def _validate_prompt(self):
        """Validate prompt configuration based on prompt_mode."""
        mode = self.prompt_mode or "Local"

        if mode == "Template":
            if not self.agent_prompt:
                frappe.throw(_("Please select an Agent Prompt when using Template mode."))
            # Record the template version when first attached or when template changes
            if self.has_value_changed("agent_prompt") or not self.template_version_at_attach:
                self._record_template_version()
        else:
            # Local mode — require instructions (backward compatible)
            if not self.instructions:
                frappe.throw(_("Please provide an instruction for this AI Agent."))

    def _record_template_version(self):
        """Snapshot the current version of the linked Agent Prompt."""
        if self.agent_prompt:
            version = frappe.db.get_value("Agent Prompt", self.agent_prompt, "version")
            self.template_version_at_attach = version or 1

    def get_indicator(doc):
        if doc.disabled:
            return _("Disabled"), "red", "disabled,=,Yes"
        else:
            return _("Enabled"), "green", "disabled,=,No"

    def on_update(self):
        clear_doc_event_agents_cache()

        if self.flags.in_insert:
            return

        prompt_changed = (
            self.has_value_changed("instructions")
            or self.has_value_changed("agent_prompt")
            or self.has_value_changed("prompt_mode")
        )
        if self.enable_multi_run and (
            prompt_changed or self.has_value_changed("enable_multi_run")
        ):
            self.generate_default_plan()
        
    def on_trash(self):
        clear_doc_event_agents_cache()
    
    def generate_default_plan(self):
        """
        Generates the default plan using run_agent_sync directly.
        Returns the agent_run_id so it can be used as a Parent Run.
        """
        from huf.ai.prompt_resolver import resolve_prompt

        resolved = resolve_prompt(self)
        if not resolved:
            return None

        planning_prompt = f"""You are a planning assistant. Break down the user's objective into a sequence of clear, atomic steps that can be executed one at a time.

            Rules:
            - Each step should be self-contained and actionable
            - Steps should be in logical order
            - Return ONLY a numbered list, nothing else
            - Keep steps concise but clear

            Example format:
            1. First action to take
            2. Second action to take

            Now break down this objective:
            {resolved}"""

        try:
            result = run_agent_sync(
                agent_name=self.name,
                prompt=planning_prompt,
                provider=self.provider,
                model=self.model,
                channel_id="orchestration_planning"
            )
            
            planning_run_id = result.get("agent_run_id")
            plan_text = result.get("response", "")
            
            steps = parse_plan_steps(plan_text)
            
            if steps:
                self.reload()
                self.set("default_plan", [])
                for idx, step in enumerate(steps, start=1):
                    self.append("default_plan", {
                        "step_index": idx,
                        "instruction": step,
                        "status": "pending"
                    })
                
                self.flags.ignore_recursion = True
                self.save()
                self.flags.ignore_recursion = False
            
            return planning_run_id, steps
                
        except Exception as e:
            frappe.log_error(f"Plan Generation Failed: {str(e)}", "Agent Plan Error")
            return None

    def set_default_color(self):
        if not self.agent_color:
                avatar_colors_hex = [
                    "#6366F1",  # indigo-500
                    "#2563EB",  # blue-600
                    "#10B981",  # emerald-500
                    "#14B8A6",  # teal-500
                    "#8B5CF6",  # violet-500
                    "#A855F7",  # purple-500
                    "#F97316",  # orange-500
                    "#F43F5E",  # rose-500
                    "#475569",  # slate-600
                    "#52525B",  # zinc-600
                ]
                self.agent_color = random.choice(avatar_colors_hex)
                self.save()

    def after_insert(self):
        """
        Trigger Multi-Run setup on Agent Creation.
        Uses the Planning Run as the Parent Run.
        """
        self.set_default_color()
        self.flags.in_insert = True
        from huf.ai.prompt_resolver import resolve_prompt
        resolved = resolve_prompt(self)
        if self.enable_multi_run and resolved:
            try:
                planning_run_id, steps = self.generate_default_plan()
                if planning_run_id:
                    create_orchestration(
                        agent_name=self.name,
                        user_prompt=resolved,
                        parent_run_id=planning_run_id,
                        override_plan=steps
                    )
                
            except Exception as e:
                frappe.log_error(f"Multi-Run Setup Failed: {str(e)}", "Agent Creation Error")

    
    def has_permission(self, permission_type=None, verbose=False):
        from huf.permissions import has_capability
        user = frappe.session.user

        # System Manager always has full access
        if "System Manager" in frappe.get_roles(user):
            return True

        # Strict Capability Checks for Mutating Actions
        if permission_type == "create":
            return has_capability(user, "agent.create")
        
        if permission_type in ("write", "save"):
            return has_capability(user, "agent.edit")

        if permission_type == "delete":
            return has_capability(user, "agent.delete")

        # Access/Read Permissions
        if self.owner == user:
            return True

        # Fetch the restrictions from the child tables
        allowed_users = [d.user for d in self.allowed_users]
        allowed_roles = [d.role for d in self.allowed_roles]

        # If both lists are empty, anyone can access (standard Huf behavior)
        if not allowed_users and not allowed_roles:
            return True

        if user in allowed_users:
            return True

        my_roles = frappe.get_roles(user)
        if set(my_roles).intersection(allowed_roles):
            return True

        return False