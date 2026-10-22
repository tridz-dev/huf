# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""End-to-end action matrix for the ``telegram`` and ``telegram_admin`` agent tools.

Runs against the in-memory fake Bot API and an in-memory cache: no network, no live bot.
The registry enums are the source of truth. Every advertised action must have a handler, a minimal
argument set and a row in each matrix below, so a new action cannot slip past this suite.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from huf.ai import telegram_send_scope as scope
from huf.ai import telegram_templates as tpl
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi, FakeResponse
from huf.ai.tools import _registry
from huf.ai.tools import telegram as tg
from huf.ai.tools import telegram_admin_tools as adm

BOT = 999
CUR = "-1001"  # chat of the current gateway conversation
OTHER = "-2002"  # allowed only by Allow-list / Approved / Any number
DENIED = "-3003"  # outside every allow-list
SECRET = TOKEN.split(":", 1)[-1]
PHOTO = "https://cdn.test/a.jpg"
TG_BASE = "https://api.telegram.org"
FLAG_FOR_GROUP = adm.FLAGS
ADMIN_RIGHTS = {
	"can_restrict_members": True, "can_promote_members": True, "can_change_info": True,
	"can_pin_messages": True, "can_delete_messages": True, "can_invite_users": True,
}
# scope name -> (chat that must be allowed, chat that must be refused, extra settings)
SCOPE_MODES = {
	"Current contact": (CUR, OTHER, {}),
	"Allow-list": (OTHER, DENIED, {"allowlist": [OTHER]}),
	"Approved contacts": (OTHER, DENIED, {}),
	"Any number": (OTHER, "not a chat", {}),
}

TG_ARGS = {
	"send_message": {"text": "hi"},
	"reply_to_message": {"text": "hi", "reply_to_message_id": 7},
	"send_photo": {"photo": PHOTO},
	"send_document": {"document": "https://cdn.test/a.pdf"},
	"send_voice": {"voice": "https://cdn.test/a.ogg"},
	"send_audio": {"audio": "https://cdn.test/a.mp3"},
	"send_video": {"video": "https://cdn.test/a.mp4"},
	"send_animation": {"animation": "https://cdn.test/a.gif"},
	"send_sticker": {"sticker": "https://cdn.test/a.webp"},
	"send_media_group": {"items": [{"type": "photo", "media": PHOTO}, {"type": "photo", "media": PHOTO}]},
	"send_location": {"latitude": 1.0, "longitude": 2.0},
	"send_contact": {"phone_number": "+100", "first_name": "A"},
	"set_reaction": {"message_id": 3, "emoji": "\U0001F44D"},
	"send_chat_action": {"chat_action": "typing"},
	"edit_message_text": {"message_id": 3, "text": "x"},
	"edit_message_caption": {"message_id": 3, "caption": "x"},
	"edit_message_reply_markup": {"message_id": 3},
	"delete_message": {"message_id": 3},
	"pin_message": {"message_id": 3},
	"unpin_message": {"message_id": 3},
	"forward_message": {"from_chat_id": CUR, "message_id": 3},
	"copy_message": {"from_chat_id": CUR, "message_id": 3},
	"answer_callback_query": {"callback_query_id": "cb", "text": "x"},
	"get_updates": {},
	"get_chat_info": {},
	"get_me": {},
	"set_webhook": {"url": "https://hooks.test/h"},
	"delete_webhook": {},
	"send_video_note": {"video_note": "https://cdn.test/n.mp4"},
	"send_venue": {"latitude": 1.0, "longitude": 2.0, "title": "T", "address": "A"},
	"send_dice": {"emoji": "dice"},
	"send_poll": {"question": "q", "options": ["a", "b"]},
	"stop_poll": {"message_id": 3},
	"send_checklist": {"business_connection_id": "c", "title": "t", "tasks": ["a"]},
	"send_template": {"template_name": "t"},
	"list_templates": {},
	"preview_template": {"template_name": "t"},
	"create_forum_topic": {"name": "n"},
	"edit_forum_topic": {"message_thread_id": 5, "name": "n"},
	"close_forum_topic": {"message_thread_id": 5},
	"reopen_forum_topic": {"message_thread_id": 5},
	"delete_forum_topic": {"message_thread_id": 5},
	"get_file": {"file_id": "A" * 25},
	"get_chat_member": {"user_id": 5},
	"get_chat_administrators": {},
	"get_chat_member_count": {},
	"list_messages": {},
	"get_account_info": {},
}

