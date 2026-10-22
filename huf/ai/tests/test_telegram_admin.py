# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram admin cockpit (WP-9). Pure-logic tests: no site, no live Telegram, no LLM (fakes only)."""

import dataclasses
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import telegram_admin as ta
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_keyboards as kb
from huf.ai.gateway_adapters import telegram_miniapp as miniapp
from huf.ai.gateway_adapters.telegram_inbound import TelegramUpdate

TOKEN = "123456:TEST-not-a-real-token"
NOW = 1_800_000_000.0
KEY = kb.derive_callback_key("webhook-secret-for-tests")
BOUND = "ops@example.com"
TG = "777"
CHAT = "777"
GW = "tg-gw"
BINDING = {
	"name": "bind-1",
	"telegram_user_id": TG,
	"frappe_user": BOUND,
	"gateway": GW,
	"role_scope": "Operator",
	"chat_id": CHAT,
}


class FakeAdapter:
	def __init__(self):
		self.sender = MagicMock()

	def sign_callback_data(self, payload, chat_id=""):
		return kb.sign_callback(KEY, payload, context=str(chat_id))

	def verify_callback_data(self, data, chat_id=""):
		return kb.verify_callback(KEY, data, context=str(chat_id))


def _msg(text, *, command="", start_payload="", sender=TG, chat=CHAT, chat_type="private"):
	return TelegramUpdate(
		kind="message",
		update_id="1",
		raw={},
		chat_id=chat,
		chat_type=chat_type,
		sender_id=sender,
		message_id="10",
		text=text,
		command=command,
		start_payload=start_payload,
	)


def _cb(data, *, sender=TG, chat=CHAT):
	return TelegramUpdate(
		kind="callback_query",
		update_id="2",
		raw={},
		chat_id=chat,
		chat_type="private",
		sender_id=sender,
		message_id="11",
		callback_query_id="cq1",
		callback_data=data,
	)


