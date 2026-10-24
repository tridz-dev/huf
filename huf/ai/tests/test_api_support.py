# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.api_support import api_error, paginate, parse_json_arg, require_permission


class TestApiSupport(IntegrationTestCase):
	def test_api_error_shape(self):
		self.assertEqual(api_error("x"), {"error": {"code": "x", "message": ""}})
		self.assertEqual(
			api_error("x", "m", field="f"), {"error": {"code": "x", "message": "m", "field": "f"}}
		)

	def test_parse_json_arg_accepts_values_and_strings(self):
		self.assertEqual(parse_json_arg({"a": 1}), {"a": 1})
		self.assertEqual(parse_json_arg('{"a": 1}', expected=dict), {"a": 1})
		self.assertEqual(parse_json_arg("[1, 2]", expected=list), [1, 2])
		self.assertEqual(parse_json_arg([1], expected=(list, dict)), [1])

	def test_parse_json_arg_defaults(self):
		self.assertEqual(parse_json_arg(None, default={}), {})
		self.assertEqual(parse_json_arg("  ", default=[]), [])
		self.assertEqual(parse_json_arg("null", default="d"), "d")

	def test_parse_json_arg_rejects_bad_input(self):
		with self.assertRaises(frappe.ValidationError):
			parse_json_arg("{nope")
		with self.assertRaises(frappe.ValidationError):
			parse_json_arg("[1]", expected=dict)
		with self.assertRaises(frappe.ValidationError):
			parse_json_arg({"a": 1}, expected=list)

	def test_paginate_list(self):
		rows = list(range(10))
		self.assertEqual(
			paginate(rows, 2, 3), {"items": [2, 3, 4], "total": 10, "start": 2, "limit": 3}
		)
		self.assertEqual(paginate(rows, 9, 5)["items"], [9])
		self.assertEqual(paginate(rows, 50, 5)["items"], [])

	def test_paginate_clamps(self):
		rows = list(range(300))
		out = paginate(rows, -5, 10000)
		self.assertEqual((out["start"], out["limit"], len(out["items"])), (0, 100, 100))
		self.assertEqual(paginate(rows, "x", 0)["limit"], 1)
		self.assertEqual(paginate(rows, 0, "bad")["limit"], 20)
		self.assertEqual(paginate(rows, 0, 500, max_limit=200)["limit"], 200)
		self.assertEqual(paginate(iter(rows), 0, 2)["total"], 300)

	def test_paginate_query(self):
		out = paginate({"doctype": "Role", "fields": ["name"], "order_by": "name asc"}, 0, 2)
		self.assertEqual(len(out["items"]), 2)
		self.assertGreaterEqual(out["total"], 2)

	def test_require_permission(self):
		require_permission(True, "no")
		require_permission(lambda: 1, "no")
		with self.assertRaises(frappe.PermissionError):
			require_permission(False, "no")
		with self.assertRaises(frappe.PermissionError):
			require_permission(lambda: None, "no")
