# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AIProvider(Document):
	def validate(self):
		self.validate_provider_name()
		self.validate_api_key()

	def validate_provider_name(self):
		# The provider name becomes the LiteLLM model routing prefix
		# (<provider>/<model>), so it must be a single word.
		if self.provider_name and any(c.isspace() for c in self.provider_name):
			if self.is_new():
				frappe.throw(_("Provider name becomes the model routing prefix — use a single word, e.g. 'Ollama'."))
			else:
				# Existing records keep working via explicit model prefixes;
				# only warn so edits are not blocked.
				frappe.msgprint(
					_("Provider names with spaces cannot be used as a model routing prefix. Use model names with an explicit prefix (e.g. 'ollama_chat/gpt-oss:20b')."),
					indicator="orange",
				)

	# Brands that are backed by per-user subscription connections rather than a
	# shared API key are allowed to omit the API key field.
	SUBSCRIPTION_BRANDS = ("openai_community", "kimi_community")

	def validate_api_key(self):
		if self.is_local_llm:
			if not (self.api_base_url or self.url):
				frappe.throw(_("API Base URL or URL is required for a local LLM provider."))
			if not self.api_key:
				# Local providers (Ollama, LM Studio) need no key; set a dummy
				# value to satisfy legacy readers that expect one.
				self.api_key = "not-needed"
		elif self.provider_brand in self.SUBSCRIPTION_BRANDS:
			# Subscription-backed providers use per-user OAuth tokens stored in
			# AI Provider Connection; no global API key is required.
			if not self.api_key:
				self.api_key = "subscription"
		elif not self.api_key:
			frappe.throw(_("API Key is required for cloud providers."))

@frappe.whitelist()
def get_provider_settings(provider_name):
    """
    Finds Single DocTypes that match the pattern '{Provider} % Settings'
    """
    if not provider_name:
        return []

    candidates = frappe.db.sql("""
        SELECT name FROM `tabDocType`
        WHERE issingle = 1
        AND name LIKE %s
        AND name LIKE '%%Settings'
    """, (f"%{provider_name}%",), as_dict=True)

    return [c.name for c in candidates]


@frappe.whitelist()
def get_configured_providers():
    """Return providers that have an API key configured (or are local LLMs).

    Only names and brands are returned; keys are never exposed.
    """
    providers = frappe.get_all(
        "AI Provider",
        fields=["name", "provider_brand", "is_local_llm"],
    )
    result = []
    for p in providers:
        if p.is_local_llm:
            result.append({"name": p.name, "provider_brand": p.provider_brand})
            continue
        try:
            key = frappe.get_doc("AI Provider", p.name).get_password("api_key")
        except Exception:
            key = None
            frappe.log_error(
                message=f"Failed to read API key for AI Provider '{p.name}':\n\n{frappe.get_traceback()}",
                title="AI Provider Key Read Error",
            )
        if key:
            result.append({"name": p.name, "provider_brand": p.provider_brand})
    return result