import frappe
import requests
import json
from frappe.model.document import Document
from frappe.utils.file_manager import get_file_path

def get_value_from_path(data, path):
    """
    Retrieves a value from a nested dict/list using dot notation.
    Example: "choices.0.message.content"
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

class OpenAISettings(Document):
    """
    Global Settings for OpenAI Provider.
    Capabilities:
    1. transcribe_audio (Speech-to-Text)
    2. text_to_speech (Text-to-Speech)
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

    def transcribe_audio(self, file_doc, kwargs=None) -> dict:
        kwargs = kwargs or {}

        if not file_doc:
            return {"success": False, "error": "Audio file is required"}

        file_path = _resolve_file_path(file_doc)
        if not file_path:
            return {"success": False, "error": "Unable to resolve physical file path."}

        data = {
            "model": self.model or "whisper-1"
        }
        data.update(kwargs)

        try:
            with open(file_path, "rb") as audio:
                files = {
                    self.file_param or "file": audio
                }
                
                response = requests.post(
                    self.api_url or "https://api.openai.com/v1/audio/transcriptions",
                    headers=self.get_headers(),
                    files=files,
                    data=data,
                    timeout=120
                )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "error": f"Provider Error ({response.status_code}): {response.text}"
                }

            res_json = response.json()

            path_key = self.response_path or "text"
            transcript = get_value_from_path(res_json, path_key)

            if not transcript:
                return {
                    "success": False, 
                    "error": f"Transcription success, but path '{path_key}' not found in response.",
                    "raw_response": res_json
                }

            return {
                "success": True,
                "result": transcript
            }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "OpenAI Transcribe Error")
            return {"success": False, "error": str(e)}

    def text_to_speech(self, text: str, voice: str = None, kwargs=None) -> dict:
        kwargs = kwargs or {}
        
        if not text:
            return {"success": False, "error": "Text is required for TTS."}

        url = "https://api.openai.com/v1/audio/speech"

        data = {
            "model": "tts-1",
            "input": text,
            "voice": voice or "alloy"
        }
        data.update(kwargs)

        try:
            response = requests.post(
                url,
                headers=self.get_headers(),
                json=data,
                timeout=60
            )

            if response.status_code >= 400:
                return {"success": False, "error": response.text}

            return {
                "success": True,
                "audio_content": response.content,
                "content_type": response.headers.get("Content-Type", "audio/mpeg")
            }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "OpenAI TTS Error")
            return {"success": False, "error": str(e)}


def _resolve_file_path(file_doc):
    if hasattr(file_doc, "file_name"):
        return get_file_path(file_doc.file_name)

    if isinstance(file_doc, dict) and file_doc.get("file_name"):
        return get_file_path(file_doc["file_name"])

    return None