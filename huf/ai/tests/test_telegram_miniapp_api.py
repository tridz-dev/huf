# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Mini App API (WP-A). Pure-logic tests: no site, no live Telegram (fakes only)."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai import telegram_admin as ta
from huf.ai import telegram_miniapp_api as api

NOW = 1_800_000_000.0
BOUND = "ops@example.com"
TG = "777"
GW = "tg-gw"
BINDING = {
	"name": "bind-1",
	"telegram_user_id": TG,
	"frappe_user": BOUND,
	"gateway": GW,
	"role_scope": "Operator",
	"chat_id": TG,
}


class Base(unittest.TestCase):
	def setUp(self):
		self.cache = ta.MemCache()
		from huf.ai.tests.telegram_fakes import isolate_admin_cache, set_local_flags

		set_local_flags(self, in_test=False)
		isolate_admin_cache(self, ta, self.cache)
		self.user = ["Guest"]
		self.users_seen = []
		self.audit = []
		self.bindings = {(TG, GW): dict(BINDING)}
		patches = [
			patch.object(ta, "_LOCAL", self.cache),
			patch.object(ta, "_current_user", lambda: self.user[0]),
			patch.object(ta, "_set_user", self._set_user),
			patch.object(ta, "_user_enabled", lambda u: True),
			patch.object(ta, "get_binding", lambda tg, gw, **kw: self._lookup(tg, gw)),
			patch.object(ta, "_commit", lambda: None),
			patch.object(ta, "_rollback", lambda: None),
			patch.object(ta, "_client_ip", lambda: "1.2.3.4"),
			patch.object(ta, "write_audit", lambda b, a, r, **kw: self.audit.append((b, a, r, kw))),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		self.token = ta.mint_session_token(self.bindings[(TG, GW)])

	def _lookup(self, tg, gw):
		row = self.bindings.get((str(tg), gw))
		return dict(row) if row else None

	def _set_user(self, user):
		self.users_seen.append(user)
		self.user[0] = user

	def call(self, fn, *a, token=None, **kw):
		"""Invoke an endpoint with the token sent in the X-Huf-Tg-Token header (the only accepted transport)."""
		raw = self.token if token is None else token
		with patch("frappe.get_request_header", lambda h: raw if h == api.TOKEN_HEADER else None):
			return fn(*a, **kw)

	def assertErr(self, res, code, status=None):
		self.assertFalse(res["ok"], res)
		self.assertEqual(res["error"]["code"], code)
		self.assertNotIn("Traceback", str(res))


class TestAuth(Base):
	def test_missing_token(self):
		self.assertErr(api.me(), "unauthorized")
		self.assertErr(self.call(api.me, token="short"), "unauthorized")

	def test_unknown_token(self):
		self.assertErr(self.call(api.me, token="x" * 40), "unauthorized")

	def test_expired_token(self):
		old = ta.mint_session_token(self.bindings[(TG, GW)], now=time.time() - 5000)
		self.assertErr(self.call(api.me, token=old), "unauthorized")

	def test_query_param_token_rejected(self):
		# The token must never be accepted from the URL/param; only the header counts.
		self.assertErr(api.me(token=self.token), "unauthorized")
		self.assertErr(api.config(token=self.token), "unauthorized")
		self.assertErr(api.act_confirm("nonce", token=self.token), "unauthorized")

	def test_token_endpoints_are_post_only(self):
		allowed = getattr(frappe, "allowed_http_methods_for_whitelisted_func", {})
		for fn in (api.me, api.config, api.search, api.get_doc_summary, api.approvals, api.act_prepare,
			api.act_confirm, api.digest, api.audit, api.revoke_token):
			self.assertEqual(list(allowed.get(fn, [])), ["POST"], fn.__name__)

	def test_query_param_rejected_even_with_valid_header(self):
		with patch("frappe.get_request_header", lambda h: self.token if h == api.TOKEN_HEADER else None):
			self.assertErr(api.me(token=self.token), "unauthorized")

	def test_revoked_token(self):
		self.assertTrue(self.call(api.revoke_token)["ok"])
		self.assertErr(self.call(api.me), "unauthorized")
		self.assertEqual(self.audit[-1][1]["op"], "miniapp_logout")

	def test_binding_revoked(self):
		self.bindings.clear()
		self.assertErr(self.call(api.me), "unauthorized")

	def test_binding_downgraded_applies_live(self):
		self.bindings[(TG, GW)]["role_scope"] = "Viewer"
		res = self.call(api.config)
		self.assertEqual(res["data"]["role_scope"], "Viewer")
		self.assertFalse(res["data"]["features"]["act"])
		self.assertErr(self.call(api.act_prepare, "Leave Application", "LA-1", "Approve"), "permission_denied")

	def test_token_for_other_binding_row_rejected(self):
		self.bindings[(TG, GW)]["name"] = "bind-2"  # re-bound since token mint
		self.assertErr(self.call(api.me), "unauthorized")

	def test_header_token(self):
		with (
			patch("frappe.get_request_header", lambda h: self.token if h == api.TOKEN_HEADER else None),
			patch("frappe.utils.get_fullname", lambda u: "Ops"),
		):
			res = api.me()
		self.assertTrue(res["ok"])

	def test_rate_limited(self):
		with patch.object(api, "API_RATE_LIMIT", 2):
			self.assertTrue(self.call(api.config)["ok"])
			self.assertTrue(self.call(api.config)["ok"])
			self.assertErr(self.call(api.config), "rate_limited")

	def test_me_runs_as_bound_user_and_restores(self):
		with patch("frappe.utils.get_fullname", lambda u: "Ops Person"):
			res = self.call(api.me)
		self.assertEqual(res["data"]["frappe_user"], BOUND)
		self.assertEqual(self.users_seen, [BOUND, "Guest"])
		self.assertEqual(self.user[0], "Guest")
		self.assertNotIn("token", str(res["data"]).lower())


class TestSearch(Base):
	def _meta(self):
		return SimpleNamespace(
			title_field="customer_name", has_field=lambda f: True, istable=0, issingle=0
		)

	def test_search_runs_as_user_with_permission_checked_list(self):
		import frappe

		seen = []

		def get_list(dt, **kw):
			seen.append((dt, self.user[0], kw["limit_page_length"]))
			return [{"name": "C-1", "customer_name": "Acme"}]

		with (
			patch.object(frappe, "get_meta", lambda dt: self._meta()),
			patch.object(frappe, "get_list", get_list),
			patch.object(frappe, "get_all", side_effect=AssertionError("bypasses permissions")),
		):
			res = self.call(api.search, "Customer", "acme", 999)
		self.assertEqual(seen, [("Customer", BOUND, api.SEARCH_MAX)])
		self.assertEqual(res["data"]["items"], [{"name": "C-1", "title": "Acme"}])

	def test_deny_doctypes(self):
		import frappe

		for dt in ("User", "Gateway", "Telegram Admin Audit", "Huf API Key"):
			with patch.object(frappe, "get_list", side_effect=AssertionError("must not query")):
				res = self.call(api.search, dt, "x")
			self.assertErr(res, "refused")
			self.assertNotIn(dt, res["error"]["message"])

	def test_permission_error_surfaced(self):
		import frappe

		def get_list(dt, **kw):
			raise frappe.PermissionError("no read on Salary Slip: secret detail")

		with patch.object(frappe, "get_meta", lambda dt: self._meta()), patch.object(frappe, "get_list", get_list):
			res = self.call(api.search, "Salary Slip", "")
		self.assertErr(res, "permission_denied")
		self.assertEqual(res["error"]["message"], "You do not have permission for that.")
		self.assertEqual(self.user[0], "Guest")

	def test_internal_error_has_no_internals(self):
		import frappe

		with (
			patch.object(frappe, "get_meta", lambda dt: self._meta()),
			patch.object(frappe, "get_list", side_effect=RuntimeError("db password=hunter2 at /srv/x.py")),
		):
			res = self.call(api.search, "Customer", "")
		self.assertErr(res, "internal")
		self.assertNotIn("hunter2", str(res))
		self.assertEqual(self.user[0], "Guest")


def _field(name, ftype="Data", permlevel=0, in_list=1, hidden=0, label=None):
	return SimpleNamespace(
		fieldname=name, fieldtype=ftype, permlevel=permlevel, in_list_view=in_list, hidden=hidden, label=label
	)


class TestSummary(Base):
	def _doc(self, **values):
		values = {"customer_name": "Acme", "api_secret": "S3CRET", "pw": "hunter2", "salary": "9999", **values}
		doc = MagicMock()
		doc.name = "C-1"
		doc.docstatus = 0
		doc.modified = "2026-01-01 00:00:00"
		doc.get.side_effect = lambda k, d=None: values.get(k, d)
		return doc

	def test_summary_filters_secret_fields(self):
		import frappe

		meta = SimpleNamespace(
			title_field="customer_name",
			istable=0,
			issingle=0,
			is_submittable=0,
			get_workflow=lambda: None,
			fields=[
				_field("customer_name"),
				_field("api_secret"),
				_field("pw", "Password"),
				_field("salary", permlevel=1),
				_field("territory"),
			],
		)
		doc = self._doc(territory="North")
		with (
			patch.object(frappe, "get_meta", lambda dt: meta),
			patch.object(frappe, "get_doc", lambda dt, dn: doc),
			patch.object(ta, "_desk_url", lambda dt, dn: "https://x/app/customer/C-1"),
			patch.object(ta, "_transitions", lambda d: ["Approve"]),
		):
			res = self.call(api.get_doc_summary, "Customer", "C-1")
		names = [f["fieldname"] for f in res["data"]["fields"]]
		self.assertEqual(names, ["customer_name", "territory"])
		self.assertNotIn("S3CRET", str(res))
		self.assertNotIn("hunter2", str(res))
		self.assertNotIn("9999", str(res))
		self.assertEqual(res["data"]["actions"], ["Approve"])
		doc.check_permission.assert_called_with("read")

	def test_summary_hides_masked_and_broad_secret_names(self):
		import frappe

		meta = SimpleNamespace(
			title_field=None, istable=0, issingle=0, is_submittable=0, get_workflow=lambda: None,
			fields=[
				_field("customer_name"), _field("pairing_code"), _field("sig_hash"), _field("access_key"),
				_field("ssn_masked"), _field("territory"),
			],
		)
		meta.fields[4].mask = 1
		doc = self._doc(pairing_code="PC", sig_hash="H", access_key="K", ssn_masked="123", territory="N")
		doc.has_permlevel_access_to.side_effect = lambda fn, df=None, pt="read": fn != "territory"
		with (
			patch.object(frappe, "get_meta", lambda dt: meta),
			patch.object(frappe, "get_doc", lambda dt, dn: doc),
			patch.object(ta, "_desk_url", lambda dt, dn: ""),
			patch.object(ta, "_transitions", lambda d: []),
		):
			res = self.call(api.get_doc_summary, "Customer", "C-1")
		self.assertEqual([f["fieldname"] for f in res["data"]["fields"]], ["customer_name"])

	def test_nonce_bound_to_gateway(self):
		act = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}
		other = ta.issue_nonce(TG, f"{api.MINIAPP_CHAT}:OtherGW", act)
		self.assertErr(self.call(api.act_confirm, other), "permission_denied")

	def test_viewer_gets_no_actions(self):
		import frappe

		self.bindings[(TG, GW)]["role_scope"] = "Viewer"
		meta = SimpleNamespace(
			title_field=None, istable=0, issingle=0, is_submittable=0, get_workflow=lambda: None, fields=[_field("customer_name")]
		)
		with (
			patch.object(frappe, "get_meta", lambda dt: meta),
			patch.object(frappe, "get_doc", lambda dt, dn: self._doc()),
			patch.object(ta, "_desk_url", lambda dt, dn: ""),
			patch.object(ta, "_transitions", side_effect=AssertionError("not for viewers")),
		):
			res = self.call(api.get_doc_summary, "Customer", "C-1")
		self.assertEqual(res["data"]["actions"], [])

	def test_denied_doctype_and_permission_error(self):
		import frappe

		self.assertErr(self.call(api.get_doc_summary, "User", "x"), "refused")
		doc = self._doc()
		doc.check_permission.side_effect = frappe.PermissionError("nope")
		meta = SimpleNamespace(istable=0, issingle=0)
		with patch.object(frappe, "get_meta", lambda dt: meta), patch.object(frappe, "get_doc", lambda dt, dn: doc):
			res = self.call(api.get_doc_summary, "Customer", "C-1")
		self.assertErr(res, "permission_denied")


