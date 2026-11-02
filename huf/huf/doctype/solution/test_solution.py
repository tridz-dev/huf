import frappe
from frappe.tests import IntegrationTestCase

from huf.testing.factories import _hash


def make_solution(**kw):
    doc = frappe.get_doc({"doctype": "Solution", "title": f"Sol {_hash()}", **kw})
    doc.insert(ignore_permissions=True)
    return doc


class TestSolution(IntegrationTestCase):
    def tearDown(self):
        frappe.db.rollback()

    def test_defaults(self):
        doc = make_solution()
        self.assertEqual(doc.status, "Paused")
        self.assertEqual(doc.purpose, "custom")

    def test_test_mode_forces_paused(self):
        doc = make_solution(status="Live", test_mode=1)
        self.assertEqual(doc.status, "Paused")
        doc.status = "Live"
        doc.save()
        self.assertEqual(doc.status, "Paused")

    def test_live_without_test_mode_kept(self):
        self.assertEqual(make_solution(status="Live").status, "Live")

    def test_agent_target_requires_agent(self):
        with self.assertRaises(frappe.ValidationError):
            make_solution(primary_target_type="Agent")

    def test_flow_target_requires_flow(self):
        with self.assertRaises(frappe.ValidationError):
            make_solution(primary_target_type="Flow")

    def test_blank_target_clears_links(self):
        doc = frappe.get_doc({"doctype": "Solution", "title": f"Sol {_hash()}",
                              "primary_agent": "x", "primary_flow": "y"})
        doc.validate()
        self.assertFalse(doc.primary_agent)
        self.assertFalse(doc.primary_flow)

    def test_target_type_clears_other_link(self):
        doc = frappe.get_doc({"doctype": "Solution", "title": f"Sol {_hash()}",
                              "primary_target_type": "Agent", "primary_agent": "x", "primary_flow": "y"})
        doc.validate()
        self.assertEqual(doc.primary_agent, "x")
        self.assertFalse(doc.primary_flow)

    def test_unique_title_and_strip(self):
        doc = make_solution(title="  Same Title  ")
        self.assertEqual(doc.title, "Same Title")
        with self.assertRaises(frappe.ValidationError):
            make_solution(title="Same Title")
