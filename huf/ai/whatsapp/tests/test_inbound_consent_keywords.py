# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""HUFCRM-04: inbound STOP/START keywords on verified SMS and email update channel consent."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from unittest.mock import patch
from urllib.parse import urlencode

from frappe.tests.utils import FrappeTestCase

from huf.ai.channels import channel_consent as cc
from huf.ai.gateway_adapters.email import EmailGatewayAdapter
from huf.ai.gateway_adapters.sms import SMSGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest

CALLS = "huf.ai.channels.channel_consent."


SMS_URL = "https://huf.test/api/method/huf.ai.gateway_webhook.receive"


def _sms_request(body_text, token="tok", sign=True):
	# Twilio signs URL + sorted POST params (key+value); the adapter verifies the exact URL.
	params = {"From": "+15550001111", "Body": body_text, "MessageSid": "SM1"}
	body = urlencode(params).encode()
	signed = SMS_URL + "".join(f"{k}{v}" for k, v in sorted(params.items()))
	sig = base64.b64encode(hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()).decode() if sign else ""
	return GatewayInboundRequest(
		method="POST",
		headers={"X-Twilio-Signature": sig},
		query={},
		body=body,
		url=SMS_URL,
		path="/api/method/huf.ai.gateway_webhook.receive",
	)


class TestInboundKeywords(FrappeTestCase):
	def _sms(self, mode="twilio"):
		return SMSGatewayAdapter({"mode": mode, "account_sid": "AC1", "auth_token": "tok", "from_number": "+1"})

	def test_keyword_table(self):
		with patch(CALLS + "record_opt_out", return_value=True) as out:
			for word in ("STOP", " stopall ", "Unsubscribe", "cancel", "END", "quit."):
				self.assertEqual(cc.handle_keyword("sms", "+1555", word), "opt_out")
			self.assertEqual(out.call_count, 6)
			self.assertIsNone(cc.handle_keyword("sms", "+1555", "please stop texting me"))
			self.assertIsNone(cc.handle_keyword("sms", "+1555", "hello"))

	def test_start_only_lifts_an_opt_out(self):
		with patch(CALLS + "_latest", return_value={"value": "opt_out", "scope": "all"}), patch(CALLS + "_insert") as ins:
			self.assertEqual(cc.handle_keyword("sms", "+15550001111", "START"), "opt_in")
			self.assertEqual(ins.call_args.args[2], "opt_in")
		with patch(CALLS + "_latest", return_value=None), patch(CALLS + "_insert") as ins:
			self.assertIsNone(cc.handle_keyword("sms", "+15550001111", "UNSTOP"))
			ins.assert_not_called()

	def test_sms_verified_stop_records_opt_out(self):
		with patch(CALLS + "record_opt_out", return_value=True) as out:
			self._sms().normalize_inbound(_sms_request("STOP"))
		self.assertEqual(out.call_args.args[:2], ("sms", "+15550001111"))

	def test_sms_unverified_or_wrong_mode_never_writes_consent(self):
		with patch(CALLS + "record_opt_out", return_value=True) as out:
			with self.assertRaises(PermissionError):
				self._sms().normalize_inbound(_sms_request("STOP", sign=False))
			with self.assertRaises(PermissionError):
				self._sms("send_only").normalize_inbound(_sms_request("STOP"))
			with self.assertRaises(PermissionError):
				self._sms().normalize_inbound(_sms_request("STOP", token="forged"))
		out.assert_not_called()

	def test_email_verified_unsubscribe_records_opt_out(self):
		req = GatewayInboundRequest(
			method="POST", headers={"X-Webhook-Secret": "s"}, query={},
			body=json.dumps({"from": "Ann <ann@example.com>", "body": "UNSUBSCRIBE", "id": "m1"}).encode(),
		)
		with patch(CALLS + "_insert") as ins:
			EmailGatewayAdapter({"webhook_secret": "s"}).normalize_inbound(req)
		self.assertEqual(ins.call_args.args[:3], ("email", "ann@example.com", "opt_out"))
		with patch(CALLS + "_insert") as ins:
			bad = GatewayInboundRequest(method="POST", headers={"X-Webhook-Secret": "x"}, query={}, body=req.body)
			with self.assertRaises(ValueError):
				EmailGatewayAdapter({"webhook_secret": "s"}).normalize_inbound(bad)
		ins.assert_not_called()
