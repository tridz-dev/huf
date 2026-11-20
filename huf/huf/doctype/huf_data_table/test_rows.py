"""Integration tests for rows.py (need a real bench; run with `bench run-tests`)."""

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.huf_data_table.api import (
	create_data_table,
	delete_data_table,
	get_table_records,
	update_data_table,
)
from huf.huf.doctype.huf_data_table.rows import (
	bulk_delete_rows,
	bulk_insert_rows,
	bulk_update_rows,
	get_table_dependencies,
	get_table_tool_signature,
	list_tables_summary,
	restore_rows,
)


class TestRows(IntegrationTestCase):
	TABLE = "Test Rows Table"
	DT = f"HF {TABLE}"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if frappe.db.exists("DocType", cls.DT):
			delete_data_table(frappe.db.get_value("Huf Data Table", {"doctype_name": cls.DT}))
		create_data_table(
			table_name=cls.TABLE,
			fields=[{"label": "Title", "fieldtype": "Data", "reqd": 1}, {"label": "Qty", "fieldtype": "Int"}],
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		name = frappe.db.get_value("Huf Data Table", {"doctype_name": cls.DT})
		if name:
			delete_data_table(name)
			frappe.db.commit()
		super().tearDownClass()

	def test_bulk_insert_reports_row_errors(self):
		res = bulk_insert_rows(self.DT, [{"title": "a", "qty": 1}, {"qty": 2}])
		self.assertEqual(len(res["inserted"]), 1)
		self.assertEqual(res["errors"][0]["index"], 1)

	def test_update_delete_restore(self):
		names = bulk_insert_rows(self.DT, [{"title": "u1"}, {"title": "u2"}])["inserted"]
		self.assertEqual(bulk_update_rows(self.DT, names, {"qty": 9})["updated"], 2)
		self.assertEqual(bulk_delete_rows(self.DT, names)["deleted"], 2)
		self.assertEqual(restore_rows(self.DT, names)["restored"], 2)
		self.assertEqual(frappe.db.get_value(self.DT, names[0], "qty"), 9)

	def test_records_total_and_operator_guard(self):
		bulk_insert_rows(self.DT, [{"title": "t1", "qty": 5}, {"title": "t2", "qty": 6}])
		res = get_table_records(self.DT, filters='[["qty", ">=", 5]]', limit=1)
		self.assertTrue(res["hasMore"])
		self.assertGreaterEqual(res["total"], 2)
		with self.assertRaises(frappe.ValidationError):
			get_table_records(self.DT, filters='[["qty", "regexp", 5]]')

	def test_summary_dependencies_signature(self):
		reg = frappe.db.get_value("Huf Data Table", {"doctype_name": self.DT})
		self.assertTrue(any(t["name"] == reg for t in list_tables_summary()))
		self.assertEqual(get_table_dependencies(reg)["agents"], [])
		sig = get_table_tool_signature(reg)
		self.assertTrue(any(t["action"] == "create" for t in sig["tools"]))

	def test_update_resyncs_and_delete_removes_tools(self):
		name = create_data_table(table_name="Test Rows Tools", fields=[{"label": "Title", "fieldtype": "Data"}])["data"]["name"]
		dt = frappe.db.get_value("Huf Data Table", name, "doctype_name")
		from huf.huf.doctype.huf_data_table.api import _scaffold_tool, _table_tool_name

		tool = _scaffold_tool(dt, "Test Rows Tools", "Create Document", "create")
		update_data_table(name, fields=[{"label": "Title", "fieldtype": "Data"}, {"label": "Extra", "fieldtype": "Int"}])
		params = [p.fieldname for p in frappe.get_doc("Agent Tool Function", tool).parameters]
		self.assertIn("extra", params)
		delete_data_table(name)
		self.assertFalse(frappe.db.exists("Agent Tool Function", _table_tool_name(dt, "Create Document")))
