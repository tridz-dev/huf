"""Teams readiness checks for ``preview_gateway_readiness`` (provider hook ``readiness_checks``).

Offline only: no token acquisition or network call (that belongs to the diagnostics verify endpoint).
Hints name missing fields and paths, never credential values.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import frappe

logger = logging.getLogger("huf.teams.readiness")

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
WEBHOOK_PATH = "/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
_REQUIRED = (("app_id", "Microsoft App ID"), ("app_password", "Microsoft App Secret"), ("tenant_id", "Tenant ID"))


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


def _webhook_url(name: str) -> str:
	path = f"{WEBHOOK_PATH}?gateway_name={quote(name, safe='')}"
	try:
		from huf.ai.telegram_public_url import public_base_url

		base = public_base_url()
	except Exception:
		base = ""
	return base + path


def _check_endpoint(gateway) -> dict[str, Any]:
	label = "Messaging endpoint"
	url = _webhook_url(str(getattr(gateway, "name", "") or "<name>"))
	enabled = bool(getattr(gateway, "is_enabled", 0))
	return _item(
		"teams-messaging-endpoint",
		label,
		enabled,
		f"Paste {url} as the Messaging endpoint of your Azure Bot (HTTPS, publicly reachable), then enable this gateway.",
	)


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


def readiness_checks(gateway, adapter) -> list[dict[str, Any]]:
	checks = (
		("teams-credentials", "Teams credentials", lambda: _check_credentials(gateway, adapter)),
		("teams-messaging-endpoint", "Messaging endpoint", lambda: _check_endpoint(gateway)),
		("teams-first-message", "Conversation reference stored", lambda: _check_first_message(gateway, adapter)),
		("teams-mention-policy", "Mention policy", lambda: _check_mention(gateway)),
		("teams-allowed-tenants", "Allowed tenants", lambda: _check_tenants(gateway, adapter)),
	)
	return [_guarded(cid, label, fn) for cid, label, fn in checks]
