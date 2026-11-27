"""Split / holdout node (H-W2-07, decision 5, C2)."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine
from huf.ai.flow.tests.test_flow_draft_validation import _graph
from huf.ai.flow.catalog import node_registry
from huf.ai.flow.nodes import send, split
from huf.ai.flow.support import reason_codes, step_keys
from huf.ai.graph.executor import GraphContext
from huf.ai.graph.validator import MODE_DRAFT, validate_flow_graph

NODE = {"id": "sp1", "type": "split"}
CONFIG = {
	"options": [
		{"label": "A", "node_id": "a", "weight": 70},
		{"label": "B", "node_id": "b", "weight": 30},
	],
	"holdout": 10,
}


def run_doc(member_key="m1", version="3"):
	return SimpleNamespace(name="RUN-1", flow_id="flow-1", flow_version=version, member_key=member_key)


class TestSplitNode(IntegrationTestCase):
	def setUp(self):
		self.ctx = GraphContext()
		for patcher in (
			patch.object(engine, "_context_of", side_effect=lambda run, settings: self.ctx),
			patch.object(engine, "_persist_context"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def run_split(self, member_key="m1", config=None, node=None, version="3"):
		return split.exec_split(run_doc(member_key, version), node or NODE, config or CONFIG, {})

	def test_same_member_same_branch_across_runs(self):
		first = self.run_split("member-42")
		for _ in range(3):
			self.ctx = GraphContext()  # a new run
			again = self.run_split("member-42")
			self.assertEqual(again["next_node_id"], first["next_node_id"])
			self.assertEqual(again["output"], first["output"])

	def test_bucket_formula_matches_contract(self):
		import hashlib

		expected = int.from_bytes(hashlib.sha256(b"3|m1").digest()[:8], "big") % 10000
		self.assertEqual(split.bucket_of("3", "m1"), expected)
		self.assertEqual(self.run_split()["output"]["bucket"], expected)

	def test_weights_hold_over_100k_members(self):
		branches, held = Counter(), 0
		options = CONFIG["options"]
		n = 100_000
		for i in range(n):
			key = f"m{i}"
			branches[split.pick_branch(options, split.bucket_of("3|arm|sp1", key))["label"]] += 1
			held += split.bucket_of("3", key) < 1000
		self.assertAlmostEqual(branches["A"] / n, 0.70, delta=0.01)
		self.assertAlmostEqual(branches["B"] / n, 0.30, delta=0.01)
		self.assertAlmostEqual(held / n, 0.10, delta=0.01)

	def test_run_flag_stored_once_in_context_not_member_vars(self):
		result = self.run_split()
		stored = self.ctx.data[split.SPLIT_KEY]
		self.assertEqual(
			stored,
			{"holdout": result["output"]["holdout"], "bucket": result["output"]["bucket"], "node_id": "sp1"},
		)
		self.run_split(node={"id": "sp2", "type": "split"}, config={**CONFIG, "holdout": 100})
		self.assertEqual(self.ctx.data[split.SPLIT_KEY]["node_id"], "sp1")  # first split wins

	def test_reentry_is_rebucketed_fresh(self):
		self.run_split(config={**CONFIG, "holdout": 100})
		self.assertTrue(split.is_holdout(self.ctx.data))
		self.ctx = GraphContext()  # re-entry: a new run, nothing carried from the last one
		self.assertFalse(split.is_holdout(self.ctx.data))
		self.run_split(config={**CONFIG, "holdout": 0})
		self.assertFalse(split.is_holdout(self.ctx.data))

	def test_no_member_fails(self):
		self.assertEqual(self.run_split(member_key=None)["status"], "failed")

	def test_weights_not_summing_to_100_fail_draft_validation(self):
		graph = _graph(
			[
				{
					"id": "sp1",
					"type": "split",
					"config": {
						"options": [
							{"label": "A", "node_id": "a", "weight": 60},
							{"label": "B", "node_id": "b", "weight": 30},
						]
					},
				},
				{"id": "a", "type": "output", "config": {}},
				{"id": "b", "type": "output", "config": {}},
			],
			entry="sp1",
		)
		result = validate_flow_graph(graph, mode=MODE_DRAFT)
		self.assertIn("SPLIT_WEIGHTS", [e.code for e in result.errors])
		graph["nodes"][0]["config"]["options"][0]["weight"] = 70
		result = validate_flow_graph(graph, mode=MODE_DRAFT)
		self.assertEqual([e for e in result.errors if e.code == "SCHEMA"], [])
		self.assertNotIn("SPLIT_WEIGHTS", [e.code for e in result.errors])

	def test_registered_and_embeddable(self):
		self.assertIn("split", engine._NODE_EXECUTORS)
		self.assertIn("split", node_registry.EMBED_BUILTIN_TYPES)
		self.assertIn("split", node_registry.embed_builtin_types())
		self.assertIn(split.HOLDOUT_NO_CONTACT, reason_codes.HUF_CODES)
		self.assertFalse(node_registry.NodeCallContext({}, {}, "r", None, None, False, None).holdout)


class TestHoldoutSend(IntegrationTestCase):
	def setUp(self):
		self.ctx = GraphContext()
		self.ctx.data[split.SPLIT_KEY] = {"holdout": True, "bucket": 5, "node_id": "sp1"}
		for patcher in (
			patch.object(engine, "_context_of", return_value=self.ctx),
			patch.object(engine, "_persist_context"),
			patch.object(engine, "_transition_run", return_value=True),
			patch.object(send, "channel_of", return_value="whatsapp"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def send(self, category):
		node = step_keys.with_key({"id": "s1", "type": "send.message", "next": "n2"}, frappe.generate_hash())
		config = {"gateway": "gw", "recipient": "+919876543210", "template": "promo", "category": category}
		return send.exec_send_message(run_doc(), node, config, {})

	def test_marketing_send_suppressed_and_continues(self):
		with patch.object(send.guard, "evaluate") as evaluate:
			result = self.send("marketing")
		evaluate.assert_not_called()
		self.assertEqual(result["output"], {"status": "blocked", "reason": "holdout_no_contact"})
		self.assertEqual(result["next_node_id"], "n2")

	def test_service_send_still_runs(self):
		with patch.object(
			send.guard,
			"evaluate",
			return_value=SimpleNamespace(defer_until=None, allowed=False, reason="no_opt_in"),
		) as evaluate:
			result = self.send("service")
		evaluate.assert_called_once()
		self.assertEqual(result["output"]["reason"], "no_opt_in")
