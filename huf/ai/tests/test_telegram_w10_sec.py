"""W10-SEC regression tests: reply-cache scoping, group admission, POST-only mutators, guard fixes."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import telegram_admin as ta
from huf.ai import telegram_guard as g
from huf.ai import telegram_management_commands as mc
from huf.ai import telegram_management_settings as ms
from huf.ai.gateway_adapters import telegram_blocks as blocks
from huf.ai.gateway_adapters import telegram_buttons as tb
from huf.ai.gateway_adapters import telegram_groups as groups
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_media_reply as mr
from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient
from huf.ai.gateway_adapters.telegram_inbound import parse_update
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi, FakeResponse
from huf.ai.tests.test_telegram_guard import CTX, Env, gw, init_data

ITEM = [{"kind": "photo", "url": "https://example.com/a.png"}]


class Cache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


class TestM1ReplyCacheScope(unittest.TestCase):
	def test_media_items_do_not_cross_chats(self):
		cache = Cache()
		a = blocks.scope_key("gw", "chat-A", "EV-A")
		b = blocks.scope_key("gw", "chat-B", "EV-B")
		mr.remember("same text", ITEM, cache=cache, scope=a)
		self.assertEqual(mr.take_items(["same text"], cache=cache, scope=b), [])
		self.assertEqual(mr.take_items(["same text"], cache=cache, scope=a), ITEM)
		self.assertEqual(mr.take_items(["same text"], cache=cache, scope=a), [])  # popped once

	def test_button_spec_does_not_cross_chats(self):
		cache = Cache()
		spec = {"rows": [[{"text": "Y", "callback": "y"}]]}
		a, b = blocks.scope_key("gw", "A", "EV1"), blocks.scope_key("gw", "B", "EV2")
		tb.remember_spec("pick one", spec, cache=cache, scope=a)
		self.assertIsNone(tb.spec_for_text("pick one", cache=cache, scope=b))
		self.assertEqual(tb.spec_for_text("pick one", cache=cache, scope=a), spec)

	def test_markup_for_uses_event_scope(self):
		cache = Cache()
		spec = {"rows": [[{"text": "Y", "callback": "y"}]]}
		ev_a = SimpleNamespace(conversation_id="A", name="EV1")
		ev_b = SimpleNamespace(conversation_id="B", name="EV2")
		gate = SimpleNamespace(name="gw")
		spec = tb.validate(spec)[0]
		tb.remember_spec("pick", spec, cache=cache, scope=blocks.scope_key("gw", "A", "EV1"))
		sign = lambda p: "c:" + p
		self.assertIsNotNone(tb.markup_for(ev_a, gate, "pick", signer=sign, cache=cache))
		self.assertIsNone(tb.markup_for(ev_b, gate, "pick", signer=sign, cache=cache))


def _join_gw(**kw):
	base = dict(name="gw1", provider="Telegram", room_policy="Disabled", pairing_pending_limit=2)
	base.update(kw)
	return SimpleNamespace(get=lambda k, d=None: base.get(k, d), **base)


def _join_update():
	return {
		"update_id": 1,
		"chat_join_request": {
			"chat": {"id": -100, "type": "supergroup", "title": "G"},
			"from": {"id": 7, "first_name": "E"},
			"user_chat_id": 7,
			"date": 1,
		},
	}


class TestM2Admission(unittest.TestCase):
	def test_join_request_ignored_for_unadmitted_room(self):
		gate = _join_gw()
		parsed = SimpleNamespace(raw=_join_update())
		with (
			mock.patch.object(groups, "decide") as decide,
			mock.patch.object(groups, "record_pending_join") as rec,
		):
			res = groups.handle_join_request(gate, SimpleNamespace(client=None), parsed, None)
		self.assertEqual(res["decision"], "ignore")
		decide.assert_not_called()
		rec.assert_not_called()

	def test_pending_join_cap(self):
		gate = _join_gw()
		ctx = {"chat_id": "-100", "user_id": "7", "user_name": "e", "chat_title": "G", "user_chat_id": "7"}
		with (
			mock.patch.object(groups.frappe, "get_all", side_effect=[[], ["a", "b"]]),
			mock.patch.object(groups.frappe, "get_doc") as get_doc,
		):
			self.assertEqual(groups.record_pending_join(gate, ctx), "")
		get_doc.assert_not_called()

	def test_welcome_requires_room_admission(self):
		sent = []
		fake_mod = SimpleNamespace(send_template=lambda *a, **k: sent.append(a) or {})
		member = {"id": 7, "first_name": "E"}
		with (
			mock.patch.dict("sys.modules", {"huf.ai.telegram_templates": fake_mod}),
			mock.patch("huf.ai.telegram_templates", fake_mod, create=True),
		):
			with Env():
				closed = gw(telegram_welcome_template="Hi", room_policy="Disabled")
				self.assertFalse(g._welcome_one(closed, "-100", "G", member, 100, 0))
				opened = gw(telegram_welcome_template="Hi", room_policy="Open")
				self.assertTrue(g._welcome_one(opened, "-100", "G", member, 100, 0))
		self.assertEqual(len(sent), 1)

	def test_welcome_per_chat_cap(self):
		sent = []
		fake_mod = SimpleNamespace(send_template=lambda *a, **k: sent.append(a) or {})
		with (
			mock.patch.dict("sys.modules", {"huf.ai.telegram_templates": fake_mod}),
			mock.patch("huf.ai.telegram_templates", fake_mod, create=True),
		):
			with Env():
				gate = gw(telegram_welcome_template="Hi", room_policy="Open")
				for uid in range(1, g.WELCOME_CHAT_CAP + 10):
					g._welcome_one(gate, "-100", "G", {"id": uid, "first_name": "E"}, 100, 0)
		self.assertEqual(len(sent), g.WELCOME_CHAT_CAP)

	def test_agent_join_run_cap(self):
		with Env(), mock.patch("frappe.enqueue") as enq:
			gate = gw()
			for _ in range(g.AGENT_JOIN_CAP + 5):
				g._schedule_agent_decision(gate, dict(CTX))
		self.assertEqual(enq.call_count, g.AGENT_JOIN_CAP)


class TestM3PostOnly(unittest.TestCase):
	def test_mutators_are_post_only(self):
		for fn in (
			mc.set_bot_profile,
			mc.set_commands,
			mc.delete_commands,
			mc.set_menu_button,
			mc.set_webhook_now,
			mc.delete_webhook_now,
			mc.apply_recommended_setup,
			ms.update_telegram_settings,
		):
			methods = frappe.allowed_http_methods_for_whitelisted_func.get(fn)
			self.assertEqual(methods, ["POST"], fn.__name__)


class TestM4SpentQuery(unittest.TestCase):
	def test_captcha_approve_uses_plain_method_not_spent_query(self):
		with Env() as env:
			nonce = g.issue_challenge(
				"gw1",
				{**CTX, "query_id": "Q1", "user_id": "42"},
				question={"kind": "math", "prompt": "1+1", "options": [], "answer": "2"},
			)
			res = g.submit_answer("gw1", nonce, init_data(42), "2")
		self.assertTrue(res["ok"])
		self.assertEqual(len(env.fake.of("approveChatJoinRequest")), 1)
		self.assertEqual(env.fake.of("answerChatJoinRequestQuery"), [])

	def test_query_failure_falls_back_to_plain_decision(self):
		with Env() as env:
			env.fake.queue("answerChatJoinRequestQuery", env.fake.error("Bad Request: query expired", 400))
			err = g.apply_decision(env.gateway, {**CTX, "query_id": "Q1"}, "approve", "test")
		self.assertEqual(err, "")
		self.assertEqual(len(env.fake.of("approveChatJoinRequest")), 1)


class TestS1AgentNeverApproves(unittest.TestCase):
	def test_agent_approve_is_queued(self):
		with Env() as env:
			out = g.resolve_agent_join("gw1", dict(CTX), runner=lambda *a: '{"decision":"approve"}')
		self.assertEqual(out, "queue")
		self.assertEqual(env.fake.of("approveChatJoinRequest"), [])


class TestS4AddressingFailsClosed(unittest.TestCase):
	def test_exception_means_not_addressed(self):
		parsed = parse_update(
			{
				"update_id": 1,
				"message": {
					"message_id": 1,
					"date": 1,
					"chat": {"id": -100, "type": "supergroup", "title": "G"},
					"from": {"id": 4, "is_bot": False, "first_name": "A"},
					"text": "@x hi",
					"entities": [{"type": "mention", "offset": 0, "length": 2}],
				},
			}
		)
		gate = SimpleNamespace(name="gw1")
		with mock.patch(
			"huf.ai.gateway_adapters.telegram_modes_hooks._bot_username", side_effect=RuntimeError("x")
		):
			out = ing._with_addressing(gate, SimpleNamespace(_token="1:x"), parsed)
		self.assertFalse(out.mentioned)


class TestS5(unittest.TestCase):
	def test_download_file_checks_http_status(self):
		api = FakeBotApi()
		client = TelegramBotClient(
			TOKEN,
			http_post=api.http_post,
			http_get=lambda url, timeout=None: FakeResponse(content=b"<html>nope</html>", status_code=404),
		)
		with self.assertRaises(TelegramApiError):
			client.download_file("FID")

	def test_deny_doctypes(self):
		for dt in ("Gateway Access Entry", "Gateway Event", "Email Account"):
			self.assertIn(dt, ta.DENY_DOCTYPES)

	def test_guard_unknown_ip_uses_per_user_bucket(self):
		keys = []
		with (
			Env() as env,
			mock.patch.object(g, "_client_ip", lambda: ""),
			mock.patch.object(g, "_rate_ok", lambda k: keys.append(k) or True),
		):
			nonce = g.issue_challenge(
				"gw1",
				{**CTX, "user_id": "42"},
				question={"kind": "math", "prompt": "q", "options": [], "answer": "2"},
			)
			g.get_challenge("gw1", nonce, init_data(42))
		self.assertEqual(keys, ["gc:nouip:42"])
		self.assertIsNotNone(env)


if __name__ == "__main__":
	unittest.main()
