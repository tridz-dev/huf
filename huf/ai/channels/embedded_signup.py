# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Meta Embedded Signup for WhatsApp (Huf as Tech Provider).

Three modes (``Channel Embedded Signup Settings.mode``):

* ``direct``: this site owns the Facebook app; the code from the FB JS SDK is exchanged here.
* ``broker``: a central Huf Cloud broker owns the app; this site posts the code to it and gets
  the business token back.
* ``broker_server``: this site IS the broker; it exposes :func:`broker_exchange` to tenants.

The business token is written to the Integration Settings credential store (Password field) and
never returned, logged or placed in an Error Log. All Graph calls use ``requests`` with timeouts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets as pysecrets
import time
from typing import Any
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.secrets import redact as redact_obj
from huf.ai.whatsapp import token_check

SETTINGS = "Channel Embedded Signup Settings"
WABA_DOCTYPE = "Embedded Signup WABA"
BROKER_WEBHOOK_METHOD = "huf.ai.channels.embedded_signup.broker_webhook"
FORWARD_ATTEMPTS = 3
FORWARD_BACKOFF_SECONDS = (1, 4)
GRAPH_ROOT = "https://graph.facebook.com"
HTTP_TIMEOUT = 20
ADMIN_ROLES = ("System Manager", "Huf Admin")
_ID_RE = re.compile(r"^\d{5,30}$")
_PIN_RE = re.compile(r"^\d{6}$")
_DUMMY_HASH = hashlib.sha256(b"huf-embedded-signup-dummy").hexdigest()


