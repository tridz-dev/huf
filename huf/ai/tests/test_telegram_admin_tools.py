# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""telegram_admin agent tool over the in-memory fake Bot API (no network, no live bot)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import telegram_business as biz
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi, FakeResponse
from huf.ai.tools import telegram_admin_tools as tool

BOT = 999
CHAT = "-1001"


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
	def __init__(self):
		super().__init__()
		self.members = {BOT: {"status": "administrator", "can_restrict_members": True, "can_promote_members": True,
			"can_change_info": True, "can_pin_messages": True, "can_delete_messages": True, "can_invite_users": True}}

	def http_post(self, url, *, json_data=None, data=None, files=None, timeout=None):
		method = url.rsplit("/", 1)[-1]
		payload = dict(json_data if json_data is not None else (data or {}))
		if method == "getMe":
			self.calls.append({"method": method, "payload": payload, "files": None, "url": url})
			return FakeResponse({"ok": True, "result": {"id": BOT, "is_bot": True}})
		if method == "getChatMember":
			self.calls.append({"method": method, "payload": payload, "files": None, "url": url})
			m = self.members.get(payload["user_id"], {"status": "member"})
			return FakeResponse({"ok": True, "result": m})
		return super().http_post(url, json_data=json_data, data=data, files=files, timeout=timeout)


class Base(unittest.TestCase):
	flags = {"group": True, "profile": True, "business": True}
	owner = False
	cap = 50
	always_human = False  # legacy owner-path tests exercise ban/promote directly; set True for the real gate

	def setUp(self):
		self.api = Api()
		self.cache = MemCache()
		self.addCleanup(patch.stopall)

		def mk(token, *, timeout=30):
			return TelegramBotClient(token, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None)

		patch.object(tool, "_make_client", side_effect=mk).start()
		patch.object(tool, "_token", return_value=TOKEN).start()
		patch.object(tool, "_cache", return_value=self.cache).start()
		patch.object(tool, "_audit").start()
		patch.object(tool, "_flag", side_effect=lambda gw, g: self.flags[g]).start()
		patch.object(tool, "_cap_limit", side_effect=lambda gw: self.cap).start()
		patch.object(tool, "_is_owner_run", side_effect=lambda gw, chat: self.owner).start()
		if not self.always_human:
			patch.object(tool, "ALWAYS_HUMAN_APPROVAL", frozenset()).start()
		patch.object(tool, "_is_paired_admin", side_effect=lambda gw, uid: str(uid) == "777").start()
		patch.object(tool.scope, "run_gateway", return_value="gw1").start()
		patch.object(tool.scope, "effective_run_id", return_value="run1").start()
		patch.object(tool.scope, "current_chat", return_value=CHAT).start()
		patch.object(tool.scope, "check_recipient", return_value=None).start()
		patch.object(tool.scope, "claim_send", return_value=None).start()
		patch.object(tool.scope, "release_send").start()
		self.admins = [{"telegram_user_id": "900", "chat_id": "900", "gateway": "gw1", "role_scope": "Admin",
			"frappe_user": "a@x.com", "name": "b1"}]
		patch.object(tool, "_admin_bindings", side_effect=lambda gw: list(self.admins)).start()
		patch.object(tool, "_callback_signer", side_effect=lambda gw, chat: (lambda p: p + "|sig")).start()

	def run_action(self, action, **kw):
		return json.loads(tool.handle_action(action=action, **kw))

	def payload(self, method):
		return self.api.last(method)["payload"]


class TestGates(Base):
	def test_flag_off_refused(self):
		for group, action in (("group", "ban"), ("profile", "set_my_name"), ("business", "get_business_connection")):
			Base.flags = {"group": True, "profile": True, "business": True, group: False}
			r = self.run_action(action, chat_id=CHAT, user_id=5, confirm=True, name="x", business_connection_id="c")
			self.assertEqual(r["error"], "action_not_permitted", action)
		Base.flags = {"group": True, "profile": True, "business": True}
		self.assertEqual(self.api.calls, [])

	def test_no_gateway_refused(self):
		with patch.object(tool.scope, "run_gateway", return_value=""):
			r = self.run_action("get_admins", chat_id=CHAT)
		self.assertEqual(r["error"], "action_not_permitted")
		self.assertEqual(self.api.calls, [])

	def test_unknown_action(self):
		self.assertEqual(self.run_action("nuke")["error"], "unknown_action")

	def test_scope_refusal(self):
		refusal = json.dumps({"message": "nope"})
		with patch.object(tool.scope, "check_recipient", return_value=refusal):
			self.assertEqual(self.run_action("get_admins", chat_id="-5")["error"], "action_not_permitted")


