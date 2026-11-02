"""Focused fixtures for the WhatsApp Cloud API adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp import (
	GRAPH_VERSION,
	WhatsAppGatewayAdapter,
	WhatsAppParsed,
	WhatsAppWindowClosed,
)

BRIDGE = "huf.ai.gateway_adapters.whatsapp.bridge"
OPEN = {"open": True, "last_inbound_at": None, "expires_at": None}
CLOSED = {"open": False, "last_inbound_at": None, "expires_at": None}


class FakeResponse:
	def __init__(self, body):
		self.body = body
		self.raised = False

	def raise_for_status(self):
		self.raised = True

	def json(self):
		return self.body


def _msg(wamid, text="hello", sender="+1 (234) 567-890", **extra):
	m = {"from": sender, "id": wamid, "type": "text", "text": {"body": text}}
	m.update(extra)
	return m


def _payload(messages=None, statuses=None, phone_id="phone-123", extra_changes=()):
	value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": phone_id}}
	if messages is not None:
		value["messages"] = messages
		value["contacts"] = [{"wa_id": "1234567890", "profile": {"name": "Ann"}}]
	if statuses is not None:
		value["statuses"] = statuses
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}, *extra_changes]}],
	}


def _request(payload):
	return GatewayInboundRequest(json.dumps(payload).encode())


class TestWhatsAppGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.creds = {
			"phone_number_id": "phone-123",
			"access_token": "access-token",
			"webhook_verify_token": "verify-value",
			"app_secret": "s3cret",
		}
		self.adapter = self.make()

	def make(self, context=None, creds=None):
		return WhatsAppGatewayAdapter(creds or self.creds, http_post=self._post, gateway_context=context)

	def _post(self, url, *, headers, json, timeout):
		self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
		return FakeResponse({"messages": [{"id": "wamid.out"}]})

	def signed(self, payload, secret="s3cret"):
		body = json.dumps(payload).encode()
		sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
		return GatewayInboundRequest(body, headers={"X-Hub-Signature-256": sig})

	# --- verification
	def test_signature_ok_forged_and_missing(self):
		p = _payload([_msg("wamid.1")])
		self.assertTrue(self.adapter.verify_inbound(self.signed(p)))
		self.assertFalse(self.adapter.verify_inbound(self.signed(p, secret="wrong")))
		self.assertFalse(self.adapter.verify_inbound(_request(p)))

	def test_missing_app_secret_fails_closed(self):
		adapter = self.make()
		adapter._app_secret = ""
		self.assertFalse(adapter.verify_inbound(self.signed(_payload([_msg("wamid.1")]))))

	def test_get_challenge_ok_and_mismatch(self):
		q = {"hub.mode": "subscribe", "hub.verify_token": "verify-value", "hub.challenge": "abc"}
		self.assertEqual(self.adapter.verify_url(GatewayInboundRequest(b"", query=q, method="GET")), "abc")
		bad = GatewayInboundRequest(b"", query={**q, "hub.verify_token": "nope"}, method="GET")
		with self.assertRaises(frappe.PermissionError):
			self.adapter.verify_url(bad)
		# hub.mode, when present, must be "subscribe"; absent is accepted (older tooling)
		with self.assertRaises(frappe.PermissionError):
			self.adapter.verify_url(GatewayInboundRequest(b"", query={**q, "hub.mode": "unsubscribe"}, method="GET"))
		legacy = {k: v for k, v in q.items() if k != "hub.mode"}
		self.assertEqual(self.adapter.verify_url(GatewayInboundRequest(b"", query=legacy, method="GET")), "abc")

	def test_graph_url_uses_shared_version_constant(self):
		from huf.ai.gateway_adapters import whatsapp as wa
		self.assertEqual(wa.GRAPH_VERSION, bridge.GRAPH_DEFAULT_VERSION)
		self.assertTrue(self.adapter._graph_url.endswith("/" + bridge.GRAPH_DEFAULT_VERSION))
		self.assertTrue(self.adapter._graph_url.startswith("https://graph.facebook.com/"))

	# --- parsing
	def test_batch_fan_out(self):
		parsed = self.adapter.parse_payload(_request(_payload([_msg("wamid.1"), _msg("wamid.2", "two")])))
		self.assertIsInstance(parsed, WhatsAppParsed)
		self.assertEqual([e.provider_event_id for e in parsed.messages], ["wamid.1", "wamid.2"])
		self.assertEqual(parsed.messages[0].sender_id, "1234567890")
		self.assertEqual(parsed.messages[0].conversation_id, "1234567890")
		self.assertEqual(parsed.messages[0].display_name, "Ann")

	def test_status_only_payload(self):
		req = _request(_payload(statuses=[{"id": "wamid.x", "status": "delivered"}]))
		parsed = self.adapter.parse_payload(req)
		self.assertEqual(parsed.messages, ())
		self.assertEqual(len(parsed.statuses), 1)
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(req)

	def test_template_update(self):
		change = {"field": "message_template_status_update", "value": {"event": "APPROVED", "message_template_name": "t"}}
		payload = {"entry": [{"changes": [change]}]}
		parsed = self.adapter.parse_payload(_request(payload))
		self.assertEqual(parsed.template_updates[0]["event"], "APPROVED")
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(_request(payload))

	def test_missing_metadata_phone_id_fails_closed(self):
		payload = _payload([_msg("wamid.1")], statuses=[{"id": "wamid.s", "status": "sent"}])
		payload["entry"][0]["changes"][0]["value"].pop("metadata")
		parsed = self.adapter.parse_payload(_request(payload))
		self.assertEqual(parsed.messages, ())
		self.assertEqual(parsed.statuses, ())
		self.assertGreaterEqual(parsed.ignored, 2)

	def test_phone_id_mismatch_ignored(self):
		parsed = self.adapter.parse_payload(_request(_payload([_msg("wamid.1")], phone_id="other")))
		self.assertEqual(parsed.messages, ())
		self.assertGreaterEqual(parsed.ignored, 1)

	def test_error_and_unknown_messages_ignored_without_raise(self):
		msgs = [{"from": "1", "id": "w1", "errors": [{"code": 131051}]}, {"from": "1", "id": "w2", "type": "unsupported"}]
		parsed = self.adapter.parse_payload(_request(_payload(msgs)))
		# w1 has no type/text (dropped); w2 is Meta's `unsupported` and now reaches the agent as text.
		self.assertEqual([m.provider_event_id for m in parsed.messages], ["w2"])
		self.assertEqual(parsed.messages[0].message_text, "[unsupported message]")
		self.assertEqual(parsed.ignored, 1)

	def test_empty_payload_raises(self):
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(_request({"object": "whatsapp_business_account"}))

	def test_quoted_reply_keeps_thread_id_none(self):
		event = self.adapter.normalize_inbound(
			_request(_payload([_msg("wamid.1", context={"id": "wamid.prev"})]))
		)
		self.assertIsNone(event.thread_id)
		self.assertEqual(event.raw_payload["quoted_message_id"], "wamid.prev")
		self.assertFalse(self.adapter.capabilities.supports_thread_reply)

	def test_media_attachment_metadata_kept(self):
		img = {"from": "1234567890", "id": "w9", "type": "image", "image": {"id": "m1", "mime_type": "image/jpeg", "caption": "pic"}}
		event = self.adapter.normalize_inbound(_request(_payload([img])))
		self.assertEqual(event.message_text, "pic")
		self.assertEqual(event.attachments[0].file_id, "m1")

	# --- send_reply
	def reply(self):
		return GatewayReply("1234567890", "hi", reply_to_provider_message_id="wamid.in")

	def test_window_open_direct_mode_single_graph_post(self):
		adapter = self.make({"gateway_name": "gw"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = OPEN
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			delivery = adapter.send_reply(self.reply())
			b.send_text.assert_not_called()
		self.assertEqual(delivery.provider_message_id, "wamid.out")
		self.assertEqual(len(self.calls), 1)
		call = self.calls[0]
		self.assertEqual(call["url"], f"https://graph.facebook.com/{GRAPH_VERSION}/phone-123/messages")
		self.assertEqual(call["json"]["text"]["body"], "hi")
		self.assertEqual(call["json"]["context"], {"message_id": "wamid.in"})

	def test_bridge_mode_single_send_no_graph_post(self):
		adapter = self.make({"gateway_name": "gw", "whatsapp_account": "acct"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = OPEN
			b.is_available.return_value = True
			b.send_text.return_value = {"success": True, "name": "WM-1", "message_id": "wamid.b", "status": "Sent"}
			delivery = adapter.send_reply(self.reply())
			b.send_text.assert_called_once_with(
				"acct", "1234567890", "hi", reply_to="wamid.in", trusted=True, preview_url=False
			)
		self.assertEqual(delivery.provider_message_id, "wamid.b")
		self.assertEqual(self.calls, [])

	def test_window_closed_with_fallback_direct_template(self):
		adapter = self.make({"gateway_name": "gw", "fallback_template": "reopen"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			adapter.send_reply(self.reply())
		self.assertEqual(len(self.calls), 1)
		payload = self.calls[0]["json"]
		self.assertEqual(payload["type"], "template")
		self.assertEqual(payload["template"]["name"], "reopen")

	def test_window_closed_with_fallback_bridge_template(self):
		adapter = self.make({"gateway_name": "gw", "whatsapp_account": "acct", "fallback_template": "reopen"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = True
			b.send_template.return_value = {"message_id": "wamid.t", "name": "WM-2"}
			delivery = adapter.send_reply(self.reply())
			b.send_template.assert_called_once()
			b.send_text.assert_not_called()
		self.assertEqual(delivery.provider_message_id, "wamid.t")
		self.assertEqual(self.calls, [])

	def test_fallback_template_uses_configured_language_in_direct_mode(self):
		adapter = self.make({"gateway_name": "gw", "fallback_template": "reopen", "fallback_template_language": "pt_BR"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			delivery = adapter.send_reply(self.reply())
		self.assertEqual(self.calls[0]["json"]["template"]["language"], {"code": "pt_BR"})
		self.assertTrue(delivery.provider_response["fallback_template_sent"])

	def test_fallback_template_language_defaults_to_en_us(self):
		adapter = self.make({"gateway_name": "gw", "fallback_template": "reopen"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			adapter.send_reply(self.reply())
		self.assertEqual(self.calls[0]["json"]["template"]["language"], {"code": "en_US"})

	def test_fallback_template_language_read_from_templates_row_in_bridge_mode(self):
		adapter = self.make(
			{"gateway_name": "gw", "whatsapp_account": "acct", "fallback_template": "reopen", "fallback_template_language": "en_US"}
		)
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = True
			b.template_language.return_value = "hi"
			b.send_template.return_value = {"message_id": "wamid.t", "name": "WM-2"}
			delivery = adapter.send_reply(self.reply())
			b.template_language.assert_called_once_with("acct", "reopen", "en_US")
			self.assertEqual(b.send_template.call_args.kwargs["language_code"], "hi")
		self.assertTrue(delivery.provider_response["fallback_template_sent"])

	def test_in_window_reply_is_not_flagged_as_fallback(self):
		adapter = self.make({"gateway_name": "gw", "fallback_template": "reopen"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = OPEN
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			delivery = adapter.send_reply(self.reply())
		self.assertNotIn("fallback_template_sent", delivery.provider_response)

	def test_unknown_phone_number_ids_are_reported_by_parse(self):
		parsed = self.adapter.parse_payload(_request(_payload([_msg("wamid.1")], phone_id="other")))
		self.assertEqual(parsed.unknown_phone_ids, ("other",))
		ok = self.adapter.parse_payload(_request(_payload([_msg("wamid.1")])))
		self.assertEqual(ok.unknown_phone_ids, ())

	def test_window_closed_without_fallback_raises(self):
		adapter = self.make({"gateway_name": "gw"})
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			with self.assertRaises(WhatsAppWindowClosed):
				adapter.send_reply(self.reply())
		self.assertEqual(self.calls, [])
		self.assertTrue(issubclass(WhatsAppWindowClosed, frappe.ValidationError))

	def test_outbound_errors_are_not_silently_accepted(self):
		adapter = self.make()
		adapter._http_post = lambda *a, **k: FakeResponse({"error": {"message": "denied"}})
		with patch(BRIDGE) as b:
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			with self.assertRaisesRegex(ValueError, "denied"):
				adapter.send_reply(self.reply())
