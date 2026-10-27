"""Slack setup wizard backend: app manifest, connection checks, test DM.

Every endpoint requires System Manager or write permission on the Gateway.
Nothing secret is returned, cached or logged.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import frappe

from huf.ai.gateways import slack_api
from huf.ai.gateways.slack_api import SlackApiError
from huf.ai.gateways.slack_context import get_gateway_credential, get_slack_api

BOT_EVENTS = ["message.channels", "message.groups", "message.im", "message.mpim", "app_mention", "reaction_added"]
EVENTS_PATH = "/api/method/huf.ai.gateways.slack_events.handle_slack_event"
# Endpoint is created by a later work package (interactivity / buttons).
INTERACTIVITY_PATH = "/api/method/huf.ai.gateways.slack_interactivity.handle_slack_interaction"

URL_VERIFIED_KEY = "huf_slack_url_verified:{}"
VERIFY_KEY = "huf_slack_verify:{}"
VERIFY_TTL = 60 * 60 * 24

_USER_ID_RE = re.compile(r"^[UW][A-Z0-9]{2,20}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_permission(gateway_name: str):
	"""Return the Gateway doc if the caller may administer it; otherwise raise PermissionError."""
	allowed = "System Manager" in (frappe.get_roles() or [])
	if not allowed:
		allowed = bool(frappe.has_permission("Gateway", "write", doc=gateway_name))
	if not allowed:
		frappe.throw("You do not have permission to manage this gateway.", frappe.PermissionError)
	gateway = frappe.get_doc("Gateway", gateway_name)
	if getattr(gateway, "provider", None) != "Slack":
		frappe.throw("This gateway is not a Slack gateway.")
	return gateway


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _site_url() -> str:
	return str(frappe.utils.get_url()).rstrip("/")


def _build_manifest(gateway) -> dict:
	base = _site_url()
	name = gateway.name
	display = (getattr(gateway, "gateway_name", None) or "Huf")[:35]
	return {
		"_metadata": {"major_version": 1, "minor_version": 1},
		"display_information": {
			"name": display,
			"description": "Chat with your Huf agents in Slack",
		},
		"features": {
			"app_home": {
				"home_tab_enabled": False,
				"messages_tab_enabled": True,
				"messages_tab_read_only_enabled": False,
			},
			"bot_user": {"display_name": display, "always_online": False},
			"shortcuts": [
				{
					"name": "Ask Huf about this",
					"type": "message",
					"callback_id": "huf_ask_message",
					"description": "Ask Huf to act on this message",
				}
			],
		},
		"oauth_config": {"scopes": {"bot": list(slack_api.REQUIRED_BOT_SCOPES)}},
		"settings": {
			"event_subscriptions": {
				"request_url": f"{base}{EVENTS_PATH}?gateway_name={_quote(name)}",
				"bot_events": list(BOT_EVENTS),
			},
			# The interactivity endpoint is built by a later work package; Slack only
			# calls it once buttons are used.
			"interactivity": {
				"is_enabled": True,
				"request_url": f"{base}{INTERACTIVITY_PATH}?gateway_name={_quote(name)}",
			},
			"org_deploy_enabled": False,
			"socket_mode_enabled": False,
			"token_rotation_enabled": False,
		},
	}


def _quote(value: str) -> str:
	from urllib.parse import quote

	return quote(str(value), safe="")


@frappe.whitelist()
def get_slack_manifest(gateway_name: str) -> dict:
	gateway = _check_permission(gateway_name)
	return _build_manifest(gateway)


def _request_url_confirmed(gateway_name: str) -> bool:
	"""Slack confirmed the URL (cache flag), or has already delivered a signed event.

	The cache flag disappears on a clear-cache or deploy; any received event proves the URL works.
	"""
	if frappe.cache().get_value(URL_VERIFIED_KEY.format(gateway_name)):
		return True
	try:
		last = frappe.db.get_value("Gateway", gateway_name, "last_event_at")
		return isinstance(last, (str, datetime)) and bool(last)
	except Exception:
		return False


def _check(id_, ok, title, detail, fix="", informational=False):
	row = {"id": id_, "ok": bool(ok), "plain_title": title, "detail": detail, "how_to_fix": fix}
	if informational:
		row["informational"] = True
	return row


def _direct_policy_check(gateway) -> dict:
	try:
		is_open = getattr(gateway, "direct_policy", None) == "Open"
	except Exception:
		is_open = False
	row = _check(
		"direct_policy", is_open, "People can connect their own account",
		"Anyone who messages the bot privately is asked to connect their account first; nothing runs until they do."
		if is_open else "Direct messages are not open, so people who have not been approved cannot reach the connect prompt.",
		"" if is_open else
		"Set the access policy to Open so people can connect their own account, or add each person to the access list first.",
		informational=True,  # a recommendation: never blocks "ready"
	)
	row["status"] = "pass" if is_open else "warn"
	return row


def _run_checks(gateway) -> list[dict]:
	checks: list[dict] = []
	token = get_gateway_credential(gateway, "token")
	kind = slack_api.token_kind(token) if token else ""

	checks.append(_check(
		"token_present", bool(token), "Bot token added",
		"A bot token is saved." if token else "No bot token is saved yet.",
		"" if token else "Open the Credentials tab and paste the Bot User OAuth Token from Slack (OAuth & Permissions).",
	))

	is_bot = kind == "bot"
	if not token:
		kind_detail, kind_fix = "Add a token first.", "Add the bot token, then check again."
	elif is_bot:
		kind_detail, kind_fix = "This is a bot token (starts with xoxb-).", ""
	elif kind == "user":
		kind_detail = (
			"This is a personal user token (xoxp-). It can read everything you can read in Slack, "
			"so Huf refuses to use it."
		)
		kind_fix = "In Slack, open OAuth & Permissions and copy the Bot User OAuth Token (starts with xoxb-) instead."
	else:
		kind_detail = "This does not look like a Slack bot token."
		kind_fix = "Copy the Bot User OAuth Token (starts with xoxb-) from OAuth & Permissions in Slack."
	checks.append(_check("token_kind", is_bot, "Token is a bot token", kind_detail, kind_fix))

	info = None
	auth_error = ""
	if is_bot:
		try:
			info = slack_api.inspect_token(get_slack_api(gateway))
		except SlackApiError as e:
			auth_error = e.error_code
		except ValueError:
			auth_error = "no_token"
	if info:
		who = info.get("team") or "your workspace"
		checks.append(_check("auth_test", True, "Slack accepts the token", f"Connected to {who}.", ""))
	else:
		checks.append(_check(
			"auth_test", False, "Slack accepts the token",
			f"Slack did not accept the token ({auth_error})." if auth_error else "Not checked yet.",
			"Reinstall the app to your workspace and paste the new Bot User OAuth Token." if auth_error
			else "Fix the token first, then check again.",
		))

	if info:
		missing = info.get("missing_scopes") or []
		checks.append(_check(
			"scopes", not missing, "Required permissions granted",
			"All required permissions are granted." if not missing else "Missing: " + ", ".join(missing),
			"" if not missing else "Add the missing scopes under OAuth & Permissions, reinstall the app, then check again.",
		))
	else:
		checks.append(_check("scopes", False, "Required permissions granted", "Not checked yet.",
			"Fix the token first, then check again."))

	secret = get_gateway_credential(gateway, "signing_secret")
	checks.append(_check(
		"signing_secret", bool(secret), "Signing secret added",
		"A signing secret is saved." if secret else "No signing secret is saved yet.",
		"" if secret else "Copy the Signing Secret from Basic Information in Slack into the Credentials tab.",
	))

	verified = _request_url_confirmed(gateway.name)
	checks.append(_check(
		"request_url", bool(verified), "Slack confirmed the Request URL",
		"Slack has confirmed the events address." if verified else "Slack has not confirmed the events address yet.",
		"" if verified else (
			"In Slack, open Event Subscriptions, click Save Request URL (or Retry), "
			"then check again here."
		),
	))

	checks.append(_direct_policy_check(gateway))

	checks.append(_check(
		"slack_connect", True, "Shared channels (Slack Connect)",
		"Channels shared with other organizations are not supported. Huf works in channels and DMs inside your own workspace.",
		"", informational=True,
	))
	return checks


@frappe.whitelist()
def verify_slack_setup(gateway_name: str) -> list[dict]:
	gateway = _check_permission(gateway_name)
	checks = _run_checks(gateway)
	required = [c for c in checks if not c.get("informational")]
	frappe.cache().set_value(
		VERIFY_KEY.format(gateway_name),
		{"checks": checks, "all_ok": all(c["ok"] for c in required), "checked_at": _now()},
		expires_in_sec=VERIFY_TTL,
	)
	return checks


@frappe.whitelist()
def get_slack_setup_status(gateway_name: str) -> dict:
	"""Last cached verify result (no Slack call) so the UI and readiness can stay truthful."""
	_check_permission(gateway_name)
	cached = frappe.cache().get_value(VERIFY_KEY.format(gateway_name)) or {}
	return {
		"verified": bool(cached.get("all_ok")),
		"checked_at": cached.get("checked_at"),
		"checks": cached.get("checks") or [],
		"request_url_verified": _request_url_confirmed(gateway_name),
	}


@frappe.whitelist()
def send_test_dm(gateway_name: str, slack_user_id: str | None = None, email: str | None = None) -> dict:
	gateway = _check_permission(gateway_name)
	slack_user_id = (slack_user_id or "").strip()
	email = (email or "").strip()
	if bool(slack_user_id) == bool(email):
		frappe.throw("Enter either a Slack member ID or an email address.")
	if slack_user_id and not _USER_ID_RE.match(slack_user_id):
		frappe.throw("That does not look like a Slack member ID (for example U012ABCDE).")
	if email and not _EMAIL_RE.match(email):
		frappe.throw("That does not look like a valid email address.")

	token = get_gateway_credential(gateway, "token")
	if slack_api.token_kind(token) != "bot":
		frappe.throw("Add a valid Slack bot token in the Credentials tab first.")
	api = get_slack_api(gateway)
	try:
		user_id = slack_user_id or api.users_lookup_by_email(email)
		if not user_id:
			frappe.throw("Slack could not find a member with that email address.")
		channel = api.conversations_open([user_id])
		if not channel:
			frappe.throw("Slack did not open a direct message with that person.")
		api.post_message(channel, "Huf is connected")
	except SlackApiError as e:
		frappe.throw(f"Slack could not send the message ({e.error_code}).")
	return {"ok": True, "user_id": user_id}
