# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase
import frappe

class TestMemoryPolicy(FrappeTestCase):
	"""Test cases for Memory Policy DocType."""
	
	def setUp(self):
		"""Set up test data."""
		# Create a test agent if it doesn't exist
		if not frappe.db.exists("Agent", "_test_policy_agent"):
			agent = frappe.new_doc("Agent")
			agent.agent_name = "_test_policy_agent"
			agent.model = "gpt-4"
			agent.provider = "openai"
			agent.insert()
		
		# Create a test memory agent
		if not frappe.db.exists("Agent", "_test_memory_agent"):
			agent = frappe.new_doc("Agent")
			agent.agent_name = "_test_memory_agent"
			agent.model = "gpt-4"
			agent.provider = "openai"
			agent.insert()
	
	def tearDown(self):
		"""Clean up test data."""
		# Clean up test policies
		frappe.db.sql("""DELETE FROM `tabMemory Policy` WHERE policy_name LIKE '_test_%'""")
		# Clean up test agents
		if frappe.db.exists("Agent", "_test_policy_agent"):
			frappe.delete_doc("Agent", "_test_policy_agent")
		if frappe.db.exists("Agent", "_test_memory_agent"):
			frappe.delete_doc("Agent", "_test_memory_agent")
	
	def test_create_policy(self):
		"""Test basic policy creation."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_basic_policy"
		policy.enabled = 1
		policy.agent = "_test_policy_agent"
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_run"
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		self.assertIsNotNone(policy.name)
		self.assertEqual(policy.policy_name, "_test_basic_policy")
		self.assertTrue(policy.enabled)
	
	def test_memory_agent_validation(self):
		"""Test validation of memory agent requirement."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_memory_agent_validation"
		policy.enabled = 1
		policy.capture_owner = "memory_agent"
		policy.capture_stage = "post_response_async"
		policy.capture_frequency_type = "every_run"
		policy.retrieval_mode_default = "inject"
		
		# Should fail without memory_agent
		with self.assertRaises(frappe.exceptions.ValidationError):
			policy.insert()
		
		# Should succeed with memory_agent
		policy.memory_agent = "_test_memory_agent"
		policy.insert()
		self.assertIsNotNone(policy.name)
	
	def test_same_agent_validation(self):
		"""Test that memory agent cannot be same as main agent."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_same_agent"
		policy.enabled = 1
		policy.agent = "_test_policy_agent"
		policy.capture_owner = "memory_agent"
		policy.memory_agent = "_test_policy_agent"  # Same as agent
		policy.capture_stage = "post_response_async"
		policy.capture_frequency_type = "every_run"
		policy.retrieval_mode_default = "inject"
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			policy.insert()
	
	def test_frequency_validation(self):
		"""Test frequency value validation."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_frequency"
		policy.enabled = 1
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_n_runs"
		policy.capture_frequency_value = 0  # Invalid
		policy.retrieval_mode_default = "inject"
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			policy.insert()
	
	def test_confidence_validation(self):
		"""Test confidence threshold validation."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_confidence"
		policy.enabled = 1
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_run"
		policy.min_confidence = 1.5  # Invalid
		policy.retrieval_mode_default = "inject"
		
		with self.assertRaises(frappe.exceptions.ValidationError):
			policy.insert()
	
	def test_should_capture_on_run(self):
		"""Test run-based capture logic."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_run_capture"
		policy.enabled = 1
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_n_runs"
		policy.capture_frequency_value = 3
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		# Should capture on runs 3, 6, 9, etc.
		self.assertFalse(policy.should_capture_on_run(1))
		self.assertFalse(policy.should_capture_on_run(2))
		self.assertTrue(policy.should_capture_on_run(3))
		self.assertFalse(policy.should_capture_on_run(4))
		self.assertFalse(policy.should_capture_on_run(5))
		self.assertTrue(policy.should_capture_on_run(6))
	
	def test_should_capture_on_turn(self):
		"""Test turn-based capture logic."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_turn_capture"
		policy.enabled = 1
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_n_turns"
		policy.capture_frequency_value = 5
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		self.assertFalse(policy.should_capture_on_turn(1))
		self.assertTrue(policy.should_capture_on_turn(5))
		self.assertTrue(policy.should_capture_on_turn(10))
	
	def test_disabled_policy(self):
		"""Test that disabled policies don't trigger capture."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_disabled"
		policy.enabled = 0
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_run"
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		self.assertFalse(policy.should_capture_on_run(1))
		self.assertFalse(policy.should_capture_on_turn(1))
	
	def test_confidence_threshold(self):
		"""Test confidence threshold checking."""
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_confidence_threshold"
		policy.enabled = 1
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_run"
		policy.min_confidence = 0.7
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		self.assertFalse(policy.check_confidence_threshold(0.5))
		self.assertTrue(policy.check_confidence_threshold(0.7))
		self.assertTrue(policy.check_confidence_threshold(0.9))
	
	def test_get_active_policy_for_agent(self):
		"""Test fetching policy for an agent."""
		# Create policy for test agent
		policy = frappe.new_doc("Memory Policy")
		policy.policy_name = "_test_agent_policy"
		policy.enabled = 1
		policy.agent = "_test_policy_agent"
		policy.capture_owner = "main_agent"
		policy.capture_stage = "in_prompt"
		policy.capture_frequency_type = "every_run"
		policy.retrieval_mode_default = "inject"
		policy.insert()
		
		fetched = MemoryPolicy.get_active_policy_for_agent("_test_policy_agent")
		self.assertIsNotNone(fetched)
		self.assertEqual(fetched.policy_name, "_test_agent_policy")
		
		# Non-existent agent should return None
		fetched = MemoryPolicy.get_active_policy_for_agent("_non_existent_agent")
		self.assertIsNone(fetched)
