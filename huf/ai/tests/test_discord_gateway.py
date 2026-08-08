"""Focused unit tests for the Discord Gateway ingress adapter."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateways import discord


class TestDiscordGateway(unittest.TestCase):
	def test_valid_ed25519_signature_is_accepted(self):
		try:
			from cryptography.hazmat.primitives import serialization
			from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
		except ImportError:
			self.skipTest("cryptography is not installed")
		private_key = Ed25519PrivateKey.generate()
		body = b'{"type":1}'
		timestamp = "1234567890"
		signature = private_key.sign(timestamp.encode() + body).hex()
		public_key = private_key.public_key().public_bytes(
			encoding=serialization.Encoding.Raw,
			format=serialization.PublicFormat.Raw,
		).hex()
		self.assertTrue(discord.verify_interaction_signature(public_key, signature, timestamp, body))

	def test_invalid_signature_is_rejected(self):
		self.assertFalse(discord.verify_interaction_signature("00" * 32, "00" * 64, "1", b"{}"))

	def test_interaction_context_normalizes_command(self):
		self.assertEqual(
			discord._interaction_context({"channel_id": "c1", "member": {"user": {"id": "u1"}}, "data": {"name": "ask", "options": [{"value": "hello"}]}}),
			{"sender_id": "u1", "conversation_id": "c1", "thread_id": "", "message_text": "ask hello"},
		)

	@patch("huf.ai.gateways.discord.ingest_gateway_event")
	@patch("huf.ai.gateways.discord.verify_interaction_signature", return_value=True)
	@patch("huf.ai.gateways.discord._gateway_public_key", return_value="public-key")
	@patch("huf.ai.gateways.discord._request_header", return_value="signature")
	@patch("huf.ai.gateways.discord._request_body", return_value=b'{"id":"i1","type":2,"channel_id":"c1","member":{"user":{"id":"u1"}},"data":{"name":"ask"}}')
	@patch("huf.ai.gateways.discord.frappe.get_doc")
	@patch("huf.ai.gateways.discord.frappe.db.exists", return_value=True)
	def test_command_is_ingested_then_deferred(self, _exists, get_doc, _body, _header, _key, _verify, ingest):
		get_doc.return_value = MagicMock(name="gateway", provider="Discord", is_enabled=True)
		get_doc.return_value.name = "discord-gateway"
		self.assertEqual(discord.handle_interaction("discord-gateway"), {"type": 5})
		ingest.assert_called_once()