class TestApprovalsDigest(Base):
	def test_approvals_skip_denied_and_unreadable(self):
		import frappe

		rows = [
			{"reference_doctype": "User", "reference_name": "u", "workflow_state": "x"},
			{"reference_doctype": "Leave Application", "reference_name": "LA-1", "workflow_state": "Pending"},
			{"reference_doctype": "Expense", "reference_name": "E-1", "workflow_state": "Pending"},
		]

		def get_doc(dt, dn):
			doc = MagicMock()
			if dt == "Expense":
				doc.check_permission.side_effect = frappe.PermissionError("no")
			return doc

		with (
			patch.object(ta, "pending_approvals", lambda limit=10: rows),
			patch.object(frappe, "get_doc", get_doc),
			patch.object(ta, "_transitions", lambda d: ["Approve", "Reject"]),
		):
			res = self.call(api.approvals)
		self.assertEqual(
			res["data"]["items"],
			[{"doctype": "Leave Application", "name": "LA-1", "state": "Pending", "actions": ["Approve", "Reject"]}],
		)

	def test_digest(self):
		data = {
			"user": BOUND,
			"actions_24h": 3,
			"approvals": [{"reference_doctype": "Leave Application", "reference_name": "LA-1", "workflow_state": "P"}],
		}
		seen = []
		with patch.object(ta, "collect_digest", lambda b, **kw: seen.append(self.user[0]) or data):
			res = self.call(api.digest)
		self.assertEqual(seen, [BOUND])
		self.assertIn("Pending approvals: 1", res["data"]["text"])
		self.assertEqual(res["data"]["actions_24h"], 3)


