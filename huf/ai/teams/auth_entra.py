"""Opt-in Entra-issued inbound tokens and the token-shape diagnostic line (split from ``auth``).

Token-shape line: a rejection at the issuer/audience/tid pre-check logs ONE structured line built from the
UNVERIFIED token: issuer kind (botframework/entra_v1/entra_v2/other), ``ver``, booleans (aud/azp/appid equal
the app id, tid / issuer tenant equal the tenant id) and the spelling of the serviceUrl claim. Never raw ids
or the token.

OPT-IN Entra issuers (UNVERIFIED against a real tenant): Microsoft's newer SDKs also accept Entra-issued
inbound tokens. With site config ``teams_accept_entra_tokens = 1`` (default off) a token whose ``iss`` is
``https://login.microsoftonline.com/<tenant_id>/v2.0`` or ``https://sts.windows.net/<tenant_id>/`` (the
Gateway's configured ``tenant_id``, a GUID) is accepted when it is signed by a key from the tenant-pinned
Entra JWKS ``https://login.microsoftonline.com/<tenant_id>/discovery/v2.0/keys`` (https, that host only,
same size/redirect/timeout limits, cache, single-flight and pre-check structure as the Bot Framework
JWKS), ``aud`` == app id, ``tid`` == tenant id, and all other checks pass (channel pin, serviceUrl claim
when present, exp/nbf). Entra keys carry no channel ``endorsements``; the channelId pin applies instead.

Default OFF. UNVERIFIED against a real tenant: whether the Teams channel ever sends Entra-issued tokens is
unknown; enable only after inspecting the ``Teams inbound token shape`` log line on a real tenant.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("huf.teams.auth")

ENTRA_HOST = "login.microsoftonline.com"
ENTRA_JWKS_URL = "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
ENTRA_ISSUERS = ("https://login.microsoftonline.com/{tenant}/v2.0", "https://sts.windows.net/{tenant}/")
ENTRA_FLAG = "teams_accept_entra_tokens"
_GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Test hook. Only set by ``_set_test_entra_jwks_url`` (tests); may contain ``{tenant}``.
_test_entra_jwks_url: str | None = None


def _set_test_entra_jwks_url(url: str | None) -> None:
	"""TEST ONLY: loopback Entra JWKS URL (``{tenant}`` placeholder allowed). ``None`` restores production."""
	global _test_entra_jwks_url
	if url is not None:
		parts = urlsplit(url.replace("{tenant}", "t"))
		if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _LOOPBACK_HOSTS:
			raise ValueError("test Entra JWKS URL must be a loopback address")  # noqa: TRY003
	from huf.ai.teams import auth

	with auth._lock:
		auth._reset_cache()  # drops shared entries under the OLD url, then under the new one
		_test_entra_jwks_url = url
		auth._reset_cache()


def _entra_jwks_url(tenant: str) -> str:
	return (_test_entra_jwks_url or ENTRA_JWKS_URL).replace("{tenant}", tenant)


def _fetch_entra_keys(tenant: str) -> dict[str, dict[str, Any]]:
	"""Tenant-pinned Entra JWKS (no discovery hop: the URL is fixed and pinned to ``ENTRA_HOST``)."""
	from huf.ai.teams import auth

	return auth._parse_jwks(auth._get_json(_entra_jwks_url(tenant), ENTRA_HOST, bool(_test_entra_jwks_url)))


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


def _issuer_kind(iss: Any) -> str:
	if iss == "https://api.botframework.com":  # auth.BOT_FRAMEWORK_ISSUER
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


# One key source per tenant for the opt-in Entra path; same state shape as ``_state``.
_entra_states: dict[str, dict[str, Any]] = {}


def _entra_cache_key(tenant: str) -> str:
	import hashlib

	from huf.ai.teams.auth import _CACHE_KEY_PREFIX

	return _CACHE_KEY_PREFIX + "entra:" + hashlib.sha256(_entra_jwks_url(tenant).encode()).hexdigest()[:16]


def _entra_source(tenant: str) -> dict[str, Any]:
	from huf.ai.teams import auth

	with auth._lock:
		state = _entra_states.setdefault(tenant, auth._new_state())
	return {"state": state, "cache_key": _entra_cache_key(tenant), "fetch": lambda: _fetch_entra_keys(tenant)}
