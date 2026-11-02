# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Keep a WhatsApp credential, its Gateways and frappe_whatsapp's WhatsApp Account in step.

The WhatsApp credential (Integration Settings, service ``whatsapp``) is the single place a user
enters Meta details. When it is saved:

1. The values are checked against Meta (token valid, phone number exists, phone number belongs to
   the business account). A definite "wrong value" answer refuses the save; Meta being unreachable
   only warns.
2. When frappe_whatsapp is installed, a WhatsApp Account is created or updated from the credential
   (matched by phone number ID). It is never marked as frappe_whatsapp's default incoming/outgoing
   account and never carries the webhook verify token, so frappe_whatsapp's own webhook cannot
   verify against Meta in place of Huf's.
3. Every Gateway using the credential gets the phone number ID, business account ID and account link.
4. The Meta app is subscribed to the business account's webhooks, and templates are synced.

Steps 2 to 4 are best effort: they never block the save and never raise.
"""

from __future__ import annotations

from typing import Any, Callable

import frappe
from frappe import _

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import token_check

SERVICE = "whatsapp"
ACCOUNT_DOCTYPE = "WhatsApp Account"


def credentials_of(doc) -> dict[str, str]:
	"""Plain credential values of an Integration Settings doc (secrets decrypted)."""
	values = {}
	for row in doc.credentials or []:
		try:
			value = row.get_password("value") if row.name else row.value
		except Exception:
			value = row.value
		values[row.key] = str(value or "").strip()
	return values


def validate_credential(doc) -> None:
	"""Integration Settings ``validate``: every required WhatsApp field must be filled in."""
	if doc.service != SERVICE or _skip_meta():
		return
	from huf.ai.gateway_adapters.registered import get_adapter_class

	present = {row.key for row in doc.credentials or [] if str(row.value or "").strip()}
	missing = [f.label for f in get_adapter_class("whatsapp").credential_schema.fields if f.required and f.key not in present]
	if missing:
		frappe.throw(_("WhatsApp credentials need: {0}.").format(", ".join(missing)))


def _base(creds: dict[str, str]) -> str:
	version = creds.get("graph_api_version") or bridge.GRAPH_DEFAULT_VERSION
	return f"{bridge.graph_base_url(creds.get('graph_api_url') or '')}/{version}"


def verify_with_meta(creds: dict[str, str], http_get: Callable[..., Any] | None = None) -> dict[str, Any]:
	"""Check the credential against Meta. Raises ``frappe.ValidationError`` on a definite mismatch.

	Returns the phone details (``display``, ``verified_name``) when Meta answered, ``{}`` when Meta
	could not be reached (the caller warns instead of refusing).
	"""
	http_get = http_get or token_check.default_http_get
	phone_id = creds.get("phone_number_id") or ""
	waba_id = creds.get("business_account_id") or ""
	result = token_check.run_check(
		{
			"token": creds.get("access_token") or "",
			"app_secret": creds.get("app_secret") or "",
			"app_id": creds.get("app_id") or "",
			"phone_id": phone_id,
			"waba_id": waba_id,
			"base": _base(creds),
		},
		http_get,
	)
	if not result.get("success"):
		return {}  # timeout / unreachable: never refuse a save because Meta is down
	if result.get("valid") is False:
		frappe.throw(_("Meta rejected these credentials: {0}").format(result.get("message") or token_check.MSG_EXPIRED))
	if not result.get("phone"):
		frappe.throw(
			_("Meta doesn't know phone number ID {0}, or the access token can't use it. {1}").format(
				phone_id, result.get("message") or ""
			).strip()
		)
	if waba_id:
		wabas = result.get("waba_ids") or []
		if wabas and waba_id not in wabas:
			frappe.throw(
				_("The access token can't manage WhatsApp Business Account {0}. Check the business account ID.").format(
					waba_id
				)
			)
		numbers = _waba_phone_ids(creds, http_get)
		if numbers is not None and phone_id not in numbers:
			frappe.throw(
				_("Phone number ID {0} doesn't belong to WhatsApp Business Account {1}.").format(phone_id, waba_id)
			)
	return dict(result["phone"])


def _waba_phone_ids(creds: dict[str, str], http_get: Callable[..., Any]) -> set[str] | None:
	"""Phone number ids of the business account, or None when Meta did not give a usable answer."""
	try:
		status, body = token_check._call(
			http_get,
			f"{_base(creds)}/{creds['business_account_id']}/phone_numbers",
			params={"fields": "id"},
			headers={"Authorization": f"Bearer {creds.get('access_token') or ''}"},
		)
	except Exception:
		return None
	err = token_check._error_of(status, body)
	if err:
		code = err.get("code")
		if str(code) in ("100", "190") or token_check._message_for(code) == token_check.MSG_PERMISSION:
			frappe.throw(
				_("Meta couldn't open WhatsApp Business Account {0} with this token: {1}").format(
					creds["business_account_id"], token_check._message_for(code)
				)
			)
		return None
	data = body.get("data")
	if not isinstance(data, list):
		return None
	return {str(row.get("id")) for row in data if isinstance(row, dict) and row.get("id")}


def _account_label(creds: dict[str, str], phone: dict[str, Any]) -> str:
	name = str(phone.get("verified_name") or "").strip()
	display = str(phone.get("display") or "").strip()
	label = " ".join(p for p in (name, display) if p) or f"WhatsApp {creds['phone_number_id']}"
	return label[:140]


def upsert_account(creds: dict[str, str], phone: dict[str, Any]) -> str | None:
	"""Create or update the WhatsApp Account for this phone number. Returns its name (None without frappe_whatsapp)."""
	if not bridge.is_available():
		return None
	phone_id = creds["phone_number_id"]
	values = {
		"phone_id": phone_id,
		"business_id": creds.get("business_account_id") or "",
		"app_id": creds.get("app_id") or "",
		"url": bridge.GRAPH_HOST,
		"version": creds.get("graph_api_version") or bridge.GRAPH_DEFAULT_VERSION,
		"status": "Active",
	}
	existing = frappe.db.get_value(ACCOUNT_DOCTYPE, {"phone_id": phone_id}, "name")
	if existing:
		doc = frappe.get_doc(ACCOUNT_DOCTYPE, existing)
		doc.update(values)
	else:
		label = _account_label(creds, phone)
		if frappe.db.exists(ACCOUNT_DOCTYPE, label):
			label = f"{label} ({phone_id})"[:140]
		doc = frappe.get_doc({"doctype": ACCOUNT_DOCTYPE, "account_name": label, **values})
	doc.token = creds.get("access_token") or ""
	doc.flags.ignore_permissions = True
	doc.save() if existing else doc.insert()
	return doc.name


def link_gateways(settings_name: str, creds: dict[str, str], account: str | None) -> list[str]:
	"""Copy the number, business account and account link onto every Gateway using this credential."""
	linked = []
	for name in frappe.get_all("Gateway", filters={"integration_settings": settings_name, "provider": "WhatsApp"}, pluck="name"):
		updates: dict[str, Any] = {
			"phone_number_id": creds.get("phone_number_id") or "",
			"whatsapp_business_account_id": creds.get("business_account_id") or "",
		}
		if account:
			updates["whatsapp_account"] = account
		frappe.db.set_value("Gateway", name, updates, update_modified=False)
		linked.append(name)
	return linked


def subscribe_app(creds: dict[str, str], http_post: Callable[..., Any] | None = None) -> bool:
	"""Subscribe the Meta app to the business account's webhooks (``POST /{waba}/subscribed_apps``)."""
	waba_id = creds.get("business_account_id") or ""
	if not waba_id:
		return False
	if http_post is None:
		import requests

		http_post = requests.post
	try:
		resp = http_post(
			f"{_base(creds)}/{waba_id}/subscribed_apps",
			headers={"Authorization": f"Bearer {creds.get('access_token') or ''}"},
			timeout=token_check.HTTP_TIMEOUT,
		)
		body = resp.json() if hasattr(resp, "json") else {}
	except Exception as exc:
		frappe.logger("huf.whatsapp").warning(f"WhatsApp app subscription failed: {token_check.redact(exc)}")
		return False
	return bool(isinstance(body, dict) and body.get("success"))