class Base(unittest.TestCase):
	def setUp(self):
		self.cache = ta.MemCache(clock=lambda: self.now)
		self.now = NOW
		self.user = ["Guest"]
		self.users_seen = []
		self.audit = []
		self.adapter = FakeAdapter()
		self.gateway = SimpleNamespace(name=GW)
		self.bindings = {(TG, GW): dict(BINDING)}
		patches = [
			patch.object(ta, "_current_user", lambda: self.user[0]),
			patch.object(ta, "_set_user", self._set_user),
			patch.object(ta, "_user_enabled", lambda u: True),
			patch.object(ta, "get_binding", lambda tg, gw, **kw: self.bindings.get((str(tg), gw))),
			patch.object(ta, "_touch_binding", lambda name: None),
			patch.object(ta, "_commit", lambda: None),
			patch.object(ta, "_rollback", lambda: None),
			patch.object(ta, "miniapp_launch_url", lambda b: ""),
			patch.object(ta, "write_audit", self._audit),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def _set_user(self, user):
		self.user[0] = user
		self.users_seen.append(user)

	def _audit(self, binding, action, result, **kw):
		self.audit.append({"binding": binding, "action": action, "result": result, **kw})

	def handle_msg(self, parsed):
		return ta.handle_message(self.gateway, self.adapter, parsed, cache=self.cache, now=self.now)

	def handle_cb(self, data, **kw):
		return ta.handle_callback(self.gateway, self.adapter, _cb(data, **kw), cache=self.cache, now=self.now)

	def sent_texts(self):
		return [c.args[1] for c in self.adapter.sender.send_text.call_args_list]

	def last_markup(self):
		return self.adapter.sender.send_text.call_args_list[-1].kwargs.get("markup")

	def buttons(self):
		return [
			b
			for row in (self.last_markup() or {}).get("inline_keyboard", [])
			for b in row
			if "callback_data" in b
		]


class TestNonces(Base):
	ACTION = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}

	def test_single_use(self):
		n = ta.issue_nonce(TG, CHAT, self.ACTION, cache=self.cache, now=NOW)
		self.assertEqual(ta.consume_nonce(n, TG, CHAT, cache=self.cache, now=NOW), self.ACTION)
		with self.assertRaises(ta.AdminError):
			ta.consume_nonce(n, TG, CHAT, cache=self.cache, now=NOW)

	def test_expired(self):
		n = ta.issue_nonce(TG, CHAT, self.ACTION, cache=self.cache, now=NOW)
		with self.assertRaisesRegex(ta.AdminError, "expired"):
			ta.consume_nonce(n, TG, CHAT, cache=self.cache, now=NOW + ta.NONCE_TTL + 1)

	def test_cross_user_and_cross_chat_rejected_without_burning(self):
		n = ta.issue_nonce(TG, CHAT, self.ACTION, cache=self.cache, now=NOW)
		with self.assertRaisesRegex(ta.AdminError, "Not authorised"):
			ta.consume_nonce(n, "999", CHAT, cache=self.cache, now=NOW)
		with self.assertRaisesRegex(ta.AdminError, "Not authorised"):
			ta.consume_nonce(n, TG, "-100", cache=self.cache, now=NOW)
		self.assertEqual(ta.consume_nonce(n, TG, CHAT, cache=self.cache, now=NOW), self.ACTION)

	def test_tampered_action_hash(self):
		n = ta.issue_nonce(TG, CHAT, self.ACTION, cache=self.cache, now=NOW)
		rec = self.cache.get_value(f"huf_tg_adm_n:{n}")
		rec["a"] = {**self.ACTION, "dn": "LA-2"}
		with self.assertRaises(ta.AdminError):
			ta.consume_nonce(n, TG, CHAT, cache=self.cache, now=NOW)

	def test_payload_fits_callback_data(self):
		n = ta.issue_nonce(TG, CHAT, self.ACTION, cache=self.cache, now=NOW)
		data = self.adapter.sign_callback_data(ta.callback_payload("c", n), CHAT)
		self.assertLessEqual(len(data.encode()), 64)
		self.assertEqual(ta.parse_callback_payload(ta.callback_payload("c", n)), ("c", n))
		self.assertIsNone(ta.parse_callback_payload("adm:z:" + n))
		self.assertIsNone(ta.parse_callback_payload("b:--:x"))


class TestBindCodes(Base):
	def test_single_use_and_gateway_bound(self):
		code = ta.mint_bind_code(BOUND, GW, "Viewer", cache=self.cache)
		self.assertIsNone(ta.consume_bind_code("BIND-" + code, "other-gw", cache=self.cache))
		rec = ta.consume_bind_code("BIND-" + code.lower(), GW, cache=self.cache)
		self.assertEqual(rec, {"user": BOUND, "gateway": GW, "role_scope": "Viewer"})
		self.assertIsNone(ta.consume_bind_code("BIND-" + code, GW, cache=self.cache))

	def test_never_for_administrator_or_guest(self):
		for user in ("Administrator", "Guest", ""):
			with self.assertRaises(ta.AdminError):
				ta.mint_bind_code(user, GW, "Viewer", cache=self.cache)

	def test_only_hash_is_stored(self):
		code = ta.mint_bind_code(BOUND, GW, "Viewer", cache=self.cache)
		self.assertFalse(any(code in k for k in self.cache.d))

	def test_start_bind_creates_binding_once(self):
		code = ta.mint_bind_code(BOUND, GW, "Operator", cache=self.cache)
		created = []
		with patch.object(
			ta, "create_binding", lambda rec, tg, chat, name="": created.append(rec) or dict(BINDING)
		):
			res = self.handle_msg(_msg(f"/start BIND-{code}", command="start", start_payload=f"BIND-{code}"))
			self.assertEqual(res["note"], "bound")
			res = self.handle_msg(_msg(f"/start BIND-{code}", command="start", start_payload=f"BIND-{code}"))
			self.assertEqual(res["note"], "bind_invalid")
		self.assertEqual(len(created), 1)
		self.assertEqual(self.audit[0]["action"]["op"], "bind")

	def test_self_assertion_never_binds(self):
		self.bindings.clear()
		with patch.object(ta, "create_binding") as create:
			res = self.handle_msg(
				_msg("/start BIND-AAAAAAAAAA", command="start", start_payload="BIND-AAAAAAAAAA")
			)
		self.assertEqual(res["note"], "bind_invalid")
		create.assert_not_called()

	def test_bind_attempts_rate_limited(self):
		for _ in range(ta.BIND_ATTEMPT_LIMIT):
			self.handle_msg(_msg("/start BIND-ZZZZZZZZZZ", command="start", start_payload="BIND-ZZZZZZZZZZ"))
		res = self.handle_msg(
			_msg("/start BIND-ZZZZZZZZZZ", command="start", start_payload="BIND-ZZZZZZZZZZ")
		)
		self.assertEqual(res["note"], "bind_rate_limited")


