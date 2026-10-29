import frappe
from frappe.tests import IntegrationTestCase
class TestDbg(IntegrationTestCase):
	def test_dbg(self):
		print("DBG now", frappe.utils.now(), frappe.utils.now_datetime())
		for r in frappe.get_all("Embedded Signup Audit", fields=["name","outcome","reason","creation","tenant_id"], order_by="creation desc", limit=6):
			print("DBG", r)
		print("DBG cnt", frappe.db.count("Embedded Signup Audit"))
