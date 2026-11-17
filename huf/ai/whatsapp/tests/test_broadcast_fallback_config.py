# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""HUFCRM-04/03: failover config validation and carousel defaults merge (pure logic, no site fixtures needed)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.whatsapp.broadcast import failover, fallback_config, params, recipients


class TestFallbackConfig(FrappeTestCase):
	def test_channels_ordered_subset(self):
		self.assertEqual(fallback_config.clean({"fallback_channels": ["email", "sms"]})["fallback_channels"], '["email", "sms"]')
		self.assertEqual(fallback_config.clean({"fallback_channels": '["sms"]'})["fallback_channels"], '["sms"]')
		self.assertIsNone(fallback_config.clean({"fallback_channels": []})["fallback_channels"])
		for bad in (["whatsapp"], ["sms", "sms"], "not json", {"a": 1}):
			with self.assertRaises(ValueError):
				fallback_config.clean({"fallback_channels": bad})

	def test_kind_marketing_or_transactional_only(self):
		self.assertEqual(fallback_config.clean({"fallback_body_kind": "Transactional"})["fallback_body_kind"], "transactional")
		for bad in ("otp", "utility", "x"):
			with self.assertRaises(ValueError):
				fallback_config.clean({"fallback_body_kind": bad})

	def test_gateway_must_exist_and_be_readable(self):
		with self.assertRaises(ValueError):
			fallback_config.clean({"fallback_sms_gateway": "no-such-gateway"})
		with patch.object(frappe.db, "exists", return_value=True), patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				fallback_config.clean({"fallback_email_gateway": "G1"})
		with patch.object(frappe.db, "exists", return_value=True), patch.object(frappe, "has_permission", return_value=True):
			self.assertEqual(fallback_config.clean({"fallback_email_gateway": "G1"})["fallback_email_gateway"], "G1")

	def test_body_required_with_channels(self):
		self.assertTrue(fallback_config.check_complete('["sms"]', ""))
		self.assertIsNone(fallback_config.check_complete('["sms"]', "hi"))
		self.assertIsNone(fallback_config.check_complete(None, ""))

	def test_row_fallback_copy_and_email(self):
		cfg = {"fallback_channels": '["sms","email"]', "fallback_body": "hi", "fallback_body_kind": "marketing"}
		out, problem = recipients._row_fallback({"recipient": "1", "params": {"fallback_email": "A@B.co"}}, cfg)
		self.assertIsNone(problem)
		self.assertEqual((out["fallback_email"], out["fallback_body"]), ("a@b.co", "hi"))
		_o, problem = recipients._row_fallback({"recipient": "1", "fallback_email": "nope"}, cfg)
		self.assertIn("fallback_email", problem)
		_o, problem = recipients._row_fallback({"recipient": "1", "fallback_body": ""}, {"fallback_channels": '["sms"]'})
		self.assertTrue(problem)

	def test_transactional_skips_marketing_opt_in(self):
		seen = []

		def consent(ch, to, purpose="marketing"):
			seen.append(purpose)
			return True, "ok"

		ok = lambda *_a: {"ok": True, "id": "1", "status": "sent", "error": None}  # noqa: E731
		with patch("huf.ai.channels.channel_consent.has_consent", consent):
			failover.run_chain(["sms"], phone="1555", email=None, body="x", body_kind="transactional", senders={"sms": ok})
			failover.run_chain(["sms"], phone="1555", email=None, body="x", body_kind="marketing", senders={"sms": ok})
		self.assertEqual(seen, ["utility", "marketing"])


class TestCarouselMerge(FrappeTestCase):
	def test_recipient_cards_override_default_per_card(self):
		default = [{"header": {"link": "https://a/1.jpg"}, "body": ["d1"]}, {"header": {"link": "https://a/2.jpg"}, "body": ["d2"]}]
		mine = [{"body": ["m1"]}]
		merged = params.merge_carousel(default, {"cards": mine})
		self.assertEqual(merged[0], {"header": {"link": "https://a/1.jpg"}, "body": ["m1"]})
		self.assertEqual(merged[1], default[1])

	def test_either_side_empty(self):
		cards = [{"header": {"link": "https://a/1.jpg"}}, {"header": {"link": "https://a/2.jpg"}}]
		self.assertEqual(params.merge_carousel(cards, None), cards)
		self.assertEqual(params.merge_carousel(None, cards), cards)
		self.assertIsNone(params.merge_carousel(None, None))


class TestNoneIsUnset(FrappeTestCase):
	def test_none_channels_means_no_fallback(self):
		self.assertIsNone(fallback_config.clean({"fallback_channels": None})["fallback_channels"])
