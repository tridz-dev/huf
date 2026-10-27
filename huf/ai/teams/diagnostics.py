"""Teams "Verify connection" diagnostics: a whitelisted, rate-limited probe of the bot credentials.

Acquires a fresh Bot Framework token (bypassing caches), checks its unverified claims against the
configured app/tenant, and reports offline endpoint/reference status. Sends no Teams message and never
calls the webhook URL. Tokens, secrets and raw claims are never returned or logged.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import frappe
from frappe import _

from huf.ai.teams import client, readiness

logger = logging.getLogger("huf.teams.diagnostics")

PROVIDER = "Microsoft Teams"
RATE_LIMIT_SECONDS = 5
_RATE_PREFIX = "huf_teams_verify:"
_AADSTS_RE = re.compile(r"AADSTS\d{4,8}")
_AADSTS_MESSAGES = {
	"AADSTS7000215": "Invalid client secret. Paste the secret Value (not the Secret ID) of the app registration.",
	"AADSTS7000222": "The client secret has expired. Create a new secret in Azure and update it here.",
	"AADSTS700016": "Application not found in this tenant. Check the Microsoft App ID and Tenant ID.",
	"AADSTS90002": "Tenant not found. Check the Tenant ID.",
}
_UNREACHABLE = "Could not reach Microsoft login. This looks temporary; try again shortly."
_SKIPPED = "Skipped because an earlier step failed."


def _step(step_id: str, label: str, ok: bool, detail: str | None = None) -> dict[str, Any]:
	return {"id": step_id, "label": label, "ok": bool(ok), "detail": detail}


def _check_credentials(creds: dict[str, str]) -> dict[str, Any]:
	problems = []
	for key in ("app_id", "tenant_id"):
		value = str(creds.get(key) or "").strip()
		if not value:
			problems.append(f"{key} is missing")
		elif not readiness.GUID_RE.match(value):
			problems.append(f"{key} is not a GUID")
	if not str(creds.get("app_password") or "").strip():
		problems.append("app_password is missing")
	return _step("credentials", "Credentials", not problems, "; ".join(problems) or None)


def _token_failure(exc: BaseException) -> str:
	if isinstance(exc, client.TeamsAuthError):
		code = _AADSTS_RE.search(str(exc))
		if not code:
			return "Microsoft rejected the credentials. Check the App ID, client secret value and Tenant ID."
		return _AADSTS_MESSAGES.get(code.group(0), f"Microsoft rejected the credentials ({code.group(0)}).")
	if isinstance(exc, client.TeamsTransientError):
		return _UNREACHABLE
	return "Could not obtain a token. See the Error Log for details."


def _jwt_claims(token: str) -> dict[str, Any] | None:
	"""Decode the JWT payload WITHOUT verifying it. Used only to compare ids; never returned."""
	try:
		payload = token.split(".")[1]
		claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
	except Exception:  # noqa: BLE001
		return None
	return claims if isinstance(claims, dict) else None


def _check_claims(token: str, creds: dict[str, str]) -> dict[str, Any]:
	label = "Token matches app and tenant"
	claims = _jwt_claims(token)
	if claims is None:
		return _step(
			"token_claims",
			label,
			False,
			"The token could not be decoded, so its app and tenant could not be checked.",
		)
	problems = []
	app_claims = [str(claims[k]).lower() for k in ("appid", "azp") if claims.get(k)]
	if not app_claims:
		problems.append("the token has no application id claim")
	elif creds["app_id"].strip().lower() not in app_claims:
		problems.append("the token was issued to a different application than the configured App ID")
	tid = str(claims.get("tid") or "").lower()
	if not tid:
		problems.append("the token has no tenant claim")
	elif tid != creds["tenant_id"].strip().lower():
		problems.append("the token was issued by a different tenant than the configured Tenant ID")
	return _step(
		"token_claims", label, not problems, "; ".join(problems).capitalize() + "." if problems else None
	)


def _informational(step_id: str, label: str, item: dict[str, Any], ok_detail: str) -> dict[str, Any]:
	done = bool(item.get("done"))
	return _step(step_id, label, done, ok_detail if done else item.get("hint"))


def _enforce_rate_limit(gateway_name: str) -> None:
	key = _RATE_PREFIX + gateway_name
	if frappe.cache.get_value(key):
		frappe.throw(
			_("Verify connection was run moments ago. Wait a few seconds and try again."),
			frappe.TooManyRequestsError,
		)
	frappe.cache.set_value(key, 1, expires_in_sec=RATE_LIMIT_SECONDS)


@frappe.whitelist(methods=["POST"])
def verify_teams_connection(gateway_name: str) -> dict:
	"""Verify the Teams bot credentials of a Microsoft Teams Gateway.

	Returns ``{ok, steps: [{id, label, ok, detail}], message}`` with steps ``credentials``, ``token``,
	``token_claims``, ``endpoint`` and ``reference`` in that order. ``ok`` covers the first three; the last
	two are informational. Needs write permission because it sends authentication traffic to Microsoft.
	"""
	frappe.has_permission("Gateway", "write", gateway_name, throw=True)
	gateway = frappe.get_doc("Gateway", gateway_name)
	if gateway.provider != PROVIDER:
		frappe.throw(_("This gateway is not a Microsoft Teams gateway."))
	_enforce_rate_limit(gateway_name)

	creds = {k: str(v or "") for k, v in (gateway._load_integration_credentials() or {}).items()}
	steps = [_check_credentials(creds)]
	token_step = _step("token", "Bot token", False, _SKIPPED)
	claims_step = _step("token_claims", "Token matches app and tenant", False, _SKIPPED)
	if steps[0]["ok"]:
		try:
			client.clear_token_cache(creds["tenant_id"], creds["app_id"])
			token = client.get_token(creds)
		except Exception as exc:  # noqa: BLE001
			# Type and AADSTS code only: exception text is never logged.
			code = _AADSTS_RE.search(str(exc))
			logger.warning(
				"Teams verify token failed (%s %s)", type(exc).__name__, code.group(0) if code else "-"
			)
			token_step = _step("token", "Bot token", False, _token_failure(exc))
		else:
			token_step = _step("token", "Bot token", True, None)
			claims_step = _check_claims(token, creds)
			del token
	steps += [token_step, claims_step]
	steps.append(
		_informational(
			"endpoint",
			"Messaging endpoint",
			readiness._check_endpoint(gateway),
			f"Gateway is enabled. Messaging endpoint: {readiness._webhook_url(gateway.name)}",
		)
	)
	steps.append(
		_informational(
			"reference",
			"Conversation reference",
			readiness._check_first_message(gateway, None),
			"A conversation reference is stored; the bot can reply.",
		)
	)

	ok = all(s["ok"] for s in steps[:3])
	if ok:
		message = "Connection verified: Microsoft issued a token for this app and tenant."
	else:
		failed = next(s for s in steps[:3] if not s["ok"])
		message = f"{failed['label']} failed: {failed['detail']}"
	return {"ok": ok, "steps": steps, "message": message}
