"""
Unit tests for the prompt_cache_mode migration patch.

Tests the migration from four separate caching fields to a single prompt_cache_mode field.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_prompt_cache_mode_migration
"""
import unittest

import frappe
from frappe.test_runner import make_test_records


class TestPromptCacheModeMigration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures."""
		# Ensure Agent doctype exists
		if not frappe.get_meta("Agent"):
			raise RuntimeError("Agent doctype not found")

	def tearDown(self):
		"""Clean up test agents after each test."""
		# Clean up any test agents we created
		for agent_name in getattr(self, "_test_agents", []):
			try:
				frappe.delete_doc("Agent", agent_name, force=True)
			except frappe.DoesNotExistError:
				pass

	def _create_test_agent(self, agent_name, **kwargs):
		"""Helper to create a test agent with specified fields."""
		agent = frappe.new_doc("Agent")
		agent.agent_name = agent_name
		agent.agent_modality = kwargs.get("agent_modality", "Voice")
		agent.instructions = kwargs.get("instructions", "Test agent for migration testing.")

		# Set caching fields if provided
		if "enable_prompt_caching" in kwargs:
			agent.enable_prompt_caching = kwargs["enable_prompt_caching"]
		if "cache_control_type" in kwargs:
			agent.cache_control_type = kwargs["cache_control_type"]
		if "cache_system_message" in kwargs:
			agent.cache_system_message = kwargs["cache_system_message"]
		if "cache_conversation_history" in kwargs:
			agent.cache_conversation_history = kwargs["cache_conversation_history"]
		if "prompt_cache_mode" in kwargs:
			agent.prompt_cache_mode = kwargs["prompt_cache_mode"]

		agent.insert(ignore_permissions=True)

		if not hasattr(self, "_test_agents"):
			self._test_agents = []
		self._test_agents.append(agent_name)

		return agent

	def test_new_agent_defaults_to_auto(self):
		"""Test that a newly created Agent defaults to prompt_cache_mode='Auto'."""
		agent = self._create_test_agent("test-new-agent-auto")
		self.assertEqual(agent.prompt_cache_mode, "Auto")

	def test_patch_sets_auto_with_enable_prompt_caching_zero(self):
		"""Test that patch sets Auto for Agent with enable_prompt_caching=0."""
		agent = self._create_test_agent("test-agent-enable-false")
		# Reset prompt_cache_mode to empty and set old field via SQL to simulate pre-migration state
		frappe.db.set_value("Agent", agent.name, {"prompt_cache_mode": "", "enable_prompt_caching": 0})
		frappe.db.commit()

		# Run the migration patch
		from huf.patches.v1.migrate_prompt_caching_fields import execute

		execute()

		# Reload and check
		agent.reload()
		self.assertEqual(agent.prompt_cache_mode, "Auto")

	def test_patch_sets_auto_with_enable_prompt_caching_one(self):
		"""Test that patch sets Auto for Agent with enable_prompt_caching=1."""
		agent = self._create_test_agent("test-agent-enable-true")
		# Set old fields via SQL to simulate pre-migration state with caching enabled
		frappe.db.set_value("Agent", agent.name, {
			"prompt_cache_mode": "",
			"enable_prompt_caching": 1,
			"cache_control_type": "ephemeral",
			"cache_system_message": 1,
			"cache_conversation_history": 0
		})
		frappe.db.commit()

		# Run the migration patch
		from huf.patches.v1.migrate_prompt_caching_fields import execute

		execute()

		# Reload and check
		agent.reload()
		self.assertEqual(agent.prompt_cache_mode, "Auto")

	def test_patch_is_idempotent(self):
		"""Test that running patch twice is safe and idempotent."""
		agent = self._create_test_agent("test-agent-idempotent")
		# Set old field via SQL to simulate pre-migration state
		frappe.db.set_value("Agent", agent.name, {"prompt_cache_mode": "", "enable_prompt_caching": 1})
		frappe.db.commit()

		# Run patch first time
		from huf.patches.v1.migrate_prompt_caching_fields import execute

		execute()
		agent.reload()
		self.assertEqual(agent.prompt_cache_mode, "Auto")

		# Run patch second time - should be safe
		execute()
		agent.reload()
		self.assertEqual(agent.prompt_cache_mode, "Auto")

	def test_patch_respects_existing_off_value(self):
		"""Test that patch does not overwrite Agent explicitly set to Off."""
		agent = self._create_test_agent(
			"test-agent-keep-off",
			prompt_cache_mode="Off",
		)

		# Run the migration patch
		from huf.patches.v1.migrate_prompt_caching_fields import execute

		execute()

		# Reload and check - should still be Off
		agent.reload()
		self.assertEqual(agent.prompt_cache_mode, "Off")

	def test_legacy_fields_unchanged(self):
		"""Test that legacy fields remain in place and unchanged after migration."""
		agent = self._create_test_agent("test-agent-legacy-fields")
		# Set old fields via SQL to simulate pre-migration state
		frappe.db.set_value("Agent", agent.name, {
			"prompt_cache_mode": "",
			"enable_prompt_caching": 1,
			"cache_control_type": "auto",
			"cache_system_message": 1,
			"cache_conversation_history": 1
		})
		frappe.db.commit()

		# Store original values (reload to get them)
		agent.reload()
		original_enable = agent.enable_prompt_caching
		original_control_type = agent.cache_control_type
		original_system_msg = agent.cache_system_message
		original_history = agent.cache_conversation_history

		# Run patch
		from huf.patches.v1.migrate_prompt_caching_fields import execute

		execute()

		# Reload and verify legacy fields are still there
		agent.reload()
		self.assertEqual(agent.enable_prompt_caching, original_enable)
		self.assertEqual(agent.cache_control_type, original_control_type)
		self.assertEqual(agent.cache_system_message, original_system_msg)
		self.assertEqual(agent.cache_conversation_history, original_history)
		self.assertEqual(agent.prompt_cache_mode, "Auto")
