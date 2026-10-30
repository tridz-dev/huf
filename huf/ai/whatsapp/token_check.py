# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp access-token health check for one Gateway (read-only Graph calls).

``check_token_for_gateway`` resolves credentials the way the gateway adapter does
(Integration Settings credential rows, plus the linked WhatsApp Account in bridge
mode), asks Meta whether the token is still good, and returns a non-secret result.
The token and app secret are never returned, logged, or placed in cached data, and
``access_token=`` is redacted from any error text.

Graph shapes (checked against Meta docs unless marked UNVERIFIED):
* ``GET /debug_token?input_token=..&access_token={app_id}|{app_secret}`` ->
  ``{"data": {"is_valid", "type", "expires_at" (0 = never), "scopes": [..],
  "granular_scopes": [{"scope", "target_ids": [..]}], "error": {code, message}}}``.
  UNVERIFIED: the docs page was not retrievable; shape is from Meta's token-debugging guide.
* ``GET /{waba_id}/subscribed_apps`` -> ``{"data": [..], "paging": {}}``. Meta documents
  ``data`` only as "WhatsAppApplication nodes". UNVERIFIED: entry fields
  (``whatsapp_business_api_data.id`` for the app, ``subscribed_fields``); if absent we
  report only "some app is subscribed" and ``webhook_messages`` stays null.
* ``GET /{phone_number_id}?fields=display_phone_number,verified_name,quality_rating,
  messaging_limit_tier,name_status`` (UNVERIFIED: ``messaging_limit_tier`` availability
  depends on API version).
In the phone-number fallback (no app secret) scopes cannot be read, so ``missing_scopes``
is empty and ``token_type`` is null.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge

HTTP_TIMEOUT = 15
RESULT_TTL_SECONDS = 600
RATE_LIMIT_SECONDS = 10
REQUIRED_SCOPES = ("whatsapp_business_messaging", "whatsapp_business_management")
_PHONE_FIELDS = "display_phone_number,verified_name,quality_rating,messaging_limit_tier,name_status"

MSG_EXPIRED = "The access token has expired or was revoked."
MSG_PERMISSION = "The token can't access this phone number or business account."
MSG_APP_SECRET = "The app secret doesn't match this token's app. Check the App Secret in Meta app settings (Settings > Basic)."
MSG_TIMEOUT = "Meta didn't answer in time."
MSG_GENERIC = "Meta returned an unexpected error."

_REDACT_RE = re.compile(r"(access_token|input_token|client_secret)=[^&\s'\"]+", re.I)


def redact(text: Any, *secrets: str) -> str:
	out = _REDACT_RE.sub(lambda m: f"{m.group(1)}=[redacted]", str(text))
	for secret in secrets:
		if secret and len(secret) >= 4:
			out = out.replace(secret, "[redacted]")
	return out


def default_http_get(url: str, params: dict | None = None, headers: dict | None = None) -> Any:
	import requests

	return requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=False)


class _Timeout(Exception):
	pass


class _Transport(Exception):
	pass


def _call(http_get: Callable[..., Any], url: str, params=None, headers=None) -> tuple[int, dict]:
	"""Return (status, json-dict); raise _Timeout / _Transport without leaking URL or token."""
	try:
		resp = http_get(url, params=params, headers=headers)
	except Exception as exc:  # noqa: BLE001 - classified by name, text discarded
		names = {c.__name__ for c in type(exc).__mro__}
		if names & {"Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"}:
			raise _Timeout() from None
		raise _Transport() from None
	try:
		body = resp.json()
	except Exception:  # noqa: BLE001
		body = {}
	return int(getattr(resp, "status_code", 0) or 0), body if isinstance(body, dict) else {}


def _error_of(status: int, body: dict) -> dict | None:
	err = body.get("error") if isinstance(body.get("error"), dict) else None
	if err:
		return err
	if status >= 400 or status in (301, 302, 303, 307, 308):
		return {"code": status, "message": ""}
	return None


def _is_app_secret_mismatch(err: dict | None) -> bool:
	"""Graph code 100 whose text names appsecret_proof: the saved App Secret is wrong for this token."""
	if not isinstance(err, dict):
		return False
	return str(err.get("code")) == "100" and "appsecret_proof" in str(err.get("message") or "").lower()


