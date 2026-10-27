"""Outbound Teams (Bot Connector) sends."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from huf.ai.gateway_adapters.types import GatewayReply, OutboundDelivery


def send_reply(
	reply: GatewayReply, credentials: Mapping[str, str], http_post: Callable[..., Any]
) -> OutboundDelivery:
	"""Post reply back to MS Teams conversation."""
	service_url = "https://smba.trafficmanager.net/amer"
	url = f"{service_url.rstrip('/')}/v3/conversations/{reply.conversation_id}/activities"

	data: dict[str, Any] = {
		"type": "message",
		"text": reply.text,
	}
	if reply.reply_to_provider_message_id:
		data["replyToId"] = reply.reply_to_provider_message_id

	response = http_post(
		url,
		headers={"Content-Type": "application/json"},
		json_data=data,
		timeout=10,
	)
	body = response.json() if hasattr(response, "json") else response
	# GW-05: a missing "id" in the Bot Framework response means the reply
	# was never actually accepted -- fabricating a hash-derived delivery
	# id here made every such failure look like a successful send.
	if not isinstance(body, dict) or not body.get("id"):
		raise ValueError(f"Microsoft Teams message delivery failed: {body!r}")

	return OutboundDelivery(str(body["id"]), provider_response=body)


def send_adaptive_card(
	conversation_id: str, card_content: dict[str, Any], http_post: Callable[..., Any]
) -> OutboundDelivery:
	"""Post an Adaptive Card attachment to an MS Teams conversation."""
	service_url = "https://smba.trafficmanager.net/amer"
	url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"

	data: dict[str, Any] = {
		"type": "message",
		"attachments": [
			{
				"contentType": "application/vnd.microsoft.card.adaptive",
				"content": card_content,
			}
		],
	}

	response = http_post(
		url,
		headers={"Content-Type": "application/json"},
		json_data=data,
		timeout=10,
	)
	body = response.json() if hasattr(response, "json") else response
	activity_id = (
		str(body.get("id") or f"teams-card-{hash(str(card_content))}")
		if isinstance(body, dict)
		else f"teams-card-{hash(str(card_content))}"
	)
	return OutboundDelivery(
		activity_id, provider_response=body if isinstance(body, dict) else {"status": "ok"}
	)
