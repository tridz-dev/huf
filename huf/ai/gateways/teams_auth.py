"""Inbound Bot Framework JWT verification for the Microsoft Teams gateway (T1).

``verify_bearer`` never raises and never logs the token; failures come back as
``TeamsAuthResult(False, <REASON_*>, {})``. Pure verification: all network access goes
through the injected ``fetch_json`` callable.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlsplit

import jwt
from jwt.algorithms import RSAAlgorithm

from huf.ai.gateways.teams_contract import (
	BOT_ISSUER,
	CLOCK_SKEW_SECONDS,
	ENTRA_ISSUER_TEMPLATES,
	JWKS_CACHE_SECONDS,
	OPENID_METADATA_URL,
	REASON_BAD_ALGORITHM,
	REASON_BAD_AUDIENCE,
	REASON_BAD_ENDORSEMENT,
	REASON_BAD_ISSUER,
	REASON_BAD_SIGNATURE,
	REASON_EXPIRED,
	REASON_MALFORMED_TOKEN,
	REASON_METADATA_UNAVAILABLE,
	REASON_MISSING_HEADER,
	REASON_NOT_YET_VALID,
	REASON_SERVICE_URL_MISMATCH,
	REASON_UNKNOWN_KEY,
	TeamsAuthResult,
)

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = ("RS256",)
REQUIRED_ENDORSEMENT = "msteams"
# Minimum gap between forced (unknown-kid) JWKS refreshes; stops kid-spray from
# turning inbound traffic into outbound metadata fetches.
FORCED_REFRESH_MIN_INTERVAL = 60
CACHE_KEY_PREFIX = "teams:jwks:"

# issuer -> OpenID metadata URL used to find the signing keys for that issuer.
# Bot Framework tokens use the BF metadata; Entra-issued tokens use the tenant's own.
ENTRA_METADATA_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"

# process-local cache: metadata_url -> {"keys": {kid: jwk}, "fetched": float, "forced": float}
_MEM: dict[str, dict] = {}


def _reset_cache() -> None:
	"""Test helper: drop the in-process cache."""
	_MEM.clear()


# -- frappe.cache layer (best effort; any failure falls back to the in-process cache) --


def _cache_get(key: str) -> Any:
	try:
		import frappe

		return frappe.cache().get_value(key)
	except Exception:
		return None


def _cache_set(key: str, value: dict) -> None:
	try:
		import frappe

		frappe.cache().set_value(key, value, expires_in_sec=JWKS_CACHE_SECONDS)
	except Exception:
		pass


def _fresh(entry: Any, ts: float) -> bool:
	return (
		isinstance(entry, dict)
		and isinstance(entry.get("keys"), dict)
		and isinstance(entry.get("fetched"), (int, float))
		and 0 <= ts - entry["fetched"] < JWKS_CACHE_SECONDS
	)


class _MetadataError(Exception):
	pass


def _download(metadata_url: str, fetch_json, ts: float) -> dict:
	try:
		meta = fetch_json(metadata_url)
		jwks_uri = meta.get("jwks_uri") if isinstance(meta, dict) else None
		if not isinstance(jwks_uri, str) or not jwks_uri.startswith("https://"):
			raise _MetadataError("no jwks_uri")
		jwks = fetch_json(jwks_uri)
		raw_keys = jwks.get("keys") if isinstance(jwks, dict) else None
		if not isinstance(raw_keys, list):
			raise _MetadataError("no keys")
	except Exception as exc:
		logger.warning("teams_auth: metadata fetch failed (%s)", type(exc).__name__)
		raise _MetadataError(type(exc).__name__) from None
	keys = {k["kid"]: k for k in raw_keys if isinstance(k, dict) and isinstance(k.get("kid"), str)}
	if not keys:
		raise _MetadataError("empty jwks")
	return {"keys": keys, "fetched": ts, "forced": 0.0}


def _get_key(metadata_url: str, kid: str, fetch_json, ts: float) -> dict | None:
	"""Return the JWK for ``kid`` (or None). Raises _MetadataError when keys cannot be loaded."""
	ckey = CACHE_KEY_PREFIX + metadata_url
	entry = _MEM.get(metadata_url)
	if not _fresh(entry, ts):
		shared = _cache_get(ckey)
		entry = shared if _fresh(shared, ts) else None
		if entry is None:
			entry = _download(metadata_url, fetch_json, ts)
			_cache_set(ckey, entry)
		_MEM[metadata_url] = entry
	jwk = entry["keys"].get(kid)
	if jwk is not None:
		return jwk
	# Unknown kid: one forced refresh, rate limited.
	if ts - max(entry.get("forced", 0.0), entry["fetched"]) < FORCED_REFRESH_MIN_INTERVAL:
		return None
	fresh = _download(metadata_url, fetch_json, ts)
	fresh["forced"] = ts
	_MEM[metadata_url] = fresh
	_cache_set(ckey, fresh)
	return fresh["keys"].get(kid)


def _norm_url(url: Any) -> str:
	if not isinstance(url, str) or not url.strip():
		return ""
	parts = urlsplit(url.strip())
	if not parts.scheme or not parts.netloc:
		return ""
	return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def _issuer_table(tenant_id: str | None) -> dict[str, str]:
	"""allowed issuer -> OpenID metadata URL. Add an issuer here (one line) to accept it."""
	table = {BOT_ISSUER: OPENID_METADATA_URL}
	if tenant_id:
		for tmpl in ENTRA_ISSUER_TEMPLATES:
			table[tmpl.format(tenant_id=tenant_id)] = ENTRA_METADATA_TEMPLATE.format(tenant_id=tenant_id)
	return table


def _fail(reason: str) -> TeamsAuthResult:
	return TeamsAuthResult(False, reason, {})


def verify_bearer(
	auth_header: str,
	*,
	app_id: str,
	activity_service_url: str,
	fetch_json,
	now,
	tenant_id: str | None = None,
) -> TeamsAuthResult:
	try:
		return _verify(auth_header, app_id, activity_service_url, fetch_json, now, tenant_id)
	except Exception as exc:  # never raise, never leak token text
		logger.warning("teams_auth: unexpected verify error (%s)", type(exc).__name__)
		return _fail(REASON_MALFORMED_TOKEN)


def _verify(auth_header, app_id, activity_service_url, fetch_json, now, tenant_id) -> TeamsAuthResult:
	if not isinstance(auth_header, str) or not auth_header.strip():
		return _fail(REASON_MISSING_HEADER)
	scheme, _, token = auth_header.strip().partition(" ")
	token = token.strip()
	if scheme.lower() != "bearer" or not token or " " in token:
		return _fail(REASON_MALFORMED_TOKEN)

	try:
		header = jwt.get_unverified_header(token)
		unverified = jwt.decode(token, options={"verify_signature": False})
	except Exception:
		return _fail(REASON_MALFORMED_TOKEN)
	if not isinstance(header, dict) or not isinstance(unverified, dict):
		return _fail(REASON_MALFORMED_TOKEN)

	if header.get("alg") not in ALLOWED_ALGORITHMS:
		return _fail(REASON_BAD_ALGORITHM)

	# The unverified iss only selects which key set to use; it is re-checked after the signature.
	table = _issuer_table(tenant_id)
	iss = unverified.get("iss")
	if not isinstance(iss, str) or iss not in table:
		return _fail(REASON_BAD_ISSUER)

	kid = header.get("kid")
	if not isinstance(kid, str) or not kid:
		return _fail(REASON_UNKNOWN_KEY)

	ts = float(now())
	try:
		jwk = _get_key(table[iss], kid, fetch_json, ts)
	except _MetadataError:
		return _fail(REASON_METADATA_UNAVAILABLE)
	if jwk is None:
		return _fail(REASON_UNKNOWN_KEY)
	if jwk.get("kty") != "RSA":
		return _fail(REASON_BAD_ALGORITHM)

	try:
		key = RSAAlgorithm.from_jwk(json.dumps(jwk))
		claims = jwt.decode(
			token,
			key,
			algorithms=list(ALLOWED_ALGORITHMS),
			options={
				"verify_signature": True,
				"verify_exp": False,
				"verify_nbf": False,
				"verify_iat": False,
				"verify_aud": False,
				"verify_iss": False,
			},
		)
	except jwt.InvalidSignatureError:
		return _fail(REASON_BAD_SIGNATURE)
	except Exception:
		return _fail(REASON_MALFORMED_TOKEN)

	if claims.get("iss") not in table:
		return _fail(REASON_BAD_ISSUER)

	aud = claims.get("aud")
	auds = aud if isinstance(aud, list) else [aud]
	if not app_id or app_id not in auds:
		return _fail(REASON_BAD_AUDIENCE)

	exp, nbf = claims.get("exp"), claims.get("nbf")
	if not isinstance(exp, (int, float)) or isinstance(exp, bool):
		return _fail(REASON_EXPIRED)
	if ts > exp + CLOCK_SKEW_SECONDS:
		return _fail(REASON_EXPIRED)
	if nbf is not None and (not isinstance(nbf, (int, float)) or ts < nbf - CLOCK_SKEW_SECONDS):
		return _fail(REASON_NOT_YET_VALID)

	claim_url = _norm_url(claims.get("serviceurl", claims.get("serviceUrl")))
	if not claim_url or claim_url != _norm_url(activity_service_url):
		return _fail(REASON_SERVICE_URL_MISMATCH)

	endorsements = jwk.get("endorsements")
	if endorsements and REQUIRED_ENDORSEMENT not in endorsements:
		return _fail(REASON_BAD_ENDORSEMENT)

	return TeamsAuthResult(True, "ok", dict(claims))
