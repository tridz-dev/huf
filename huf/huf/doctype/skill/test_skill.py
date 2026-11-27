# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.skill.skill import make_unique_skill_name, slugify_skill_title


class TestSkillNaming(IntegrationTestCase):
	def test_slugify(self):
		self.assertEqual(slugify_skill_title("  Email Parser! v2 "), "email_parser_v2")
		self.assertEqual(slugify_skill_title("!!!"), "skill")
		self.assertEqual(slugify_skill_title(None), "skill")

	def test_unique_suffix(self):
		taken = {"email_parser", "email_parser_2"}
		self.assertEqual(make_unique_skill_name("Email Parser", taken.__contains__), "email_parser_3")

	def test_same_title_twice_and_explicit_name(self):
		created = []
		try:
			docs = [
				frappe.get_doc({"doctype": "Skill", "title": "Same Title ILF"}).insert(),
				frappe.get_doc({"doctype": "Skill", "title": "Same Title ILF"}).insert(),
				frappe.get_doc(
					{"doctype": "Skill", "title": "Other", "skill_name": "explicit_name_ilf"}
				).insert(),
			]
			created = [d.name for d in docs]
			self.assertEqual(created, ["same_title_ilf", "same_title_ilf_2", "explicit_name_ilf"])
		finally:
			for name in created:
				frappe.delete_doc("Skill", name, force=True)
