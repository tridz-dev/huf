# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram web access exchange: target validation, replay, eligibility matrix (pure, mocked Frappe)."""

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import telegram_web_access as twa
from huf.ai.gateway_adapters.telegram_miniapp import build_init_data_for_test

TOKEN = "123456:TEST-TOKEN"
GW = "tg-gw"
RAW = inspect.unwrap(twa.exchange)


class _Gw(dict):
	name = GW
	is_enabled = 1

	def get(self, key, default=None):
		return dict.get(self, key, default)


def gateway(**kw):
	base = {
		"telegram_web_access_enabled": 1,
		"telegram_web_allowed_paths": "/huf\n/app/todo",
		"telegram_web_session_hours": 24,
		"telegram_web_allow_privileged": 0,
		"telegram_web_allow_writes": 0,
	}
	base.update(kw)
	return _Gw(base)


def init(user_id=42, **extra):
	return build_init_data_for_test(TOKEN, user={"id": user_id, "first_name": "T"}, extra=extra or None)


def fake_frappe(case):
	fake = mock.MagicMock()
	fake.PermissionError = frappe.PermissionError
	fake.db.exists.side_effect = lambda *a, **k: case.gw_exists
	fake.get_doc.side_effect = lambda *a, **k: case.gw
	fake.db.get_value.side_effect = lambda *a, **k: case.user_row
	fake.get_roles.side_effect = lambda u: case.roles

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	fake.throw.side_effect = throw
	return fake


class TestTargets(unittest.TestCase):
	def test_normalize_ok(self):
		self.assertEqual(twa.normalize_target("/huf/chat?x=1#frag"), "/huf/chat?x=1")
		self.assertEqual(twa.normalize_target("/huf"), "/huf")

	def test_normalize_rejects_open_redirects(self):
		bad = [
			"",
			None,
			"huf",
			"//evil.com",
			"/\\evil.com",
			"/huf\\x",
			"https://evil.com",
			"/https://evil.com",
			"/huf@evil.com",
			"/huf/%2f%2fevil.com",
			"/huf/%5cevil",
			"/huf/%40evil",
			"/huf/%252f%252fevil",
			"/huf/%0d%0aSet-Cookie:x",
			"/huf/\r\nx",
			"/huf/../admin",
			"/huf/%2e%2e/admin",
			"/huf/\x00",
			"/huf?next=\\evil",
			"/" + "a" * 600,
			["/huf"],
		]
		for item in bad:
			self.assertIsNone(twa.normalize_target(item), item)

	def test_prefix_boundary(self):
		gw = gateway()
		self.assertEqual(twa.resolve_target("/huf/chat", gw), "/huf/chat")
		self.assertEqual(twa.resolve_target("/huf", gw), "/huf")
		self.assertEqual(twa.resolve_target("", gw), "/huf")
		for bad in ("/hufx", "/hufx/a", "/app", "/app/todos", "/desk"):
			with self.assertRaises(twa.WebAccessDenied):
				twa.resolve_target(bad, gw)

	def test_allowed_prefixes_cleanup(self):
		gw = gateway(telegram_web_allowed_paths=" /huf/ \n/\n//x\nhttps://a\n/huf\n\n/a?b")
		self.assertEqual(twa.allowed_prefixes(gw), ["/huf"])
		with self.assertRaises(twa.WebAccessDenied):
			twa.resolve_target("", gateway(telegram_web_allowed_paths=""))


class TestMarker(unittest.TestCase):
	def test_marker(self):
		m = {"web_access_version": 1, "tg_id": "1"}
		self.assertEqual(twa.session_marker({"tg_origin": m}), m)
		self.assertEqual(twa.session_marker({"data": {"tg_origin": m}}), m)
		self.assertIsNone(twa.session_marker({"tg_origin": {"web_access_version": 2}}))
		self.assertIsNone(twa.session_marker(None))
		self.assertIsNone(twa.session_marker({}))