class TestActions(Base):
	def _workflow_patches(self, applied, error=None):
		import frappe
		import frappe.model.workflow as wf

		doc = MagicMock()
		doc.name = "LA-1"
		doc.get.side_effect = lambda k, d=None: "Approved" if k == "workflow_state" else None

		def apply_workflow(d, action):
			applied.append((action, self.user[0]))
			if error:
				raise error
			return doc

		return [
			patch.object(frappe, "get_doc", lambda dt, dn: doc),
			patch.object(frappe, "get_meta", lambda dt: SimpleNamespace(istable=0, issingle=0)),
			patch.object(frappe, "db", MagicMock(), create=True),
			patch.object(wf, "apply_workflow", apply_workflow),
			patch.object(ta, "_transitions", lambda d: ["Approve", "Reject"]),
		]

	def _start(self, patches):
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def test_prepare_confirm_executes_once_as_user_and_audits(self):
		applied = []
		self._start(self._workflow_patches(applied))
		prep = self.call(api.act_prepare, "Leave Application", "LA-1", "Approve")
		self.assertTrue(prep["ok"], prep)
		self.assertEqual(applied, [])  # prepare never mutates
		self.assertIn("Apply 'Approve' to Leave Application LA-1", prep["data"]["description"])
		nonce = prep["data"]["nonce"]
		res = self.call(api.act_confirm, nonce)
		self.assertTrue(res["ok"], res)
		self.assertEqual(applied, [("Approve", BOUND)])
		self.assertEqual(self.user[0], "Guest")
		self.assertEqual(self.audit[-1][2], "ok")
		self.assertEqual(self.audit[-1][1]["transition"], "Approve")
		# replay
		again = self.call(api.act_confirm, nonce)
		self.assertErr(again, "refused")
		self.assertEqual(len(applied), 1)

	def test_cross_user_nonce_rejected(self):
		applied = []
		self._start(self._workflow_patches(applied))
		nonce = self.call(api.act_prepare, "Leave Application", "LA-1", "Approve")["data"]["nonce"]
		other = {**BINDING, "name": "bind-9", "telegram_user_id": "888", "frappe_user": "other@example.com"}
		self.bindings[("888", GW)] = other
		other_token = ta.mint_session_token(other)
		res = self.call(api.act_confirm, nonce, token=other_token)
		self.assertErr(res, "permission_denied")
		self.assertEqual(applied, [])
		# the owner can still confirm: a foreign press must not burn the nonce
		self.assertTrue(self.call(api.act_confirm, nonce)["ok"])

	def test_chat_cockpit_nonce_not_usable_from_miniapp(self):
		applied = []
		self._start(self._workflow_patches(applied))
		act = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}
		nonce = ta.issue_nonce(TG, TG, act)  # issued for the private chat
		self.assertErr(self.call(api.act_confirm, nonce), "permission_denied")
		self.assertEqual(applied, [])

	def test_expired_and_malformed_nonce(self):
		self.assertErr(self.call(api.act_confirm, "nope"), "invalid")
		self.assertErr(self.call(api.act_confirm, "a" * 16), "refused")
		act = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}
		old = ta.issue_nonce(TG, api.nonce_chat(BINDING), act, now=NOW - 10_000)
		self.assertErr(self.call(api.act_confirm, old), "refused")

	def test_unavailable_transition_and_denied_doctype(self):
		self._start(self._workflow_patches([]))
		self.assertErr(self.call(api.act_prepare, "Leave Application", "LA-1", "Explode"), "invalid")
		self.assertErr(self.call(api.act_prepare, "User", "x", "Approve"), "refused")
		self.assertErr(self.call(api.act_prepare, "Leave Application", "", "Approve"), "invalid")

	def test_permission_error_on_confirm_is_surfaced_and_audited(self):
		import frappe

		self._start(self._workflow_patches([], error=frappe.PermissionError("Not allowed")))
		nonce = self.call(api.act_prepare, "Leave Application", "LA-1", "Approve")["data"]["nonce"]
		res = self.call(api.act_confirm, nonce)
		self.assertFalse(res["ok"])
		self.assertEqual(self.audit[-1][2], "error")
		self.assertEqual(self.user[0], "Guest")

	def test_viewer_cannot_prepare_or_confirm(self):
		applied = []
		self._start(self._workflow_patches(applied))
		nonce = self.call(api.act_prepare, "Leave Application", "LA-1", "Approve")["data"]["nonce"]
		self.bindings[(TG, GW)]["role_scope"] = "Viewer"  # demoted between prepare and confirm
		self.assertErr(self.call(api.act_confirm, nonce), "refused")
		self.assertEqual(applied, [])


