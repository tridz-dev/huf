"""Unit tests for SMS gateway adapter: fail-closed inbound, send-only, honest ids (HUFCRM-02)."""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters.sms import SMSGatewayAdapter, send_sms_message
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply

BODY = b"From=+1234567890&To=+0987654321&Body=Hello&MessageSid=SM1"


def _req(body=BODY, headers=None):
	return GatewayInboundRequest(body=body, headers=headers or {}, query={}, method="POST")


def _sig(token, body=BODY):
	return base64.b64encode(hmac.new(token.encode(), body, hashlib.sha1).digest()).decode()


TW = {"mode": "twilio", "account_sid": "AC1", "auth_token": "tok", "from_number": "+1555"}


class TestSMSInboundFailClosed(unittest.TestCase):
	def test_bypass_empty_credentials_rejected(self):
		# Previously returned True (account_sid defaulted to frappe_sms).
		self.assertFalse(SMSGatewayAdapter({}).verify_inbound(_req()))

	def test_bypass_frappe_sms_sid_rejected(self):
		self.assertFalse(SMSGatewayAdapter({"account_sid": "frappe_sms"}).verify_inbound(_req()))

	def test_missing_auth_token_rejected_even_in_twilio_mode(self):
		self.assertFalse(SMSGatewayAdapter({"mode": "twilio", "account_sid": "AC1"}).verify_inbound(_req()))

	def test_frappe_sms_mode_rejects_inbound(self):
		self.assertFalse(SMSGatewayAdapter({"mode": "frappe_sms"}).verify_inbound(_req()))

	def test_send_only_rejects_even_valid_signature(self):
		a = SMSGatewayAdapter({**TW, "mode": "send_only"})
		self.assertFalse(a.verify_inbound(_req(headers={"X-Twilio-Signature": _sig("tok")})))

	def test_missing_and_invalid_signature_rejected(self):
		a = SMSGatewayAdapter(TW)
		self.assertFalse(a.verify_inbound(_req()))
		self.assertFalse(a.verify_inbound(_req(headers={"X-Twilio-Signature": "bad"})))

	def test_valid_signature_accepted(self):
		a = SMSGatewayAdapter(TW)
		self.assertTrue(a.verify_inbound(_req(headers={"X-Twilio-Signature": _sig("tok")})))

	def test_normalize_refuses_unverified(self):
		with self.assertRaises(PermissionError):
			SMSGatewayAdapter(TW).normalize_inbound(_req())

	def test_normalize_missing_sid_uses_unique_uuid_id(self):
		body = b"From=+1&Body=x"
		a = SMSGatewayAdapter(TW)
		r = _req(body, {"X-Twilio-Signature": _sig("tok", body)})
		e1, e2 = a.normalize_inbound(r), a.normalize_inbound(r)
		self.assertTrue(e1.provider_event_id.startswith("sms-unknown-"))
		self.assertNotEqual(e1.provider_event_id, e2.provider_event_id)


class TestSMSSend(unittest.TestCase):
	def test_unset_mode_send_raises(self):
		with self.assertRaises(ValueError):
			SMSGatewayAdapter({"account_sid": "AC1", "auth_token": "t"}).send_reply(GatewayReply("+1", "hi"))

	def test_twilio_success_uses_real_sid(self):
		post = MagicMock(return_value={"sid": "SM9", "status": "queued"})
		d = SMSGatewayAdapter(TW, http_post=post).send_reply(GatewayReply("+1", "hi"))
		self.assertEqual(d.provider_message_id, "SM9")

	def test_twilio_failure_raises(self):
		for bad in ({"message": "nope"}, {"sid": "", "error_code": 21211}, {"sid": "S", "error_code": 1}):
			a = SMSGatewayAdapter(TW, http_post=MagicMock(return_value=bad))
			with self.assertRaises(ValueError):
				a.send_reply(GatewayReply("+1", "hi"))

	def test_send_only_sends(self):
		post = MagicMock(return_value={"sid": "SM2"})
		SMSGatewayAdapter({**TW, "mode": "send_only"}, http_post=post).send_reply(GatewayReply("+1", "hi"))
		post.assert_called_once()

	def test_frappe_sms_status_unknown_and_id_unique(self):
		a = SMSGatewayAdapter({"mode": "frappe_sms"})
		with patch("frappe.core.doctype.sms_settings.sms_settings.send_sms", create=True):
			d1, d2 = a.send_reply(GatewayReply("+1", "hi")), a.send_reply(GatewayReply("+1", "hi"))
		self.assertEqual(d1.provider_response["status"], "unknown")
		self.assertNotEqual(d1.provider_message_id, d2.provider_message_id)

	def test_frappe_sms_failure_raises(self):
		with patch("frappe.core.doctype.sms_settings.sms_settings.send_sms", side_effect=RuntimeError("x"), create=True):
			with self.assertRaises(RuntimeError):
				SMSGatewayAdapter({"mode": "frappe_sms"}).send_reply(GatewayReply("+1", "hi"))


class TestSendSmsMessage(unittest.TestCase):
	def test_ok(self):
		a = SMSGatewayAdapter(TW, http_post=MagicMock(return_value={"sid": "SM3", "status": "queued"}))
		self.assertEqual(send_sms_message(a, "+1", "otp"), {"ok": True, "id": "SM3", "status": "queued", "error": None})

	def test_failure_returns_failed(self):
		r = send_sms_message({}, "+1", "otp")
		self.assertFalse(r["ok"])
		self.assertEqual(r["status"], "failed")
		self.assertTrue(r["error"])