class TestRouting(Base):
	def test_no_binding_falls_through(self):
		self.bindings.clear()
		self.assertIsNone(self.handle_msg(_msg("/help", command="help")))
		self.adapter.sender.send_text.assert_not_called()

	def test_free_text_and_groups_fall_through(self):
		self.assertIsNone(self.handle_msg(_msg("what's my revenue?")))
		self.assertIsNone(self.handle_msg(_msg("/help", command="help", chat_type="group", chat="-100")))
		self.assertIsNone(self.handle_msg(_msg("/weather", command="weather")))

	def test_help_for_bound_user(self):
		res = self.handle_msg(_msg("/help", command="help"))
		self.assertEqual(res["note"], "command:help")
		self.assertIn("/approvals", self.sent_texts()[-1])

	def test_rate_limit(self):
		for _ in range(ta.RATE_LIMIT):
			self.handle_msg(_msg("/help", command="help"))
		res = self.handle_msg(_msg("/help", command="help"))
		self.assertEqual(res["note"], "rate_limited")
		self.now += ta.RATE_WINDOW
		self.assertEqual(self.handle_msg(_msg("/help", command="help"))["note"], "command:help")

	def test_viewer_cannot_use_admin_command(self):
		self.bindings[(TG, GW)]["role_scope"] = "Viewer"
		self.handle_msg(_msg("/audit", command="audit"))
		self.assertIn("Admin scope required", self.sent_texts()[-1])

	def test_registered_in_update_registry_and_chains(self):
		import huf.ai.gateway_adapters.telegram_admin_hooks as hooks  # noqa: F401

		self.assertIn("message", ing._UPDATE_HANDLERS)
		self.assertIn("callback_query", ing._UPDATE_HANDLERS)
		saved = dict(ing._UPDATE_HANDLERS)
		try:
			ing._UPDATE_HANDLERS.pop("message")
			ing.register_update_handler("message", lambda g, a, p, r: {"prev": True})
			hooks._chain("message", lambda g, a, p, r: None)
			self.assertEqual(ing._UPDATE_HANDLERS["message"](None, None, None, None), {"prev": True})
		finally:
			ing._UPDATE_HANDLERS.clear()
			ing._UPDATE_HANDLERS.update(saved)


