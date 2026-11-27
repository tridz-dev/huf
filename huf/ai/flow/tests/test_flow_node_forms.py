"""Editor forms for router.decision (Decision mode), knowledge.search and handoff."""

import unittest

from huf.ai.flow.catalog.fields import guaranteed_predecessors
from huf.ai.flow.nodes import handoff, knowledge
from huf.ai.flow.support.node_schemas import build_node_schemas


def _fields(schemas, node_type):
	return {f["name"]: f for f in schemas[node_type]["config_schema"]}


class TestNodeForms(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.schemas = build_node_schemas()

	def test_router_decision_has_decision_mode(self):
		fields = _fields(self.schemas, "router.decision")
		self.assertEqual(fields["decision"]["type"], "json")
		self.assertFalse(fields["decision"]["required"])
		self.assertFalse(fields["options"]["required"])
		props = self.schemas["router.decision"]["json_schema"]["properties"]["decision"]
		self.assertEqual(set(props["required"]), {"candidates", "uncertain_next"})
		self.assertFalse(self.schemas["router.decision"]["routing"]["next"])

	def test_knowledge_search_matches_module_keys(self):
		fields = _fields(self.schemas, "knowledge.search")
		self.assertEqual(set(fields), set(knowledge.KEYS))
		self.assertTrue(fields["query"]["required"] and fields["knowledge_source"]["required"])
		self.assertEqual(fields["query"]["type"], "value")
		self.assertEqual((fields["top_k"]["min"], fields["top_k"]["max"]), (1, knowledge.MAX_TOP_K))
		self.assertEqual(fields["top_k"]["default"], knowledge.DEFAULT_TOP_K)
		self.assertEqual(self.schemas["knowledge.search"]["category"], "ai")

	def test_handoff_fields(self):
		fields = _fields(self.schemas, "handoff")
		self.assertTrue({"conversation", "gateway", "recipient", "reason", "timeout_ms", "timeout_next"} <= set(fields))
		self.assertEqual(fields["timeout_next"]["type"], "node_select")
		self.assertEqual(fields["priority"]["default"], "normal")
		self.assertTrue(self.schemas["handoff"]["routing"]["next"])
		self.assertEqual(handoff.PARK_REASON, "handoff")

	def test_existing_node_types_kept(self):
		for t in ("split", "router.llm", "send.message", "condition"):
			self.assertIn(t, self.schemas)


class TestBuilderTargets(unittest.TestCase):
	def test_decision_candidates_are_edges(self):
		graph = {
			"entry": ["t"],
			"nodes": [
				{"id": "t", "type": "trigger.webhook", "next": "r"},
				{"id": "r", "type": "router.decision", "config": {"options": [], "decision": {
					"candidates": [{"node_id": "a"}, {"node_id": "b"}], "uncertain_next": "u"}}},
				{"id": "a", "type": "output"}, {"id": "b", "type": "output"}, {"id": "u", "type": "output"},
			],
		}
		for nid in ("a", "b", "u"):
			self.assertEqual(guaranteed_predecessors(graph, nid), {"t", "r"})

	def test_handoff_timeout_next_is_edge(self):
		graph = {
			"entry": ["t"],
			"nodes": [
				{"id": "t", "type": "trigger.webhook", "next": "h"},
				{"id": "h", "type": "handoff", "config": {"timeout_next": "late"}},
				{"id": "late", "type": "output"},
			],
		}
		self.assertEqual(guaranteed_predecessors(graph, "late"), {"t", "h"})


if __name__ == "__main__":
	unittest.main()
