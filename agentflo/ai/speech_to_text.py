import frappe
import openai
import requests
import tempfile
import os
from frappe import _
from frappe.utils.file_manager import save_file, get_file_path

@frappe.whitelist()
def transcribe_audio(audio_file_url: str, language: str = "en") -> dict:
    """
    Transcribe audio using OpenAI Whisper
    
    Args:
        audio_file_url (str): URL or path to the audio file
        language (str): Language code for the audio
    
    Returns:
        dict: Transcription result
    """
    try:

        openai_provider = frappe.get_doc("AI Provider", "OpenAI")  
        api_key = openai_provider.get_password("api_key")
        
        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured"}
        

        client = openai.OpenAI(api_key=api_key)
        

        if audio_file_url.startswith('/files/'):

            file_path = get_file_path(audio_file_url.split('/')[-1])
            audio_file = open(file_path, 'rb')
        elif audio_file_url.startswith('http'):

            response = requests.get(audio_file_url)
            if response.status_code != 200:
                return {"success": False, "error": f"Failed to download audio file: {response.status_code}"}
            

            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            audio_file = open(temp_file_path, 'rb')
        else:
            return {"success": False, "error": "Invalid audio file URL format"}
        
        try:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="text"
            )
            
            return {
                "success": True,
                "text": transcription,
                "language": language,
                "audio_file_url": audio_file_url
            }
            
        except Exception as e:
            return {"success": False, "error": f"Transcription failed: {str(e)}"}
        finally:
            audio_file.close()
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except Exception as e:
        frappe.log_error(f"Speech to Text Error: {str(e)}")
        return {"success": False, "error": str(e)}