"""Focused fixtures for the Slack outbound (chat.postMessage) adapter."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters import GatewayReply
from huf.ai.gateway_adapters.slack import SlackGatewayAdapter
from huf.ai.gateway_adapters.types import OutboundDelivery


class FakeResponse:
	def __init__(self, body):
		self.body = body
		self.raised = False

	def raise_for_status(self):
		self.raised = True

	def json(self):
		return self.body


class TestSlackGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.response = FakeResponse({"ok": True, "ts": "1700000000.000100", "channel": "C123"})
		self.adapter = SlackGatewayAdapter({"token": "xoxb-test"}, http_post=self._post)

	def _post(self, url, *, headers, json_data, timeout):
		self.calls.append({"url": url, "headers": headers, "json_data": json_data, "timeout": timeout})
		return self.response

	def test_missing_token_raises(self):
		with self.assertRaisesRegex(ValueError, "token"):
			SlackGatewayAdapter({})

	def test_empty_token_raises(self):
		with self.assertRaisesRegex(ValueError, "token"):
			SlackGatewayAdapter({"token": ""})

	def test_send_reply_posts_chat_message_with_bearer_token(self):
		self.adapter.send_reply(GatewayReply("C123", "hi *there*"))
		self.assertEqual(len(self.calls), 1)
		call = self.calls[0]
		self.assertEqual(call["url"], "https://slack.com/api/chat.postMessage")
		self.assertEqual(call["headers"]["Authorization"], "Bearer xoxb-test")
		self.assertEqual(call["headers"]["Content-Type"], "application/json")
		self.assertEqual(call["json_data"], {"channel": "C123", "text": "hi *there*", "mrkdwn": True})
		self.assertEqual(call["timeout"], 10)

	def test_thread_ts_comes_from_thread_id(self):
		self.adapter.send_reply(GatewayReply("C123", "reply", thread_id="1699999999.000001"))
		self.assertEqual(self.calls[0]["json_data"]["thread_ts"], "1699999999.000001")

	def test_thread_ts_falls_back_to_reply_to_provider_message_id(self):
		self.adapter.send_reply(GatewayReply("C123", "reply", reply_to_provider_message_id="1699999998.000002"))
		self.assertEqual(self.calls[0]["json_data"]["thread_ts"], "1699999998.000002")

	def test_thread_id_wins_over_reply_to_provider_message_id(self):
		self.adapter.send_reply(
			GatewayReply(
				"C123",
				"reply",
				thread_id="1699999999.000001",
				reply_to_provider_message_id="1699999998.000002",
			)
		)
		self.assertEqual(self.calls[0]["json_data"]["thread_ts"], "1699999999.000001")

	def test_no_thread_ts_when_neither_thread_id_nor_reply_target_set(self):
		self.adapter.send_reply(GatewayReply("C123", "top level"))
		self.assertNotIn("thread_ts", self.calls[0]["json_data"])

	def test_send_reply_returns_ts_as_provider_message_id(self):
		delivery = self.adapter.send_reply(GatewayReply("C123", "hi"))
		self.assertIsInstance(delivery, OutboundDelivery)
		self.assertEqual(delivery.provider_message_id, "1700000000.000100")
		self.assertTrue(delivery.accepted)
		self.assertEqual(delivery.provider_response["channel"], "C123")

	def test_send_reply_invokes_raise_for_status(self):
		self.adapter.send_reply(GatewayReply("C123", "hi"))
		self.assertTrue(self.response.raised)

	def test_http_error_from_raise_for_status_propagates(self):
		class HttpError(Exception):
			pass

		class FailingResponse(FakeResponse):
			def raise_for_status(self):
				raise HttpError("500 Server Error")

		self.response = FailingResponse({"ok": True, "ts": "1"})
		with self.assertRaisesRegex(HttpError, "500"):
			self.adapter.send_reply(GatewayReply("C123", "hi"))

	def test_ok_false_raises_with_slack_error(self):
		self.response = FakeResponse({"ok": False, "error": "channel_not_found"})
		with self.assertRaisesRegex(ValueError, "channel_not_found"):
			self.adapter.send_reply(GatewayReply("C123", "hi"))

	def test_non_mapping_response_raises(self):
		self.response = FakeResponse(["not", "a", "mapping"])
		with self.assertRaisesRegex(ValueError, "Unknown Slack API error"):
			self.adapter.send_reply(GatewayReply("C123", "hi"))


if __name__ == "__main__":
	unittest.main()
