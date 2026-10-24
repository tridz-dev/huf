# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Referral tag and button payload extraction on inbound WhatsApp messages."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters.whatsapp_inbound import extract_referral_tag, parse_button_payload
from huf.ai.whatsapp.tests.test_whatsapp_contract import WhatsAppContractBase


class TestPureHelpers(unittest.TestCase):
	def test_source_id_wins(self):
		self.assertEqual(extract_referral_tag({"referral": {"source_id": "123"}}, "ref:abc"), "123")

	def test_ref_token_case_insensitive_first_wins(self):
		self.assertEqual(extract_referral_tag({}, "hi REF:Spring_Sale-1 and ref:other"), "Spring_Sale-1")

	def test_no_hash_tag_and_empty(self):
		self.assertEqual(extract_referral_tag({}, "#spring"), "")
		self.assertEqual(extract_referral_tag({}, ""), "")
		self.assertEqual(extract_referral_tag({}, "ref:"), "")

	def test_tag_capped_at_64(self):
		self.assertEqual(extract_referral_tag({}, "ref:" + "a" * 70), "a" * 64)

	def test_parse_button_payload(self):
		self.assertEqual(parse_button_payload("sol:orders|track"), {"solution": "orders", "free": "track"})
		self.assertEqual(parse_button_payload("sol:orders"), {"solution": "orders", "free": ""})
		self.assertEqual(parse_button_payload("sol:a|b|c"), {"solution": "a", "free": "b|c"})
		for bad in ("CONFIRM_ORDER", "sol:", "sol:|x", "", None):
			self.assertIsNone(parse_button_payload(bad))


class TestNormalizedRaw(WhatsAppContractBase):
	def raw(self, name):
		return self.parse(name).messages[0].raw_payload

	def test_ctwa_source_id(self):
		event = self.parse("text_ctwa_referral.json").messages[0]
		self.assertEqual(event.raw_payload["referral_tag"], "123")
		self.assertEqual(event.raw_payload["referral"]["source_id"], "123")
		self.assertTrue(event.message_text.startswith("[Ad referral: Summer sale]"))

	def test_ref_token_in_text(self):
		event = self.parse("text_ref_tag.json").messages[0]
		self.assertEqual(event.raw_payload["referral_tag"], "spring_sale")
		self.assertIn("ref:spring_sale", event.message_text)

	def test_plain_text_has_no_tag(self):
		raw = self.raw("text_inbound.json")
		self.assertNotIn("referral_tag", raw)
		self.assertNotIn("button_payload", raw)

	def test_template_button_payload(self):
		self.assertEqual(self.raw("button_quick_reply.json")["button_payload"], "CONFIRM_ORDER")
		self.assertEqual(self.raw("button_sol_payload.json")["button_payload"], "sol:orders|track")

	def test_interactive_reply_id(self):
		self.assertEqual(self.raw("interactive_button_reply.json")["button_payload"], "approve_leave_42")
