# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Test connection for Gmail, Slack, Google Drive and Google Sheets.

Makes one harmless read-only call (Gmail users.getProfile, Slack auth.test, Drive about.get;
Sheets only mints a token) and answers Connected / Rejected with plain copy. Never sends mail,
never stores anything and never returns credential values.
"""

import json

import frappe
import httpx
from frappe import _

from huf.ai.tools.provider_errors import (
	ProviderCredentialError,
	check_google_response,
	mint_google_access_token,
	not_connected_message,
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
ALLOWED_ROLES = ("System Manager", "Huf Manager")


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
	if not all(creds.get(k) for k in GOOGLE_KEYS):
		raise ProviderCredentialError(
			not_connected_message(label, "the client ID, client secret and refresh token"), kind="missing"
		)
	return mint_google_access_token(label, creds["client_id"], creds["client_secret"], creds["refresh_token"])["access_token"]


def _test_gmail(creds: dict) -> str:
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
			return "Google accepted the saved credentials. They cannot read the mailbox profile, which is fine for sending (gmail.send)."
		raise
	address = resp.json().get("emailAddress")
	return f"Connected to Gmail as {address}." if address else "Google accepted the saved credentials."


def _test_sheets(creds: dict) -> str:
	_google_tokens("Google Sheets", creds)
	return "Google accepted the saved credentials. Sheets has no read-only check, so access to a specific spreadsheet is only confirmed when a step runs."


def _test_drive(creds: dict) -> str:
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
	return f"Connected to Google Drive as {who}." if who else "Google accepted the saved credentials."


def _test_slack(creds: dict) -> str:
	token = creds.get("token")
	if not token:
		raise ProviderCredentialError(not_connected_message("Slack", "the bot token"), kind="missing")
	resp = httpx.post("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {token}"}, timeout=15)
	resp.raise_for_status()
	data = resp.json()
	if not data.get("ok"):
		raise ProviderCredentialError(slack_error_message(data))
	team, user = data.get("team"), data.get("user")
	return f"Connected to Slack workspace {team} as {user}." if team and user else "Slack accepted the saved token."


_TESTERS = {"gmail": _test_gmail, "google_sheets": _test_sheets, "google_drive": _test_drive, "slack": _test_slack}


@frappe.whitelist(methods=["POST"])
def test_connection(service: str, setting: str | None = None, credentials: str | dict | None = None) -> dict:
	"""Check that a Gmail / Slack / Drive / Sheets integration's credentials are accepted.

	setting: an Integration Settings name whose saved credentials are used.
	credentials: optional values typed on the form (used instead of saved ones, never stored).
	Returns ``{status: "Connected" | "Rejected" | "Not connected", message}``.
	"""
	frappe.only_for(ALLOWED_ROLES)
	if service not in _TESTERS:
		frappe.throw(_("Test connection is not available for this integration."))
	if setting and not frappe.has_permission("Integration Settings", "read", doc=setting):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if isinstance(credentials, str):
		credentials = json.loads(credentials or "{}")
	provided = credentials if isinstance(credentials, dict) else {}

	label = LABELS[service]
	try:
		message = _TESTERS[service](_resolve_credentials(service, setting, provided))
		return {"status": "Connected", "message": message}
	except ProviderCredentialError as e:
		return {"status": "Not connected" if e.kind == "missing" else "Rejected", "message": str(e)}
	except (httpx.TransportError, httpx.HTTPStatusError) as e:
		frappe.logger("huf").warning(f"{label} test connection failed: {type(e).__name__}")
		return {"status": "Rejected", "message": f"Could not check {label} right now. Check the server's internet access and try again."}
	except Exception:
		frappe.log_error(title=f"{label} test connection")
		return {"status": "Rejected", "message": f"Could not check {label}. The details are in the error log."}
