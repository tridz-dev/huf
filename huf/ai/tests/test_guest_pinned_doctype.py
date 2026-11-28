"""A Guest tool call that bypasses permissions stays on the tool's pinned doctype and its data fields."""

import asyncio
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.sdk_tools import create_function_tool
from huf.ai.tools import invocation
from huf.ai.tools.invocation import build_extra_args

TYPES = {
	"Get Value": "huf.ai.sdk_tools.handle_get_value",
	"Set Value": "huf.ai.sdk_tools.handle_set_value",
	"Submit Document": "huf.ai.sdk_tools.handle_submit_document",
	"Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
	"Create Document": "huf.ai.sdk_tools.handle_create_document",
	"Update Document": "huf.ai.sdk_tools.handle_update_document",
	"Get List": "huf.ai.sdk_tools.handle_get_list",
}


class TestGuestPinnedDoctype(IntegrationTestCase):
	def setUp(self):
		self.todo = frappe.get_doc({"doctype": "ToDo", "description": "pinned"}).insert()
		self.note = frappe.get_doc({"doctype": "Note", "title": frappe.generate_hash(), "content": "secret"}).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _call(self, tool_type, args, pin="ToDo", user="Guest"):
		"""Run the same call through both tool paths and return both results."""
		doc = {
			"name": "t_guest", "tool_name": "t_guest", "types": tool_type, "function_path": None,
			"reference_doctype": pin, "allowed_for_guest": 1, "is_alias": True,
		}
		frappe.set_user(user)
		try:
			with patch.object(invocation, "resolve_tool_doc", return_value=doc):
				flow = invocation.invoke_tool_sync("t_guest", dict(args)).as_dict()
			tool = create_function_tool(
				"t_guest", "t", TYPES[tool_type], {"type": "object", "properties": {}},
				extra_args=build_extra_args(doc), tool_type=tool_type, allowed_for_guest=True,
			)
			sdk = json.loads(asyncio.run(tool.on_invoke_tool(None, json.dumps(args))))
		finally:
			frappe.set_user("Administrator")
		return flow, sdk

	def assertRefused(self, tool_type, args, pin="ToDo"):
		flow, sdk = self._call(tool_type, args, pin)
		self.assertTrue(flow.get("denied"), (tool_type, args, flow))
		self.assertTrue(sdk.get("denied"), (tool_type, args, sdk))

	def test_unpinned_types_are_refused(self):
		note = self.note.name
		self.assertRefused("Get Value", {"doctype": "Note", "filters": note, "fieldname": "content"}, None)
		self.assertRefused("Set Value", {"doctype": "Note", "filters": note, "fieldname": "content", "value": "x"}, None)
		self.assertRefused("Submit Document", {"reference_doctype": "Note", "document_id": note}, None)
		self.assertRefused("Cancel Document", {"reference_doctype": "Note", "document_id": note}, None)
		self.assertEqual(frappe.db.get_value("Note", note, "content"), "secret")

	def test_another_doctype_is_refused(self):
		note = self.note.name
		self.assertRefused("Get Value", {"doctype": "Note", "filters": note, "fieldname": "content"})
		self.assertRefused("Set Value", {"doctype": "Note", "filters": note, "fieldname": "content", "value": "x"})
		self.assertRefused("Create Document", {"doctype": "Note", "title": "x"})
		self.assertRefused("Create Document", {"doc": {"doctype": "Note", "title": "x"}})
		self.assertEqual(frappe.db.get_value("Note", note, "content"), "secret")

	def test_system_and_foreign_fields_are_refused(self):
		name = self.todo.name
		for field in ("docstatus", "owner", "flags", "assigned_by.email"):
			self.assertRefused("Set Value", {"filters": name, "fieldname": field, "value": 1})
			self.assertRefused("Update Document", {"document_id": name, "data": {field: 1}})
			self.assertRefused("Create Document", {"description": "x", field: 1})
		self.assertRefused("Get Value", {"filters": name, "fieldname": "assigned_by.email"})
		self.assertRefused("Get Value", {"filters": {"assigned_by.email": "a"}, "fieldname": "name"})
		self.assertRefused("Get List", {"filters": [["User", "name", "like", "%"]]})
		self.assertRefused("Get List", {"order_by": "assigned_by.email desc"})

	def test_pinned_calls_still_work(self):
		name = self.todo.name
		for result in self._call("Get Value", {"filters": name, "fieldname": "description"}):
			self.assertIn("pinned", json.dumps(result))
		for result in self._call("Set Value", {"doctype": "ToDo", "filters": name, "fieldname": "description", "value": "new"}):
			self.assertNotIn("denied", result)
		self.assertEqual(frappe.db.get_value("ToDo", name, "description"), "new")
		for result in self._call("Update Document", {"document_id": name, "description": "newer"}):
			self.assertNotIn("denied", result)
		self.assertEqual(frappe.db.get_value("ToDo", name, "description"), "newer")
		for result in self._call("Create Document", {"description": "made"}):
			self.assertNotIn("denied", result)
		for result in self._call("Get List", {"filters": {"name": name}, "order_by": "modified desc"}):
			self.assertNotIn("denied", result)

	def test_signed_in_callers_are_unchanged(self):
		args = {"doctype": "Note", "filters": self.note.name, "fieldname": "content"}
		for result in self._call("Get Value", args, user="Administrator"):
			self.assertIn("secret", json.dumps(result))
