"""Payment-link provider adapters + paid webhooks for WhatsApp Orders.

``PaymentProvider.create_link(amount, currency, reference, customer) -> {url, provider_ref}``.
``reference`` is the WhatsApp Order name. Credentials come from the Gateway's connected Integration Settings
(credential rows) with a site-config fallback; they are never logged. The ``WhatsApp Order`` doctype is owned by
the catalog WP, so it is only touched by name, guarded by ``frappe.db.exists("DocType", ...)``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import frappe
import requests

ORDER = "WhatsApp Order"
TIMEOUT = 20
STRIPE_TOLERANCE_SECONDS = 300


class PaymentError(Exception):
	pass


def _cred(gateway: Any, key: str) -> str:
	"""Read a credential by key: Integration Settings row first, then site config. Never logged."""
	try:
		gw = frappe.get_doc("Gateway", gateway) if isinstance(gateway, str) else gateway
		if gw and gw.integration_settings:
			int_doc = frappe.get_doc("Integration Settings", gw.integration_settings)
			for row in int_doc.credentials or []:
				if row.key == key:
					value = row.get_password("value") if hasattr(row, "get_password") else row.value
					if value:
						return str(value)
	except Exception:
		pass
	return str(frappe.conf.get(key) or "")


class PaymentProvider:
	name = "none"

	def __init__(self, gateway: Any = None):
		self.gateway = gateway

	def create_link(self, amount, currency: str, reference: str, customer: dict | None = None) -> dict[str, str]:
		raise NotImplementedError


class ERPNextProvider(PaymentProvider):
	name = "erpnext"

	def create_link(self, amount, currency, reference, customer=None):
		try:
			from erpnext.accounts.doctype.payment_request import payment_request as pr_mod
		except Exception as exc:
			raise PaymentError("erpnext_not_installed") from exc
		customer = customer or {}
		dt = customer.get("reference_doctype") or "Sales Order"
		pr = pr_mod.make_payment_request(
			dt=dt, dn=reference, party_type="Customer", party=customer.get("party"),
			recipient_id=customer.get("email"), mute_email=1, submit_doc=1, return_doc=1,
		)
		url = getattr(pr, "payment_url", None) or (pr.get_payment_url() if hasattr(pr, "get_payment_url") else "")
		if not url:
			raise PaymentError("no_payment_url")
		return {"url": str(url), "provider_ref": str(pr.name)}


class RazorpayProvider(PaymentProvider):
	name = "razorpay"

	def create_link(self, amount, currency, reference, customer=None):
		key, secret = _cred(self.gateway, "razorpay_key_id"), _cred(self.gateway, "razorpay_key_secret")
		if not key or not secret:
			raise PaymentError("razorpay_credentials_missing")
		customer = customer or {}
		body: dict[str, Any] = {
			"amount": int(round(float(amount) * 100)),
			"currency": currency,
			"reference_id": reference,
			"notes": {"reference": reference},
		}
		contact = {k: v for k, v in (("contact", customer.get("phone")), ("name", customer.get("name")), ("email", customer.get("email"))) if v}
		if contact:
			body["customer"] = contact
		res = requests.post("https://api.razorpay.com/v1/payment_links", json=body, auth=(key, secret), timeout=TIMEOUT)
		if res.status_code >= 400:
			raise PaymentError(f"razorpay_http_{res.status_code}")
		data = res.json()
		return {"url": data["short_url"], "provider_ref": data["id"]}


class StripeProvider(PaymentProvider):
	name = "stripe"

	def create_link(self, amount, currency, reference, customer=None):
		secret = _cred(self.gateway, "stripe_secret_key")
		if not secret:
			raise PaymentError("stripe_credentials_missing")
		customer = customer or {}
		form = {
			"mode": "payment",
			"success_url": customer.get("success_url") or "https://wa.me/",
			"line_items[0][quantity]": 1,
			"line_items[0][price_data][currency]": currency.lower(),
			"line_items[0][price_data][unit_amount]": int(round(float(amount) * 100)),
			"line_items[0][price_data][product_data][name]": f"Order {reference}",
			"metadata[reference]": reference,
			"client_reference_id": reference,
		}
		if customer.get("email"):
			form["customer_email"] = customer["email"]
		res = requests.post("https://api.stripe.com/v1/checkout/sessions", data=form, auth=(secret, ""), timeout=TIMEOUT)
		if res.status_code >= 400:
			raise PaymentError(f"stripe_http_{res.status_code}")
		data = res.json()
		return {"url": data["url"], "provider_ref": data["id"]}


PROVIDERS = {"erpnext": ERPNextProvider, "razorpay": RazorpayProvider, "stripe": StripeProvider}


def get_provider(gateway: Any) -> PaymentProvider:
	gw = frappe.get_doc("Gateway", gateway) if isinstance(gateway, str) else gateway
	cls = PROVIDERS.get(str(getattr(gw, "payment_provider", "") or "none"))
	if not cls:
		raise PaymentError("no_payment_provider")
	return cls(gw)


def create_payment_link(order: str, gateway: str | None = None) -> dict[str, str]:
	"""Create a payment link for a WhatsApp Order and store it on the order."""
	if not frappe.db.exists("DocType", ORDER):
		raise PaymentError("order_doctype_missing")
	doc = frappe.get_doc(ORDER, order)
	gateway = gateway or (frappe.db.get_value("Channel Conversation", doc.conversation, "gateway") if doc.conversation else None)
	if not gateway:
		raise PaymentError("no_gateway")
	link = get_provider(gateway).create_link(doc.total, doc.currency, doc.name, {"phone": _handle(doc)})
	frappe.db.set_value(ORDER, doc.name, "payment_link", link["url"])
	return link


def _handle(doc) -> str:
	if getattr(doc, "conversation", None):
		return frappe.db.get_value("Channel Conversation", doc.conversation, "contact_handle") or ""
	return ""


# ------------------------------------------------------------------ signatures

def verify_razorpay_signature(body: bytes, signature: str, secret: str) -> bool:
	if not (secret and signature):
		return False
	expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, signature.strip())


def verify_stripe_signature(body: bytes, header: str, secret: str, now: float | None = None) -> bool:
	if not (secret and header):
		return False
	parts: dict[str, list[str]] = {}
	for item in header.split(","):
		k, _, v = item.strip().partition("=")
		parts.setdefault(k, []).append(v)
	try:
		ts = int(parts.get("t", [""])[0])
	except ValueError:
		return False
	if abs((now if now is not None else time.time()) - ts) > STRIPE_TOLERANCE_SECONDS:
		return False
	expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
	return any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", []))


# ------------------------------------------------------------------ paid handling

def mark_paid(order: str, gateway: str | None = None) -> dict[str, Any]:
	"""Mark the order Paid (idempotent) and send the confirmation once."""
	if not frappe.db.exists("DocType", ORDER) or not frappe.db.exists(ORDER, order):
		return {"status": "ignored"}
	doc = frappe.get_doc(ORDER, order)
	if doc.payment_status == "Paid":
		return {"status": "already_paid"}
	values = {"payment_status": "Paid"}
	field = frappe.get_meta(ORDER).get_field("status")
	if field and "Paid" in (field.options or "").split("\n"):
		values["status"] = "Paid"
	frappe.db.set_value(ORDER, order, values)
	sent = _send_confirmation(doc, gateway)
	return {"status": "paid", "confirmation": sent}


def _send_confirmation(doc, gateway: str | None) -> str:
	if not getattr(doc, "conversation", None):
		return "no_conversation"
	from huf.ai.channels import reply_api

	gw = gateway or frappe.db.get_value("Channel Conversation", doc.conversation, "gateway")
	template = frappe.db.get_value("Gateway", gw, "order_confirmed_template") if gw else None
	total = f"{doc.currency} {doc.total}"
	if template:
		res = reply_api.deliver_reply(doc.conversation, template=template, params=[doc.name, total])
	else:
		res = reply_api.deliver_reply(doc.conversation, text=f"Payment received for order {doc.name} ({total}). Thank you!")
	return res.get("status", "unknown")


def _request_body() -> bytes:
	return frappe.request.get_data() if getattr(frappe, "request", None) else b""


def _gateway_secret(gateway: str, key: str) -> str:
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return ""
	return _cred(gateway, key)


def process_razorpay(body: bytes, signature: str, gateway: str) -> dict[str, Any]:
	if not verify_razorpay_signature(body, signature, _gateway_secret(gateway, "razorpay_webhook_secret")):
		return {"ok": False, "error": "invalid_signature"}
	event = json.loads(body or b"{}")
	if event.get("event") != "payment_link.paid":
		return {"ok": True, "status": "ignored"}
	entity = ((event.get("payload") or {}).get("payment_link") or {}).get("entity") or {}
	ref = entity.get("reference_id") or (entity.get("notes") or {}).get("reference")
	return {"ok": True, **mark_paid(ref, gateway)} if ref else {"ok": True, "status": "ignored"}


def process_stripe(body: bytes, signature: str, gateway: str) -> dict[str, Any]:
	if not verify_stripe_signature(body, signature, _gateway_secret(gateway, "stripe_webhook_secret")):
		return {"ok": False, "error": "invalid_signature"}
	event = json.loads(body or b"{}")
	if event.get("type") not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
		return {"ok": True, "status": "ignored"}
	obj = (event.get("data") or {}).get("object") or {}
	if obj.get("payment_status") not in (None, "paid"):
		return {"ok": True, "status": "ignored"}
	ref = (obj.get("metadata") or {}).get("reference") or obj.get("client_reference_id")
	return {"ok": True, **mark_paid(ref, gateway)} if ref else {"ok": True, "status": "ignored"}


def _reject(result: dict[str, Any]) -> dict[str, Any]:
	if not result.get("ok"):
		frappe.local.response["http_status_code"] = 401
	return result


@frappe.whitelist(allow_guest=True, methods=["POST"])
def razorpay_webhook(gateway: str | None = None) -> dict[str, Any]:
	sig = frappe.get_request_header("X-Razorpay-Signature") or ""
	return _reject(process_razorpay(_request_body(), sig, gateway or ""))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def stripe_webhook(gateway: str | None = None) -> dict[str, Any]:
	sig = frappe.get_request_header("Stripe-Signature") or ""
	return _reject(process_stripe(_request_body(), sig, gateway or ""))
