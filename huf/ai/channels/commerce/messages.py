"""Interactive commerce messages: single ``product`` and multi ``product_list``, plus the agent tool ``send_products``.

Builders are pure (no network). The tool delegates to ``huf.ai.tools.whatsapp.handle_action('send_products')``,
so allow-list, opt-out, 24h window / proactive gate, caps and idempotency all apply as for every other send.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_messages as wm

MAX_PRODUCTS = 30
MAX_SECTIONS = 10
DEFAULT_SECTION = "Products"
DEFAULT_BODY = "Here are some items you may like."


def _err(field: str, code: str, message: str) -> dict[str, str]:
	return wm.err(field, code, message)


def build_product_payload(to, catalog_id, retailer_id, body=None, footer=None, reply_to=None):
	errors = []
	if not str(catalog_id or "").strip():
		errors.append(_err("catalog_id", "catalog_required", "The gateway has no catalog_id."))
	if not str(retailer_id or "").strip():
		errors.append(_err("item_codes", "item_required", "A product item code is required."))
	if errors:
		return None, errors
	data = wm._base(to, "interactive", reply_to)
	inter: dict[str, Any] = {"type": "product", "action": {"catalog_id": str(catalog_id), "product_retailer_id": str(retailer_id)}}
	if wm._text(body):
		inter["body"] = {"text": wm._text(body)[:1024]}
	if wm._text(footer):
		inter["footer"] = {"text": wm._text(footer)[:60]}
	data["interactive"] = inter
	return data, []


def build_product_list_payload(to, catalog_id, sections, header, body, footer=None, reply_to=None):
	"""``sections``: ``[{title, product_retailer_ids: [...]}]`` (or ``product_items``); header and body are required by Meta."""
	errors = []
	if not str(catalog_id or "").strip():
		errors.append(_err("catalog_id", "catalog_required", "The gateway has no catalog_id."))
	if not wm._text(header):
		errors.append(_err("header", "header_required", "A product list needs a header text."))
	if not wm._text(body):
		errors.append(_err("body", "body_required", "A product list needs a body text."))
	out_sections, total = [], 0
	for sec in sections or []:
		ids = [str(x).strip() for x in (sec.get("product_retailer_ids") or []) if str(x).strip()]
		if ids:
			out_sections.append({"title": wm._text(sec.get("title") or DEFAULT_SECTION)[:24], "product_items": [{"product_retailer_id": i} for i in ids]})
			total += len(ids)
	if not out_sections:
		errors.append(_err("item_codes", "item_required", "At least one product item code is required."))
	if len(out_sections) > MAX_SECTIONS:
		errors.append(_err("sections", "too_many_sections", f"At most {MAX_SECTIONS} sections."))
	if total > MAX_PRODUCTS:
		errors.append(_err("item_codes", "too_many_items", f"At most {MAX_PRODUCTS} products per message."))
	if errors:
		return None, errors
	data = wm._base(to, "interactive", reply_to)
	inter: dict[str, Any] = {
		"type": "product_list",
		"header": {"type": "text", "text": wm._text(header)[:60]},
		"body": {"text": wm._text(body)[:1024]},
		"action": {"catalog_id": str(catalog_id), "sections": out_sections},
	}
	if wm._text(footer):
		inter["footer"] = {"text": wm._text(footer)[:60]}
	data["interactive"] = inter
	return data, []


def build_products_payload(to, catalog_id, item_codes, header=None, body=None, footer=None, reply_to=None):
	"""One code -> ``product``; several -> a single-section ``product_list``. Duplicates are dropped, order kept."""
	codes = list(dict.fromkeys(str(c).strip() for c in item_codes or [] if str(c).strip()))
	if len(codes) == 1:
		return build_product_payload(to, catalog_id, codes[0], body, footer, reply_to)
	return build_product_list_payload(
		to, catalog_id, [{"title": DEFAULT_SECTION, "product_retailer_ids": codes}], header or "Our products", body or DEFAULT_BODY, footer, reply_to
	)


def deliver(kwargs: dict, deliver_typed) -> str:
	"""Build and send for ``handle_action``; ``deliver_typed`` is ``tools.whatsapp._deliver_typed`` (gates + bridge/direct send)."""
	from huf.ai.tools import whatsapp as wa_tool

	recipient = wa_tool._recipient(kwargs)
	if not recipient:
		return wa_tool._error("Recipient phone number ('to') is required", definite=True)
	codes = kwargs.get("item_codes")
	if isinstance(codes, str):
		try:
			codes = json.loads(codes)
		except ValueError:
			codes = [c for c in codes.split(",")]
	catalog_id = (frappe.db.get_value("Gateway", kwargs.get("gateway_name"), "catalog_id") or "").strip()
	reply_to = (kwargs.get("reply_to") or "").strip() or None
	built = build_products_payload(recipient, catalog_id, codes if isinstance(codes, list) else [], kwargs.get("header"), kwargs.get("body"), kwargs.get("footer"), reply_to)

	return deliver_typed(kwargs, recipient, built, lambda account: bridge._send_payload(account, built[0], False), "a product message")


def send_products(item_codes=None, header: str | None = None, body: str | None = None, to: str | None = None) -> str:
	"""Agent tool: send catalog products (one -> product card, several -> product list) to the customer."""
	from huf.ai.tools import whatsapp as wa_tool

	return wa_tool.handle_action("send_products", item_codes=item_codes, header=header, body=body, to=to)
