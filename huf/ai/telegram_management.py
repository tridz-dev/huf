# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram management API for the Overview page: masked overview and live health per Gateway.

Gateway admins only (same model as ``whatsapp_management``). The bot token and webhook secret are
read server-side to call the Bot API and are never returned; the client only sees whether they are
present. Pure helpers (``build_overview``, ``build_health``) take plain data so they can be unit tested.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import frappe
from frappe import _

from huf.ai.telegram_public_url import public_base_url

ADMIN_ROLES = ("System Manager", "Huf Admin")
TELEGRAM_PROVIDER = "Telegram"

_GATEWAY_FIELDS = [
	"name",
	"provider",
	"is_enabled",
	"integration_settings",
	"last_event_at",
	"last_error",
	"telegram_inline_enabled",
	"telegram_inline_feedback_enabled",
	"typing_indicator",
]

CAPABILITY_FLAGS = (
	"can_join_groups",
	"can_connect_to_business",
	"supports_guest_queries",
	"supports_join_request_queries",
	"has_topics_enabled",
)


def _error(code: str, message: str = "") -> dict[str, Any]:
	out: dict[str, Any] = {"success": False, "error": code}
	if message:
		out["message"] = message
	return out


def _is_admin() -> bool:
	return bool(set(frappe.get_roles() or []).intersection(ADMIN_ROLES))


def _can_manage_integrations() -> bool:
	if _is_admin():
		return True
	try:
		from huf.permissions import has_capability

		return bool(has_capability(frappe.session.user, "system.integrations.manage"))
	except Exception:
		return False


def _require_gateway_admin(gateway: str) -> None:
	if not (_can_manage_integrations() or frappe.has_permission("Gateway", "write", doc=gateway)):
		raise frappe.PermissionError(_("Not permitted to manage this gateway"))


def _webhook_url(gateway_name: str) -> str:
	return (
		f"{public_base_url()}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
		f"?gateway_name={quote(gateway_name, safe='')}"
	)


def _load_gateway(gateway: str | None):
	"""The Telegram Gateway row, or an error dict. Permission is checked before existence leaks."""
	if not gateway:
		return _error("gateway_required", "Choose a Telegram gateway.")
	_require_gateway_admin(gateway)
	rows = frappe.get_all(
		"Gateway",
		filters={"provider": TELEGRAM_PROVIDER, "name": gateway},
		fields=_GATEWAY_FIELDS,
		limit_page_length=1,
	)
	if not rows:
		return _error("not_found", "Gateway not found.")
	return dict(rows[0])


def _credentials(gateway: dict[str, Any]) -> dict[str, str]:
	from huf.ai.gateway_webhook import _gateway_credentials

	return _gateway_credentials(frappe.get_doc("Gateway", gateway["name"]))


def _client(credentials: dict[str, str]):
	from huf.ai.gateway_adapters.telegram_client import TelegramBotClient, truthy_flag

	return TelegramBotClient(
		credentials.get("token", ""), test_environment=truthy_flag(credentials.get("test_environment"))
	)


def credential_presence(credentials: dict[str, str]) -> dict[str, bool]:
	return {
		"token_present": bool(credentials.get("token")),
		"webhook_secret_present": bool(credentials.get("webhook_secret")),
	}


def _safe_text(value: Any, credentials: dict[str, str]) -> str:
	"""Error text with any credential value scrubbed (defence in depth; the client already redacts)."""
	text = str(value or "")
	for secret in credentials.values():
		if secret and secret in text:
			text = text.replace(secret, "***")
	return text


def build_overview(
	gateway: dict[str, Any],
	presence: dict[str, bool],
	bot: dict[str, Any] | None,
	bot_error: str,
	webhook_url: str,
) -> dict[str, Any]:
	"""Masked, client-safe overview payload."""
	return {
		"name": gateway["name"],
		"enabled": bool(gateway.get("is_enabled")),
		"webhook_url": webhook_url,
		"token_present": presence["token_present"],
		"webhook_secret_present": presence["webhook_secret_present"],
		"last_event_at": str(gateway["last_event_at"]) if gateway.get("last_event_at") else None,
		"last_error": gateway.get("last_error") or None,
		"bot": bot,
		"bot_error": bot_error or None,
		"typing": build_typing(gateway),
	}


def _checklist(
	enabled: bool, presence: dict[str, bool], checks: dict[str, bool], has_events: bool
) -> list[dict[str, str]]:
	def state(done: bool, blocked: bool = False) -> str:
		return "done" if done else ("blocked" if blocked else "todo")

	token_ok = checks.get("bot_reachable", False)
	return [
		{
			"code": "bot_token",
			"state": state(
				presence["token_present"] and token_ok,
				presence["token_present"] and not token_ok and "bot_reachable" in checks,
			),
		},
		{"code": "webhook_secret", "state": state(presence["webhook_secret_present"])},
		{
			"code": "webhook",
			"state": state(checks.get("webhook_url", False) and checks.get("webhook_allowed_updates", False)),
		},
		{"code": "enabled", "state": state(enabled)},
		{"code": "first_message", "state": state(has_events)},
	]


INLINE_FEEDBACK_FIX = "In BotFather send /setinlinefeedback and choose Enabled"


