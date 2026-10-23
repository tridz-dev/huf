"""GROUP-FIX: addressing, supergroup migration, group removal opt-out, duplicate tool+final replies."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai import gateway_service as svc
from huf.ai import telegram_send_scope as scope
from huf.ai.gateway_adapters import telegram_groups as groups
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram_inbound import parse_update

GW = SimpleNamespace(name="gw1", provider="Telegram", mention_required=1, get=lambda k, d=None: d)
AD = SimpleNamespace(_token="777:SECRET")
ME = "TGram_HufBot"


def group_update(text="", entities=None, reply_from=None, uid=1):
	msg = {
		"message_id": 10,
		"date": 1,
		"chat": {"id": -100123, "type": "supergroup", "title": "G"},
		"from": {"id": 42, "is_bot": False, "first_name": "Ann"},
		"text": text,
		"entities": entities or [],
	}
	if reply_from:
		msg["reply_to_message"] = {"message_id": 9, "from": reply_from, "chat": msg["chat"], "text": "hi"}
	return parse_update({"update_id": uid, "message": msg})


def addressed(parsed, username=ME):
	with mock.patch("huf.ai.gateway_adapters.telegram_modes_hooks._bot_username", return_value=username):
		return ing._with_addressing(GW, AD, parsed).mentioned


def ent(kind, text, sub):
	return {"type": kind, "offset": text.index(sub), "length": len(sub)}


class TestAddressing(unittest.TestCase):
	def test_own_mention_and_command_addressed(self):
		t = "hey @TGram_HufBot go"
		self.assertTrue(addressed(group_update(t, [ent("mention", t, "@TGram_HufBot")])))
		t = "/start@TGram_HufBot"
		self.assertTrue(addressed(group_update(t, [ent("bot_command", t, t)])))

	def test_other_bot_mention_and_command_not_addressed(self):
		t = "hey @OtherBot go"
		self.assertFalse(addressed(group_update(t, [ent("mention", t, "@OtherBot")])))
		t = "/start@OtherBot"
		self.assertFalse(addressed(group_update(t, [ent("bot_command", t, t)])))

	def test_text_mention_of_this_bot_only(self):
		t = "hey you"
		mine = {"type": "text_mention", "offset": 4, "length": 3, "user": {"id": 777}}
		other = {**mine, "user": {"id": 888}}
		self.assertTrue(addressed(group_update(t, [mine])))
		self.assertFalse(addressed(group_update(t, [other])))

	def test_reply_to_own_message_addressed_even_without_username(self):
		parsed = group_update("thanks", reply_from={"id": 777, "is_bot": True, "username": ME})
		self.assertTrue(addressed(parsed))
		self.assertTrue(addressed(parsed, username=""))
		other = group_update("thanks", reply_from={"id": 888, "is_bot": True, "username": "OtherBot"})
		self.assertFalse(addressed(other))

	def test_private_chat_untouched(self):
		parsed = parse_update(
			{
				"update_id": 2,
				"message": {
					"message_id": 1,
					"date": 1,
					"chat": {"id": 42, "type": "private"},
					"from": {"id": 42, "is_bot": False, "first_name": "A"},
					"text": "hello",
				},
			}
		)
		self.assertIs(ing._with_addressing(GW, AD, parsed), parsed)

	def test_admission_accepts_reply_to_bot(self):
		gw = SimpleNamespace(
			mention_required=1,
			room_policy="Open",
			room_sender_policy="Open",
			direct_policy="Open",
			provider="Telegram",
		)
		parsed = ing._with_addressing(GW, AD, group_update("ok", reply_from={"id": 777, "is_bot": True}))
		ok, _ = svc._admission(
			gw,
			{"is_room": True, "mentioned": parsed.mentioned, "sender_id": "42", "conversation_id": "-100123"},
		)
		self.assertTrue(ok)


class TestMigration(unittest.TestCase):
	def run_migrate(self, approved):
		old_doc = SimpleNamespace(display_label="G", expires_at=None, approved_by="a@b.c", notes="")
		created = []
		fake_get_doc = mock.Mock(
			side_effect=lambda *a: (
				SimpleNamespace(insert=lambda **k: created.append(1)) if isinstance(a[0], dict) else old_doc
			)
		)
		with (
			mock.patch.object(svc, "_has_access_entry", side_effect=lambda g, t, i: approved.get(i, False)),
			mock.patch.object(svc, "_live_room_entry", return_value={"name": "E1"}),
			mock.patch.object(svc, "_drop_pending_room"),
			mock.patch.object(svc, "_save_entry") as save,
			mock.patch.object(groups.frappe, "get_doc", fake_get_doc),
			mock.patch("frappe.utils.now_datetime", return_value="NOW"),
		):
			moved = groups.migrate_room(GW, "-5", "-1005")
		return moved, created, save, fake_get_doc

	def test_rekeys_approved_room_and_revokes_old(self):
		moved, created, save, get_doc = self.run_migrate({"-5": True})
		self.assertTrue(moved)
		self.assertEqual(len(created), 1)
		doc = get_doc.call_args_list[-1].args[0]
		self.assertEqual((doc["entry_type"], doc["state"], doc["external_id"]), ("Room", "Approved", "-1005"))
		self.assertEqual(save.call_args.args[1]["state"], "Revoked")
		self.assertIn("-1005", save.call_args.args[1]["notes"])

	def test_idempotent_and_unapproved_noop(self):
		for approved in ({"-5": True, "-1005": True}, {}):
			moved, created, save, _ = self.run_migrate(approved)
			self.assertFalse(moved)
			self.assertEqual(created, [])
			save.assert_not_called()

	def test_service_message_both_directions(self):
		for key, chat, pair in (
			("migrate_to_chat_id", "-5", ("-5", "-1005")),
			("migrate_from_chat_id", "-1005", ("-5", "-1005")),
		):
			other = {"migrate_to_chat_id": -1005, "migrate_from_chat_id": -5}[key]
			parsed = SimpleNamespace(
				kind="message",
				chat_type="group",
				chat_id=chat,
				raw={"message": {key: other, "chat": {"id": chat}}},
			)
			with mock.patch.object(groups, "migrate_room", return_value=True) as mig:
				res = groups.handle_service_message(GW, None, parsed, None)
			mig.assert_called_once_with(GW, *pair)
			self.assertEqual(res["ignored"], "migrate_chat")

	def test_loop_guard_prefilter_lets_migration_through(self):
		from huf.ai.gateway_adapters import telegram_modes_hooks as mh

		msg = {"migrate_to_chat_id": -1005, "from": {"id": 9, "is_bot": True}, "chat": {"id": -5}}
		parsed = SimpleNamespace(kind="message", raw={"message": msg}, chat_id="-5", is_room=True)
		self.assertIsNone(mh.prefilter(GW, AD, parsed, None))


class TestRoomOptOut(unittest.TestCase):
	def test_removal_marks_room_entry_not_sender(self):
		with (
			mock.patch.object(svc, "_live_room_entry", return_value={"name": "E1", "state": "Approved"}),
			mock.patch.object(svc, "_drop_pending_room"),
			mock.patch.object(svc, "_save_entry") as save,
			mock.patch.object(svc.frappe, "get_doc") as gd,
		):
			svc._record_room_opt_out(GW, "-100123")
		save.assert_called_once_with("E1", {"state": "Opted out", "previous_state": "Approved"})
		gd.assert_not_called()

	def test_removal_of_unknown_room_creates_nothing(self):
		with (
			mock.patch.object(svc, "_live_room_entry", return_value=None),
			mock.patch.object(svc, "_save_entry") as save,
			mock.patch.object(svc.frappe, "get_doc") as gd,
		):
			svc._record_room_opt_out(GW, "-100123")
		save.assert_not_called()
		gd.assert_not_called()

	def test_readd_restores_previous_state(self):
		with (
			mock.patch.object(
				svc,
				"_live_room_entry",
				return_value={"name": "E1", "state": "Opted out", "previous_state": "Approved"},
			),
			mock.patch.object(svc, "_save_entry") as save,
		):
			svc._record_room_opt_in(GW, "-100123")
		save.assert_called_once_with("E1", {"state": "Approved", "previous_state": ""})

	def test_blocked_send_in_group_opts_out_room_not_sender(self):
		event = SimpleNamespace(
			conversation_id="-100123", sender_id="42", reply_message_id="", name="EV", agent_run=""
		)
		with (
			mock.patch.object(tp, "_svc", return_value=svc),
			mock.patch.object(svc, "_record_room_opt_out") as room,
			mock.patch.object(svc, "_record_opt_out") as sender,
			mock.patch.object(
				tp,
				"classify",
				return_value={"blocked": True, "retryable": False, "operator_text": "blocked", "code": "x"},
			),
			mock.patch.object(svc, "_reply_max_attempts", return_value=3),
			mock.patch.object(svc, "_redact_error_text", return_value="e"),
			mock.patch("frappe.log_error"),
			mock.patch.object(svc, "_set_gateway_error", create=True),
		):
			event.db_set = mock.Mock()
			tp.handle_failure(event, GW, RuntimeError("blocked"), ["x"], 1)
		room.assert_called_once_with(GW, "-100123")
		sender.assert_not_called()


class TestDuplicateReply(unittest.TestCase):
	def test_similarity(self):
		sent = ["Sure, the report is ready and attached below."]
		self.assertTrue(tp.duplicates_tool_reply(sent, "Sure! The report is ready and attached below."))
		# any successful current-chat tool send suppresses the final plain reply
		self.assertTrue(tp.duplicates_tool_reply(sent, "Also, remember the meeting at 5pm tomorrow."))
		self.assertFalse(tp.duplicates_tool_reply([], "anything"))

	def test_scope_records_and_reads(self):
		store = {}
		cache = SimpleNamespace(
			set_value=lambda k, v, expires_in_sec=None: store.__setitem__(k, v),
			get_value=lambda k: store.get(k),
		)
		with mock.patch.object(scope, "_cache", return_value=cache):
			scope.note_current_chat_text("gw1", "run1", "hello there")
			scope.note_current_chat_text("gw1", "run1", "  ")
			self.assertEqual(scope.current_chat_texts("gw1", "run1"), ["hello there"])
			self.assertEqual(scope.current_chat_texts("gw1", "run2"), [])

	def _send(self, tool_texts, final):
		event = SimpleNamespace(name="EV", sender_id="42", db_set=mock.Mock())
		with (
			mock.patch.object(svc, "_reply_finished"),
			mock.patch.object(svc, "is_opted_out", return_value=False),
			mock.patch.object(scope, "current_chat_texts", return_value=tool_texts),
			mock.patch.object(svc, "_attempt_reply_parts", return_value={"status": "Succeeded"}) as att,
		):
			res = svc._send_telegram_reply(event, GW, "run1", final)
		return res, att, event

	def test_final_suppressed_when_tool_already_said_it(self):
		res, att, event = self._send(["Done, I created the task."], "Done! I created the task.")
		att.assert_not_called()
		self.assertTrue(res["reply_suppressed"])
		self.assertEqual(res["status"], "Succeeded")

	def test_final_after_tool_send_is_suppressed(self):
		res, att, _ = self._send(["Done, I created the task."], "By the way the deadline moved to Friday.")
		att.assert_not_called()
		self.assertEqual(res.get("reply_status"), "suppressed")


if __name__ == "__main__":
	unittest.main()
