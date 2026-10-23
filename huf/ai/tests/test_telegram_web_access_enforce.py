# Copyright (c) 2026, Huf and contributors
import json
import unittest
from unittest import mock

from huf.ai import telegram_web_access_enforce as E

M_OFF = {"binding": "B1", "gateway": "G", "tg_id": 1, "allow_writes": False, "web_access_version": 1}
M_ON = {**M_OFF, "allow_writes": True}
S = {
	"telegram_web_access_enabled": 1,
	"telegram_web_allowed_paths": "/app/sales-invoice\n/app/query-report/",
	"telegram_web_extra_read_methods": "myapp.api.read_thing",
}


def d(m, method, path, fd=None, s=S):
	return E.decide(m, s, method, path, fd or {})


class TestPaths(unittest.TestCase):
	def test_segment_boundary(self):
		self.assertTrue(d(M_OFF, "GET", "/app/sales-invoice"))
		self.assertTrue(d(M_OFF, "GET", "/app/sales-invoice/SINV-1"))
		self.assertTrue(d(M_OFF, "HEAD", "/app/query-report/Foo"))
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoices"))
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoice-x/1"))
		self.assertFalse(d(M_OFF, "GET", "/app"))
		self.assertFalse(d(M_OFF, "GET", "/"))

	def test_traversal_encoded_case(self):
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoice/../user"))
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoice/%2e%2e/user"))
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoice/%252e%252e/user"))
		self.assertFalse(d(M_OFF, "GET", "/app/sales-invoice\\..\\user"))
		self.assertFalse(d(M_OFF, "GET", "/app%2fuser"))
		self.assertTrue(d(M_OFF, "GET", "/APP/Sales-Invoice/X"))
		self.assertTrue(d(M_OFF, "GET", "//app//sales-invoice"))
		self.assertTrue(d(M_OFF, "GET", "/app/sales-invoice?x=/user"))

	def test_navigation_non_get_denied(self):
		self.assertFalse(d(M_ON, "POST", "/app/sales-invoice"))

	def test_assets_and_always(self):
		self.assertTrue(d(M_OFF, "GET", "/assets/frappe/js/x.js"))
		self.assertTrue(d(M_OFF, "GET", "/files/a.png"))
		self.assertFalse(d(M_OFF, "POST", "/files/a.png"))
		self.assertTrue(d(M_OFF, "GET", "/api/method/frappe.ping"))
		self.assertTrue(d(M_OFF, "POST", "/api/method/logout"))

	def test_disabled_gateway_denies(self):
		self.assertFalse(d(M_OFF, "GET", "/assets/x.js", s={**S, "telegram_web_access_enabled": 0}))


class TestMatrix(unittest.TestCase):
	def test_writes_off(self):
		self.assertTrue(d(M_OFF, "POST", "/api/method/frappe.desk.query_report.run"))
		self.assertTrue(d(M_OFF, "POST", "/api/method/frappe.client.get_list"))
		self.assertTrue(d(M_OFF, "POST", "/api/method/myapp.api.read_thing"))
		self.assertFalse(d(M_OFF, "POST", "/api/method/frappe.client.set_value"))
		self.assertFalse(d(M_OFF, "POST", "/api/method/frappe.client.insert"))
		self.assertFalse(d(M_OFF, "GET", "/api/method/myapp.api.do_write"))
		self.assertFalse(d(M_OFF, "POST", "/api/method/upload_file"))
		self.assertFalse(d(M_OFF, "PUT", "/api/resource/ToDo/1"))
		self.assertFalse(d(M_OFF, "POST", "/api/resource/ToDo"))
		self.assertTrue(d(M_OFF, "GET", "/api/resource/ToDo"))

	def test_writes_on(self):
		self.assertTrue(d(M_ON, "POST", "/api/method/frappe.client.set_value", {"doctype": "ToDo"}))
		self.assertTrue(d(M_ON, "PUT", "/api/resource/ToDo/1"))
		self.assertTrue(d(M_ON, "DELETE", "/api/resource/ToDo/1"))
		self.assertTrue(d(M_ON, "POST", "/api/method/upload_file"))

	def test_always_blocked(self):
		for m in (M_OFF, M_ON):
			for meth in ("GET", "POST"):
				self.assertFalse(d(m, meth, "/api/method/frappe.core.doctype.user.user.impersonate"))
				self.assertFalse(
					d(m, meth, "/api/method/frappe.desk.doctype.system_console.system_console.execute_code")
				)
				self.assertFalse(
					d(m, meth, "/api/method/frappe.core.doctype.data_import.data_import.form_start_import")
				)
				self.assertFalse(d(m, meth, "/api/method/frappe.permissions.add_user_permission"))
			for dt in (
				"User",
				"Role",
				"System Settings",
				"Server Script",
				"Data Import",
				"DocPerm",
				"Has Role",
			):
				self.assertFalse(d(m, "GET", f"/api/resource/{dt.replace(' ', '%20')}"))
				self.assertFalse(d(m, "POST", "/api/method/frappe.client.set_value", {"doctype": dt}))
			self.assertFalse(
				d(m, "POST", "/api/method/frappe.client.insert", {"doc": json.dumps({"doctype": "User"})})
			)
			self.assertFalse(d(m, "POST", "/api/method/frappe.client.get_list", {"doctype": "user"}))
			self.assertFalse(
				d(m, "POST", "/api/method/frappe.client.save", {"doc": json.dumps({"doctype": "Role"})})
			)

	def test_sid_denied(self):
		for m in (M_OFF, M_ON):
			self.assertFalse(d(m, "GET", "/assets/x.js", {"sid": "abc"}))
			self.assertFalse(d(m, "POST", "/api/method/frappe.client.get_list", {"sid": "abc"}))

	def test_cmd_form(self):
		self.assertFalse(d(M_OFF, "POST", "/", {"cmd": "frappe.client.insert"}))
		self.assertTrue(d(M_OFF, "POST", "/", {"cmd": "frappe.client.get_list"}))

	def test_method_case_sensitive(self):
		self.assertFalse(d(M_OFF, "POST", "/api/method/Frappe.Client.Get_List"))


