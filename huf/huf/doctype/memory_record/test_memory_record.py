# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMemoryRecord(FrappeTestCase):
	def test_active_requires_summary_text(self):
		doc = frappe.new_doc("Memory Record")
		doc.status = "Active"
		doc.summary_text = ""
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_promote_to_knowledge_requires_knowledge_source(self):
		doc = frappe.new_doc("Memory Record")
		doc.promote_to_knowledge = 1
		doc.knowledge_source = ""
		doc.status = "Active"
		doc.summary_text = "test"
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_global_scope_autofills_scope_key(self):
		doc = frappe.new_doc("Memory Record")
		doc.scope_type = "Global"
		doc.scope_key = ""
		doc.set_defaults()
		self.assertEqual(doc.scope_key, "global")

	def test_site_scope_autofills_scope_key(self):
		doc = frappe.new_doc("Memory Record")
		doc.scope_type = "Site"
		doc.scope_key = ""
		doc.set_defaults()
		self.assertIsNotNone(doc.scope_key)
		self.assertNotEqual(doc.scope_key, "")

	def test_conversation_scope_key_must_match_conversation(self):
		doc = frappe.new_doc("Memory Record")
		doc.scope_type = "Conversation"
		doc.conversation = "CONV-001"
		doc.scope_key = "WRONG"
		doc.summary_text = "test"
		with self.assertRaises(frappe.ValidationError):
			doc.validate_scope()

	def test_agent_scope_key_must_match_agent(self):
		doc = frappe.new_doc("Memory Record")
		doc.scope_type = "Agent"
		doc.agent = "my-agent"
		doc.scope_key = "other-agent"
		doc.summary_text = "test"
		with self.assertRaises(frappe.ValidationError):
			doc.validate_scope()
