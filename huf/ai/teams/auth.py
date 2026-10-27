"""Inbound request authentication for Teams (Bot Framework) activities.

Implements the Bot Connector -> bot validation contract
(https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-connector-authentication):

- ``Authorization: Bearer <JWT>``, RS256 only (``none``/HS*/alg confusion rejected);
- signature checked against the key (``kid``) published at the Bot Framework JWKS;
- ``iss`` is exactly ``https://api.botframework.com``;
- ``aud`` equals the configured bot ``app_id``;
- ``exp``/``nbf`` honoured with a 300 s clock-skew leeway;
- the ``serviceUrl`` claim (``serviceUrl`` or ``serviceurl``) equals ``activity.serviceUrl``;
- the JWKS key's ``endorsements`` contain ``activity.channelId`` (``msteams``).

Everything fails closed: any problem returns ``False`` and ``verify_request`` never raises. The spec
asks for HTTP 403 on a missing endorsement and 401 otherwise; this function only answers
accept/reject, the generic webhook decides the status code (it currently answers 401 for all).

Key cache: process-level plus ``frappe.cache`` (shared by workers), refreshed every 24 h. A stale cache
is kept (up to 7 days) when a refresh fails. An unknown ``kid`` triggers at most one forced refetch per
5 minutes. With no cached keys and a failing JWKS/OpenID endpoint the request is rejected.

Log lines carry reason codes only; tokens, headers and bodies are never logged.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from huf.ai.gateway_adapters.types import GatewayInboundRequest

logger = logging.getLogger("huf.teams.auth")

BOT_FRAMEWORK_OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
BOT_FRAMEWORK_HOST = "login.botframework.com"
BOT_FRAMEWORK_ISSUER = "https://api.botframework.com"

# TODO(entra): tenant-specific Entra issuers (https://sts.windows.net/{tenant}/,
# https://login.microsoftonline.com/{tenant}/v2.0) with Entra JWKS are NOT accepted yet. When real-tenant
# behaviour is confirmed, extend ``_allowed_issuers`` (only place that decides) behind an explicit flag.

CLOCK_SKEW_SECONDS = 300
KEY_TTL_SECONDS = 24 * 3600
STALE_KEY_MAX_SECONDS = 7 * 24 * 3600
MIN_FORCED_REFRESH_SECONDS = 300
FAILURE_BACKOFF_SECONDS = 15
HTTP_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TOKEN_CHARS = 16 * 1024
MAX_KEYS = 64
_CACHE_KEY_PREFIX = "huf:teams:botframework_jwks:"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Test hook. Only set by ``_set_test_openid_url`` (called from tests); nothing reads request data into it.
_test_openid_url: str | None = None

_lock = threading.RLock()
_state: dict[str, Any] = {"keys": None, "fetched_at": 0.0, "last_forced": 0.0, "last_failure": 0.0}


class _FetchError(Exception):
	"""JWKS/OpenID retrieval failed (reason code only, never response content)."""


# -- test hooks --------------------------------------------------------------------------------------


def _set_test_openid_url(url: str | None) -> None:
	"""TEST ONLY: point discovery at a loopback fake server (http allowed). ``None`` restores production."""
	global _test_openid_url
	if url is not None:
		parts = urlsplit(url)
		if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _LOOPBACK_HOSTS:
			raise ValueError("test OpenID URL must be a loopback address")  # noqa: TRY003
	with _lock:
		_test_openid_url = url
		_reset_cache()


def _reset_cache() -> None:
	"""Drop process and shared cache for the active OpenID URL (tests)."""
	with _lock:
		_state.update(keys=None, fetched_at=0.0, last_forced=0.0, last_failure=0.0)
	try:
		import frappe

		frappe.cache.delete_value(_cache_key())
	except Exception:  # noqa: BLE001, S110
		pass


def _openid_url() -> str:
	return _test_openid_url or BOT_FRAMEWORK_OPENID_URL


def _cache_key() -> str:
	import hashlib

	return _CACHE_KEY_PREFIX + hashlib.sha256(_openid_url().encode()).hexdigest()[:16]


# -- fetching ----------------------------------------------------------------------------------------


def _url_ok(url: str) -> bool:
	parts = urlsplit(url)
	host = (parts.hostname or "").lower()
	if _test_openid_url:
		return parts.scheme in ("http", "https") and host in _LOOPBACK_HOSTS
	return parts.scheme == "https" and host == BOT_FRAMEWORK_HOST and parts.port in (None, 443)


def _get_json(url: str) -> Any:
	if not _url_ok(url):
		raise _FetchError("url_rejected")
	import requests

	session = requests.Session()
	session.trust_env = not _test_openid_url  # tests must never be routed via env proxies
	try:
		resp = session.get(url, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=False, stream=True)
		try:
			if resp.status_code != 200:
				raise _FetchError(f"http_{resp.status_code}")
			raw = b""
			for chunk in resp.iter_content(chunk_size=16384):
				raw += chunk
				if len(raw) > MAX_RESPONSE_BYTES:
					raise _FetchError("response_too_large")
		finally:
			resp.close()
	except _FetchError:
		raise
	except Exception as exc:  # noqa: BLE001
		raise _FetchError(type(exc).__name__) from None
	finally:
		session.close()
	try:
		return json.loads(raw)
	except ValueError:
		raise _FetchError("invalid_json") from None


def _fetch_keys() -> dict[str, dict[str, Any]]:
	config = _get_json(_openid_url())
	jwks_uri = config.get("jwks_uri") if isinstance(config, dict) else None
	if not isinstance(jwks_uri, str):
		raise _FetchError("no_jwks_uri")
	jwks = _get_json(jwks_uri)
	entries = jwks.get("keys") if isinstance(jwks, dict) else None
	if not isinstance(entries, list):
		raise _FetchError("bad_jwks")
	keys: dict[str, dict[str, Any]] = {}
	for jwk in entries[:MAX_KEYS]:
		if isinstance(jwk, dict) and isinstance(jwk.get("kid"), str) and jwk.get("kty") == "RSA":
			keys[jwk["kid"]] = jwk
	if not keys:
		raise _FetchError("no_keys")
	return keys


def _load_shared_cache() -> None:
	try:
		import frappe

		cached = frappe.cache.get_value(_cache_key())
	except Exception:  # noqa: BLE001
		return
	if isinstance(cached, dict) and isinstance(cached.get("keys"), dict):
		_state["keys"] = cached["keys"]
		_state["fetched_at"] = float(cached.get("fetched_at") or 0)


def _store(keys: dict[str, dict[str, Any]], now: float) -> None:
	_state["keys"] = keys
	_state["fetched_at"] = now
	try:
		import frappe

		frappe.cache.set_value(
			_cache_key(), {"keys": keys, "fetched_at": now}, expires_in_sec=STALE_KEY_MAX_SECONDS
		)
	except Exception:  # noqa: BLE001, S110
		pass


def _refresh(now: float) -> bool:
	"""Fetch keys now. Caller holds ``_lock``. False (and a short backoff) on failure."""
	if now - _state["last_failure"] < FAILURE_BACKOFF_SECONDS:
		return False
	try:
		_store(_fetch_keys(), now)
		return True  # noqa: TRY300
	except _FetchError as exc:
		_state["last_failure"] = now
		logger.warning(
			"Teams JWKS refresh failed (%s); %s",
			exc,
			"using cached keys" if _state["keys"] else "no cached keys",
		)
		return False


def _get_key(kid: str) -> dict[str, Any] | None:
	"""Return the JWK for ``kid`` or None. Applies the cache/refetch policy."""
	with _lock:
		now = time.time()
		if _state["keys"] is None:
			_load_shared_cache()
		keys = _state["keys"]
		age = now - _state["fetched_at"]
		if keys is None or age >= KEY_TTL_SECONDS:
			_refresh(now)
			keys = _state["keys"]
			age = now - _state["fetched_at"]
		if keys is None or age >= STALE_KEY_MAX_SECONDS:
			return None
		if kid in keys:
			return keys[kid]
		# Unknown kid: ONE forced refetch, at most once per MIN_FORCED_REFRESH_SECONDS.
		if now - _state["last_forced"] >= MIN_FORCED_REFRESH_SECONDS:
			_state["last_forced"] = now
			if _refresh(now):
				return _state["keys"].get(kid)
		return None


# -- validation --------------------------------------------------------------------------------------


def _allowed_issuers(credentials: Mapping[str, str]) -> tuple[str, ...]:
	# TODO(entra): add tenant-specific issuers here behind an explicit flag (see module header).
	return (BOT_FRAMEWORK_ISSUER,)


def _normalize_service_url(value: Any) -> str:
	if not isinstance(value, str) or not value.strip():
		return ""
	parts = urlsplit(value.strip())
	if not parts.scheme or not parts.hostname:
		return ""
	port = f":{parts.port}" if parts.port else ""
	return f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}{parts.path.rstrip('/')}"


def _service_url_claim(claims: Mapping[str, Any]) -> Any:
	for name, value in claims.items():
		if isinstance(name, str) and name.lower() == "serviceurl":
			return value
	return None


def _header(request: GatewayInboundRequest, name: str) -> str:
	for key, value in (request.headers or {}).items():
		if isinstance(key, str) and key.lower() == name:
			return str(value or "")
	return ""


def _reject(reason: str) -> bool:
	logger.warning("Teams inbound auth rejected: %s", reason)
	return False


def verify_request(request: GatewayInboundRequest, credentials: Mapping[str, str]) -> bool:
	"""True only for a fully validated Bot Framework JWT for this bot and this activity. Never raises."""
	try:
		return _verify(request, credentials)
	except Exception as exc:  # noqa: BLE001
		return _reject(f"error:{type(exc).__name__}")


def _verify(request: GatewayInboundRequest, credentials: Mapping[str, str]) -> bool:
	import jwt as pyjwt

	app_id = str((credentials or {}).get("app_id") or "").strip()
	if not app_id:
		return _reject("no_app_id")

	scheme, _, token = _header(request, "authorization").strip().partition(" ")
	token = token.strip()
	if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN_CHARS:
		return _reject("bad_authorization_header")

	try:
		activity = json.loads((request.body or b"").decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return _reject("invalid_body")
	if not isinstance(activity, dict):
		return _reject("invalid_body")
	body_service_url = _normalize_service_url(activity.get("serviceUrl"))
	channel_id = activity.get("channelId")
	if not body_service_url or not isinstance(channel_id, str) or not channel_id.strip():
		return _reject("missing_service_url_or_channel")

	try:
		header = pyjwt.get_unverified_header(token)
	except pyjwt.PyJWTError:
		return _reject("malformed_token")
	kid = header.get("kid")
	if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
		return _reject("bad_alg_or_kid")

	jwk = _get_key(kid)
	if jwk is None:
		return _reject("key_unavailable")

	issuers = _allowed_issuers(credentials)
	try:
		public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
		claims = pyjwt.decode(
			token,
			key=public_key,
			algorithms=["RS256"],
			audience=app_id,
			issuer=list(issuers),
			leeway=CLOCK_SKEW_SECONDS,
			options={"require": ["exp", "aud", "iss"], "verify_signature": True, "verify_nbf": True},
		)
	except pyjwt.PyJWTError as exc:
		return _reject(f"jwt:{type(exc).__name__}")

	if _normalize_service_url(_service_url_claim(claims)) != body_service_url:
		return _reject("service_url_mismatch")

	endorsements = jwk.get("endorsements")
	if not isinstance(endorsements, list) or channel_id.strip().lower() not in {
		str(e).lower() for e in endorsements
	}:
		return _reject("channel_not_endorsed")  # spec: HTTP 403
	return True