class SignupError(Exception):
	"""Expected failure; message is safe to show (already redacted)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def hash_api_key(key: str) -> str:
	return hashlib.sha256((key or "").encode()).hexdigest()


def _require_admin() -> None:
	roles = set(frappe.get_roles() or [])
	if roles.intersection(ADMIN_ROLES):
		return
	try:
		from huf.permissions import has_capability

		if has_capability(frappe.session.user, "system.integrations.manage"):
			return
	except Exception:
		pass
	raise frappe.PermissionError(_("System Manager or Huf Admin role required"))


def _settings():
	return frappe.get_single(SETTINGS)


def _secret(settings, field: str) -> str:
	try:
		return str(settings.get_password(field, raise_exception=False) or "")
	except Exception:
		return ""


def _graph(settings) -> str:
	return f"{GRAPH_ROOT}/{(settings.graph_version or 'v21.0').strip()}"


def _is_https_ok(url: str) -> bool:
	return urlparse(url or "").scheme == "https" or bool(frappe.conf.get("developer_mode"))


def require_https_url(url: str, label: str) -> None:
	if not _is_https_ok(url):
		frappe.throw(_("{0} must use https.").format(label))


def _clean(text: Any, *secret_values: str) -> str:
	"""Redact a message for logs and users."""
	return str(redact_obj(token_check.redact(text, *secret_values)))[:500]


def _log_error(title: str, text: Any, *secret_values: str) -> None:
	try:
		frappe.log_error(title=title, message=_clean(text, *secret_values))
	except Exception:
		pass


def _graph_error(resp, *secret_values: str) -> str:
	"""A short, safe description of a Graph error response."""
	try:
		err = (resp.json() or {}).get("error") or {}
		msg = err.get("message") or f"HTTP {resp.status_code}"
		code = err.get("code")
		return _clean(f"{msg} (code {code})" if code else msg, *secret_values)
	except Exception:
		return f"HTTP {getattr(resp, 'status_code', '?')}"


def _digits(value: Any, label: str) -> str:
	v = str(value or "").strip()
	if not _ID_RE.match(v):
		frappe.throw(_("{0} is not valid.").format(label))
	return v


def _request_is_https() -> bool:
	if frappe.conf.get("developer_mode"):
		return True
	req = getattr(frappe.local, "request", None)
	if req is None:
		return False
	proto = (req.headers.get("X-Forwarded-Proto") or req.scheme or "").split(",")[0].strip().lower()
	return proto == "https"


# ---------------------------------------------------------------------------
# config for the UI (no secrets)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_signup_config() -> dict[str, Any]:
	_require_admin()
	s = _settings()
	ready = bool(s.enabled and s.facebook_app_id and s.config_id)
	if s.mode == "direct":
		ready = ready and bool(_secret(s, "app_secret"))
	elif s.mode == "broker":
		ready = ready and bool(s.broker_url and _secret(s, "broker_api_key"))
	else:
		ready = ready and bool(_secret(s, "app_secret"))
	return {
		"enabled": bool(ready and s.mode in ("direct", "broker", "broker_server")),
		"app_id": s.facebook_app_id or "",
		"config_id": s.config_id or "",
		"graph_version": s.graph_version or "v21.0",
	}


@frappe.whitelist()
def get_settings_admin() -> dict[str, Any]:
	"""Settings for the admin panel; secrets are reported only as booleans."""
	_require_admin()
	s = _settings()
	return {
		"enabled": bool(s.enabled),
		"mode": s.mode or "direct",
		"facebook_app_id": s.facebook_app_id or "",
		"config_id": s.config_id or "",
		"graph_version": s.graph_version or "v21.0",
		"broker_url": s.broker_url or "",
		"tenant_id": s.tenant_id or "",
		"app_secret_set": bool(_secret(s, "app_secret")),
		"broker_api_key_set": bool(_secret(s, "broker_api_key")),
		"broker_verify_token_set": bool(_secret(s, "broker_verify_token")),
		"broker_callback_url": f"{frappe.utils.get_url().rstrip('/')}/api/method/{BROKER_WEBHOOK_METHOD}",
	}


_EDITABLE = ("enabled", "mode", "facebook_app_id", "config_id", "graph_version", "broker_url", "tenant_id")
_WRITE_ONLY = ("app_secret", "broker_api_key", "broker_verify_token")


@frappe.whitelist(methods=["POST"])
def save_settings(values: Any) -> dict[str, Any]:
	"""Update the Single. Secret fields are written only when a non-empty value is sent."""
	_require_admin()
	if isinstance(values, str):
		import json

		values = json.loads(values or "{}")
	values = values or {}
	s = _settings()
	for key in _EDITABLE:
		if key in values:
			s.set(key, values[key])
	for key in _WRITE_ONLY:
		v = str(values.get(key) or "").strip()
		if v:
			s.set(key, v)
	s.save()
	return get_settings_admin()


@frappe.whitelist(methods=["POST"])
def create_tenant_key(tenant_id: str, site_url: str | None = None) -> dict[str, Any]:
	"""broker_server: add/rotate a tenant. The plaintext key is returned once; only its hash is stored."""
	_require_admin()
	tenant_id = (tenant_id or "").strip()
	if not re.match(r"^[A-Za-z0-9_.-]{2,64}$", tenant_id):
		frappe.throw(_("Tenant ID is not valid."))
	key = "hsk_" + pysecrets.token_urlsafe(32)
	s = _settings()
	row = next((r for r in s.allowed_tenants or [] if r.tenant_id == tenant_id), None)
	if row is None:
		row = s.append("allowed_tenants", {"tenant_id": tenant_id, "enabled": 1})
	row.api_key_hash = hash_api_key(key)
	if site_url:
		row.site_url = site_url
	s.save()
	return {"tenant_id": tenant_id, "api_key": key}


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


# ---------------------------------------------------------------------------
# broker_server
# ---------------------------------------------------------------------------
def _audit(tenant_id: str, outcome: str, reason: str = "", waba_id: str = "") -> None:
	"""Audit row per exchange (never the code or token). Committed so rejects survive the thrown error."""
	try:
		ip = getattr(frappe.local, "request_ip", "") or ""
		frappe.get_doc(
			{
				"doctype": "Embedded Signup Audit",
				"tenant_id": (tenant_id or "")[:140],
				"outcome": outcome,
				"reason": reason[:140],
				"waba_id": waba_id[:140],
				"ip_address": ip[:140],
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		pass


def _derive_signing_secret(settings, tenant_id: str) -> str:
	return hmac.new(
		_secret(settings, "app_secret").encode(), f"tenant:{tenant_id}".encode(), hashlib.sha256
	).hexdigest()


def _callback_ok(site_url: str | None, callback_url: str) -> bool:
	"""https (developer mode excepted) and the same host as the tenant's registered site_url."""
	cb = urlparse(callback_url or "")
	site = urlparse(site_url or "")
	if not site.hostname or not cb.hostname or cb.hostname.lower() != site.hostname.lower():
		return False
	if cb.scheme not in ("https", "http") or (cb.port or 0) != (site.port or 0):
		return False
	return cb.scheme == "https" or bool(frappe.conf.get("developer_mode"))


