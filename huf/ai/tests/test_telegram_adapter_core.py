"""Adapter composition: inbound normalization, signed callbacks, capabilities and replies."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters import GatewayAttachment, GatewayInboundRequest, GatewayReply
from huf.ai.gateway_adapters.telegram import (
	WEBHOOK_SECRET_HEADER,
	TelegramGatewayAdapter,
	TelegramIgnoredUpdate,
)
from huf.ai.gateway_adapters.telegram_client import TelegramApiError
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi, load_fixture


class TestAdapterCore(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			http_get=self.api.http_get,
			download_attachments=False,
		)

	def request(self, payload):
		return GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})

	def test_capabilities(self):
		caps = self.adapter.capabilities
		self.assertTrue(caps.supports_media_reply)
		for flag in ("supports_reactions", "supports_typing", "supports_buttons", "supports_edit", "supports_voice_reply"):
			self.assertTrue(getattr(caps, flag), flag)

	def test_other_adapters_default_flags_false(self):
		from huf.ai.gateway_adapters.types import GatewayCapabilities

		caps = GatewayCapabilities(frozenset({"webhook"}))
		self.assertFalse(any((caps.supports_reactions, caps.supports_typing, caps.supports_buttons, caps.supports_edit, caps.supports_voice_reply)))

	def test_callback_query_signed_round_trip(self):
		update = load_fixture("callback_query")
		update["callback_query"]["data"] = self.adapter.sign_callback_data("approve:42", chat_id="111")
		event = self.adapter.normalize_inbound(self.request(update))
		self.assertEqual(event.message_text, "approve:42")
		self.assertEqual(event.raw_payload["callback_query"]["id"], "cbq-1")

	def test_callback_query_unsigned_or_tampered_rejected(self):
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request(load_fixture("callback_query")))
		update = load_fixture("callback_query")
		update["callback_query"]["data"] = self.adapter.sign_callback_data("approve:42", chat_id="999")  # other chat
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request(update))

	def test_non_event_updates_raise_ignored_with_typed_update(self):
		with self.assertRaises(TelegramIgnoredUpdate) as ctx:
			self.adapter.normalize_inbound(self.request(load_fixture("my_chat_member_blocked")))
		self.assertTrue(ctx.exception.update.bot_blocked)
		parsed = self.adapter.parse_update(self.request(load_fixture("message_reaction_count")))
		self.assertEqual(parsed.kind, "message_reaction_count")

	def test_parse_update_requires_verification(self):
		bad = GatewayInboundRequest(b"{}", headers={WEBHOOK_SECRET_HEADER: "nope"})
		with self.assertRaises(ValueError):
			self.adapter.parse_update(bad)

	def test_reaction_event(self):
		event = self.adapter.normalize_inbound(self.request(load_fixture("message_reaction_added")))
		self.assertEqual((event.kind, event.reaction_emoji, event.reaction_to), ("reaction", "👍", "55"))

	def test_media_event_carries_attachment_without_download(self):
		event = self.adapter.normalize_inbound(self.request(load_fixture("voice")))
		self.assertEqual([(a.kind, a.file_id, a.file_doc) for a in event.attachments], [("voice", "voice-id", None)])

	def test_animation_not_duplicated_as_document(self):
		event = self.adapter.normalize_inbound(self.request(load_fixture("animation")))
		self.assertEqual([a.kind for a in event.attachments], ["animation"])

	def test_send_reply_splits_long_text(self):
		delivery = self.adapter.send_reply(GatewayReply("999", "y" * 5000, reply_to_provider_message_id="4"))
		calls = self.api.of("sendMessage")
		self.assertEqual(len(calls), 2)
		self.assertEqual(calls[0]["payload"]["reply_to_message_id"], 4)
		self.assertEqual(delivery.provider_message_id, "101")
		self.assertEqual(delivery.provider_response["message_ids"], [101, 102])

	def test_send_reply_with_attachments(self):
		reply = GatewayReply(
			"999", "see this",
			attachments=(GatewayAttachment(file_id="PH", kind="photo"), GatewayAttachment(url="https://x/a.pdf", kind="file")),
		)
		self.adapter.send_reply(reply)
		self.assertEqual([c["method"] for c in self.api.calls], ["sendPhoto", "sendDocument", "sendMessage"])
		self.assertEqual(self.api.calls[1]["payload"]["document"], "https://x/a.pdf")

	def test_send_reply_html_mode_and_fallback(self):
		adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=self.api.http_post, parse_mode="HTML"
		)
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: can't parse entities", 400))
		adapter.send_reply(GatewayReply("999", "**x**"))
		self.assertEqual(self.api.calls[-1]["payload"].get("parse_mode"), None)
		self.assertEqual(self.api.calls[-1]["payload"]["text"], "x")

	def test_blocked_error_surfaces_classification(self):
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		with self.assertRaises(TelegramApiError) as ctx:
			self.adapter.send_reply(GatewayReply("999", "hi"))
		self.assertTrue(ctx.exception.blocked_by_user)

	def test_best_effort_helpers_never_raise(self):
		self.api.queue("sendChatAction", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		self.assertFalse(self.adapter.send_typing(1))
		self.assertTrue(self.adapter.send_typing(1))
		self.api.queue("setMessageReaction", FakeBotApi.error("Bad Request: REACTION_INVALID", 400))
		self.assertFalse(self.adapter.react(1, 2, "x"))
		self.api.queue("answerCallbackQuery", FakeBotApi.error("query is too old", 400))
		self.assertFalse(self.adapter.answer_callback("q"))