ADMIN_ARGS = {
	"ban": {"user_id": 5},
	"unban": {"user_id": 5},
	"restrict": {"user_id": 5, "preset": "mute"},
	"unrestrict": {"user_id": 5},
	"promote": {"user_id": 5, "rights": ["can_pin_messages"]},
	"demote": {"user_id": 5},
	"set_chat_title": {"title": "T"},
	"set_chat_description": {"description": "d"},
	"pin": {"message_id": 3},
	"unpin": {"message_id": 3},
	"delete_message": {"message_id": 3},
	"approve_join_request": {"user_id": 5},
	"decline_join_request": {"user_id": 5},
	"create_invite_link": {"name": "x"},
	"revoke_invite_link": {"invite_link": "https://t.me/+abc"},
	"get_admins": {},
	"set_my_commands": {"commands": [{"command": "a", "description": "b"}]},
	"set_my_name": {"name": "n"},
	"set_my_description": {"description": "d"},
	"set_my_short_description": {"short_description": "s"},
	"set_chat_menu_button": {"menu_button": {"type": "default"}},
	"get_business_connection": {"business_connection_id": "c"},
	"send_business_message": {"business_connection_id": "c", "chat_id": 5, "text": "x"},
	"read_business_message": {"business_connection_id": "c", "chat_id": 5, "message_id": 3},
	"delete_business_messages": {"business_connection_id": "c", "message_ids": [1]},
}
# destructive action -> the Bot API method it must call once confirmed
MUTATING = {
	"ban": "banChatMember",
	"restrict": "restrictChatMember",
	"promote": "promoteChatMember",
	"delete_message": "deleteMessage",
	"set_my_commands": "setMyCommands",
	"delete_business_messages": "deleteBusinessMessages",
}


def _enum(tool_name: str) -> list[str]:
	"""Action names advertised by the registry for ``tool_name`` (parsed from the action parameter)."""
	entries = _registry.TELEGRAM_TOOLS + _registry.TELEGRAM_ADMIN_TOOLS
	(tool,) = [t for t in entries if t["tool_name"] == tool_name]
	(param,) = [p for p in tool["parameters"] if p["fieldname"] == "action"]
	return param["description"].split("One of: ", 1)[1].split("|")


def _dispatch_keys() -> set[str]:
	"""Keys of the ``dispatch`` table in ``telegram.handle_action`` (read from source)."""
	src = Path(tg.__file__).read_text(encoding="utf-8")
	block = src.split("dispatch = {", 1)[1].split("handler = dispatch.get", 1)[0]
	return set(re.findall(r'"(\w+)": _handle_', block))


TG_ENUM = _enum("telegram")
ADMIN_ENUM = _enum("telegram_admin")


class MemCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


class Api(FakeBotApi):
	"""Fake Bot API where the bot is an admin with every needed right; ``fail_with`` makes every call fail."""

	def __init__(self):
		super().__init__()
		self.members = {BOT: {"status": "administrator", **ADMIN_RIGHTS}}
		self.fail_with = None  # error body (dict) returned for every call
		self.raise_with = None  # exception raised for every call

	def http_post(self, url, *, json_data=None, data=None, files=None, timeout=None):
		method = url.rsplit("/", 1)[-1]
		if self.fail_with is not None or self.raise_with is not None:
			payload = dict(json_data if json_data is not None else (data or {}))
			self.calls.append({"method": method, "payload": payload, "files": None, "url": url})
			if self.raise_with is not None:
				raise self.raise_with
			return FakeResponse(self.fail_with, status_code=400)
		if method == "getMe":
			self.calls.append({"method": method, "payload": {}, "files": None, "url": url})
			return FakeResponse({"ok": True, "result": {"id": BOT, "is_bot": True, "username": "bot"}})
		if method == "getChatMember":
			payload = dict(json_data or {})
			self.calls.append({"method": method, "payload": payload, "files": None, "url": url})
			member = self.members.get(payload.get("user_id"), {"status": "member"})
			return FakeResponse({"ok": True, "result": member})
		return super().http_post(url, json_data=json_data, data=data, files=files, timeout=timeout)