def _is_bad_app_signature(err: dict | None) -> bool:
	"""Code 190 'signature' from debug_token: the App Secret (app token) is wrong, the input token may be fine."""
	if not isinstance(err, dict):
		return False
	return str(err.get("code")) == "190" and "signature" in str(err.get("message") or "").lower()


def _message_for_error(err: dict | None) -> str:
	if _is_app_secret_mismatch(err):
		return MSG_APP_SECRET
	return _message_for((err or {}).get("code"))


def _message_for(code: Any) -> str:
	try:
		code = int(code)
	except (TypeError, ValueError):
		return MSG_GENERIC
	if code == 190:
		return MSG_EXPIRED
	if code in (100, 10, 200, 803, 33) or 200 <= code <= 299:
		return MSG_PERMISSION
	return MSG_GENERIC


def _iso(epoch: Any) -> str | None:
	try:
		epoch = int(epoch)
	except (TypeError, ValueError):
		return None
	if epoch <= 0:
		return None
	return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty(source: str | None = None) -> dict[str, Any]:
	return {
		"success": True,
		"valid": None,
		"token_type": None,
		"expires_at": None,
		"missing_scopes": [],
		"waba_ids": [],
		"phone": None,
		"webhook_subscribed": None,
		"webhook_messages": None,
		"checked_at": _now_iso(),
		"source": source,
		"error_code": None,
		"message": "",
	}


def run_check(creds: dict[str, Any], http_get: Callable[..., Any] = default_http_get) -> dict[str, Any]:
	"""Pure check. ``creds``: token, base (graph root with version), phone_id, waba_id, app_id, app_secret."""
	token = creds.get("token") or ""
	secret = creds.get("app_secret") or ""
	base = creds["base"].rstrip("/")
	app_id = str(creds.get("app_id") or "").strip()
	phone_id = str(creds.get("phone_id") or "").strip()
	waba_id = str(creds.get("waba_id") or "").strip()
	bearer = {"Authorization": f"Bearer {token}"}
	secrets = (token, secret)

	use_debug = bool(app_id and secret)
	out = _empty("debug_token" if use_debug else "phone_number")
	try:
		if use_debug:
			status, body = _call(
				http_get,
				f"{base}/debug_token",
				params={"input_token": token, "access_token": f"{app_id}|{secret}"},
			)
			data = body.get("data") if isinstance(body.get("data"), dict) else {}
			err = _error_of(status, body) if not data else (data.get("error") or None)
			if not data and err is None:
				err = {"code": status, "message": ""}
			valid = bool(data.get("is_valid")) and not err
			out["valid"] = valid
			out["token_type"] = data.get("type") or None
			out["expires_at"] = _iso(data.get("expires_at"))
			scopes = {str(s) for s in data.get("scopes") or []}
			wabas: list[str] = []
			for gs in data.get("granular_scopes") or []:
				if not isinstance(gs, dict):
					continue
				scopes.add(str(gs.get("scope") or ""))
				if str(gs.get("scope") or "") in REQUIRED_SCOPES:
					for tid in gs.get("target_ids") or []:
						if str(tid) not in wabas:
							wabas.append(str(tid))
			out["waba_ids"] = wabas
			out["missing_scopes"] = [s for s in REQUIRED_SCOPES if s not in scopes] if valid else []
			if not valid:
				code = (err or {}).get("code")
				out["error_code"] = code
				if not data and _is_bad_app_signature(err):
					out["message"] = MSG_APP_SECRET
				else:
					out["message"] = _message_for_error(err) if err else MSG_EXPIRED
				return out
			if out["missing_scopes"]:
				out["message"] = "The token is missing: " + ", ".join(out["missing_scopes"]) + "."
		# phone number details (also the whole check in fallback mode)
		if phone_id:
			status, body = _call(
				http_get, f"{base}/{phone_id}", params={"fields": _PHONE_FIELDS}, headers=bearer
			)
			err = _error_of(status, body)
			if err:
				out["phone"] = None
				if not use_debug:
					out["valid"] = False
					out["error_code"] = err.get("code")
					out["message"] = _message_for_error(err)
					return out
				out["error_code"] = err.get("code")
				out["message"] = _message_for_error(err)
			else:
				out["phone"] = {
					"display": body.get("display_phone_number"),
					"verified_name": body.get("verified_name"),
					"quality": body.get("quality_rating"),
					"tier": body.get("messaging_limit_tier"),
				}
				if not use_debug:
					out["valid"] = True
		elif not use_debug:
			out["success"] = False
			out["error_code"] = "not_configured"
			out["message"] = "No phone number ID is configured for this gateway."
			return out

		# webhook subscription for the WABA
		target_waba = waba_id or (out["waba_ids"][0] if out["waba_ids"] else "")
		if target_waba and out["valid"]:
			try:
				status, body = _call(http_get, f"{base}/{target_waba}/subscribed_apps", headers=bearer)
			except (_Timeout, _Transport):
				status, body = 0, {}
			if _error_of(status, body) is None and isinstance(body.get("data"), list):
				entries = [e for e in body["data"] if isinstance(e, dict)]
				mine = entries
				if app_id:
					with_ids = [
						e for e in entries if isinstance(e.get("whatsapp_business_api_data"), dict)
					]
					if with_ids:
						mine = [e for e in with_ids if str(e["whatsapp_business_api_data"].get("id")) == app_id]
				out["webhook_subscribed"] = bool(mine)
				fields = None
				for e in mine:
					if isinstance(e.get("subscribed_fields"), list):
						fields = (fields or []) + [str(f) for f in e["subscribed_fields"]]
				out["webhook_messages"] = ("messages" in fields) if fields is not None else None
		return out
	except _Timeout:
		out.update(success=False, valid=None, error_code="timeout", message=MSG_TIMEOUT)
		return out
	except _Transport:
		out.update(success=False, valid=None, error_code="unreachable", message="Couldn't reach Meta.")
		return out


