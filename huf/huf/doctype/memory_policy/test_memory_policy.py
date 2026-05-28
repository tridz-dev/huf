# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMemoryPolicy(FrappeTestCase):
	def test_auto_promote_requires_knowledge_source(self):
		doc = frappe.new_doc("Memory Policy")
		doc.auto_promote_to_knowledge = 1
		doc.knowledge_source = ""
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_agent_scope_autofills_scope_key(self):
		doc = frappe.new_doc("Memory Policy")
		doc.agent = "test-agent"
		doc.scope_type = "Agent"
		doc.scope_key = ""
		doc.validate()
		self.assertEqual(doc.scope_key, "test-agent")
