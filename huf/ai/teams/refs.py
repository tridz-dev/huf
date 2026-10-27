"""Conversation references: where to send proactive/reply Teams messages.

A Teams reply cannot be addressed from ``conversation_id`` alone; the Bot Connector ``serviceUrl`` is
regional and arrives only on inbound activities. The reference is therefore stored (frappe cache, long
TTL) when a *verified* activity is received, and recovered from the latest verified Gateway Event
``raw_payload`` for the conversation when the cache has been evicted.

The cache key is ``sha256(gateway_name NUL app_id NUL conversation_id)`` so two Gateways sharing an app id
never share or overwrite references; the app password is never involved.

Allowed serviceUrl hosts (outbound requests to it carry the bot bearer token): ONLY
``smba.trafficmanager.net`` with an optional region segment (``/amer/``, ``/emea/``, ``/teams/`` ...)
optionally followed by ONE tenant GUID segment (``/amer/<tenant-guid>/``, as seen on real tenants), with
an optional trailing slash. Host and path are lowercased; anything else (extra/empty/dot segments,
percent-encoding, query, fragment) is rejected. Microsoft documents the public Teams service URLs as ``https://smba.trafficmanager.net/<x>/``
(learn.microsoft.com/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages). The former
``*.trafficmanager.net`` wildcard let any Azure customer register a host, and ``*.botframework.com`` covers
non-Teams channels (Direct Line, Web Chat, token/login/api/state) with no Teams documentation behind it, so both
are gone. Sovereign clouds (GCC ``smba.infra.gcc.teams.microsoft.com``, GCC High/DoD ``*.teams.microsoft.us``)
are NOT supported yet.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

import frappe

# serviceUrl comes from the (verified, but still attacker-influenceable) inbound payload and is later used
# as an outbound request target carrying a bearer token, so only Bot Connector hosts are acceptable.
ALLOWED_SERVICE_HOSTS = ("smba.trafficmanager.net",)
_GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PATH_RE = re.compile(rf"/[a-z0-9-]+(?:/{_GUID})?/?")  # matched against the LOWERCASED path

REFERENCE_TTL_SECONDS = 90 * 24 * 3600
_CACHE_PREFIX = "huf_teams_ref:"
_REFERENCE_KEYS = ("serviceUrl", "conversation_id", "bot_id", "tenant_id", "channelId")


def _host_allowed(host: str) -> bool:
	return host in ALLOWED_SERVICE_HOSTS


def validate_service_url(url: Any) -> str:
	"""Return ``url`` normalised (https origin + path, no trailing slash) or raise ``ValueError``.

	https only; host must match ``ALLOWED_SERVICE_HOSTS``; no IP literals, userinfo, non-443 ports,
	query or fragment. Redirects are never followed by the sender, so a vetted host stays vetted.
	"""
	if not isinstance(url, str) or not url.strip() or url != url.strip():
		raise ValueError("Teams serviceUrl is missing or malformed")
	if "\\" in url or any(ord(c) < 33 for c in url):
		raise ValueError("Teams serviceUrl contains forbidden characters")
	try:
		parts = urlsplit(url)
		port = parts.port
	except ValueError as exc:
		raise ValueError("Teams serviceUrl is malformed") from exc
	if parts.scheme != "https":
		raise ValueError("Teams serviceUrl must use https")
	if parts.username is not None or parts.password is not None or "@" in parts.netloc:
		raise ValueError("Teams serviceUrl must not contain credentials")
	if port not in (None, 443):
		raise ValueError("Teams serviceUrl must use port 443")
	if parts.query or parts.fragment:
		raise ValueError("Teams serviceUrl must not have a query or fragment")
	if not url.isascii():
		raise ValueError("Teams serviceUrl must be ASCII")
	host = (parts.hostname or "").lower()
	if not host:
		raise ValueError("Teams serviceUrl has no host")
	try:
		ipaddress.ip_address(host.strip("[]"))
	except ValueError:
		pass
	else:
		raise ValueError("Teams serviceUrl must not be an IP address")
	if not _host_allowed(host):
		raise ValueError("Teams serviceUrl host is not an allowed Bot Connector host")
	path = parts.path.lower()
	if path not in ("", "/") and not _PATH_RE.fullmatch(path):
		raise ValueError("Teams serviceUrl path must be empty, /<region> or /<region>/<tenant-guid>")
	return f"https://{host}{path}".rstrip("/")


def reference_from_activity(activity: dict[str, Any]) -> dict[str, str]:
	"""Extract the reference fields from an inbound activity (not validated)."""
	conversation = activity.get("conversation") or {}
	recipient = activity.get("recipient") or {}
	channel_data = activity.get("channelData") or {}
	tenant = (channel_data.get("tenant") or {}).get("id") or conversation.get("tenantId") or ""
	return {
		"serviceUrl": str(activity.get("serviceUrl") or ""),
		"conversation_id": str(conversation.get("id") or ""),
		"bot_id": str(recipient.get("id") or ""),
		"tenant_id": str(tenant),
		"channelId": str(activity.get("channelId") or ""),
	}


def _cache_key(gateway_name: str, app_id: str, conversation_id: str) -> str:
	digest = hashlib.sha256(f"{gateway_name}\x00{app_id}\x00{conversation_id}".encode()).hexdigest()
	return _CACHE_PREFIX + digest


def _clean(reference: dict[str, Any]) -> dict[str, str]:
	cleaned = {key: str(reference.get(key) or "") for key in _REFERENCE_KEYS}
	cleaned["serviceUrl"] = validate_service_url(cleaned["serviceUrl"])
	return cleaned


def save_reference(gateway_name: str, app_id: str, conversation_id: str, reference: dict[str, Any]) -> None:
	"""Validate and cache the reference. Raises ``ValueError`` on a bad serviceUrl (nothing stored)."""
	if not conversation_id or not gateway_name:
		raise ValueError("Teams gateway name and conversation id are required")
	cleaned = _clean(reference)
	frappe.cache.set_value(
		_cache_key(gateway_name, app_id, conversation_id), cleaned, expires_in_sec=REFERENCE_TTL_SECONDS
	)


def _from_gateway_event(gateway_name: str, conversation_id: str) -> dict[str, str] | None:
	rows = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "conversation_id": conversation_id, "verified_sender": 1},
		fields=["raw_payload"],
		order_by="received_at desc, creation desc",
		limit_page_length=5,
	)
	for row in rows:
		payload = row.get("raw_payload")
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except ValueError:
				continue
		if not isinstance(payload, dict):
			continue
		reference = reference_from_activity(payload)
		if reference["conversation_id"] != conversation_id:
			continue
		try:
			return _clean(reference)
		except ValueError:
			continue
	return None


def get_reference(gateway_name: str, app_id: str, conversation_id: str) -> dict[str, str] | None:
	"""Cached reference, else rebuilt from the latest verified Gateway Event (and re-cached)."""
	if not conversation_id or not gateway_name:
		return None
	cached = frappe.cache.get_value(_cache_key(gateway_name, app_id, conversation_id))
	if isinstance(cached, dict) and cached.get("serviceUrl"):
		try:
			return _clean(cached)
		except ValueError:
			pass
	reference = _from_gateway_event(gateway_name, conversation_id)
	if reference:
		try:
			save_reference(gateway_name, app_id, conversation_id, reference)
		except Exception:
			frappe.log_error(title="Teams reference cache write failed")
	return reference