class TestEnforceHook(unittest.TestCase):
	def test_non_tg_session_is_single_lookup(self):
		sess = mock.MagicMock()
		sess.get.return_value = {}
		with mock.patch.object(E.frappe, "local", mock.MagicMock(session=sess)) as loc:
			with mock.patch.object(E, "_gateway_settings") as gs:
				E.enforce()
				gs.assert_not_called()
			self.assertEqual(sess.get.call_count, 1)
			self.assertIsNotNone(loc)

	def test_tg_denied_raises_403(self):
		loc = mock.MagicMock()
		loc.session = {"data": {"tg_origin": M_OFF}}
		loc.request.method = "GET"
		loc.request.path = "/app/user"
		loc.form_dict = {}
		with (
			mock.patch.object(E.frappe, "local", loc),
			mock.patch.object(E, "_gateway_settings", return_value=S),
		):
			with self.assertRaises(E._Forbidden) as cm:
				E.enforce()
			self.assertEqual(cm.exception.code, 403)
			self.assertIn(b"Not allowed in a Telegram session", cm.exception.response.get_data())

	def test_tg_allowed_returns(self):
		loc = mock.MagicMock()
		loc.session = {"data": {"tg_origin": M_OFF}}
		loc.request.method = "GET"
		loc.request.path = "/app/sales-invoice/X"
		loc.form_dict = {}
		with (
			mock.patch.object(E.frappe, "local", loc),
			mock.patch.object(E, "_gateway_settings", return_value=S),
		):
			self.assertIsNone(E.enforce())


class TestRevoke(unittest.TestCase):
	def test_only_matching_binding(self):
		rows = [
			("s1", json.dumps({"tg_origin": {"binding": "B1"}})),
			("s2", json.dumps({"tg_origin": {"binding": "B2"}})),
			("s3", "not json tg_origin"),
		]
		db = mock.MagicMock()
		db.sql.return_value = rows
		with mock.patch.object(E.frappe, "db", db), mock.patch.object(E.frappe, "cache", mock.MagicMock()):
			self.assertEqual(E.revoke_binding_sessions("B1", "u@x.com"), 1)
		db.delete.assert_called_once_with("Sessions", {"sid": "s1"})
		self.assertIn("like", db.sql.call_args[0][0])


class TestSessionExpiry(unittest.TestCase):
	def test_expired_session_end_is_denied_and_unreadable_fails_closed(self):
		from types import SimpleNamespace
		from unittest import mock

		from huf.ai import telegram_web_access_enforce as enf

		def run(end):
			sess = {"data": {"tg_origin": {"gateway": "G"}, "session_end": end}}
			with mock.patch.object(enf.frappe.local, "session", sess, create=True):
				return enf._session_expired()

		self.assertTrue(run("2020-01-01T00:00:00+00:00"))
		self.assertFalse(run("2999-01-01T00:00:00+00:00"))
		self.assertFalse(run(""))
		self.assertTrue(run("not-a-date"))
