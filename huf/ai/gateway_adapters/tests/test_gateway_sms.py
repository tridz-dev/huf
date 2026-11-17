"""Unit tests for SMS gateway adapter: fail-closed inbound, send-only, honest ids (HUFCRM-02)."""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters.sms import SMSGatewayAdapter, send_sms_message
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply

BODY = b"From=+1234567890&To=+0987654321&Body=Hello&MessageSid=SM1"


URL = "https://crm.example.com/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=g1"
PATH = "/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
QS = "gateway_name=g1"


def _req(body=BODY, headers=None, url=URL, path=PATH, qs=QS):
	return GatewayInboundRequest(
		body=body, headers=headers or {}, query={}, method="POST", url=url, path=path, query_string=qs
	)


def twilio_sig(token, url, params):
	data = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
	return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


FORM = {"From": "+1234567890", "To": "+0987654321", "Body": "Hello", "MessageSid": "SM1"}


def _sig(token, body=BODY, url=URL):
	from urllib.parse import parse_qsl

	return twilio_sig(token, url, dict(parse_qsl(body.decode(), keep_blank_values=True)))


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

	def test_twilio_published_vector(self):
		# Twilio security docs worked example.
		url = "https://example.com/myapp.php?foo=1&bar=2"
		params = {"CallSid": "CA1234567890ABCDE", "Caller": "+14158675310", "Digits": "1234",
			"From": "+14158675310", "To": "+18005551212"}
		self.assertEqual(twilio_sig("12345", url, params), "L/OH5YylLD5NRKLltdqwSvS0BnU=")
		body = "&".join(f"{k}={v.replace('+', '%2B')}" for k, v in reversed(list(params.items()))).encode()
		a = SMSGatewayAdapter({**TW, "auth_token": "12345"})
		req = _req(body, {"X-Twilio-Signature": "L/OH5YylLD5NRKLltdqwSvS0BnU="}, url, "/myapp.php", "foo=1&bar=2")
		self.assertTrue(a.verify_inbound(req))

	def test_body_only_hmac_rejected(self):
		sig = base64.b64encode(hmac.new(b"tok", BODY, hashlib.sha1).digest()).decode()
		self.assertFalse(SMSGatewayAdapter(TW).verify_inbound(_req(headers={"X-Twilio-Signature": sig})))

	def test_tampered_param_and_wrong_url_rejected(self):
		a = SMSGatewayAdapter(TW)
		sig = _sig("tok")
		self.assertFalse(a.verify_inbound(_req(BODY.replace(b"Hello", b"Hacked"), {"X-Twilio-Signature": sig})))
		self.assertFalse(a.verify_inbound(_req(headers={"X-Twilio-Signature": sig}, url=URL.replace("g1", "g2"))))

	def test_header_case_insensitive_and_default_port(self):
		a = SMSGatewayAdapter(TW)
		self.assertTrue(a.verify_inbound(_req(headers={"x-twilio-signature": _sig("tok")})))
		ported = URL.replace("crm.example.com", "crm.example.com:443")
		self.assertTrue(a.verify_inbound(_req(headers={"X-Twilio-Signature": _sig("tok")}, url=ported)))

	def test_undeterminable_url_rejected(self):
		a = SMSGatewayAdapter(TW)
		self.assertFalse(a.verify_inbound(_req(headers={"X-Twilio-Signature": _sig("tok")}, url="")))

	def test_base_url_setting_overrides_internal_url(self):
		a = SMSGatewayAdapter({**TW, "webhook_base_url": "https://crm.example.com/"})
		req = _req(headers={"X-Twilio-Signature": _sig("tok")}, url="http://127.0.0.1:8000" + PATH + "?" + QS)
		self.assertTrue(a.verify_inbound(req))

	def test_forwarded_headers_ignored_unless_trusted(self):
		fwd = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.com"}
		internal = "http://127.0.0.1:8000" + PATH + "?" + QS
		h = {"X-Twilio-Signature": _sig("tok"), **fwd}
		self.assertFalse(SMSGatewayAdapter(TW).verify_inbound(_req(headers=h, url=internal)))
		self.assertTrue(SMSGatewayAdapter({**TW, "trusted_proxy": "1"}).verify_inbound(_req(headers=h, url=internal)))
		# trusted proxy but headers absent: fail closed
		self.assertFalse(SMSGatewayAdapter({**TW, "trusted_proxy": "1"}).verify_inbound(
			_req(headers={"X-Twilio-Signature": _sig("tok")}, url=internal)))

	def test_json_body_sha256(self):
		body = b'{"From": "+1", "Body": "hi", "MessageSid": "SMj"}'
		url = URL + "&bodySHA256=" + hashlib.sha256(body).hexdigest()
		qs = QS + "&bodySHA256=" + hashlib.sha256(body).hexdigest()
		h = {"X-Twilio-Signature": twilio_sig("tok", url, {}), "Content-Type": "application/json"}
		a = SMSGatewayAdapter(TW)
		self.assertTrue(a.verify_inbound(_req(body, h, url, PATH, qs)))
		self.assertEqual(a.normalize_inbound(_req(body, h, url, PATH, qs)).provider_event_id, "SMj")
		# body altered after signing: hash mismatch
		self.assertFalse(a.verify_inbound(_req(body + b" ", h, url, PATH, qs)))
		# no bodySHA256 in URL
		h2 = {"X-Twilio-Signature": twilio_sig("tok", URL, {}), "Content-Type": "application/json"}
		self.assertFalse(a.verify_inbound(_req(body, h2)))

	def test_stop_keyword_wired_after_verification(self):
		body = b"From=%2B1&Body=STOP&MessageSid=SM5"
		a = SMSGatewayAdapter(TW)
		with patch("huf.ai.channels.channel_consent.handle_keyword") as hk:
			a.normalize_inbound(_req(body, {"X-Twilio-Signature": _sig("tok", body)}))
			hk.assert_called_once_with("sms", "+1", "STOP", "sms_inbound")
			hk.reset_mock()
			with self.assertRaises(PermissionError):
				a.normalize_inbound(_req(body))
			hk.assert_not_called()

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
