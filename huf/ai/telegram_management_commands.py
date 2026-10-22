# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram management API: bot profile, command menus, menu button, token check and webhook control.

Gateway admins only, same permission model as ``telegram_management``. The bot token and webhook secret are read
server-side and never returned. Logic lives in pure functions over a ``TelegramBotClient`` (testable with a fake
client); the ``@frappe.whitelist`` wrappers resolve the gateway, check permission and build the client.
"""

from __future__ import annotations

from typing import Any, Callable

import frappe

from huf.ai.gateway_adapters import telegram_commands as tc
from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError
from huf.ai.telegram_management import (
	_client,
	_credentials,
	_error,
	_load_gateway,
	_safe_text,
	_webhook_url,
)

NAME_MAX = 64
ABOUT_MAX = 120  # short description (profile page "About")
DESCRIPTION_MAX = 512  # shown in an empty chat
UI_SCOPES = ("default", "all_private_chats", "all_group_chats", "all_chat_administrators")
MENU_TYPES = ("commands", "web_app", "default")


def _truthy(value: Any) -> bool:
	return str(value).strip().lower() in ("1", "true", "yes", "on")


# -- pure logic over a client -------------------------------------------------------------------


def _lang(language: str | None) -> dict[str, Any]:
	return {"language_code": language} if language else {}


def profile_get(client: Any, language: str | None = None) -> dict[str, Any]:
	kw = _lang(language)
	return {
		"name": (client.call("getMyName", kw) or {}).get("name", ""),
		"description": (client.call("getMyDescription", kw) or {}).get("description", ""),
		"short_description": (client.call("getMyShortDescription", kw) or {}).get("short_description", ""),
	}


def validate_profile(name: str | None, description: str | None, short_description: str | None) -> dict[str, str]:
	"""Fields to send (only those given), or ValueError on a limit violation."""
	out: dict[str, str] = {}
	for key, value, limit, label in (
		("name", name, NAME_MAX, "Name"),
		("description", description, DESCRIPTION_MAX, "Description"),
		("short_description", short_description, ABOUT_MAX, "About text"),
	):
		if value is None:
			continue
		value = str(value).strip()
		if len(value) > limit:
			raise ValueError(f"{label} must be at most {limit} characters")
		if key == "name" and not value:
			raise ValueError("Name cannot be empty")
		out[key] = value
	if not out:
		raise ValueError("Nothing to update")
	return out


_PROFILE_METHODS = {"name": "setMyName", "description": "setMyDescription", "short_description": "setMyShortDescription"}


def profile_set(client: Any, fields: dict[str, str], language: str | None = None) -> list[str]:
	for key, value in fields.items():
		client.call(_PROFILE_METHODS[key], {key: value, **_lang(language)})
	return list(fields)


def menu_button_payload(menu_type: str, text: str = "", url: str = "") -> dict[str, Any]:
	if menu_type not in MENU_TYPES:
		raise ValueError("Menu button type must be commands, web_app or default")
	if menu_type != "web_app":
		return {"type": menu_type}
	text, url = (text or "").strip(), (url or "").strip()
	if not text or len(text) > 64:
		raise ValueError("Button text must be 1-64 characters")
	if not url.startswith("https://"):
		raise ValueError("Web app URL must start with https://")
	return {"type": "web_app", "text": text, "web_app": {"url": url}}


def token_summary(client: Any) -> dict[str, Any]:
	me = client.get_me() or {}
	return {
		"valid": True,
		"id": me.get("id"),
		"username": me.get("username"),
		"first_name": me.get("first_name"),
		"is_bot": bool(me.get("is_bot", True)),
	}


def webhook_summary(client: Any, expected_url: str) -> dict[str, Any]:
	from huf.ai.gateway_adapters.telegram_health import check_webhook

	info = check_webhook(client, expected_url)
	info["expected_url"] = expected_url
	info["expected_allowed_updates"] = list(ALLOWED_UPDATES)
	return info


# -- wrappers -----------------------------------------------------------------------------------


def _with_client(gateway: str | None, fn: Callable[[Any, dict[str, Any], dict[str, str]], dict[str, Any]]) -> dict[str, Any]:
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	try:
		credentials = _credentials(row)
	except Exception:
		credentials = {}
	if not credentials.get("token"):
		return _error("token_missing", "Add the bot token in Settings first.")
	try:
		return {"success": True, **fn(_client(credentials), row, credentials)}
	except TelegramApiError as exc:
		return _error("telegram_error", _safe_text(exc.description, credentials))
	except ValueError as exc:
		return _error("invalid", _safe_text(exc, credentials))


@frappe.whitelist()
def get_bot_profile(gateway: str | None = None, language: str | None = None) -> dict[str, Any]:
	return _with_client(gateway, lambda c, r, cr: {"profile": profile_get(c, language), "limits": {"name": NAME_MAX, "short_description": ABOUT_MAX, "description": DESCRIPTION_MAX}})


@frappe.whitelist()
def set_bot_profile(
	gateway: str | None = None, name: str | None = None, description: str | None = None,
	short_description: str | None = None, language: str | None = None,
) -> dict[str, Any]:
	def run(c, r, cr):
		return {"updated": profile_set(c, validate_profile(name, description, short_description), language)}

	return _with_client(gateway, run)


@frappe.whitelist()
def get_commands(gateway: str | None = None, scope: str = "default", language: str | None = None) -> dict[str, Any]:
	def run(c, r, cr):
		if scope not in UI_SCOPES:
			raise ValueError("Unknown command scope")
		return {"scope": scope, "language": language or "", "commands": tc.get_commands(c, scope=scope, language_code=language or None) or []}

	return _with_client(gateway, run)


def _parse_commands(commands: Any) -> list[Any]:
	if isinstance(commands, str):
		commands = frappe.parse_json(commands)
	return list(commands or [])


@frappe.whitelist()
def set_commands(gateway: str | None = None, scope: str = "default", language: str | None = None, commands: Any = None) -> dict[str, Any]:
	def run(c, r, cr):
		if scope not in UI_SCOPES:
			raise ValueError("Unknown command scope")
		items = tc.build_commands(_parse_commands(commands))
		tc.set_commands(c, items, scope=scope, language_code=language or None)
		return {"scope": scope, "language": language or "", "count": len(items)}

	return _with_client(gateway, run)


@frappe.whitelist()
def delete_commands(gateway: str | None = None, scope: str = "default", language: str | None = None) -> dict[str, Any]:
	def run(c, r, cr):
		if scope not in UI_SCOPES:
			raise ValueError("Unknown command scope")
		tc.delete_commands(c, scope=scope, language_code=language or None)
		return {"scope": scope, "language": language or ""}

	return _with_client(gateway, run)


@frappe.whitelist()
def get_menu_button(gateway: str | None = None) -> dict[str, Any]:
	return _with_client(gateway, lambda c, r, cr: {"menu_button": c.call("getChatMenuButton", {}) or {"type": "default"}})


@frappe.whitelist()
def set_menu_button(gateway: str | None = None, type: str = "commands", text: str = "", url: str = "") -> dict[str, Any]:  # noqa: A002
	def run(c, r, cr):
		button = menu_button_payload(type, text, url)
		c.call("setChatMenuButton", {"menu_button": button})
		return {"menu_button": button}

	return _with_client(gateway, run)


@frappe.whitelist()
def check_token(gateway: str | None = None) -> dict[str, Any]:
	"""getMe only. A rejected token is a normal result (valid: false), not an error."""
	row = _load_gateway(gateway)
	if "success" in row:
		return row
	try:
		credentials = _credentials(row)
	except Exception:
		credentials = {}
	if not credentials.get("token"):
		return {"success": True, "check": {"valid": False, "reason": "No bot token is saved for this gateway."}}
	try:
		return {"success": True, "check": token_summary(_client(credentials))}
	except TelegramApiError as exc:
		return {"success": True, "check": {"valid": False, "reason": _safe_text(exc.description, credentials)}}


@frappe.whitelist()
def refresh_webhook_health(gateway: str | None = None) -> dict[str, Any]:
	return _with_client(gateway, lambda c, r, cr: {"webhook": webhook_summary(c, _webhook_url(r["name"]))})


@frappe.whitelist()
def set_webhook_now(gateway: str | None = None, confirm: Any = 0, drop_pending_updates: Any = 0) -> dict[str, Any]:
	"""Point this bot's webhook at this site. Takes over delivery for the bot, so ``confirm=1`` is required."""
	if not _truthy(confirm):
		return _error("confirm_required", "Setting the webhook takes over message delivery for this bot. Confirm to continue.")

	def run(c, r, cr):
		secret = cr.get("webhook_secret")
		if not secret:
			raise ValueError("Add a webhook secret in Settings first.")
		url = _webhook_url(r["name"])
		c.set_webhook(url, secret_token=secret, allowed_updates=ALLOWED_UPDATES, drop_pending_updates=_truthy(drop_pending_updates))
		return {"webhook": webhook_summary(c, url)}

	return _with_client(gateway, run)


@frappe.whitelist()
def delete_webhook_now(gateway: str | None = None, confirm: Any = 0, drop_pending_updates: Any = 0) -> dict[str, Any]:
	"""Stop delivery to this site. Needs ``confirm=1``."""
	if not _truthy(confirm):
		return _error("confirm_required", "Deleting the webhook stops this bot receiving messages here. Confirm to continue.")

	def run(c, r, cr):
		c.delete_webhook(drop_pending_updates=_truthy(drop_pending_updates))
		return {"webhook": webhook_summary(c, _webhook_url(r["name"]))}

	return _with_client(gateway, run)
