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

	def validate_api_key(self):
		if self.is_local_llm:
			if not (self.api_base_url or self.url):
				frappe.throw(_("API Base URL or URL is required for a local LLM provider."))
			if not self.api_key:
				# Local providers (Ollama, LM Studio) need no key; set a dummy
				# value to satisfy legacy readers that expect one.
				self.api_key = "not-needed"
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