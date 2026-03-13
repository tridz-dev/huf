import frappe
import requests
import json
from frappe.model.document import Document
from frappe.utils.file_manager import get_file_path

def get_value_from_path(data, path):
    """
    Retrieves a value from a nested dict/list using dot notation.
    Example: "results.0.transcript"
    """
    if not path or not isinstance(data, (dict, list)):
        return None
        
    keys = path.split('.')
    current = data
    
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                return None
        except (IndexError, TypeError, AttributeError):
            return None
            
        if current is None:
            return None
            
    return current


class GroqSettings(Document):
    """
    Global Settings for Groq Provider.
    
    Capabilities:
    1. transcribe_audio (Speech-to-Text)
       - Uses 'whisper-large-v3' by default
    """

    ALLOWED_TRANSCRIPTION_PARAMS = {
        "model",
        "language",
        "temperature",
        "prompt",
        "response_format"
    }

    def get_headers(self):
        api_key = self.get_password("api_key")
        if not api_key:
            frappe.throw(f"{self.name}: API Key is not configured.")
        
        return {
            "Authorization": f"Bearer {api_key}"
        }

    def transcribe_audio(self, file_doc, kwargs=None) -> dict:
        kwargs = kwargs or {}

        if not file_doc:
            return {"success": False, "error": "Audio file is required"}

        file_path = _resolve_file_path(file_doc)
        if not file_path:
            return {"success": False, "error": "Unable to resolve physical file path."}

        data = {
            "model": self.model or "whisper-large-v3"
        }

        for key, value in kwargs.items():
            if key in self.ALLOWED_TRANSCRIPTION_PARAMS:
                data[key] = value

        try:
            api_url = self.api_url or "https://api.groq.com/openai/v1/audio/transcriptions"
            
            with open(file_path, "rb") as audio:
                files = {
                    self.file_param or "file": audio
                }
                
                response = requests.post(
                    api_url,
                    headers=self.get_headers(),
                    files=files,
                    data=data,
                    timeout=120
                )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "error": f"Groq Error ({response.status_code}): {response.text}"
                }

            res_json = response.json()

            path_key = self.response_path or "text"
            transcript = get_value_from_path(res_json, path_key)

            if not transcript:
                return {
                    "success": False, 
                    "error": f"Transcription success, but path '{path_key}' not found.",
                    "raw_response": res_json
                }

            return {
                "success": True,
                "result": transcript
            }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Groq Transcribe Error")
            return {"success": False, "error": str(e)}


def _resolve_file_path(file_doc):
    if hasattr(file_doc, "file_name"):
        return get_file_path(file_doc.file_name)

    if isinstance(file_doc, dict) and file_doc.get("file_name"):
        return get_file_path(file_doc["file_name"])

    return None