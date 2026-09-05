"""Google Chat Gateway Adapter for two-way Google Workspace Chat communications.

Google Chat apps configured as an "HTTP endpoint" (Google's current,
non-deprecated integration model) authenticate every inbound event with an
``Authorization: Bearer <JWT>`` header signed by
``chat@system.gserviceaccount.com``. There is no body-level verification
token in this integration model. Outbound replies made via the Chat REST
API (``spaces.messages.create``) likewise require a Bearer OAuth2 access
token minted from a service account -- an Incoming Webhook URL (if
configured) is pre-authenticated by the token embedded in its query string
and needs no Authorization header, but only ever posts to the one space it
was created for.

This adapter therefore needs two independent credentials:

- ``audience``: the Google Cloud project number (or custom configured
  audience string) that this Chat app's inbound JWTs carry in their ``aud``
  claim. Required to verify inbound requests -- without it, the adapter
  fails closed (nothing can be trusted as "the right app").
- ``service_account_key``: the JSON key of a service account with the
  ``https://www.googleapis.com/auth/chat.bot`` scope, used to mint OAuth2
  access tokens for authenticated outbound REST calls. Required for
  outbound sends that are not routed through ``webhook_url``.

``webhook_url`` remains optional and is now only a *fallback* transport --
used when no per-event space is available -- rather than the transport that
silently wins over the actual conversation's space.
"""

from __future__ import annotations

import json
import time
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

# Google Chat's HTTP-endpoint integration signs inbound requests as this
# service account. See:
# https://developers.google.com/workspace/chat/authenticate-authorize-chat-app
_GOOGLE_CHAT_ISSUER = "chat@system.gserviceaccount.com"
_GOOGLE_CERTS_URL = (
	"https://www.googleapis.com/service_accounts/v1/metadata/x509/chat@system.gserviceaccount.com"
)
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_CHAT_BOT_SCOPE = "https://www.googleapis.com/auth/chat.bot"

# How long a fetched JWKS / minted access token is trusted before being
# refetched. Access tokens are also refreshed early (see
# _ACCESS_TOKEN_REFRESH_SKEW_SECONDS) so an in-flight request never races an
# expiry that already passed.
_CERTS_CACHE_TTL_SECONDS = 3600
_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60


def _requests_post(url: str, *, headers: Mapping[str, str], json_data: Any, timeout: int) -> Any:
	import requests

	return requests.post(url, headers=headers, json=json_data, timeout=timeout)


def _requests_post_form(url: str, *, data: Mapping[str, str], timeout: int) -> Any:
	import requests

	return requests.post(url, data=data, timeout=timeout)


def _fetch_google_certs(*, timeout: int = 10) -> Mapping[str, str]:
	"""Fetch Google's current {kid: PEM x509 cert} map for Chat's signer."""
	import requests

	response = requests.get(_GOOGLE_CERTS_URL, timeout=timeout)
	response.raise_for_status()
	return response.json()


def _public_key_from_pem_cert(pem_cert: str) -> Any:
	from cryptography.hazmat.backends import default_backend
	from cryptography.x509 import load_pem_x509_certificate

	certificate = load_pem_x509_certificate(pem_cert.encode("utf-8"), default_backend())
	return certificate.public_key()