class Harness(unittest.TestCase):
	"""Patches shared by every test: fake Bot API, in-memory cache, and the gateway state each test flips."""

	def setUp(self):
		self.api = Api()
		self.cache = MemCache()
		self.gw_on = False
		self.run_id = "run1"
		self.conf = {"scope": "Current contact", "allowlist": [], "per_run": 20, "per_day": 200}
		self.approved = {OTHER}
		self.owner = False
		self.cap = 50
		self.flags = {"group": True, "profile": True, "business": True}
		self.addCleanup(patch.stopall)

		def make_client(token, *, timeout=30):
			return TelegramBotClient(
				token,
				http_post=self.api.http_post,
				http_get=self.api.http_get,
				timeout=timeout,
				sleep=lambda s: None,
			)

		for mod in (tg, adm):
			patch.object(mod, "_make_client", side_effect=make_client).start()
		patch.object(tg, "_token_for_run", return_value=TOKEN).start()
		patch.object(adm, "_token", return_value=TOKEN).start()
		patch.object(tg, "update_last_error").start()
		patch.object(tg, "_idem_cache", side_effect=lambda: self.cache).start()
		patch.object(tg, "_gateway_flag", return_value=True).start()
		patch.object(adm, "_cache", side_effect=lambda: self.cache).start()
		patch.object(scope, "_cache", side_effect=lambda: self.cache).start()
		patch.object(adm, "_audit").start()
		patch.object(adm, "_flag", side_effect=lambda gw, group: self.flags[group]).start()
		patch.object(adm, "_cap_limit", side_effect=lambda gw: self.cap).start()
		patch.object(adm, "_is_owner_run", side_effect=lambda gw, chat: self.owner).start()
		patch.object(adm, "_is_paired_admin", side_effect=lambda gw, uid: str(uid) == "777").start()
		patch.object(scope, "run_gateway", side_effect=lambda: "gw1" if self.gw_on else "").start()
		patch.object(scope, "effective_run_id", side_effect=lambda: self.run_id).start()
		patch.object(scope, "current_chat", side_effect=lambda run_id: CUR).start()
		patch.object(scope, "settings", side_effect=lambda gw: dict(self.conf)).start()
		patch.object(scope, "_is_approved", side_effect=lambda gw, chat: chat in self.approved).start()
		patch("huf.ai.http_handler.validate_url", return_value=(True, None)).start()
		patch.object(tg.frappe, "get_doc", return_value=MagicMock(file_url="/private/files/x.jpg")).start()
		patch.object(tg.frappe, "get_list", return_value=[]).start()
		patch.object(tg.frappe, "has_permission", return_value=True).start()
		patch.object(tpl, "list_templates", return_value=[]).start()
		patch.object(tpl, "render_template", return_value={"text": "hi"}).start()
		patch.object(tpl, "send_template", return_value={"message_id": 9}).start()
		patch.object(
			adm.biz, "get_connection",
			return_value={
				"id": "c", "gateway": "gw1", "rights": {"can_delete_sent_messages": True}, "is_enabled": True,
			},
		).start()

	def tg_call(self, action, **kwargs):
		return json.loads(tg.handle_action(action=action, **kwargs))

	def adm_call(self, action, **kwargs):
		return json.loads(adm.handle_action(action=action, **kwargs))

	def configure_scope(self, mode, **extra):
		self.conf = {"scope": mode, "allowlist": [], "per_run": 20, "per_day": 200, **extra}

	def chat_args(self, action, chat):
		args = dict(TG_ARGS[action])
		args["chat_id"] = chat
		if action in ("forward_message", "copy_message"):
			args["from_chat_id"] = chat
		return args

	def sent(self, method):
		return [c for c in self.api.calls if c["method"] == method]


