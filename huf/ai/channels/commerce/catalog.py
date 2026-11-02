"""Catalog sync: ERPNext Item + Item Price -> Meta Commerce catalog (``POST /{catalog_id}/items_batch``).

Idempotent by construction: each request is an ``UPDATE`` with ``allow_upsert`` keyed on
``retailer_id`` = ``item_code``, so re-running pushes the same state. Items without a selling price
or an image are skipped (Meta rejects them) and counted. Needs ERPNext; without it a clear error is returned.
"""

from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe import _

from huf.ai.channels.adapters.erpnext import erpnext_installed
from huf.ai.gateway_adapters import whatsapp_bridge as bridge

BATCH_SIZE = 500  # Meta allows up to 5000 requests per call; stay well inside it
TIMEOUT = 30
NOT_INSTALLED = "ERPNext is not installed on this site; the catalog cannot be synced from Item / Item Price."


def _graph_credentials(gateway: str) -> tuple[str, str]:
	"""(versioned Graph root, access token) for the gateway: linked WhatsApp Account first, else its Integration Settings."""
	acct_name = bridge.gateway_account(gateway)
	if acct_name:
		acct = bridge.resolve_account(acct_name)
		if acct and not acct.get("error") and acct.get("token"):
			return f"{acct['url']}/{acct['version']}", acct["token"]
	from huf.ai.tools import whatsapp as wa_tool

	token = wa_tool._gateway_integration_values(gateway).get("access_token", "")
	return wa_tool._graph_root(gateway), token


def _selling_price_list() -> str | None:
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or None


def _absolute(url: str | None) -> str:
	url = (url or "").strip()
	if not url:
		return ""
	return url if url.startswith(("http://", "https://")) else frappe.utils.get_url(url)


def fetch_items() -> tuple[list[dict[str, Any]], int]:
	"""Meta item ``data`` dicts for sellable, enabled Items, plus the number skipped (no price / image)."""
	items = frappe.get_all(
		"Item",
		filters={"is_sales_item": 1, "disabled": 0},
		fields=["item_code", "item_name", "description", "image", "brand"],
		order_by="item_code asc",
		limit_page_length=0,
	)
	if not items:
		return [], 0
	price_list = _selling_price_list()
	pfilters: dict[str, Any] = {"selling": 1, "item_code": ["in", [i["item_code"] for i in items]]}
	if price_list:
		pfilters["price_list"] = price_list
	prices: dict[str, dict] = {}
	for row in frappe.get_all(
		"Item Price", filters=pfilters, fields=["item_code", "price_list_rate", "currency"], order_by="modified asc", limit_page_length=0
	):
		prices[row["item_code"]] = row  # newest wins
	site_url = frappe.utils.get_url()
	out, skipped = [], 0
	for it in items:
		price = prices.get(it["item_code"])
		image = _absolute(it.get("image"))
		if not price or price.get("price_list_rate") is None or not price.get("currency") or not image:
			skipped += 1
			continue
		title = (it.get("item_name") or it["item_code"])[:150]
		desc = frappe.utils.strip_html_tags(it.get("description") or "").strip() or title
		out.append(
			{
				"id": it["item_code"],
				"title": title,
				"description": desc[:5000],
				"availability": "in stock",
				"condition": "new",
				"price": f"{float(price['price_list_rate']):.2f} {price['currency']}",
				"link": site_url,
				"image_link": image,
				"brand": it.get("brand") or title,
			}
		)
	return out, skipped


def build_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
	"""The ``items_batch`` request body for ``rows`` (upsert keyed on ``id`` = retailer_id)."""
	return {
		"item_type": "PRODUCT_ITEM",
		"allow_upsert": True,
		"requests": [{"method": "UPDATE", "data": r} for r in rows],
	}


def _post_batch(root: str, token: str, catalog_id: str, body: dict[str, Any]) -> dict[str, Any]:
	try:
		resp = requests.post(
			f"{root}/{catalog_id}/items_batch",
			json=body,
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
			timeout=TIMEOUT,
		)
	except Exception as exc:
		return {"ok": False, "error": f"Graph request failed: {type(exc).__name__}"}
	try:
		data = resp.json()
	except ValueError:
		data = {}
	if resp.status_code >= 400 or "error" in data:
		msg = (data.get("error") or {}).get("message") or f"HTTP {resp.status_code}"
		return {"ok": False, "error": str(msg)[:300]}
	return {"ok": True, "handles": data.get("handles") or []}


def sync_catalog(gateway: str) -> dict[str, Any]:
	"""Push the ERPNext sales items to the gateway's Meta catalog. Returns counts; never raises for Meta errors."""
	if not erpnext_installed():
		return {"success": False, "error": NOT_INSTALLED}
	catalog_id = (frappe.db.get_value("Gateway", gateway, "catalog_id") or "").strip()
	if not catalog_id:
		return {"success": False, "error": "This gateway has no catalog_id; set the Catalog ID on the Gateway first."}
	root, token = _graph_credentials(gateway)
	if not token:
		return {"success": False, "error": "No WhatsApp access token is configured for this gateway."}
	rows, skipped = fetch_items()
	result = {"success": True, "gateway": gateway, "catalog_id": catalog_id, "items": len(rows), "skipped": skipped,
		"batches": 0, "synced": 0, "failed": 0, "errors": []}
	for i in range(0, len(rows), BATCH_SIZE):
		chunk = rows[i : i + BATCH_SIZE]
		res = _post_batch(root, token, catalog_id, build_batch(chunk))
		result["batches"] += 1
		if res["ok"]:
			result["synced"] += len(chunk)
		else:
			result["failed"] += len(chunk)
			result["errors"].append(res["error"])
	result["success"] = result["failed"] == 0
	return result


@frappe.whitelist()
def sync_catalog_now(gateway: str) -> dict[str, Any]:
	"""Admin action: sync one gateway's catalog (needs write authority on the Gateway)."""
	from huf.ai.whatsapp import management as mgmt

	if not frappe.db.exists("Gateway", gateway):
		frappe.throw(_("Gateway not found."), frappe.DoesNotExistError)
	if not mgmt._gateway_write_allowed(gateway):
		raise frappe.PermissionError(_("Not permitted to sync this Gateway's catalog"))
	return sync_catalog(gateway)


def sync_all_catalogs() -> None:
	"""Daily scheduler: sync every enabled WhatsApp gateway that has a catalog_id. No-op without ERPNext."""
	if not erpnext_installed():
		return
	for name in frappe.get_all("Gateway", filters={"provider": "WhatsApp", "is_enabled": 1, "catalog_id": ["is", "set"]}, pluck="name"):
		try:
			sync_catalog(name)
		except Exception:
			frappe.log_error(title=f"Catalog sync failed for {name}")
