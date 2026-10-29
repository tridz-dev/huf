# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Test connection for Gmail, Slack, Google Drive and Google Sheets.

Makes one harmless read-only call (Gmail users.getProfile, Slack auth.test, Drive about.get;
Sheets only mints a token) and answers Connected / Rejected with plain copy. Never sends mail,
never stores anything and never returns credential values.
"""

import json
import re
import time

import frappe
import httpx
from frappe import _
from frappe.utils import now_datetime

from huf.ai.tools.integration.provider_errors import (
	ProviderCredentialError,
	check_google_response,
	mint_google_access_token,
	slack_error_message,
)

GOOGLE_KEYS = ("client_id", "client_secret", "refresh_token")
SERVICE_KEYS = {
	"gmail": GOOGLE_KEYS,
	"google_drive": GOOGLE_KEYS,
	"google_sheets": GOOGLE_KEYS,
	"slack": ("token",),
}
LABELS = {"gmail": "Gmail", "google_drive": "Google Drive", "google_sheets": "Google Sheets", "slack": "Slack"}
KEY_NAMES = {
	"client_id": "the client ID",
	"client_secret": "the client secret",
	"refresh_token": "the refresh token",
	"token": "the bot token",
}
ALLOWED_ROLES = ("System Manager", "Huf Manager")
# Seconds the Recipients tab / flow step may wait for Slack before it shows an error with a retry.
CHANNEL_LIST_TIMEOUT = 10
CHANNEL_LIST_BUDGET = 20


def _list_of(names: list[str]) -> str:
	if len(names) <= 1:
		return "".join(names)
	return ", ".join(names[:-1]) + " and " + names[-1]


def _missing_error(service: str, creds: dict) -> "ProviderCredentialError | None":
	"""Nothing (or not everything) saved: told apart from credentials the provider refused."""
	missing = [k for k in SERVICE_KEYS[service] if not creds.get(k)]
	if not missing:
		return None
	if len(missing) == len(SERVICE_KEYS[service]):
		message = f"No credentials saved yet. Add {_list_of([KEY_NAMES[k] for k in missing])} first."
	else:
		message = f"Some credentials are missing: add {_list_of([KEY_NAMES[k] for k in missing])}."
	return ProviderCredentialError(message, kind="missing")


def _on_this_screen(label: str, message: str) -> str:
	"""The provider copy ends with "Reconnect X in Integrations."; on the Integrations screen that is a button, so the sentence is dropped."""
	return re.sub(rf"\s*Reconnect {re.escape(label)} in Integrations\.$", "", message)


def _resolve_credentials(service: str, setting: str | None, provided: dict) -> dict:
	keys = SERVICE_KEYS[service]
	creds: dict = {}
	if setting:
		doc = frappe.get_doc("Integration Settings", setting)
		if doc.service != service:
			frappe.throw(_("That integration is not a {0} integration.").format(LABELS[service]))
		for row in doc.credentials:
			if row.key in keys:
				creds[row.key] = row.get_password("value", raise_exception=False)
	# With no saved integration (the "new" screen) only the typed values count: another integration's
	# credentials must not make an empty form look connected.
	for key in keys:
		value = (provided.get(key) or "").strip() if isinstance(provided.get(key), str) else ""
		if value:
			creds[key] = value
	return creds


def _google_tokens(label: str, creds: dict) -> str:
	return mint_google_access_token(label, creds["client_id"], creds["client_secret"], creds["refresh_token"])["access_token"]


def _test_gmail(creds: dict) -> tuple[str, str | None]:
	token = _google_tokens("Gmail", creds)
	resp = httpx.get(
		"https://gmail.googleapis.com/gmail/v1/users/me/profile",
		headers={"Authorization": f"Bearer {token}"},
		timeout=15,
	)
	try:
		check_google_response(resp, "Gmail", "gmail.readonly")
	except ProviderCredentialError as e:
		if e.kind == "scope":
			# The token itself is accepted; sending only needs gmail.send, which cannot read the profile.
			return "Google accepted the saved credentials. They cannot read the mailbox profile, which is fine for sending (gmail.send).", None
		raise
	address = resp.json().get("emailAddress")
	return (f"Connected to Gmail as {address}." if address else "Google accepted the saved credentials."), address


def _test_sheets(creds: dict) -> tuple[str, str | None]:
	_google_tokens("Google Sheets", creds)
	return "Google accepted the saved credentials. Sheets has no read-only check, so access to a specific spreadsheet is only confirmed when a step runs.", None


def _test_drive(creds: dict) -> tuple[str, str | None]:
	token = _google_tokens("Google Drive", creds)
	resp = httpx.get(
		"https://www.googleapis.com/drive/v3/about",
		headers={"Authorization": f"Bearer {token}"},
		params={"fields": "user(displayName,emailAddress)"},
		timeout=15,
	)
	check_google_response(resp, "Google Drive", "drive.readonly")
	user = resp.json().get("user") or {}
	who = user.get("emailAddress") or user.get("displayName")
	return (f"Connected to Google Drive as {who}." if who else "Google accepted the saved credentials."), who


def _test_slack(creds: dict) -> tuple[str, str | None]:
	token = creds.get("token")
	resp = httpx.post("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {token}"}, timeout=15)
	resp.raise_for_status()
	data = resp.json()
	if not data.get("ok"):
		raise ProviderCredentialError(slack_error_message(data))
	team, user = data.get("team"), data.get("user")
	message = f"Connected to Slack workspace {team} as {user}." if team and user else "Slack accepted the saved token."
	return message, team


_TESTERS = {"gmail": _test_gmail, "google_sheets": _test_sheets, "google_drive": _test_drive, "slack": _test_slack}


def _remember_check(setting: str, result: dict) -> None:
	"""Keep the answer of a check of the SAVED credentials, so the list can show health without testing again.

	A success also clears an older "last error": from then on any error shown is newer than the last good check.
	"""
	values = {
		"last_test_status": result["status"],
		"last_test_at": now_datetime(),
		"last_test_message": result["message"][:500],
		"account_label": (result.get("account") or "")[:140],
	}
	if result["status"] == "Connected":
		values["last_error"] = ""
	frappe.db.set_value("Integration Settings", setting, values, update_modified=False)


@frappe.whitelist(methods=["POST"])
def test_connection(service: str, setting: str | None = None, credentials: str | dict | None = None) -> dict:
	"""Check that a Gmail / Slack / Drive / Sheets integration's credentials are accepted.

	setting: an Integration Settings name whose saved credentials are used.
	credentials: optional values typed on the form (used instead of saved ones, never stored).
	Returns ``{status, code, message, account?, checked_at?}``. status is Connected | Rejected | Not connected;
	code is ok | no_credentials | missing_credentials | rejected | missing_permission | unreachable.
	When only saved credentials were checked, the answer is also kept on the integration (not for ``unreachable``).
	"""
	frappe.only_for(ALLOWED_ROLES)
	if service not in _TESTERS:
		frappe.throw(_("Test connection is not available for this integration."))
	if setting and not frappe.has_permission("Integration Settings", "read", doc=setting):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if isinstance(credentials, str):
		credentials = json.loads(credentials or "{}")
	provided = credentials if isinstance(credentials, dict) else {}
	typed = any(isinstance(provided.get(k), str) and provided[k].strip() for k in SERVICE_KEYS[service])

	label = LABELS[service]
	result: dict
	try:
		creds = _resolve_credentials(service, setting, provided)
		missing = _missing_error(service, creds)
		if missing:
			raise missing
		message, account = _TESTERS[service](creds)
		result = {"status": "Connected", "code": "ok", "message": message, "account": account}
	except ProviderCredentialError as e:
		if e.kind == "missing":
			code = "no_credentials" if str(e).startswith("No credentials") else "missing_credentials"
			result = {"status": "Not connected", "code": code, "message": str(e)}
		else:
			result = {
				"status": "Rejected",
				"code": "missing_permission" if e.kind == "scope" else "rejected",
				"message": _on_this_screen(label, str(e)),
			}
	except (httpx.TransportError, httpx.HTTPStatusError) as e:
		frappe.logger("huf").warning(f"{label} test connection failed: {type(e).__name__}")
		return {
			"status": "Rejected",
			"code": "unreachable",
			"message": f"Could not check {label} right now. Check the server's internet access and try again.",
		}
	except Exception:
		frappe.log_error(title=f"{label} test connection")
		return {"status": "Rejected", "code": "unreachable", "message": f"Could not check {label}. The details are in the error log."}

	if setting and not typed:
		_remember_check(setting, result)
		result["checked_at"] = str(now_datetime())
	return result


def slack_channels_for_setting(setting: str | None) -> dict:
	from huf.ai.tools.slack import SlackChannelError, fetch_channels

	if setting:
		token = _resolve_credentials("slack", setting, {}).get("token")
	else:
		# No integration named (the flow step form): the one the tools themselves would use.
		from huf.ai.tools.credentials import get_credential

		token = get_credential("slack", "token")
	if not token:
		return {"status": "Not connected", "code": "no_credentials", "message": "No credentials saved yet. Add the bot token first.", "channels": []}
	try:
		channels = fetch_channels(
			token, force=True, timeout=CHANNEL_LIST_TIMEOUT, deadline=time.monotonic() + CHANNEL_LIST_BUDGET
		)
	except SlackChannelError as e:
		return {"status": "Rejected", "code": "rejected", "message": str(e), "channels": []}
	except (httpx.TransportError, httpx.HTTPStatusError) as e:
		frappe.logger("huf").warning(f"Slack channel list failed: {type(e).__name__}")
		return {"status": "Rejected", "code": "unreachable", "message": "Could not reach Slack right now. Try again.", "channels": []}
	return {"status": "Connected", "code": "ok", "channels": sorted(channels, key=lambda c: (c.get("name") or ""))}


@frappe.whitelist(methods=["POST"])
def list_slack_channels(setting: str | None = None) -> dict:
	"""Read-only list of the Slack channels the integration's bot can see (no message is sent).

	Returns ``{status: "Connected", channels: [{id, name, is_private}]}`` or
	``{status: "Rejected" | "Not connected", message, channels: []}``.
	"""
	frappe.only_for(ALLOWED_ROLES)
	if setting and not frappe.has_permission("Integration Settings", "read", doc=setting):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return slack_channels_for_setting(setting)