class TestRegistryParity(Harness):
	def test_telegram_enum_matches_dispatch_table(self):
		self.assertEqual(set(TG_ENUM), _dispatch_keys())
		self.assertEqual(len(TG_ENUM), len(set(TG_ENUM)))

	def test_telegram_admin_enum_matches_action_table(self):
		self.assertEqual(set(ADMIN_ENUM), set(adm.ACTIONS))
		self.assertEqual(len(ADMIN_ENUM), len(set(ADMIN_ENUM)))

	def test_every_action_has_a_matrix_row(self):
		self.assertEqual(set(TG_ARGS), set(TG_ENUM))
		self.assertEqual(set(ADMIN_ARGS), set(ADMIN_ENUM))

	def test_destructive_set_is_the_expected_one(self):
		self.assertEqual({a for a, v in adm.ACTIONS.items() if v[2]}, set(MUTATING))

	def test_unknown_actions_are_refused(self):
		self.assertIn("Unknown action", self.tg_call("nuke")["error"])
		self.assertEqual(self.adm_call("nuke")["error"], "unknown_action")


class TestEnvelope(Harness):
	def test_telegram_every_action_returns_standard_envelope(self):
		for action in TG_ENUM:
			with self.subTest(action=action):
				res = self.tg_call(action, chat_id=CUR, **TG_ARGS[action])
				self.assertIsInstance(res.get("success"), bool, res)
				if res["success"]:
					self.assertIn("results", res)
				else:
					self.assertIsInstance(res.get("error"), str)
					self.assertTrue(res["error"])
					self.assertNotIn("Unknown action", res["error"])

	def test_admin_every_action_returns_standard_envelope(self):
		self.gw_on = True
		for action in ADMIN_ENUM:
			with self.subTest(action=action):
				res = self.adm_call(action, **ADMIN_ARGS[action])
				self.assertIsInstance(res.get("success"), bool, res)
				if action in MUTATING:
					self.assertEqual(res.get("error"), "needs_confirmation", res)
					self.assertTrue(res.get("confirmation_token"))
				elif res["success"]:
					self.assertEqual(res["action"], action)
					self.assertIn("result", res)
				else:
					self.assertIsInstance(res.get("error"), str)
					self.assertIsInstance(res.get("message"), str)


