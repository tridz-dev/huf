"""``doc.get`` and ``doc.update`` nodes (flow/nodes/docops.py): read or change one document as the run user."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext, PinnedVersion


class _Run:
	flow_id = "f"
	name = "FR-1"


def _settings(data=None, max_writes=5, read=({"doctype": "ToDo"},), write=({"doctype": "ToDo"},)):
	envelope = {"read": list(read), "write": list(write), "http": "none", "code": "none"}
	graph = {
		"schema_version": "1.0.0", "profile": "flow", "entry": "n", "nodes": [],
		"contract": {"limits": {"max_writes": max_writes}, "permission_envelope": envelope},
	}
	return flow_engine.FlowRunContext(context=GraphContext(data or {}), version=PinnedVersion.pin(graph))


def _get(config, data=None, settings=None):
	node = {"id": "n", "type": "doc.get", "config": config}
	return flow_engine._exec_doc_get(_Run(), node, config, settings if settings is not None else _settings(data))


def _update(config, data=None, settings=None):
	node = {"id": "n", "type": "doc.update", "config": config}
	return flow_engine._exec_doc_update(_Run(), node, config, settings if settings is not None else _settings(data))


class TestDocOpsNodes(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "flow doc ops test", "status": "Open", "priority": "Low"}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.rollback)

	def test_get_returns_fields_only_allowed(self):
		result = _get({"doctype": "ToDo", "name": self.todo.name, "fields": ["description", "status"]})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["output"], {"doc": {"description": "flow doc ops test", "status": "Open"}})
		bad = _get({"doctype": "ToDo", "name": self.todo.name, "fields": ["no_such_field"]})
		self.assertEqual(bad["status"], "failed")
		table = _get({"doctype": "ToDo", "name": self.todo.name, "fields": ["allocated_to", "nonexistent"]})
		self.assertEqual(table["status"], "failed")

	def test_get_by_filter_and_not_allowed_doctype(self):
		result = _get({"doctype": "ToDo", "filters": {"description": "flow doc ops test"}, "fields": ["status"]})
		self.assertEqual(result["output"], {"doc": {"status": "Open"}})
		denied = _get({"doctype": "ToDo", "name": self.todo.name}, settings=_settings(read=()))
		self.assertEqual(denied["status"], "failed")

	def test_get_missing_error_vs_empty(self):
		missing = {"doctype": "ToDo", "filters": {"description": "no such todo xyz"}}
		self.assertEqual(_get(missing)["status"], "failed")
		empty = _get({**missing, "on_missing": "empty"})
		self.assertEqual(empty["status"], "success")
		self.assertEqual(empty["output"], {"found": False})

	def test_update_sets_fields(self):
		result = _update(
			{"doctype": "ToDo", "name": self.todo.name, "values": {"status": "Closed", "priority": "High"}}
		)
		self.assertEqual(result["status"], "success", result)
		self.assertEqual(result["output"], {"doctype": "ToDo", "name": self.todo.name})
		row = frappe.db.get_value("ToDo", self.todo.name, ["status", "priority"], as_dict=True)
		self.assertEqual(row, {"status": "Closed", "priority": "High"})

	def test_update_permission_denied(self):
		def only_read(doctype, ptype="read", *args, **kwargs):
			return ptype == "read"

		with patch("frappe.has_permission", side_effect=only_read):
			result = _update({"doctype": "ToDo", "name": self.todo.name, "values": {"status": "Closed"}})
		self.assertEqual(result["status"], "failed")
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "status"), "Open")
		no_envelope = _update(
			{"doctype": "ToDo", "name": self.todo.name, "values": {"status": "Closed"}},
			settings=_settings(write=()),
		)
		self.assertEqual(no_envelope["status"], "failed")

	def test_update_unknown_field_rejected(self):
		result = _update({"doctype": "ToDo", "name": self.todo.name, "values": {"no_such_field": "x"}})
		self.assertEqual(result["status"], "failed")
		self.assertIn("no_such_field", result["error"])
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "status"), "Open")
