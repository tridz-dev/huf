"""Unit tests for Discord, Email, SMS, Google Chat, and Teams Gateway Adapters."""

import unittest
from unittest.mock import MagicMock

from huf.ai.gateway_adapters.discord import DiscordGatewayAdapter
from huf.ai.gateway_adapters.email import EmailGatewayAdapter
from huf.ai.gateway_adapters.sms import SMSGatewayAdapter
from huf.ai.gateway_adapters.google_chat import GoogleChatGatewayAdapter
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply


class TestAllGatewayAdapters(unittest.TestCase):
	def test_discord_adapter_outbound(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"id": "msg_12345"}

		adapter = DiscordGatewayAdapter(
			{"bot_token": "test_bot_token", "public_key": "a" * 64},
			http_post=mock_post,
		)

		reply = GatewayReply(
			conversation_id="channel_99",
			text="Hello Discord",
			reply_to_provider_message_id=None,
		)

		delivery = adapter.send_reply(reply)
		self.assertEqual(delivery.provider_message_id, "msg_12345")
		mock_post.assert_called_once()

	def test_email_adapter_inbound_and_outbound(self):
		import frappe

		original_sendmail = getattr(frappe, "sendmail", None)
		mock_sendmail = MagicMock()
		frappe.sendmail = mock_sendmail

		try:
			adapter = EmailGatewayAdapter({"webhook_secret": "mysecret", "sender_email": "bot@example.com"})

			req = GatewayInboundRequest(
				body=b'{"from": "user@example.com", "to": "bot@example.com", "body": "Need help", "message_id": "email_1"}',
				headers={"X-Webhook-Secret": "mysecret"},
				query={},
				method="POST",
			)

			self.assertTrue(adapter.verify_inbound(req))
			event = adapter.normalize_inbound(req)
			self.assertEqual(event.sender_id, "user@example.com")
			self.assertEqual(event.message_text, "Need help")

			reply = GatewayReply(
				conversation_id="user@example.com",
				text="Got your email",
			)
			delivery = adapter.send_reply(reply)
			self.assertEqual(delivery.provider_response["status"], "sent")
			mock_sendmail.assert_called_once()
		finally:
			if original_sendmail:
				frappe.sendmail = original_sendmail

	def test_sms_adapter_outbound(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"sid": "SM12345"}

		adapter = SMSGatewayAdapter(
			{
				"account_sid": "AC123",
				"auth_token": "secret",
				"from_number": "+1234567890",
			},
			http_post=mock_post,
		)

		req = GatewayInboundRequest(
			body=b"From=%2B1987654321&Body=Hello+SMS&MessageSid=SM999",
			headers={},
			query={},
			method="POST",
		)
		event = adapter.normalize_inbound(req)
		self.assertEqual(event.sender_id, "+1987654321")
		self.assertEqual(event.message_text, "Hello SMS")

		reply = GatewayReply(
			conversation_id="+1987654321",
			text="SMS Reply",
		)
		delivery = adapter.send_reply(reply)
		self.assertEqual(delivery.provider_message_id, "SM12345")

	def test_google_chat_adapter(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"name": "spaces/1/messages/100"}

		adapter = GoogleChatGatewayAdapter(
			{"webhook_url": "https://chat.googleapis.com/v1/spaces/1/messages?key=abc"},
			http_post=mock_post,
		)

		req = GatewayInboundRequest(
			body=b'{"space": {"name": "spaces/1"}, "user": {"displayName": "Alice"}, "message": {"text": "Hi Chat", "name": "msg1"}}',
			headers={},
			query={},
			method="POST",
		)

		event = adapter.normalize_inbound(req)
		self.assertEqual(event.conversation_id, "spaces/1")
		self.assertEqual(event.message_text, "Hi Chat")

		reply = GatewayReply(
			conversation_id="spaces/1",
			text="Chat Reply",
		)
		delivery = adapter.send_reply(reply)
		self.assertEqual(delivery.provider_message_id, "spaces/1/messages/100")

	def test_teams_adapter(self):
		mock_post = MagicMock()
		mock_post.return_value.json.return_value = {"id": "act_999"}

		adapter = TeamsGatewayAdapter(
			{"app_id": "appid", "app_password": "apppass"},
			http_post=mock_post,
		)

		req = GatewayInboundRequest(
			body=b'{"id": "act_1", "from": {"id": "user1"}, "conversation": {"id": "conv1"}, "text": "Hi Teams"}',
			headers={"Authorization": "Bearer token"},
			query={},
			method="POST",
		)

		event = adapter.normalize_inbound(req)
		self.assertEqual(event.sender_id, "user1")
		self.assertEqual(event.message_text, "Hi Teams")

		reply = GatewayReply(
			conversation_id="conv1",
			text="Teams Reply",
		)
		delivery = adapter.send_reply(reply)
		self.assertEqual(delivery.provider_message_id, "act_999")
