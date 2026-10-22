"""Keyboard builders and signed callback_data."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters import telegram_keyboards as kb


class TestCallbackSigning(unittest.TestCase):
	def setUp(self):
		self.key = kb.derive_callback_key("gateway-secret")

	def test_round_trip_within_64_bytes(self):
		signed = kb.sign_callback(self.key, "approve:42", context="111")
		self.assertLessEqual(len(signed.encode()), 64)
		self.assertEqual(kb.verify_callback(self.key, signed, context="111"), "approve:42")

	def test_max_payload_fits_exactly(self):
		payload = "x" * kb.MAX_PAYLOAD_BYTES
		self.assertEqual(len(kb.sign_callback(self.key, payload).encode()), 64)
		with self.assertRaises(ValueError):
			kb.sign_callback(self.key, payload + "x")

	def test_payload_with_separator_round_trips(self):
		self.assertEqual(kb.verify_callback(self.key, kb.sign_callback(self.key, "a|b|c")), "a|b|c")

	def test_tamper_rejected(self):
		signed = kb.sign_callback(self.key, "approve:42")
		self.assertIsNone(kb.verify_callback(self.key, signed.replace("approve:42", "approve:43")))
		self.assertIsNone(kb.verify_callback(self.key, signed[:-1] + ("A" if signed[-1] != "A" else "B")))
		for bad in ("", "approve:42", "|", "approve:42|short", None):
			self.assertIsNone(kb.verify_callback(self.key, bad))

	def test_wrong_key_or_context_rejected(self):
		signed = kb.sign_callback(self.key, "go", context="111")
		self.assertIsNone(kb.verify_callback(kb.derive_callback_key("other"), signed, context="111"))
		self.assertIsNone(kb.verify_callback(self.key, signed, context="222"))

	def test_empty_secret_refused(self):
		with self.assertRaises(ValueError):
			kb.derive_callback_key("")


class TestKeyboards(unittest.TestCase):
	def test_inline_keyboard(self):
		markup = kb.inline_keyboard([[kb.callback_button("Yes", "y|sig"), kb.url_button("Docs", "https://x")], []])
		self.assertEqual(
			markup,
			{"inline_keyboard": [[{"text": "Yes", "callback_data": "y|sig"}, {"text": "Docs", "url": "https://x"}]]},
		)
		self.assertEqual(kb.web_app_button("App", "https://a")["web_app"], {"url": "https://a"})

	def test_callback_button_enforces_limit(self):
		with self.assertRaises(ValueError):
			kb.callback_button("x", "y" * 65)

	def test_reply_keyboard(self):
		markup = kb.reply_keyboard([["A", "B"], [{"text": "Share", "request_contact": True}]], one_time=True, placeholder="pick")
		self.assertEqual(markup["keyboard"][0], [{"text": "A"}, {"text": "B"}])
		self.assertTrue(markup["one_time_keyboard"])
		self.assertEqual(markup["input_field_placeholder"], "pick")
		self.assertEqual(kb.remove_keyboard(), {"remove_keyboard": True})
		self.assertEqual(kb.force_reply(), {"force_reply": True})
