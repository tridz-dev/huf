"""Microsoft Teams diagnostics: separate, plain-language checks and a redacted support bundle.

Every check is independent (one failing check never breaks the report), queries are bounded
and grouped (no N+1), and nothing returned contains secrets, tokens, message text, file URLs
or raw payloads. Credential values are only ever tested for presence.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable
from urllib.parse import quote

import frappe

from huf.ai.gateways import teams_api, teams_contract as tc, teams_tenant
from huf.ai.gateways.health import redact
from huf.ai.gateways.teams_outbox import redact_payload

PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"
REQUIRED_CREDS = ("app_id", "app_password", "tenant_id")
GROUP_LIMIT = 50
DEAD_LIMIT = 20
EVENT_WINDOW_HOURS = 24
ERROR_CLIP = 160
OUTBOX_STATUSES = ("Pending", "Sent", "Failed", "Dead")

# Seam for tests: ``fn(creds, gateway_name=...) -> token``.
_token_fn: Callable[..., str] | None = None

_TOKEN_FIXES = {
	"invalid_client": (
		"Microsoft rejected the app password.",
		"The client secret is wrong or has expired. Create a new secret in Entra ID "
		"(App registrations > Certificates & secrets) and paste its Value, not its ID.",
	),
	"unauthorized_client": (
		"This app is not allowed to sign in for that tenant.",
		"Check the Tenant ID and that the app registration is single-tenant for that directory.",
	),
	"invalid_tenant_id": (
		"The Tenant ID is not valid.",
		"Copy the Directory (tenant) ID from the Entra ID app overview page.",
	),
	"missing_credentials": (
		"Credentials are incomplete.",
		"Fill in App ID, App password and Tenant ID.",
	),
	"invalid_token_response": (
		"Microsoft answered but did not return a token.",
		"Retry in a minute; if it persists check the Entra app registration.",
	),
}


def _(text: str) -> str:
	return frappe._(text)


def _clip(text: Any, limit: int = ERROR_CLIP) -> str:
	text = " ".join(redact(text).split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _check(cid: str, status: str, title: str, detail: str = "", how_to_fix: str = "") -> dict:
	return {"id": cid, "status": status, "title": title, "detail": detail, "how_to_fix": how_to_fix}


# ----------------------------------------------------------------- permission

def _gateway_for(gateway_name: str):
	if not gateway_name or not isinstance(gateway_name, str):
		frappe.throw(_("Choose a gateway."), frappe.ValidationError)
	if "System Manager" not in (frappe.get_roles() or []):
		if not frappe.has_permission("Gateway", "write", doc=gateway_name):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("Gateway", gateway_name):
		frappe.throw(_("Gateway not found."), frappe.DoesNotExistError)
	gateway = frappe.get_doc("Gateway", gateway_name)
	if getattr(gateway, "provider", None) != tc.PROVIDER_LABEL:
		frappe.throw(_("This gateway is not a Microsoft Teams gateway."), frappe.ValidationError)
	return gateway


def _creds(gateway) -> dict[str, str]:
	return {k: teams_tenant.get_gateway_credential(gateway, k) for k in REQUIRED_CREDS}


def endpoint_url(gateway_name: str) -> str:
	return (
		f"{frappe.utils.get_url().rstrip('/')}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
		f"?gateway_name={quote(gateway_name, safe='')}"
	)


# --------------------------------------------------------------------- checks

def _check_credentials(ctx) -> list[dict]:
	missing = [k for k in REQUIRED_CREDS if not ctx["creds"].get(k)]
	out = []
	if missing:
		out.append(_check("credentials_present", FAIL, _("Credentials"),
			_("Missing: {0}").format(", ".join(missing)),
			_("Open the gateway credentials and fill in App ID, App password and Tenant ID.")))
	else:
		out.append(_check("credentials_present", PASS, _("Credentials"), _("App ID, App password and Tenant ID are set.")))
	out.append(_check("credential_expiry", INFO, _("Secret expiry"),
		_("Huf cannot see when the client secret expires."),
		_("Check the expiry date in Entra ID and rotate before it lapses.")))
	return out


def _check_token(ctx) -> list[dict]:
	if any(not ctx["creds"].get(k) for k in REQUIRED_CREDS):
		return [_check("token_acquisition", FAIL, _("Sign-in to Microsoft"), _("Skipped: credentials are incomplete."),
			_("Fill in the credentials first."))]
	fn = _token_fn or teams_api.get_bot_token
	try:
		token = fn(ctx["creds"], gateway_name=ctx["name"])
	except teams_api.TeamsApiError as e:
		code = e.code or ""
		detail, fix = _TOKEN_FIXES.get(code, (
			_("Microsoft sign-in failed (HTTP {0}).").format(e.status),
			_("Retry shortly; if it persists verify App ID, secret and Tenant ID."),
		))
		if e.status:
			detail = f"{detail} (HTTP {e.status})"
		return [_check("token_acquisition", FAIL, _("Sign-in to Microsoft"), detail, fix)]
	if not token:
		return [_check("token_acquisition", FAIL, _("Sign-in to Microsoft"), _("No token was returned."),
			_("Verify the credentials."))]
	return [_check("token_acquisition", PASS, _("Sign-in to Microsoft"), _("A bot token was obtained."))]


def _check_endpoint(ctx) -> list[dict]:
	url = endpoint_url(ctx["name"])
	status = PASS if url.startswith("https://") else WARN
	fix = "" if status == PASS else _("Teams requires a public HTTPS messaging endpoint.")
	return [_check("messaging_endpoint", status, _("Messaging endpoint"), url,
		fix or _("Paste this URL as the Messaging endpoint in the Azure Bot resource."))]


def _check_tenants(ctx) -> list[dict]:
	allowed = teams_tenant.get_allowed_tenants(ctx["name"])
	if not allowed:
		return [_check("allowed_tenants", WARN, _("Allowed tenants"),
			_("None configured: only the home tenant can use this bot."),
			_("Add partner tenant IDs in Teams settings if other organisations should connect."))]
	return [_check("allowed_tenants", PASS, _("Allowed tenants"), _("{0} tenant(s) allowed.").format(len(allowed)))]


def _check_last_inbound(ctx) -> list[dict]:
	rows = frappe.get_all("Gateway Event", filters={"gateway": ctx["name"]},
		fields=["name", "status", "received_at"], order_by="received_at desc", limit_page_length=1)
	if not rows:
		return [_check("last_inbound", WARN, _("Last inbound message"), _("No messages received yet."),
			_("Send 'help' to the bot in a personal chat in Teams."))]
	r = rows[0]
	return [_check("last_inbound", PASS, _("Last inbound message"),
		_("{0} ({1})").format(r.get("received_at"), r.get("status")))]


def _check_rejections(ctx) -> list[dict]:
	since = frappe.utils.now_datetime() - timedelta(hours=EVENT_WINDOW_HOURS)
	rows = frappe.get_all("Gateway Event",
		filters={"gateway": ctx["name"], "status": "Rejected", "received_at": (">=", since)},
		fields=["error_message", "count(name) as n"], group_by="error_message",
		order_by="n desc", limit_page_length=GROUP_LIMIT)
	counts = {_clip(r.get("error_message") or "unknown", 80): int(r.get("n") or 0) for r in rows}
	ctx["rejections"] = counts
	total = sum(counts.values())
	if not total:
		return [_check("rejections_24h", PASS, _("Rejections (24h)"), _("None."))]
	detail = ", ".join(f"{k}: {v}" for k, v in counts.items())
	return [_check("rejections_24h", WARN, _("Rejections (24h)"), detail,
		_("Rejected messages usually mean an unlisted tenant, an unlinked user or a bad token."))]


def _check_references(ctx) -> list[dict]:
	rows = frappe.get_all("Teams Conversation Reference",
		filters={"gateway": ctx["name"], "installed": 1}, fields=["conversation_type", "count(name) as n"],
		group_by="conversation_type", limit_page_length=GROUP_LIMIT)
	counts = {r.get("conversation_type") or "unknown": int(r.get("n") or 0) for r in rows}
	ctx["references"] = counts
	if not sum(counts.values()):
		return [_check("conversation_references", WARN, _("Installed conversations"), _("None installed."),
			_("Install the app in Teams (personal, team or group chat)."))]
	detail = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
	return [_check("conversation_references", PASS, _("Installed conversations"), detail)]


def _check_outbox(ctx) -> list[dict]:
	rows = frappe.get_all("Teams Outbound Message", filters={"gateway": ctx["name"]},
		fields=["status", "count(name) as n"], group_by="status", limit_page_length=GROUP_LIMIT)
	counts = {r.get("status"): int(r.get("n") or 0) for r in rows}
	ctx["outbox"] = counts
	dead = frappe.get_all("Teams Outbound Message", filters={"gateway": ctx["name"], "status": "Dead"},
		fields=["name", "last_error"], order_by="modified desc", limit_page_length=DEAD_LIMIT)
	ctx["dead"] = [{"name": d.get("name"), "last_error": _clip(d.get("last_error"))} for d in dead]
	detail = ", ".join(f"{s}: {counts.get(s, 0)}" for s in OUTBOX_STATUSES)
	if ctx["dead"]:
		names = ", ".join(d["name"] for d in ctx["dead"])
		return [_check("outbox", FAIL, _("Outgoing messages"), f"{detail}. Dead: {names}",
			_("Dead messages ran out of retries. Check the last error on each, fix the cause and resend."))]
	if counts.get("Failed"):
		return [_check("outbox", WARN, _("Outgoing messages"), detail, _("Failed messages will be retried automatically."))]
	return [_check("outbox", PASS, _("Outgoing messages"), detail)]


def _check_links(ctx) -> list[dict]:
	n = frappe.db.count("Gateway Identity Link", {"gateway": ctx["name"], "state": "Linked"})
	ctx["linked"] = int(n or 0)
	if not ctx["linked"]:
		return [_check("linked_users", WARN, _("Linked users"), _("No Teams users are linked."),
			_("Ask users to send 'link' to the bot to connect their Huf account."))]
	return [_check("linked_users", PASS, _("Linked users"), str(ctx["linked"]))]


def _check_package(ctx) -> list[dict]:
	version = teams_tenant.get_settings(ctx["name"]).get("app_package_version") or ""
	if not version:
		return [_check("app_package", INFO, _("App package version"), _("No version recorded."),
			_("Download the app package and record its version in Teams settings after uploading."))]
	return [_check("app_package", INFO, _("App package version"),
		_("Recorded {0}; contract {1}.").format(version, tc.CONTRACT_VERSION))]


def _check_private_send(ctx) -> list[dict]:
	personal = (ctx.get("references") or {}).get("personal", 0)
	if personal:
		return [_check("private_send_ready", PASS, _("Private messages"), _("{0} personal chat(s) installed.").format(personal))]
	return [_check("private_send_ready", WARN, _("Private messages"), _("No user has the app installed in a personal chat."),
		_("Users must install the app (or an admin pre-installs it) before Huf can message them privately."))]


_CHECKS = (
	("credentials_present", _check_credentials), ("token_acquisition", _check_token),
	("messaging_endpoint", _check_endpoint), ("allowed_tenants", _check_tenants),
	("last_inbound", _check_last_inbound), ("rejections_24h", _check_rejections),
	("conversation_references", _check_references), ("outbox", _check_outbox),
	("linked_users", _check_links), ("app_package", _check_package),
	("private_send_ready", _check_private_send),
)


def _run_checks(ctx: dict) -> list[dict]:
	out: list[dict] = []
	for cid, fn in _CHECKS:
		try:
			out.extend(fn(ctx))
		except Exception as e:  # one broken check must not break the report
			out.append(_check(cid, FAIL, cid.replace("_", " ").capitalize(),
				_("This check could not run ({0}).").format(type(e).__name__),
				_("Retry; if it persists contact support with the support bundle.")))
	return out


@frappe.whitelist()
def teams_diagnose(gateway_name: str) -> dict:
	gateway = _gateway_for(gateway_name)
	ctx = {"name": gateway_name, "creds": {}}
	try:
		ctx["creds"] = _creds(gateway)
	except Exception:
		pass
	checks = _run_checks(ctx)
	summary = {s: sum(1 for c in checks if c["status"] == s) for s in (PASS, WARN, FAIL, INFO)}
	return {"gateway": gateway_name, "checks": checks, "summary": summary}


@frappe.whitelist()
def teams_support_bundle(gateway_name: str) -> dict:
	"""Redacted, JSON-able bundle: versions, counts, timestamps, error codes. No content."""
	gateway = _gateway_for(gateway_name)
	ctx = {"name": gateway_name, "creds": {}}
	try:
		ctx["creds"] = _creds(gateway)
	except Exception:
		pass
	report = _run_checks(ctx)
	checks = [{"id": c["id"], "status": c["status"]} for c in report]
	settings = {}
	try:
		settings = teams_tenant.get_settings(gateway_name)
	except Exception:
		pass
	bundle = {
		"gateway": gateway_name,
		"generated_at": str(frappe.utils.now_datetime()),
		"contract_version": tc.CONTRACT_VERSION,
		"app_package_version": settings.get("app_package_version") or "",
		"allowed_tenant_count": len(teams_tenant.parse_tenant_text(settings.get("allowed_tenants"))),
		"fields_configured": [k.replace("app_password", "app_secret") for k in REQUIRED_CREDS if ctx["creds"].get(k)],
		"checks": checks,
		"rejections_24h": ctx.get("rejections", {}),
		"conversation_references": ctx.get("references", {}),
		"outbox_counts": ctx.get("outbox", {}),
		"dead_letters": ctx.get("dead", []),
		"linked_users": ctx.get("linked", 0),
	}
	return redact_payload(bundle)