class TestRunsAsBoundUser(Base):
	def test_find_runs_as_bound_user_with_permission_checked_list(self):
		import frappe

		calls = []

		def get_list(dt, **kw):
			calls.append((dt, self.user[0]))
			return [{"name": "CUST-1", "customer_name": "Acme"}]

		meta = SimpleNamespace(title_field="customer_name", has_field=lambda f: True)
		with (
			patch.object(ta, "_resolve_doctype", lambda text: ("Customer", "acme")),
			patch.object(ta, "_check_doctype", lambda dt: dt),
			patch.object(frappe, "get_meta", lambda dt: meta),
			patch.object(frappe, "get_list", get_list),
			patch.object(frappe, "get_all", side_effect=AssertionError("get_all bypasses permissions")),
		):
			self.handle_msg(_msg("/find Customer acme", command="find"))
		self.assertEqual(calls, [("Customer", BOUND)])
		self.assertEqual(self.user[0], "Guest")  # restored
		self.assertIn("CUST-1", self.sent_texts()[-1])

	def test_permission_error_is_reported_not_bypassed(self):
		import frappe

		def get_list(dt, **kw):
			raise frappe.PermissionError("no read on Salary Slip")

		meta = SimpleNamespace(title_field=None, has_field=lambda f: False)
		with (
			patch.object(ta, "_resolve_doctype", lambda text: ("Salary Slip", "")),
			patch.object(ta, "_check_doctype", lambda dt: dt),
			patch.object(frappe, "get_meta", lambda dt: meta),
			patch.object(frappe, "get_list", get_list),
		):
			self.handle_msg(_msg("/find Salary Slip", command="find"))
		self.assertEqual(self.sent_texts()[-1], "You do not have permission for that.")
		self.assertEqual(self.user[0], "Guest")

	def test_run_as_refuses_administrator_and_guest(self):
		for user in ("Administrator", "Guest", ""):
			with self.assertRaises(ta.AdminError):
				with ta.run_as(user):
					pass
		self.assertEqual(self.users_seen, [])

	def test_run_as_restores_on_error(self):
		with self.assertRaises(RuntimeError):
			with ta.run_as(BOUND):
				raise RuntimeError("boom")
		self.assertEqual(self.users_seen, [BOUND, "Guest"])

	def test_denied_doctypes(self):
		for dt in ("Telegram Admin Binding", "Gateway", "User"):
			with self.assertRaises(ta.AdminError):
				ta._check_doctype(dt)


