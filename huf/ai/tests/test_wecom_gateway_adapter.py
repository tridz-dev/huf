"""Cryptographic fixtures for the WeCom self-built-app adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply, assert_adapter_conforms
from huf.ai.gateway_adapters.wecom import WECOM_GET_TOKEN_URL, WECOM_SEND_MESSAGE_URL, WeComGatewayAdapter


class FakeResponse:
	def __init__(self, body):
		self.body = body

	def raise_for_status(self):
		return None

	def json(self):
		return self.body


class TestWeComGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.key = b"0123456789abcdef0123456789abcdef"
		self.encoding_key = base64.b64encode(self.key).decode().rstrip("=")
		self.get_calls = []
		self.post_calls = []
		self.now = 1000.0
		self.adapter = WeComGatewayAdapter(
			{
				"corp_id": "wx-corp",
				"agent_id": "100001",
				"corp_secret": "corp-secret",
				"callback_token": "callback-token",
				"encoding_aes_key": self.encoding_key,
			},
			http_get=self._get,
			http_post=self._post,
			clock=lambda: self.now,
		)

	def _get(self, url, *, params, timeout):
		self.get_calls.append({"url": url, "params": params, "timeout": timeout})
		return FakeResponse({"errcode": 0, "access_token": "access-token", "expires_in": 7200})

	def _post(self, url, *, params, json, timeout):
		self.post_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
		return FakeResponse({"errcode": 0, "msgid": "message-1"})

	def _encrypt(self, plaintext: bytes, receive_id: str = "wx-corp") -> str:
		content = b"R" * 16 + struct.pack("!I", len(plaintext)) + plaintext + receive_id.encode()
		padding = 32 - len(content) % 32
		content += bytes([padding]) * padding
		encryptor = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16])).encryptor()
		return base64.b64encode(encryptor.update(content) + encryptor.finalize()).decode()

	def _request(self, plaintext: bytes, *, receive_id: str = "wx-corp", challenge: bool = False):
		encrypted = self._encrypt(plaintext, receive_id)
		timestamp, nonce = "1700000000", "nonce-1"
		signature = hashlib.sha1("".join(sorted(("callback-token", timestamp, nonce, encrypted))).encode()).hexdigest()
		query = {"msg_signature": signature, "timestamp": timestamp, "nonce": nonce}
		if challenge:
			query["echostr"] = encrypted
			return GatewayInboundRequest(b"", query=query, method="GET")
		return GatewayInboundRequest(f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>".encode(), query=query)

	def test_signed_encrypted_callback_normalizes_a_text_message(self):
		xml = b"<xml><ToUserName><![CDATA[bot]]></ToUserName><FromUserName><![CDATA[user-1]]></FromUserName><CreateTime>1</CreateTime><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[hello]]></Content><MsgId>msg-1</MsgId></xml>"
		request = self._request(xml)
		self.assertTrue(self.adapter.verify_inbound(request))
		event = self.adapter.normalize_inbound(request)
		self.assertEqual((event.provider_event_id, event.sender_id, event.conversation_id, event.message_text), ("msg-1", "user-1", "user-1", "hello"))

	def test_url_verification_and_wrong_signature_or_receive_id_fail_closed(self):
		challenge = self._request(b"echo-value", challenge=True)
		self.assertEqual(self.adapter.verify_url(challenge), "echo-value")
		bad_signature = GatewayInboundRequest(challenge.body, query={**challenge.query, "msg_signature": "wrong"}, method="GET")
		with self.assertRaises(ValueError):
			self.adapter.verify_url(bad_signature)
		wrong_corp = self._request(b"<xml><MsgType>text</MsgType></xml>", receive_id="other-corp")
		self.assertFalse(self.adapter.verify_inbound(wrong_corp))

	def test_outbound_reply_fetches_and_caches_access_token(self):
		first = self.adapter.send_reply(GatewayReply("user-1", "hello"))
		self.now += 1
		second = self.adapter.send_reply(GatewayReply("user-2", "again"))
		self.assertEqual((first.provider_message_id, second.provider_message_id), ("message-1", "message-1"))
		self.assertEqual(len(self.get_calls), 1)
		self.assertEqual(self.get_calls[0]["url"], WECOM_GET_TOKEN_URL)
		self.assertEqual(self.post_calls[0], {
			"url": WECOM_SEND_MESSAGE_URL,
			"params": {"access_token": "access-token"},
			"json": {"touser": "user-1", "msgtype": "text", "agentid": "100001", "text": {"content": "hello"}},
			"timeout": 10,
		})

	def test_conformance_runner_uses_real_encryption_fixture(self):
		xml = b"<xml><FromUserName><![CDATA[user-1]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[hello]]></Content><MsgId>msg-1</MsgId></xml>"
		event = assert_adapter_conforms(self.adapter, self._request(xml), GatewayReply("user-1", "reply"))
		self.assertEqual(event.provider_event_id, "msg-1")

	def test_non_text_events_are_not_normalized(self):
		xml = b"<xml><FromUserName><![CDATA[user-1]]></FromUserName><MsgType><![CDATA[image]]></MsgType><MsgId>msg-1</MsgId></xml>"
		with self.assertRaisesRegex(ValueError, "not a text"):
			self.adapter.normalize_inbound(self._request(xml))
