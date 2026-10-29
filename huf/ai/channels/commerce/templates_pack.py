"""Utility template pack for commerce events (order / delivery / invoice / payment / cart)."""

from __future__ import annotations

from typing import Any

import frappe

TEMPLATES_PACK: list[dict[str, Any]] = [
	{"name": "order_confirmed", "body": "Hi, your order {{1}} for {{2}} is confirmed. Thank you for shopping with us!", "samples": ["ORD-0001", "INR 999"]},
	{"name": "order_shipped", "body": "Good news! Your order {{1}} has shipped. Tracking: {{2}}.", "samples": ["ORD-0001", "TRK123456"]},
	{"name": "payment_reminder", "body": "Your order {{1}} for {{2}} is awaiting payment. Pay here: {{3}}", "samples": ["ORD-0001", "INR 999", "https://pay.example.com/abc"]},
	{"name": "invoice_ready", "body": "The invoice {{1}} for your order is ready: {{2}}", "samples": ["INV-0001", "https://example.com/invoice/abc"]},
	{"name": "cart_reminder", "body": "You left items in your cart (order {{1}}, {{2}}). Reply here and we will help you complete it.", "samples": ["ORD-0001", "INR 999"]},
]


def template_payload(spec: dict[str, Any]) -> dict[str, Any]:
	return {
		"template_name": spec["name"],
		"category": "UTILITY",
		"language_code": "en",
		"template": spec["body"],
		"sample_values": list(spec["samples"]),
	}


@frappe.whitelist(methods=["POST"])
def submit_templates_pack(gateway: str) -> dict[str, Any]:
	"""Admin: create the commerce utility templates on the gateway's WhatsApp account via the existing create path."""
	from huf.ai.whatsapp import management

	management._require_admin()
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return {"success": False, "error": "not_found"}
	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account")
	results = {}
	for spec in TEMPLATES_PACK:
		res = management.create_template(account=account, payload=template_payload(spec), gateway_name=gateway)
		results[spec["name"]] = res
	return {"success": True, "results": results}
