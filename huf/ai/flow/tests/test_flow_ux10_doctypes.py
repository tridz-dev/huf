"""Pure tests for the document-type list a "When a document changes" trigger offers (UX-10, B14)."""

import unittest

from huf.ai.flow.support.doctype_catalog import build_catalog, classify, friendly_label


def row(name, module, custom=0):
	return {"name": name, "module": module, "custom": custom}


class TestCatalog(unittest.TestCase):
	def test_system_noise_is_left_out(self):
		# B14: searching "ToDo" used to surface these.
		for name, module in (
			("Custom DocPerm", "Core"),
			("DocPerm", "Core"),
			("OAuth Authorization Code", "Integrations"),
			("OAuth Client", "Integrations"),
			("Personal Data Download Request", "Website"),
			("Token Cache", "Integrations"),
			("Print Format", "Printing"),
			("Property Setter", "Custom"),
			("Flow Definition", "Huf"),
			("Dashboard Chart", "Desk"),
		):
			self.assertIsNone(classify(name, module), name)
		self.assertEqual(build_catalog([row("Custom DocPerm", "Core"), row("OAuth Client", "Integrations")]), [])

	def test_everyday_records_are_kept_and_named_for_people(self):
		cat = {d["name"]: d for d in build_catalog([row("ToDo", "Desk"), row("Event", "Desk"), row("User", "Core"), row("Note", "Desk")])}
		self.assertEqual(cat["ToDo"]["label"], "To-do")
		self.assertEqual(cat["Event"]["label"], "Calendar event")
		self.assertTrue(all(d["group"] == "common" for d in cat.values()))
		self.assertEqual(friendly_label("Sales Order"), "Sales Order")

	def test_apps_and_your_own_tables_are_kept_in_groups(self):
		cat = build_catalog(
			[row("Sales Order", "Selling"), row("Customer", "Selling"), row("Uiv Wp7 Doc", "Custom", 1), row("ToDo", "Desk"), row("Contact", "Contacts")]
		)
		self.assertEqual([d["group"] for d in cat], ["common", "yours", "apps", "apps", "apps"])
		self.assertEqual([d["name"] for d in cat if d["group"] == "apps"], ["Contact", "Customer", "Sales Order"])

	def test_rows_without_a_name_are_ignored(self):
		self.assertEqual(build_catalog([{"module": "Selling"}, None, {"name": ""}]), [])
