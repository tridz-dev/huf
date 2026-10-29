"""Catalog sync (ERPNext Item/Item Price -> Meta items_batch) and product message builders. Graph is mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.commerce import catalog, messages

CAT = "huf.ai.channels.commerce.catalog"

ITEMS = [
	{"item_code": "A-1", "item_name": "Alpha", "description": "", "image": "https://cdn.x/a.png", "brand": None},
	{"item_code": "B-2", "item_name": "Bravo", "description": "<p>Tasty</p>", "image": "/files/b.png", "brand": "Acme"},
	{"item_code": "NOPRICE", "item_name": "x", "description": "", "image": "/files/n.png", "brand": None},
	{"item_code": "NOIMG", "item_name": "y", "description": "", "image": "", "brand": None},
]
PRICES = [
	{"item_code": "B-2", "price_list_rate": 10, "currency": "INR"},
	{"item_code": "A-1", "price_list_rate": 5.5, "currency": "USD"},
	{"item_code": "NOIMG", "price_list_rate": 1, "currency": "USD"},
]


def _get_all(doctype, **kw):
	return {"Item": ITEMS, "Item Price": PRICES}[doctype]


def _ok(status=200, body=None):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = body if body is not None else {"handles": ["h"]}
	return r


class TestCatalogSync(IntegrationTestCase):
	def _patches(self):
		return (
			patch(f"{CAT}.erpnext_installed", return_value=True),
			patch.object(frappe, "get_all", side_effect=_get_all),
			patch.object(frappe.db, "get_single_value", return_value="Standard Selling"),
			patch.object(frappe.db, "get_value", return_value="CAT1"),
			patch(f"{CAT}._graph_credentials", return_value=("https://graph.test/v99", "tok")),
			patch.object(frappe.utils, "get_url", side_effect=lambda p="": f"https://shop.test{p}"),
		)

	def test_absent_erpnext_clear_error(self):
		with patch(f"{CAT}.erpnext_installed", return_value=False), patch(f"{CAT}.requests.post") as post:
			res = catalog.sync_catalog("GW")
		self.assertFalse(res["success"])
		self.assertIn("ERPNext is not installed", res["error"])
		post.assert_not_called()

	def test_no_catalog_id(self):
		with patch(f"{CAT}.erpnext_installed", return_value=True), patch.object(frappe.db, "get_value", return_value=""):
			self.assertIn("catalog_id", catalog.sync_catalog("GW")["error"])

	def test_batch_payload_shape(self):
		p = self._patches()
		with p[0], p[1], p[2], p[3], p[4], p[5], patch(f"{CAT}.requests.post", return_value=_ok()) as post:
			res = catalog.sync_catalog("GW")
		self.assertEqual((res["items"], res["skipped"], res["batches"], res["synced"], res["failed"]), (2, 2, 1, 2, 0))
		self.assertTrue(res["success"])
		url = post.call_args.args[0]
		body = post.call_args.kwargs["json"]
		self.assertEqual(url, "https://graph.test/v99/CAT1/items_batch")
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tok")
		self.assertEqual(body["item_type"], "PRODUCT_ITEM")
		self.assertTrue(body["allow_upsert"])
		reqs = body["requests"]
		self.assertEqual([r["method"] for r in reqs], ["UPDATE", "UPDATE"])
		a, b = (r["data"] for r in reqs)
		self.assertEqual((a["id"], a["price"], a["image_link"], a["availability"]), ("A-1", "5.50 USD", "https://cdn.x/a.png", "in stock"))
		self.assertEqual((b["id"], b["price"], b["description"]), ("B-2", "10.00 INR", "Tasty"))
		self.assertEqual(b["image_link"], "https://shop.test/files/b.png")

	def test_idempotent_same_payload_every_run(self):
		p = self._patches()
		with p[0], p[1], p[2], p[3], p[4], p[5], patch(f"{CAT}.requests.post", return_value=_ok()) as post:
			catalog.sync_catalog("GW")
			catalog.sync_catalog("GW")
		self.assertEqual(post.call_args_list[0].kwargs["json"], post.call_args_list[1].kwargs["json"])

	def test_batches_split(self):
		p = self._patches()
		rows = [{"id": f"I{i}"} for i in range(5)]
		with p[0], p[3], p[4], patch(f"{CAT}.fetch_items", return_value=(rows, 0)), patch(f"{CAT}.BATCH_SIZE", 2), \
			patch(f"{CAT}.requests.post", return_value=_ok()) as post:
			res = catalog.sync_catalog("GW")
		self.assertEqual((res["batches"], post.call_count, res["synced"]), (3, 3, 5))

	def test_graph_error_counted_not_raised(self):
		p = self._patches()
		err = _ok(400, {"error": {"message": "bad catalog"}})
		with p[0], p[1], p[2], p[3], p[4], p[5], patch(f"{CAT}.requests.post", return_value=err):
			res = catalog.sync_catalog("GW")
		self.assertFalse(res["success"])
		self.assertEqual((res["failed"], res["errors"]), (2, ["bad catalog"]))

	def test_scheduler_only_gateways_with_catalog(self):
		with patch(f"{CAT}.erpnext_installed", return_value=True), patch.object(frappe, "get_all", return_value=["G1"]) as ga, \
			patch(f"{CAT}.sync_catalog") as sc:
			catalog.sync_all_catalogs()
		self.assertEqual(ga.call_args.kwargs["filters"]["catalog_id"], ["is", "set"])
		sc.assert_called_once_with("G1")
		with patch(f"{CAT}.erpnext_installed", return_value=False), patch(f"{CAT}.sync_catalog") as sc:
			catalog.sync_all_catalogs()
		sc.assert_not_called()

	def test_gateway_has_catalog_id_field(self):
		self.assertTrue(frappe.get_meta("Gateway").has_field("catalog_id"))


class TestProductMessages(IntegrationTestCase):
	def test_single_product(self):
		p, e = messages.build_product_payload("15550001111", "CAT1", "A-1", body="Look", footer="f")
		self.assertEqual(e, [])
		self.assertEqual(p["type"], "interactive")
		self.assertEqual(p["interactive"], {
			"type": "product", "body": {"text": "Look"}, "footer": {"text": "f"},
			"action": {"catalog_id": "CAT1", "product_retailer_id": "A-1"},
		})

	def test_product_list_sections(self):
		p, e = messages.build_product_list_payload(
			"1", "CAT1", [{"title": "Hot", "product_retailer_ids": ["A", "B"]}, {"title": "New", "product_retailer_ids": ["C"]}], "Menu", "Pick"
		)
		self.assertEqual(e, [])
		inter = p["interactive"]
		self.assertEqual(inter["type"], "product_list")
		self.assertEqual(inter["header"], {"type": "text", "text": "Menu"})
		self.assertEqual(inter["action"]["sections"][0], {"title": "Hot", "product_items": [{"product_retailer_id": "A"}, {"product_retailer_id": "B"}]})
		self.assertEqual(len(inter["action"]["sections"]), 2)

	def test_validation(self):
		self.assertIsNone(messages.build_product_payload("1", "", "A")[0])
		self.assertIsNone(messages.build_product_list_payload("1", "C", [], "h", "b")[0])
		self.assertIsNone(messages.build_product_list_payload("1", "C", [{"product_retailer_ids": ["A"]}], "", "b")[0])
		many = [{"product_retailer_ids": [f"I{i}" for i in range(31)]}]
		self.assertEqual(messages.build_product_list_payload("1", "C", many, "h", "b")[1][0]["code"], "too_many_items")

	def test_dispatch_single_vs_many_and_dedupe(self):
		p, _ = messages.build_products_payload("1", "C", ["A", "A"])
		self.assertEqual(p["interactive"]["type"], "product")
		p, _ = messages.build_products_payload("1", "C", ["A", "B", "A"])
		self.assertEqual(p["interactive"]["type"], "product_list")
		self.assertEqual(len(p["interactive"]["action"]["sections"][0]["product_items"]), 2)

	def test_deliver_goes_through_deliver_typed(self):
		sent = MagicMock(return_value=json.dumps({"success": True}))
		with patch.object(frappe.db, "get_value", return_value="CAT1"):
			out = messages.deliver({"gateway_name": "GW", "to": "+1 555 000 1111", "item_codes": '["A","B"]'}, sent)
		self.assertTrue(json.loads(out)["success"])
		kw, recipient, built, _call, what = sent.call_args.args
		self.assertEqual(recipient, "15550001111")
		self.assertEqual(built[0]["interactive"]["type"], "product_list")
		self.assertEqual(what, "a product message")

	def test_action_is_a_gated_send(self):
		from huf.ai.tools import whatsapp as wa

		self.assertIn("send_products", wa._SEND_ACTIONS)

	def test_registered_tool(self):
		from huf.ai.tools._registry import COMMERCE_TOOLS

		self.assertEqual(COMMERCE_TOOLS[0]["tool_name"], "send_products")