class TestRights(Base):
	def test_bot_not_admin(self):
		self.api.members[BOT] = {"status": "member"}
		self.assertEqual(self.run_action("pin", message_id=1)["error"], "bot_not_admin")

	def test_missing_right(self):
		self.api.members[BOT] = {"status": "administrator", "can_pin_messages": False}
		r = self.run_action("pin", message_id=1)
		self.assertEqual((r["error"], r["missing_right"]), ("bot_missing_right", "can_pin_messages"))
		self.assertEqual(self.api.of("pinChatMessage"), [])


class TestConfirmation(Base):
	def test_owner_needs_only_confirm(self):
		Base.owner = True
		self.addCleanup(setattr, Base, "owner", False)
		# ban is in ALWAYS_HUMAN_APPROVAL now; delete_message keeps the simple owner confirm=true path
		self.assertEqual(self.run_action("delete_message", message_id=3)["error"], "needs_confirmation")
		self.assertTrue(self.run_action("delete_message", message_id=3, confirm=True)["success"])

	def test_non_destructive_needs_nothing(self):
		self.assertTrue(self.run_action("set_chat_title", title="Hi")["success"])


class TestCapsAndTargets(Base):
	def test_cap(self):
		Base.cap = 2
		self.addCleanup(setattr, Base, "cap", 50)
		self.assertTrue(self.run_action("pin", message_id=1)["success"])
		self.assertTrue(self.run_action("pin", message_id=2)["success"])
		self.assertEqual(self.run_action("pin", message_id=3)["error"], "admin_cap_exceeded")
		self.assertEqual(len(self.api.of("pinChatMessage")), 2)
		self.assertTrue(self.run_action("get_admins")["success"])  # reads are free

	def test_failed_action_releases_cap(self):
		self.api.queue("pinChatMessage", self.api.error("Bad Request: message to pin not found", 400))
		self.assertFalse(self.run_action("pin", message_id=1)["success"])
		self.assertEqual(tool._cap_count("gw1", "run1"), 0)

	def test_chat_admin_target_refused(self):
		self.api.members[42] = {"status": "administrator"}
		self.api.members[43] = {"status": "creator"}
		for uid in (42, 43):
			for action in ("ban", "restrict", "promote"):
				self.assertEqual(self.run_action(action, user_id=uid, rights=["can_pin_messages"])["error"], "target_is_admin")
		self.assertEqual(self.run_action("demote", user_id=43)["error"], "target_is_admin")
		self.assertEqual(self.api.of("banChatMember"), [])

	def test_paired_admin_refused(self):
		self.assertEqual(self.run_action("ban", user_id=777)["error"], "target_is_admin")
		self.assertEqual(self.run_action("demote", user_id=777)["error"], "target_is_admin")

	def test_demote_regular_admin_ok(self):
		self.api.members[42] = {"status": "administrator"}
		self.assertTrue(self.run_action("demote", user_id=42)["success"])
		p = self.payload("promoteChatMember")
		self.assertFalse(p["can_pin_messages"])


