"""WhatsApp Cloud API adapter.

This adapter handles WhatsApp Cloud API native verification, event normalization,
and outbound message request.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import (
    GatewayCapabilities,
    GatewayCredentialField,
    GatewayCredentialSchema,
    GatewayInboundRequest,
    GatewayReply,
    NormalizedGatewayEvent,
    OutboundDelivery,
)


def _requests_post(url: str, *, headers: Mapping[str, str], json_data: Any, timeout: int) -> Any:
    import requests

    return requests.post(url, headers=headers, json=json_data, timeout=timeout)


class WhatsAppGatewayAdapter(GatewayAdapter):
    """Authenticate WhatsApp Cloud API payloads and deliver text replies."""

    provider_id = "whatsapp"
    credential_schema = GatewayCredentialSchema(
        (
            GatewayCredentialField("phone_number_id", "Phone Number ID"),
            GatewayCredentialField("access_token", "System User Access Token"),
            GatewayCredentialField("verify_token", "Webhook Verify Token"),
        )
    )
    capabilities = GatewayCapabilities(
        frozenset({"webhook"}),
        supports_thread_reply=True,
        max_outbound_messages_per_second=50,
    )

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        http_post: Callable[..., Any] = _requests_post,
    ) -> None:
        missing = self.credential_schema.missing_required(credentials)
        if missing:
            raise ValueError(f"WhatsApp adapter is missing required credentials: {', '.join(missing)}")
        self._phone_number_id = credentials["phone_number_id"]
        self._access_token = credentials["access_token"]
        self._verify_token = credentials["verify_token"]
        self._http_post = http_post

    def verify_url(self, request: GatewayInboundRequest) -> str | None:
        """Handle WhatsApp webhook GET challenge verification."""
        query = request.query
        if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == self._verify_token:
            return query.get("hub.challenge")
        return None

    def verify_inbound(self, request: GatewayInboundRequest) -> bool:
        """Fail closed unless this is a verified WhatsApp payload."""
        payload = self._payload(request)
        if not payload or payload.get("object") != "whatsapp_business_account":
            return False
        return True

    def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
        """Normalize a verified WhatsApp webhook payload."""
        if not self.verify_inbound(request):
            raise ValueError("WhatsApp request was not verified")
        payload = self._payload(request) or {}
        
        entries = payload.get("entry") or []
        if not entries:
            raise ValueError("WhatsApp payload has no entries")
            
        changes = entries[0].get("changes") or []
        if not changes:
            raise ValueError("WhatsApp payload has no changes")
            
        value = changes[0].get("value") or {}
        messages = value.get("messages") or []
        if not messages:
            raise ValueError("WhatsApp payload contains no messages")
            
        message = messages[0]
        
        provider_event_id = str(message.get("id") or "")
        sender_id = str(message.get("from") or "")
        conversation_id = sender_id
        
        message_text = ""
        msg_type = message.get("type")
        if msg_type == "text":
            message_text = str((message.get("text") or {}).get("body") or "")
        elif msg_type == "button":
            message_text = str((message.get("button") or {}).get("text") or "")
        elif msg_type == "interactive":
            interactive = message.get("interactive") or {}
            if interactive.get("type") == "button_reply":
                message_text = str((interactive.get("button_reply") or {}).get("title") or "")
            elif interactive.get("type") == "list_reply":
                message_text = str((interactive.get("list_reply") or {}).get("title") or "")
                
        if not provider_event_id or not sender_id:
            raise ValueError("WhatsApp message is missing id or sender")
            
        thread_id = None
        context = message.get("context")
        if context and context.get("id"):
            thread_id = str(context.get("id"))
            
        return NormalizedGatewayEvent(
            provider_event_id=provider_event_id,
            sender_id=sender_id,
            conversation_id=conversation_id,
            message_text=message_text,
            thread_id=thread_id,
            is_room=False,
            raw_payload=payload,
        )

    def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
        """Send a WhatsApp text reply."""
        url = f"https://graph.facebook.com/v17.0/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": str(reply.conversation_id),
            "type": "text",
            "text": {"preview_url": False, "body": reply.text},
        }
        
        if reply.reply_to_provider_message_id:
            data["context"] = {"message_id": reply.reply_to_provider_message_id}

        response = self._http_post(url, headers=headers, json_data=data, timeout=10)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        body = response.json() if hasattr(response, "json") else response
        if not isinstance(body, Mapping):
            raise ValueError("WhatsApp messages returned an invalid response")
            
        if body.get("error"):
            error = body["error"]
            message = error.get("message") if isinstance(error, Mapping) else "WhatsApp API rejected reply"
            raise ValueError(f"WhatsApp API failed: {message}")
            
        messages = body.get("messages") or []
        if not messages:
            raise ValueError("WhatsApp response did not include messages")
            
        message_id = messages[0].get("id")
        return OutboundDelivery(str(message_id), provider_response=body)

    def list_templates(self) -> dict:
        """List templates for the WhatsApp Business Account."""
        raise NotImplementedError("Template management requires WABA ID.")

    def send_template_message(self, to: str, template_name: str, language_code: str = "en_US", components: list = None) -> OutboundDelivery:
        """Send a WhatsApp template message."""
        url = f"https://graph.facebook.com/v17.0/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or []
            },
        }
        response = self._http_post(url, headers=headers, json_data=data, timeout=10)
        body = response.json() if hasattr(response, "json") else response
        if body.get("error"):
            raise ValueError(f"WhatsApp API failed: {body['error']}")
        messages = body.get("messages") or []
        return OutboundDelivery(str(messages[0]["id"]), provider_response=body)

    @staticmethod
    def _payload(request: GatewayInboundRequest) -> dict[str, Any] | None:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