def sync_templates_job(account: str) -> None:
	"""Background: pull the account's templates from Meta (best effort)."""
	try:
		bridge.sync_templates(account)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "WhatsApp template sync after credential save failed")


def _skip_meta() -> bool:
	"""Unit tests skip this whole module's save-time behaviour unless a test opts in.

	Existing fixtures save WhatsApp credentials with only the four runtime keys, choose direct or bridge
	mode explicitly, and must never reach Meta.
	"""
	return bool(getattr(frappe.flags, "in_test", False)) and not getattr(frappe.flags, "huf_whatsapp_credential_checks", False)


def on_credential_update(doc) -> dict[str, Any]:
	"""Integration Settings ``on_update`` hook for the WhatsApp service."""
	if doc.service != SERVICE or not doc.is_active or _skip_meta():
		return {}
	creds = credentials_of(doc)
	if not creds.get("phone_number_id") or not creds.get("access_token"):
		return {}
	phone = verify_with_meta(creds)
	if not phone:
		frappe.msgprint(
			_("Saved, but Meta couldn't be reached to check these credentials. Save again later to verify them."),
			indicator="orange",
			alert=True,
		)

	account = None
	try:
		account = upsert_account(creds, phone)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "WhatsApp Account sync from credential failed")
	gateways = link_gateways(doc.name, creds, account)

	subscribed = subscribe_app(creds)
	if account:
		frappe.enqueue(
			"huf.ai.whatsapp.credential_sync.sync_templates_job",
			account=account,
			enqueue_after_commit=True,
			queue="short",
		)
	return {"account": account, "gateways": gateways, "subscribed": subscribed, "phone": phone}


def account_for_phone(phone_number_id: str) -> str | None:
	"""The WhatsApp Account carrying this phone number ID, when frappe_whatsapp is installed."""
	if not phone_number_id or _skip_meta() or not bridge.is_available():
		return None
	return frappe.db.get_value(ACCOUNT_DOCTYPE, {"phone_id": phone_number_id}, "name")
