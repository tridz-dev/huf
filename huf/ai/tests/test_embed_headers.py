"""Frame policy and access checks for /huf/embed/ (docs/flow/BUILDER_EMBED.md, section 2.2)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from frappe.website.path_resolver import resolve_path
from frappe.website.serve import handle_exception
from werkzeug.datastructures import Headers

from huf.www import huf as page

CSP = "Content-Security-Policy"
KEY = page.EMBED_CONFIG_KEY
NO_ROLE_USER = "embed-no-role@example.com"


class TestEmbedHeaders(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", NO_ROLE_USER):
			frappe.get_doc(
				{"doctype": "User", "email": NO_ROLE_USER, "first_name": "Embed", "send_welcome_email": 0}
			).insert(ignore_permissions=True)

	def setUp(self):
		self._saved = {key: frappe.conf.get(key) for key in (KEY, "developer_mode")}
		self._request = getattr(frappe.local, "request", None)
		frappe.conf.pop(KEY, None)
		frappe.conf.developer_mode = 0
		frappe.local.response_headers = Headers()

	def tearDown(self):
		frappe.set_user("Administrator")
		for key, value in self._saved.items():
			if value is None:
				frappe.conf.pop(key, None)
			else:
				frappe.conf[key] = value
		frappe.local.request = self._request
		frappe.local.response_headers = Headers()

	def _open(self, path="/huf/embed/flow/missing-flow", headers=None):
		set_request(method="GET", path=path, headers=headers)
		frappe.local.response_headers = Headers()
		with patch.object(page, "build_boot_context", return_value={}) as boot:
			page.get_context(frappe._dict())
		return boot.call_args.args[0]

	def _policy(self):
		return frappe.local.response_headers.get(CSP)

	def test_default_is_none(self):
		for value in (None, [], "'self'", ["*"]):
			frappe.conf[KEY] = value
			extra = self._open()
			self.assertEqual(self._policy(), "frame-ancestors 'none'", value)
			self.assertEqual(extra, {"huf_embed": {"allowed_origins": []}})

	def test_configured_entries(self):
		frappe.conf[KEY] = ["'self'", "https://App.Example.com:443", "https://b.example.com:8443"]
		extra = self._open(headers={"Host": "site.example.com", "X-Forwarded-Proto": "https"})
		self.assertEqual(
			self._policy(), "frame-ancestors 'self' https://app.example.com https://b.example.com:8443"
		)
		self.assertEqual(
			extra["huf_embed"]["allowed_origins"],
			["https://site.example.com", "https://app.example.com", "https://b.example.com:8443"],
		)

	def test_invalid_entries_are_dropped(self):
		frappe.conf[KEY] = [
			"*",
			"https://*.example.com",
			"https://a.example/path",
			"https://a.example/",
			"https://a.example; script-src *",
			"https://a.example, https://b.example",
			"https://a.example\n",
			"https://a.example:99999",
			"http://a.example",
			"'unsafe-inline'",
			7,
		]
		self._open()
		self.assertEqual(self._policy(), "frame-ancestors 'none'")

		frappe.conf.developer_mode = 1
		frappe.conf[KEY] = ["http://a.example"]
		self._open()
		self.assertEqual(self._policy(), "frame-ancestors http://a.example")

	def test_denied_users_get_permission_error_with_header(self):
		frappe.conf[KEY] = ["'self'"]
		for user in ("Guest", NO_ROLE_USER):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				self._open()
			self.assertEqual(self._policy(), "frame-ancestors 'self'", user)

	def test_user_without_flow_read_is_denied(self):
		real = frappe.has_permission

		def no_read_on_flow(doctype, ptype="read", doc=None, **kwargs):
			if doc == "f1":
				return False
			return real(doctype, ptype, doc=doc, **kwargs)

		with patch.object(frappe.db, "exists", return_value=True), patch.object(
			frappe, "has_permission", side_effect=no_read_on_flow
		), self.assertRaises(frappe.PermissionError):
			self._open("/huf/embed/flow/f1")

	def test_unknown_embed_paths_and_variants_are_covered(self):
		for path in ("/huf/embed", "/huf/embed/other/x", "/HUF//Embed/nothing"):
			with self.assertRaises(frappe.PermissionError, msg=path):
				self._open(path)
			self.assertEqual(self._policy(), "frame-ancestors 'none'", path)

	def test_denied_page_is_403_and_keeps_the_header(self):
		# The built shell (huf.html) is not in a source checkout, so render the error path directly.
		self.assertEqual(resolve_path("huf/embed/flow/missing-flow"), "huf")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError) as raised:
			self._open()
		response = handle_exception(raised.exception, "huf", "/huf/embed/flow/missing-flow", 200)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(self._policy(), "frame-ancestors 'none'")

	def test_other_huf_pages_are_unchanged(self):
		frappe.conf[KEY] = ["'self'"]
		for path in ("/huf/flows/f1", "/huf", "/huf/embedded"):
			self.assertIsNone(self._open(path), path)
			self.assertIsNone(self._policy(), path)

	def test_boot_data_carries_extra_keys(self):
		with patch.object(frappe.sessions, "get", return_value={}), patch.object(
			frappe.sessions, "get_csrf_token", return_value="t"
		), patch.object(frappe.db, "commit"):
			context = page.build_boot_context({"huf_embed": {"allowed_origins": []}})
		self.assertEqual(json.loads(json.loads(context["boot"]))["huf_embed"], {"allowed_origins": []})
