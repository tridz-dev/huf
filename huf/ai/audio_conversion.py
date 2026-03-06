import frappe
from frappe.utils.file_manager import save_file
import os

def convert_webm_to_mp3(file_id: str, new_filename: str, attached_to_doctype: str, attached_to_name: str):
    """
    Reads a webm file from Frappe storage and encodes it to MP3 using pydub/ffmpeg.
    Returns the new Frappe File document ID and file_url.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        frappe.log_error("pydub not installed. MP3 conversion skipped.", "Audio Conversion Error")
        return None

    try:
        file_doc = frappe.get_doc("File", file_id)
        file_path = file_doc.get_full_path()
        
        if not os.path.exists(file_path):
            frappe.log_error(f"File path does not exist: {file_path}", "Audio Conversion Error")
            return None

        # Load webm audio
        audio = AudioSegment.from_file(file_path, format="webm")
        
        # We need a temporary file path to export to, then read chunks back
        temp_mp3_path = file_path + ".temp.mp3"
        
        # Export as MP3
        audio.export(temp_mp3_path, format="mp3", bitrate="128k")
        
        # Read the MP3 bytes
        with open(temp_mp3_path, "rb") as f:
            mp3_data = f.read()
            
        # Clean up temp file
        if os.path.exists(temp_mp3_path):
            os.remove(temp_mp3_path)

        # Save MP3 back to Frappe
        saved_mp3 = save_file(
            fname=new_filename,
            content=mp3_data,
            dt=attached_to_doctype,
            dn=attached_to_name,
            is_private=file_doc.is_private
        )
        
        return {
            "file_id": saved_mp3.name if hasattr(saved_mp3, "name") else saved_mp3.get("name"),
            "file_url": saved_mp3.file_url if hasattr(saved_mp3, "file_url") else saved_mp3.get("file_url")
        }

    except Exception as e:
        frappe.log_error(f"MP3 Conversion Failed: {str(e)}", "Audio Conversion Error")
        return None
