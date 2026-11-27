"""``knowledge.search`` node: top_k, run-user permission, kill switch, masked trace."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.nodes import knowledge as node_mod
from huf.ai.run_budget import AI_DISABLED

SOURCE = "Flow KS Test Source"
PHONE = "+14155550123"


class _Ctx:
	def __init__(self, values):
		self.values = values

	def resolve(self, value):
		if isinstance(value, str) and value.startswith("$"):
			return self.values.get(value[1:])
		return value


def _rows(query, knowledge_source, top_k, filters):
	return [
		{"text": f"passage {i}", "title": "T", "score": 1.0 / (i + 1), "source": knowledge_source,
		 "chunk_id": f"c{i}", "ref": f"r{i}", "metadata": {"x": 1}}
		for i in range(10)
	][:top_k]


class TestFlowKnowledgeSearch(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Knowledge Source", SOURCE):
			frappe.get_doc({
				"doctype": "Knowledge Source", "source_name": SOURCE, "scope": "Global",
				"storage_mode": "Frappe File", "knowledge_type": "sqlite_fts", "status": "Ready",
				"chunk_size": 512, "chunk_overlap": 50,
			}).insert(ignore_permissions=True)

	def _run(self, config, ctx_values=None, run_ctx=None):
		ctx = _Ctx(ctx_values or {"q": f"refund for {PHONE}"})
		with patch.object(node_mod, "knowledge_search", side_effect=_rows) as search:
			out = node_mod.exec_knowledge_search({"id": "k1"}, config, ctx, run_ctx)
		return out, search

	def test_top_k_respected_and_passages_have_source_ids(self):
		out, search = self._run({"query": "$q", "knowledge_source": SOURCE, "top_k": 3})
		self.assertEqual(out["status"], "success")
		passages = out["output"]["passages"]
		self.assertEqual(len(passages), 3)
		self.assertTrue(all(p["source"] == SOURCE and p["chunk_id"] for p in passages))
		self.assertEqual(search.call_args.kwargs["top_k"], 3)

	def test_top_k_out_of_range_fails(self):
		out, search = self._run({"query": "$q", "knowledge_source": SOURCE, "top_k": 500})
		self.assertEqual(out["status"], "failed")
		search.assert_not_called()

	def test_no_permission_gives_clear_error(self):
		with patch.object(node_mod.frappe, "has_permission", return_value=False):
			out, search = self._run({"query": "$q", "knowledge_source": SOURCE})
		self.assertEqual(out["status"], "failed")
		self.assertIn("permission", out["error"])
		self.assertIn(SOURCE, out["error"])
		search.assert_not_called()

	def test_missing_source_fails(self):
		out, _ = self._run({"query": "$q", "knowledge_source": "No Such Source KS"})
		self.assertEqual(out["status"], "failed")

	def test_trace_result_has_no_raw_query_pii(self):
		out, _ = self._run({"query": "$q", "knowledge_source": SOURCE, "top_k": 2})
		trace = frappe.as_json(out["result"])
		self.assertNotIn(PHONE, trace)
		self.assertNotIn("refund for", trace)
		self.assertEqual(len(out["result"]["passages"]), 2)

	def test_site_kill_switch_blocks_search(self):
		with patch.object(node_mod, "assert_ai_enabled",
				side_effect=node_mod.AIDisabled(AI_DISABLED)):
			out, search = self._run({"query": "$q", "knowledge_source": SOURCE})
		self.assertEqual(out["status"], "failed")
		self.assertEqual(out["reason_code"], AI_DISABLED)
		search.assert_not_called()

	def test_spent_run_budget_blocks_search(self):
		class _Budget:
			def check_deadline(self):
				raise node_mod.RunBudgetExceeded("Run budget deadline exceeded")

		out, search = self._run({"query": "$q", "knowledge_source": SOURCE},
			run_ctx=SimpleNamespace(budget=_Budget()))
		self.assertEqual(out["reason_code"], "run_budget_exceeded")
		search.assert_not_called()

	def test_unknown_config_key_fails(self):
		out, _ = self._run({"query": "$q", "knowledge_source": SOURCE, "bogus": 1})
		self.assertEqual(out["status"], "failed")
