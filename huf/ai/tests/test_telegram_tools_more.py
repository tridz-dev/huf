# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-X Telegram agent-tool actions over the in-memory fake Bot API (no network, no live bot)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import telegram_senders_more as more
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi
from huf.ai.tools import telegram as tool

FILE_ID = "AgACAgIAAxkBAAIBQ2abcdefghijklmnopqrstuvwxyz0123"


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, key):
		return self.d.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def delete_value(self, key):
		self.d.pop(key, None)


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.cache = FakeCache()

		def fake_make_client(token, *, timeout=30):
			return TelegramBotClient(
				token, http_post=self.api.http_post, http_get=self.api.http_get, timeout=timeout, sleep=lambda s: None
			)

		self.addCleanup(patch.stopall)
		patch.object(tool, "update_last_error").start()
		patch.object(tool, "_make_client", side_effect=fake_make_client).start()
		patch.object(tool, "_get_token", return_value=TOKEN).start()
		patch.object(tool.scope, "run_gateway", return_value="").start()
		patch.object(tool.scope, "effective_run_id", return_value="").start()
		patch.object(tool.scope, "current_chat", return_value="").start()
		patch.object(tool, "_idem_cache", return_value=self.cache).start()

	def run_action(self, **kwargs):
		return json.loads(tool.handle_action(**kwargs))

	def payload(self, method):
		return self.api.last(method)["payload"]


class TestNewSends(Base):
	def test_video_note(self):
		r = self.run_action(action="send_video_note", chat_id="9", video_note=FILE_ID, length=240, duration=5)
		self.assertTrue(r["success"], r)
		p = self.payload("sendVideoNote")
		self.assertEqual((p["video_note"], p["length"], p["duration"]), (FILE_ID, 240, 5))

	def test_venue_with_common_options(self):
		r = self.run_action(
			action="send_venue", chat_id="9", latitude=1.5, longitude=2.5, title="Cafe", address="Main St",
			message_thread_id=4, disable_notification=True, protect_content=True, message_effect_id="eff1",
			reply_to_message_id=7,
		)
		self.assertTrue(r["success"], r)
		p = self.payload("sendVenue")
		self.assertEqual((p["latitude"], p["title"], p["address"]), (1.5, "Cafe", "Main St"))
		self.assertEqual(p["message_thread_id"], 4)
		self.assertTrue(p["disable_notification"] and p["protect_content"])
		self.assertEqual(p["message_effect_id"], "eff1")
		self.assertEqual(p["reply_parameters"]["message_id"], 7)

	def test_venue_validation(self):
		self.assertIn("required", self.run_action(action="send_venue", chat_id="9", latitude=1, longitude=2)["error"])
		self.assertIn("-90", self.run_action(
			action="send_venue", chat_id="9", latitude=99, longitude=2, title="t", address="a")["error"])
		self.assertEqual(self.api.calls, [])

	def test_dice(self):
		self.assertTrue(self.run_action(action="send_dice", chat_id="9", emoji="\U0001F3AF")["success"])
		self.assertEqual(self.payload("sendDice")["emoji"], "\U0001F3AF")
		self.assertIn("emoji", self.run_action(action="send_dice", chat_id="9", emoji="x")["error"])

	def test_message_effect_and_protect_on_send_message_and_media(self):
		self.run_action(action="send_message", chat_id="9", text="hi", message_effect_id="e", protect_content=True)
		p = self.payload("sendMessage")
		self.assertEqual(p["message_effect_id"], "e")
		self.assertTrue(p["protect_content"])
		self.run_action(action="send_photo", chat_id="9", photo=FILE_ID, message_effect_id="e", has_spoiler=True)
		p = self.payload("sendPhoto")
		self.assertEqual(p["message_effect_id"], "e")
		self.assertTrue(p["has_spoiler"])


