# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Embedded Signup, tenant side: token exchange and ``complete_signup``."""

from __future__ import annotations

import secrets as pysecrets
from typing import Any

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.channels.embedded_signup.core import (
	_PIN_RE,
	HTTP_TIMEOUT,
	SignupError,
	_clean,
	_digits,
	_graph,
	_graph_error,
	_is_https_ok,
	_log_error,
	_require_admin,
	_secret,
	_settings,
)

# ---------------------------------------------------------------------------
# token exchange
# ---------------------------------------------------------------------------
def _exchange_code_with_meta(settings, code: str) -> str:
	"""Exchange the SDK code for a business integration token using this site's app secret."""
	app_id = (settings.facebook_app_id or "").strip()
	secret = _secret(settings, "app_secret")
	if not app_id or not secret:
		raise SignupError(_("Facebook app id / secret are not configured."))
	try:
		resp = requests.get(
			f"{_graph(settings)}/oauth/access_token",
			params={"client_id": app_id, "client_secret": secret, "code": code},
			timeout=HTTP_TIMEOUT,
		)
	except Exception as exc:
		raise SignupError(_("Could not reach Meta: {0}").format(_clean(exc, secret, code))) from None
	if resp.status_code >= 400:
		raise SignupError(_("Meta rejected the signup code: {0}").format(_graph_error(resp, secret, code)))
	try:
		token = (resp.json() or {}).get("access_token")
	except Exception:
		token = None
	if not token:
		raise SignupError(_("Meta did not return an access token."))
	return str(token)


def _exchange_via_broker(
	settings, code: str, waba_id: str, phone_number_id: str, callback_url: str = ""
) -> dict[str, Any]:
	url = (settings.broker_url or "").strip()
	key = _secret(settings, "broker_api_key")
	if not url or not key:
		raise SignupError(_("Broker URL / API key are not configured."))
	if not _is_https_ok(url):
		raise SignupError(_("Broker URL must use https."))
	try:
		resp = requests.post(
			url,
			json={
				"code": code,
				"waba_id": waba_id,
				"phone_number_id": phone_number_id,
				"callback_url": callback_url,
			},
			headers={"Authorization": f"Bearer {key}", "X-Huf-Tenant": settings.tenant_id or ""},
			timeout=HTTP_TIMEOUT,
		)
	except Exception as exc:
		raise SignupError(_("Could not reach the broker: {0}").format(_clean(exc, key, code))) from None
	if resp.status_code >= 400:
		raise SignupError(_("The broker refused the signup (HTTP {0}).").format(resp.status_code))
	try:
		body = resp.json() or {}
	except Exception:
		body = {}
	body = body.get("message", body) if isinstance(body.get("message", None), dict) else body
	if not body.get("access_token"):
		raise SignupError(_("The broker did not return an access token."))
	return body


def _post_graph(settings, path: str, token: str, payload: dict | None = None):
	return requests.post(
		f"{_graph(settings)}/{path}",
		json=payload or {},
		headers={"Authorization": f"Bearer {token}"},
		timeout=HTTP_TIMEOUT,
	)


def _subscribe_app(settings, waba_id: str, token: str) -> str | None:
	"""Returns a warning string on failure."""
	try:
		resp = _post_graph(settings, f"{waba_id}/subscribed_apps", token)
		if resp.status_code >= 400:
			return _("Could not subscribe the app to the WhatsApp account: {0}").format(_graph_error(resp, token))
	except Exception as exc:
		return _("Could not subscribe the app to the WhatsApp account: {0}").format(_clean(exc, token))
	return None


def _register_phone(settings, phone_number_id: str, token: str, pin: str) -> str | None:
	try:
		resp = _post_graph(settings, f"{phone_number_id}/register", token, {"messaging_product": "whatsapp", "pin": pin})
		if resp.status_code >= 400:
			return _("Could not register the phone number: {0}").format(_graph_error(resp, token, pin))
	except Exception as exc:
		return _("Could not register the phone number: {0}").format(_clean(exc, token, pin))
	return None


def _planned_gateway_name(gateway_name: str | None, phone_number_id: str) -> str:
	"""The Gateway name ``_save_gateway`` will use (needed before it exists, for the webhook callback URL)."""
	if (gateway_name or "").strip():
		return gateway_name.strip()
	hit = frappe.db.get_value("Gateway", {"provider": "WhatsApp", "phone_number_id": phone_number_id}, "name")
	return hit or f"WhatsApp {phone_number_id[-4:]}"


