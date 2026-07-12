# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestHufDataTable(HufTestSuite):
	def test_doctype_name_derived_from_table_name(self):
		table = frappe.get_doc({
			"doctype": "Huf Data Table",
			"table_name": "_Test Widgets",
		}).insert(ignore_permissions=True)

		self.assertEqual(table.doctype_name, "HF _Test Widgets")

	def test_creation_applies_defaults(self):
		table = frappe.get_doc({
			"doctype": "Huf Data Table",
			"table_name": "_Test Defaults Table",
		}).insert(ignore_permissions=True)

		self.assertEqual(table.autoname_method, "Autoincrement")
		self.assertEqual(table.is_active, 1)
		self.assertEqual(table.field_count, 0)
		self.assertEqual(table.record_count, 0)

	def test_table_name_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Huf Data Table",
			}).insert(ignore_permissions=True)

	def test_table_name_is_unique(self):
		frappe.get_doc({
			"doctype": "Huf Data Table",
			"table_name": "_Test Unique Table",
		}).insert(ignore_permissions=True)

		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({
				"doctype": "Huf Data Table",
				"table_name": "_Test Unique Table",
			}).insert(ignore_permissions=True)

	def test_delete_registry_entry_without_dynamic_doctype(self):
		"""on_trash only deletes the associated DocType when it exists —
		deleting a bare registry entry must not fail."""
		table = frappe.get_doc({
			"doctype": "Huf Data Table",
			"table_name": "_Test Disposable Table",
		}).insert(ignore_permissions=True)

		table.delete(ignore_permissions=True)

		self.assertFalse(frappe.db.exists("Huf Data Table", table.name))
