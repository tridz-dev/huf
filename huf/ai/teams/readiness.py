"""Teams readiness checks for ``preview_gateway_readiness`` (provider hook ``readiness_checks``).

Offline only: no token acquisition or network call (that belongs to the diagnostics verify endpoint).
Hints name missing fields and paths, never credential values.

Drop record (operator visibility for silent drops): ``record_drop(bucket, kind)`` keeps, per Gateway (and
one global ``AUTH_BUCKET`` for inbound-auth rejections, which happen before a Gateway handle exists), a
small frappe.cache entry ``huf_teams_drops:<bucket>`` = ``{"entries": last 20 {ts, kind}, "counts":
{kind: n}, "window_start": ts}``; counts reset after 24 h. Kinds are reason codes only (no ids, names,
tokens). Read-modify-write is not atomic: concurrent drops may lose a count (visibility only).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit

import frappe

logger = logging.getLogger("huf.teams.readiness")

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
WEBHOOK_PATH = "/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
DROPS_PREFIX = "huf_teams_drops:"
AUTH_BUCKET = "__auth__"
DROPS_KEEP = 20
DROPS_WINDOW_SECONDS = 24 * 3600
_DROPS_TTL_SECONDS = 7 * 24 * 3600
_REQUIRED = (
	("app_id", "Microsoft App ID"),
	("app_password", "Microsoft App Secret"),
	("tenant_id", "Tenant ID"),
)


def _item(cid: str, label: str, done: bool, hint: str | None = None) -> dict[str, Any]:
	return {"id": cid, "label": label, "done": bool(done), "hint": None if done else hint}


def _guarded(cid: str, label: str, fn) -> dict[str, Any]:
	try:
		return fn()
	except Exception:
		logger.exception("Teams readiness check %s failed", cid)
		return _item(cid, label, False, "This check could not be evaluated; see the Error Log.")


def _stored_credentials(gateway, adapter) -> dict[str, str]:
	if adapter is not None:
		return dict(adapter._credentials())
	loader = getattr(gateway, "_load_integration_credentials", None)
	return dict(loader() or {}) if callable(loader) else {}


def _check_credentials(gateway, adapter) -> dict[str, Any]:
	label = "Teams credentials"
	creds = _stored_credentials(gateway, adapter)
	problems = []
	for key, name in _REQUIRED:
		value = str(creds.get(key) or "").strip()
		if not value:
			problems.append(f"{name} ({key}) is missing")
		elif key != "app_password" and not GUID_RE.match(value):
			problems.append(f"{name} ({key}) must be a GUID")
	if adapter is None and not problems:
		problems.append("the adapter could not be built from the stored credentials")
	if not problems:
		return _item("teams-credentials", label, True)
	return _item(
		"teams-credentials",
		label,
		False,
		"Fix the Integration Settings credentials: " + "; ".join(problems) + ".",
	)


def _public_base_url() -> str:
	try:
		from huf.ai.telegram_public_url import public_base_url

		return public_base_url()
	except Exception:
		return ""


def _webhook_url(name: str) -> str:
	return _public_base_url() + f"{WEBHOOK_PATH}?gateway_name={quote(name, safe='')}"


def _non_public_host(url: str) -> str | None:
	"""The host when ``url`` is not a public https URL Azure can call, else None."""
	parts = urlsplit(url)
	host = (parts.hostname or "").lower()
	if parts.scheme != "https" or not host:
		return host or "<none>"
	if host in ("localhost", "127.0.0.1") or host.endswith((".local", ".localhost")):
		return host
	try:
		ipaddress.ip_address(host.strip("[]"))
	except ValueError:
		return None
	return host


def _check_endpoint(gateway) -> dict[str, Any]:
	label = "Messaging endpoint"
	url = _webhook_url(str(getattr(gateway, "name", "") or "<name>"))
	enabled = bool(getattr(gateway, "is_enabled", 0))
	bad_host = _non_public_host(url)
	if bad_host is not None:
		hint = (
			f"Messaging endpoint must be a public https URL (current: {bad_host}) — "
			"set host_name in site config / a public URL"
		)
	else:
		hint = f"Paste {url} as the Messaging endpoint of your Azure Bot (HTTPS, publicly reachable), then enable this gateway."
	item = _item("teams-messaging-endpoint", label, enabled and bad_host is None, hint)
	item["endpoint_url"] = url
	return item


def _check_first_message(gateway, adapter) -> dict[str, Any]:
	found = bool(
		frappe.get_all(
			"Gateway Event",
			filters={"gateway": gateway.name, "verified_sender": 1, "conversation_id": ["!=", ""]},
			fields=["name"],
			limit_page_length=1,
		)
	)
	return _item(
		"teams-first-message",
		"Conversation reference stored",
		found,
		"Send a message to the bot in Teams so Huf can store the conversation reference "
		"(required for replies and test send).",
	)


def _check_mention(gateway) -> dict[str, Any]:
	required = bool(int(getattr(gateway, "mention_required", 0) or 0))
	return _item(
		"teams-mention-policy",
		"Mention policy",
		required,
		"Mentions are not required in rooms. Teams channels deliver only @mentions to the bot "
		"unless the app has resource-specific consent (RSC); enable 'Require mention in rooms' for predictable behaviour.",
	)


def _check_tenants(gateway, adapter) -> dict[str, Any]:
	raw = str(_stored_credentials(gateway, adapter).get("allowed_tenant_ids") or "")
	parts = [p.strip() for p in raw.split(",") if p.strip()]
	bad = [p for p in parts if not GUID_RE.match(p)]
	return _item(
		"teams-allowed-tenants",
		"Allowed tenants",
		not bad,
		f"{len(bad)} entr{'y' if len(bad) == 1 else 'ies'} in allowed_tenant_ids "
		"is not a GUID; use a comma-separated list of tenant IDs or leave it empty.",
	)


def _now() -> float:
	return time.time()


def record_drop(bucket: str, kind: str) -> None:
	"""Remember one dropped activity / auth rejection (reason code only). Never raises."""
	try:
		key = DROPS_PREFIX + str(bucket or AUTH_BUCKET)
		now = _now()
		record = frappe.cache.get_value(key)
		if (
			not isinstance(record, dict)
			or now - float(record.get("window_start") or 0) > DROPS_WINDOW_SECONDS
		):
			record = {
				"entries": (record or {}).get("entries", []) if isinstance(record, dict) else [],
				"counts": {},
				"window_start": now,
			}
		kind = str(kind)[:64]
		record["counts"][kind] = int(record["counts"].get(kind, 0)) + 1
		record["entries"] = [*record["entries"], {"ts": now, "kind": kind}][-DROPS_KEEP:]
		frappe.cache.set_value(key, record, expires_in_sec=_DROPS_TTL_SECONDS)
	except Exception:
		logger.debug("Teams drop record could not be written", exc_info=True)


def recent_drops(bucket: str) -> tuple[dict[str, int], float | None]:
	"""``(counts, last_ts)`` for drops in the last 24 h; ``({}, None)`` when none."""
	record = frappe.cache.get_value(DROPS_PREFIX + bucket)
	if not isinstance(record, dict) or not record.get("entries"):
		return {}, None
	last = max(float(e.get("ts") or 0) for e in record["entries"])
	if _now() - last > DROPS_WINDOW_SECONDS:
		return {}, None
	return dict(record.get("counts") or {}), last


def drops_summary(gateway_name: str, *, include_auth: bool = True) -> str | None:
	"""Human summary of recent drops for this gateway (plus the global auth bucket when asked), or None."""
	counts, last = recent_drops(gateway_name)
	auth_counts, auth_last = recent_drops(AUTH_BUCKET) if include_auth else ({}, None)
	if not counts and not auth_counts:
		return None
	parts = [f"{n} {kind}" for kind, n in sorted(counts.items())]
	parts += [f"{n} {kind} (all Teams gateways)" for kind, n in sorted(auth_counts.items())]
	ts = datetime.fromtimestamp(max(t for t in (last, auth_last) if t), UTC).isoformat(timespec="seconds")
	return f"Recent dropped activities: {', '.join(parts)} (last: {ts}) — see docs troubleshooting"


def _check_drops(gateway) -> dict[str, Any]:
	# Auth rejections live in a global bucket that internet scanners/forged requests can fill; they are shown
	# in the Verify connection `drops` step, not here, so they cannot make every gateway "not ready".
	summary = drops_summary(str(getattr(gateway, "name", "") or ""), include_auth=False)
	return _item("teams-recent-drops", "Recent dropped activities", summary is None, summary)


def readiness_checks(gateway, adapter) -> list[dict[str, Any]]:
	checks = (
		("teams-credentials", "Teams credentials", lambda: _check_credentials(gateway, adapter)),
		("teams-messaging-endpoint", "Messaging endpoint", lambda: _check_endpoint(gateway)),
		(
			"teams-first-message",
			"Conversation reference stored",
			lambda: _check_first_message(gateway, adapter),
		),
		("teams-mention-policy", "Mention policy", lambda: _check_mention(gateway)),
		("teams-allowed-tenants", "Allowed tenants", lambda: _check_tenants(gateway, adapter)),
		("teams-recent-drops", "Recent dropped activities", lambda: _check_drops(gateway)),
	)
	return [_guarded(cid, label, fn) for cid, label, fn in checks]