class TestGatewayScopeMatrix(Harness):
	def setUp(self):
		super().setUp()
		self.gw_on = True

	def test_telegram_send_and_chat_actions_follow_scope(self):
		for mode, (allowed, denied, extra) in SCOPE_MODES.items():
			self.configure_scope(mode, **extra)
			for action in sorted(tg.CHAT_ACTIONS):
				with self.subTest(scope=mode, action=action, side="allowed"):
					self.api.calls.clear()
					self.cache.d.clear()
					res = self.tg_call(action, **self.chat_args(action, allowed))
					self.assertNotEqual(res.get("error"), "recipient_not_permitted", res)
				with self.subTest(scope=mode, action=action, side="denied"):
					self.api.calls.clear()
					self.cache.d.clear()
					res = self.tg_call(action, **self.chat_args(action, denied))
					self.assertEqual(res.get("error"), "recipient_not_permitted", res)
					self.assertEqual(self.api.calls, [], "a refused recipient must not reach the Bot API")

	def test_telegram_forward_checks_source_chat_too(self):
		self.configure_scope("Allow-list", allowlist=[OTHER])
		for action in ("forward_message", "copy_message"):
			with self.subTest(action=action):
				res = self.tg_call(action, chat_id=OTHER, from_chat_id=DENIED, message_id=3)
				self.assertEqual(res.get("error"), "recipient_not_permitted", res)
				self.assertEqual(self.api.calls, [])

	def test_telegram_webhook_control_blocked_in_gateway(self):
		for action in sorted(tg.GATEWAY_BLOCKED_ACTIONS):
			with self.subTest(action=action):
				res = self.tg_call(action, **TG_ARGS[action])
				self.assertEqual(res.get("error"), "action_not_permitted", res)
		self.assertEqual(self.api.calls, [])

	def test_admin_group_actions_follow_scope(self):
		for mode, (allowed, denied, extra) in SCOPE_MODES.items():
			if mode == "Any number":
				# a malformed chat_id is not refused by the admin tool: it falls back to the current chat
				# the numeric-chat rule for this mode is covered by the telegram tool
				continue
			self.configure_scope(mode, **extra)
			for action in sorted(adm.CHAT_ACTIONS):
				args = dict(ADMIN_ARGS[action])
				with self.subTest(scope=mode, action=action, side="allowed"):
					self.api.calls.clear()
					self.cache.d.clear()
					res = self.adm_call(action, chat_id=allowed, **args)
					self.assertNotIn("recipient", res.get("message", ""), res)
				with self.subTest(scope=mode, action=action, side="denied"):
					self.api.calls.clear()
					self.cache.d.clear()
					res = self.adm_call(action, chat_id=denied, **args)
					self.assertEqual(res.get("error"), "action_not_permitted", res)
					self.assertIn("recipient", res.get("message", ""))
					self.assertEqual(self.api.calls, [])

	@unittest.expectedFailure  # BUG: profile actions skip the recipient scope check
	def test_profile_chat_scope_gap(self):
		"""Known gap: profile actions take a ``chat_id`` but are not checked against the send scope."""
		self.configure_scope("Current contact")
		res = self.adm_call("set_chat_menu_button", chat_id=DENIED, menu_button={"type": "default"})
		self.assertEqual(res.get("error"), "action_not_permitted", res)
		self.assertEqual(self.sent("setChatMenuButton"), [])

	@unittest.expectedFailure  # BUG: confirmed setMyCommands skips the recipient scope check
	def test_profile_command_scope_gap_after_confirmation(self):
		"""Known gap: a chat-scoped setMyCommands for a non-scoped chat goes through once confirmed."""
		self.configure_scope("Current contact")
		args = {
			"commands": [{"command": "a", "description": "b"}], "command_scope": "chat", "chat_id": DENIED,
		}
		token = self.adm_call("set_my_commands", **args)["confirmation_token"]
		res = self.adm_call("set_my_commands", confirm=True, confirmation_token=token, **args)
		self.assertEqual(res.get("error"), "action_not_permitted", res)
		self.assertEqual(self.sent("setMyCommands"), [])


class TestAdminFlagMatrix(Harness):
	def test_flag_by_gateway_matrix(self):
		for action, (group, *_rest) in adm.ACTIONS.items():
			for gw_on in (False, True):
				for flag_on in (False, True):
					with self.subTest(action=action, gateway=gw_on, flag=flag_on):
						self.api.calls.clear()
						self.gw_on = gw_on
						self.flags = {g: True for g in FLAG_FOR_GROUP}
						self.flags[group] = flag_on
						res = self.adm_call(action, **ADMIN_ARGS[action])
						if not gw_on:
							self.assertEqual(res.get("error"), "action_not_permitted", res)
						elif not flag_on:
							self.assertEqual(res.get("error"), "action_not_permitted", res)
							self.assertIn(FLAG_FOR_GROUP[group], res.get("message", ""))
						else:
							self.assertNotIn("is off", res.get("message", ""))
						if not (gw_on and flag_on):
							self.assertEqual(self.api.calls, [], "disabled action reached the Bot API")


