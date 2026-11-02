"""Pure tests for the webhook sample request (UX-10): redaction, the 8 KB cap and who gets to see it."""

import json
import unittest

from huf.ai.flow.support.redact import drop_webhook_secrets, hide_webhook_secrets
from huf.ai.flow.support.trigger_sample import MASK, MAX_SAMPLE_BYTES, drop_samples, redact_sample


class TestRedactSample(unittest.TestCase):
	def test_secrets_are_hidden_at_any_depth(self):
		out = redact_sample({"name": "Ada", "password": "hunter2", "auth": {"api_key": "k", "token": "t", "ok": 1}, "X-Authorization": "Bearer x"})
		self.assertEqual(out["name"], "Ada")
		self.assertEqual(out["password"], MASK)
		self.assertEqual(out["auth"], {"api_key": MASK, "token": MASK, "ok": 1})
		self.assertEqual(out["X-Authorization"], MASK)

	def test_long_text_and_lists_are_shortened(self):
		out = redact_sample({"note": "x" * 1000, "items": list(range(50))})
		self.assertEqual(len(out["note"]), 200)
		self.assertTrue(out["note"].endswith("..."))
		self.assertEqual(out["items"], list(range(20)))  # UX-24: up to 20 items are kept (it used to be 5)

	def test_whole_sample_fits_in_8kb(self):
		huge = {f"field_{i}": "y" * 190 for i in range(300)}
		out = redact_sample(huge)
		self.assertLessEqual(len(json.dumps(out).encode()), MAX_SAMPLE_BYTES)
		self.assertIn("field_0", out)

	def test_depth_is_limited(self):
		deep = cur = {}
		for _ in range(20):
			cur["n"] = {}
			cur = cur["n"]
		self.assertLessEqual(len(json.dumps(redact_sample(deep))), 400)


class TestOnlyEditorsSeeSamples(unittest.TestCase):
	graph = {"nodes": [{"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "s" * 40}, "_sample": {"email": "a@b.c"}}, {"id": "e", "type": "output", "config": {}}]}

	def test_viewer_copy_has_no_sample_and_no_secret(self):
		out = hide_webhook_secrets(self.graph)
		self.assertNotIn("_sample", out["nodes"][0])
		self.assertIsNone(out["nodes"][0]["config"]["secret"])
		self.assertEqual(self.graph["nodes"][0]["_sample"], {"email": "a@b.c"})  # stored graph untouched

	def test_run_snapshot_keeps_neither(self):
		out = drop_webhook_secrets(self.graph)
		self.assertNotIn("_sample", out["nodes"][0])
		self.assertNotIn("secret", out["nodes"][0]["config"])

	def test_drop_samples_handles_odd_shapes(self):
		self.assertEqual(drop_samples(None), None)
		self.assertEqual(drop_samples({"nodes": None}), {"nodes": None})
