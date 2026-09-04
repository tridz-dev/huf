"""Unit tests for Discord, Email, SMS, Google Chat, and Teams Gateway Adapters."""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters.email import EmailGatewayAdapter
from huf.ai.gateway_adapters.google_chat import GoogleChatGatewayAdapter
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply


class TestAllGatewayAdapters(unittest.TestCase):

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


	def test_email_adapter_wrong_secret_rejected(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={"X-Webhook-Secret": "wrong-secret"},
			query={},
			method="POST",
		)

		self.assertFalse(adapter.verify_inbound(req))

	def test_email_adapter_missing_token_rejected(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={},
			query={},
			method="POST",
		)

		self.assertFalse(adapter.verify_inbound(req))

	def test_email_adapter_uses_hmac_compare_digest(self):
		adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

		req = GatewayInboundRequest(
			body=b"{}",
			headers={"X-Webhook-Secret": "mysecret"},
			query={},
			method="POST",
		)

		with patch(
			"huf.ai.gateway_adapters.email.hmac.compare_digest", return_value=True
		) as mock_compare:
			self.assertTrue(adapter.verify_inbound(req))
			mock_compare.assert_called_once_with("mysecret", "mysecret")


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
