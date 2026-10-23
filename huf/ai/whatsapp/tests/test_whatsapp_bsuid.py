# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-3b: BSUID-only inbound is ingested with the BSUID kept verbatim; normalize_phone never digit-strips one."""

import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import gateway_service
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CREDS = {"phone_number_id": "106540352242922", "access_token": "t", "webhook_verify_token": "v", "app_secret": "s"}
BSUID = "IN.460812345678901234"


def parse(name=None, body=None):
	adapter = WhatsAppGatewayAdapter(CREDS)
	body = body if body is not None else (FIXTURES / name).read_bytes()
	return adapter.parse_payload(GatewayInboundRequest(body=body, headers={}, method="POST"))


class TestNormalize(unittest.TestCase):
	def test_bsuid_verbatim(self):
		for v in (BSUID, "US.13491208655302741918", "US.ENT.1349120865", " IN.4608 "):
			self.assertEqual(bridge.normalize_phone(v), v.strip())
			self.assertTrue(bridge.is_bsuid(v))

	def test_phones_unchanged(self):
		self.assertEqual(bridge.normalize_phone("+91 98765-43210"), "919876543210")
		self.assertEqual(bridge.normalize_phone("0091 9876543210"), "919876543210")
		self.assertFalse(bridge.is_bsuid("919876543210"))
		self.assertFalse(bridge.is_bsuid(""))


class TestParse(unittest.TestCase):
	def test_bsuid_only_ingested_verbatim(self):
		parsed = parse("bsuid_only.json")
		self.assertEqual(len(parsed.messages), 1)
		ev = parsed.messages[0]
		self.assertEqual(ev.sender_id, BSUID)
		self.assertEqual(ev.conversation_id, BSUID)
		self.assertEqual(ev.display_name, "Ravi Kumar")

	def test_user_id_fallback(self):
		import json
		body = json.loads((FIXTURES / "bsuid_only.json").read_text())
		msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
		msg["user_id"] = msg.pop("from_user_id")
		self.assertEqual(parse(body=json.dumps(body).encode()).messages[0].sender_id, BSUID)

	def test_both_keeps_phone_primary_and_bsuid_alongside(self):
		ev = parse("both.json").messages[0]
		self.assertEqual(ev.sender_id, "919876543210")
		self.assertEqual(ev.raw_payload["bsuid"], BSUID)
		self.assertEqual(ev.raw_payload["message"]["from_user_id"], BSUID)

	def test_bsuid_only_logged_masked(self):
		with patch("huf.ai.gateway_adapters.whatsapp.frappe.logger") as lg:
			parse("bsuid_only.json")
		lines = " ".join(str(c) for c in lg.return_value.info.call_args_list)
		self.assertIn("bsuid_only_sender", lines)
		self.assertNotIn(BSUID, lines)
		self.assertIn(BSUID[-4:], lines)

	def test_no_identity_still_dropped(self):
		import json
		body = json.loads((FIXTURES / "bsuid_only.json").read_text())
		del body["entry"][0]["changes"][0]["value"]["messages"][0]["from_user_id"]
		self.assertEqual(parse(body=json.dumps(body).encode()).messages, ())


class TestLookups(unittest.TestCase):
	def test_sender_key_normalization_keeps_bsuid(self):
		self.assertEqual(gateway_service._normalize_sender_for_provider("WhatsApp", "Sender", BSUID), BSUID)

	def test_is_opted_out_queries_bsuid_verbatim(self):
		gw = SimpleNamespace(name="gw", provider="WhatsApp")
		def get_all(doctype, **kw):
			return [] if doctype == "Gateway Event" else ["row"]

		with patch.object(gateway_service.frappe, "get_all", side_effect=get_all) as ga:
			self.assertTrue(gateway_service.is_opted_out(gw, BSUID))
		self.assertEqual(ga.call_args.kwargs["filters"]["external_id"], ["in", [BSUID]])

	def test_live_sender_entry_uses_bsuid(self):
		gw = SimpleNamespace(name="gw", provider="WhatsApp")
		with patch.object(gateway_service.frappe, "get_all", return_value=[{"name": "x"}]) as ga:
			gateway_service._live_sender_entry(gw, BSUID)
		self.assertEqual(ga.call_args.kwargs["filters"]["external_id"], BSUID)
