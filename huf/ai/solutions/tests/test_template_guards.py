from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.solutions import template_usage as tu
from huf.ai.whatsapp import management as mgmt
from huf.huf.doctype.solution.test_solution import make_solution

ACCT = "acct-guard"
ROWS = [
	{"name": "hello-en", "template_name": "hello", "actual_name": "hello", "language_code": "en", "whatsapp_account": ACCT},
	{"name": "bye-en", "template_name": "bye", "actual_name": "bye", "language_code": "en", "whatsapp_account": ACCT},
	{"name": "solo-en", "template_name": "solo", "actual_name": "solo", "language_code": "en", "whatsapp_account": ACCT},
]


def _rows():
	return [dict(r) for r in ROWS]


class TestTemplateGuards(IntegrationTestCase):
	def setUp(self):
		self.a, self.b = make_solution(), make_solution()
		tu.record_observed(ACCT, "hello", "en", self.a.name)
		tu.record_observed(ACCT, "hello", "en", self.b.name)
		tu.record_observed(ACCT, "bye", "en", self.b.name)
		self.patches = [
			patch.object(bridge, "is_available", return_value=True),
			patch.object(bridge, "list_templates", side_effect=lambda *a, **k: _rows()),
			patch.object(bridge, "template_buttons", return_value={}),
			patch.object(bridge, "resolve_account", return_value={"business_id": ""}),
			patch.object(tu, "template_identity", side_effect=self._identity),
		]
		for p in self.patches:
			p.start()

	def tearDown(self):
		for p in self.patches:
			p.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	@staticmethod
	def _identity(name):
		row = next((r for r in ROWS if r["name"] == name), None)
		return (ACCT, row["actual_name"], row["language_code"]) if row else None

	def test_list_rows_gain_usage(self):
		with patch.object(mgmt, "_has_doctype_permission"):
			res = mgmt.list_templates(account=ACCT)
		by = {r["name"]: r for r in res["templates"]}
		self.assertTrue(by["hello-en"]["shared"])
		self.assertEqual(by["hello-en"]["owner"]["solution"], self.a.name)
		self.assertEqual(len(by["hello-en"]["used_by"]), 2)
		self.assertFalse(by["bye-en"]["shared"])
		self.assertEqual(by["solo-en"], {**by["solo-en"], "used_by": [], "shared": False, "owner": None})

	def test_list_solution_filter(self):
		with patch.object(mgmt, "_has_doctype_permission"):
			res = mgmt.list_templates(account=ACCT, solution=self.b.name)
			self.assertEqual({r["name"] for r in res["templates"]}, {"hello-en", "bye-en"})
			res = mgmt.list_templates(account=ACCT, solution=self.a.name)
			self.assertEqual({r["name"] for r in res["templates"]}, {"hello-en"})

	def test_edit_shared_refused_until_acknowledged(self):
		with patch.object(bridge, "edit_template", return_value={"success": True}) as edit:
			res = mgmt.edit_template("hello-en", {"body": "x"})
			self.assertEqual(res["error"], "shared_template")
			self.assertEqual(len(res["used_by"]), 2)
			edit.assert_not_called()
			self.assertTrue(mgmt.edit_template("hello-en", {"body": "x"}, acknowledge_shared=1)["success"])
			self.assertTrue(mgmt.edit_template("bye-en", {"body": "x"})["success"])
			self.assertTrue(mgmt.edit_template("solo-en", {"body": "x"})["success"])

	def test_delete_shared_refused_until_acknowledged(self):
		with patch.object(bridge, "delete_template", return_value={"success": True}) as dele:
			res = mgmt.delete_template("hello-en")
			self.assertEqual(res["error"], "shared_template")
			dele.assert_not_called()
			self.assertTrue(mgmt.delete_template("hello-en", acknowledge_shared=1)["success"])
			self.assertTrue(mgmt.delete_template("solo-en")["success"])

	def test_declare_template_usage(self):
		c = make_solution()
		res = mgmt.declare_template_usage(ACCT, "solo", "en", c.name, owner=1)
		self.assertTrue(res["success"])
		self.assertEqual(tu.usage_for(ACCT, "solo", "en")["owner"]["solution"], c.name)
		self.assertEqual(mgmt.declare_template_usage(ACCT, "solo", "en", "nope")["error"], "not_found")

	def test_non_admin_without_access_gets_nothing(self):
		email = "tu-nobody@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": "Nobody", "send_welcome_email": 0, "roles": []}
			).insert(ignore_permissions=True)
		frappe.set_user(email)
		with patch.object(mgmt, "_has_doctype_permission"):
			with self.assertRaises(frappe.PermissionError):
				mgmt.list_templates(account=ACCT)
		with self.assertRaises(frappe.PermissionError):
			mgmt.declare_template_usage(ACCT, "solo", "en", self.a.name)