class TestConfirmFlow(Base):
	ACTION = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}

	def _propose_button(self):
		ctx = ta.Ctx(
			binding=dict(BINDING), tg_user=TG, chat_id=CHAT, gateway=GW, cache=self.cache, now=self.now
		)
		ta._send(
			self.adapter,
			ctx,
			ta.Reply("LA-1", buttons=ta._transition_buttons(ctx, "Leave Application", "LA-1", ["Approve"])),
		)
		return self.buttons()[0]["callback_data"]

	def _confirm_buttons(self):
		res = self.handle_cb(self._propose_button())
		self.assertEqual(res["note"], "proposed")
		self.assertIn("Apply 'Approve' to Leave Application LA-1", self.sent_texts()[-1])
		confirm, cancel = self.buttons()
		self.assertEqual((confirm["text"], cancel["text"]), ("Confirm", "Cancel"))
		return confirm["callback_data"], cancel["callback_data"]

	def _patch_workflow(self, applied, error=None):
		import frappe
		import frappe.model.workflow as wf

		doc = MagicMock()
		doc.get.side_effect = lambda k, d=None: "Approved" if k == "workflow_state" else None

		def apply_workflow(d, action):
			applied.append((action, self.user[0]))
			if error:
				raise error
			return doc

		return [
			patch.object(frappe, "get_doc", lambda dt, dn: doc),
			patch.object(frappe, "db", MagicMock()),
			patch.object(wf, "apply_workflow", apply_workflow),
		]

	def test_confirm_executes_as_bound_user_and_audits(self):
		confirm, _cancel = self._confirm_buttons()
		applied = []
		ps = self._patch_workflow(applied)
		for p in ps:
			p.start()
		try:
			res = self.handle_cb(confirm)
		finally:
			for p in ps:
				p.stop()
		self.assertEqual(res["note"], "confirmed")
		self.assertEqual(applied, [("Approve", BOUND)])
		self.assertEqual(self.user[0], "Guest")
		self.assertEqual([a["result"] for a in self.audit], ["ok"])
		self.assertEqual(self.audit[0]["action"], self.ACTION)
		self.assertTrue(self.audit[0]["nonce"])
		edited = self.adapter.sender.edit_message_text.call_args
		self.assertIn("now Approved", edited.args[2])
		self.assertEqual(edited.kwargs["markup"], {"inline_keyboard": []})

	def test_replayed_confirm_rejected(self):
		confirm, _cancel = self._confirm_buttons()
		applied = []
		ps = self._patch_workflow(applied)
		for p in ps:
			p.start()
		try:
			self.handle_cb(confirm)
			res = self.handle_cb(confirm)
		finally:
			for p in ps:
				p.stop()
		self.assertEqual(res["note"], "nonce_rejected")
		self.assertEqual(len(applied), 1)
		self.assertEqual(len(self.audit), 1)

	def test_expired_confirm_rejected(self):
		confirm, _cancel = self._confirm_buttons()
		self.now += ta.NONCE_TTL + 1
		self.assertEqual(self.handle_cb(confirm)["note"], "nonce_rejected")
		self.assertEqual(self.audit, [])

	def test_cross_user_confirm_rejected(self):
		confirm, _cancel = self._confirm_buttons()
		self.bindings[("888", GW)] = {**BINDING, "name": "bind-2", "telegram_user_id": "888"}
		self.assertEqual(self.handle_cb(confirm, sender="888")["note"], "nonce_rejected")
		self.assertEqual(self.audit, [])

	def test_cancel_burns_nonce_without_executing(self):
		confirm, cancel = self._confirm_buttons()
		self.assertEqual(self.handle_cb(cancel)["note"], "cancelled")
		self.assertEqual(self.audit, [])

	def test_forged_callback(self):
		self._confirm_buttons()
		res = self.handle_cb("adm:c:AAAAAAAAAAAAAAAA|forgedsig123")
		self.assertEqual(res["note"], "forged_callback")
		other_chat = self.adapter.sign_callback_data("adm:c:AAAAAAAAAAAAAAAA", "-100")
		self.assertEqual(self.handle_cb(other_chat)["note"], "forged_callback")

	def test_foreign_callback_falls_through(self):
		self.assertIsNone(self.handle_cb(self.adapter.sign_callback_data("b:--:yes", CHAT)))

	def test_no_binding_callback_rejected(self):
		data = self._propose_button()
		self.bindings.clear()
		self.assertEqual(self.handle_cb(data)["note"], "no_binding")

	def test_viewer_gets_no_action_buttons_and_cannot_execute(self):
		ctx = ta.Ctx(binding={**BINDING, "role_scope": "Viewer"}, tg_user=TG, chat_id=CHAT, gateway=GW)
		self.assertEqual(ta._transition_buttons(ctx, "Leave Application", "LA-1", ["Approve"]), [])
		with self.assertRaises(ta.AdminError):
			ta.execute(ctx, self.ACTION, "n")

	def test_failed_execution_is_audited(self):
		import frappe

		confirm, _cancel = self._confirm_buttons()
		applied = []
		ps = self._patch_workflow(applied, error=frappe.PermissionError("Not allowed"))
		for p in ps:
			p.start()
		try:
			self.handle_cb(confirm)
		finally:
			for p in ps:
				p.stop()
		self.assertEqual([a["result"] for a in self.audit], ["error"])
		self.assertIn("Failed", self.adapter.sender.edit_message_text.call_args.args[2])


