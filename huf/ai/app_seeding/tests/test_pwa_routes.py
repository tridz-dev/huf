"""Pure-python tests for PWA static_routes validation and path resolution.

Run with: python3 -m pytest huf/ai/app_seeding/tests/test_pwa_routes.py
(frappe is stubbed when not importable, so no bench is needed).
"""
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock

try:
	import frappe  # noqa: F401
except Exception:
	for name in (
		"frappe",
		"frappe.website",
		"frappe.website.page_renderers",
		"frappe.website.page_renderers.base_renderer",
		"huf.www.huf",
	):
		sys.modules.setdefault(name, MagicMock())
	sys.modules["frappe.website.page_renderers.base_renderer"].BaseRenderer = object

from huf.ai.app_portal_renderer import (  # noqa: E402
	parse_static_routes,
	resolve_static_file,
	split_static_route,
	static_content_type,
	static_response_headers,
)
from huf.ai.app_seeding.apps_loader import _validate_static_routes  # noqa: E402


class TestValidateStaticRoutes(unittest.TestCase):
	def test_valid(self):
		self.assertIsNone(_validate_static_routes(["sw.js", "icons/a-1.png", "manifest.webmanifest"]))
		self.assertIsNone(_validate_static_routes([]))

	def test_invalid(self):
		for bad in (["../x"], ["a/../b"], ["/sw.js"], ["SW.js"], ["a b"], [1], "sw.js", ["a\\b"]):
			self.assertIsNotNone(_validate_static_routes(bad), bad)


class TestPathResolution(unittest.TestCase):
	def test_split(self):
		self.assertEqual(split_static_route("/order/sw.js", "/order"), "sw.js")
		self.assertEqual(split_static_route("order/icons/a.png", "/order/"), "icons/a.png")
		self.assertIsNone(split_static_route("/order", "/order"))
		self.assertIsNone(split_static_route("/ordering/sw.js", "/order"))
		self.assertIsNone(split_static_route("/x", "/"))

	def test_parse(self):
		self.assertEqual(parse_static_routes("a.js\n\n b.png \n"), ["a.js", "b.png"])
		self.assertEqual(parse_static_routes(None), [])

	def test_resolve(self):
		with tempfile.TemporaryDirectory() as d:
			os.makedirs(os.path.join(d, "icons"))
			for f in ("sw.js", "secret.txt", "icons/a.png"):
				open(os.path.join(d, f), "w").write("x")
			allow = ["sw.js", "icons/a.png", "../secret.txt", "missing.js"]
			self.assertTrue(resolve_static_file(d, "sw.js", allow).endswith("sw.js"))
			self.assertTrue(resolve_static_file(d, "icons/a.png", allow))
			self.assertIsNone(resolve_static_file(d, "secret.txt", allow))  # not allowlisted
			self.assertIsNone(resolve_static_file(d, "../secret.txt", allow))  # traversal
			self.assertIsNone(resolve_static_file(d, "missing.js", allow))
			self.assertIsNone(resolve_static_file(d, "icons", ["icons"]))  # directory

	def test_symlink_escape(self):
		with tempfile.TemporaryDirectory() as outer:
			base = os.path.join(outer, "t")
			os.makedirs(base)
			open(os.path.join(outer, "evil.js"), "w").write("x")
			os.symlink(os.path.join(outer, "evil.js"), os.path.join(base, "evil.js"))
			self.assertIsNone(resolve_static_file(base, "evil.js", ["evil.js"]))

	def test_headers_and_types(self):
		h = static_response_headers("sw.js", "/order")
		self.assertEqual(h["Service-Worker-Allowed"], "/order/")
		self.assertEqual(h["Cache-Control"], "no-cache")
		self.assertEqual(static_response_headers("a.png", "/order"), {})
		self.assertEqual(static_content_type("m.webmanifest"), "application/manifest+json")
		self.assertEqual(static_content_type("sw.js"), "application/javascript")
		self.assertEqual(static_content_type("a.png"), "image/png")


if __name__ == "__main__":
	unittest.main()