class TestAudit(Base):
	ROW = {
		"name": "a1",
		"action": "workflow",
		"frappe_user": BOUND,
		"reference_doctype": "Leave Application",
		"reference_name": "LA-1",
		"result": "ok",
		"creation": "2026-01-01 10:00:00",
	}

	def test_operator_sees_own_rows_only(self):
		import frappe

		captured = {}

		def get_all(dt, **kw):
			captured.update(kw)
			return [dict(self.ROW)]

		with (
			patch.object(frappe, "get_all", get_all),
			patch.object(frappe, "get_list", side_effect=AssertionError("admin path")),
		):
			res = self.call(api.audit, 500)
		self.assertEqual(captured["filters"], {"frappe_user": BOUND})
		self.assertEqual(captured["limit_page_length"], api.AUDIT_MAX)
		self.assertEqual(res["data"]["scope"], "own")
		self.assertNotIn("arguments_json", str(res))

	def test_admin_sees_all_via_permission_checked_list(self):
		import frappe

		self.bindings[(TG, GW)]["role_scope"] = "Admin"
		seen = []

		def get_list(dt, **kw):
			seen.append(self.user[0])
			return [dict(self.ROW)]

		with (
			patch.object(frappe, "get_list", get_list),
			patch.object(frappe, "get_all", side_effect=AssertionError("must use get_list")),
		):
			res = self.call(api.audit, 5)
		self.assertEqual(seen, [BOUND])
		self.assertEqual(res["data"]["scope"], "all")


class TestConfig(Base):
	def test_config_shape(self):
		import frappe

		db = MagicMock()
		db.get_value.return_value = "My Bot"
		with patch.object(frappe, "db", db, create=True):
			res = self.call(api.config)
		data = res["data"]
		self.assertEqual(data["bot_name"], "My Bot")
		self.assertEqual(data["gateway"], GW)
		self.assertEqual(data["role_scope"], "Operator")
		self.assertTrue(data["features"]["act"])
		self.assertFalse(data["features"]["audit_all"])
		self.assertEqual(data["confirm_ttl"], ta.NONCE_TTL)


if __name__ == "__main__":
	unittest.main()