class TestMiniAppAuth(Base):
	def _init(self, user_id=int(TG), age=10):
		return miniapp.build_init_data_for_test(
			TOKEN, user={"id": user_id, "first_name": "Ops"}, auth_date=int(NOW) - age
		)

	def _auth(self, init_data):
		return ta.miniapp_auth(init_data, GW, bot_token=TOKEN, cache=self.cache, now=NOW)

	def test_token_only_with_binding(self):
		out = self._auth(self._init())
		self.assertEqual(out["role_scope"], "Operator")
		self.assertNotIn("frappe_user", out)
		session = ta.resolve_session_token(
			out["token"], cache=self.cache, now=NOW, binding_lookup=ta.get_binding
		)
		self.assertEqual(session["frappe_user"], BOUND)
		with self.assertRaises(ta.AdminError):
			self._auth(self._init(user_id=999))

	def test_bad_or_stale_init_data(self):
		with self.assertRaises(ta.AdminError):
			self._auth(self._init() + "x")
		with self.assertRaises(ta.AdminError):
			self._auth(self._init(age=ta.MINIAPP_MAX_AGE + 5))

	def test_session_expires_and_dies_with_binding(self):
		out = self._auth(self._init())
		self.assertIsNone(ta.resolve_session_token(out["token"], cache=self.cache, now=NOW + ta.SESSION_TTL))
		self.bindings.clear()
		self.assertIsNone(ta.resolve_session_token(out["token"], cache=self.cache, now=NOW))


class TestPureHelpers(unittest.TestCase):
	def test_redact(self):
		out = ta.redact({"api_key": "k", "nested": {"password": "p", "ok": "v"}, "list": [{"token": "t"}]})
		self.assertEqual(
			out, {"api_key": "***", "nested": {"password": "***", "ok": "v"}, "list": [{"token": "***"}]}
		)

	def test_compose_digest(self):
		text = ta.compose_digest(
			{
				"approvals": [{"reference_doctype": "PO", "reference_name": f"PO-{i}"} for i in range(7)],
				"actions_24h": 3,
			}
		)
		self.assertIn("Pending approvals: 7", text)
		self.assertIn("and 2 more", text)
		self.assertIn("last 24h: 3", text)

	def test_rate_window(self):
		c = ta.MemCache()
		self.assertTrue(ta.check_rate("k", 1, 60, cache=c, now=NOW))
		self.assertFalse(ta.check_rate("k", 1, 60, cache=c, now=NOW))
		self.assertTrue(ta.check_rate("k", 1, 60, cache=c, now=NOW + 60))


if __name__ == "__main__":
	unittest.main()


class FakeRedis:
	"""Minimal atomic-counter redis surface (make_key / incrby / expire)."""

	def __init__(self):
		self.counts, self.ttls = {}, {}

	def make_key(self, key):
		return f"site|{key}"

	def incrby(self, key, n):
		self.counts[key] = self.counts.get(key, 0) + n
		return self.counts[key]

	def expire(self, key, ttl):
		self.ttls[key] = ttl


class TestAtomicRate(unittest.TestCase):
	def test_uses_incr_and_expire_once(self):
		r = FakeRedis()
		res = [ta.check_rate("u:1", 3, 60, cache=r, now=120.0) for _ in range(5)]
		self.assertEqual(res, [True, True, True, False, False])
		(key,) = r.counts
		self.assertTrue(key.startswith("site|huf_tg_adm_rl:u:1:"))
		self.assertEqual(r.ttls, {key: 60})

	def test_falls_back_when_redis_errors(self):
		r = FakeRedis()
		r.incrby = MagicMock(side_effect=ConnectionError("down"))
		res = [ta.check_rate("u:fb", 2, 60, cache=r, now=120.0) for _ in range(3)]
		self.assertEqual(res, [True, True, False])


