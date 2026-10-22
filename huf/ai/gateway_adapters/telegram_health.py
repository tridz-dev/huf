# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram bot health checks: pure functions over ``TelegramBotClient`` (no Frappe).

``check_bot`` reports getMe capability flags, ``check_webhook`` reports getWebhookInfo delivery
state, and ``readiness`` turns both into an ordered list of pass/fail checks with operator hints.
Errors from the Bot API are caught and reported as failed checks; the client already redacts the
bot token from every message, so nothing returned here carries it.
"""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError, TelegramBotClient

BOT_FLAGS = (
	"can_join_groups",
	"can_connect_to_business",
	"supports_guest_queries",
	"supports_join_request_queries",
	"has_topics_enabled",
)

# A backlog above this means the webhook is not draining (the handler is failing or too slow).
MAX_HEALTHY_PENDING_UPDATES = 100


def check_bot(client: TelegramBotClient) -> dict[str, Any]:
	"""getMe as a plain dict: identity plus the capability flags the gateway branches on."""
	me = client.get_me()
	if not isinstance(me, Mapping):
		me = {}
	result: dict[str, Any] = {"id": me.get("id"), "username": me.get("username")}
	for flag in BOT_FLAGS:
		result[flag] = bool(me.get(flag, False))
	return result


def check_webhook(client: TelegramBotClient, expected_url: str) -> dict[str, Any]:
	"""getWebhookInfo as a plain dict, with whether the registered URL matches ``expected_url``."""
	info = client.get_webhook_info()
	if not isinstance(info, Mapping):
		info = {}
	url = str(info.get("url") or "")
	allowed = info.get("allowed_updates")
	return {
		"url": url,
		"url_matches": bool(url) and url == (expected_url or ""),
		"pending_update_count": int(info.get("pending_update_count") or 0),
		"last_error_date": info.get("last_error_date"),
		"last_error_message": info.get("last_error_message") or "",
		"allowed_updates": list(allowed) if isinstance(allowed, (list, tuple)) else None,
		"allowed_updates_present": isinstance(allowed, (list, tuple)) and bool(allowed),
		"allowed_updates_ok": isinstance(allowed, (list, tuple)) and set(ALLOWED_UPDATES) <= set(allowed),
	}


def readiness(client: TelegramBotClient, expected_url: str) -> list[dict[str, Any]]:
	"""Ordered pass/fail checks: id, label, ok, hint. Never raises on Bot API errors."""
	checks: list[dict[str, Any]] = []

	def add(check_id: str, label: str, ok: bool, hint: str) -> None:
		checks.append({"id": check_id, "label": label, "ok": bool(ok), "hint": "" if ok else hint})

	try:
		bot = check_bot(client)
	except TelegramApiError as exc:
		add("bot_reachable", "Bot token accepted (getMe)", False, f"getMe failed: {exc.description}")
		bot = None
	else:
		add("bot_reachable", "Bot token accepted (getMe)", bot.get("id") is not None, "getMe returned no bot id")

	try:
		hook = check_webhook(client, expected_url)
	except TelegramApiError as exc:
		add("webhook_info", "Webhook info readable (getWebhookInfo)", False, f"getWebhookInfo failed: {exc.description}")
		return checks

	add("webhook_url", "Webhook URL points at this site", hook["url_matches"], "Run the webhook setup action for this site")
	add(
		"webhook_error",
		"No recent delivery error",
		hook["last_error_date"] is None,
		f"Telegram reports: {hook['last_error_message'] or 'delivery error'}",
	)
	add(
		"webhook_pending",
		"Pending update backlog is small",
		hook["pending_update_count"] <= MAX_HEALTHY_PENDING_UPDATES,
		f"{hook['pending_update_count']} updates are waiting; check that the webhook handler responds",
	)
	add(
		"webhook_allowed_updates",
		"allowed_updates includes the gateway's update types",
		hook["allowed_updates_ok"],
		"Re-run webhook setup so allowed_updates lists every type the gateway handles",
	)
	if bot is not None:
		add(
			"bot_identity",
			"Bot identity resolved",
			bool(bot.get("username")),
			"Bot has no username; set one in BotFather",
		)
	return checks
