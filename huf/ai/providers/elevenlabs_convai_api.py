import frappe
import requests
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from huf.ai.conversation_manager import ConversationManager
from frappe.utils.file_manager import save_file

SETTINGS_DOCTYPE = "Elevenlabs Settings"


def _get_settings():
    """
    Fetch ElevenLabs credentials from Single Settings DocType.
    """

    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        frappe.throw(f"{SETTINGS_DOCTYPE} DocType not found", frappe.ValidationError)

    settings = frappe.get_single(SETTINGS_DOCTYPE)

    agent_id = settings.agent_id
    api_key = settings.get_password("api_key")

    return agent_id, api_key


@frappe.whitelist(allow_guest=True)
def health():
    agent_id, api_key = _get_settings()

    return {
        "status": "ok",
        "settings": {
            "hasAgentId": bool(agent_id),
            "hasApiKey": bool(api_key),
            "agentIdLength": len(agent_id) if agent_id else 0,
            "apiKeyLength": len(api_key) if api_key else 0,
        },
    }


@frappe.whitelist(allow_guest=True)
def get_signed_url():
    agent_id, api_key = _get_settings()

    if not agent_id or not api_key:
        frappe.throw(
            "Missing Agent ID or API Key in Elevenlabs Settings", frappe.ValidationError
        )

    url = (
        "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
        f"?agent_id={agent_id}"
    )

    headers = {"xi-api-key": api_key}

    response = requests.get(url, headers=headers, timeout=30)

    if not response.ok:
        try:
            error_json = response.json()
            if error_json.get("detail", {}).get("status") == "missing_permissions":
                frappe.throw(
                    "ElevenLabs API key is missing convai_write permission",
                    frappe.PermissionError,
                )
        except Exception:
            pass

        frappe.throw(
            f"ElevenLabs API error ({response.status_code})", frappe.ValidationError
        )

    data = response.json()
    return {"signedUrl": data.get("signed_url")}


@frappe.whitelist(allow_guest=True)
def get_agent_id():
    agent_id, _ = _get_settings()
    return {"agentId": agent_id}


@frappe.whitelist(allow_guest=True)
def handle_elevenlabs_webhook(type=None, data=None, event_timestamp=None):
    """
    Handles ElevenLabs Post Call Transcription.
    Validates against 'Elevenlabs Settings' and finds the linked Huf Agent.
    """
    request = frappe.request

    el_settings = frappe.get_single("Elevenlabs Settings")

    secret = el_settings.get_password("webhook_secret")
    api_key = el_settings.get_password("api_key")
    stored_agent_id = el_settings.agent_id

    if not secret:
        frappe.log_error("Webhook Secret missing in Elevenlabs Settings", "Huf Webhook")
        return {"status": "error", "message": "Configuration error"}

    sig_header = request.headers.get("elevenlabs-signature")
    if sig_header:
        try:
            parts = sig_header.split(",")
            t_part = parts[0].split("=")[1]
            v0_part = parts[1].split("=")[1]

            if int(time.time()) - int(t_part) > 300:
                frappe.throw("Timestamp expired", exc=frappe.PermissionError)

            raw_body = request.get_data()
            payload_to_sign = f"{t_part}.".encode("utf-8") + raw_body

            calculated = hmac.new(
                key=secret.encode("utf-8"),
                msg=payload_to_sign,
                digestmod=hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(v0_part, calculated):
                frappe.throw("Invalid Signature", exc=frappe.PermissionError)
        except Exception as e:
            frappe.log_error(f"Signature Failed: {str(e)}", "ElevenLabs Security")
            return {"status": "forbidden"}

    if type != "post_call_transcription" or not data:
        return {"status": "ignored"}

    incoming_agent_id = data.get("agent_id")

    if incoming_agent_id != stored_agent_id:
        frappe.log_error(
            f"Agent ID mismatch. Expected {stored_agent_id}, got {incoming_agent_id}",
            "Huf Webhook",
        )
        return {"status": "error", "message": "Agent ID mismatch"}

    agent_name = frappe.db.get_value("Agent", {"provider": "ElevenLabs"}, "name")
    model = frappe.db.get_value("Agent", agent_name, "model")

    if not agent_name:
        frappe.log_error("No Huf Agent found with provider 'ElevenLabs'", "Huf Webhook")
        return {"status": "error", "message": "Internal Agent not found"}

    conversation_id = data.get("conversation_id")
    transcript = data.get("transcript", [])
    analysis = data.get("analysis", {})
    metadata = data.get("metadata", {})

    client_data = data.get("conversation_initiation_client_data", {})
    lead_name = client_data.get("dynamic_variables", {}).get("lead_name", "User")

    cm = ConversationManager(
        agent_name=agent_name, channel="elevenlabs_voice", external_id=conversation_id
    )

    title = f"Voice Call: {lead_name}"
    conversation = cm.get_or_create_conversation(title=title)

    start_time_unix = metadata.get("start_time_unix_secs")
    start_time = (
        datetime.fromtimestamp(start_time_unix)
        if start_time_unix
        else frappe.utils.now_datetime()
    )

    run_doc = frappe.get_doc(
        {
            "doctype": "Agent Run",
            "agent": agent_name,
            "conversation": conversation.name,
            "status": (
                "Success" if analysis.get("call_successful") == "success" else "Failed"
            ),
            "start_time": start_time,
            "prompt": "Voice Call Initiated",
            "response": analysis.get("transcript_summary", "Voice call completed."),
            "provider": "ElevenLabs",
            "model": model,
            "total_cost": metadata.get("cost", 0),
        }
    )
    run_doc.insert(ignore_permissions=True)
    if api_key and conversation_id:
        try:
            audio_url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}/audio"
            audio_res = requests.get(audio_url, headers={"xi-api-key": api_key})

            if audio_res.status_code == 200:
                saved_file = save_file(
                    fname=f"call_{conversation_id}.mp3",
                    content=audio_res.content,
                    dt="Agent Run",
                    dn=run_doc.name
                )
                

                run_doc.db_set("call_recording", saved_file.file_url)
            else:
                frappe.log_error(f"Failed to fetch audio: {audio_res.text}", "ElevenLabs Audio")
        except Exception as e:
            frappe.log_error(f"Audio Download Error: {str(e)}", "ElevenLabs Audio")

    
    transcript.sort(key=lambda x: x.get('time_in_call_secs', 0))
    for turn in transcript:
        role = "agent" if turn.get("role") == "agent" else "user"
        msg_content = turn.get("message")
        
        msg_time_offset = turn.get("time_in_call_secs", 0)
        msg_timestamp = start_time + timedelta(seconds=msg_time_offset)

        if msg_content:
            msg_doc=cm.add_message(
                conversation=conversation,
                role=role,
                content=msg_content,
                provider="ElevenLabs",
                model=model,
                agent=agent_name,
                run_name=run_doc.name,
            )
            msg_doc.db_set("creation", msg_timestamp)

    frappe.db.commit()
    return {"status": "success", "run_id": run_doc.name}