def inline_feedback_check(gateway: dict[str, Any]) -> dict[str, Any] | None:
	"""Warn-level row; never changes the overall health. None when inline mode is off."""
	if not int(gateway.get("telegram_inline_enabled", 1) or 0):
		return None
	from huf.ai.gateway_adapters import telegram_inline

	ok = bool(int(gateway.get("telegram_inline_feedback_enabled") or 0)) or telegram_inline.feedback_seen(
		gateway["name"]
	)
	return {
		"id": "inline_feedback",
		"label": "Inline feedback",
		"ok": ok,
		"hint": "" if ok else INLINE_FEEDBACK_FIX,
		"level": "warn",
	}


def build_health(
	gateway: dict[str, Any],
	presence: dict[str, bool],
	readiness_checks: list[dict[str, Any]],
	pending_update_count: int | None = None,
) -> dict[str, Any]:
	"""Health state, checklist and the raw readiness checks (hints are operator text, token-free)."""
	by_id = {c["id"]: bool(c["ok"]) for c in readiness_checks}
	enabled = bool(gateway.get("is_enabled"))
	has_events = bool(gateway.get("last_event_at"))
	checklist = _checklist(enabled, presence, by_id, has_events)
	failing = [c for c in readiness_checks if not c["ok"]]
	if not presence["token_present"] or not presence["webhook_secret_present"]:
		health = "not_set_up"
	elif not enabled:
		health = "disabled"
	elif by_id.get("bot_reachable") is False:
		health = "blocked"
	elif failing:
		health = "degraded"
	elif not has_events:
		health = "not_set_up"
	else:
		health = "healthy"
	checks = [
		{"id": c["id"], "label": c["label"], "ok": bool(c["ok"]), "hint": c.get("hint") or ""}
		for c in readiness_checks
	]
	inline_check = inline_feedback_check(gateway)
	if inline_check:
		checks.append(inline_check)
	return {
		"name": gateway["name"],
		"enabled": enabled,
		"health": health,
		"checks": checks,
		"checklist": checklist,
		"pending_update_count": pending_update_count,
		"last_event_at": str(gateway["last_event_at"]) if gateway.get("last_event_at") else None,
	}


def build_typing(gateway: dict[str, Any]) -> dict[str, Any] | None:
	"""Typing indicator counters for the Overview line; None when the gateway's typing indicator is off."""
	if not int(gateway.get("typing_indicator") or 0):
		return None
	from huf.ai.gateway_adapters import telegram_typing_metrics

	return telegram_typing_metrics.read(gateway["name"])


@frappe.whitelist()
def get_telegram_overview(gateway: str | None = None) -> dict[str, Any]:
	"""Masked overview of one Telegram Gateway, including the bot's capability flags (live getMe)."""
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	credentials: dict[str, str] = {}
	bot: dict[str, Any] | None = None
	bot_error = ""
	try:
		credentials = _credentials(row)
	except Exception as exc:
		bot_error = _safe_text(exc, credentials)
	presence = credential_presence(credentials)
	if presence["token_present"]:
		from huf.ai.gateway_adapters.telegram_client import TelegramApiError
		from huf.ai.gateway_adapters.telegram_health import check_bot

		try:
			bot = check_bot(_client(credentials))
		except TelegramApiError as exc:
			bot_error = _safe_text(exc.description, credentials)
		except Exception as exc:
			bot_error = _safe_text(exc, credentials)
	return {
		"success": True,
		"gateway": build_overview(row, presence, bot, bot_error, _webhook_url(row["name"])),
	}


@frappe.whitelist()
def get_telegram_health(gateway: str | None = None) -> dict[str, Any]:
	"""Live readiness (getMe + getWebhookInfo) for one Telegram Gateway."""
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	credentials: dict[str, str] = {}
	try:
		credentials = _credentials(row)
	except Exception:
		credentials = {}
	presence = credential_presence(credentials)
	checks: list[dict[str, Any]] = []
	pending: int | None = None
	if presence["token_present"]:
		from huf.ai.gateway_adapters.telegram_health import check_webhook, readiness

		client = _client(credentials)
		url = _webhook_url(row["name"])
		checks = readiness(client, url)
		try:
			pending = check_webhook(client, url)["pending_update_count"]
		except Exception:
			pending = None
	for c in checks:
		c["hint"] = _safe_text(c.get("hint"), credentials)
	payload = build_health(row, presence, checks, pending)
	payload["typing"] = build_typing(row)
	return {"success": True, "gateway": payload}


@frappe.whitelist()
def list_telegram_gateways() -> dict[str, Any]:
	"""Telegram gateways the caller may manage, for the page's gateway switcher (names and state only)."""
	if not _can_manage_integrations():
		raise frappe.PermissionError(_("Not permitted to manage gateways"))
	rows = frappe.get_all(
		"Gateway",
		filters={"provider": TELEGRAM_PROVIDER},
		fields=["name", "is_enabled", "last_event_at"],
		limit_page_length=100,
	)
	return {
		"success": True,
		"gateways": [
			{
				"name": r["name"],
				"enabled": bool(r.get("is_enabled")),
				"has_events": bool(r.get("last_event_at")),
			}
			for r in rows or []
		],
	}