class TestPayloads(Base):
	owner = True
	def ok(self, action, **kw):
		r = self.run_action(action, **kw)
		self.assertTrue(r["success"], r)
		return r

	def test_ban_unban(self):
		self.ok("ban", user_id=5, duration_minutes=10, revoke_messages=True, confirm=True)
		p = self.payload("banChatMember")
		self.assertEqual((p["chat_id"], p["user_id"], p["revoke_messages"]), (-1001, 5, True))
		self.assertGreater(p["until_date"], 0)
		self.ok("unban", user_id=5)
		self.assertEqual(self.payload("unbanChatMember")["only_if_banned"], True)

	def test_restrict_preset_and_unrestrict(self):
		self.ok("restrict", user_id=5, preset="mute", confirm=True)
		p = self.payload("restrictChatMember")
		self.assertFalse(p["permissions"]["can_send_messages"])
		self.assertTrue(p["permissions"]["can_invite_users"])
		self.ok("unrestrict", user_id=5)
		self.assertTrue(all(self.payload("restrictChatMember")["permissions"].values()))

	def test_restrict_bad_preset(self):
		self.api.members[5] = {"status": "member"}
		r = self.run_action("restrict", user_id=5, preset="zzz", confirm=True)
		self.assertEqual(r["error"], "invalid_argument")

	def test_promote_explicit_rights_and_no_escalation(self):
		a = dict(user_id=5, rights=["can_pin_messages", "can_delete_messages"])
		self.ok("promote", confirm=True, **a)
		p = self.payload("promoteChatMember")
		self.assertTrue(p["can_pin_messages"] and p["can_delete_messages"])
		self.assertFalse(p["can_promote_members"])
		bad = dict(user_id=5, rights=["can_promote_members"])
		self.assertEqual(
			self.run_action("promote", confirm=True, **bad)["error"], "right_not_grantable"
		)

	def test_chat_edits_and_pins(self):
		self.ok("set_chat_title", title="T")
		self.assertEqual(self.payload("setChatTitle"), {"chat_id": -1001, "title": "T"})
		self.ok("set_chat_description", description="D")
		self.assertEqual(self.payload("setChatDescription")["description"], "D")
		self.ok("pin", message_id=7)
		self.assertEqual(self.payload("pinChatMessage")["message_id"], 7)
		self.ok("unpin", message_id=7)
		self.assertEqual(self.payload("unpinChatMessage"), {"chat_id": -1001, "message_id": 7})
		self.ok("approve_join_request", user_id=5)
		self.assertEqual(self.payload("approveChatJoinRequest"), {"chat_id": -1001, "user_id": 5})
		self.ok("decline_join_request", user_id=5)
		self.assertEqual(self.payload("declineChatJoinRequest")["user_id"], 5)

	def test_invite_links(self):
		self.ok("create_invite_link", name="n", member_limit=3)
		self.assertEqual(self.payload("createChatInviteLink"), {"chat_id": -1001, "name": "n", "member_limit": 3})
		self.ok("revoke_invite_link", invite_link="https://t.me/+abc")
		self.assertEqual(self.payload("revokeChatInviteLink")["invite_link"], "https://t.me/+abc")

	def test_get_admins(self):
		self.api.queue("getChatAdministrators", {"ok": True, "result": [{"status": "creator", "user": {"id": 1, "username": "o"}}]})
		r = self.ok("get_admins")
		self.assertEqual(r["result"][0]["user_id"], 1)

	def test_title_too_long(self):
		self.assertEqual(self.run_action("set_chat_title", title="x" * 200)["error"], "invalid_argument")


class TestProfile(Base):
	owner = True
	def test_profile_actions(self):
		self.assertTrue(self.run_action("set_my_name", name="Bot", language_code="en")["success"])
		self.assertEqual(self.payload("setMyName"), {"name": "Bot", "language_code": "en"})
		self.run_action("set_my_description", description="d")
		self.assertEqual(self.payload("setMyDescription"), {"description": "d"})
		self.run_action("set_my_short_description", short_description="s")
		self.assertEqual(self.payload("setMyShortDescription"), {"short_description": "s"})
		self.run_action("set_chat_menu_button", menu_button={"type": "commands"})
		self.assertEqual(self.payload("setChatMenuButton"), {"menu_button": {"type": "commands"}})
		self.assertEqual(self.run_action("set_chat_menu_button", menu_button={"type": "web_app", "text": "x", "web_app": {"url": "http://a"}})["error"], "invalid_argument")

	def test_set_my_commands_confirm_and_payload(self):
		cmds = [{"command": "help", "description": "Help", "is_ephemeral": True}]
		r = self.run_action("set_my_commands", commands=cmds, command_scope="all_private_chats")
		self.assertEqual(r["error"], "needs_confirmation")
		r = self.run_action(
			"set_my_commands", commands=cmds, command_scope="all_private_chats", confirm=True,
		)
		self.assertTrue(r["success"], r)
		p = self.payload("setMyCommands")
		self.assertEqual(p["scope"], {"type": "all_private_chats"})
		self.assertTrue(p["commands"][0]["is_ephemeral"])

	def test_bad_commands(self):
		bad = [{"command": "Bad Name", "description": "x"}]
		self.assertEqual(self.run_action("set_my_commands", commands=bad, confirm=True)["error"], "invalid_argument")


