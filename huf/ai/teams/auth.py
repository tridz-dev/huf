"""Inbound request authentication for Teams (Bot Framework) activities.

Implements the Bot Connector -> bot validation contract
(https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-connector-authentication):

- ``Authorization: Bearer <JWT>``, RS256 only (``none``/HS*/alg confusion rejected);
- signature checked against the key (``kid``) published at the Bot Framework JWKS;
- ``iss`` is exactly ``https://api.botframework.com``;
- ``aud`` equals the configured bot ``app_id``;
- ``exp``/``nbf`` honoured with a 300 s clock-skew leeway;
- the ``serviceUrl`` claim (``serviceUrl`` or ``serviceurl``) equals ``activity.serviceUrl``;
- ``activity.channelId`` is ``msteams`` (pinned: the Bot Framework JWKS also endorses webchat/directline/
  emulator, whose secret holders could otherwise mint activities with arbitrary tenant/sender data) AND the
  JWKS key's ``endorsements`` contain it.

Known protocol limit (accepted, S3): the Bot Framework JWT is NOT bound to the request body. A captured,
unexpired token (~1 h lifetime + skew) can be replayed with an arbitrary body for the same bot whose
``serviceUrl`` equals the claim. Mitigations are TLS on the endpoint, the channel pin, the serviceUrl match,
tenant admission and event de-duplication; there is no cryptographic body binding in the protocol.

Everything fails closed: any problem returns ``False`` and ``verify_request`` never raises. The spec
asks for HTTP 403 on a missing endorsement and 401 otherwise; this function only answers
accept/reject, the generic webhook decides the status code (it currently answers 401 for all).

Key cache: process-level plus ``frappe.cache`` (shared by workers), refreshed every 24 h. A stale cache
is kept (up to 7 days) when a refresh fails. An unknown ``kid`` triggers at most one forced refetch per
5 minutes, and only for tokens that already passed the cheap checks (RS256, sane ``kid``, unverified
``aud``/``iss``/``exp``/``serviceUrl`` match), so junk kids cannot burn the window. JWKS network I/O runs
outside the module lock behind a single-flight guard: one thread fetches, others keep verifying with cached
keys (stale ones during a TTL refresh) or wait at most ``FETCH_WAIT_SECONDS``. With no cached keys and a failing JWKS/OpenID endpoint the request is rejected.

Log lines carry reason codes only; tokens, headers and bodies are never logged. A rejection at the
issuer/audience pre-check additionally logs ONE structured diagnostic line built from the UNVERIFIED
token: issuer kind (botframework/entra_v1/entra_v2/other), ``ver``, and booleans (aud/azp/appid equal the
app id, tid equals the tenant id), plus the spelling of the serviceUrl claim. Never raw ids or the token.
Every rejection is also counted (reason code only) in the global ``auth`` bucket of the Teams drop record
(``readiness.record_drop``) so operators see silent 401s in readiness / Verify connection.

OPT-IN Entra issuers (UNVERIFIED against a real tenant): Microsoft's newer SDKs also accept Entra-issued
inbound tokens. With site config ``teams_accept_entra_tokens = 1`` (default off) a token whose ``iss`` is
``https://login.microsoftonline.com/<tenant_id>/v2.0`` or ``https://sts.windows.net/<tenant_id>/`` (the
Gateway's configured ``tenant_id``, a GUID) is accepted when it is signed by a key from the tenant-pinned
Entra JWKS ``https://login.microsoftonline.com/<tenant_id>/discovery/v2.0/keys`` (https, that host only,
same size/redirect/timeout limits, cache, single-flight and pre-check structure as the Bot Framework
JWKS), ``aud`` == app id, ``tid`` == tenant id, and all other checks pass (channel pin, serviceUrl claim
when present, exp/nbf). Entra keys carry no channel ``endorsements``; the channelId pin applies instead.
"""

from __future__ import annotations

import json
import logging
import re
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
ENTRA_HOST = "login.microsoftonline.com"
ENTRA_JWKS_URL = "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
ENTRA_ISSUERS = ("https://login.microsoftonline.com/{tenant}/v2.0", "https://sts.windows.net/{tenant}/")
ENTRA_FLAG = "teams_accept_entra_tokens"
_GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

