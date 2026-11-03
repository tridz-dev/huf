"""Pure-python tests for portal access decisions (frappe stubbed)."""
import sys
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
		"huf.ai.apps_api",
	):
		sys.modules.setdefault(name, MagicMock())
	sys.modules["frappe.website.page_renderers.base_renderer"].BaseRenderer = object

from huf.ai.app_portal_renderer import (  # noqa: E402
	decide_portal_access,
	portal_guest_login_url,
	portal_slash_redirect,
	with_query_string,
)


class TestPortalAccess(unittest.TestCase):
	def test_guest_redirects_to_login(self):
		self.assertEqual(
			decide_portal_access("Guest", True, "/order", "/order"),
			("redirect", "/login?redirect-to=/order/"),
		)
		self.assertEqual(portal_guest_login_url("order/"), "/login?redirect-to=/order/")

	def test_login_url_is_percent_encoded(self):
		self.assertEqual(
			portal_guest_login_url("/a b&x=1"), "/login?redirect-to=/a%20b%26x%3D1/"
		)

	def test_query_string_appended(self):
		self.assertEqual(with_query_string("/order/", b"a=1&b=2"), "/order/?a=1&b=2")
		self.assertEqual(with_query_string("/order/", "a=1"), "/order/?a=1")
		self.assertEqual(with_query_string("/order/", b""), "/order/")
		self.assertEqual(with_query_string("/order/", None), "/order/")

	def test_forbidden(self):
		self.assertEqual(decide_portal_access("a@b.c", False, "/order/", "/order"), ("forbidden", None))

	def test_slash_redirect(self):
		self.assertEqual(decide_portal_access("a@b.c", True, "/order", "/order"), ("slash", "/order/"))
		self.assertEqual(portal_slash_redirect("/order", "order/"), "/order/")

	def test_render(self):
		self.assertEqual(decide_portal_access("a@b.c", True, "/order/", "/order"), ("render", None))

	def test_no_slash_redirect_for_root_or_other_path(self):
		self.assertIsNone(portal_slash_redirect("/", "/"))
		self.assertIsNone(portal_slash_redirect("/order/x", "/order"))


if __name__ == "__main__":
	unittest.main()