class TestPoll(Base):
	def test_regular_poll(self):
		r = self.run_action(
			action="send_poll", chat_id="9", question="Q?", options=["a", "b", "c"], is_anonymous=False, open_period=30
		)
		self.assertTrue(r["success"], r)
		p = self.payload("sendPoll")
		self.assertEqual(p["options"], [{"text": "a"}, {"text": "b"}, {"text": "c"}])
		self.assertEqual((p["type"], p["is_anonymous"], p["open_period"]), ("regular", False, 30))

	def test_quiz_maps_correct_option_to_ids(self):
		r = self.run_action(
			action="send_poll", chat_id="9", question="Q?", options='["a","b"]', poll_type="quiz",
			correct_option_id=1, explanation="because",
		)
		self.assertTrue(r["success"], r)
		p = self.payload("sendPoll")
		self.assertEqual((p["type"], p["correct_option_ids"], p["explanation"]), ("quiz", [1], "because"))

	def test_validation(self):
		base = {"action": "send_poll", "chat_id": "9", "question": "Q"}
		cases = [
			({"options": ["only"]}, "options"),
			({"options": [str(i) for i in range(13)]}, "options"),
			({"options": ["a", "a"]}, "unique"),
			({"options": ["a", "b"], "poll_type": "quiz"}, "correct_option_id"),
			({"options": ["a", "b"], "poll_type": "quiz", "correct_option_id": 5}, "outside"),
			({"options": ["a", "b"], "correct_option_id": 0}, "quiz"),
			({"options": ["a", "b"], "open_period": 2}, "open_period"),
			({"options": ["a", "b"], "question": "x" * 301}, "too long"),
			({"options": ["a", "x" * 101]}, "too long"),
			({"options": ["a", "b"], "poll_type": "weird"}, "type"),
		]
		for extra_args, needle in cases:
			r = self.run_action(**{**base, **extra_args})
			self.assertFalse(r["success"], extra_args)
			self.assertIn(needle, r["error"], extra_args)
		self.assertEqual(self.api.calls, [])

	def test_stop_poll(self):
		self.assertTrue(self.run_action(action="stop_poll", chat_id="9", message_id=12)["success"])
		self.assertEqual(self.payload("stopPoll")["message_id"], 12)
		self.assertIn("message_id", self.run_action(action="stop_poll", chat_id="9")["error"])