def resolve_credentials(gateway_name: str) -> dict[str, Any]:
	"""Credentials for the check, mirroring gateway_webhook.get_gateway_adapter. Raises frappe.ValidationError."""
	from huf.ai.gateway_webhook import _gateway_credentials

	gateway = frappe.get_doc("Gateway", gateway_name)
	if gateway.provider != "WhatsApp":
		raise frappe.ValidationError("Not a WhatsApp gateway.")
	creds = _gateway_credentials(gateway)
	account = {}
	account_name = (gateway.get("whatsapp_account") or "").strip()
	if account_name:
		acct = bridge.resolve_account(account_name)
		if acct and not acct.get("error"):
			account = acct
	token = (creds.get("access_token") or "").strip() or (account.get("token") or "")
	if not token:
		raise frappe.ValidationError("No access token is configured for this gateway.")
	version = (creds.get("graph_api_version") or "").strip() or account.get("version") or bridge.GRAPH_DEFAULT_VERSION
	root = bridge.graph_base_url(creds.get("graph_api_url") or "")
	if root == bridge.GRAPH_HOST and account.get("url"):
		root = account["url"]
	return {
		"token": token,
		"app_secret": (creds.get("app_secret") or "").strip(),
		"app_id": (creds.get("app_id") or "").strip() or str(account.get("app_id") or ""),
		"phone_id": (creds.get("phone_number_id") or "").strip() or str(account.get("phone_id") or ""),
		"waba_id": (creds.get("business_account_id") or creds.get("waba_id") or "").strip()
		or str(account.get("business_id") or ""),
		"base": f"{root}/{version}",
	}


def _result_key(gateway: str) -> str:
	return f"huf:wa_token_check:result:{gateway}"


def _stamp_key(gateway: str) -> str:
	return f"huf:wa_token_check:stamp:{gateway}"


def check_token_for_gateway(
	gateway_name: str, force: bool = False, http_get: Callable[..., Any] | None = None
) -> dict[str, Any]:
	if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
		return {"success": False, "error_code": "gateway_not_found", "message": "Choose a WhatsApp gateway."}
	cache = frappe.cache()
	if not force:
		cached = cache.get_value(_result_key(gateway_name), expires=True)
		if cached:
			return dict(cached, cached=True)
	if cache.get_value(_stamp_key(gateway_name), expires=True):
		return {
			"success": False,
			"error_code": "rate_limited",
			"message": "Please wait a few seconds before checking again.",
		}
	cache.set_value(_stamp_key(gateway_name), 1, expires_in_sec=RATE_LIMIT_SECONDS)
	try:
		creds = resolve_credentials(gateway_name)
	except frappe.ValidationError as exc:
		return {"success": False, "error_code": "not_configured", "message": redact(exc)}
	result = run_check(creds, http_get or default_http_get)
	if result.get("success"):
		cache.set_value(_result_key(gateway_name), result, expires_in_sec=RESULT_TTL_SECONDS)
	return dict(result, cached=False)
