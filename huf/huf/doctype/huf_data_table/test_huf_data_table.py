import frappe
from frappe.tests import IntegrationTestCase


class TestHufDataTable(IntegrationTestCase):
	def tearDown(self):
		"""Clean up test data tables."""
		for table in frappe.get_all("Huf Data Table", pluck="name"):
			registry = frappe.get_doc("Huf Data Table", table)
			if frappe.db.exists("DocType", registry.doctype_name):
				frappe.delete_doc("DocType", registry.doctype_name, force=True)
			frappe.delete_doc("Huf Data Table", table, force=True)
		frappe.db.commit()

	def test_create_data_table(self):
		from .api import create_data_table

		result = create_data_table(
			table_name="Test Products",
			fields=[
				{"fieldtype": "Data", "label": "Product Name", "reqd": 1},
				{"fieldtype": "Currency", "label": "Price"},
				{"fieldtype": "Check", "label": "Is Active"},
			],
		)

		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["table_name"], "Test Products")
		self.assertEqual(result["data"]["doctype_name"], "HT Test Products")
		self.assertTrue(frappe.db.exists("DocType", "HT Test Products"))
		self.assertTrue(frappe.db.exists("Huf Data Table", {"table_name": "Test Products"}))

	def test_get_table_schema(self):
		from .api import create_data_table, get_table_schema

		result = create_data_table(
			table_name="Schema Test",
			fields=[
				{"fieldtype": "Data", "label": "Name Field", "reqd": 1},
				{"fieldtype": "Int", "label": "Count"},
			],
		)

		schema = get_table_schema(result["data"]["name"])
		self.assertEqual(schema["table_name"], "Schema Test")
		self.assertEqual(len(schema["fields"]), 2)
		self.assertEqual(schema["fields"][0]["fieldname"], "name_field")

	def test_delete_data_table(self):
		from .api import create_data_table, delete_data_table

		result = create_data_table(
			table_name="Delete Test",
			fields=[{"fieldtype": "Data", "label": "Title"}],
		)

		delete_result = delete_data_table(result["data"]["name"])
		self.assertTrue(delete_result["success"])
		self.assertFalse(frappe.db.exists("DocType", "HT Delete Test"))
		self.assertFalse(frappe.db.exists("Huf Data Table", result["data"]["name"]))

	def test_duplicate_table_name(self):
		from .api import create_data_table

		create_data_table(
			table_name="Duplicate Test",
			fields=[{"fieldtype": "Data", "label": "Title"}],
		)

		with self.assertRaises(frappe.ValidationError):
			create_data_table(
				table_name="Duplicate Test",
				fields=[{"fieldtype": "Data", "label": "Title"}],
			)

	def test_invalid_field_type(self):
		from .api import create_data_table

		with self.assertRaises(frappe.ValidationError):
			create_data_table(
				table_name="Invalid Fields",
				fields=[{"fieldtype": "Table", "label": "Child Table"}],
			)
