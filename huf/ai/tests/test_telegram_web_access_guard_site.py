# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Site test: ``enforce()`` on a resumed Telegram session (throwaway user, gateway, binding)."""

from types import SimpleNamespace

import frappe
from frappe.auth import CookieManager
from frappe.sessions import Session
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from huf.ai import telegram_web_access as twa
from huf.ai import telegram_web_access_enforce as E
from huf.ai.telegram_web_access_paths import parse_prefixes, path_matches

USER = "tg-guard-test@example.com"
GW = "tg-guard-test-gw"


def _request(path, method="GET", cookie=None, **kw):
	headers = {"Cookie": f"sid={cookie}"} if cookie else {}
	return Request(EnvironBuilder(path=path, method=method, headers=headers, **kw).get_environ())


class TestGuardSite(IntegrationTestCase):
	def setUp(self):
		self._cleanup()
		self.addCleanup(self._cleanup)
		frappe.set_user("Administrator")
		frappe.get_doc(
			{"doctype": "User", "email": USER, "first_name": "TgGuard", "send_welcome_email": 0}
		).insert(ignore_permissions=True).add_roles("Desk User")
		frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": GW,
				"provider": "Telegram",
				"is_enabled": 0,
				"telegram_web_access_enabled": 1,
				"telegram_web_allowed_paths": "/app/note",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Gateway", GW, "is_enabled", 1)  # skips validate()'s integration check
		self.binding = frappe.get_doc(
			{
				"doctype": "Telegram Admin Binding",
				"telegram_user_id": "7001",
				"frappe_user": USER,
				"gateway": GW,
				"role_scope": "Viewer",
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		frappe.local.request = _request("/")
		frappe.local.cookie_manager = CookieManager()
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.response = frappe._dict()
		gw = SimpleNamespace(name=GW, get=lambda k, d=None: None)
		twa._create_session({"name": self.binding.name, "frappe_user": USER}, "7001", gw, 1)
		self.sid = frappe.session.sid
		frappe.db.commit()
		E.clear_gateway_cache()

	def _cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Sessions", {"user": USER})
		for name in frappe.get_all("Telegram Admin Binding", {"frappe_user": USER}, pluck="name"):
			frappe.delete_doc("Telegram Admin Binding", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Gateway", GW):
			frappe.delete_doc("Gateway", GW, force=True, ignore_permissions=True)
		if frappe.db.exists("User", USER):
			frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
		frappe.db.commit()
		E.clear_gateway_cache()

	def _enforce(self, request):
		"""Resume the Telegram session the way Frappe does (``sid`` popped from form_dict), then run the guard."""
		frappe.local.request = request
		frappe.local.form_dict = frappe._dict({k: v for k, v in request.args.items()})
		frappe.local.form_dict.update({k: v for k, v in request.form.items()})
		if request.mimetype == "application/json":
			frappe.local.form_dict.update(request.get_json(silent=True) or {})
		frappe.local.cookie_manager = CookieManager()
		frappe.local.response = frappe._dict()
		frappe.local.session = Session(user=None, resume=True).data
		self.assertEqual(frappe.session.user, USER if frappe.session.sid != "Guest" else "Guest")
		return E.enforce()

	def _status(self, request):
		try:
			self._enforce(request)
		except E._Forbidden as exc:
			return exc.code
		return 200

	def test_baseline(self):
		self.assertEqual(self._status(_request("/api/method/ping", cookie=self.sid)), 200)
		self.assertEqual(self._status(_request("/app/user", cookie=self.sid)), 403)

	def test_sid_in_raw_request_is_denied(self):
		"""Frappe pops ``sid`` from form_dict before ``before_request``; the guard must see it in the raw request."""
		sid = self.sid
		requests = [
			_request(f"/api/method/ping?sid={sid}", cookie=sid),
			_request(f"/api/method/ping?sid={sid}"),
			_request("/api/method/ping", "POST", cookie=sid, data={"sid": sid}),
			_request("/api/method/ping", "POST", data={"sid": sid}),
			_request("/api/method/ping", "POST", json={"sid": sid}),
			_request("/api/method/ping", "POST", cookie=sid, json={"sid": sid}),
		]
		for request in requests:
			self.assertEqual(
				self._status(request),
				403,
				(request.method, request.mimetype, request.cookies.get("sid") is not None),
			)

	def test_private_files_not_reachable(self):
		for path in (
			"/private/files/x.txt",
			"/private/files/../../sites/site_config.json",
			"/files/../private/files/x.txt",
		):
			self.assertEqual(self._status(_request(path, cookie=self.sid)), 403, path)
		self.assertFalse(path_matches("/private/files/x.txt", parse_prefixes("/app/note")))

	def test_revoked_binding_removes_sessions(self):
		E.revoke_binding_sessions(self.binding.name, USER)
		self.assertFalse(frappe.db.sql("select sid from tabSessions where sid=%s", self.sid))

	def test_exchange_missing_or_malformed_arguments_are_uniform_403(self):
		frappe.local.request = _request("/", "POST")
		for kwargs in (
			{},
			{"init_data": "x"},
			{"init_data": 5, "gateway": [1]},
			{"init_data": "x", "gateway": GW},
		):
			with self.assertRaises(frappe.PermissionError) as ctx:
				twa.exchange(**kwargs)
			self.assertIn("Not authorized", str(ctx.exception))
