"""Join requests / Guard mode, membership events and group admin helpers (WP-8c)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import GatewayInboundRequest
from huf.ai.gateway_adapters import telegram_admin_actions as admin
from huf.ai.gateway_adapters import telegram_groups as groups
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.tests.telegram_fakes import (
	SECRET,
	TOKEN,
	FakeBotApi,
	clear_update_dedup,
	isolate_update_dedup,
	load_fixture,
)

GW = SimpleNamespace(
	name="gw1", provider="Telegram", mention_required=0, room_policy="Open", get=lambda k, d=None: d
)


def make():
	fake = FakeBotApi()
	adapter = TelegramGatewayAdapter({"token": TOKEN, "webhook_secret": SECRET}, download_attachments=False)
	adapter.client = TelegramBotClient(TOKEN, http_post=fake.http_post, http_get=fake.http_get)
	return fake, adapter


def req(payload):
	return GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})


def deliver(fixture, adapter):
	"""Route through telegram_ingest.handle_update (handlers registered by telegram_hooks import)."""
	import huf.ai.gateway_adapters.telegram_hooks

	clear_update_dedup()  # the same fixture update_id may be delivered repeatedly within one test
	return ing.handle_update(GW, adapter, req(load_fixture(fixture)))


class TestJoinRequests(unittest.TestCase):
	def setUp(self):
		isolate_update_dedup(self)

	def tearDown(self):
		groups.register_join_policy(None)

	def test_default_queues_records_pending_and_notifies_no_one(self):
		fake, ad = make()
		with mock.patch.object(groups, "record_pending_join", return_value="E1") as rec:
			res = deliver("chat_join_request", ad)
		self.assertEqual(res["decision"], "queue")
		rec.assert_called_once()
		self.assertEqual(rec.call_args[0][1]["user_id"], "777")
		self.assertEqual(fake.calls, [])  # no approve / decline / message

	def test_custom_policy_approve_and_decline_payloads(self):
		for decision, method in (
			("approve", "approveChatJoinRequest"),
			("decline", "declineChatJoinRequest"),
		):
			fake, ad = make()
			seen = []
			groups.register_join_policy(lambda ctx, d=decision: (seen.append(ctx), d)[1])
			res = deliver("chat_join_request", ad)
			self.assertEqual(res["decision"], decision)
			self.assertEqual(fake.last(method)["payload"], {"chat_id": -1001234, "user_id": 777})
			self.assertEqual(seen[0]["chat_title"], "Huf Guests")

	def test_guard_mode_answers_query(self):
		for decision in ("approve", "decline", "queue"):
			fake, ad = make()
			groups.register_join_policy(lambda ctx, d=decision: d)
			with mock.patch.object(groups, "record_pending_join"):
				deliver("chat_join_request_guard", ad)
			self.assertEqual(
				fake.last("answerChatJoinRequestQuery")["payload"],
				{"chat_join_request_query_id": "q-abc", "result": decision},
			)
			self.assertEqual(fake.of("approveChatJoinRequest"), [])

	def test_bad_or_raising_policy_falls_back_to_queue(self):
		for fn in (lambda c: "yes please", lambda c: 1 / 0, lambda c: None):
			groups.register_join_policy(fn)
			self.assertEqual(groups.decide({}), "queue")

	def test_insufficient_rights_is_clear_and_acked(self):
		fake, ad = make()
		fake.queue(
			"approveChatJoinRequest",
			fake.error("Bad Request: not enough rights to manage chat invite link", 400),
		)
		groups.register_join_policy(lambda c: "approve")
		res = deliver("chat_join_request", ad)
		self.assertTrue(res["success"])
		self.assertTrue(res["error"].startswith("not_enough_rights"))

	def test_non_join_unsupported_falls_through(self):
		fake, ad = make()
		self.assertIsNone(groups.handle_join_request(GW, ad, SimpleNamespace(raw={"update_id": 1}), None))

	def test_pending_record_is_deduplicated_room_entry(self):
		ctx = groups.join_request_ctx(load_fixture("chat_join_request"))
		with mock.patch("frappe.get_all", return_value=["EXIST"]), mock.patch("frappe.get_doc") as gd:
			self.assertEqual(groups.record_pending_join(GW, ctx), "EXIST")
			gd.assert_not_called()
		with (
			mock.patch("frappe.get_all", return_value=[]),
			mock.patch("huf.ai.gateway_service._new_unique_pairing_code", return_value="PAIR-1"),
			mock.patch("frappe.utils.now_datetime"),
			mock.patch("frappe.utils.add_to_date"),
			mock.patch("frappe.get_doc") as gd,
		):
			groups.record_pending_join(GW, ctx)
			doc = gd.call_args[0][0]
		self.assertEqual(
			(doc["entry_type"], doc["state"], doc["external_id"]), ("Room", "Pending", "join:-1001234:777")
		)


class TestMembership(unittest.TestCase):
	def test_bot_removed_marks_chat_unsendable(self):
		_, ad = make()
		from huf.ai.gateway_adapters.telegram_inbound import parse_update

		p = parse_update(load_fixture("my_chat_member_group_removed"))
		with (
			mock.patch("huf.ai.gateway_service._record_room_opt_out") as out,
			mock.patch("huf.ai.gateway_service._record_opt_out") as sender_out,
		):
			res = groups.handle_membership(GW, ad, p, None)
		self.assertEqual(res["transition"], "removed")
		out.assert_called_once_with(GW, "-1001234")
		sender_out.assert_not_called()  # a chat id must never become a Sender entry

	def test_bot_added_restores_and_promoted_logged(self):
		from huf.ai.gateway_adapters.telegram_inbound import parse_update

		with mock.patch("huf.ai.gateway_service._record_room_opt_in") as inn:
			res = groups.handle_membership(
				GW, None, parse_update(load_fixture("my_chat_member_group_added")), None
			)
		self.assertEqual(res["transition"], "added")
		inn.assert_called_once_with(GW, "-1001234")
		with (
			mock.patch("huf.ai.gateway_service._record_opt_in") as inn,
			mock.patch("huf.ai.gateway_service._record_opt_out") as out,
		):
			res = groups.handle_membership(
				GW, None, parse_update(load_fixture("my_chat_member_group_promoted")), None
			)
		self.assertEqual(res["transition"], "promoted")
		inn.assert_not_called()
		out.assert_not_called()

	def test_other_member_join_only_logged_and_private_declined(self):
		from huf.ai.gateway_adapters.telegram_inbound import parse_update

		with mock.patch("huf.ai.gateway_service._record_opt_out") as out:
			res = groups.handle_membership(GW, None, parse_update(load_fixture("chat_member_joined")), None)
		self.assertEqual(res["transition"], "added")
		out.assert_not_called()
		self.assertIsNone(
			groups.handle_membership(GW, None, parse_update(load_fixture("my_chat_member_blocked")), None)
		)


class TestAdminActions(unittest.TestCase):
	def setUp(self):
		self.fake = FakeBotApi()
		self.c = TelegramBotClient(TOKEN, http_post=self.fake.http_post, http_get=self.fake.http_get)

	def test_ban_unban_pin_delete_title_description(self):
		admin.ban_member(self.c, -100, 5, until_date=99, revoke_messages=True)
		self.assertEqual(
			self.fake.last("banChatMember")["payload"],
			{"chat_id": -100, "user_id": 5, "until_date": 99, "revoke_messages": True},
		)
		admin.unban_member(self.c, -100, 5)
		self.assertTrue(self.fake.last("unbanChatMember")["payload"]["only_if_banned"])
		admin.pin_message(self.c, -100, 7)
		self.assertEqual(self.fake.last("pinChatMessage")["payload"]["disable_notification"], True)
		admin.delete_message(self.c, -100, 7)
		admin.set_chat_title(self.c, -100, " New ")
		self.assertEqual(self.fake.last("setChatTitle")["payload"]["title"], "New")
		admin.set_chat_description(self.c, -100, "d")
		with self.assertRaises(ValueError):
			admin.set_chat_title(self.c, -100, "x" * 129)

	def test_restrict_and_unrestrict(self):
		admin.restrict_member(self.c, -100, 5, {"can_send_messages": True}, until_date=50)
		p = self.fake.last("restrictChatMember")["payload"]
		self.assertTrue(p["permissions"]["can_send_messages"])
		self.assertFalse(p["permissions"]["can_send_photos"])
		self.assertTrue(p["use_independent_chat_permissions"])
		admin.unrestrict_member(self.c, -100, 5)
		self.assertTrue(all(self.fake.last("restrictChatMember")["payload"]["permissions"].values()))
		with self.assertRaises(ValueError):
			admin.restrict_member(self.c, -100, 5, {"can_fly": True})

	def test_promote_explicit_rights(self):
		admin.promote_member(self.c, -100, 5, {"can_delete_messages": True, "can_pin_messages": True})
		p = self.fake.last("promoteChatMember")["payload"]
		self.assertTrue(p["can_delete_messages"] and p["can_pin_messages"])
		self.assertFalse(p["can_promote_members"])
		self.assertEqual(sum(1 for k in admin.ADMIN_RIGHTS if p[k]), 2)
		with self.assertRaises(ValueError):
			admin.promote_member(self.c, -100, 5, {})
		with self.assertRaises(ValueError):
			admin.promote_member(self.c, -100, 5, {"can_everything": True})
		admin.demote_member(self.c, -100, 5)
		self.assertFalse(any(self.fake.last("promoteChatMember")["payload"][k] for k in admin.ADMIN_RIGHTS))

	def test_admins_and_guard_helpers(self):
		self.fake.queue("getChatAdministrators", {"ok": True, "result": [{"status": "creator"}]})
		self.assertEqual(len(admin.get_admins(self.c, "@grp", return_bots=True)), 1)
		p = self.fake.last("getChatAdministrators")["payload"]
		self.assertEqual((p["chat_id"], p["return_bots"]), ("@grp", True))
		admin.send_join_request_web_app(self.c, "q1", "https://x.example/app")
		self.assertEqual(
			self.fake.last("sendChatJoinRequestWebApp")["payload"]["web_app_url"], "https://x.example/app"
		)
		with self.assertRaises(ValueError):
			admin.send_join_request_web_app(self.c, "q1", "http://x")
		with self.assertRaises(ValueError):
			admin.answer_join_request_query(self.c, "q1", "maybe")

	def test_error_classification(self):
		cases = {
			"Bad Request: not enough rights to restrict/unrestrict chat member": "not_enough_rights",
			"Bad Request: CHAT_ADMIN_REQUIRED": "not_enough_rights",
			"Bad Request: chat not found": "chat_not_found",
			"Bad Request: USER_NOT_PARTICIPANT": "user_not_in_chat",
			"Bad Request: can't remove chat owner": "cannot_target_admin",
			"Bad Request: HIDE_REQUESTER_MISSING": "request_gone",
			"Bad Request: message to delete not found": "message_gone",
			"Bad Request: something odd": "bad_request",
		}
		for desc, code in cases.items():
			fake = FakeBotApi()
			fake.queue("banChatMember", fake.error(desc, 400))
			c = TelegramBotClient(TOKEN, http_post=fake.http_post)
			with self.assertRaises(admin.AdminActionError) as cm:
				admin.ban_member(c, -1, 2)
			self.assertEqual(cm.exception.code, code, desc)
		fake = FakeBotApi()
		fake.queue("banChatMember", fake.error("Too Many Requests", 429, retry_after=3))
		with self.assertRaises(admin.AdminActionError) as cm:
			admin.ban_member(TelegramBotClient(TOKEN, http_post=fake.http_post), -1, 2)
		self.assertEqual(cm.exception.code, "flood")
		self.assertIn(
			"administrator right",
			str(
				admin.classify_error(
					"x",
					__import__("huf.ai.gateway_adapters.telegram_client", fromlist=["x"]).TelegramApiError(
						"x", "not enough rights"
					),
				)
			),
		)


class TestServiceMessages(unittest.TestCase):
	def parsed(self, message, chat_type="supergroup"):
		return SimpleNamespace(kind="message", chat_type=chat_type, chat_id="-100", raw={"message": message})

	def test_new_members_welcomes_and_acks(self):
		msg = {"new_chat_members": [{"id": 1}]}
		with mock.patch("huf.ai.telegram_guard.welcome_new_members", return_value=1) as w:
			ack = groups.handle_service_message(GW, None, self.parsed(msg), None)
		self.assertEqual((ack["ignored"], ack["welcomed"]), ("new_chat_members", 1))
		w.assert_called_once()

	def test_welcome_failure_still_acks(self):
		with mock.patch("huf.ai.telegram_guard.welcome_new_members", side_effect=RuntimeError("x")):
			ack = groups.handle_service_message(
				GW, None, self.parsed({"new_chat_members": [{"id": 1}]}), None
			)
		self.assertEqual(ack["ignored"], "new_chat_members")

	def test_left_member_recorded(self):
		ack = groups.handle_service_message(GW, None, self.parsed({"left_chat_member": {"id": 9}}), None)
		self.assertEqual((ack["ignored"], ack["user_id"]), ("left_chat_member", "9"))

	def test_other_messages_and_private_fall_through(self):
		self.assertIsNone(groups.handle_service_message(GW, None, self.parsed({"text": "hi"}), None))
		self.assertIsNone(
			groups.handle_service_message(
				GW, None, self.parsed({"new_chat_members": [{"id": 1}]}, "private"), None
			)
		)


if __name__ == "__main__":
	unittest.main()