class GoogleChatGatewayAdapter(GatewayAdapter):
	"""Handle Google Chat webhook verification, text & card messages, and thread replies."""

	provider_id = "google_chat"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField(
				"audience",
				"Audience (Google Cloud Project Number or configured audience string)",
				required=True,
				secret=False,
				description=(
					"Value the Chat app's inbound JWTs carry as their 'aud' claim. "
					"Configured in the Google Chat app's Google Cloud Console setup."
				),
			),
			GatewayCredentialField(
				"service_account_key",
				"Service Account JSON Key (for authenticated outbound sends)",
				required=True,
				description=(
					"Full JSON key of a service account granted the "
					"https://www.googleapis.com/auth/chat.bot scope. Used to mint "
					"OAuth2 access tokens for direct REST replies."
				),
			),
			GatewayCredentialField(
				"webhook_url",
				"Google Chat Incoming Webhook URL (fallback only)",
				required=False,
				description=(
					"Used only when a reply has no per-event space to route to. "
					"When the event's own space is known, replies go there instead "
					"of this fixed webhook."
				),
			),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=20,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		token_http_post: Callable[..., Any] = _requests_post_form,
		jwks_fetcher: Callable[..., Mapping[str, str]] = _fetch_google_certs,
	) -> None:
		self._webhook_url = credentials.get("webhook_url", "")
		self._audience = credentials.get("audience", "")
		self._service_account_key_raw = credentials.get("service_account_key", "")
		self._http_post = http_post
		self._token_http_post = token_http_post
		self._jwks_fetcher = jwks_fetcher

		self._certs_cache: Mapping[str, str] | None = None
		self._certs_cache_at: float = 0.0

		self._access_token_cache: str | None = None
		self._access_token_cache_at: float = 0.0
		self._access_token_cache_ttl: float = 0.0

	# -- Inbound: Bearer-JWT verification ---------------------------------

	def _get_certs(self) -> Mapping[str, str]:
		now = time.time()
		if self._certs_cache is None or (now - self._certs_cache_at) > _CERTS_CACHE_TTL_SECONDS:
			self._certs_cache = self._jwks_fetcher()
			self._certs_cache_at = now
		return self._certs_cache

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify the ``Authorization: Bearer <JWT>`` header Google Chat sends.

		Fails closed (returns False) if:
		- ``audience`` is not configured (nothing to check the JWT's ``aud`` against)
		- the Authorization header is missing or not a Bearer token
		- the JWT's signature does not verify against Google's published certs
		- the JWT's ``iss`` is not ``chat@system.gserviceaccount.com``
		- the JWT's ``aud`` does not match the configured ``audience``
		- the JWT is expired, not-yet-valid, or otherwise malformed

		A body-level ``token`` field (the retired verification mechanism this
		adapter used to check) is never consulted -- no current Google Chat
		app configuration can produce one.
		"""
		if not self._audience:
			return False

		auth_header = request.headers.get("Authorization") or request.headers.get("authorization") or ""
		if not auth_header.startswith("Bearer "):
			return False
		token = auth_header[len("Bearer "):].strip()
		if not token:
			return False

		try:
			import jwt as pyjwt

			certs = self._get_certs()
			unverified_header = pyjwt.get_unverified_header(token)
			kid = unverified_header.get("kid")
			pem_cert = certs.get(kid) if kid else None
			if not pem_cert:
				return False

			public_key = _public_key_from_pem_cert(pem_cert)
			pyjwt.decode(
				token,
				key=public_key,
				algorithms=["RS256"],
				audience=self._audience,
				issuer=_GOOGLE_CHAT_ISSUER,
			)
			return True
		except Exception:
			return False

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Google Chat Bearer JWT verification failed")

		try:
			payload = json.loads(request.body.decode("utf-8")) if request.body else {}
		except Exception as exc:
			raise ValueError("Invalid Google Chat JSON payload") from exc

		message = payload.get("message") or {}
		sender = payload.get("user") or message.get("sender") or {}
		space = payload.get("space") or message.get("space") or {}

		sender_id = str(sender.get("name") or sender.get("displayName") or "")
		space_name = str(space.get("name") or "")
		text = str(message.get("text") or payload.get("text") or "")
		event_id = str(message.get("name") or payload.get("eventTime") or hash(f"{sender_id}:{text}"))

		thread = message.get("thread") or {}
		thread_id = str(thread.get("name") or "") if thread else None

		return NormalizedGatewayEvent(
			provider_event_id=event_id,
			sender_id=sender_id,
			conversation_id=space_name,
			message_text=text.strip(),
			thread_id=thread_id,
			is_room=True,
			raw_payload=payload,
		)

	# -- Outbound: authenticated REST, or webhook fallback -----------------

	def _mint_access_token(self) -> tuple[str, float]:
		"""Self-sign a service-account JWT and exchange it for an OAuth2 access token."""
		import jwt as pyjwt

		if not self._service_account_key_raw:
			raise ValueError(
				"Google Chat adapter has no configured service_account_key; "
				"cannot authenticate outbound REST calls"
			)

		try:
			key_info = json.loads(self._service_account_key_raw)
		except Exception as exc:
			raise ValueError("Google Chat service_account_key is not valid JSON") from exc

		client_email = key_info.get("client_email")
		private_key = key_info.get("private_key")
		if not client_email or not private_key:
			raise ValueError("Google Chat service_account_key is missing client_email/private_key")

		now = int(time.time())
		assertion = pyjwt.encode(
			{
				"iss": client_email,
				"scope": _GOOGLE_CHAT_BOT_SCOPE,
				"aud": _GOOGLE_TOKEN_URL,
				"iat": now,
				"exp": now + 3600,
			},
			private_key,
			algorithm="RS256",
		)

		response = self._token_http_post(
			_GOOGLE_TOKEN_URL,
			data={
				"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
				"assertion": assertion,
			},
			timeout=10,
		)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		access_token = body.get("access_token") if isinstance(body, dict) else None
		if not access_token:
			raise ValueError(f"Google Chat OAuth2 token exchange failed: {body!r}")
		expires_in = float(body.get("expires_in", 3600)) if isinstance(body, dict) else 3600.0
		return str(access_token), expires_in

	def _get_access_token(self) -> str:
		now = time.time()
		is_fresh = (
			self._access_token_cache is not None
			and (now - self._access_token_cache_at) < (self._access_token_cache_ttl - _ACCESS_TOKEN_REFRESH_SKEW_SECONDS)
		)
		if not is_fresh:
			token, ttl = self._mint_access_token()
			self._access_token_cache = token
			self._access_token_cache_at = now
			self._access_token_cache_ttl = ttl
		assert self._access_token_cache is not None
		return self._access_token_cache

	def _post_authenticated(self, target_url: str, data: dict[str, Any]) -> Any:
		access_token = self._get_access_token()
		return self._http_post(
			target_url,
			headers={
				"Content-Type": "application/json",
				"Authorization": f"Bearer {access_token}",
			},
			json_data=data,
			timeout=10,
		)

	def _post_via_webhook(self, data: dict[str, Any]) -> Any:
		# The webhook URL embeds its own auth token as a query parameter;
		# no Authorization header is needed (or possible) here.
		return self._http_post(
			self._webhook_url,
			headers={"Content-Type": "application/json"},
			json_data=data,
			timeout=10,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Deliver a Google Chat reply, preferring the event's own space over webhook_url.

		Routing order:
		1. If ``reply.conversation_id`` names a real space (``spaces/...``), post
		   there via the authenticated REST API -- this is per-event routing and
		   always wins when available, so a fixed ``webhook_url`` can no longer
		   silently redirect every reply to one space.
		2. Otherwise, fall back to ``webhook_url`` if one is configured.
		3. Otherwise, raise -- there is nowhere to deliver this reply.
		"""
		data: dict[str, Any] = {"text": reply.text}
		if reply.thread_id:
			data["thread"] = {"name": reply.thread_id}

		if reply.conversation_id.startswith("spaces/"):
			response = self._post_authenticated(
				f"https://chat.googleapis.com/v1/{reply.conversation_id}/messages", data
			)
		elif self._webhook_url:
			response = self._post_via_webhook(data)
		else:
			raise ValueError(
				"Google Chat adapter has no per-event space (reply.conversation_id) "
				"and no configured webhook_url fallback"
			)

		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		# GW-05/G4: a missing "name" in the Google Chat response means the
		# message was never actually created -- fabricating a hash-derived
		# delivery id here made every such failure look like a successful
		# send.
		if not isinstance(body, dict) or not body.get("name"):
			raise ValueError(f"Google Chat message delivery failed: {body!r}")

		return OutboundDelivery(str(body["name"]), provider_response=body)

	def send_card(self, space_id: str, card_v2_payload: dict[str, Any], thread_id: str | None = None) -> OutboundDelivery:
		"""Send a Card V2 interactive message to a Google Chat space."""
		data: dict[str, Any] = {"cardsV2": [card_v2_payload]}
		if thread_id:
			data["thread"] = {"name": thread_id}

		if space_id.startswith("spaces/"):
			response = self._post_authenticated(f"https://chat.googleapis.com/v1/{space_id}/messages", data)
		elif self._webhook_url:
			response = self._post_via_webhook(data)
		else:
			raise ValueError(
				"Google Chat adapter has no valid space_id and no configured webhook_url fallback"
			)

		body = response.json() if hasattr(response, "json") else response
		# See send_reply's NOTE above -- same G4/GW-05 fabrication, same
		# deliberate non-duplication.
		msg_id = str(body.get("name") or f"gchat-card-{hash(str(card_v2_payload))}") if isinstance(body, dict) else f"gchat-card-{hash(str(card_v2_payload))}"
		return OutboundDelivery(msg_id, provider_response=body if isinstance(body, dict) else {"status": "ok"})