class TestConfirmation(Harness):
	def setUp(self):
		super().setUp()
		self.gw_on = True

	def mutated(self):
		return [c["method"] for c in self.api.calls if c["method"] in MUTATING.values()]

	def test_two_step_for_each_destructive_action(self):
		for action, method in MUTATING.items():
			args = ADMIN_ARGS[action]
			with self.subTest(action=action):
				self.api.calls.clear()
				first = self.adm_call(action, **args)
				self.assertEqual(first["error"], "needs_confirmation")
				token = first["confirmation_token"]
				self.assertEqual(self.mutated(), [], "nothing may be mutated before confirmation")

				mismatch = self.adm_call(action, confirm=True, confirmation_token=token, reason="x", **args)
				self.assertEqual(mismatch["error"], "confirmation_mismatch")
				self.assertEqual(self.mutated(), [])
				# the token is single use, even after a mismatch
				again = self.adm_call(action, confirm=True, confirmation_token=token, **args)
				self.assertEqual(again["error"], "confirmation_invalid")

				token = self.adm_call(action, **args)["confirmation_token"]
				ok = self.adm_call(action, confirm=True, confirmation_token=token, **args)
				self.assertTrue(ok["success"], ok)
				self.assertEqual(self.mutated(), [method])
				replay = self.adm_call(action, confirm=True, confirmation_token=token, **args)
				self.assertEqual(replay["error"], "confirmation_invalid")

	def test_confirm_flag_without_token_is_not_enough(self):
		res = self.adm_call("ban", confirm=True, user_id=5)
		self.assertEqual(res["error"], "needs_confirmation")
		self.assertTrue(res.get("confirmation_token"))
		self.assertEqual(self.mutated(), [])

	def test_owner_run_needs_confirm_flag_only(self):
		self.owner = True
		first = self.adm_call("ban", user_id=5)
		self.assertEqual(first["error"], "needs_confirmation")
		self.assertNotIn("confirmation_token", first)
		self.assertEqual(self.mutated(), [])
		self.assertTrue(self.adm_call("ban", user_id=5, confirm=True)["success"])
		self.assertEqual(self.mutated(), ["banChatMember"])