class TestChecklist(Base):
	def test_payload(self):
		r = self.run_action(
			action="send_checklist", chat_id="9", business_connection_id="bc1", title="T", tasks=["one", "two"],
			others_can_mark_tasks_as_done=True,
		)
		self.assertTrue(r["success"], r)
		p = self.payload("sendChecklist")
		self.assertEqual(p["business_connection_id"], "bc1")
		self.assertEqual(p["checklist"]["tasks"], [{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
		self.assertTrue(p["checklist"]["others_can_mark_tasks_as_done"])

	def test_requires_connection_and_tasks(self):
		self.assertIn("business_connection_id", self.run_action(
			action="send_checklist", chat_id="9", title="T", tasks=["a"])["error"])
		self.assertIn("tasks", self.run_action(
			action="send_checklist", chat_id="9", business_connection_id="b", title="T", tasks=[])["error"])


class TestTemplates(Base):
	def setUp(self):
		super().setUp()
		self.tpl = MagicMock()
		patch.object(tool, "_templates", return_value=self.tpl).start()

	def test_list_and_preview(self):
		self.tpl.list_templates.return_value = [{"template_name": "welcome"}]
		self.tpl.render_template.return_value = SimpleNamespace(text="Hi Bo", parse_mode="HTML", media=None, missing=[])
		r = self.run_action(action="list_templates", gateway="gw")
		self.assertEqual(r["results"], [{"template_name": "welcome"}])
		self.tpl.list_templates.assert_called_with("gw")
		r = self.run_action(action="preview_template", template_name="welcome", variables='{"name": "Bo"}', gateway="gw")
		self.assertEqual(r["results"]["text"], "Hi Bo")
		self.tpl.render_template.assert_called_with("welcome", {"name": "Bo"}, "gw")

	def test_send_template(self):
		self.tpl.send_template.return_value = {"message_ids": [5]}
		r = self.run_action(
			action="send_template", chat_id="9", template_name="welcome", variables={"name": "Bo"}, gateway="gw",
			message_thread_id=3,
		)
		self.assertTrue(r["success"], r)
		args, kw = self.tpl.send_template.call_args
		self.assertEqual(args[:3], ("gw", "9", "welcome"))
		self.assertEqual(args[3], {"name": "Bo"})
		self.assertEqual(kw["thread_id"], 3)
		self.assertIsNotNone(kw["sender"])

	def test_errors(self):
		self.assertIn("template_name", self.run_action(action="send_template", chat_id="9", gateway="gw")["error"])
		self.assertIn("gateway", self.run_action(action="send_template", chat_id="9", template_name="x")["error"])
		self.assertIn("JSON", self.run_action(
			action="preview_template", template_name="x", variables="{bad")["error"])
		self.tpl.render_template.side_effect = RuntimeError("missing template")
		self.assertIn("missing template", self.run_action(action="preview_template", template_name="x")["error"])


class TestForumTopics(Base):
	def admin(self, **rights):
		self.api.queue("getMe", {"ok": True, "result": {"id": 77, "is_bot": True}})
		self.api.queue("getChatMember", {"ok": True, "result": {"status": "administrator", **rights}})

	def test_create_edit_close_reopen_delete(self):
		cases = [
			("create_forum_topic", "createForumTopic", {"name": "Ops", "icon_color": 7322096}, {}),
			("edit_forum_topic", "editForumTopic", {"message_thread_id": 5, "name": "New"}, {}),
			("close_forum_topic", "closeForumTopic", {"message_thread_id": 5}, {}),
			("reopen_forum_topic", "reopenForumTopic", {"message_thread_id": 5}, {}),
			("delete_forum_topic", "deleteForumTopic", {"message_thread_id": 5}, {"can_delete_messages": True}),
		]
		for action, method, args, rights in cases:
			self.admin(can_manage_topics=True, **rights)
			r = self.run_action(action=action, chat_id="-100", **args)
			self.assertTrue(r["success"], (action, r))
			self.assertEqual(self.payload(method)["chat_id"], "-100")
		self.assertEqual(self.payload("createForumTopic")["icon_color"], 7322096)
		self.assertEqual(self.payload("editForumTopic")["message_thread_id"], 5)

	def test_bot_rights_required(self):
		self.admin(can_manage_topics=False)
		r = self.run_action(action="close_forum_topic", chat_id="-100", message_thread_id=5)
		self.assertIn("manage topics", r["error"])
		self.assertEqual(self.api.of("closeForumTopic"), [])
		self.admin(can_manage_topics=True)  # delete additionally needs can_delete_messages
		r = self.run_action(action="delete_forum_topic", chat_id="-100", message_thread_id=5)
		self.assertIn("delete messages", r["error"])
		self.api.queue("getMe", {"ok": True, "result": {"id": 77}})
		self.api.queue("getChatMember", {"ok": True, "result": {"status": "member"}})
		r = self.run_action(action="create_forum_topic", chat_id="-100", name="x")
		self.assertIn("not an administrator", r["error"])

	def test_validation(self):
		self.assertIn("message_thread_id", self.run_action(action="close_forum_topic", chat_id="-100")["error"])
		self.admin(can_manage_topics=True)
		self.assertIn("icon_color", self.run_action(action="create_forum_topic", chat_id="-100", name="x", icon_color=1)["error"])


class TestReads(Base):
	def test_chat_member_is_trimmed(self):
		self.api.queue("getChatMember", {"ok": True, "result": {
			"status": "administrator", "user": {"id": 5, "first_name": "A", "language_code": "en"},
			"can_delete_messages": True, "can_manage_topics": False,
		}})
		r = self.run_action(action="get_chat_member", chat_id="-100", user_id=5)
		res = r["results"]
		self.assertEqual(res["status"], "administrator")
		self.assertEqual(res["rights"], ["can_delete_messages"])
		self.assertNotIn("language_code", res["user"])
		self.assertIn("user_id", self.run_action(action="get_chat_member", chat_id="-100")["error"])

	def test_admins_and_count(self):
		self.api.queue("getChatAdministrators", {"ok": True, "result": [{"status": "creator", "user": {"id": 1}}]})
		self.api.queue("getChatMemberCount", {"ok": True, "result": 42})
		self.assertEqual(self.run_action(action="get_chat_administrators", chat_id="-100")["results"][0]["user"]["id"], 1)
		self.assertEqual(self.run_action(action="get_chat_member_count", chat_id="-100")["results"], 42)


class TestGetFile(Base):
	def test_saves_file(self):
		doc = MagicMock(file_url="/private/files/f.jpg")
		with patch.object(tool.frappe, "get_doc", return_value=doc) as get_doc:
			r = self.run_action(action="get_file", file_id=FILE_ID)
		self.assertTrue(r["success"], r)
		self.assertEqual(r["results"]["file_url"], "/private/files/f.jpg")
		spec = get_doc.call_args[0][0]
		self.assertEqual((spec["doctype"], spec["is_private"], spec["content"]), ("File", 1, b"file-bytes"))
		doc.insert.assert_called_once()

	def test_size_cap_and_bad_id(self):
		self.api.queue("getFile", {"ok": True, "result": {"file_path": "x/y.bin", "file_size": 21 * 1024 * 1024}})
		r = self.run_action(action="get_file", file_id=FILE_ID)
		self.assertIn("20 MB", r["error"])
		self.assertEqual(self.api.gets, [])
		self.assertIn("file_id", self.run_action(action="get_file", file_id="x")["error"])


class TestListMessagesAndAccount(Base):
	def test_list_messages_redacts_and_limits(self):
		row = {"name": "E1", "message_text": f"token {TOKEN} " + "x" * 600, "status": "Replied"}
		with patch.object(tool.frappe, "has_permission", return_value=True), \
				patch.object(tool.frappe, "get_list", return_value=[row]) as get_list:
			r = self.run_action(action="list_messages", chat_id="9", gateway="gw", limit=500)
		self.assertTrue(r["success"], r)
		kw = get_list.call_args.kwargs
		self.assertEqual(kw["limit_page_length"], 50)
		self.assertEqual(kw["filters"]["gateway"], "gw")
		text = r["results"]["items"][0]["message_text"]
		self.assertNotIn(TOKEN, text)
		self.assertLessEqual(len(text), 500)
		self.assertNotIn("raw_payload", kw["fields"])

	def test_list_messages_permission(self):
		with patch.object(tool.frappe, "has_permission", return_value=False):
			r = self.run_action(action="list_messages", chat_id="9", gateway="gw")
		self.assertEqual(r["error"], "permission_denied")

	def test_account_info_has_no_secrets(self):
		self.api.queue("getMe", {"ok": True, "result": {"id": 1, "username": "bot", "can_join_groups": True}})
		self.api.queue("getWebhookInfo", {"ok": True, "result": {
			"url": f"https://x/{TOKEN}", "pending_update_count": 3, "last_error_message": f"err {TOKEN}"}})
		r = self.run_action(action="get_account_info")
		self.assertTrue(r["success"], r)
		self.assertEqual(r["results"]["bot"]["username"], "bot")
		self.assertEqual(r["results"]["webhook"]["pending_update_count"], 3)
		self.assertNotIn(TOKEN, json.dumps(r))
		self.assertNotIn("https://x", json.dumps(r))


class TestIdempotency(Base):
	def test_duplicate_returns_first_result(self):
		a = self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k1")
		b = self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k1")
		self.assertEqual(a, b)
		self.assertEqual(len(self.api.of("sendMessage")), 1)
		self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k2")
		self.run_action(action="send_message", chat_id="10", text="hi", idempotency_key="k1")
		self.assertEqual(len(self.api.of("sendMessage")), 3)

	def test_failed_send_can_retry(self):
		self.api.queue("sendMessage", self.api.error("Bad Request: chat not found", 400))
		self.assertFalse(self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k")["success"])
		self.assertTrue(self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k")["success"])

	def test_invalid_key_and_in_flight(self):
		self.assertEqual(
			self.run_action(action="send_message", chat_id="9", text="x", idempotency_key="bad key!")["error"],
			"invalid_idempotency_key",
		)
		key = tool._idempotency_key("send_message", {"chat_id": "9", "idempotency_key": "p"})
		self.cache.set_value(key, {"state": "pending"})
		r = self.run_action(action="send_message", chat_id="9", text="x", idempotency_key="p")
		self.assertEqual(r["error"], "duplicate_in_flight")
		self.assertEqual(self.api.calls, [])

	def test_ignored_for_reads(self):
		self.run_action(action="get_me", idempotency_key="k")
		self.run_action(action="get_me", idempotency_key="k")
		self.assertEqual(len(self.api.of("getMe")), 2)


class TestGatewayScope(Base):
	def setUp(self):
		super().setUp()
		patch.object(tool.scope, "run_gateway", return_value="gw").start()
		patch.object(tool.scope, "effective_run_id", return_value="run1").start()
		patch.object(tool.scope, "current_chat", return_value="9").start()
		patch.object(tool.scope, "settings", return_value={
			"scope": "Current contact", "allowlist": [], "per_run": 2, "per_day": 10}).start()
		patch.object(tool, "_token_for_run", return_value=TOKEN).start()
		patch.object(tool, "_gateway_flag", return_value=False).start()
		self.counts = {}
		patch.object(tool.scope, "_load", side_effect=lambda k: self.counts.setdefault(k, [])).start()
		patch.object(tool.scope, "_save", side_effect=lambda k, v, ttl: self.counts.__setitem__(k, v)).start()

	def test_other_chat_denied_for_every_new_action(self):
		cases = {
			"send_video_note": {"video_note": FILE_ID}, "send_venue": {"latitude": 1, "longitude": 1, "title": "t", "address": "a"},
			"send_dice": {}, "send_poll": {"question": "q", "options": ["a", "b"]}, "stop_poll": {"message_id": 1},
			"send_checklist": {"business_connection_id": "b", "title": "t", "tasks": ["a"]},
			"send_template": {"template_name": "x"}, "create_forum_topic": {"name": "n"},
			"edit_forum_topic": {"message_thread_id": 1, "name": "n"}, "close_forum_topic": {"message_thread_id": 1},
			"reopen_forum_topic": {"message_thread_id": 1}, "delete_forum_topic": {"message_thread_id": 1},
			"get_chat_member": {"user_id": 1}, "get_chat_administrators": {}, "get_chat_member_count": {},
			"list_messages": {},
		}
		for action, args in cases.items():
			r = self.run_action(action=action, chat_id="555", **args)
			self.assertEqual(r["error"], "recipient_not_permitted", action)
		self.assertEqual(self.api.calls, [])

	def test_defaults_to_current_chat_and_counts_caps(self):
		self.assertTrue(self.run_action(action="send_dice")["success"])
		self.assertEqual(self.payload("sendDice")["chat_id"], "9")
		self.assertTrue(self.run_action(action="send_venue", latitude=1, longitude=1, title="t", address="a")["success"])
		r = self.run_action(action="send_poll", question="q", options=["a", "b"])
		self.assertEqual(r["error"], "send_cap_exceeded")

	def test_failed_send_releases_cap(self):
		self.api.queue("sendDice", self.api.error("Bad Request: nope", 400))
		self.assertFalse(self.run_action(action="send_dice")["success"])
		self.assertTrue(self.run_action(action="send_dice")["success"])
		self.assertTrue(self.run_action(action="send_dice")["success"])

	def test_checklist_needs_business_flag(self):
		args = {"business_connection_id": "b", "title": "t", "tasks": ["a"]}
		self.assertEqual(self.run_action(action="send_checklist", **args)["error"], "action_not_permitted")
		with patch.object(tool, "_gateway_flag", return_value=True):
			self.assertTrue(self.run_action(action="send_checklist", **args)["success"])

	def test_reads_do_not_use_send_caps(self):
		self.api.queue("getChatMemberCount", {"ok": True, "result": 3})
		self.assertTrue(self.run_action(action="get_chat_member_count")["success"])
		self.assertEqual(self.counts, {})


class TestSendersMore(unittest.TestCase):
	def test_build_poll_multiple_correct(self):
		poll = more.build_poll("Q", ["a", "b", "c"], poll_type="quiz", correct_option_ids=[2, 0], allows_multiple_answers=True)
		self.assertEqual(poll["correct_option_ids"], [0, 2])
		with self.assertRaises(ValueError):
			more.build_poll("Q", ["a", "b", "c"], poll_type="quiz", correct_option_ids=[2, 0])


class TestFailClosedGatewayRuns(Base):
	"""Inside a gateway run that is not an enabled Telegram gateway, tools refuse (never unscoped)."""

	def setUp(self):
		super().setUp()
		patch.object(tool.scope, "gateway_state", return_value=("invalid", "")).start()

	def test_invalid_gateway_refuses_every_kind_of_action(self):
		for kw in (
			{"action": "send_message", "chat_id": "9", "text": "hi"},
			{"action": "get_me"},
			{"action": "set_webhook", "url": "https://x.example/h"},
			{"action": "delete_webhook"},
			{"action": "get_updates"},
		):
			r = self.run_action(**kw)
			self.assertEqual(r["error"], "action_not_permitted", kw)
		self.assertEqual(self.api.calls, [])

	def test_invalid_gateway_refuses_even_with_idempotency_key(self):
		r = self.run_action(action="send_message", chat_id="9", text="hi", idempotency_key="k")
		self.assertEqual(r["error"], "action_not_permitted")

	def test_non_gateway_run_unchanged(self):
		tool.scope.gateway_state.return_value = ("none", "")
		self.assertTrue(self.run_action(action="send_message", chat_id="9", text="hi")["success"])
		self.assertTrue(self.run_action(action="get_me")["success"])


class TestFailClosedEndToEnd(Base):
	"""Real gateway_state against a fake DB: WhatsApp gateway, disabled mid-run, DB error."""

	def setUp(self):
		super().setUp()
		patch.stopall()
		self.addCleanup(patch.stopall)
		self.api = FakeBotApi()
		patch.object(tool, "update_last_error").start()
		patch.object(tool, "_make_client", side_effect=lambda token, *, timeout=30: TelegramBotClient(
			token, http_post=self.api.http_post, http_get=self.api.http_get, timeout=timeout, sleep=lambda s: None)).start()
		patch.object(tool, "_get_token", return_value=TOKEN).start()
		patch.object(tool, "_idem_cache", return_value=self.cache).start()
		self.row = {"provider": "WhatsApp", "is_enabled": 1}
		self.boom = False

		def get_value(doctype, name, fields=None, as_dict=False):
			if self.boom:
				raise RuntimeError("db down")
			if doctype == "Agent Run":
				return "C"
			if doctype == "Agent Conversation":
				return "gateway:GW"
			return self.row
		patch.object(tool.scope.frappe, "flags", SimpleNamespace(huf_current_agent_run_id="R")).start()
		patch.object(tool.scope.frappe, "db", SimpleNamespace(get_value=get_value)).start()

	def test_whatsapp_gateway_run_refused(self):
		self.assertEqual(self.run_action(action="send_message", chat_id="9", text="hi")["error"], "action_not_permitted")
		self.assertEqual(self.run_action(action="set_webhook", url="https://x.example/h")["error"], "action_not_permitted")
		self.assertEqual(self.api.calls, [])

	def test_disabled_mid_run_refused(self):
		self.row = {"provider": "Telegram", "is_enabled": 0}
		self.assertEqual(self.run_action(action="send_message", chat_id="9", text="hi")["error"], "action_not_permitted")
		self.assertEqual(self.api.calls, [])

	def test_db_error_refused(self):
		self.boom = True
		self.assertEqual(self.run_action(action="delete_webhook")["error"], "action_not_permitted")
		self.assertEqual(self.api.calls, [])


class TestIdempotencyScopedFirst(Base):
	def test_cached_result_not_returned_once_scope_forbids(self):
		patch.object(tool.scope, "run_gateway", return_value="gw").start()
		patch.object(tool.scope, "effective_run_id", return_value="run1").start()
		patch.object(tool.scope, "current_chat", return_value="9").start()
		patch.object(tool.scope, "settings", return_value={
			"scope": "Current contact", "allowlist": [], "per_run": 5, "per_day": 10}).start()
		patch.object(tool, "_token_for_run", return_value=TOKEN).start()
		store = {}
		patch.object(tool.scope, "_load", side_effect=lambda k: store.setdefault(k, [])).start()
		patch.object(tool.scope, "_save", side_effect=lambda k, v, ttl: store.__setitem__(k, v)).start()
		self.assertTrue(self.run_action(action="send_message", text="hi", idempotency_key="k")["success"])
		# the same key now aimed at a forbidden chat must be refused by scope, not by the cache
		r = self.run_action(action="send_message", chat_id="555", text="hi", idempotency_key="k")
		self.assertEqual(r["error"], "recipient_not_permitted")
		# the gateway going invalid means the original (cached) call is refused too
		patch.object(tool.scope, "run_gateway", return_value="").start()
		patch.object(tool.scope, "gateway_state", return_value=("invalid", "")).start()
		r = self.run_action(action="send_message", text="hi", idempotency_key="k")
		self.assertEqual(r["error"], "action_not_permitted")

	def test_key_includes_gateway_and_chat(self):
		patch.object(tool.scope, "run_gateway", return_value="gwA").start()
		a = tool._idempotency_key("send_message", {"chat_id": "9", "idempotency_key": "k"})
		tool.scope.run_gateway.return_value = "gwB"
		b = tool._idempotency_key("send_message", {"chat_id": "9", "idempotency_key": "k"})
		self.assertNotEqual(a, b)
		self.assertIn("gwA", a)


if __name__ == "__main__":
	unittest.main()