def _save_gateway(
	*, token: str, app_secret: str, app_id: str, waba_id: str, phone_number_id: str, gateway_name: str | None
) -> tuple[str, str]:
	"""Create or update the WhatsApp Integration Settings + Gateway (same docs the wizard's credentials step writes)."""
	verify_token = "huf-" + pysecrets.token_hex(12)
	existing = None
	if gateway_name and frappe.db.exists("Gateway", gateway_name):
		existing = frappe.get_doc("Gateway", gateway_name)
	elif not gateway_name:
		hit = frappe.db.get_value("Gateway", {"provider": "WhatsApp", "phone_number_id": phone_number_id}, "name")
		existing = frappe.get_doc("Gateway", hit) if hit else None
	if existing is not None and existing.provider != "WhatsApp":
		raise SignupError(_("{0} is not a WhatsApp gateway.").format(existing.name))

	rows = {
		"phone_number_id": phone_number_id,
		"business_account_id": waba_id,
		"app_id": app_id,
		"access_token": token,
		"app_secret": app_secret,
		"webhook_verify_token": verify_token,
	}
	settings_name = existing.integration_settings if existing else None
	if settings_name:
		doc = frappe.get_doc("Integration Settings", settings_name)
		current = {r.key: r for r in doc.credentials or []}
		for key, value in rows.items():
			if key == "webhook_verify_token" and key in current:
				continue  # keep the verify token Meta already knows
			if key in current:
				current[key].value = value
			else:
				doc.append("credentials", {"key": key, "value": value})
		doc.is_active = 1
		doc.save()
		verify_token = _secret_row(doc, "webhook_verify_token") or verify_token
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"is_active": 1,
				"credentials": [{"key": k, "value": v} for k, v in rows.items()],
			}
		).insert()
		settings_name = doc.name

	if existing:
		existing.integration_settings = settings_name
		existing.is_enabled = 1
		existing.save()
		return existing.name, verify_token
	name = (gateway_name or "").strip() or f"WhatsApp {phone_number_id[-4:]}"
	gw = frappe.get_doc(
		{
			"doctype": "Gateway",
			"gateway_name": name,
			"provider": "WhatsApp",
			"is_enabled": 1,
			"integration_settings": settings_name,
			"direct_policy": "Pairing",  # safe default: strangers get a pairing code
			"execution_user": frappe.session.user,
		}
	).insert()
	return gw.name, verify_token


def _secret_row(doc, key: str) -> str:
	for r in doc.credentials or []:
		if r.key == key:
			try:
				return str(r.get_password("value") or "")
			except Exception:
				return ""
	return ""


def _hint(token: str) -> str:
	return f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "set"


def _setup_stage(name: str) -> str:
	try:
		from huf.ai.whatsapp import management as mgmt

		row = frappe.get_all(
			"Gateway", filters={"name": name}, fields=mgmt._GATEWAY_FIELDS, limit_page_length=1
		)[0]
		row = dict(row)
		row["whatsapp_account"] = mgmt._gateway_whatsapp_account(name)
		return mgmt._gateway_status(row)["setup_stage"]
	except Exception:
		return "connected_unverified"


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def complete_signup(
	code: str,
	waba_id: str,
	phone_number_id: str,
	business_id: str | None = None,
	gateway_name: str | None = None,
	pin: str | None = None,
) -> dict[str, Any]:
	"""Finish an Embedded Signup: token exchange, webhook subscription, number registration, gateway.

	Returns ``{gateway, setup_stage, webhook_url, verify_token_hint, warnings[, pin]}``. The access
	token is never returned. ``pin`` is returned only when generated here (shown once).
	"""
	_require_admin()
	code = str(code or "").strip()
	if not code:
		frappe.throw(_("The signup code is missing."))
	waba_id = _digits(waba_id, _("WhatsApp Business Account ID"))
	phone_number_id = _digits(phone_number_id, _("Phone Number ID"))
	if business_id:
		_digits(business_id, _("Business ID"))
	pin_generated = not pin
	if pin and not _PIN_RE.match(str(pin)):
		frappe.throw(_("The PIN must be 6 digits."))
	pin = str(pin) if pin else f"{pysecrets.randbelow(10**6):06d}"

	s = _settings()
	if not s.enabled:
		frappe.throw(_("Facebook signup is not enabled."))
	token = ""
	try:
		if s.mode == "broker":
			from huf.ai.whatsapp.management import _webhook_url

			callback = _webhook_url(_planned_gateway_name(gateway_name, phone_number_id))
			body = _exchange_via_broker(s, code, waba_id, phone_number_id, callback)
			token = str(body["access_token"])
			app_secret = str(body.get("webhook_signing_secret") or "")
			if not app_secret:
				raise SignupError(_("The broker did not return a webhook signing secret."))
		else:
			token = _exchange_code_with_meta(s, code)
			app_secret = _secret(s, "app_secret")

		warnings = [
			w
			for w in (
				_subscribe_app(s, waba_id, token),
				_register_phone(s, phone_number_id, token, pin),
			)
			if w
		]
		gw, verify_token = _save_gateway(
			token=token,
			app_secret=app_secret,
			app_id=(s.facebook_app_id or "").strip(),
			waba_id=waba_id,
			phone_number_id=phone_number_id,
			gateway_name=gateway_name,
		)
	except SignupError as exc:
		_log_error("WhatsApp Embedded Signup failed", exc, token, code, pin)
		frappe.throw(_clean(exc, token, code, pin))
	except frappe.ValidationError as exc:
		_log_error("WhatsApp Embedded Signup failed", exc, token, code, pin)
		raise
	except Exception as exc:
		_log_error("WhatsApp Embedded Signup failed", frappe.get_traceback(), token, code, pin)
		frappe.throw(_("Signup failed: {0}").format(_clean(exc, token, code, pin)))

	from huf.ai.whatsapp.management import _webhook_url

	out: dict[str, Any] = {
		"gateway": gw,
		"setup_stage": _setup_stage(gw),
		"webhook_url": _webhook_url(gw),
		"verify_token_hint": _hint(verify_token),
		"warnings": warnings,
	}
	if pin_generated:
		out["pin"] = pin
	return out
