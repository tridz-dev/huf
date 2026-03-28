# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase
import frappe
from frappe.utils import now_datetime, add_days

class TestMemoryRecord(FrappeTestCase):
	"""Test cases for Memory Record DocType."""
	
	def setUp(self):
		"""Set up test data."""
		# Create a test agent if it doesn't exist
		if not frappe.db.exists("Agent", "_test_memory_agent"):
			agent = frappe.new_doc("Agent")
			agent.agent_name = "_test_memory_agent"
			agent.model = "gpt-4"
			agent.provider = "openai"
			agent.insert()
	
	def tearDown(self):
		"""Clean up test data."""
		# Clean up test memory records
		frappe.db.sql("""DELETE FROM `tabMemory Record` WHERE agent = '_test_memory_agent'""")
		# Clean up test agent
		if frappe.db.exists("Agent", "_test_memory_agent"):
			frappe.delete_doc("Agent", "_test_memory_agent")
	
	def test_create_memory_record(self):
		"""Test basic memory record creation."""
		memory = frappe.new_doc("Memory Record")
		memory.title = "Test Memory"
		memory.agent = "_test_memory_agent"
		memory.source_type = "manual"
		memory.producer_mode = "manual"
		memory.memory_type = "fact"
		memory.scope_type = "agent"
		memory.scope_key = "_test_memory_agent"
		memory.visibility = "private"
		memory.data_json = '{"key": "value"}'
		memory.insert()
		
		self.assertIsNotNone(memory.name)
		self.assertTrue(memory.name.startswith("MREC-"))
		self.assertEqual(memory.status, "active")
		self.assertIsNotNone(memory.creation_timestamp)
	
	def test_confidence_validation(self):
		"""Test confidence score validation."""
		memory = frappe.new_doc("Memory Record")
		memory.title = "Test Memory"
		memory.agent = "_test_memory_agent"
		memory.source_type = "manual"
		memory.producer_mode = "manual"
		memory.memory_type = "fact"
		memory.scope_type = "agent"
		memory.scope_key = "_test_memory_agent"
		memory.visibility = "private"
		memory.data_json = '{}'
		memory.confidence = 1.5  # Invalid
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			memory.insert()
	
	def test_ttl_expiration(self):
		"""Test TTL-based expiration."""
		memory = frappe.new_doc("Memory Record")
		memory.title = "Test Memory"
		memory.agent = "_test_memory_agent"
		memory.source_type = "manual"
		memory.producer_mode = "manual"
		memory.memory_type = "fact"
		memory.scope_type = "agent"
		memory.scope_key = "_test_memory_agent"
		memory.visibility = "private"
		memory.data_json = '{}'
		memory.ttl_days = 7
		memory.insert()
		
		self.assertIsNotNone(memory.expiration_timestamp)
		expected_expiry = add_days(memory.creation_timestamp, 7)
		self.assertEqual(memory.expiration_timestamp.date(), expected_expiry.date())
	
	def test_is_valid(self):
		"""Test validity check."""
		memory = frappe.new_doc("Memory Record")
		memory.title = "Test Memory"
		memory.agent = "_test_memory_agent"
		memory.source_type = "manual"
		memory.producer_mode = "manual"
		memory.memory_type = "fact"
		memory.scope_type = "agent"
		memory.scope_key = "_test_memory_agent"
		memory.visibility = "private"
		memory.data_json = '{}'
		memory.insert()
		
		self.assertTrue(memory.is_valid())
		
		# Test expired status
		memory.status = "expired"
		self.assertFalse(memory.is_valid())
	
	def test_record_retrieval(self):
		"""Test retrieval tracking."""
		memory = frappe.new_doc("Memory Record")
		memory.title = "Test Memory"
		memory.agent = "_test_memory_agent"
		memory.source_type = "manual"
		memory.producer_mode = "manual"
		memory.memory_type = "fact"
		memory.scope_type = "agent"
		memory.scope_key = "_test_memory_agent"
		memory.visibility = "private"
		memory.data_json = '{}'
		memory.insert()
		
		initial_count = memory.retrieval_count or 0
		memory.record_retrieval()
		
		# Reload and check
		memory.reload()
		self.assertEqual(memory.retrieval_count, initial_count + 1)
		self.assertIsNotNone(memory.last_retrieved_at)
	
	def test_superseded_record_update(self):
		"""Test that superseding updates old record status."""
		# Create first record
		memory1 = frappe.new_doc("Memory Record")
		memory1.title = "Test Memory v1"
		memory1.agent = "_test_memory_agent"
		memory1.source_type = "manual"
		memory1.producer_mode = "manual"
		memory1.memory_type = "fact"
		memory1.scope_type = "agent"
		memory1.scope_key = "_test_memory_agent"
		memory1.visibility = "private"
		memory1.data_json = '{"version": 1}'
		memory1.insert()
		
		# Create second record that supersedes first
		memory2 = frappe.new_doc("Memory Record")
		memory2.title = "Test Memory v2"
		memory2.agent = "_test_memory_agent"
		memory2.source_type = "manual"
		memory2.producer_mode = "manual"
		memory2.memory_type = "fact"
		memory2.scope_type = "agent"
		memory2.scope_key = "_test_memory_agent"
		memory2.visibility = "private"
		memory2.data_json = '{"version": 2}'
		memory2.supersedes_memory_record = memory1.name
		memory2.insert()
		
		# Check first record is now superseded
		memory1.reload()
		self.assertEqual(memory1.status, "superseded")
