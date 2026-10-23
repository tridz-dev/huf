"""WP-4a: caption split, fallback-template parameters/approval, window_state record-only skip."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import GatewayReply
from huf.ai.gateway_adapters import whatsapp_bridge as wb
from huf.ai.gateway_adapters.types import GatewayAttachment
from huf.ai.gateway_adapters.whatsapp import (
	WhatsAppFallbackUnavailable,
	WhatsAppGatewayAdapter,
	WhatsAppWindowClosed,
)

BRIDGE = "huf.ai.gateway_adapters.whatsapp.bridge"
OPEN = {"open": True, "last_inbound_at": None, "expires_at": None}
CLOSED = {"open": False, "last_inbound_at": None, "expires_at": None}
NOW = datetime(2026, 1, 10, 12, 0, 0)
CREDS = {
	"phone_number_id": "phone-123",
	"access_token": "access-token",
	"webhook_verify_token": "verify-value",
	"app_secret": "s3cret",
}


class _Resp:
	def raise_for_status(self):
		pass

	def json(self):
		return {"messages": [{"id": "wamid.out"}]}


class TestCaptionSplit(unittest.TestCase):
	def setUp(self):
		self.calls = []

	def _post(self, url, *, headers, json, timeout):
		self.calls.append(json)
		return _Resp()

	def _adapter(self):
		return WhatsAppGatewayAdapter(CREDS, http_post=self._post, gateway_context={"gateway_name": "gw"})

	def _send(self, text, kind="image"):
		reply = GatewayReply(
			"15551230000", text, attachments=(GatewayAttachment(url="https://x.test/a.png", kind=kind),)
		)
		with patch(BRIDGE) as b:
			b.window_state.return_value = OPEN
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			return self._adapter().send_reply(reply)

	def test_long_text_with_media_keeps_all_text(self):
		words = " ".join(f"w{i:04d}" for i in range(400))  # ~2800 chars
		delivery = self._send(words)
		self.assertEqual(self.calls[0]["type"], "image")
		caption = self.calls[0]["image"]["caption"]
		self.assertLessEqual(len(caption), 1024)
		texts = [c["text"]["body"] for c in self.calls[1:]]
		self.assertTrue(texts)
		sent = " ".join([caption, *texts]).split()
		self.assertEqual(sent, words.split())
		self.assertEqual(delivery.provider_message_id, "wamid.out")

	def test_short_text_is_only_the_caption(self):
		self._send("**bold** hello")
		self.assertEqual(len(self.calls), 1)
		self.assertEqual(self.calls[0]["image"]["caption"], "*bold* hello")  # formatted for WhatsApp


class TestFallbackTemplate(unittest.TestCase):
	def setUp(self):
		self.calls = []

	def _post(self, url, *, headers, json, timeout):
		self.calls.append(json)
		return _Resp()

	def _reply(self):
		return GatewayReply("15551230000", "hi")

	def test_configured_params_are_sent_bridge_mode(self):
		ctx = {
			"gateway_name": "gw", "whatsapp_account": "acct", "fallback_template": "reopen",
			"fallback_template_params": ["Ann", "Acme"],
		}
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=self._post, gateway_context=ctx)
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = True
			b.template_language.return_value = "en_US"
			b.fallback_template_info.return_value = {"status": "APPROVED", "variables": ["1", "2"]}
			b.send_template.return_value = {"message_id": "wamid.t", "name": "WM"}
			adapter.send_reply(self._reply())
		self.assertEqual(b.send_template.call_args.args[3], ["Ann", "Acme"])

	def test_default_params_fill_each_variable(self):
		ctx = {"gateway_name": "gw", "whatsapp_account": "acct", "fallback_template": "reopen"}
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=self._post, gateway_context=ctx)
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = True
			b.template_language.return_value = "en_US"
			b.fallback_template_info.return_value = {"status": "APPROVED", "variables": ["1", "2"]}
			b.send_template.return_value = {"message_id": "wamid.t", "name": "WM"}
			adapter.send_reply(self._reply())
		params = b.send_template.call_args.args[3]
		self.assertEqual(len(params), 2)
		self.assertTrue(all(isinstance(p, str) and p for p in params))

	def test_direct_mode_sends_configured_params(self):
		ctx = {"gateway_name": "gw", "fallback_template": "reopen", "fallback_template_params": ["Ann"]}
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=self._post, gateway_context=ctx)
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = False
			b.normalize_phone.side_effect = lambda x: x
			adapter.send_reply(self._reply())
		body = self.calls[0]["template"]["components"][0]
		self.assertEqual(body["type"], "body")
		self.assertEqual(body["parameters"][0]["text"], "Ann")

	def test_unapproved_template_is_refused_with_typed_error(self):
		ctx = {"gateway_name": "gw", "whatsapp_account": "acct", "fallback_template": "reopen"}
		adapter = WhatsAppGatewayAdapter(CREDS, http_post=self._post, gateway_context=ctx)
		with patch(BRIDGE) as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = True
			b.template_language.return_value = "en_US"
			b.fallback_template_info.return_value = {"status": "PAUSED", "variables": []}
			with self.assertRaises(WhatsAppFallbackUnavailable) as cm:
				adapter.send_reply(self._reply())
			b.send_template.assert_not_called()
		self.assertEqual(cm.exception.code, "fallback_template_not_approved")
		self.assertIsInstance(cm.exception, WhatsAppWindowClosed)  # existing callers already catch this
		self.assertEqual(self.calls, [])


class TestWindowStateRecordOnly(unittest.TestCase):
	def _window(self, rows):
		with patch.object(frappe, "get_all", return_value=rows):
			return wb.window_state("GW", "+1 415", now=NOW)

	def test_record_only_kinds_do_not_open_window(self):
		for kind in ("edit", "revoke", "system", "unknown"):
			row = {
				"received_at": NOW - timedelta(minutes=5), "verified_sender": 1, "raw_payload": {"kind": kind},
			}
			self.assertFalse(self._window([row])["open"], kind)

	def test_record_only_does_not_extend_older_real_message(self):
		old = {"received_at": NOW - timedelta(hours=20), "verified_sender": 1, "raw_payload": {"kind": "message"}}
		edit = {"received_at": NOW - timedelta(minutes=1), "verified_sender": 1, "raw_payload": {"kind": "edit"}}
		res = self._window([edit, old])
		self.assertTrue(res["open"])
		self.assertEqual(res["last_inbound_at"], NOW - timedelta(hours=20))