class TestBusiness(Base):
	owner = True
	def setUp(self):
		super().setUp()
		self.conns = {
			"c1": {"id": "c1", "gateway": "gw1", "owner_id": "1", "owner_name": "O", "user_chat_id": "1",
				"rights": {"can_reply": True, "can_read_messages": True, "can_delete_sent_messages": True}, "is_enabled": True},
			"c2": {"id": "c2", "gateway": "other", "owner_id": "1", "owner_name": "O", "user_chat_id": "1",
				"rights": {"can_reply": True}, "is_enabled": True},
			"c3": {"id": "c3", "gateway": "gw1", "owner_id": "1", "owner_name": "O", "user_chat_id": "1",
				"rights": {}, "is_enabled": True},
		}
		patch.object(biz, "get_connection", side_effect=lambda cid, *a, **k: self.conns.get(cid)).start()

	def test_get_connection(self):
		r = self.run_action("get_business_connection", business_connection_id="c1")
		self.assertTrue(r["result"]["rights"]["can_reply"])
		self.assertEqual(self.api.calls, [])

	def test_unknown_or_foreign_connection(self):
		for cid in ("nope", "c2"):
			r = self.run_action("send_business_message", business_connection_id=cid, chat_id=5, text="hi")
			self.assertEqual(r["error"], "unknown_connection")

	def test_send_payload(self):
		r = self.run_action("send_business_message", business_connection_id="c1", chat_id=5, text="hi", reply_to_message_id=2)
		self.assertTrue(r["success"], r)
		p = self.payload("sendMessage")
		self.assertEqual((p["business_connection_id"], p["chat_id"], p["text"]), ("c1", 5, "hi"))
		self.assertEqual(p["reply_parameters"]["message_id"], 2)

	def test_rights_enforced(self):
		for action, kw in (("send_business_message", {"text": "x", "chat_id": 5}),
			("read_business_message", {"chat_id": 5, "message_id": 1})):
			r = self.run_action(action, business_connection_id="c3", **kw)
			self.assertEqual(r["error"], "business_right_missing", action)
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_read_and_delete(self):
		self.assertTrue(self.run_action("read_business_message", business_connection_id="c1", chat_id=5, message_id=9)["success"])
		self.assertEqual(self.payload("readBusinessMessage")["message_id"], 9)
		args = dict(business_connection_id="c1", message_ids=[1, 2])
		t = self.run_action("delete_business_messages", **args)
		self.assertEqual(t["error"], "needs_confirmation")
		r = self.run_action("delete_business_messages", confirm=True, **args)
		self.assertTrue(r["success"], r)
		self.assertEqual(self.payload("deleteBusinessMessages"), {"business_connection_id": "c1", "message_ids": [1, 2]})

	def test_delete_all_needs_all_right(self):
		args = dict(business_connection_id="c1", message_ids=[1], all_messages=True)
		patch.object(tool.scope, "settings", return_value={"scope": "Any number"}).start()
		r = self.run_action("delete_business_messages", confirm=True, **args)
		self.assertEqual(r["error"], "business_right_missing")