class TestExchange(unittest.TestCase):
	def setUp(self):
		self.claims = set()
		self.gw_exists = True
		self.created = []
		self.gw = gateway()
		self.binding = {"name": "B1", "telegram_user_id": "42", "frappe_user": "u@x.com", "gateway": GW}
		self.user_row = SimpleNamespace(enabled=1, user_type="System User")
		self.roles = ["Desk User"]
		self.audits = []
		self.fake = fake_frappe(self)
		patches = [
			mock.patch.object(twa, "_", side_effect=lambda m: m),
			mock.patch.object(twa, "_check_origin"),
			mock.patch.object(twa, "_bot_token", return_value=TOKEN),
			mock.patch.object(twa, "get_binding", side_effect=lambda tg, g: self.binding),
			mock.patch.object(twa, "_claim_once", side_effect=self._claim),
			mock.patch.object(twa, "check_rate", return_value=True),
			mock.patch.object(twa, "_create_session", side_effect=lambda *a: self.created.append(a)),
			mock.patch.object(twa, "_existing_session_ok", return_value=False),
			mock.patch.object(twa, "_audit", side_effect=lambda *a: self.audits.append(a)),
			mock.patch.object(twa, "_log"),
			mock.patch.object(twa, "frappe", self.fake),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def _claim(self, key):
		if key in self.claims:
			return False
		self.claims.add(key)
		return True

	def run_ex(self, data=None, to="", gw=GW):
		ctx = {}
		return twa._exchange(data if data is not None else init(), gw, to, twa._digest(data or ""), ctx)

	def denied(self, code, **kw):
		with self.assertRaises(twa.WebAccessDenied) as cm:
			self.run_ex(**kw)
		self.assertEqual(cm.exception.code, code)
		self.assertEqual(self.created, [])

	def test_happy_path(self):
		out = self.run_ex(to="/huf/chat")
		self.assertEqual(out, {"ok": True, "redirect": "/huf/chat"})
		self.assertEqual(len(self.created), 1)

	def test_wrong_token(self):
		bad = build_init_data_for_test("9:OTHER", user={"id": 42})
		self.denied("init_data_invalid", data=bad)

	def test_expired_over_120s(self):
		import time

		old = build_init_data_for_test(TOKEN, user={"id": 42}, auth_date=int(time.time()) - 121)
		self.denied("init_data_invalid", data=old)
		fresh = build_init_data_for_test(TOKEN, user={"id": 42}, auth_date=int(time.time()) - 100)
		self.assertTrue(self.run_ex(data=fresh)["ok"])

	def test_replay_hash_and_query_id(self):
		data = init()
		self.run_ex(data=data)
		self.created.clear()
		self.denied("replayed", data=data)
		a = init(query_id="Q1")
		self.run_ex(data=a)
		self.created.clear()
		import time

		b = build_init_data_for_test(
			TOKEN, user={"id": 42}, extra={"query_id": "Q1"}, auth_date=int(time.time()) - 1
		)
		self.denied("replayed_query", data=b)

	def test_chat_type(self):
		self.denied("chat_type", data=init(chat_type="group"))
		self.denied("chat_type", data=init(chat_type="supergroup"))
		self.assertTrue(self.run_ex(data=init(chat_type="private"))["ok"])
		self.assertTrue(self.run_ex(data=init(7, chat_type="sender"))["ok"])

	def test_unbound(self):
		self.binding = None
		self.denied("unbound")

	def test_gateway_disabled_and_web_off(self):
		self.gw = gateway(telegram_web_access_enabled=0)
		self.denied("web_access_disabled")
		self.gw = gateway()
		self.gw.is_enabled = 0
		self.denied("gateway_disabled")

	def test_unknown_gateway(self):
		self.gw_exists = False
		self.denied("gateway_unknown")

	def test_privileged(self):
		self.roles = ["Desk User", "System Manager"]
		self.denied("privileged_denied")
		self.claims.clear()
		self.gw = gateway(telegram_web_allow_privileged=1)
		self.assertTrue(self.run_ex()["ok"])

	def test_forbidden_users(self):
		for user in ("Administrator", "Guest"):
			self.binding = {**self.binding, "frappe_user": user}
			self.denied("user_forbidden", data=init())
			self.claims.clear()
		self.gw = gateway(telegram_web_allow_privileged=1)
		self.binding = {**self.binding, "frappe_user": "Administrator"}
		self.denied("user_forbidden")

	def test_disabled_and_website_user(self):
		self.user_row = SimpleNamespace(enabled=0, user_type="System User")
		self.denied("user_disabled")
		self.user_row = SimpleNamespace(enabled=1, user_type="Website User")
		self.denied("user_type", data=init(43))

	def test_rate_limited_per_tg_user(self):
		with mock.patch.object(twa, "check_rate", return_value=False):
			self.denied("rate_limited")

	def test_bad_target_does_not_burn_init_data(self):
		data = init()
		self.denied("target_not_allowed", data=data, to="/desk")
		self.assertEqual(self.claims, set())
		self.assertTrue(self.run_ex(data=data)["ok"])

	def test_bad_request_types(self):
		self.denied("bad_request", data="")
		with self.assertRaises(twa.WebAccessDenied):
			twa._exchange(init(), None, "", "x", {})


class TestUniformFailure(unittest.TestCase):
	def setUp(self):
		p = mock.patch.object(twa, "_", side_effect=lambda m: m)
		p.start()
		self.addCleanup(p.stop)

	def fake_with_logger(self, logger):
		fake = fake_frappe(SimpleNamespace(gw_exists=True, gw=None, user_row=None, roles=[]))
		fake.logger.return_value = logger
		return fake

	def test_endpoint_uniform_error_and_no_secrets_logged(self):
		logged = []
		secret = init()
		sid_like = "SECRETSID"
		fake_logger = SimpleNamespace(info=logged.append, warning=logged.append)
		with (
			mock.patch.object(twa, "_exchange", side_effect=twa.WebAccessDenied("unbound")),
			mock.patch.object(twa, "frappe", self.fake_with_logger(fake_logger)),
			mock.patch.object(twa, "_audit"),
		):
			with self.assertRaises(frappe.PermissionError) as cm:
				RAW(secret, GW, sid_like)
		self.assertIn("Not authorized", str(cm.exception))
		self.assertNotIn("unbound", str(cm.exception))
		blob = json.dumps(logged)
		self.assertNotIn(secret, blob)
		self.assertNotIn(sid_like, blob)

	def test_internal_error_is_uniform(self):
		with (
			mock.patch.object(twa, "_exchange", side_effect=RuntimeError("boom secret")),
			mock.patch.object(twa, "_audit"),
			mock.patch.object(twa, "_log"),
			mock.patch.object(twa, "frappe", self.fake_with_logger(SimpleNamespace(warning=lambda m: None))),
		):
			with self.assertRaises(frappe.PermissionError) as cm:
				RAW(init(), GW, "")
		self.assertNotIn("boom", str(cm.exception))

	def test_log_line_has_only_codes(self):
		lines = []
		with mock.patch.object(twa, "frappe", self.fake_with_logger(SimpleNamespace(info=lines.append))):
			twa._log("replayed", twa._digest(init()), "42", "B1", "denied")
		self.assertEqual(len(lines), 1)
		self.assertRegex(lines[0], r"reason=replayed h=[0-9a-f]{12} tg=42 binding=B1")
		self.assertNotIn("hash=", lines[0])
