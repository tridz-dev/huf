import json
import frappe

def execute_provider_capability(
    provider: str,
    capability_method: str,
    *args,
    **kwargs
) -> dict:
    """
    Generic dispatcher that loads the Provider Settings DocType
    and calls a specific method (e.g., 'transcribe_audio', 'text_to_speech').
    """
    if not provider:
        return {"success": False, "error": "Provider is required"}

    try:
        settings_doctype = f"{provider} Settings"
        
        if not frappe.db.exists("DocType", settings_doctype):
            return {
                "success": False,
                "error": f"Settings DocType '{settings_doctype}' not found. Please create it."
            }

        settings_doc = frappe.get_doc(settings_doctype)

        if not hasattr(settings_doc, capability_method):
            return {
                "success": False,
                "error": f"Provider '{provider}' does not support '{capability_method}' (Method missing in {settings_doctype})."
            }

        method = getattr(settings_doc, capability_method)
        result = method(*args, **kwargs)

        if not isinstance(result, dict):
            return {
                "success": False,
                "error": f"{settings_doctype}.{capability_method}() must return a dict."
            }

        if "success" not in result:
            return {
                "success": False,
                "error": f"Response from {settings_doctype} missing 'success' key."
            }

        return result

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            f"Provider Capability Error: {capability_method}"
        )
        return {"success": False, "error": str(e)}



def handle_speech_to_text(
    file_id: str = None,
    file_url: str = None,
    language: str = None,
    translate: bool = False,
    provider: str = None,
    api_key: str = None,
    conversation: str = None,
    reference_doctype: str = None,
    document_id: str = None,
    message_id: str = None,
    **kwargs
):
    """
    Speech-to-Text dispatcher.
    Calls .transcribe_audio() on the provider settings.
    """

    try:
        if not file_id:
            return {"success": False, "error": "File ID is required."}

        if not provider and conversation:
            try:
                conv_doc = frappe.get_doc("Agent Conversation", conversation)
                if conv_doc.agent:
                    provider = frappe.db.get_value("Agent", conv_doc.agent, "provider")
            except Exception:
                pass

        if not provider:
            return {"success": False, "error": "Provider could not be determined."}

        file_doc = frappe.get_doc("File", file_id)

        runtime_kwargs = {
            "language": language,
            "translate": translate,
            "api_key": api_key,
        }
        
        runtime_kwargs = {k: v for k, v in runtime_kwargs.items() if v is not None}
        runtime_kwargs.update(kwargs)

        response = execute_provider_capability(
            provider=provider,
            capability_method="transcribe_audio",
            file_doc=file_doc,
            kwargs=runtime_kwargs
        )

        if not response.get("success"):
            return response

        text = response.get("result") or "(empty transcript)"

        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)

        if message_id:
            frappe.db.set_value(
                "Agent Message",
                message_id,
                "content",
                text,
                update_modified=True
            )
        elif conversation:
            new_msg = frappe.get_doc({
                "doctype": "Agent Message",
                "conversation": conversation,
                "role": "user",
                "content": text,
                "user": frappe.session.user
            })
            new_msg.insert(ignore_permissions=True)
            message_id = new_msg.name

        return {
            "success": True,
            "text": text,
            "file_id": file_id,
            "message_id": message_id
        }

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Speech To Text Error"
        )
        return {"success": False, "error": str(e)}