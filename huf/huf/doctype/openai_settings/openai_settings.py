import frappe
from frappe.model.document import Document


class OpenAISettings(Document):
    """
    Legacy global settings for the OpenAI Provider.

    Audio transcription and text-to-speech are now handled by the canonical
    audio service (``huf.ai.audio_service``) via LiteLLM. This DocType is
    retained only for backward compatibility of saved configuration data.
    The provider-specific capability methods have been removed in favor of
    the unified ``transcribe_audio_file`` / ``handle_generate_audio`` paths.
    """

    def get_headers(self):
        """
        Centralized header generation for all OpenAI calls.
        """
        api_key = self.get_password("api_key")
        if not api_key:
            frappe.throw(f"{self.name}: API Key is not configured.")

        return {
            "Authorization": f"Bearer {api_key}"
        }
