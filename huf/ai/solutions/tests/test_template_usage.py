import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.solution.test_solution import make_solution

ACCT = "acct-tu"


def _tu():
	from huf.ai.solutions import template_usage

	return template_usage


class TestTemplateUsage(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_first_observed_becomes_owner_then_user(self):
		tu = _tu()
		a, b = make_solution(), make_solution()
		tu.record_observed(ACCT, "hello", "en", a.name)
		tu.record_observed(ACCT, "hello", "en", b.name)
		u = tu.usage_for(ACCT, "hello", "en")
		self.assertEqual(u["owner"]["solution"], a.name)
		self.assertEqual(u["owner"]["title"], a.title)
		self.assertEqual({r["solution"] for r in u["used_by"]}, {a.name, b.name})
		self.assertTrue(u["shared"])

	def test_observed_is_idempotent(self):
		tu = _tu()
		a = make_solution()
		for _ in range(3):
			tu.record_observed(ACCT, "hello", "en", a.name)
		u = tu.usage_for(ACCT, "hello", "en")
		self.assertEqual(len(u["used_by"]), 1)
		self.assertFalse(u["shared"])

	def test_observed_without_solution_is_noop(self):
		tu = _tu()
		tu.record_observed(ACCT, "hello", "en", None)
		self.assertEqual(tu.usage_for(ACCT, "hello", "en"), {"owner": None, "used_by": [], "shared": False})

	def test_declare_owner_demotes_previous(self):
		tu = _tu()
		a, b = make_solution(), make_solution()
		tu.declare(ACCT, "hello", "en", a.name, owner=True)
		tu.declare(ACCT, "hello", "en", b.name, owner=True)
		u = tu.usage_for(ACCT, "hello", "en")
		self.assertEqual(u["owner"]["solution"], b.name)
		kinds = frappe.get_all(
			"Template Usage", filters={"whatsapp_account": ACCT, "template": "hello"}, fields=["solution", "kind", "source"]
		)
		self.assertEqual(sum(1 for k in kinds if k.kind == "Owner"), 1)
		self.assertTrue(all(k.source == "Declared" for k in kinds))

	def test_declare_upgrades_observed_source(self):
		tu = _tu()
		a = make_solution()
		tu.record_observed(ACCT, "hello", "en", a.name)
		tu.declare(ACCT, "hello", "en", a.name)
		row = frappe.get_all("Template Usage", filters={"whatsapp_account": ACCT}, fields=["source", "kind"])[0]
		self.assertEqual((row.source, row.kind), ("Declared", "Owner"))

	def test_set_owner(self):
		tu = _tu()
		a, b = make_solution(), make_solution()
		tu.declare(ACCT, "hello", "en", a.name, owner=True)
		tu.declare(ACCT, "hello", "en", b.name)
		tu.set_owner(ACCT, "hello", "en", b.name)
		self.assertEqual(tu.usage_for(ACCT, "hello", "en")["owner"]["solution"], b.name)

	def test_accounts_and_languages_are_isolated(self):
		tu = _tu()
		a = make_solution()
		tu.record_observed(ACCT, "hello", "en", a.name)
		self.assertEqual(tu.usage_for("other", "hello", "en")["used_by"], [])
		self.assertEqual(tu.usage_for(ACCT, "hello", "fr")["used_by"], [])

	def test_bulk_usage(self):
		tu = _tu()
		a, b = make_solution(), make_solution()
		tu.record_observed(ACCT, "hello", "en", a.name)
		tu.record_observed(ACCT, "hello", "en", b.name)
		tu.record_observed(ACCT, "bye", "en", a.name)
		tu.record_observed("other", "hello", "en", b.name)
		res = tu.bulk_usage(ACCT, [("hello", "en"), ("bye", "en"), ("none", "en")])
		self.assertTrue(res[("hello", "en")]["shared"])
		self.assertFalse(res[("bye", "en")]["shared"])
		self.assertEqual(res[("none", "en")], {"owner": None, "used_by": [], "shared": False})

	def test_guard_shared(self):
		tu = _tu()
		a, b = make_solution(), make_solution()
		tu.record_observed(ACCT, "hello", "en", a.name)
		self.assertIsNone(tu.guard_shared(ACCT, "hello", "en", False))
		tu.record_observed(ACCT, "hello", "en", b.name)
		refusal = tu.guard_shared(ACCT, "hello", "en", False)
		self.assertEqual(refusal["error"], "shared_template")
		self.assertEqual(len(refusal["used_by"]), 2)
		self.assertIsNone(tu.guard_shared(ACCT, "hello", "en", True))

	def test_button_payload_helper(self):
		tu = _tu()
		self.assertEqual(tu.solution_button_payload("sol-1", "Yes"), "sol:sol-1|Yes")
		self.assertEqual(tu.solution_button_payload(None, "Yes"), "Yes")

	def test_note_template_sent_records_usage_and_never_raises(self):
		from unittest.mock import patch

		from huf.ai.whatsapp import outbound_policy as policy

		a = make_solution()
		with patch.object(policy, "gateways_for_account", return_value=[]):
			policy.note_template_sent(ACCT, "15551234567", None, "hello", "en", a.name)
			policy.note_template_sent(ACCT, "15551234567", None)  # positional compat
		self.assertEqual(_tu().usage_for(ACCT, "hello", "en")["owner"]["solution"], a.name)
		with patch.object(_tu(), "record_observed", side_effect=RuntimeError("boom")), patch.object(
			policy, "gateways_for_account", return_value=[]
		):
			policy.note_template_sent(ACCT, "15551234567", None, "hello", "en", a.name)