class TestRunAsRestore(Base):
	def test_restores_previous_user_not_guest(self):
		self.user[0] = "someone@x.com"
		with self.assertRaises(ValueError):
			with ta.run_as(BOUND):
				raise ValueError("x")
		self.assertEqual(self.user[0], "someone@x.com")

	def test_restore_failure_logged_and_raised_clearly(self):
		calls = []

		def set_user(u):
			calls.append(u)
			if len(calls) > 1:
				raise RuntimeError("redis gone")
			self.user[0] = u

		with (
			patch.object(ta, "_set_user", set_user),
			patch.object(ta, "_log_restore_failure") as logged,
			self.assertRaises(ta.AdminError) as cm,
		):
			with ta.run_as(BOUND):
				pass
		self.assertIn("restore", str(cm.exception).lower())
		logged.assert_called_once()

	def test_restore_failure_masks_nothing_when_body_raised(self):
		def set_user(u):
			if u == "Guest":
				raise RuntimeError("redis gone")
			self.user[0] = u

		with (
			patch.object(ta, "_set_user", set_user),
			patch.object(ta, "_log_restore_failure"),
			self.assertRaises(ta.AdminError) as cm,
		):
			with ta.run_as(BOUND):
				raise ValueError("body")
		self.assertIsInstance(cm.exception.__cause__, RuntimeError)


class TestLiveAdminRecheck(unittest.TestCase):
	def setUp(self):
		import frappe

		self.cache = ta.MemCache(clock=lambda: self.now)
		self.now = NOW
		self.row = {**BINDING, "role_scope": "Admin"}
		self.admin = [True]
		self.enabled = [True]
		self.audits = []
		db = MagicMock()
		db.get_value = lambda *a, **k: _Row(self.row)
		for p in (
			patch.object(frappe, "db", db, create=True),
			patch("huf.permissions.is_gateway_admin", lambda u=None: self.admin[0]),
			patch.object(ta, "_user_enabled", lambda u: self.enabled[0]),
			patch.object(ta, "write_audit", lambda b, a, r, **kw: self.audits.append((b, a, r))),
		):
			p.start()
			self.addCleanup(p.stop)

	def get(self):
		return ta.get_binding(TG, GW, cache=self.cache)

	def test_still_admin_stays_admin(self):
		self.assertEqual(self.get()["role_scope"], "Admin")
		self.assertEqual(self.audits, [])

	def test_demoted_to_operator_audited_once_and_cached(self):
		self.admin[0] = False
		for _ in range(3):
			self.assertEqual(self.get()["role_scope"], "Operator")
		self.assertEqual(len(self.audits), 1)
		self.assertEqual(self.audits[0][2], "scope_downgraded")

	def test_recheck_after_ttl(self):
		self.assertEqual(self.get()["role_scope"], "Admin")
		self.admin[0] = False
		self.assertEqual(self.get()["role_scope"], "Admin")  # cached <= 60s
		self.now += 61
		self.assertEqual(self.get()["role_scope"], "Operator")

	def test_disabled_user_is_inactive(self):
		self.enabled[0] = False
		self.assertIsNone(self.get())
		self.assertIsNone(self.get())
		self.assertEqual(len(self.audits), 1)

	def test_operator_binding_skips_checks(self):
		self.row["role_scope"] = "Operator"
		self.admin[0] = False
		self.assertEqual(self.get()["role_scope"], "Operator")
		self.assertEqual(self.audits, [])


class _Row(dict):
	def __getattr__(self, k):
		return self[k]


class TestPrivateOnly(Base):
	def _no_lookup(self):
		return patch.object(ta, "get_binding", side_effect=AssertionError("binding looked up"))

	def test_group_channel_business_refused_before_binding_lookup(self):
		variants = [
			_msg("/help", command="help", chat_type="group", chat="-100"),
			_msg("/help", command="help", chat_type="supergroup", chat="-100"),
			_msg("/help", command="help", chat_type="channel", chat="-100"),
			_msg("/start BIND-ABC", command="start", start_payload="BIND-ABC", chat_type="group", chat="-1"),
		]
		base = _msg("/help", command="help")
		post = dataclasses.replace(base, kind="channel_post")
		biz = dataclasses.replace(base, kind="business_message")
		biz2 = dataclasses.replace(base, business_connection_id="bc1")
		chan = dataclasses.replace(base, is_channel=True)
		with self._no_lookup():
			for v in variants + [post, biz, biz2, chan]:
				self.assertIsNone(self.handle_msg(v))
		self.adapter.sender.send_text.assert_not_called()

	def test_unbound_private_user_gets_no_reply(self):
		self.bindings.clear()
		self.assertIsNone(self.handle_msg(_msg("/audit", command="audit")))
		self.adapter.sender.send_text.assert_not_called()