def _record_waba(tenant_id: str, waba_id: str, phone_number_id: str, callback_url: str) -> None:
	if frappe.db.exists(WABA_DOCTYPE, waba_id):
		doc = frappe.get_doc(WABA_DOCTYPE, waba_id)
		doc.phone_number_id = phone_number_id or doc.phone_number_id
		doc.callback_url = callback_url or doc.callback_url
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": WABA_DOCTYPE,
				"tenant_id": tenant_id,
				"waba_id": waba_id,
				"phone_number_id": phone_number_id,
				"callback_url": callback_url,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()


def _authenticate_tenant(settings, tenant_id: str, key: str):
	"""Constant-time check of the bearer key against the stored hash. Returns the tenant row or None."""
	row = next(
		(r for r in settings.allowed_tenants or [] if r.tenant_id == tenant_id and r.enabled), None
	)
	stored = (row.api_key_hash if row else "") or _DUMMY_HASH
	ok = hmac.compare_digest(hash_api_key(key), stored)
	return row if (ok and row and row.api_key_hash) else None


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=3600)
def broker_exchange() -> dict[str, Any]:
	"""broker_server mode: exchange a tenant's signup code for a business token (HTTPS only)."""
	s = _settings()
	req = frappe.local.request
	tenant_id = (req.headers.get("X-Huf-Tenant") or "").strip()
	auth = req.headers.get("Authorization") or ""
	key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""

	def reject(reason: str, exc=frappe.AuthenticationError, status: str = "Rejected"):
		_audit(tenant_id, status, reason)
		frappe.throw(_("Not permitted"), exc)

	if not (s.enabled and s.mode == "broker_server"):
		reject("broker_disabled", frappe.PermissionError)
	if not _request_is_https():
		reject("https_required", frappe.PermissionError)
	tenant_row = _authenticate_tenant(s, tenant_id, key) if tenant_id and key else None
	if tenant_row is None:
		reject("bad_credentials")

	form = frappe.form_dict
	code = str(form.get("code") or "").strip()
	waba_id = str(form.get("waba_id") or "").strip()
	if not code or (waba_id and not _ID_RE.match(waba_id)):
		reject("bad_request", frappe.ValidationError)
	phone_number_id = str(form.get("phone_number_id") or "").strip()
	if phone_number_id and not _ID_RE.match(phone_number_id):
		reject("bad_request", frappe.ValidationError)
	callback_url = str(form.get("callback_url") or "").strip()
	if callback_url and not _callback_ok(tenant_row.site_url, callback_url):
		reject("bad_callback_url", frappe.ValidationError)
	if waba_id:
		owner = frappe.db.get_value(WABA_DOCTYPE, waba_id, "tenant_id")
		if owner and owner != tenant_id:
			reject("waba_owned_by_other_tenant", frappe.PermissionError)
	try:
		token = _exchange_code_with_meta(s, code)
	except SignupError as exc:
		_audit(tenant_id, "Failed", "meta_exchange_failed", waba_id)
		_log_error("Embedded Signup broker exchange failed", exc, code)
		frappe.throw(_clean(exc, code), frappe.ValidationError)
	if waba_id:
		_record_waba(tenant_id, waba_id, phone_number_id, callback_url)
	_audit(tenant_id, "Success", "", waba_id)
	# Never hand out the real app secret: the tenant gets a per-tenant derived signing secret
	# (the broker's webhook forwarder re-signs forwarded events with it).
	return {"access_token": token, "webhook_signing_secret": _derive_signing_secret(s, tenant_id)}


# ---------------------------------------------------------------------------
# broker_server: Meta webhook -> owning tenant
# ---------------------------------------------------------------------------
def _sign(secret: str, body: bytes) -> str:
	return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _broker_signature_ok(secret: str, body: bytes, header: str) -> bool:
	if not secret or not header or not header.startswith("sha256="):
		return False
	return hmac.compare_digest(header.encode(), _sign(secret, body).encode())


