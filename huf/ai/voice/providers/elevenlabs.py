"""
ElevenLabs Voice Agent Provider

Implements VoiceAgentBase for ElevenLabs ConvAI API.
Maintains backward compatibility with existing ElevenLabs implementation.
"""

import frappe
import requests
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, AsyncGenerator
from huf.ai.voice.base import VoiceAgentBase
from huf.ai.conversation_manager import ConversationManager
from frappe.utils.file_manager import save_file

SETTINGS_DOCTYPE = "Elevenlabs Settings"


class VoiceAgent(VoiceAgentBase):
    """ElevenLabs voice agent implementation."""

    def __init__(self, provider_name: str, agent_name: str):
        super().__init__(provider_name, agent_name)
        self.settings_doctype = SETTINGS_DOCTYPE

    def _get_settings(self) -> tuple[str, str]:
        """
        Fetch ElevenLabs credentials from Settings DocType.
        
        Returns:
            Tuple of (agent_id, api_key)
        """
        if not frappe.db.exists("DocType", self.settings_doctype):
            frappe.throw(
                f"{self.settings_doctype} DocType not found",
                frappe.ValidationError
            )

        settings = frappe.get_single(self.settings_doctype)
        
        # Use provider from settings or fall back to instance provider
        settings_provider = settings.provider if hasattr(settings, 'provider') else self.provider_name
        provider = frappe.get_doc("AI Provider", settings_provider)
        api_key = provider.get_password("api_key")
        agent_id = settings.agent_id

        return agent_id, api_key

    def get_signed_url(self, **kwargs) -> Dict[str, Any]:
        """
        Get signed URL for ElevenLabs conversation.
        
        Returns:
            Dictionary with signed_url
        """
        agent_id, api_key = self._get_settings()

        if not agent_id or not api_key:
            frappe.throw(
                "Missing Agent ID or API Key in Elevenlabs Settings",
                frappe.ValidationError
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
                f"ElevenLabs API error ({response.status_code})",
                frappe.ValidationError
            )

        data = response.json()
        return {"signedUrl": data.get("signed_url")}

    def validate_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """
        Validate ElevenLabs webhook signature.
        
        Args:
            payload: Raw request body bytes
            signature: Signature from elevenlabs-signature header
            secret: Webhook secret from settings
            
        Returns:
            True if signature is valid
        """
        try:
            parts = signature.split(",")
            t_part = parts[0].split("=")[1]
            v0_part = parts[1].split("=")[1]

            # Check timestamp (5 minute window)
            if int(time.time()) - int(t_part) > 300:
                return False

            payload_to_sign = f"{t_part}.".encode("utf-8") + payload

            calculated = hmac.new(
                key=secret.encode("utf-8"),
                msg=payload_to_sign,
                digestmod=hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(v0_part, calculated)
        except Exception:
            return False

    def handle_webhook(
        self, request_data: Dict[str, Any], headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Handle ElevenLabs webhook callback.
        
        Args:
            request_data: Parsed webhook payload (may be direct data or wrapped with type)
            headers: Request headers
            
        Returns:
            Dictionary with status and run_id
        """
        request = frappe.request

        el_settings = frappe.get_single(self.settings_doctype)
        secret = el_settings.get_password("webhook_secret")
        provider = frappe.get_doc("AI Provider", el_settings.provider)
        api_key = provider.get_password("api_key")
        stored_agent_id = el_settings.agent_id

        if not secret:
            frappe.log_error(
                "Webhook Secret missing in Elevenlabs Settings",
                "Huf Webhook"
            )
            return {"status": "error", "message": "Configuration error"}

        sig_header = headers.get("elevenlabs-signature")
        if sig_header:
            raw_body = request.get_data()
            if not self.validate_webhook_signature(raw_body, sig_header, secret):
                frappe.log_error(
                    "Invalid webhook signature",
                    "ElevenLabs Security"
                )
                return {"status": "forbidden"}

        # Handle both formats: direct data dict or wrapped with type
        webhook_type = request_data.get("type")
        data = request_data.get("data", request_data)

        if webhook_type != "post_call_transcription" or not data:
            return {"status": "ignored"}

        incoming_agent_id = data.get("agent_id")

        if incoming_agent_id != stored_agent_id:
            frappe.log_error(
                f"Agent ID mismatch. Expected {stored_agent_id}, got {incoming_agent_id}",
                "Huf Webhook",
            )
            return {"status": "error", "message": "Agent ID mismatch"}

        agent_name = frappe.db.get_value(
            "Agent", {"provider": provider.name}, "name"
        )
        model = frappe.db.get_value("Agent", agent_name, "model")

        if not agent_name:
            frappe.log_error(
                "No Huf Agent found with provider 'ElevenLabs'",
                "Huf Webhook"
            )
            return {"status": "error", "message": "Internal Agent not found"}

        conversation_id = data.get("conversation_id")
        transcript = data.get("transcript", [])
        analysis = data.get("analysis", {})
        metadata = data.get("metadata", {})

        client_data = data.get("conversation_initiation_client_data", {})
        lead_name = client_data.get("dynamic_variables", {}).get(
            "lead_name", "User"
        )

        cm = ConversationManager(
            agent_name=agent_name,
            channel="elevenlabs_voice",
            external_id=conversation_id
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
                    "Success"
                    if analysis.get("call_successful") == "success"
                    else "Failed"
                ),
                "start_time": start_time,
                "prompt": "Voice Call Initiated",
                "response": analysis.get(
                    "transcript_summary", "Voice call completed."
                ),
                "provider": provider.name,
                "model": model,
                "total_cost": metadata.get("cost", 0),
            }
        )
        run_doc.insert(ignore_permissions=True)

        # Download and save call recording
        if api_key and conversation_id:
            try:
                audio_url = (
                    f"https://api.elevenlabs.io/v1/convai/conversations/"
                    f"{conversation_id}/audio"
                )
                audio_res = requests.get(
                    audio_url, headers={"xi-api-key": api_key}
                )

                if audio_res.status_code == 200:
                    saved_file = save_file(
                        fname=f"call_{conversation_id}.mp3",
                        content=audio_res.content,
                        dt="Agent Run",
                        dn=run_doc.name
                    )
                    run_doc.db_set("call_recording", saved_file.file_url)
                else:
                    frappe.log_error(
                        f"Failed to fetch audio: {audio_res.text}",
                        "ElevenLabs Audio"
                    )
            except Exception as e:
                frappe.log_error(
                    f"Audio Download Error: {str(e)}",
                    "ElevenLabs Audio"
                )

        # Process transcript
        transcript.sort(key=lambda x: x.get("time_in_call_secs", 0))
        for turn in transcript:
            role = "agent" if turn.get("role") == "agent" else "user"
            msg_content = turn.get("message")

            msg_time_offset = turn.get("time_in_call_secs", 0)
            msg_timestamp = start_time + timedelta(seconds=msg_time_offset)

            if msg_content:
                msg_doc = cm.add_message(
                    conversation=conversation,
                    role=role,
                    content=msg_content,
                    provider=provider.name,
                    model=model,
                    agent=agent_name,
                    run_name=run_doc.name,
                )
                msg_doc.db_set("creation", msg_timestamp)

        frappe.db.commit()
        return {"status": "success", "run_id": run_doc.name}

    async def stream_realtime(
        self,
        audio_input: AsyncGenerator[bytes, None],
        session_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream real-time audio for ElevenLabs (if supported).
        
        Note: ElevenLabs ConvAI uses signed URLs and webhooks,
        not direct WebSocket streaming. This method is a placeholder
        for future real-time streaming support.
        """
        # ElevenLabs ConvAI doesn't support direct WebSocket streaming
        # It uses signed URLs and webhooks instead
        raise NotImplementedError(
            "ElevenLabs ConvAI uses signed URLs and webhooks, "
            "not direct WebSocket streaming. Use get_signed_url() instead."
        )