CLOCK_SKEW_SECONDS = 300
KEY_TTL_SECONDS = 24 * 3600
STALE_KEY_MAX_SECONDS = 7 * 24 * 3600
MIN_FORCED_REFRESH_SECONDS = 300
FAILURE_BACKOFF_SECONDS = 15
HTTP_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TOKEN_CHARS = 16 * 1024
MAX_KEYS = 64
FETCH_WAIT_SECONDS = 2 * HTTP_TIMEOUT_SECONDS + 1
MAX_KID_CHARS = 128
_KID_RE = re.compile(r"[A-Za-z0-9._~+/=-]+")
TEAMS_CHANNEL_ID = "msteams"
_CACHE_KEY_PREFIX = "huf:teams:botframework_jwks:"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Test hooks. Only set by ``_set_test_openid_url`` / ``_set_test_entra_jwks_url`` (called from tests);
# nothing reads request data into them.
_test_openid_url: str | None = None
_test_entra_jwks_url: str | None = None  # may contain ``{tenant}``

_lock = threading.RLock()
_state: dict[str, Any] = {
	"keys": None,
	"fetched_at": 0.0,
	"last_forced": 0.0,
	"last_failure": 0.0,
	"inflight": None,  # threading.Event while one thread fetches (single-flight)
}


# One key source per tenant for the opt-in Entra path; same state shape as ``_state``.
_entra_states: dict[str, dict[str, Any]] = {}


def _new_state() -> dict[str, Any]:
	return {"keys": None, "fetched_at": 0.0, "last_forced": 0.0, "last_failure": 0.0, "inflight": None}


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


def _set_test_entra_jwks_url(url: str | None) -> None:
	"""TEST ONLY: loopback Entra JWKS URL (``{tenant}`` placeholder allowed). ``None`` restores production."""
	global _test_entra_jwks_url
	if url is not None:
		parts = urlsplit(url.replace("{tenant}", "t"))
		if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _LOOPBACK_HOSTS:
			raise ValueError("test Entra JWKS URL must be a loopback address")  # noqa: TRY003
	with _lock:
		_reset_cache()  # drops shared entries under the OLD url, then under the new one
		_test_entra_jwks_url = url
		_reset_cache()


def _reset_cache() -> None:
	"""Drop process and shared caches for the active OpenID URL and all Entra tenants (tests)."""
	with _lock:
		_state.update(_new_state())
		tenants = list(_entra_states)
		_entra_states.clear()
	try:
		import frappe

		frappe.cache.delete_value(_cache_key())
		for tenant in tenants:
			frappe.cache.delete_value(_entra_cache_key(tenant))
	except Exception:  # noqa: BLE001, S110
		pass


def _openid_url() -> str:
	return _test_openid_url or BOT_FRAMEWORK_OPENID_URL


def _cache_key() -> str:
	import hashlib

	return _CACHE_KEY_PREFIX + hashlib.sha256(_openid_url().encode()).hexdigest()[:16]


# -- fetching ----------------------------------------------------------------------------------------


def _url_ok(url: str, prod_host: str = BOT_FRAMEWORK_HOST, test_mode: bool | None = None) -> bool:
	parts = urlsplit(url)
	host = (parts.hostname or "").lower()
	if test_mode if test_mode is not None else bool(_test_openid_url):
		return parts.scheme in ("http", "https") and host in _LOOPBACK_HOSTS
	return parts.scheme == "https" and host == prod_host and parts.port in (None, 443)


def _get_json(url: str, prod_host: str = BOT_FRAMEWORK_HOST, test_mode: bool | None = None) -> Any:
	test_mode = test_mode if test_mode is not None else bool(_test_openid_url)
	if not _url_ok(url, prod_host, test_mode):
		raise _FetchError("url_rejected")
	import requests

	session = requests.Session()
	session.trust_env = not test_mode  # tests must never be routed via env proxies
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
	return _parse_jwks(_get_json(jwks_uri))


