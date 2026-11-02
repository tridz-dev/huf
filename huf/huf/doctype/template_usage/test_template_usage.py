import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.solution.test_solution import make_solution


def _usage(sol, **kw):
    vals = {"doctype": "Template Usage", "whatsapp_account": "acct", "template": "hello",
            "language": "en", "solution": sol, "kind": "User", "source": "Declared"}
    vals.update(kw)
    return frappe.get_doc(vals).insert(ignore_permissions=True)


class TestTemplateUsage(IntegrationTestCase):
    def tearDown(self):
        frappe.db.rollback()

    def test_unique_tuple(self):
        sol = make_solution()
        _usage(sol.name)
        with self.assertRaises(frappe.ValidationError):
            _usage(sol.name)

    def test_variations_allowed(self):
        sol, sol2 = make_solution(), make_solution()
        _usage(sol.name)
        _usage(sol.name, language="fr")
        _usage(sol.name, template="other")
        _usage(sol.name, whatsapp_account="acct2")
        _usage(sol2.name)

    def test_account_is_plain_data(self):
        field = frappe.get_meta("Template Usage").get_field("whatsapp_account")
        self.assertEqual(field.fieldtype, "Data")
