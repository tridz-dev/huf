# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Tests for GW-30 (attachment schema), GW-31 (Telegram inbound media download),
and GW-32 (WhatsApp/Messenger/Instagram supports_media_reply flag correction).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters.instagram import InstagramGatewayAdapter
from huf.ai.gateway_adapters.messenger import MessengerGatewayAdapter
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.gateway_adapters.types import (
	GatewayAttachment,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
)
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter


class FakeResponse:
	def __init__(self, body=None, content=None):
		self._body = body
		self.content = content

	def json(self):
		return self._body


class TestGatewayAttachmentSchema(unittest.TestCase):
	"""GW-30: NormalizedGatewayEvent/GatewayReply carry an attachments field."""

	def test_normalized_event_defaults_to_no_attachments(self):
		event = NormalizedGatewayEvent(
			provider_event_id="1", sender_id="s", conversation_id="c", message_text="hi"
		)
		self.assertEqual(tuple(event.attachments), ())

	def test_normalized_event_accepts_attachments(self):
		attachment = GatewayAttachment(file_id="file123", mime_type="image/jpeg")
		event = NormalizedGatewayEvent(
			provider_event_id="1",
			sender_id="s",
			conversation_id="c",
			message_text="hi",
			attachments=(attachment,),
		)
		self.assertEqual(event.attachments[0].file_id, "file123")

	def test_gateway_reply_accepts_attachments(self):
		attachment = GatewayAttachment(url="https://example.com/a.png")
		reply = GatewayReply(conversation_id="c", text="hi", attachments=(attachment,))
		self.assertEqual(reply.attachments[0].url, "https://example.com/a.png")

	def test_gateway_attachment_requires_url_or_file_id(self):
		with self.assertRaises(ValueError):
			GatewayAttachment(mime_type="image/jpeg")


class TestTelegramInboundAttachments(unittest.TestCase):
	"""GW-30/GW-31: a synthetic Telegram photo update produces attachments
	carrying the file_id, and (best-effort) downloads the content to a Frappe
	File doctype record.
	"""

	def _photo_update(self):
		return {
			"update_id": 777,
			"message": {
				"message_id": 20,
				"chat": {"id": 999, "type": "private"},
				"from": {"id": 111, "username": "janedoe"},
				"caption": "check this out",
				"photo": [
					{"file_id": "small-file-id", "width": 90, "height": 90},
					{"file_id": "big-file-id", "width": 800, "height": 800, "file_size": 12345},
				],
			},
		}

	def _request(self, payload):
		return GatewayInboundRequest(
			json.dumps(payload).encode(),
			headers={WEBHOOK_SECRET_HEADER: "shh"},
		)

	def test_photo_update_produces_attachment_with_file_id(self):
		adapter = TelegramGatewayAdapter(
			{"token": "123:ABC", "webhook_secret": "shh"},
			download_attachments=False,
		)
		event = adapter.normalize_inbound(self._request(self._photo_update()))
		self.assertEqual(len(event.attachments), 1)
		attachment = event.attachments[0]
		# Telegram sends smallest-first; adapter should pick the largest/last.
		self.assertEqual(attachment.file_id, "big-file-id")
		self.assertEqual(attachment.kind, "photo")
		self.assertEqual(event.message_text, "check this out")

	def test_photo_update_downloads_to_file_doctype_record(self):
		"""GW-31: mocked Telegram getFile + file-server download saves a File doc."""
		get_file_response = FakeResponse({"ok": True, "result": {"file_path": "photos/file_1.jpg"}})
		file_bytes_response = FakeResponse(content=b"\xff\xd8\xff\xe0fakejpegbytes")

		http_post = MagicMock(return_value=get_file_response)
		http_get = MagicMock(return_value=file_bytes_response)

		fake_file_doc = MagicMock()
		fake_file_doc.name = "File-0001"

		adapter = TelegramGatewayAdapter(
			{"token": "123:ABC", "webhook_secret": "shh"},
			http_post=http_post,
			http_get=http_get,
		)

		with patch("frappe.utils.file_manager.save_file", return_value=fake_file_doc, create=True):
			event = adapter.normalize_inbound(self._request(self._photo_update()))

		self.assertEqual(len(event.attachments), 1)
		attachment = event.attachments[0]
		self.assertEqual(attachment.file_id, "big-file-id")
		self.assertEqual(attachment.file_doc, "File-0001")

		# getFile was called with the resolved (largest) file_id.
		get_file_call = http_post.call_args
		self.assertIn("getFile", get_file_call.args[0])
		self.assertEqual(get_file_call.kwargs["json_data"], {"file_id": "big-file-id"})
		# The download URL uses the resolved file_path from getFile's response.
		download_call = http_get.call_args
		self.assertIn("photos/file_1.jpg", download_call.args[0])

	def test_download_failure_degrades_to_file_id_only_attachment(self):
		"""A Telegram/network failure during download must not break normalize_inbound."""

		def _raise(*args, **kwargs):
			raise RuntimeError("network unreachable")

		adapter = TelegramGatewayAdapter(
			{"token": "123:ABC", "webhook_secret": "shh"},
			http_post=_raise,
		)
		event = adapter.normalize_inbound(self._request(self._photo_update()))
		self.assertEqual(len(event.attachments), 1)
		self.assertEqual(event.attachments[0].file_id, "big-file-id")
		self.assertIsNone(event.attachments[0].file_doc)

	def test_text_only_update_has_no_attachments(self):
		adapter = TelegramGatewayAdapter(
			{"token": "123:ABC", "webhook_secret": "shh"},
			download_attachments=False,
		)
		payload = {
			"update_id": 1,
			"message": {
				"message_id": 1,
				"chat": {"id": 1, "type": "private"},
				"from": {"id": 1},
				"text": "just text",
			},
		}
		event = adapter.normalize_inbound(self._request(payload))
		self.assertEqual(event.attachments, ())


