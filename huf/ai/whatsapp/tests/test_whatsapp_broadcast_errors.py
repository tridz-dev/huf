"""Broadcast additions to whatsapp_errors (pure Python)."""

import importlib
import importlib.util
import os
import unittest


def _load():
	try:
		return importlib.import_module("huf.ai.gateway_adapters.whatsapp_errors")
	except Exception:
		path = os.path.join(os.path.dirname(__file__), "..", "..", "gateway_adapters", "whatsapp_errors.py")
		spec = importlib.util.spec_from_file_location("whatsapp_errors", path)
		mod = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(mod)
		return mod


we = _load()


def body(code):
	return {"error": {"message": "m", "code": code}}


class TestBroadcastErrors(unittest.TestCase):
	def test_131050_permanent_marketing_stop(self):
		c = we.classify(body(131050))
		self.assertEqual(c["code"], 131050)
		self.assertTrue(we.is_permanent(c))
		self.assertFalse(we.should_retry(c, 1))
		self.assertTrue(we.is_marketing_stop(131050))
		self.assertFalse(we.is_marketing_stop(131049))
		self.assertIsNone(we.backoff_seconds(c, 1))

	def test_135000_pacing_dropped_not_retryable(self):
		c = we.classify(body(135000))
		self.assertEqual(c["kind"], "pacing_dropped")
		self.assertFalse(c["retryable"])
		self.assertIn("pacing_dropped", we.KINDS)
		self.assertTrue(we.is_pause_signal(c))

	def test_is_pause_signal(self):
		for code in (132015, 135000, 132016, 131042):
			self.assertTrue(we.is_pause_signal(code), code)
		for code in (131050, 131049, 130429, 131056, None, "x"):
			self.assertFalse(we.is_pause_signal(code), code)

	def test_should_defer_24h(self):
		self.assertTrue(we.should_defer_24h(131049))
		self.assertTrue(we.should_defer_24h(we.classify(body(131049))))
		self.assertFalse(we.should_defer_24h(131050))
		self.assertFalse(we.should_defer_24h(None))

	def test_existing_retry_codes_unchanged(self):
		for code in (130429, 131056, 131057):
			self.assertTrue(we.classify(body(code))["retryable"])
