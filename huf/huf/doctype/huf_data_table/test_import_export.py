"""Bench integration tests for import/export (need a site: bench run-tests --module ...)."""
import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.huf_data_table import import_export as ie
from huf.huf.doctype.huf_data_table.api import create_data_table


class TestImportExport(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		res = create_data_table(
			table_name="IE Test Table",
			fields=[
				{"label": "Title", "fieldtype": "Data", "reqd": 1},
				{"label": "Qty", "fieldtype": "Int"},
				{"label": "Status", "fieldtype": "Select", "options": "Open\nClosed"},
			],
		)
		self.table = res.get("name") if isinstance(res, dict) else res
		self.dt = frappe.db.get_value("Huf Data Table", self.table, "doctype_name")

	def _file(self, content):
		f = frappe.get_doc({"doctype": "File", "file_name": "t.csv", "content": content, "is_private": 1}).insert()
		return f.file_url

	def test_preview_reports_all_invalid_rows(self):
		url = self._file("Title,Qty,Status\n" + "\n".join(f"a{i},x,Open" for i in range(80)))
		out = ie.preview_import(self.table, url)
		self.assertEqual(len(out["invalid_rows"]), 80)

	def test_insert_update_replace(self):
		url = self._file("Title,Qty,Status\nA,1,Open\nB,2,Closed\nC,bad,Open\n")
		m = {"Title": "title", "Qty": "qty", "Status": "status"}
		r = ie.run_import(self.table, url, m, "insert")
		self.assertEqual((r["inserted"], r["rejected"]), (2, 1))
		self.assertIn("C", r["rejected_csv"])
		url2 = self._file("Title,Qty\nA,10\nZ,1\n")
		r = ie.run_import(self.table, url2, {"Title": "title", "Qty": "qty"}, "update", "title")
		self.assertEqual((r["updated"], r["rejected"]), (1, 1))
		with self.assertRaises(Exception):
			ie.run_import(self.table, url2, {"Title": "title"}, "replace")
		r = ie.run_import(self.table, url2, {"Title": "title", "Qty": "qty"}, "replace", confirm_replace=True)
		self.assertEqual(frappe.db.count(self.dt), 2)

	def test_export_leaves_no_file(self):
		before = frappe.db.count("File")
		out = ie.export_rows(self.table)
		self.assertTrue(out["content"].startswith("name,"))
		self.assertEqual(frappe.db.count("File"), before)

	def test_create_only_user_can_preview(self):
		# TODO(bench): user with only data.records.create passes _require_import
		pass
