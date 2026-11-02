"""WhatsApp and Telegram extras a flow trigger sees: structured fields, names equal to the registry payload_fields."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.flow.gateways.registry import get_gateway_trigger_spec
from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters.trigger_extras import telegram_fields as tf
from huf.ai.gateway_adapters.trigger_extras import whatsapp_fields as wf
from huf.ai.tests.telegram_fakes import load_fixture


def _names(node_type):
	return {f["path"].split(".", 1)[1] for f in get_gateway_trigger_spec(None, node_type)["payload_fields"]}


def _wa(message, **raw):
	return {"message": message, "contact_name": raw.pop("contact_name", "Asha"), **raw}


class TestWhatsAppExtras(unittest.TestCase):
	def test_button_reply(self):
		out = wf.message_extras(_wa({"type": "interactive", "interactive": {"button_reply": {"id": "yes", "title": "Yes please"}}}), "15550001111")
		self.assertEqual((out["button_id"], out["button_title"], out["button_payload"]), ("yes", "Yes please", "yes"))

	def test_template_quick_reply_payload(self):
		out = wf.message_extras(_wa({"type": "button", "button": {"payload": "sol:refund|7", "text": "Refund"}}), "1")
		self.assertEqual((out["button_payload"], out["button_title"]), ("sol:refund|7", "Refund"))

	def test_referral_and_tag(self):
		ref = {"source_id": "ad-9", "source_url": "https://fb.me/x", "source_type": "ad", "headline": "Sale", "body": "50%", "ctwa_clid": "c1", "media_url": "dropped"}
		out = wf.message_extras(_wa({"type": "text", "text": {"body": "hi"}, "referral": ref}), "1")
		self.assertEqual(set(out["referral"]), {"source_id", "source_url", "source_type", "headline", "body", "ctwa_clid"})
		self.assertEqual(out["referral_tag"], "ad-9")

	def test_forwarded_location_contacts_order(self):
		msg = {
			"type": "location", "context": {"forwarded": True},
			"location": {"latitude": 12.5, "longitude": 77.1, "name": "Shop", "address": "1 Main St"},
			"contacts": [{"name": {"formatted_name": "Ravi"}, "phones": [{"phone": "+91 99999 11111"}]}],
			"order": {"text": "gift wrap", "product_items": [{"product_retailer_id": "sku1", "quantity": 2, "item_price": 10, "currency": "USD"}]},
		}
		out = wf.message_extras(_wa(msg), "1")
		self.assertTrue(out["forwarded"])
		self.assertEqual(out["location"], {"lat": 12.5, "lng": 77.1, "name": "Shop", "address": "1 Main St"})
		self.assertEqual(out["contacts"], [{"name": "Ravi", "phones": ["+91 99999 11111"]}])
		self.assertEqual((out["order"]["total"], out["order"]["note"], len(out["order"]["items"])), (20.0, "gift wrap", 1))

	def test_name_and_kind(self):
		out = wf.message_extras(_wa({"type": "text", "text": {"body": "hi"}}, kind="reaction"), "1")
		self.assertEqual((out["contact_name"], out["display_name"], out["kind"], out["is_room"]), ("Asha", "Asha", "reaction", False))

	def test_hours_since_previous(self):
		from datetime import datetime

		rows = [{"received_at": datetime(2026, 1, 1, 9, 0)}]
		with mock.patch("frappe.utils.get_datetime", side_effect=lambda v: v):
			hours = wf.hours_since_previous("GW", "1", datetime(2026, 1, 1, 12, 30), db_get_all=lambda *a, **k: rows)
		self.assertEqual(hours, 3.5)
		self.assertIsNone(wf.hours_since_previous("GW", "1", datetime(2026, 1, 1), db_get_all=lambda *a, **k: []))

	def test_keys_are_registry_names(self):
		msg = {"type": "location", "location": {"latitude": 1, "longitude": 2}, "referral": {"source_id": "a"}, "context": {"forwarded": True},
			"interactive": {"button_reply": {"id": "i", "title": "t"}}, "contacts": [{"name": {"formatted_name": "x"}}], "order": {"product_items": []}}
		out = wf.message_extras(_wa(msg), "1")
		self.assertLessEqual(set(out), _names("trigger.whatsapp"))

	def test_hook_returns_extras_and_wa_id(self):
		hook = provider_hooks.get("WhatsApp", "extra_event_fields")
		ev = SimpleNamespace(raw_payload=json.dumps(_wa({"type": "text", "text": {"body": "hi"}})), get=lambda k, d=None: None)
		with mock.patch.object(wf, "hours_since_previous", return_value=2.0):
			out = hook(ev, SimpleNamespace(name="GW"), "15550001111")
		self.assertEqual((out["wa_id"], out["hours_since_last_customer_message"], out["contact_name"]), ("15550001111", 2.0, "Asha"))


def _tg_event(raw):
	return SimpleNamespace(raw_payload=raw, conversation_id="111", get=lambda k, d=None: raw)


class TestTelegramExtras(unittest.TestCase):
	def test_command_with_bot_suffix(self):
		self.assertEqual(tf.split_command("/help@huf_bot now please"), ("help", "now please"))
		self.assertEqual(tf.split_command("/Start"), ("start", ""))
		self.assertEqual(tf.split_command("hello /start"), ("", ""))

	def test_command_update(self):
		raw = load_fixture("message_bot_command")
		raw["telegram_meta"] = {"chat_type": "supergroup", "is_room": True}
		out = ing.extra_fields(_tg_event(raw), SimpleNamespace(), "111")
		self.assertEqual((out["command"], out["command_args"], out["username"], out["display_name"]), ("help", "now", "janedoe", "Jane"))
		self.assertTrue(out["is_room"])
		self.assertEqual(out["kind"], "message")

	def test_topic_edit_channel_and_bot(self):
		raw = load_fixture("forum_topic_message")
		raw["telegram_meta"] = {"message_thread_id": "900", "is_bot": True}
		out = ing.extra_fields(_tg_event(raw), SimpleNamespace(), "111")
		self.assertEqual((out["topic_id"], out["sender_is_bot"], out["edited"], out["is_channel_post"]), ("900", True, False, False))
		self.assertTrue(ing.extra_fields(_tg_event(load_fixture("edited_message")), SimpleNamespace(), "1")["edited"])
		self.assertTrue(ing.extra_fields(_tg_event(load_fixture("channel_post")), SimpleNamespace(), "1")["is_channel_post"])

	def test_web_app_data(self):
		raw = {"message": {"chat": {"id": 1, "type": "private"}, "from": {"id": 1}, "web_app_data": {"data": "{\"a\":1}", "button_text": "Open"}}}
		out = tf.extra_fields(_tg_event(raw), SimpleNamespace(), "1")
		self.assertEqual(out["web_app_data"], {"data": "{\"a\":1}", "button_text": "Open"})

	def test_keys_are_registry_names(self):
		allowed = _names("trigger.telegram")
		for name in ("message_bot_command", "forum_topic_message", "edited_message", "channel_post", "callback_query"):
			raw = load_fixture(name)
			raw["telegram_meta"] = {"chat_type": "private", "callback_data": "x", "callback_query_id": "q", "business_connection_id": "b", "is_room": True, "mentioned": True}
			self.assertLessEqual(set(tf.extra_fields(_tg_event(raw), SimpleNamespace(), "1")), allowed, name)

	def test_callback_kind(self):
		raw = load_fixture("callback_query")
		raw["telegram_meta"] = {"callback_data": "approve:42", "callback_query_id": "q1"}
		out = tf.extra_fields(_tg_event(raw), SimpleNamespace(), "111")
		self.assertEqual((out["kind"], out["callback_data"]), ("callback", "approve:42"))
		self.assertNotIn("command", out)


class TestCallbackShowsRealData(unittest.TestCase):
	"""The synthesized text of a Huf button swaps in the label; the flow still sees the id the author set."""

	def _run(self, data):
		from huf.ai.tests.test_telegram_ingest import adapter, run

		ad = adapter()
		payload = load_fixture("callback_query")
		payload["callback_query"]["data"] = ad.sign_callback_data(data, "111")
		with (
			mock.patch("huf.ai.gateway_adapters.telegram_buttons.time.time", return_value=1760000100.0),
			mock.patch("huf.ai.gateway_adapters.telegram_buttons._claim", return_value=True),
		):
			return run(payload, ad)[1]

	def test_foreign_payload(self):
		m = self._run("approve:42")
		self.assertEqual(m.call_args.kwargs["raw_payload"]["telegram_meta"]["callback_data"], "approve:42")

	def test_huf_button_keeps_id_not_label_text(self):
		from huf.ai.gateway_adapters.telegram_buttons import encode_payload

		m = self._run(encode_payload("refund_yes", once=False, edit=False))
		meta = m.call_args.kwargs["raw_payload"]["telegram_meta"]
		self.assertEqual(meta["callback_data"], "refund_yes")
		self.assertNotEqual(m.call_args.args[2]["message_text"], "refund_yes")  # agent text routing unchanged


if __name__ == "__main__":
	unittest.main()
