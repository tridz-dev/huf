# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Slack Gateway Adapter.

Slack inbound webhook verification and normalization is handled separately by
`slack_events.py` due to the unique structure of Slack's Events API.

This adapter exists exclusively to handle outbound delivery (e.g. system
welcome messages, agent responses, and pairing codes) so that the core
Gateway system can treat Slack like any other provider for outbound messaging.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

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


def _httpx_post(url: str, *, headers: dict, json_data: Mapping[str, Any], timeout: int) -> Any:
    import httpx
    return httpx.post(url, headers=headers, json=json_data, timeout=timeout)


class SlackGatewayAdapter(GatewayAdapter):
    """Deliver outbound text replies to Slack."""

    provider_id = "slack"
    credential_schema = GatewayCredentialSchema(
        (
            GatewayCredentialField("token", "Slack Bot Token (xoxb-...)"),
        )
    )
    capabilities = GatewayCapabilities(
        frozenset({"webhook"}),
        supports_thread_reply=True,
    )

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        http_post: Callable[..., Any] = _httpx_post,
    ) -> None:
        missing = self.credential_schema.missing_required(credentials)
        if missing:
            raise ValueError("Slack adapter is missing required credentials: " + ", ".join(missing))
        self._token = credentials["token"]
        self._http_post = http_post

    def verify_inbound(self, request: GatewayInboundRequest) -> bool:
        raise NotImplementedError("Slack inbound is handled by slack_events.py")

    def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
        raise NotImplementedError("Slack inbound is handled by slack_events.py")

    def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
        """Send a Slack chat.postMessage reply."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": reply.conversation_id,
            "text": reply.text,
            "mrkdwn": True
        }
        
        if reply.thread_id or reply.reply_to_provider_message_id:
            payload["thread_ts"] = reply.thread_id or reply.reply_to_provider_message_id

        response = self._http_post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json_data=payload,
            timeout=10
        )
        
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
            
        data = response.json() if hasattr(response, "json") else response
        if not isinstance(data, Mapping) or not data.get("ok"):
            error_msg = data.get("error") if isinstance(data, Mapping) else "Unknown Slack API error"
            raise ValueError(f"Slack chat.postMessage failed: {error_msg}")

        return OutboundDelivery(str(data.get("ts")), provider_response=data)
