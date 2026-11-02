import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.solution.test_solution import make_solution
from huf.testing.factories import _hash


def _gateway():
    doc = frappe.get_doc(
        {"doctype": "Gateway", "gateway_name": f"GW {_hash()}", "provider": "Telegram",
         "is_enabled": 0, "direct_policy": "Pairing"}
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestConversationAssignment(IntegrationTestCase):
    def tearDown(self):
        frappe.db.rollback()

    def _assign(self, gw, contact, sol):
        return frappe.get_doc(
            {"doctype": "Conversation Assignment", "gateway": gw, "contact": contact, "solution": sol}
        ).insert(ignore_permissions=True)

    def test_unique_per_gateway_contact(self):
        gw, sol = _gateway(), make_solution()
        self._assign(gw.name, "15550001", sol.name)
        with self.assertRaises(frappe.ValidationError):
            self._assign(gw.name, "15550001", make_solution().name)

    def test_other_contact_or_gateway_allowed(self):
        gw, gw2, sol = _gateway(), _gateway(), make_solution()
        self._assign(gw.name, "15550001", sol.name)
        self._assign(gw.name, "15550002", sol.name)
        self._assign(gw2.name, "15550001", sol.name)

    def test_resave_same_row_ok(self):
        gw, sol = _gateway(), make_solution()
        doc = self._assign(gw.name, "15550001", sol.name)
        doc.set_by = "rule"
        doc.save()
