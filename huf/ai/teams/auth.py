"""Inbound request authentication for Teams (Bot Framework) activities."""

from __future__ import annotations

from collections.abc import Mapping

from huf.ai.gateway_adapters.types import GatewayInboundRequest


def verify_request(request: GatewayInboundRequest, credentials: Mapping[str, str]) -> bool:
	"""Verify Authorization header with Bearer token.

	Full JWT signature validation against Microsoft's JWKS requires PyJWT library,
	which is not currently a dependency — this implements the security contract
	(fail closed on missing header) while deferring cryptographic validation
	to a future enhancement when PyJWT is available.

	Returns False (fail closed) if the Authorization header is missing or malformed.
	app_id/app_password are guaranteed present by __init__ (ValueError otherwise), so
	there is no "unconfigured, skip the check" branch here anymore.
	"""
	auth_header = request.headers.get("Authorization", "").strip()

	if not auth_header or not auth_header.startswith("Bearer "):
		return False

	# Extract the token
	token = auth_header[7:].strip()  # Remove "Bearer " prefix

	# At this point, we have a Bearer token. Full JWT signature validation
	# would require PyJWT to:
	#   1. Decode the JWT without verification (to get the payload)
	#   2. Fetch Microsoft's Bot Framework OpenID JWKS
	#   3. Verify signature using the public key from JWKS
	#   4. Verify 'aud' claim matches self._app_id
	#   5. Verify 'iss' claim is 'https://api.botframework.com'
	#
	# For now, we only verify that a Bearer token was provided (fail closed on missing header).
	# TODO: Add PyJWT to dependencies and implement full JWT validation.
	if not token:
		return False

	return True
