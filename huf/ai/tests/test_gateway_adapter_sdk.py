"""Contract tests for the provider-neutral Gateway Adapter SDK."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters import (
	GatewayAdapter,
	GatewayAdapterConformanceError,
	GatewayAdapterRegistry,
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
	assert_adapter_conforms,
)


class FakeAdapter(GatewayAdapter):
	provider_id = "fake"
	credential_schema = GatewayCredentialSchema((GatewayCredentialField("secret", "Secret"),))
	capabilities = GatewayCapabilities(frozenset({"webhook"}), supports_thread_reply=True)

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		return request.headers.get("X-Fake-Signature") == "valid"

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Inbound request was not verified")
		return NormalizedGatewayEvent(
			provider_event_id="event-1",
			sender_id="sender-1",
			conversation_id="conversation-1",
			message_text=request.body.decode(),
			thread_id="thread-1",
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		if not reply.text:
			raise ValueError("Reply text is required")
		return OutboundDelivery("message-1", provider_response={"conversation": reply.conversation_id})


class TestGatewayAdapterSdk(unittest.TestCase):
	def test_credential_schema_rejects_duplicate_keys_and_finds_missing_required(self):
		field = GatewayCredentialField("token", "Token")
		with self.assertRaises(ValueError):
			GatewayCredentialSchema((field, field))
		self.assertEqual(
			GatewayCredentialSchema((field,)).missing_required({}),
			("token",),
		)

	def test_value_types_reject_missing_required_fields(self):
		with self.assertRaises(ValueError):
			GatewayCapabilities(frozenset())
		with self.assertRaises(ValueError):
			NormalizedGatewayEvent("", "sender", "conversation", "hello")
		with self.assertRaises(ValueError):
			GatewayReply("conversation", "")
		with self.assertRaises(ValueError):
			OutboundDelivery("")

	def test_registry_is_deterministic_and_rejects_duplicates(self):
		registry = GatewayAdapterRegistry()
		registry.register(FakeAdapter)
		self.assertIs(registry.get("fake"), FakeAdapter)
		self.assertEqual(registry.names(), ["fake"])
		with self.assertRaises(ValueError):
			registry.register(type("DuplicateAdapter", (FakeAdapter,), {"provider_id": "fake"}))
		with self.assertRaises(KeyError):
			registry.get("missing")

	def test_verified_inbound_normalizes_and_sends_reply(self):
		adapter = FakeAdapter()
		request = GatewayInboundRequest(b"hello", headers={"X-Fake-Signature": "valid"})
		self.assertTrue(adapter.verify_inbound(request))
		event = adapter.normalize_inbound(request)
		self.assertEqual(event.provider_event_id, "event-1")
		delivery = adapter.send_reply(GatewayReply(event.conversation_id, "hi", thread_id=event.thread_id))
		self.assertTrue(delivery.accepted)
		self.assertEqual(delivery.provider_message_id, "message-1")

	def test_conformance_runner_exercises_the_minimum_adapter_contract(self):
		adapter = FakeAdapter()
		request = GatewayInboundRequest(b"hello", headers={"X-Fake-Signature": "valid"})
		event = assert_adapter_conforms(adapter, request, GatewayReply("conversation-1", "hi"))
		self.assertEqual(event.sender_id, "sender-1")
		with self.assertRaises(GatewayAdapterConformanceError):
			assert_adapter_conforms(adapter, GatewayInboundRequest(b"hello"), GatewayReply("conversation-1", "hi"))

	def test_unverified_request_cannot_be_normalized_by_conforming_adapter(self):
		adapter = FakeAdapter()
		request = GatewayInboundRequest(b"hello", headers={"X-Fake-Signature": "invalid"})
		self.assertFalse(adapter.verify_inbound(request))
		with self.assertRaises(ValueError):
			adapter.normalize_inbound(request)