def _entra_jwks_url(tenant: str) -> str:
	return (_test_entra_jwks_url or ENTRA_JWKS_URL).replace("{tenant}", tenant)


def _fetch_entra_keys(tenant: str) -> dict[str, dict[str, Any]]:
	"""Tenant-pinned Entra JWKS (no discovery hop: the URL is fixed and pinned to ``ENTRA_HOST``)."""
	return _parse_jwks(_get_json(_entra_jwks_url(tenant), ENTRA_HOST, bool(_test_entra_jwks_url)))


def _parse_jwks(jwks: Any) -> dict[str, dict[str, Any]]:
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


def _bf_source() -> dict[str, Any]:
	# ``_fetch_keys`` is looked up at call time so tests can patch it.
	return {"state": _state, "cache_key": _cache_key(), "fetch": lambda: _fetch_keys()}


def _entra_cache_key(tenant: str) -> str:
	import hashlib

	return _CACHE_KEY_PREFIX + "entra:" + hashlib.sha256(_entra_jwks_url(tenant).encode()).hexdigest()[:16]


def _entra_source(tenant: str) -> dict[str, Any]:
	with _lock:
		state = _entra_states.setdefault(tenant, _new_state())
	return {"state": state, "cache_key": _entra_cache_key(tenant), "fetch": lambda: _fetch_entra_keys(tenant)}


def _load_shared_cache(src: dict[str, Any]) -> None:
	try:
		import frappe

		cached = frappe.cache.get_value(src["cache_key"])
	except Exception:  # noqa: BLE001
		return
	if isinstance(cached, dict) and isinstance(cached.get("keys"), dict):
		src["state"]["keys"] = cached["keys"]
		src["state"]["fetched_at"] = float(cached.get("fetched_at") or 0)


def _store_shared(src: dict[str, Any], keys: dict[str, dict[str, Any]], now: float) -> None:
	try:
		import frappe

		frappe.cache.set_value(
			src["cache_key"], {"keys": keys, "fetched_at": now}, expires_in_sec=STALE_KEY_MAX_SECONDS
		)
	except Exception:  # noqa: BLE001, S110
		pass


def _refresh(now: float, src: dict[str, Any] | None = None) -> bool:
	"""Single-flight JWKS fetch WITHOUT holding ``_lock`` during network I/O.

	The first caller fetches; concurrent callers wait (bounded) for its result. False on failure/backoff.
	"""
	src = src or _bf_source()
	_state = src["state"]
	with _lock:
		if now - _state["last_failure"] < FAILURE_BACKOFF_SECONDS:
			return False
		event = _state["inflight"]
		leader = event is None
		if leader:
			event = threading.Event()
			_state["inflight"] = event
	if not leader:
		return event.wait(FETCH_WAIT_SECONDS) and bool(getattr(event, "ok", False))
	keys: dict[str, dict[str, Any]] | None = None
	try:
		keys = src["fetch"]()
	except _FetchError as exc:
		logger.warning(
			"Teams JWKS refresh failed (%s); %s",
			exc,
			"using cached keys" if _state["keys"] else "no cached keys",
		)
	finally:
		with _lock:
			if keys is not None:
				_state["keys"] = keys
				_state["fetched_at"] = now
			else:
				_state["last_failure"] = now
			_state["inflight"] = None
		event.ok = keys is not None  # type: ignore[attr-defined]
		event.set()
	if keys is None:
		return False
	_store_shared(src, keys, now)
	return True


def _snapshot(now: float, src: dict[str, Any]) -> tuple[dict[str, dict[str, Any]] | None, float]:
	with _lock:
		if src["state"]["keys"] is None:
			_load_shared_cache(src)
		return src["state"]["keys"], now - src["state"]["fetched_at"]


