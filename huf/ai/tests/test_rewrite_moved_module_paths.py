"""Tests for the patch that rewrites stored dotted paths of moved huf.ai modules."""

import frappe
from frappe.tests import IntegrationTestCase

from huf.patches.v1 import rewrite_moved_module_paths as patch

OLD = "huf.ai.flow_api.handle_get_flow_run"
NEW = "huf.ai.flow.api.handle_get_flow_run"


class TestRewritePath(IntegrationTestCase):
	def test_exact_prefix_is_rewritten(self):
		self.assertEqual(patch.rewrite_path(OLD), NEW)
		self.assertEqual(
			patch.rewrite_path("huf.ai.agent_integration.run_agent_sync"),
			"huf.ai.agent.integration.run_agent_sync",
		)

	def test_new_and_unrelated_paths_are_untouched(self):
		for value in (NEW, "huf.ai.tools.registry.get_x", "frappe.client.get", "huf.ai.flow_api_extra.x", "", None):
			self.assertEqual(patch.rewrite_path(value), value)

	def test_every_mapped_target_resolves(self):
		for old, new in patch.MAPPING.items():
			module = new.rstrip(".")
			__import__(module)  # the new module must exist
			self.assertNotIn(old, new)


class TestRewriteStoredRows(IntegrationTestCase):
	def setUp(self):
		self.name = "test_rewrite_moved_paths_tool"
		if frappe.db.exists("Agent Tool Function", self.name):
			frappe.delete_doc("Agent Tool Function", self.name, force=True)
		doc = frappe.get_doc(
			{
				"doctype": "Agent Tool Function",
				"name": self.name,
				"tool_name": self.name,
				"tool_type": "Miscellaneous",
				"types": "Custom Function",
				"function_path": "huf.testing.tool_testing.echo",
				"description": "rewrite patch test",
			}
		)
		doc.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Agent Tool Function", self.name, force=True)

	def _stored(self):
		return frappe.db.get_value("Agent Tool Function", self.name, "function_path")

	def test_old_row_is_rewritten_once_and_resolves(self):
		frappe.db.set_value("Agent Tool Function", self.name, "function_path", OLD, update_modified=False)
		patch.execute()
		self.assertEqual(self._stored(), NEW)
		self.assertTrue(callable(frappe.get_attr(self._stored())))
		patch.execute()  # idempotent
		self.assertEqual(self._stored(), NEW)

	def test_row_on_new_path_is_not_changed(self):
		before = frappe.db.get_value("Agent Tool Function", self.name, "modified")
		patch.execute()
		self.assertEqual(self._stored(), "huf.testing.tool_testing.echo")
		self.assertEqual(frappe.db.get_value("Agent Tool Function", self.name, "modified"), before)