class TestBusinessScope(Base):
	"""Business actions obey the recipient scope and send caps; connections need an exact gateway match."""

	def setUp(self):
		super().setUp()
		self.conns = {"c1": {"id": "c1", "gateway": "gw1", "owner_id": "1", "owner_name": "O", "user_chat_id": "1",
			"rights": {"can_reply": True, "can_read_messages": True, "can_delete_sent_messages": True}, "is_enabled": True}}
		patch.object(biz, "get_connection", side_effect=lambda cid, *a, **k: self.conns.get(cid)).start()

	def deny(self, message="nope"):
		return patch.object(tool.scope, "check_recipient", return_value=json.dumps({"message": message}))

	def test_send_denied_outside_scope(self):
		with self.deny():
			r = self.run_action("send_business_message", business_connection_id="c1", chat_id=5, text="hi")
		self.assertEqual(r["error"], "recipient_not_permitted")
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_read_denied_outside_scope(self):
		with self.deny():
			r = self.run_action("read_business_message", business_connection_id="c1", chat_id=5, message_id=1)
		self.assertEqual(r["error"], "recipient_not_permitted")
		self.assertEqual(self.api.of("readBusinessMessage"), [])

	def test_send_counted_and_cap_enforced(self):
		self.assertTrue(self.run_action("send_business_message", business_connection_id="c1", chat_id=5, text="hi")["success"])
		tool.scope.claim_send.assert_called_with("gw1", "run1")
		cap = json.dumps({"message": "cap"})
		with patch.object(tool.scope, "claim_send", return_value=cap):
			r = self.run_action("send_business_message", business_connection_id="c1", chat_id=5, text="again")
		self.assertEqual(r["error"], "send_cap_exceeded")
		self.assertEqual(len(self.api.of("sendMessage")), 1)

	def test_failed_send_releases_claim(self):
		self.api.queue("sendMessage", self.api.error("Bad Request: nope", 400))
		self.assertFalse(self.run_action("send_business_message", business_connection_id="c1", chat_id=5, text="hi")["success"])
		tool.scope.release_send.assert_called_with("gw1", "run1")

	def test_delete_all_messages_needs_any_number_scope(self):
		Base.owner = True
		self.addCleanup(setattr, Base, "owner", False)
		self.conns["c1"]["rights"]["can_delete_all_messages"] = True
		with patch.object(tool.scope, "settings", return_value={"scope": "Allow-list"}):
			r = self.run_action("delete_business_messages", business_connection_id="c1", message_ids=[1],
				all_messages=True, confirm=True)
		self.assertEqual(r["error"], "recipient_not_permitted")
		self.assertEqual(self.api.of("deleteBusinessMessages"), [])

	def test_delete_checks_chat_scope(self):
		Base.owner = True
		self.addCleanup(setattr, Base, "owner", False)
		with self.deny():
			r = self.run_action("delete_business_messages", business_connection_id="c1", message_ids=[1],
				chat_id=77, confirm=True)
		self.assertEqual(r["error"], "recipient_not_permitted")

	def test_unbound_connection_refused_for_every_gateway(self):
		self.conns["c4"] = {**self.conns["c1"], "id": "c4", "gateway": ""}
		for action, kw in (("get_business_connection", {}), ("send_business_message", {"chat_id": 5, "text": "x"})):
			r = self.run_action(action, business_connection_id="c4", **kw)
			self.assertEqual(r["error"], "unknown_connection", action)
		self.assertEqual(self.api.of("sendMessage"), [])

	def test_menu_button_chat_scope_checked(self):
		with self.deny():
			r = self.run_action("set_chat_menu_button", chat_id=55, menu_button={"type": "default"})
		self.assertEqual(r["error"], "action_not_permitted")
		self.assertEqual(self.api.of("setChatMenuButton"), [])
		self.assertTrue(self.run_action("set_chat_menu_button", chat_id=55, menu_button={"type": "default"})["success"])


class TestHumanApproval(Base):
	"""Non-owner runs cannot self-confirm: a human Admin approves via signed buttons."""

	def setUp(self):
		super().setUp()
		from huf.ai import telegram_admin as ta

		self.ta = ta

	def buttons(self):
		kb = self.api.last("sendMessage")["payload"]["reply_markup"]["inline_keyboard"][0]
		return {b["text"]: b["callback_data"] for b in kb}

	def test_pending_and_buttons_to_admin_chat(self):
		r = self.run_action("ban", user_id=5)
		self.assertEqual(r["status"], "pending_human_approval")
		self.assertEqual(self.api.of("banChatMember"), [])
		sent = self.api.last("sendMessage")["payload"]
		self.assertEqual(sent["chat_id"], 900)
		b = self.buttons()
		self.assertTrue(b["Approve"].startswith("adm:c:") and b["Reject"].startswith("adm:x:"))

	def test_agent_confirm_and_token_are_ignored(self):
		r = self.run_action("ban", user_id=5, confirm=True, confirmation_token="whatever")
		self.assertEqual(r["status"], "pending_human_approval")
		self.assertEqual(self.api.of("banChatMember"), [])

	def test_no_admin_binding_refuses(self):
		self.admins = []
		r = self.run_action("ban", user_id=5, confirm=True)
		self.assertEqual(r["error"], "no_admin_available")
		self.assertEqual(self.api.of("sendMessage"), [])
		self.assertEqual(tool._cap_count("gw1", "run1"), 0)

	def test_duplicate_request_not_resent(self):
		self.run_action("delete_message", message_id=3)
		self.run_action("delete_message", message_id=3)
		self.assertEqual(len(self.api.of("sendMessage")), 1)

	def test_approved_press_executes_once(self):
		self.run_action("delete_message", message_id=3)
		nonce = self.buttons()["Approve"].split("|")[0].split(":")[2]
		action = self.ta.consume_nonce(nonce, "900", "900", cache=self.cache)
		self.assertEqual((action["op"], action["action"], action["gateway"], action["chat"]), ("agent_action", "delete_message", "gw1", CHAT))
		self.assertEqual(self.api.of("deleteMessage"), [])
		binding = {"name": "b1", "telegram_user_id": "900", "frappe_user": "a@x.com", "gateway": "gw1", "role_scope": "Admin", "chat_id": "900"}
		ctx = self.ta.Ctx(binding=binding, tg_user="900", chat_id="900", gateway="gw1", cache=self.cache)
		with patch.object(self.ta, "write_audit") as audit, patch.object(self.ta, "_commit"), patch.object(tool, "_gateway_token", return_value=TOKEN):
			self.ta.execute(ctx, action, nonce)
			self.assertEqual(self.payload("deleteMessage")["message_id"], 3)
			audit.assert_called()
			with self.assertRaises(self.ta.AdminError):
				self.ta.execute(ctx, action, nonce)
		self.assertEqual(len(self.api.of("deleteMessage")), 1)


