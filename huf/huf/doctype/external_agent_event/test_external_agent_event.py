# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestExternalAgentEvent(FrappeTestCase):
	def test_doctype_exists_with_hash_autoname(self):
		meta = frappe.get_meta("External Agent Event")
		self.assertEqual(meta.autoname, "hash")
		self.assertEqual(meta.get_field("session").options, "External Agent Session")
		self.assertEqual(meta.get_field("status").default, "Pending")
