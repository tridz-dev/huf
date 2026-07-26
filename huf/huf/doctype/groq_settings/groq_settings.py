import frappe
from frappe.model.document import Document


class GroqSettings(Document):
    """
    Legacy global settings for the Groq Provider.

    Audio transcription is now handled by the canonical audio service
    (``huf.ai.audio_service``) via LiteLLM. This DocType is retained only
    for backward compatibility of saved configuration data.
    """

    def get_headers(self):
        api_key = self.get_password("api_key")
        if not api_key:
            frappe.throw(f"{self.name}: API Key is not configured.")

        return {
            "Authorization": f"Bearer {api_key}"
        }
