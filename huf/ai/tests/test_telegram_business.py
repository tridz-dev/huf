"""Telegram Business (Secretary) mode: connection store, policy matrix, loop prevention, drafts."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import GatewayInboundRequest
from huf.ai.gateway_adapters import telegram_business as biz
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi, clear_update_dedup, isolate_update_dedup

GW = SimpleNamespace(name="gw1", provider="Telegram", mention_required=0)
OWNER = 900
CUST = 111


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, key):
		return self.d.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value


def connection(enabled=True, rights=None, cid="bc-1"):
	conn = {
		"id": cid,
		"user": {"id": OWNER, "is_bot": False, "first_name": "Owner"},
		"user_chat_id": OWNER,
		"date": 1760000000,
		"is_enabled": enabled,
	}
	if rights is not None:
		conn["rights"] = rights
	return {"update_id": 1, "business_connection": conn}


def message(kind="business_message", sender=CUST, extra=None, text="hello", cid="bc-1"):
	msg = {
		"message_id": 7,
		"business_connection_id": cid,
		"from": {"id": sender, "is_bot": False, "first_name": "X"},
		"chat": {"id": CUST, "type": "private"},
		"date": 1760000000,
		"text": text,
	}
	msg.update(extra or {})
	return {"update_id": 2, kind: msg}


DELETED = {
	"update_id": 3,
	"deleted_business_messages": {
		"business_connection_id": "bc-1",
		"chat": {"id": CUST, "type": "private"},
		"message_ids": [7, 8],
	},
}


class Base(unittest.TestCase):
	def setUp(self):
		for kind, fn in (
			("business_connection", biz.handle_business_connection),
			("business_message", biz.handle_business_message),
			("edited_business_message", biz.handle_business_message),
			("deleted_business_messages", biz.handle_deleted_business_messages),
		):
			ing.register_update_handler(kind, fn)
		isolate_update_dedup(self)
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			download_attachments=False,
		)
		self.cache = FakeCache()
		for p in (
			mock.patch.object(biz, "_cache", return_value=self.cache),
			mock.patch.object(biz.frappe, "logger"),
		):
			p.start()
			self.addCleanup(p.stop)
		self._saved = (biz._POLICY, biz._DRAFT_PRODUCER, list(biz._OBSERVERS))
		self.addCleanup(self._restore)

	def _restore(self):
		biz._POLICY, biz._DRAFT_PRODUCER = self._saved[:2]
		biz._OBSERVERS[:] = self._saved[2]

	def feed(self, payload):
		clear_update_dedup()  # fixtures reuse fixed update ids; a site cache would otherwise ack them as duplicates
		req = GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})
		with mock.patch("huf.ai.gateway_service.ingest_gateway_event") as ingest:
			result = ing.handle_update(GW, self.adapter, req)
		ingest.assert_not_called()
		return result

	def sends(self):
		return self.api.of("sendMessage")


class TestConnection(Base):
	def test_handlers_registered(self):
		import huf.ai.gateway_adapters.telegram_hooks  # noqa: F401

		for k in biz.BUSINESS_KINDS:
			self.assertIn(k, ing._UPDATE_HANDLERS)

	def test_connection_stored(self):
		r = self.feed(connection(rights={"can_reply": True}))
		self.assertTrue(r["enabled"])
		c = biz.get_connection("bc-1")
		self.assertEqual(
			(c["owner_id"], c["user_chat_id"], c["rights"]), (str(OWNER), str(OWNER), {"can_reply": True})
		)

	def test_disabled_and_missing_rights(self):
		self.feed(connection(enabled=False))
		self.assertFalse(biz.get_connection("bc-1")["is_enabled"])
		self.feed(connection())
		self.assertFalse(biz.can(biz.get_connection("bc-1"), "can_reply"))

	def test_unknown_connection_refresh_via_api(self):
		self.api.queue(
			"getBusinessConnection",
			{"ok": True, "result": connection(rights={"can_reply": True})["business_connection"]},
		)
		self.assertEqual(biz.get_connection("bc-1", self.adapter)["owner_id"], str(OWNER))
		self.assertEqual(self.api.last("getBusinessConnection")["payload"]["business_connection_id"], "bc-1")


class TestPolicy(Base):
	def setUp(self):
		super().setUp()
		self.feed(connection(rights={"can_reply": True}))

	def test_default_observe_never_replies(self):
		r = self.feed(message())
		self.assertEqual(r["policy"], "observe")
		self.assertEqual(self.api.calls, [])
		self.assertEqual(biz.observations("gw1")[-1]["event"], "message")

	def test_ignore(self):
		biz.register_business_policy(lambda c: "ignore")
		self.assertEqual(self.feed(message())["policy"], "ignore")
		self.assertEqual([o for o in biz.observations("gw1") if o["event"] == "message"], [])

	def test_invalid_and_raising_policy_observe(self):
		biz.register_business_policy(lambda c: "yolo")
		self.assertEqual(self.feed(message())["policy"], "observe")
		biz.register_business_policy(lambda c: 1 / 0)
		self.assertEqual(self.feed(message())["policy"], "observe")

	def test_reply_downgraded_without_right(self):
		self.feed(connection())  # rights missing
		biz.register_business_policy(lambda c: "reply")
		r = self.feed(message())
		self.assertEqual(r["policy"], "observe")
		self.assertEqual(biz.observations("gw1")[-1]["note"], "no_reply_right")

	def test_reply_disabled_connection(self):
		self.feed(connection(enabled=False, rights={"can_reply": True}))
		biz.register_business_policy(lambda c: "reply")
		self.assertEqual(self.feed(message())["policy"], "observe")

	def test_reply_signals_agent_run_but_sends_nothing(self):
		biz.register_business_policy(lambda c: "reply")
		r = self.feed(message())
		self.assertTrue(r["needs_agent_run"])
		self.assertEqual(self.api.calls, [])

	def test_draft_without_producer_observes(self):
		biz.register_business_policy(lambda c: "draft")
		self.assertEqual(self.feed(message())["policy"], "observe")

	def test_edited_never_drafts(self):
		biz.register_business_policy(lambda c: "draft")
		biz.register_draft_producer(lambda c: "x")
		self.assertEqual(self.feed(message("edited_business_message"))["policy"], "observe")
		self.assertEqual(self.api.calls, [])

	def test_deleted_recorded(self):
		self.feed(DELETED)
		self.assertEqual(biz.observations("gw1")[-1]["message_ids"], [7, 8])


class TestLoopPrevention(Base):
	def setUp(self):
		super().setUp()
		self.feed(connection(rights={"can_reply": True}))
		biz.register_business_policy(lambda c: "reply")
		biz.register_draft_producer(lambda c: "draft")

	def test_owner_outgoing_ignored(self):
		r = self.feed(message(sender=OWNER))
		self.assertEqual(r["policy"], "ignore")
		self.assertEqual(biz.observations("gw1")[-1]["event"], "outgoing")
		self.assertNotIn("needs_agent_run", r)

	def test_sender_business_bot_ignored(self):
		r = self.feed(message(extra={"sender_business_bot": {"id": 5, "is_bot": True, "first_name": "B"}}))
		self.assertEqual(r["policy"], "ignore")

	def test_bot_sender_ignored(self):
		p = message()
		p["business_message"]["from"]["is_bot"] = True
		self.assertEqual(self.feed(p)["policy"], "ignore")

	def test_unknown_connection_observe_only(self):
		self.api.queue("getBusinessConnection", self.api.error("not found", 400))
		r = self.feed(message(cid="bc-x"))
		self.assertEqual(r["policy"], "observe")
		self.assertEqual(self.sends(), [])


class TestSend(Base):
	def setUp(self):
		super().setUp()
		self.feed(connection(rights={"can_reply": True, "can_read_messages": True}))

	def test_reply_as_business_payload(self):
		biz.reply_as_business("bc-1", CUST, "hi", sender=self.adapter.sender, reply_to=7)
		p = self.api.last("sendMessage")["payload"]
		self.assertEqual((p["business_connection_id"], p["chat_id"], p["text"]), ("bc-1", CUST, "hi"))
		self.assertEqual(p["reply_parameters"]["message_id"], 7)

	def test_blocked_cases(self):
		for conn, reason in (
			(connection(), "no_reply_right"),
			(connection(enabled=False, rights={"can_reply": True}), "connection_disabled"),
		):
			self.feed(conn)
			with self.assertRaises(biz.BusinessReplyBlocked) as cm:
				biz.reply_as_business("bc-1", CUST, "hi", sender=self.adapter.sender)
			self.assertEqual(cm.exception.reason, reason)
		with self.assertRaises(biz.BusinessReplyBlocked):
			biz.reply_as_business("nope", CUST, "hi", sender=self.adapter.sender)
		self.assertEqual(self.sends(), [])

	def test_read_and_delete_rights(self):
		biz.mark_read("bc-1", CUST, 7, sender=self.adapter.sender)
		self.assertEqual(self.api.last("readBusinessMessage")["payload"]["business_connection_id"], "bc-1")
		with self.assertRaises(biz.BusinessReplyBlocked):
			biz.delete_messages("bc-1", [7], sender=self.adapter.sender)


class TestDraft(Base):
	def setUp(self):
		super().setUp()
		self.feed(connection(rights={"can_reply": True}))
		biz.register_business_policy(lambda c: "draft")
		biz.register_draft_producer(lambda c: "Sure, 3pm works.")
		r = self.feed(message())
		self.draft_id = r["draft_id"]

	def _cb(self, action, sender=OWNER):
		data = self.adapter.sign_callback_data(f"bz:{action}:{self.draft_id}", OWNER)
		payload = self.adapter.verify_callback_data(data, OWNER)
		return biz.handle_draft_callback(self.adapter, SimpleNamespace(sender_id=str(sender)), payload)

	def test_draft_goes_to_owner_only(self):
		(call,) = self.sends()
		self.assertEqual(call["payload"]["chat_id"], str(OWNER))
		self.assertNotIn("business_connection_id", call["payload"])
		row = call["payload"]["reply_markup"]["inline_keyboard"][0]
		self.assertEqual([b["text"] for b in row], ["Approve", "Edit", "Reject"])

	def test_approve_sends_as_business_once(self):
		self.assertEqual(self._cb("a")["result"], "approved")
		sent = self.sends()[-1]["payload"]
		self.assertEqual(
			(sent["business_connection_id"], sent["chat_id"], sent["text"]),
			("bc-1", str(CUST), "Sure, 3pm works."),
		)
		n = len(self.sends())
		self.assertEqual(self._cb("a")["result"], "stale")
		self.assertEqual(len(self.sends()), n)

	def test_reject_sends_nothing(self):
		n = len(self.sends())
		self.assertEqual(self._cb("r")["result"], "rejected")
		self.assertEqual(self._cb("a")["result"], "stale")
		self.assertEqual(len(self.sends()), n)

	def test_non_owner_forbidden(self):
		n = len(self.sends())
		self.assertEqual(self._cb("a", sender=CUST)["result"], "forbidden")
		self.assertEqual(len(self.sends()), n)

	def test_edit_then_submit(self):
		self.assertEqual(self._cb("e")["result"], "editing")
		self.assertEqual(biz.submit_edit(self.adapter, self.draft_id, CUST, "x")["result"], "forbidden")
		self.assertEqual(
			biz.submit_edit(self.adapter, self.draft_id, OWNER, "4pm instead")["result"], "approved"
		)
		self.assertEqual(self.sends()[-1]["payload"]["text"], "4pm instead")

	def test_approve_after_right_revoked_blocked(self):
		self.feed(connection())
		self.assertEqual(self._cb("a")["result"], "blocked")
		self.assertEqual(biz.get_draft(self.draft_id)["status"], "pending")

	def test_foreign_callback_ignored(self):
		self.assertIsNone(biz.handle_draft_callback(self.adapter, SimpleNamespace(sender_id="1"), "other:x"))


class TestSendFailures(Base):
	def setUp(self):
		super().setUp()
		self.feed(connection(rights={"can_reply": True}))
		biz.register_business_policy(lambda c: "draft")
		biz.register_draft_producer(lambda c: "Sure, 3pm works.")
		self.draft_id = self.feed(message())["draft_id"]

	def cb(self, action, cqid="cq1"):
		data = self.adapter.sign_callback_data(f"bz:{action}:{self.draft_id}", OWNER)
		payload = self.adapter.verify_callback_data(data, OWNER)
		parsed = SimpleNamespace(sender_id=str(OWNER), callback_query_id=cqid, message_id="101")
		return biz.handle_draft_callback(self.adapter, parsed, payload)

	def status(self):
		return biz.get_draft(self.draft_id)["status"]

	def fail_next(self, description, code):
		self.api.queue("sendMessage", FakeBotApi.error(description, code))

	def owner_texts(self):
		return [c["payload"]["text"] for c in self.sends() if str(c["payload"]["chat_id"]) == str(OWNER)]

	def toast(self):
		return self.api.last("answerCallbackQuery")["payload"]["text"]

	def test_permanent_error_on_approve_marks_failed_and_notifies(self):
		self.fail_next("Bad Request: business connection not found", 400)
		out = self.cb("a")  # must not raise
		self.assertEqual(out["result"], "failed")
		self.assertEqual(self.status(), "failed")
		self.assertTrue(self.owner_texts()[-1].startswith("Could not send: "))
		self.assertNotIn(TOKEN, " ".join(self.owner_texts()))
		self.assertIn("Could not send", self.toast())

	def test_transient_error_on_approve_resets_pending_and_retry_works(self):
		self.fail_next("Too Many Requests: retry after 5", 429)
		out = self.cb("a")
		self.assertEqual(out["result"], "retry")
		self.assertEqual(self.status(), "pending")
		self.assertIn("Could not send", self.owner_texts()[-1])
		self.assertEqual(self.cb("a")["result"], "approved")
		self.assertEqual(self.status(), "sent")

	def test_unexpected_exception_does_not_propagate(self):
		with mock.patch.object(biz, "reply_as_business", side_effect=RuntimeError("boom")):
			out = self.cb("a")
		self.assertEqual(out["result"], "retry")
		self.assertEqual(self.status(), "pending")

	def test_second_approve_on_failed_cannot_retry(self):
		self.fail_next("Bad Request: business connection not found", 400)
		self.cb("a")
		n = len(self.sends())
		self.assertEqual(self.cb("a", cqid="cq2")["result"], "failed")
		self.assertEqual(len(self.sends()), n)
		self.assertIn("can't be retried", self.toast())

	def test_edit_send_failure_keeps_editing_and_notifies(self):
		self.cb("e")
		self.fail_next("Bad Gateway", 502)
		out = biz.submit_edit(self.adapter, self.draft_id, OWNER, "4pm")
		self.assertEqual(out["result"], "retry")
		self.assertEqual(self.status(), "editing")
		self.assertIn("Could not send", self.owner_texts()[-1])
		self.assertEqual(biz.submit_edit(self.adapter, self.draft_id, OWNER, "4pm")["result"], "approved")

	def test_edit_send_permanent_failure_marks_failed(self):
		self.cb("e")
		self.fail_next("Bad Request: business connection not found", 400)
		self.assertEqual(biz.submit_edit(self.adapter, self.draft_id, OWNER, "4pm")["result"], "failed")
		self.assertEqual(self.status(), "failed")

	def test_approve_gives_toast_and_removes_buttons(self):
		self.assertEqual(self.cb("a")["result"], "approved")
		self.assertEqual(self.toast(), "Sent")
		edit = self.api.last("editMessageText")["payload"]
		self.assertEqual(edit["reply_markup"], {"inline_keyboard": []})
		self.assertIn("Sent.", edit["text"])

	def test_reject_and_edit_toasts(self):
		self.cb("e")
		self.assertEqual(self.toast(), "Send your replacement text")
		self.cb("r", cqid="cq3")
		self.assertEqual(self.toast(), "Rejected")
		self.assertIn("Rejected.", self.api.last("editMessageText")["payload"]["text"])

	def test_ack_for_queued_draft(self):
		biz.register_draft_producer(lambda c: biz.DRAFT_QUEUED)
		r = self.feed(message(text="again"))
		self.assertIn("draft queued", json.dumps(r))
