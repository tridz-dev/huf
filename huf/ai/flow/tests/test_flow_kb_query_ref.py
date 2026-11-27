"""FIX-kb-query-save: a Search knowledge step whose query is the UI's 'Use data' chip
``{"$from": "input.message"}`` saves (no 417) and the run searches the referenced text."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.engine import create_flow_run
from huf.ai.flow.engine import run_flow as engine_run_flow
from huf.ai.flow.nodes import knowledge as node_mod

SOURCE = "Flow KS Ref Test Source"
SECRET = "test-webhook-secret-0123456789abcdef"


def _definition(query):
	return {
		"version": "1.0",
		"profile": "flow",
		"entry": "start",
		"metadata": {"name": "KB ref test"},
		"nodes": [
			{"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": SECRET}, "next": "kb"},
			{"id": "kb", "type": "knowledge.search", "config": {"query": query, "knowledge_source": SOURCE, "top_k": 2}},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": {
				"max_nodes": 10, "max_rows": 10, "max_output_bytes": 100_000, "max_parallel_calls": 1,
				"max_foreach_iterations": 1, "max_external_calls": 5, "max_writes": 0,
				"max_wall_time_ms": 5000, "fail_closed": True,
			},
		},
	}


def _rows(query, knowledge_source, top_k, filters):
	return [{"text": "passage", "title": "T", "score": 1.0, "source": knowledge_source,
			 "chunk_id": "c0", "ref": "r0", "metadata": {}}][:top_k]


class TestFlowKbQueryRef(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Knowledge Source", SOURCE):
			frappe.get_doc({
				"doctype": "Knowledge Source", "source_name": SOURCE, "scope": "Global",
				"storage_mode": "Frappe File", "knowledge_type": "sqlite_fts", "status": "Ready",
				"chunk_size": 512, "chunk_overlap": 50,
			}).insert(ignore_permissions=True)

	def _save(self, query):
		flow_id = f"_test-kb-ref-{frappe.generate_hash(length=8)}"
		return flow_api.save_flow_definition(flow_id, _definition(query))["flow_id"]

	def test_reference_query_saves_and_resolves_at_run(self):
		flow_id = self._save({"$from": "input.message"})
		flow_run = create_flow_run(flow_id=flow_id, payload={"message": "where is my refund"}, trigger_type="Webhook")
		with patch.object(node_mod, "knowledge_search", side_effect=_rows) as search, \
				patch.object(node_mod, "_ai_block", return_value=None):
			engine_run_flow(flow_run.name)
		search.assert_called_once()
		self.assertEqual(search.call_args.kwargs["query"], "where is my refund")
		flow_run.reload()
		self.assertNotEqual(flow_run.status, "Failed", flow_run.last_error)

	def test_plain_text_query_still_saves(self):
		self.assertTrue(self._save("refund policy"))

	def test_malformed_reference_is_still_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._save({"$from": "input.message", "extra": 1})
