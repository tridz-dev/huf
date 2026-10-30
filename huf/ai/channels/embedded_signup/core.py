# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared constants, helpers and the settings API of Meta Embedded Signup (see the package docstring).
"""

from __future__ import annotations

import hashlib
import re
import secrets as pysecrets
from typing import Any
from urllib.parse import urlparse

import frappe
from frappe import _

from huf.ai.secrets import redact as redact_obj
from huf.ai.whatsapp import token_check

SETTINGS = "Channel Embedded Signup Settings"
WABA_DOCTYPE = "Embedded Signup WABA"
MOD_PATH = "huf.ai.channels.embedded_signup"
BROKER_WEBHOOK_METHOD = f"{MOD_PATH}.broker_webhook"
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
