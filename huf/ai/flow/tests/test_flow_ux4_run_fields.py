"""Run story fields on the Flow Run payloads (UX-4): outcome, input hint, step meta.

  python -m pytest huf/ai/flow/tests/test_flow_ux4_run_fields.py   (pure logic: no bench needed)
"""

import unittest

from huf.ai.flow.runs.shape import compute_outcome, input_hint, step_meta_from

DEFN = {
	"nodes": [
		{"id": "t", "type": "trigger.webhook", "config": {}},
		{"id": "loop", "type": "foreach", "config": {"body": ["a", "b"]}},
		{"id": "ok", "type": "output", "config": {"outcome": {"label": "Order shipped", "tone": "GOOD"}}},
		{"id": "bad", "type": "output", "config": {"outcome": {"label": "Refused", "tone": "odd"}}},
		{"id": "plain", "type": "output", "config": {"value": "x"}},
	]
}


class TestStepMeta(unittest.TestCase):
	def test_types_loop_body_and_end_outcomes(self):
		meta = step_meta_from(DEFN)
		self.assertEqual(meta["t"], {"type": "trigger.webhook"})
		self.assertEqual(meta["loop"]["body"], ["a", "b"])
		self.assertEqual(meta["ok"]["outcome"], {"label": "Order shipped", "tone": "good"})
		self.assertEqual(meta["bad"]["outcome"]["tone"], "neutral")
		self.assertNotIn("outcome", meta["plain"])

	def test_pinned_definition_wraps_the_graph(self):
		self.assertIn("t", step_meta_from({"fingerprint": "x", "graph": DEFN}))

	def test_nodes_as_a_dict_and_garbage(self):
		self.assertIn("a", step_meta_from({"nodes": {"a": {"type": "transform"}}}))
		self.assertEqual(step_meta_from(None), {})


class TestOutcome(unittest.TestCase):
	def _ctx(self, decision):
		return {"__node_outputs__": {"h": {"decision": decision, "decided_by": "ana"}, "end": "x"}}

	def test_rejection_reads_as_rejected_not_plain_success(self):
		self.assertEqual(compute_outcome("Success", "end", self._ctx("rejected"), {}), {"label": "Rejected", "tone": "bad"})
		self.assertEqual(compute_outcome("Success", "end", self._ctx("approved"), {})["tone"], "good")
		self.assertEqual(compute_outcome("Success", "end", self._ctx("timeout"), {})["label"], "Timed out")

	def test_end_step_outcome_wins(self):
		meta = step_meta_from(DEFN)
		self.assertEqual(compute_outcome("Success", "ok", self._ctx("rejected"), meta)["label"], "Order shipped")

	def test_no_outcome_without_approval_or_for_unfinished_runs(self):
		self.assertIsNone(compute_outcome("Success", "end", {"__node_outputs__": {"a": 1}}, {}))
		self.assertIsNone(compute_outcome("Failed", "end", self._ctx("rejected"), {}))
		self.assertIsNone(compute_outcome("Success", "end", None, {}))


class TestInputHint(unittest.TestCase):
	def test_two_facts_in_plain_words(self):
		self.assertEqual(input_hint({"order_total": 150, "customer-name": "Ada", "extra": 1}), "order total 150, customer name Ada")

	def test_skips_internal_secret_empty_and_nested(self):
		ctx = {"__node_outputs__": {"a": 1}, "api_key": "k", "note": "  ", "items": [1, 2], "ok": True}
		self.assertEqual(input_hint(ctx), "ok yes")

	def test_skips_what_the_engine_adds_to_scheduled_runs(self):
		ctx = {"scheduled_for": "2026-10-30 06:35:00", "trigger_node": "empty_trigger", "due": "2026-10-30", "amount": 5}
		self.assertEqual(input_hint(ctx), "amount 5")

	def test_rich_text_values_read_as_plain_words(self):
		html = '<div class="ql-editor read-mode"><p>Order &amp; <b>delivery</b></p></div>'
		self.assertEqual(input_hint({"description": html}), "description Order & delivery")

	def test_empty_and_long(self):
		self.assertEqual(input_hint({}), "")
		self.assertEqual(input_hint(None), "")
		self.assertLessEqual(len(input_hint({"a": "x" * 200})), 70)