class TestAgentActionApproval(Base):
	"""Op ``agent_action``: a destructive agent request executes only from an Admin's own button press."""

	def setUp(self):
		super().setUp()
		self.bindings[(TG, GW)]["role_scope"] = "Admin"
		self.action = {"op": "agent_action", "gateway": GW, "chat": "-100", "action": "ban",
			"args": {"user_id": 5, "chat_id": "-100"}, "fp": "fp1"}
		self.ran = []
		from huf.ai.tools import telegram_admin_tools as tools

		patch.object(tools, "execute_approved", side_effect=lambda a: self.ran.append(a) or "Done: ban").start()
		self.addCleanup(patch.stopall)

	def press(self, verb, **kw):
		ta.agent_action_mark_pending("fp1", cache=self.cache)
		nonce = ta.issue_nonce(TG, CHAT, self.action, cache=self.cache, now=self.now, ttl=600)
		data = self.adapter.sign_callback_data(ta.callback_payload(verb, nonce), CHAT)
		return self.handle_cb(data, **kw)

	def test_describe(self):
		self.assertIn("ban", ta.describe(self.action))

	def test_approve_executes_and_audits(self):
		self.press("c")
		self.assertEqual(len(self.ran), 1)
		self.assertEqual(self.audit[-1]["result"], "ok")
		self.assertEqual(self.audit[-1]["action"]["op"], "agent_action")

	def test_reject_does_not_execute_and_blocks_later_approve(self):
		self.press("x")
		self.assertEqual(self.ran, [])
		self.assertEqual(self.audit[-1]["result"], "rejected")
		self.assertFalse(ta.agent_action_pending("fp1", cache=self.cache))
		nonce = ta.issue_nonce(TG, CHAT, self.action, cache=self.cache, now=self.now, ttl=600)
		self.handle_cb(self.adapter.sign_callback_data(ta.callback_payload("c", nonce), CHAT))
		self.assertEqual(self.ran, [])

	def test_operator_scope_cannot_approve(self):
		self.bindings[(TG, GW)]["role_scope"] = "Operator"
		self.press("c")
		self.assertEqual(self.ran, [])

	def test_other_gateway_action_refused(self):
		self.action["gateway"] = "other-gw"
		self.press("c")
		self.assertEqual(self.ran, [])

	def test_foreign_user_cannot_use_nonce(self):
		nonce = ta.issue_nonce(TG, CHAT, self.action, cache=self.cache, now=self.now, ttl=600)
		ta.agent_action_mark_pending("fp1", cache=self.cache)
		self.bindings[("888", GW)] = {**BINDING, "telegram_user_id": "888", "role_scope": "Admin", "chat_id": "888"}
		self.handle_cb(self.adapter.sign_callback_data(ta.callback_payload("c", nonce), "888"), sender="888", chat="888")
		self.assertEqual(self.ran, [])

	def test_nonce_single_use_and_ttl_10_minutes(self):
		nonce = ta.issue_nonce(TG, CHAT, self.action, cache=self.cache, now=self.now, ttl=600)
		with self.assertRaises(ta.AdminError):
			ta.consume_nonce(nonce, TG, CHAT, cache=self.cache, now=self.now + 601)
		nonce = ta.issue_nonce(TG, CHAT, self.action, cache=self.cache, now=self.now, ttl=600)
		ta.consume_nonce(nonce, TG, CHAT, cache=self.cache, now=self.now + 599)
