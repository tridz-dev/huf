import frappe
from frappe.tests import IntegrationTestCase
from huf.ai.channels import tools_erp as t
class TestDbg(IntegrationTestCase):
	def test_dbg(self):
		print("DBG company", t._default_company(), frappe.get_all("Company", fields=["name","default_currency","country"]))
		print("DBG pl", frappe.get_all("Price List", fields=["name","currency","selling","enabled"]))
		print("DBG ss", frappe.db.get_single_value("Selling Settings","selling_price_list"), frappe.db.get_single_value("Global Defaults","default_company"), frappe.db.get_single_value("Global Defaults","default_currency"))
		print("DBG cg", frappe.get_all("Customer Group", fields=["name","is_group"]), frappe.get_all("Territory", fields=["name","is_group"]))
