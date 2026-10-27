# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Site test: a real Frappe session is created by the Telegram web access exchange (throwaway user)."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.auth import CookieManager
from frappe.sessions import Session
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from huf.ai import telegram_web_access as twa

EMAIL = "tg-web-access-test@example.com"


def _sessiondata(sid):
	rows = frappe.db.sql("select sessiondata from tabSessions where sid=%s", (sid,))
	return rows[0][0] if rows else None


def _request(headers=None):
	return Request(EnvironBuilder(path="/", headers=headers or {}, base_url="http://tg.test").get_environ())


class TestTelegramWebAccessSite(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL,
				"first_name": "TgWeb",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc("User", EMAIL).add_roles("Desk User")
		frappe.db.commit()
		self.sids = []
		self.binding = {"name": "B-TEST", "frappe_user": EMAIL, "telegram_user_id": "4242"}
		self.gw = SimpleNamespace(
			name="gw-test", get=lambda k, d=None: {"telegram_web_allow_writes": 1}.get(k, d)
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		for sid in self.sids:
			frappe.db.delete("Sessions", {"sid": sid})
			frappe.cache.hdel("session", sid)
		frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _login(self, headers=None, hours=24):
		frappe.local.request = _request(headers)
		frappe.local.cookie_manager = CookieManager()
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.response = frappe._dict()
		twa._create_session(self.binding, "4242", self.gw, hours)
		sid = frappe.session.sid
		self.sids.append(sid)
		return sid

	def test_session_cookie_marker_and_resume(self):
		before = datetime.now(UTC)
		with mock.patch.dict(frappe.conf, {"host_name": "http://tg.test"}):
			sid = self._login({"X-Forwarded-Proto": "https"}, hours=2)
		self.assertEqual(frappe.session.user, EMAIL)
		cookie = frappe.local.cookie_manager.cookies["sid"]
		self.assertEqual(cookie["value"], sid)
		self.assertTrue(cookie["httponly"])
		self.assertFalse(cookie["secure"])  # a client-supplied X-Forwarded-Proto is not trusted
		self.assertEqual(cookie["max_age"], 7200)
		row = _sessiondata(sid)
		data = json.loads(row)
		self.assertEqual(data["audit_user"], "telegram:4242")
		end = datetime.fromisoformat(data["session_end"])
		self.assertIsNotNone(end.tzinfo)
		self.assertAlmostEqual((end - before).total_seconds(), 7200, delta=60)
		marker = data["tg_origin"]
		self.assertEqual(
			marker,
			{
				"binding": "B-TEST",
				"gateway": "gw-test",
				"tg_id": "4242",
				"web_access_version": 1,
			},
		)
		self.assertNotIn(sid, json.dumps(frappe.local.response, default=str))
		self.assertIsNone(frappe.local.response.get("home_page"))
		# resume from the cache path and from the database path
		for drop_cache in (False, True):
			if drop_cache:
				frappe.cache.hdel("session", sid)
			frappe.local.request = _request({"Cookie": f"sid={sid}"})
			frappe.local.cookie_manager = CookieManager()
			resumed = Session(user=None, resume=True)
			self.assertEqual(resumed.user, EMAIL)
			self.assertEqual(twa.session_marker(resumed.data.data), marker)
			frappe.local.session = resumed.data
			self.assertTrue(twa.is_tg_session())
			self.assertTrue(twa._existing_session_ok(self.binding, "4242", "gw-test"))
			self.assertFalse(twa._existing_session_ok(self.binding, "9999", "gw-test"))

	def test_plain_http_cookie_not_secure(self):
		with mock.patch.dict(frappe.conf, {"host_name": "http://tg.test"}):
			self._login()
		self.assertFalse(frappe.local.cookie_manager.cookies["sid"]["secure"])

	def test_https_host_name_sets_secure(self):
		with mock.patch.dict(frappe.conf, {"host_name": "https://tg.test"}):
			self._login()
		self.assertTrue(frappe.local.cookie_manager.cookies["sid"]["secure"])

	def test_expired_session_end_rejected_on_resume(self):
		sid = self._login()
		session_data = json.loads(_sessiondata(sid))
		session_data["session_end"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
		frappe.db.sql("update tabSessions set sessiondata=%s where sid=%s", (json.dumps(session_data), sid))
		frappe.cache.hset("session", sid, frappe._dict(user=EMAIL, sid=sid, data=frappe._dict(session_data)))
		frappe.local.request = _request({"Cookie": f"sid={sid}"})
		frappe.local.cookie_manager = CookieManager()
		frappe.local.response = frappe._dict()
		resumed = Session(user=None, resume=True)
		self.assertEqual(resumed.user, "Guest")

	def test_not_a_tg_session_for_normal_login(self):
		frappe.local.session = frappe._dict(user=EMAIL, data=frappe._dict())
		self.assertFalse(twa.is_tg_session())
