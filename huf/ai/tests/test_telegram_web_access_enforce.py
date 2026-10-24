# Copyright (c) 2026, Huf and contributors
import json
import unittest
from unittest import mock

from huf.ai import telegram_web_access_enforce as E

M_OFF = {"binding": "B1", "gateway": "G", "tg_id": 1, "allow_writes": False, "web_access_version": 1}
M_ON = {**M_OFF, "allow_writes": True}
S = {
	"is_enabled": 1,
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

	def test_missing_or_disabled_gateway_denies(self):
		self.assertFalse(d(M_OFF, "GET", "/assets/x.js", s={}))
		self.assertFalse(d(M_OFF, "GET", "/assets/x.js", s={**S, "is_enabled": 0}))


class TestMatrix(unittest.TestCase):
	def test_writes_off(self):
		with mock.patch.object(E, "_report_ok", return_value=True):
			self.assertTrue(
				d(M_OFF, "POST", "/api/method/frappe.desk.query_report.run", {"report_name": "R"})
			)
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
			mock.patch.object(E, "_binding_active", return_value=True),
			mock.patch.object(E, "_is_privileged", return_value=False),
			mock.patch.object(E.frappe, "session", mock.MagicMock(user="u@x.com")),
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


class TestResourceShapes(unittest.TestCase):
	def test_run_method_bypass_denied(self):
		for key in ("run_method", "cmd", "method"):
			self.assertFalse(d(M_OFF, "GET", "/api/resource/ToDo/1", {key: "x"}), key)
			self.assertFalse(d(M_OFF, "GET", "/api/resource/ToDo", {key: "x"}), key)

	def test_only_exact_shapes(self):
		self.assertTrue(d(M_OFF, "GET", "/api/resource/ToDo/1"))
		self.assertFalse(d(M_OFF, "GET", "/api/resource/ToDo/1/extra"))
		self.assertFalse(d(M_OFF, "GET", "/api/resource"))
		self.assertFalse(d(M_OFF, "GET", "/api/resourcex/ToDo"))

	def test_v2_document_and_doctype(self):
		self.assertTrue(d(M_OFF, "GET", "/api/v2/document/ToDo/1"))
		self.assertFalse(d(M_OFF, "GET", "/api/v2/document/ToDo/1", {"run_method": "x"}))
		self.assertFalse(d(M_OFF, "POST", "/api/v2/document/ToDo"))
		self.assertTrue(d(M_ON, "POST", "/api/v2/document/ToDo"))
		self.assertFalse(d(M_OFF, "GET", "/api/v2/document/ToDo/1/method/x"))
		self.assertTrue(d(M_OFF, "GET", "/api/v2/doctype/ToDo"))
		self.assertFalse(d(M_OFF, "GET", "/api/v2/doctype/ToDo/meta"))
		self.assertFalse(d(M_ON, "POST", "/api/v2/doctype/ToDo"))
		for m in (M_OFF, M_ON):
			for dt in ("User", "Gateway", "Telegram%20Admin%20Binding", "Role", "DocPerm"):
				self.assertFalse(d(m, "GET", f"/api/v2/document/{dt}"), dt)
				self.assertFalse(d(m, "GET", f"/api/v2/document/{dt}/x"), dt)
				self.assertFalse(d(m, "GET", f"/api/v2/doctype/{dt}"), dt)
				self.assertFalse(d(m, "GET", f"/api/resource/{dt}/x"), dt)

	def test_v2_two_segment_method_denied(self):
		for m in (M_OFF, M_ON):
			self.assertFalse(d(m, "GET", "/api/v2/method/ToDo/run"))
			self.assertFalse(d(m, "POST", "/api/v2/method/ToDo/run"))
		self.assertTrue(d(M_OFF, "GET", "/api/v2/method/frappe.client.get_list"))


class TestSessionStillValid(unittest.TestCase):
	def _enforce(self, settings=S, active=True, privileged=False):
		loc = mock.MagicMock()
		loc.session = {"data": {"tg_origin": M_OFF}, "sid": "sidX"}
		loc.request.method = "GET"
		loc.request.path = "/app/sales-invoice/X"
		loc.form_dict = {}
		rev = mock.MagicMock()
		with (
			mock.patch.object(E.frappe, "local", loc),
			mock.patch.object(E, "_gateway_settings", return_value=settings),
			mock.patch.object(E, "_binding_active", return_value=active),
			mock.patch.object(E, "_is_privileged", return_value=privileged),
			mock.patch.object(E.frappe, "session", mock.MagicMock(user="u@x.com")),
			mock.patch.object(E, "_revoke_current_session", rev),
		):
			try:
				E.enforce()
				return True, rev
			except E._Forbidden:
				return False, rev

	def test_ok(self):
		self.assertTrue(self._enforce()[0])

	def test_newly_privileged_revoked(self):
		ok, rev = self._enforce(privileged=True)
		self.assertFalse(ok)
		rev.assert_called_once()
		self.assertTrue(self._enforce(settings={**S, "telegram_web_allow_privileged": 1}, privileged=True)[0])

	def test_missing_gateway_denied(self):
		self.assertFalse(self._enforce(settings={})[0])

	def test_inactive_binding_denied(self):
		ok, rev = self._enforce(active=False)
		self.assertFalse(ok)
		rev.assert_called_once()

	def test_privileged_roles_constant(self):
		self.assertEqual(E.PRIVILEGED_ROLES, frozenset({"System Manager", "Administrator"}))
		with mock.patch.object(E.frappe, "get_roles", return_value=["Administrator"]):
			E.clear_gateway_cache()
			self.assertTrue(E._is_privileged("u1"))
		E.clear_gateway_cache()


class TestBindingUpdate(unittest.TestCase):
	def _doc(self, **kw):
		from frappe import _dict

		return _dict(
			{
				"name": "B1",
				"is_active": 1,
				"role_scope": "a",
				"frappe_user": "old@x.com",
				"telegram_user_id": "1",
				"gateway": "G",
				**kw,
			}
		)

	def _run(self, **change):
		before = self._doc()
		doc = self._doc(**change)
		doc.get_doc_before_save = lambda: before
		with mock.patch.object(E, "revoke_binding_sessions") as rv:
			E.on_binding_update(doc)
		return rv

	def test_no_change_no_revoke(self):
		self._run().assert_not_called()

	def test_user_change_revokes_old_user(self):
		rv = self._run(frappe_user="new@x.com")
		self.assertIn(mock.call("B1", "old@x.com"), rv.call_args_list)

	def test_tg_id_and_gateway_change_revoke(self):
		self._run(telegram_user_id="2").assert_called()
		self._run(gateway="G2").assert_called()


class TestExpiryAndHours(unittest.TestCase):
	def test_naive_session_end_is_expired(self):
		sess = {"data": {"tg_origin": {"gateway": "G"}, "session_end": "2999-01-01T00:00:00"}}
		with mock.patch.object(E.frappe.local, "session", sess, create=True):
			self.assertTrue(E._session_expired())

	def test_naive_session_end_gives_403_in_enforce(self):
		loc = mock.MagicMock()
		loc.session = {"data": {"tg_origin": M_OFF, "session_end": "2999-01-01T00:00:00"}}
		loc.request.method = "GET"
		loc.request.path = "/app/sales-invoice/X"
		loc.form_dict = {}
		with mock.patch.object(E.frappe, "local", loc):
			with self.assertRaises(E._Forbidden):
				E.enforce()

	def test_hours_cap(self):
		from huf.ai import telegram_web_access as twa

		self.assertEqual(twa._session_hours({"telegram_web_session_hours": 99999}), 720)
		self.assertEqual(twa._session_hours({"telegram_web_session_hours": 5}), 5)
		self.assertEqual(twa._session_hours({}), 24)

	def test_cookie_secure_logic(self):
		from huf.ai import telegram_web_access as twa

		def scheme(req_scheme, host_name=None, fwd=None):
			req = mock.MagicMock(scheme=req_scheme)
			with (
				mock.patch.object(twa.frappe.local, "request", req, create=True),
				mock.patch.object(twa.frappe, "conf", {"host_name": host_name} if host_name else {}),
				mock.patch.object(twa.frappe, "get_request_header", return_value=fwd),
			):
				return twa._effective_scheme()

		self.assertEqual(scheme("https"), "https")
		self.assertEqual(scheme("http", fwd="https"), "http")  # spoofed header ignored
		self.assertEqual(scheme("http", host_name="https://x.example"), "https")
		self.assertEqual(scheme("http", host_name="http://x.example"), "http")


class TestCmdBypassAndReports(unittest.TestCase):
	def test_cmd_on_non_method_paths_denied(self):
		fd = {"cmd": "frappe.ping"}
		for method, path in (
			("GET", "/api/resource/User"),
			("GET", "/api/resource/ToDo/x"),
			("POST", "/api/resource/Server%20Script"),
			("GET", "/app/anything"),
			("GET", "/private/files/x"),
			("GET", "/files/a.png"),
			("GET", "/assets/x.js"),
			("GET", "/app/sales-invoice"),
		):
			for m in (M_OFF, M_ON):
				self.assertFalse(d(m, method, path, fd), (method, path))
		self.assertFalse(d(M_OFF, "GET", "/api/resource/ToDo/x", {"run_method": "m", "cmd": "frappe.ping"}))

	def test_cmd_must_match_path_method(self):
		self.assertTrue(d(M_OFF, "GET", "/api/method/frappe.ping", {"cmd": "frappe.ping"}))
		self.assertFalse(d(M_ON, "POST", "/api/method/frappe.ping", {"cmd": "frappe.client.insert"}))
		self.assertFalse(d(M_OFF, "GET", "/api/method/frappe.ping", {"cmd": ["x"]}))

	def test_legit_cmd_cases(self):
		self.assertTrue(d(M_OFF, "GET", "/api/method/frappe.ping"))
		self.assertTrue(d(M_OFF, "GET", "/", {"cmd": "frappe.ping"}))
		self.assertFalse(d(M_OFF, "POST", "/", {"cmd": "frappe.client.insert"}))
		self.assertFalse(d(M_ON, "POST", "/", {"cmd": "frappe.core.doctype.user.user.impersonate"}))

	def test_report_methods_gated(self):
		with mock.patch.object(E, "_report_ok", side_effect=lambda n: n == "Good"):
			for meth in ("frappe.desk.query_report.run", "frappe.desk.query_report.get_script"):
				self.assertTrue(d(M_OFF, "GET", f"/api/method/{meth}", {"report_name": "Good"}))
				self.assertFalse(d(M_OFF, "GET", f"/api/method/{meth}", {"report_name": "Bad"}))
				self.assertFalse(d(M_OFF, "GET", f"/api/method/{meth}", {}))
			fd = {"doctype": "Report", "name": "Good"}
			self.assertTrue(d(M_OFF, "GET", "/api/method/frappe.desk.form.load.getdoc", fd))
			self.assertFalse(
				d(M_OFF, "GET", "/api/method/frappe.desk.form.load.getdoc", {**fd, "name": "Bad"})
			)

	def test_report_ok_lookup(self):
		rows = {
			"Ok": {"ref_doctype": "ToDo", "report_type": "Script Report"},
			"Bad": {"ref_doctype": "User", "report_type": "Script Report"},
			"Cust": {"ref_doctype": "ToDo", "report_type": "Custom Report", "reference_report": "Bad"},
		}
		with mock.patch.object(
			E.frappe, "db", mock.Mock(get_value=lambda dt, n, f, as_dict=False: rows.get(n))
		):
			self.assertTrue(E._report_ok("Ok"))
			self.assertFalse(E._report_ok("Bad"))
			self.assertFalse(E._report_ok("Cust"))
			self.assertFalse(E._report_ok("Missing"))

	def test_report_not_reachable_as_resource(self):
		self.assertFalse(d(M_OFF, "GET", "/api/resource/Report/x"))

	def test_extended_blocked_list(self):
		for dt in (
			"Role Profile", "Custom Role", "Module Profile", "User Type", "User Group", "Webhook",
			"Notification", "Print Format", "Custom Field", "Property Setter", "DocType", "Report",
			"Email Account", "Access Log", "Scheduled Job Type", "Deleted Document", "Has Role",
			"User Permission", "OAuth Client",
		):  # fmt: skip
			self.assertIn(dt, E.BLOCKED_DOCTYPES)
			self.assertFalse(d(M_ON, "POST", f"/api/resource/{dt}", {}), dt)


class TestLaunchPageStaysReachable(unittest.TestCase):
	def test_launch_page_and_exchange_are_always_allowed_for_a_live_session(self):
		from huf.ai import telegram_web_access_enforce as enf

		marker = {"gateway": "G", "tg_id": "1", "binding": "B", "allow_writes": False}
		settings = {
			"telegram_web_access_enabled": 1,
			"is_enabled": 1,
			"telegram_web_allowed_paths": "/app/query-report/ToDo",
		}
		self.assertTrue(enf.decide(marker, settings, "GET", "/tg_open", {"gw": "G", "to": "/app/x"}))
		self.assertFalse(enf.decide(marker, settings, "POST", "/tg_open", {}))
		self.assertFalse(enf.decide(marker, settings, "GET", "/tg_open", {"cmd": "frappe.client.insert"}))
		self.assertTrue(
			enf.decide(marker, settings, "POST", "/api/method/huf.ai.telegram_web_access.exchange", {})
		)


class TestDeskAliasInGuard(unittest.TestCase):
	def test_desk_spelling_of_an_allowed_app_page_is_navigable(self):
		from huf.ai import telegram_web_access_enforce as enf

		marker = {"gateway": "G", "tg_id": "1", "binding": "B", "allow_writes": False}
		settings = {
			"telegram_web_access_enabled": 1,
			"is_enabled": 1,
			"telegram_web_allowed_paths": "/app/query-report/ToDo",
		}
		self.assertTrue(enf.decide(marker, settings, "GET", "/desk/query-report/ToDo", {}))
		self.assertTrue(enf.decide(marker, settings, "GET", "/app/query-report/ToDo", {}))
		self.assertFalse(enf.decide(marker, settings, "GET", "/desk/user", {}))
		self.assertFalse(enf.decide(marker, settings, "GET", "/desk/query-report/ToDoX", {}))
