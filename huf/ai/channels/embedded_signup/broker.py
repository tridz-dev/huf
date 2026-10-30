# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Embedded Signup, broker_server side: tenant exchange and the Meta webhook fan-out."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.channels.embedded_signup.core import (
	_DUMMY_HASH,
	_ID_RE,
	FORWARD_ATTEMPTS,
	FORWARD_BACKOFF_SECONDS,
	HTTP_TIMEOUT,
	MOD_PATH,
	WABA_DOCTYPE,
	SignupError,
	_clean,
	_log_error,
	_request_is_https,
	_secret,
	_settings,
	hash_api_key,
)
from huf.ai.channels.embedded_signup.tenant import _exchange_code_with_meta

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


def _verify_handshake(s) -> Any:
	"""Meta's GET verification handshake: echo ``hub.challenge`` when the verify token matches (no writes)."""
	req = frappe.request
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


def _forward_webhook(s) -> Any:
	"""Meta's signed POST: verify the signature, split per owning tenant, forward async."""
	req = frappe.request
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


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def broker_webhook() -> Any:
	"""broker_server: Meta's app-level webhook. GET answers the verify handshake; POST is verified, split and forwarded."""
	s = _settings()
	if not (s.enabled and s.mode == "broker_server"):
		frappe.local.response.http_status_code = 403
		return {"success": False}
	if frappe.request.method == "GET":
		return _verify_handshake(s)
	return _forward_webhook(s)


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
