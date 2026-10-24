# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram bot health checks: pure functions over ``TelegramBotClient`` (no Frappe).

``check_bot`` reports getMe capability flags, ``check_webhook`` reports getWebhookInfo delivery
state, and ``readiness`` turns both into an ordered list of pass/fail checks with operator hints.
Errors from the Bot API are caught and reported as failed checks; the client already redacts the
bot token from every message, so nothing returned here carries it.
"""

from __future__ import annotations

import time
from typing import Any, Mapping
from urllib.parse import urlparse

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError, TelegramBotClient

BOT_FLAGS = (
	"can_join_groups",
	"can_connect_to_business",
	"supports_guest_queries",
	"supports_join_request_queries",
	"has_topics_enabled",
	"supports_inline_queries",
	"can_read_all_group_messages",
	"has_main_web_app",
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
		# Kinds the gateway handles that this registration does not deliver (registered before they were added).
		"missing_updates": [k for k in ALLOWED_UPDATES if k not in (allowed or ())],
	}


def check_menu_button(client: TelegramBotClient) -> dict[str, Any]:
	"""getChatMenuButton (the bot-wide default) as ``{type, url}``; ``url`` is only set for a Mini App button."""
	button = client.call("getChatMenuButton", {})
	if not isinstance(button, Mapping):
		button = {}
	web_app = button.get("web_app")
	url = str(web_app.get("url") or "") if isinstance(web_app, Mapping) else ""
	return {"type": str(button.get("type") or "default"), "url": url}


def _age(epoch: Any, now: float | None = None) -> str:
	"""'4 min ago' style age of a unix timestamp; empty when unknown."""
	try:
		seconds = max(0, int((time.time() if now is None else now) - float(epoch)))
	except (TypeError, ValueError):
		return ""
	if seconds < 90:
		return "just now"
	if seconds < 5400:
		return f"{round(seconds / 60)} min ago"
	if seconds < 129600:
		return f"{round(seconds / 3600)} h ago"
	return f"{round(seconds / 86400)} days ago"


def _last_error_text(hook: Mapping[str, Any]) -> str:
	"""'(last error 3 min ago: <message>)' for the hints, empty when Telegram reports none."""
	when = _age(hook.get("last_error_date"))
	message = hook.get("last_error_message") or ""
	if not when and not message:
		return ""
	return (
		" Last error " + " ".join(p for p in (when + ":" if when and message else when, message) if p) + "."
	)


def probe(client: TelegramBotClient, expected_url: str) -> dict[str, Any]:
	"""getMe and getWebhookInfo once each: ``bot`` / ``hook`` dicts, or ``bot_error`` / ``hook_error`` text."""
	out: dict[str, Any] = {"bot": None, "bot_error": "", "hook": None, "hook_error": ""}
	try:
		out["bot"] = check_bot(client)
	except TelegramApiError as exc:
		out["bot_error"] = exc.description
	try:
		out["hook"] = check_webhook(client, expected_url)
	except TelegramApiError as exc:
		out["hook_error"] = exc.description
	return out


def readiness(client: TelegramBotClient, expected_url: str) -> list[dict[str, Any]]:
	"""Ordered pass/fail checks: id, label, ok, hint. Never raises on Bot API errors."""
	return readiness_from(probe(client, expected_url))


def readiness_from(found: Mapping[str, Any]) -> list[dict[str, Any]]:
	"""The pass/fail checks for a ``probe`` result."""
	checks: list[dict[str, Any]] = []

	def add(check_id: str, label: str, ok: bool, hint: str) -> None:
		checks.append({"id": check_id, "label": label, "ok": bool(ok), "hint": "" if ok else hint})

	bot, hook = found["bot"], found["hook"]
	if found["bot_error"]:
		add(
			"bot_reachable",
			"Telegram accepts the bot token",
			False,
			f"Telegram rejected the bot token: {found['bot_error']}",
		)
	else:
		add(
			"bot_reachable",
			"Telegram accepts the bot token",
			bot.get("id") is not None,
			"Telegram did not return the bot, check the token",
		)
	if hook is None:
		add(
			"webhook_info",
			"Connection to Telegram can be read",
			False,
			f"Telegram could not be reached: {found['hook_error']}",
		)
		return checks

	add(
		"webhook_url",
		"Telegram sends messages to this site",
		hook["url_matches"],
		"Connect to Telegram again so messages come to this site",
	)
	add(
		"webhook_error",
		"Messages are delivered without errors",
		hook["last_error_date"] is None,
		f"Telegram reports: {hook['last_error_message'] or 'delivery error'}"
		+ (f" ({_age(hook['last_error_date'])})" if _age(hook["last_error_date"]) else ""),
	)
	add(
		"webhook_pending",
		"No messages are waiting",
		hook["pending_update_count"] <= MAX_HEALTHY_PENDING_UPDATES,
		f"{hook['pending_update_count']} messages are waiting and are not being picked up."
		+ _last_error_text(hook),
	)
	missing = hook["missing_updates"]
	add(
		"webhook_allowed_updates",
		"Telegram sends every message type",
		hook["allowed_updates_ok"],
		"Telegram is not sending these message types: "
		+ (", ".join(missing) if hook["allowed_updates_present"] else "some message types")
		+ ". Connect to Telegram again to turn them on",
	)
	if bot is not None:
		add(
			"bot_identity",
			"Bot has a username",
			bool(bot.get("username")),
			"Bot has no username; set one in BotFather",
		)
	return checks


# Optional-feature rows: (id, label, bot flag, features key, hint with the exact fix). The row is "off" when the
# feature is not in use, "pass" when the flag is set, and "warn" (never a health failure) when it is in use but
# the flag is missing.
_FLAG_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
	(
		"inline_mode",
		"Inline mode",
		"supports_inline_queries",
		"inline",
		"Turn on inline mode in BotFather: send /setinline, pick this bot and give it a placeholder text.",
	),
	(
		"group_privacy",
		"Bot sees all group messages",
		"can_read_all_group_messages",
		"group_open",
		"Groups are open without a mention, but the bot only sees mentions and commands. In BotFather send "
		"/setprivacy and choose Disable, then remove the bot from each group and add it again.",
	),
	(
		"join_groups",
		"Bot can be added to groups",
		"can_join_groups",
		"groups",
		"Groups are on, but the bot cannot be added to them. In BotFather send /setjoingroups and choose Enable.",
	),
	(
		"business_mode",
		"Business accounts",
		"can_connect_to_business",
		"business",
		"Business chats are on, but the bot cannot connect to a Business account. In BotFather open Bot "
		"Settings, turn on Business Mode, and connect it from a Telegram Premium account.",
	),
	(
		"guest_mode",
		"Guest questions",
		"supports_guest_queries",
		"guest",
		"Guests are allowed, but the bot cannot receive guest questions. Turn on guest mode for this bot in BotFather.",
	),
	(
		"join_requests",
		"Join request review",
		"supports_join_request_queries",
		"join_requests",
		"Join requests are handled here, but the bot does not receive them. Turn on join request queries for "
		"this bot in BotFather.",
	),
)


def _host(url: str) -> str:
	return (urlparse(url).hostname or "").lower()


def capability_checks(
	bot: Mapping[str, Any] | None,
	features: Mapping[str, bool],
	menu: Mapping[str, Any] | None = None,
	site_host: str = "",
) -> list[dict[str, Any]]:
	"""Optional-feature rows with ``state`` pass / warn / off; none of them ever counts as a failure.

	``features`` says which features this gateway uses (inline, groups, group_open, business, guest,
	join_requests). Without a readable getMe (``bot`` None) nothing can be judged, so no rows are returned.
	"""
	if bot is None:
		return []
	rows: list[dict[str, Any]] = []

	def add(check_id: str, label: str, used: bool, ok: bool, hint: str) -> None:
		state = "off" if not used else ("pass" if ok else "warn")
		rows.append(
			{
				"id": check_id,
				"label": label,
				"ok": state != "warn",
				"state": state,
				"hint": hint if state == "warn" else "",
				"level": "warn",
			}
		)

	for check_id, label, flag, feature, hint in _FLAG_ROWS:
		add(check_id, label, bool(features.get(feature)), bool(bot.get(flag)), hint)

	menu_url = (menu or {}).get("url") or ""
	mini_app = bool(menu_url) or bool(bot.get("has_main_web_app"))
	menu_host = _host(menu_url)
	add(
		"mini_app",
		"Mini App button",
		mini_app,
		not menu_url or not site_host or menu_host == site_host.lower(),
		f"The bot's menu button opens {menu_host}, not this site ({site_host}). Update the menu button.",
	)
	return rows
