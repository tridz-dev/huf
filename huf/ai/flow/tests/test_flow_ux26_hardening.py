"""UX-26: owner check when the meta key is gone, gate fails closed on unresolved actions, error redaction, wider token patterns."""

import json
import time
import unittest
from unittest.mock import patch

from huf.ai.flow.support.trigger_sample import MASK, hide_secret_values, redact_sample
from huf.ai.flow.testrun import gate, step_sample, step_test_api as api
from huf.ai.flow.testrun import step_test as st

TOKEN = "a" * 32


class TestPollNeedsMeta(unittest.TestCase):
	def test_result_without_meta_is_not_returned(self):
		def fake_get(key):
			return None if key.endswith(":meta") else json.dumps({"status": "success", "output": {"secret": "x"}})

		with patch.object(api.frappe, "cache") as cache:
			cache.return_value.get.side_effect = fake_get
			out = api.get_step_test_result(TOKEN)
		self.assertEqual(out["status"], "failed")
		self.assertIn("no longer available", out["error"])
		self.assertNotIn("secret", json.dumps(out))


class TestGateUnresolvedAction(unittest.TestCase):
	def test_reference_action_that_cannot_be_resolved_is_simulated(self):
		node = {"type": "tool.call", "config": {"tool_id": "ERPNext", "input": {"action": {"$from": "input.a"}}}}

		def boom(_value):
			raise RuntimeError("cannot resolve")

		with patch.object(gate, "effect_for_call", return_value="reads"):
			out = gate.simulate_node(node, boom)
		self.assertIsNotNone(out)
		self.assertTrue(out["simulated"])

	def test_literal_read_still_runs(self):
		node = {"type": "tool.call", "config": {"tool_id": "ERPNext", "input": {"action": "get"}}}
		with patch.object(gate, "effect_for_call", return_value="reads"):
			self.assertIsNone(gate.simulate_node(node, lambda v: v))


class TestFailureRedaction(unittest.TestCase):
	def test_error_text_hides_tokens(self):
		out = st._failure({"id": "n", "type": "tool.call"}, "401 for Bearer abcdefghijklmnopqrstuv and sk_live_abcdefghijklmnop1234", time.monotonic())
		self.assertNotIn("abcdefghijklmnopqrstuv", out["error"])
		self.assertNotIn("sk_live_", out["error"])
		self.assertIn(MASK, out["error"])


class TestWiderPatterns(unittest.TestCase):
	def test_values(self):
		for v in ("sk_live_abcdefghijklmnop1234", "rk_live_abcdefghijklmnop1234", "AKIAABCDEFGHIJKLMNOP", "xapp-1-A0123-456789-abcdef"):
			self.assertEqual(hide_secret_values(f"x {v} y"), f"x {MASK} y", v)

	def test_keys_in_both_paths(self):
		body = {"pwd": "a", "signing_key": "b", "client_key": "c", "name": "ok"}
		for safe in (redact_sample(body), step_sample.redact_output(body)[0]):
			self.assertEqual([safe[k] for k in ("pwd", "signing_key", "client_key")], [MASK] * 3)
			self.assertEqual(safe["name"], "ok")
