# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase
import frappe
import json

class TestMemoryProfile(FrappeTestCase):
	"""Test cases for Memory Profile DocType."""
	
	def tearDown(self):
		"""Clean up test profiles."""
		frappe.db.sql("""DELETE FROM `tabMemory Profile` WHERE profile_name LIKE '_test_%'""")
	
	def test_create_profile(self):
		"""Test basic profile creation."""
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_profile"
		profile.description = "Test profile for unit testing"
		profile.category = "custom"
		profile.default_schema_json = json.dumps({"field": "value"})
		profile.default_capture_prompt = "Extract information"
		profile.insert()
		
		self.assertIsNotNone(profile.name)
		self.assertEqual(profile.profile_name, "_test_profile")
		self.assertFalse(profile.is_system_profile)
	
	def test_schema_validation(self):
		"""Test schema JSON validation."""
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_invalid_schema"
		profile.category = "custom"
		profile.default_schema_json = "invalid json {"
		profile.default_capture_prompt = "Test"
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			profile.insert()
	
	def test_type_mapping_validation(self):
		"""Test type mapping JSON validation."""
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_invalid_mapping"
		profile.category = "custom"
		profile.default_schema_json = json.dumps({"field": "value"})
		profile.default_capture_prompt = "Test"
		profile.default_memory_type_mapping = "not an object"
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			profile.insert()
		
		# Should work with valid object
		profile.default_memory_type_mapping = json.dumps({"pattern": "type"})
		profile.insert()
		self.assertIsNotNone(profile.name)
	
	def test_get_schema(self):
		"""Test schema retrieval."""
		schema = {"type": "object", "properties": {"name": {"type": "string"}}}
		
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_get_schema"
		profile.category = "custom"
		profile.default_schema_json = json.dumps(schema)
		profile.default_capture_prompt = "Test"
		profile.insert()
		
		retrieved = profile.get_schema()
		self.assertEqual(retrieved, schema)
	
	def test_get_capture_prompt(self):
		"""Test capture prompt retrieval with context."""
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_prompt"
		profile.category = "custom"
		profile.default_schema_json = json.dumps({})
		profile.default_capture_prompt = "Hello {name}, extract {type}"
		profile.insert()
		
		# Without context
		prompt = profile.get_capture_prompt()
		self.assertEqual(prompt, "Hello {name}, extract {type}")
		
		# With context
		prompt = profile.get_capture_prompt({"name": "World", "type": "data"})
		self.assertEqual(prompt, "Hello World, extract data")
	
	def test_infer_memory_type(self):
		"""Test memory type inference."""
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_infer"
		profile.category = "custom"
		profile.default_schema_json = json.dumps({})
		profile.default_capture_prompt = "Test"
		profile.default_memory_type_mapping = json.dumps({
			"code": "programming",
			"bug": "debugging",
			"api": "integration"
		})
		profile.insert()
		
		self.assertEqual(profile.infer_memory_type("some code example"), "programming")
		self.assertEqual(profile.infer_memory_type("found a bug"), "debugging")
		self.assertEqual(profile.infer_memory_type("random content"), "custom")
	
	def test_get_system_profiles(self):
		"""Test fetching system profiles."""
		# Create a system profile
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_system_profile"
		profile.category = "general"
		profile.is_system_profile = 1
		profile.default_schema_json = json.dumps({})
		profile.default_capture_prompt = "Test"
		profile.insert()
		
		# Create a non-system profile
		profile2 = frappe.new_doc("Memory Profile")
		profile2.profile_name = "_test_user_profile"
		profile2.category = "general"
		profile2.is_system_profile = 0
		profile2.default_schema_json = json.dumps({})
		profile2.default_capture_prompt = "Test"
		profile2.insert()
		
		system_profiles = MemoryProfile.get_system_profiles()
		profile_names = [p.profile_name for p in system_profiles]
		
		self.assertIn("_test_system_profile", profile_names)
		self.assertNotIn("_test_user_profile", profile_names)
	
	def test_get_profile_by_category(self):
		"""Test fetching profile by category."""
		# Create profile in specific category
		profile = frappe.new_doc("Memory Profile")
		profile.profile_name = "_test_science_profile"
		profile.category = "science"
		profile.is_system_profile = 1
		profile.default_schema_json = json.dumps({})
		profile.default_capture_prompt = "Test"
		profile.insert()
		
		fetched = MemoryProfile.get_profile_by_category("science")
		self.assertIsNotNone(fetched)
		self.assertEqual(fetched.profile_name, "_test_science_profile")
		
		# Non-existent category
		fetched = MemoryProfile.get_profile_by_category("nonexistent")
		self.assertIsNone(fetched)
	
	def test_create_default_profiles(self):
		"""Test creating default system profiles."""
		# Clean up any existing default profiles
		default_names = [
			"Programming Memory",
			"General Knowledge Memory",
			"Travel Planning Memory",
			"CRM Memory",
			"Documentation Memory"
		]
		for name in default_names:
			if frappe.db.exists("Memory Profile", name):
				frappe.delete_doc("Memory Profile", name)
		
		created = MemoryProfile.create_default_profiles()
		self.assertEqual(len(created), 5)
		
		# Verify all default profiles exist
		for name in default_names:
			self.assertTrue(frappe.db.exists("Memory Profile", name))
			profile = frappe.get_doc("Memory Profile", name)
			self.assertTrue(profile.is_system_profile)
