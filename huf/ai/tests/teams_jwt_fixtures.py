"""Test-time JWT/OpenID fixtures for the Teams gateway (no network, no real keys)."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
JWKS_URL = "https://login.botframework.com/v1/.well-known/keys"
DEFAULT_KID = "test-kid-1"
DEFAULT_APP_ID = "00000000-0000-0000-0000-0000000000b1"
DEFAULT_SERVICE_URL = "https://smba.trafficmanager.net/amer/"
DEFAULT_ISSUER = "https://api.botframework.com"
FIXED_NOW = 1_767_268_800.0  # 2026-01-01T12:00:00Z

_KEYS: dict[str, Any] = {}


def get_private_key(kid: str = DEFAULT_KID):
	"""RSA-2048 key, generated once per process per kid."""
	if kid not in _KEYS:
		_KEYS[kid] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	return _KEYS[kid]


def fixed_clock(value: float = FIXED_NOW) -> Callable[[], float]:
	return lambda: value


def make_jwk(kid: str = DEFAULT_KID, endorsements: list[str] | None = None) -> dict:
	import json

	jwk = json.loads(RSAAlgorithm.to_jwk(get_private_key(kid).public_key()))
	jwk.update({"kid": kid, "use": "sig", "alg": "RS256", "endorsements": endorsements or ["msteams"]})
	return jwk


def fake_openid_metadata() -> dict:
	return {
		"issuer": DEFAULT_ISSUER,
		"authorization_endpoint": "https://login.botframework.com/v1/.well-known/oauth/authorize",
		"jwks_uri": JWKS_URL,
		"id_token_signing_alg_values_supported": ["RS256"],
		"token_endpoint_auth_methods_supported": ["private_key_jwt"],
	}


def fake_jwks(kids: tuple[str, ...] = (DEFAULT_KID,)) -> dict:
	return {"keys": [make_jwk(k) for k in kids]}


def make_token(
	*,
	kid: str = DEFAULT_KID,
	algorithm: str = "RS256",
	key: Any = None,
	now: float = FIXED_NOW,
	**claims: Any,
) -> str:
	"""Sign a Bot Framework style token. Pass ``claim=None`` to drop a default claim."""
	payload: dict[str, Any] = {
		"iss": DEFAULT_ISSUER,
		"aud": DEFAULT_APP_ID,
		"serviceurl": DEFAULT_SERVICE_URL,
		"nbf": int(now) - 60,
		"iat": int(now) - 60,
		"exp": int(now) + 3600,
	}
	if "serviceUrl" in claims:  # accept either spelling; Bot Framework uses "serviceurl"
		claims["serviceurl"] = claims.pop("serviceUrl")
	payload.update(claims)
	payload = {k: v for k, v in payload.items() if v is not None}
	return jwt.encode(payload, key or get_private_key(kid), algorithm=algorithm, headers={"kid": kid})


def fake_fetch_json(
	kids: tuple[str, ...] = (DEFAULT_KID,), calls: list[str] | None = None
) -> Callable[[str], Mapping[str, Any]]:
	"""Injectable ``fetch_json(url)`` serving the fake OpenID metadata and JWKS."""

	def fetch(url: str) -> Mapping[str, Any]:
		if calls is not None:
			calls.append(url)
		if url == OPENID_URL:
			return fake_openid_metadata()
		if url == JWKS_URL:
			return fake_jwks(kids)
		raise AssertionError(f"unexpected fetch: {url}")

	return fetch


def real_clock() -> float:
	return time.time()
