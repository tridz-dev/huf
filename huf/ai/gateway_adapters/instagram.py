# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Meta Instagram Messaging API adapter for Huf Gateway.

Integrates Instagram Professional Accounts messaging with Huf's fail-closed
Gateway ingress and routing, leveraging frappe_messenger for document persistence.
"""

from __future__ import annotations

from typing import Any

from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
)
from huf.ai.gateway_adapters.messenger import MessengerGatewayAdapter


class InstagramGatewayAdapter(MessengerGatewayAdapter):
	"""Authenticate Instagram Direct webhooks and deliver text replies."""

	provider_id = "instagram"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("instagram_account_id", "Instagram Professional Account ID / Page ID", secret=False),
			GatewayCredentialField("access_token", "Facebook / Instagram Page Access Token"),
			GatewayCredentialField("webhook_verify_token", "Webhook Verify Token"),
			GatewayCredentialField("app_secret", "Meta App Secret (for HMAC signature verification)", required=True),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_text_reply=True,
		supports_thread_reply=True,
		supports_media_reply=True,
		max_outbound_messages_per_second=20,
	)

	def __init__(
		self,
		credentials: Any,
		**kwargs: Any,
	) -> None:
		# Map instagram_account_id to page_id for underlying Messenger adapter logic
		creds = dict(credentials)
		if "instagram_account_id" in creds and "page_id" not in creds:
			creds["page_id"] = creds["instagram_account_id"]
		super().__init__(creds, **kwargs)