class TestGatewayServicePromptAttachmentNote(unittest.TestCase):
	"""GW-30: process_gateway_event's prompt reflects attachment presence."""

	def test_describe_attachments_detects_telegram_photo(self):
		from huf.ai.gateway_service import _describe_attachments

		raw_payload = {
			"update_id": 1,
			"message": {"chat": {"id": 1}, "from": {"id": 1}, "photo": [{"file_id": "f1"}]},
		}
		note = _describe_attachments(raw_payload)
		self.assertIn("photo", note)
		self.assertTrue(note.startswith("[Attachment"))

	def test_describe_attachments_empty_for_text_only_payload(self):
		from huf.ai.gateway_service import _describe_attachments

		raw_payload = {"message": {"chat": {"id": 1}, "from": {"id": 1}, "text": "hi"}}
		self.assertEqual(_describe_attachments(raw_payload), "")

	def test_describe_attachments_detects_whatsapp_image(self):
		from huf.ai.gateway_service import _describe_attachments

		raw_payload = {
			"entry": [
				{
					"changes": [
						{"value": {"messages": [{"type": "image", "image": {"id": "media1"}}]}}
					]
				}
			]
		}
		note = _describe_attachments(raw_payload)
		self.assertIn("image", note)


class TestSupportsMediaReplyFlagAccuracy(unittest.TestCase):
	"""GW-32: supports_media_reply must match send_reply's real (text-only) behavior."""

	def test_whatsapp_flag_is_false(self):
		self.assertFalse(WhatsAppGatewayAdapter.capabilities.supports_media_reply)

	def test_messenger_flag_is_false(self):
		self.assertFalse(MessengerGatewayAdapter.capabilities.supports_media_reply)

	def test_instagram_flag_is_false(self):
		self.assertFalse(InstagramGatewayAdapter.capabilities.supports_media_reply)


if __name__ == "__main__":
	unittest.main()
