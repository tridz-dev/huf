import frappe
import requests
import hmac
import hashlib
import json
import time
from datetime import datetime, timedelta
from huf.ai.conversation_manager import ConversationManager
from frappe.utils.file_manager import save_file
from frappe.rate_limiter import rate_limit

SETTINGS_DOCTYPE = "Elevenlabs Settings"


def _get_settings():
    """
    Fetch ElevenLabs credentials from Single Settings DocType.
    """

    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        frappe.throw(f"{SETTINGS_DOCTYPE} DocType not found", frappe.ValidationError)

    settings = frappe.get_single(SETTINGS_DOCTYPE)
    provider = frappe.get_doc("AI Provider", settings.provider)
    api_key = provider.get_password("api_key")
    agent_id = settings.agent_id

    return agent_id, api_key


@frappe.whitelist()
def health():
    agent_id, api_key = _get_settings()

    return {
        "status": "ok",
        "settings": {
            "hasAgentId": bool(agent_id),
            "hasApiKey": bool(api_key),
        },
    }

@frappe.whitelist()
@rate_limit(limit=10, seconds=60)
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


@frappe.whitelist()
@rate_limit(limit=10, seconds=60)
def get_agent_id():
    agent_id, _ = _get_settings()
    return {"agentId": agent_id}


def _verify_webhook_signature(secret, sig_header, raw_body):
    """Return True only if sig_header carries a valid, unexpired HMAC for raw_body.

    Fails closed: returns False if the secret is unset, the header is missing or
    malformed, the timestamp is outside the 5-minute window, or the signature
    does not match. Never raises.
    """
    if not secret or not sig_header:
        return False
    try:
        parts = sig_header.split(",")
        t_part = parts[0].split("=")[1]
        v0_part = parts[1].split("=")[1]
    except (IndexError, AttributeError):
        return False
    try:
        if int(time.time()) - int(t_part) > 300:
            return False
    except (ValueError, TypeError):
        return False
    payload_to_sign = f"{t_part}.".encode("utf-8") + raw_body
    calculated = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_to_sign,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(v0_part, calculated)


@frappe.whitelist(allow_guest=True)
def handle_elevenlabs_webhook(type=None, data=None, event_timestamp=None):
    """
    Handles ElevenLabs Post Call Transcription.
    Validates against 'Elevenlabs Settings' and finds the linked Huf Agent.
    """
    request = frappe.request

    el_settings = frappe.get_single("Elevenlabs Settings")

    secret = el_settings.get_password("webhook_secret")
    provider = frappe.get_doc("AI Provider", el_settings.provider)
    api_key = provider.get_password("api_key")

    if not secret:
        frappe.log_error("Webhook Secret missing in Elevenlabs Settings", "Huf Webhook")
        return {"status": "error", "message": "Configuration error"}

    raw_body = request.get_data()
    sig_header = request.headers.get("elevenlabs-signature")
    if not _verify_webhook_signature(secret, sig_header, raw_body):
        frappe.log_error("ElevenLabs webhook signature verification failed", "ElevenLabs Security")
        return {"status": "forbidden"}

    if type != "post_call_transcription" or not data:
        return {"status": "ignored"}

    incoming_agent_id = data.get("agent_id")

    # NOTE: `stored_agent_id` (the Elevenlabs Settings singleton) is no longer
    # the authority here -- multiple Agents can share this AI Provider, each
    # with its own ElevenLabs agent_id in its own voice_config. The per-Agent
    # voice_config match below is authoritative; a singleton equality gate
    # here would reject every webhook except the one Agent that happens to
    # match the singleton.
    agent_name = None
    candidates = frappe.get_all(
        "Agent",
        filters={"voice_enabled": 1, "voice_engine": "elevenlabs_convai"},
        fields=["name", "voice_config"],
        ignore_permissions=True,
    )
    for candidate in candidates:
        try:
            voice_config = json.loads(candidate.voice_config or "{}")
        except (TypeError, ValueError):
            continue
        if voice_config.get("agent_id") == incoming_agent_id:
            agent_name = candidate.name
            break

    if not agent_name:
        frappe.log_error(
            f"No Huf Agent found with voice_config.agent_id {incoming_agent_id}", "Huf Webhook"
        )
        return {"status": "error", "message": "Internal Agent not found"}

    from huf.ai.agent_access import assert_agent_access

    agent_doc = frappe.get_doc("Agent", agent_name)
    try:
        assert_agent_access(agent_doc, user="Guest")
    except frappe.PermissionError:
        frappe.log_error(
            f"Agent '{agent_name}' does not allow guest access; rejecting ElevenLabs webhook",
            "Huf Webhook",
        )
        return {"status": "error", "message": "Agent not accessible"}
    model = frappe.db.get_value("Agent", agent_name, "model")

    conversation_id = data.get("conversation_id")
    transcript = data.get("transcript", [])
    analysis = data.get("analysis", {})
    metadata = data.get("metadata", {})

    client_data = data.get("conversation_initiation_client_data", {})
    lead_name = client_data.get("dynamic_variables", {}).get("lead_name", "User")
    huf_conversation_id = client_data.get("dynamic_variables", {}).get("huf_conversation_id")

    cm = ConversationManager(
        agent_name=agent_name, channel="elevenlabs_voice", external_id=conversation_id
    )

    title = f"Voice Call: {lead_name}"
    try:
        conversation = cm.get_or_create_conversation(title=title, conversation_id=huf_conversation_id)
    except frappe.PermissionError:
        # huf_conversation_id is a client-echoed value from ElevenLabs' own
        # conversation_initiation_client_data - it was ownership-checked once,
        # synchronously, against the real caller in huf.ai.voice.api.start_session
        # (see _check_conversation_access there), before ever being sent to
        # ElevenLabs. By the time it comes back here the webhook itself runs as
        # Guest and cannot re-verify who echoed it, so a stale/deleted/tampered
        # value must degrade to a fresh conversation rather than aborting the
        # whole webhook - losing the Agent Run audit record and call recording
        # over a conversation-continuity mismatch would be strictly worse.
        frappe.log_error(
            f"huf_conversation_id '{huf_conversation_id}' rejected for agent '{agent_name}'; "
            "falling back to a fresh conversation",
            "Huf Webhook",
        )
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
            "provider": provider.name,
            "model": model,
            "cost": metadata.get("cost", 0),
        }
    )
    # Guest webhook runs after signature validation; internal audit record created on behalf of the system.
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
                provider=provider.name,
                model=model,
                agent=agent_name,
                run_name=run_doc.name,
            )
            msg_doc.db_set("creation", msg_timestamp)

    return {"status": "success", "run_id": run_doc.name}
