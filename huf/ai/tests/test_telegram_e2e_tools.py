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
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import telegram_admin as ta
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
ADMIN_BINDING = {
	"name": "b1",
	"telegram_user_id": "900",
	"chat_id": "900",
	"gateway": "gw1",
	"role_scope": "Admin",
	"frappe_user": "a@x.com",
}
SECRET = TOKEN.split(":", 1)[-1]
PHOTO = "https://cdn.test/a.jpg"
TG_BASE = "https://api.telegram.org"
FLAG_FOR_GROUP = adm.FLAGS
ADMIN_RIGHTS = {
	"can_restrict_members": True,
	"can_promote_members": True,
	"can_change_info": True,
	"can_pin_messages": True,
	"can_delete_messages": True,
	"can_invite_users": True,
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
	"send_speech": {"text": "hello"},
	"send_audio": {"audio": "https://cdn.test/a.mp3"},
	"send_video": {"video": "https://cdn.test/a.mp4"},
	"send_animation": {"animation": "https://cdn.test/a.gif"},
	"send_sticker": {"sticker": "https://cdn.test/a.webp"},
	"send_media_group": {"items": [{"type": "photo", "media": PHOTO}, {"type": "photo", "media": PHOTO}]},
	"send_location": {"latitude": 1.0, "longitude": 2.0},
	"send_contact": {"phone_number": "+100", "first_name": "A"},
	"set_reaction": {"message_id": 3, "emoji": "\U0001f44d"},
	"send_chat_action": {"chat_action": "typing"},
	"edit_message_text": {"message_id": 3, "text": "x"},
	"edit_message_caption": {"message_id": 3, "caption": "x"},
	"edit_message_reply_markup": {"message_id": 3},
	"delete_message": {"message_id": 3},
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
	"send_business_message": {"business_connection_id": "c", "chat_id": CUR, "text": "x"},
	"read_business_message": {"business_connection_id": "c", "chat_id": CUR, "message_id": 3},
	"delete_business_messages": {"business_connection_id": "c", "message_ids": [1]},
}
# state-changing action -> the Bot API method it must call once a human admin approved it (send_business_message
# is covered separately: its method, sendMessage, is also what the approval prompt uses)
MUTATING = {
	"ban": "banChatMember",
	"unban": "unbanChatMember",
	"restrict": "restrictChatMember",
	"unrestrict": "restrictChatMember",
	"promote": "promoteChatMember",
	"demote": "promoteChatMember",
	"set_chat_title": "setChatTitle",
	"set_chat_description": "setChatDescription",
	"pin": "pinChatMessage",
	"unpin": "unpinChatMessage",
	"delete_message": "deleteMessage",
	"approve_join_request": "approveChatJoinRequest",
	"decline_join_request": "declineChatJoinRequest",
	"create_invite_link": "createChatInviteLink",
	"revoke_invite_link": "revokeChatInviteLink",
	"set_my_commands": "setMyCommands",
	"set_my_name": "setMyName",
	"set_my_description": "setMyDescription",
	"set_my_short_description": "setMyShortDescription",
	"set_chat_menu_button": "setChatMenuButton",
	"read_business_message": "readBusinessMessage",
	"delete_business_messages": "deleteBusinessMessages",
}
STATE_CHANGING = set(MUTATING) | {"send_business_message"}


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
		self.owner = True
		self.cap = 50
		self.flags = {"group": True, "profile": True, "business": True}
		self.gw_invalid = False  # inside a gateway run whose gateway is disabled / missing / not Telegram
		self.admins = [dict(ADMIN_BINDING)]  # active Admin cockpit bindings that approval buttons go to
		self.addCleanup(patch.stopall)
		from huf.ai.gateway_adapters import telegram_voice

		patch.object(
			telegram_voice, "speech_upload", return_value=("reply.ogg", b"OggS", "audio/ogg")
		).start()  # no TTS/ffmpeg

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
		# owner-path tests drive ban/promote/delete_business_messages with confirm=true; the always-human gate is
		# covered in test_telegram_admin_tools (TestOwnerGate)
		patch.object(adm, "ALWAYS_HUMAN_APPROVAL", frozenset()).start()
		patch.object(adm, "_is_paired_admin", side_effect=lambda gw, uid: str(uid) == "777").start()
		patch.object(scope, "run_gateway", side_effect=lambda: "gw1" if self.gw_on else "").start()
		patch.object(
			scope,
			"gateway_state",
			side_effect=lambda: (
				("invalid", "") if self.gw_invalid else (("telegram", "gw1") if self.gw_on else ("none", ""))
			),
		).start()
		patch.object(adm, "_admin_bindings", side_effect=lambda gw: list(self.admins)).start()
		patch.object(adm, "_callback_signer", side_effect=lambda gw, chat: lambda p: p + "|sig").start()
		patch.object(adm, "_gateway_token", return_value=TOKEN).start()
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
			adm.biz,
			"get_connection",
			return_value={
				"id": "c",
				"gateway": "gw1",
				"rights": {"can_delete_sent_messages": True, "can_read_messages": True},
				"is_enabled": True,
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

	def approval_buttons(self):
		"""Approve/Reject callback_data of the last approval prompt sent to an admin chat."""
		markup = self.sent("sendMessage")[-1]["payload"]["reply_markup"]["inline_keyboard"][0]
		return {b["text"]: b["callback_data"] for b in markup}

	def press_admin(self, label, tg_user="900"):
		"""Press an approval button through the real admin callback handler (signature stub: ``|sig``)."""
		parsed = SimpleNamespace(
			kind="callback_query",
			callback_data=self.approval_buttons()[label],
			callback_query_id="cq",
			chat_id=tg_user,
			chat_type="private",
			sender_id=tg_user,
			message_id=11,
		)
		adapter = MagicMock()
		adapter.verify_callback_data.side_effect = lambda raw, chat: raw.rsplit("|", 1)[0]
		binding = dict(ADMIN_BINDING, telegram_user_id=tg_user, chat_id=tg_user)
		with (
			patch.object(ta, "get_binding", return_value=binding),
			patch.object(ta, "write_audit"),
			patch.object(ta, "_commit"),
			patch.object(ta, "_rollback"),
		):
			return ta.handle_callback(SimpleNamespace(name="gw1"), adapter, parsed, cache=self.cache), adapter


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
		self.assertEqual({a for a, v in adm.ACTIONS.items() if v[2]}, STATE_CHANGING)
		self.assertEqual({a for a in adm.ACTIONS if a.startswith("get_")}, set(adm.ACTIONS) - STATE_CHANGING)

	def test_state_changing_actions_are_not_in_the_plain_tool(self):
		gone = {
			"pin_message",
			"unpin_message",
			"create_forum_topic",
			"edit_forum_topic",
			"close_forum_topic",
			"reopen_forum_topic",
			"delete_forum_topic",
		}
		self.assertFalse(gone & set(TG_ENUM))
		for action in gone:
			res = self.tg_call(action, chat_id=CUR, message_id=3, message_thread_id=5, name="n")
			self.assertEqual(res["error"], "owner_required", action)

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
		patch.object(
			adm, "ALWAYS_HUMAN_APPROVAL", frozenset(a for a, v in adm.ACTIONS.items() if v[2])
		).start()
		for action in ADMIN_ENUM:
			with self.subTest(action=action):
				res = self.adm_call(action, **ADMIN_ARGS[action])
				self.assertIsInstance(res.get("success"), bool, res)
				if action in STATE_CHANGING:
					self.assertTrue(res["success"], res)
					self.assertEqual(res.get("status"), "pending_human_approval", res)
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

	def test_profile_chat_scope_is_enforced(self):
		"""``set_chat_menu_button`` with a chat_id is checked against the send scope."""
		self.configure_scope("Current contact")
		res = self.adm_call("set_chat_menu_button", chat_id=DENIED, menu_button={"type": "default"})
		self.assertEqual(res.get("error"), "action_not_permitted", res)
		self.assertEqual(self.sent("setChatMenuButton"), [])

	def test_profile_command_scope_gap(self):
		"""A chat-scoped setMyCommands for a non-scoped chat should be refused before asking for approval."""
		self.configure_scope("Current contact")
		args = {
			"commands": [{"command": "a", "description": "b"}],
			"command_scope": "chat",
			"chat_id": DENIED,
		}
		res = self.adm_call("set_my_commands", **args)
		self.assertEqual(res.get("error"), "action_not_permitted", res)
		self.assertEqual(self.sent("sendMessage"), [])
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
	"""Every state change needs an owner run AND a HUMAN admin's button press; ``confirm`` is never approval."""

	def setUp(self):
		super().setUp()
		self.gw_on = True
		patch.object(
			adm, "ALWAYS_HUMAN_APPROVAL", frozenset(a for a, v in adm.ACTIONS.items() if v[2])
		).start()

	def mutated(self):
		return [c["method"] for c in self.api.calls if c["method"] in MUTATING.values()]

	def test_non_owner_destructive_action_is_pending_until_admin_approves(self):
		for action, method in MUTATING.items():
			args = ADMIN_ARGS[action]
			with self.subTest(action=action):
				self.api.calls.clear()
				self.cache.d.clear()
				first = self.adm_call(action, **args)
				self.assertEqual(first["status"], "pending_human_approval", first)
				self.assertEqual(self.mutated(), [], "nothing may be mutated before approval")
				prompt = self.sent("sendMessage")[-1]["payload"]
				self.assertEqual(prompt["chat_id"], 900)  # the Admin binding's chat, not the agent's
				self.assertEqual(set(self.approval_buttons()), {"Approve", "Reject"})
				ack, _ = self.press_admin("Approve")
				self.assertEqual(ack["note"], "confirmed")
				self.assertEqual(self.mutated(), [method])
				replay, _ = self.press_admin("Approve")  # nonce is single use
				self.assertEqual(replay["note"], "nonce_rejected")
				self.assertEqual(self.mutated(), [method])

	def test_reject_press_executes_nothing_and_blocks_later_approve(self):
		self.adm_call("ban", user_id=5)
		buttons = self.approval_buttons()
		ack, _ = self.press_admin("Reject")
		self.assertEqual(ack["note"], "cancelled")
		self.assertEqual(self.mutated(), [])
		self.assertEqual(
			[k for k in self.cache.d if k.startswith("huf_tg_adm_pend:") and not k.endswith(":u")], []
		)
		# the Approve button of the same request is dead once the request was resolved
		ack, _ = self.press_admin("Approve")
		self.assertEqual(self.mutated(), [], buttons)

	def test_agent_supplied_confirm_and_token_are_ignored(self):
		for extra in ({"confirm": True}, {"confirm": True, "confirmation_token": "whatever"}):
			with self.subTest(extra=extra):
				self.cache.d.clear()
				res = self.adm_call("ban", user_id=5, **extra)
				self.assertEqual(res["status"], "pending_human_approval", res)
				self.assertEqual(self.mutated(), [])

	def test_duplicate_pending_request_is_not_resent(self):
		self.adm_call("ban", user_id=5)
		again = self.adm_call("ban", user_id=5, confirm=True)
		self.assertEqual(again["status"], "pending_human_approval")
		self.assertEqual(len(self.sent("sendMessage")), 1)

	def test_no_admin_available_refuses_without_sending_or_counting(self):
		self.admins = []
		for action in MUTATING:
			with self.subTest(action=action):
				res = self.adm_call(action, confirm=True, **ADMIN_ARGS[action])
				self.assertFalse(res["success"], res)
				self.assertEqual(res["error"], "no_admin_available")
		self.assertEqual(self.sent("sendMessage"), [])
		self.assertEqual(self.mutated(), [])

	def test_admin_prompt_delivery_failure_is_no_admin_available(self):
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		res = self.adm_call("ban", user_id=5)
		self.assertEqual(res["error"], "no_admin_available")
		self.assertEqual(self.mutated(), [])

	def test_foreign_admin_of_other_gateway_cannot_approve(self):
		self.adm_call("ban", user_id=5)
		parsed = SimpleNamespace(
			kind="callback_query",
			callback_data=self.approval_buttons()["Approve"],
			callback_query_id="cq",
			chat_id="900",
			chat_type="private",
			sender_id="900",
			message_id=11,
		)
		adapter = MagicMock()
		adapter.verify_callback_data.side_effect = lambda raw, chat: raw.rsplit("|", 1)[0]
		binding = dict(ADMIN_BINDING, gateway="other-gw")
		with (
			patch.object(ta, "get_binding", return_value=binding),
			patch.object(ta, "write_audit"),
			patch.object(ta, "_commit"),
			patch.object(ta, "_rollback"),
		):
			ta.handle_callback(SimpleNamespace(name="other-gw"), adapter, parsed, cache=self.cache)
		self.assertEqual(self.mutated(), [])

	def test_non_owner_run_is_refused_for_every_state_change(self):
		self.owner = False
		for action, (_g, _r, changing, _c) in adm.ACTIONS.items():
			if not changing:
				continue
			with self.subTest(action=action):
				self.api.calls.clear()
				res = self.adm_call(action, confirm=True, **ADMIN_ARGS[action])
				self.assertEqual(res["error"], "owner_required", res)
				self.assertIn("bound admin", res["message"])
				self.assertEqual(self.mutated(), [])
				self.assertEqual(self.sent("sendMessage"), [])

	def test_read_only_actions_stay_free_for_non_owner(self):
		self.owner = False
		for action in ("get_admins", "get_business_connection"):
			res = self.adm_call(action, **ADMIN_ARGS[action])
			self.assertNotEqual(res.get("error"), "owner_required", res)


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


class TestInvalidGatewayRefusal(Harness):
	"""A gateway run whose gateway is disabled / missing / non-Telegram is refused by the telegram tool."""

	def setUp(self):
		super().setUp()
		self.gw_invalid = True  # run_gateway() is '' (patched) while gateway_state() says invalid

	def test_every_action_is_refused_without_a_bot_call(self):
		for action in TG_ENUM:
			with self.subTest(action=action):
				res = self.tg_call(action, chat_id=CUR, **TG_ARGS[action])
				self.assertFalse(res["success"], res)
				self.assertEqual(res["error"], "action_not_permitted", res)
		self.assertEqual(self.api.calls, [])

	def test_refusal_precedes_idempotency_replay(self):
		self.gw_invalid = False
		self.gw_on = True
		first = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k9")
		self.assertTrue(first["success"])
		self.gw_on = False
		self.gw_invalid = True
		res = self.tg_call("send_message", chat_id=CUR, text="hi", idempotency_key="k9")
		self.assertEqual(res["error"], "action_not_permitted")
		self.assertEqual(len(self.sent("sendMessage")), 1)

	def test_non_gateway_run_is_unchanged(self):
		self.gw_invalid = False
		self.gw_on = False
		self.assertTrue(self.tg_call("get_me")["success"])


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