def _get_key(kid: str, src: dict[str, Any] | None = None) -> dict[str, Any] | None:
	"""Return the JWK for ``kid`` or None. Applies the cache/refetch policy (never fetches under ``_lock``)."""
	src = src or _bf_source()
	_state = src["state"]
	now = time.time()
	keys, age = _snapshot(now, src)
	if keys is None or age >= KEY_TTL_SECONDS:
		usable_stale = keys is not None and age < STALE_KEY_MAX_SECONDS
		if not (usable_stale and _state["inflight"] is not None):  # someone else refreshing: use stale keys
			_refresh(now, src)
			keys, age = _snapshot(now, src)
	if keys is None or age >= STALE_KEY_MAX_SECONDS:
		return None
	if kid in keys:
		return keys[kid]
	# Unknown kid: ONE forced refetch, at most once per MIN_FORCED_REFRESH_SECONDS (caller pre-checked token).
	with _lock:
		if now - _state["last_forced"] < MIN_FORCED_REFRESH_SECONDS:
			return None
		_state["last_forced"] = now
	if _refresh(now, src):
		return (_state["keys"] or {}).get(kid)
	return None


# -- validation --------------------------------------------------------------------------------------


def _entra_enabled() -> bool:
	try:
		import frappe

		return bool(frappe.conf.get(ENTRA_FLAG))
	except Exception:  # noqa: BLE001
		return False


def _tenant(credentials: Mapping[str, str]) -> str:
	tenant = str((credentials or {}).get("tenant_id") or "").strip().lower()
	return tenant if _GUID_RE.fullmatch(tenant) else ""


def _entra_issuers(credentials: Mapping[str, str]) -> tuple[str, ...]:
	tenant = _tenant(credentials)
	if not tenant or not _entra_enabled():
		return ()
	return tuple(i.format(tenant=tenant) for i in ENTRA_ISSUERS)


def _allowed_issuers(credentials: Mapping[str, str]) -> tuple[str, ...]:
	"""The only place that decides accepted issuers: Bot Framework, plus tenant-pinned Entra when opted in."""
	return (BOT_FRAMEWORK_ISSUER, *_entra_issuers(credentials))


def _normalize_service_url(value: Any) -> str:
	if not isinstance(value, str) or not value.strip():
		return ""
	parts = urlsplit(value.strip())
	if not parts.scheme or not parts.hostname:
		return ""
	port = f":{parts.port}" if parts.port else ""
	# Path lowercased like refs.validate_service_url (region / tenant GUID segments are case-insensitive).
	return f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}{parts.path.rstrip('/').lower()}"


def _service_url_claim(claims: Mapping[str, Any]) -> Any:
	for name, value in claims.items():
		if isinstance(name, str) and name.lower() == "serviceurl":
			return value
	return None


def _wall_clock() -> float:
	# Same clock PyJWT uses for exp (not ``time.time``, which the key-cache policy uses).
	from datetime import UTC, datetime

	return datetime.now(UTC).timestamp()


def _issuer_kind(iss: Any) -> str:
	if iss == BOT_FRAMEWORK_ISSUER:
		return "botframework"
	if isinstance(iss, str) and iss.startswith("https://sts.windows.net/"):
		return "entra_v1"
	if isinstance(iss, str) and iss.startswith("https://login.microsoftonline.com/"):
		return "entra_v2"
	return "other"


def _log_claim_shape(reason: str, claims: Mapping[str, Any], app_id: str, tenant: str) -> None:
	"""ONE structured line describing the UNVERIFIED token shape. Booleans and enums only, never ids."""
	aud = claims.get("aud")
	auds = aud if isinstance(aud, list) else [aud]
	iss = claims.get("iss")
	claim_names = [k for k in claims if isinstance(k, str) and k.lower() == "serviceurl"]
	ver = claims.get("ver")
	logger.warning(
		"Teams inbound token shape: reason=%s iss_kind=%s iss_tenant_match=%s aud_is_app_id=%s ver=%s "
		"azp_is_app_id=%s appid_is_app_id=%s tid_is_tenant=%s serviceurl_claim=%s entra_enabled=%s",
		reason,
		_issuer_kind(iss),
		bool(tenant) and isinstance(iss, str) and tenant in iss.lower(),
		app_id in auds,
		ver if ver in ("1.0", "2.0") else ("absent" if ver is None else "other"),
		claims.get("azp") == app_id,
		claims.get("appid") == app_id,
		bool(tenant) and str(claims.get("tid") or "").lower() == tenant,
		claim_names[0]
		if len(claim_names) == 1 and claim_names[0] in ("serviceUrl", "serviceurl")
		else ("absent" if not claim_names else "other"),
		_entra_enabled(),
	)


