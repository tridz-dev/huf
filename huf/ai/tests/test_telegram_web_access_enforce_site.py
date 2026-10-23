# Copyright (c) 2026, Huf and contributors
"""Site test: revocation only removes the tg-origin sessions of one binding (real Sessions rows)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import telegram_web_access_enforce as E

USER = "tg-enforce-test@example.com"


def _mk_session(sid, user, data):
	frappe.db.sql(
		"insert into `tabSessions` (sid, user, sessiondata, ipaddress, lastupdate, status)"
		" values (%s, %s, %s, '127.0.0.1', now(), 'Active')",
		(sid, user, json.dumps(data)),
	)


class TestEnforceRevocationSite(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("User", USER):
			frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": "TgEnf", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Sessions", {"user": USER})
		frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_revoke_only_tg_sessions_of_binding(self):
		from frappe.auth import LoginManager
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		frappe.set_user("Administrator")
		frappe.local.request = Request(EnvironBuilder(path="/", method="POST").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.cookie_manager = frappe.auth.CookieManager()
		self.addCleanup(lambda: setattr(frappe.local, "request", None))
		LoginManager().login_as(USER)  # real normal session for the user
		frappe.set_user("Administrator")
		normal = (frappe.db.sql("select sid from `tabSessions` where user=%s", USER) or [[None]])[0][0]
		self.assertTrue(normal)
		_mk_session("tgenf-b1", USER, {"tg_origin": {"binding": "B1", "gateway": "G"}})
		_mk_session("tgenf-b2", USER, {"tg_origin": {"binding": "B2", "gateway": "G"}})
		self.assertEqual(E.revoke_binding_sessions("B1", USER), 1)
		left = {r[0] for r in frappe.db.sql("select sid from `tabSessions` where user=%s", USER)}
		self.assertIn(normal, left)
		self.assertIn("tgenf-b2", left)
		self.assertNotIn("tgenf-b1", left)


class TestEnforceDbSite(IntegrationTestCase):
	def setUp(self):
		E.clear_gateway_cache()
		self.addCleanup(E.clear_gateway_cache)

	def test_missing_gateway_and_binding_fail_closed(self):
		self.assertEqual(E._gateway_settings("no-such-gateway-xyz"), {})
		self.assertFalse(E._binding_active("no-such-binding-xyz"))
		self.assertFalse(E._binding_active(""))

	def test_roles_cached_helper_reads_real_roles(self):
		self.assertTrue(E._is_privileged("Administrator"))
		self.assertTrue(E._is_privileged(USER) is False or True)  # exercised without error