class TestOwnerRank(unittest.TestCase):
	"""``_is_owner_run`` requires binding role rank >= Admin."""

	def owner(self, role):
		from types import SimpleNamespace

		with patch.object(tool.frappe, "db", new=SimpleNamespace(get_value=lambda *a, **k: role), create=True):
			return tool._is_owner_run("gw1", "55")

	def test_viewer_and_operator_chat_not_owner(self):
		self.assertFalse(self.owner("Viewer"))
		self.assertFalse(self.owner("Operator"))

	def test_admin_chat_is_owner(self):
		self.assertTrue(self.owner("Admin"))

	def test_no_binding_or_chat_not_owner(self):
		self.assertFalse(self.owner(None))
		self.assertFalse(tool._is_owner_run("gw1", ""))


class TestOwnerGate(Base):
	always_human = True

	def test_always_human_approval_set(self):
		self.assertEqual(set(tool.ALWAYS_HUMAN_APPROVAL), {"delete_business_messages", "promote", "ban"})

	def test_owner_ban_and_promote_still_need_human(self):
		Base.owner = True
		self.addCleanup(setattr, Base, "owner", False)
		for action in ("ban", "promote"):
			r = self.run_action(action, user_id=5, confirm=True)
			self.assertEqual(r["status"], "pending_human_approval", action)
		self.assertEqual(self.api.of("banChatMember"), [])

	def test_low_rank_chat_goes_to_human_and_refuses_without_admin(self):
		self.admins = []
		r = self.run_action("delete_message", message_id=3, confirm=True)
		self.assertEqual(r["error"], "no_admin_available")
		self.assertEqual(self.api.of("deleteMessage"), [])

	def test_low_rank_chat_pending_approval(self):
		r = self.run_action("delete_message", message_id=3, confirm=True)
		self.assertEqual(r["status"], "pending_human_approval")


class TestApprovalOrdering(Base):
	def test_pending_marked_before_send(self):
		from huf.ai import telegram_admin as ta

		seen = []
		orig = self.api.http_post

		def spy(url, **kw):
			if url.endswith("sendMessage"):
				seen.append([k for k in self.cache.d if k.startswith("huf_tg_adm_pend:") and not k.endswith(":s")])
			return orig(url, **kw)

		self.api.http_post = spy
		self.run_action("delete_message", message_id=3)
		self.assertTrue(seen and seen[0], "pending mark must exist when buttons are sent")
		self.assertTrue(any(ta.agent_action_pending(k.split(":", 1)[1], cache=self.cache) for k in seen[0]))

	def test_undelivered_clears_mark(self):
		with patch.object(tool, "_callback_signer", return_value=None):
			r = self.run_action("delete_message", message_id=3)
		self.assertEqual(r["error"], "no_admin_available")
		self.assertFalse([k for k in self.cache.d if k.startswith("huf_tg_adm_pend:")])
		self.assertEqual(self.run_action("delete_message", message_id=3)["status"], "pending_human_approval")

	def test_concurrent_duplicate_sends_once(self):
		import threading

		results = []
		barrier = threading.Barrier(6)

		def go():
			barrier.wait()
			results.append(self.run_action("delete_message", message_id=9)["status"])

		ts = [threading.Thread(target=go) for _ in range(6)]
		[t.start() for t in ts]
		[t.join() for t in ts]
		self.assertEqual(results, ["pending_human_approval"] * 6)
		self.assertEqual(len(self.api.of("sendMessage")), 1)


if __name__ == "__main__":
	unittest.main()