def _precheck(
	token: str, app_id: str, issuers: tuple[str, ...], body_service_url: str, tenant: str = ""
) -> str | None:
	"""Cheap UNVERIFIED claim checks run before any key lookup/refetch. Returns a reason code or None.

	Not a security decision on its own (the signature is checked afterwards); it only stops junk tokens
	from triggering the rate-limited forced JWKS refetch.
	"""
	import jwt as pyjwt

	try:
		claims = pyjwt.decode(token, options={"verify_signature": False})
	except pyjwt.PyJWTError:
		return "malformed_token"
	if not isinstance(claims, dict):
		return "malformed_token"
	aud = claims.get("aud")
	auds = aud if isinstance(aud, list) else [aud]
	reason = None
	if app_id not in auds:
		reason = "pre_aud"
	elif claims.get("iss") not in issuers:
		reason = "pre_iss"
	elif claims.get("iss") != BOT_FRAMEWORK_ISSUER and str(claims.get("tid") or "").lower() != tenant:
		reason = "pre_tid"
	if reason:
		_log_claim_shape(reason, claims, app_id, tenant)
		return reason
	exp = claims.get("exp")
	if not isinstance(exp, int | float) or exp + CLOCK_SKEW_SECONDS < _wall_clock():
		return "pre_exp"
	claim = _service_url_claim(claims)
	if claims.get("iss") != BOT_FRAMEWORK_ISSUER and claim is None:
		return None  # Entra tokens may not carry the claim; the check applies only when present
	if _normalize_service_url(claim) != body_service_url:
		return "service_url_mismatch"
	return None


def _header(request: GatewayInboundRequest, name: str) -> str:
	for key, value in (request.headers or {}).items():
		if isinstance(key, str) and key.lower() == name:
			return str(value or "")
	return ""


def _reject(reason: str) -> bool:
	logger.warning("Teams inbound auth rejected: %s", reason)
	try:
		from huf.ai.teams import readiness

		readiness.record_drop(readiness.AUTH_BUCKET, f"auth:{reason}")
	except Exception:  # noqa: BLE001, S110
		pass  # visibility only; must never change the decision
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
	if channel_id.strip().lower() != TEAMS_CHANNEL_ID:
		return _reject("channel_not_msteams")

	try:
		header = pyjwt.get_unverified_header(token)
	except pyjwt.PyJWTError:
		return _reject("malformed_token")
	kid = header.get("kid")
	if (
		header.get("alg") != "RS256"
		or not isinstance(kid, str)
		or len(kid) > MAX_KID_CHARS
		or not _KID_RE.fullmatch(kid)
	):
		return _reject("bad_alg_or_kid")

	issuers = _allowed_issuers(credentials)
	tenant = _tenant(credentials)
	reason = _precheck(token, app_id, issuers, body_service_url, tenant)
	if reason:
		return _reject(reason)

	entra = pyjwt.decode(token, options={"verify_signature": False}).get("iss") != BOT_FRAMEWORK_ISSUER
	if entra:
		issuers = _entra_issuers(credentials)
	jwk = _get_key(kid, _entra_source(tenant) if entra else None)
	if jwk is None:
		return _reject("key_unavailable")

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

	claim = _service_url_claim(claims)
	if not (entra and claim is None) and _normalize_service_url(claim) != body_service_url:
		return _reject("service_url_mismatch")
	if entra:
		if str(claims.get("tid") or "").lower() != tenant:
			return _reject("tid_mismatch")
		return True  # Entra keys carry no endorsements; the channelId pin above applies instead

	endorsements = jwk.get("endorsements")
	if not isinstance(endorsements, list) or channel_id.strip().lower() not in {
		str(e).lower() for e in endorsements
	}:
		return _reject("channel_not_endorsed")  # spec: HTTP 403
	return True
