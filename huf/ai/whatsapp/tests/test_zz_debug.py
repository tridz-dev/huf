import frappe
from frappe.tests import IntegrationTestCase
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
class TestDbg(IntegrationTestCase):
	def test_dbg(self):
		k = bridge._edit_blocked_key("A", "n")
		print("DBG ver", frappe.__version__, bridge.EDIT_BLOCKED_SECONDS)
		print("DBG set", bridge._mark_edit_blocked("A", "n"))
		print("DBG get", bridge._edit_blocked_until("A", "n"), frappe.cache().get_value(k))
		print("DBG q", bridge.edit_quota("APPROVED", [], blocked_until=bridge._edit_blocked_until("A","n")))
