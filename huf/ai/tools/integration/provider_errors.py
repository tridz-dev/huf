# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Plain-language errors for third-party credential problems (Google, Slack).

Separates "credentials are missing" from "the provider rejected the saved credentials" and from
"the credentials work but lack a permission". Messages never include secrets or provider payloads.
"""

import re

import httpx

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class ProviderCredentialError(ValueError):
	"""A credential problem whose message is safe and plain enough to show to the user.

	kind: "missing" (nothing saved), "rejected" (provider refused the credentials) or "scope"
	(credentials work but lack a permission).
	"""

	def __init__(self, message: str, kind: str = "rejected"):
		super().__init__(message)
		self.kind = kind


def not_connected_message(label: str, what: str) -> str:
	return f"{label} is not connected: add {what} in Integrations."


def rejected_message(label: str, reason: str) -> str:
	return f"{label} rejected the saved credentials ({reason}). Reconnect {label} in Integrations."


def needs_scope_message(label: str, scope: str) -> str:
	return f"{label} needs the {scope} permission: reconnect with that scope."


_GOOGLE_TOKEN_REASONS = {
	"invalid_grant": "token expired or revoked",
	"invalid_client": "the client ID or client secret is wrong",
	"unauthorized_client": "this client is not allowed to use the requested access",
	"invalid_scope": "a requested permission is not allowed",
	"access_denied": "access was denied",
}


def _json_or_empty(resp) -> dict:
	try:
		data = resp.json()
	except Exception:
		return {}
	return data if isinstance(data, dict) else {}


def google_token_error_message(label: str, resp) -> str:
	"""Message for a failed Google refresh-token exchange."""
	status = getattr(resp, "status_code", None)
	if isinstance(status, int) and status >= 500:
		return f"Google is not responding right now (status {status}). Try again in a minute."
	code = _json_or_empty(resp).get("error")
	reason = _GOOGLE_TOKEN_REASONS.get(code) if isinstance(code, str) else None
	if reason is None:
		reason = f"Google said: {code}" if isinstance(code, str) and code.replace("_", "").isalnum() else "Google did not accept them"
	return rejected_message(label, reason)


def mint_google_access_token(label: str, client_id: str, client_secret: str, refresh_token: str) -> dict:
	"""Exchange a refresh token for an access token. Returns Google's token payload.

	Raises ProviderCredentialError with plain copy when Google rejects the credentials.
	"""
	try:
		resp = httpx.post(
			GOOGLE_TOKEN_URL,
			data={
				"client_id": client_id,
				"client_secret": client_secret,
				"refresh_token": refresh_token,
				"grant_type": "refresh_token",
			},
			timeout=15,
		)
	except httpx.TransportError:
		raise ProviderCredentialError(f"Could not reach Google to check the {label} credentials. Check the server's internet access.") from None
	try:
		resp.raise_for_status()
	except Exception:
		raise ProviderCredentialError(google_token_error_message(label, resp)) from None
	data = resp.json()
	if not data.get("access_token"):
		raise ProviderCredentialError(rejected_message(label, "Google returned no access token"))
	return data


def _google_error_reasons(resp) -> str:
	body = _json_or_empty(resp).get("error")
	if not isinstance(body, dict):
		return ""
	parts = [str(body.get("status", "")), str(body.get("message", ""))]
	for entry in (body.get("errors") or []) + (body.get("details") or []):
		if isinstance(entry, dict):
			parts.append(str(entry.get("reason", "")))
	return " ".join(parts).lower()


def check_google_response(resp, label: str, scope: str, not_found: str | None = None) -> None:
	"""Raise a plain-language error for a failed Google API response; otherwise do nothing.

	scope: the permission the call needs (shown when Google reports insufficient scopes).
	not_found: noun for a 404, e.g. "spreadsheet".
	"""
	status = getattr(resp, "status_code", None)
	if not isinstance(status, int) or status < 400:
		resp.raise_for_status()
		return
	if status == 401:
		raise ProviderCredentialError(rejected_message(label, "token expired or revoked"))
	reasons = _google_error_reasons(resp)
	if status == 403 and ("scope" in reasons or "insufficientpermissions" in reasons.replace(" ", "")):
		raise ProviderCredentialError(needs_scope_message(label, scope), kind="scope")
	if status == 404 and not_found:
		raise ProviderCredentialError(
			f"{label} could not find that {not_found}. Check the ID, and that the connected Google account can open it."
		)
	resp.raise_for_status()


_SLACK_REJECTED = {
	"invalid_auth": "the token is not valid",
	"not_authed": "no valid token was sent",
	"account_inactive": "the token's account is deactivated",
	"token_revoked": "token revoked",
	"token_expired": "token expired",
}


def slack_error_message(data: dict) -> str:
	"""Plain message for a Slack ``ok: false`` response body."""
	code = str((data or {}).get("error") or "unknown_error")
	if code in _SLACK_REJECTED:
		return rejected_message("Slack", _SLACK_REJECTED[code]).replace(
			"saved credentials", "saved token"
		)
	if code == "missing_scope":
		needed = str((data or {}).get("needed") or "").strip()
		scope = needed or "a required"
		return f"Slack needs the {scope} permission: add that scope to the Slack app, reinstall it, then update the token in Integrations."
	if code == "channel_not_found":
		return "Slack could not find that channel. Check the channel ID, and invite the bot to private channels."
	if code == "not_in_channel":
		return "The Slack bot is not in that channel. Invite it with /invite, then try again."
	return code


# ---- recipient validation (Send Email) ----

_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def invalid_recipients(value: str) -> list[str]:
	"""Return the entries of a comma/semicolon separated address list that are not valid emails.

	Accepts ``a@b.co`` and ``Name <a@b.co>``. An empty list means all entries are valid.
	"""
	from email.utils import parseaddr

	entries = [e.strip() for e in re.split(r"[;,]", value or "") if e.strip()]
	if not entries:
		return [value or ""]
	bad = []
	for entry in entries:
		addr = parseaddr(entry)[1]
		if not addr or not _EMAIL_RE.match(addr) or "\n" in entry or "\r" in entry:
			bad.append(entry)
	return bad


def normalize_recipients(value: str) -> str:
	"""Comma-join a comma/semicolon separated address list (Gmail expects commas)."""
	return ", ".join(e.strip() for e in re.split(r"[;,]", value or "") if e.strip())