class TestIdempotency(Harness):
	def test_same_key_same_chat_sends_once(self):
		first = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		second = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		self.assertTrue(first["success"])
		self.assertEqual(first, second)
		self.assertEqual(len(self.sent("sendMessage")), 1)

	def test_same_key_other_chat_is_a_new_send(self):
		self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		self.tg_call("send_message", chat_id=OTHER, text="hi", idempotency_key="k1")
		self.assertEqual(len(self.sent("sendMessage")), 2)

	def test_same_key_other_action_is_a_new_send(self):
		self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		self.tg_call("send_photo", chat_id=CUR, photo=PHOTO, idempotency_key="k1")
		self.assertEqual(len(self.sent("sendMessage")), 1)
		self.assertEqual(len(self.sent("sendPhoto")), 1)

	def test_key_is_scoped_to_the_run(self):
		self.gw_on = True
		self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		self.run_id = "run2"
		self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k1")
		self.assertEqual(len(self.sent("sendMessage")), 2)

	def test_invalid_key_is_refused_without_a_call(self):
		res = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="bad key!")
		self.assertEqual(res["error"], "invalid_idempotency_key")
		self.assertEqual(self.api.calls, [])

	def test_failed_send_releases_key_for_retry(self):
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: chat not found", 400))
		first = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k2")
		self.assertFalse(first["success"])
		self.assertTrue(self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k2")["success"])
		self.assertEqual(len(self.sent("sendMessage")), 2)

	def test_non_send_action_ignores_key(self):
		self.tg_call("get_me", idempotency_key="k3")
		self.tg_call("get_me", idempotency_key="k3")
		self.assertEqual(len(self.sent("getMe")), 2)


class TestCaps(Harness):
	def test_telegram_per_run_cap(self):
		self.gw_on = True
		self.configure_scope("Current contact", per_run=2)
		results = [self.tg_call("send_message", chat_id=CUR, text=str(i)) for i in range(3)]
		self.assertTrue(results[0]["success"] and results[1]["success"])
		self.assertEqual(results[2]["error"], "send_cap_exceeded")
		self.assertEqual(len(self.sent("sendMessage")), 2)

	def test_telegram_per_day_cap(self):
		self.gw_on = True
		self.configure_scope("Current contact", per_run=20, per_day=2)
		self.tg_call("send_message", chat_id=CUR, text="a")
		self.tg_call("send_message", chat_id=CUR, text="b")
		res = self.tg_call("send_message", chat_id=CUR, text="c")
		self.assertEqual(res["error"], "send_cap_exceeded")
		self.assertIn("retry_after", res)
		self.assertEqual(len(self.sent("sendMessage")), 2)

	def test_failed_send_releases_its_cap_slot(self):
		self.gw_on = True
		self.configure_scope("Current contact", per_run=1)
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked", 403))
		self.assertFalse(self.tg_call("send_message", chat_id=CUR, text="a")["success"])
		self.assertTrue(self.tg_call("send_message", chat_id=CUR, text="b")["success"])

	def test_refused_recipient_does_not_consume_a_slot(self):
		self.gw_on = True
		self.configure_scope("Current contact", per_run=1)
		refused = self.tg_call("send_message", chat_id=DENIED, text="a")
		self.assertEqual(refused["error"], "recipient_not_permitted")
		self.assertTrue(self.tg_call("send_message", chat_id=CUR, text="b")["success"])

	def test_admin_per_run_cap_and_read_only_actions_are_free(self):
		self.gw_on = True
		self.owner = True
		self.cap = 2
		results = [self.adm_call("ban", user_id=5, confirm=True) for _ in range(3)]
		self.assertTrue(results[0]["success"] and results[1]["success"])
		self.assertEqual(results[2]["error"], "admin_cap_exceeded")
		for _ in range(5):
			self.assertTrue(self.adm_call("get_admins")["success"])
		self.assertEqual(self.adm_call("ban", user_id=5, confirm=True)["error"], "admin_cap_exceeded")

	def test_admin_failed_action_releases_its_slot(self):
		self.gw_on = True
		self.owner = True
		self.cap = 1
		self.api.queue("banChatMember", FakeBotApi.error("Bad Request: user is an administrator", 400))
		self.assertFalse(self.adm_call("ban", user_id=5, confirm=True)["success"])
		self.assertTrue(self.adm_call("ban", user_id=5, confirm=True)["success"])


class TestTokenNeverLeaks(Harness):
	def _leaky(self, variant):
		if variant == "error_body":
			self.api.fail_with = FakeBotApi.error(f"Unauthorized: bad token {TOKEN} in {SECRET}", 401)
		else:
			self.api.raise_with = RuntimeError(f"connect {TG_BASE}/bot{TOKEN}/x failed: {SECRET}")

	def test_telegram_errors_are_redacted(self):
		self.gw_on = True
		self.configure_scope("Any number")
		for variant in ("error_body", "raise"):
			self._leaky(variant)
			errors = 0
			for action in TG_ENUM:
				with self.subTest(variant=variant, action=action):
					raw = tg.handle_action(action=action, chat_id=CUR, **TG_ARGS[action])
					self.assertNotIn(TOKEN, raw)
					self.assertNotIn(SECRET, raw)
					errors += not json.loads(raw).get("success")
			self.assertGreater(errors, 0)
			self.api.fail_with = self.api.raise_with = None

	def test_admin_errors_are_redacted(self):
		self.gw_on = True
		self.owner = True
		for variant in ("error_body", "raise"):
			self._leaky(variant)
			for action in ADMIN_ENUM:
				with self.subTest(variant=variant, action=action):
					raw = adm.handle_action(action=action, confirm=True, **ADMIN_ARGS[action])
					self.assertNotIn(TOKEN, raw)
					self.assertNotIn(SECRET, raw)
			self.api.fail_with = self.api.raise_with = None


if __name__ == "__main__":
	unittest.main()