def _split_by_tenant(settings, payload: dict) -> tuple[list[tuple[str, str, dict]], list[str]]:
	"""Returns ([(tenant_id, callback_url, tenant_payload)], dropped_waba_ids)."""
	enabled = {r.tenant_id: r for r in settings.allowed_tenants or [] if r.enabled}
	groups: dict[str, dict[str, Any]] = {}
	dropped: list[str] = []
	for entry in payload.get("entry") or []:
		waba = str(entry.get("id") or "") if isinstance(entry, dict) else ""
		row = frappe.db.get_value(WABA_DOCTYPE, waba, ["tenant_id", "callback_url"], as_dict=True) if waba else None
		tenant = enabled.get(row.tenant_id) if row else None
		if not row or tenant is None or not row.callback_url or not _callback_ok(tenant.site_url, row.callback_url):
			dropped.append(waba[:40])
			continue
		g = groups.setdefault(row.tenant_id, {"url": row.callback_url, "entries": []})
		g["entries"].append(entry)
	out = []
	for tenant_id, g in groups.items():
		tp = {k: v for k, v in payload.items() if k != "entry"}
		tp["entry"] = g["entries"]
		out.append((tenant_id, g["url"], tp))
	return out, dropped


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def broker_webhook() -> Any:
	"""broker_server: Meta's app-level webhook. Verifies, splits per owning tenant, forwards async."""
	s = _settings()
	req = frappe.request
	if not (s.enabled and s.mode == "broker_server"):
		frappe.local.response.http_status_code = 403
		return {"success": False}

	if req.method == "GET":
		token = _secret(s, "broker_verify_token")
		given = str(req.args.get("hub.verify_token") or "")
		if (
			token
			and str(req.args.get("hub.mode") or "subscribe") == "subscribe"
			and hmac.compare_digest(given.encode(), token.encode())
		):
			frappe.local.response.update(
				{"type": "txt", "doctype": "gateway-callback", "result": str(req.args.get("hub.challenge") or "")}
			)
			return None
		frappe.local.response.http_status_code = 403
		return {"success": False}

	body = req.get_data() or b""
	if not _broker_signature_ok(_secret(s, "app_secret"), body, req.headers.get("X-Hub-Signature-256") or ""):
		_audit("", "Rejected", "bad_webhook_signature")
		frappe.local.response.http_status_code = 401
		return {"success": False}
	try:
		payload = json.loads(body)
		if not isinstance(payload, dict):
			raise ValueError
	except ValueError:
		frappe.local.response.http_status_code = 400
		return {"success": False}

	parts, dropped = _split_by_tenant(s, payload)
	for tenant_id, url, tp in parts:
		raw = json.dumps(tp, separators=(",", ":"), ensure_ascii=False).encode()
		frappe.enqueue(
			f"{MOD_PATH}.forward_to_tenant",
			queue="short",
			enqueue_after_commit=False,
			tenant_id=tenant_id,
			url=url,
			body=raw.decode(),
			signature=_sign(_derive_signing_secret(s, tenant_id), raw),
			entries=len(tp["entry"]),
		)
	for waba in dropped:
		_audit("", "Dropped", "unknown_waba", waba)
	return {"success": True, "forwarded": len(parts), "dropped": len(dropped)}


MOD_PATH = "huf.ai.channels.embedded_signup"


def forward_to_tenant(tenant_id: str, url: str, body: str, signature: str, entries: int = 0, sleep=time.sleep) -> bool:
	"""Background job: POST the re-signed payload to the tenant, up to 3 attempts with backoff.

	Only counts and ids are audited; the body is never logged.
	"""
	status = "exception"
	for attempt in range(FORWARD_ATTEMPTS):
		try:
			resp = requests.post(
				url,
				data=body.encode(),
				headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
				timeout=HTTP_TIMEOUT,
			)
			status = str(resp.status_code)
			if resp.status_code < 400:
				_audit(tenant_id, "Forwarded", f"entries={entries}")
				return True
			if resp.status_code < 500 and resp.status_code != 429:
				break  # tenant rejected it; retrying will not help
		except Exception:
			status = "exception"
		if attempt < FORWARD_ATTEMPTS - 1:
			sleep(FORWARD_BACKOFF_SECONDS[min(attempt, len(FORWARD_BACKOFF_SECONDS) - 1)])
	_audit(tenant_id, "Failed", f"forward_failed:{status}:entries={entries}")
	return False
