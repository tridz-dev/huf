import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def _session():
	service_name = "shopify"
	shop_name = require_credential(service_name, "shop_name")
	token = require_credential(service_name, "access_token")
	
	# Strip .myshopify.com if provided, as we append it
	clean_shop = shop_name.replace(".myshopify.com", "").strip()
	return clean_shop, {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}


def _get(endpoint, params=None):
	shop, headers = _session()
	url = f"https://{shop}.myshopify.com/admin/api/2024-01/{endpoint}"
	resp = requests.get(url, headers=headers, params=params, timeout=30)
	resp.raise_for_status()
	return resp.json()


def handle_get_shop_info(**kwargs):
	"""Get information about the Shopify store."""
	service_name = "shopify"
	try:
		data = _get("shop.json")
		shop = data.get("shop", {})
		return json.dumps({
			"success": True,
			"results": {
				"name": shop.get("name", ""),
				"email": shop.get("email", ""),
				"domain": shop.get("domain", ""),
				"currency": shop.get("currency", ""),
				"plan_name": shop.get("plan_name", ""),
			}
		})
	except Exception as e:
		frappe.log_error(f"Shopify Error (Shop Info): {str(e)}", "Shopify Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_products(**kwargs):
	"""Get products from the Shopify store."""
	service_name = "shopify"
	try:
		limit = int(kwargs.get("max_results", 50))
		data = _get("products.json", {"limit": limit})
		products = [
			{
				"id": p["id"],
				"title": p["title"],
				"status": p.get("status", ""),
				"vendor": p.get("vendor", ""),
				"product_type": p.get("product_type", ""),
				"price": p["variants"][0]["price"] if p.get("variants") else None,
			}
			for p in data.get("products", [])
		]
		return json.dumps({
			"success": True,
			"count": len(products),
			"results": products
		})
	except Exception as e:
		frappe.log_error(f"Shopify Error (Products): {str(e)}", "Shopify Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_orders(**kwargs):
	"""Get recent orders from the Shopify store."""
	service_name = "shopify"
	try:
		limit = int(kwargs.get("max_results", 50))
		data = _get("orders.json", {"limit": limit, "status": "any"})
		orders = [
			{
				"id": o["id"],
				"order_number": o.get("order_number"),
				"total_price": o.get("total_price"),
				"currency": o.get("currency"),
				"financial_status": o.get("financial_status"),
				"fulfillment_status": o.get("fulfillment_status"),
				"created_at": o.get("created_at"),
			}
			for o in data.get("orders", [])
		]
		return json.dumps({
			"success": True,
			"count": len(orders),
			"results": orders
		})
	except Exception as e:
		frappe.log_error(f"Shopify Error (Orders): {str(e)}", "Shopify Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_inventory(**kwargs):
	"""Get inventory levels from the Shopify store."""
	service_name = "shopify"
	try:
		data = _get("products.json", {"limit": 50})
		inventory = []
		for p in data.get("products", []):
			for v in p.get("variants", []):
				inventory.append({
					"product": p["title"],
					"variant": v.get("title", "Default"),
					"sku": v.get("sku", ""),
					"quantity": v.get("inventory_quantity", 0),
					"price": v.get("price"),
				})
		return json.dumps({
			"success": True,
			"count": len(inventory),
			"results": inventory
		})
	except Exception as e:
		frappe.log_error(f"Shopify Error (Inventory): {str(e)}", "Shopify Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
