"""Inbound Teams activity -> NormalizedGatewayEvent."""

from __future__ import annotations

import json
from collections.abc import Mapping

from huf.ai.gateway_adapters.types import GatewayAttachment, GatewayInboundRequest, NormalizedGatewayEvent
from huf.ai.teams import auth


def normalize(request: GatewayInboundRequest, credentials: Mapping[str, str]) -> NormalizedGatewayEvent:
	if not auth.verify_request(request, credentials):
		raise ValueError("Microsoft Teams authorization failed")

	try:
		activity = json.loads(request.body.decode("utf-8")) if request.body else {}
	except Exception as exc:
		raise ValueError("Invalid Teams Activity JSON payload") from exc

	activity_id = str(activity.get("id") or "")
	from_account = activity.get("from") or {}
	sender_id = str(from_account.get("id") or from_account.get("name") or "")

	conversation = activity.get("conversation") or {}
	conversation_id = str(conversation.get("id") or "")

	text = str(activity.get("text") or "").strip()

	attachments = []
	for attachment in activity.get("attachments") or []:
		content_url = attachment.get("contentUrl")
		if not content_url:
			continue
		attachments.append(
			GatewayAttachment(
				mime_type=str(attachment.get("contentType") or ""),
				filename=str(attachment.get("name") or ""),
				url=content_url,
				kind="file",
			)
		)

	return NormalizedGatewayEvent(
		provider_event_id=activity_id,
		sender_id=sender_id,
		conversation_id=conversation_id,
		message_text=text,
		thread_id=activity.get("replyToId"),
		is_room=bool(conversation.get("isGroup")),
		raw_payload=activity,
		attachments=tuple(attachments),
	)
