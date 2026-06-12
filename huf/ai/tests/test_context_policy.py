"""
Tests for Agent Message context policy filtering.
Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_context_policy
"""
import unittest
import frappe
from huf.ai.conversation_manager import ConversationManager


class TestContextPolicy(unittest.TestCase):
	"""Tests for context policy filtering in get_conversation_history."""

	def setUp(self):
		self.agent_name = frappe.db.get_value("Agent", {}, "name")
		if not self.agent_name:
			self.skipTest("No Agent document found in database")

		self.conv_manager = ConversationManager(
			agent_name=self.agent_name,
			channel="test",
			external_id="test_context_policy"
		)
		self.conversation = self.conv_manager.create_new_conversation(title="Test Context Policy")

		# Track created docs for cleanup
		self._created_conversations = [self.conversation.name]

	def tearDown(self):
		for conv_name in self._created_conversations:
			try:
				frappe.db.sql("DELETE FROM `tabAgent Message` WHERE conversation = %s", conv_name)
				frappe.db.sql("DELETE FROM `tabAgent Conversation` WHERE name = %s", conv_name)
				frappe.db.commit()
			except Exception:
				pass

	def _get_provider_model(self):
		provider = frappe.db.get_value("AI Provider", {}, "name") or "test-provider"
		model = frappe.db.get_value("AI Model", {}, "name") or "test-model"
		return provider, model

	def test_include_full_policy(self):
		"""Existing behavior: full content included when policy is include_full."""
		provider, model = self._get_provider_model()
		self.conv_manager.add_message(
			self.conversation, "user", "Hello full",
			provider, model, self.agent_name,
			context_policy="include_full"
		)
		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 1)
		self.assertEqual(history[0]["content"], "Hello full")

	def test_include_reference_policy(self):
		"""Reference policy: compact handle only, raw content excluded."""
		provider, model = self._get_provider_model()
		large_result = "X" * 5000
		self.conv_manager.add_message(
			self.conversation, "tool", large_result,
			provider, model, self.agent_name,
			kind="Tool Result",
			record_kind="tool_result",
			context_policy="include_reference",
			context_summary="5000-char result from search tool",
			reference_doctype="Agent Tool Call",
			reference_name="ATC-TEST-001"
		)
		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 1)
		msg = history[0]
		self.assertIn("tool_result", msg["content"])
		self.assertIn("ATC-TEST-001", msg["content"])
		self.assertNotIn("XXXXX", msg["content"])  # raw content must not appear

	def test_exclude_policy(self):
		"""Exclude policy: message omitted entirely from history."""
		provider, model = self._get_provider_model()
		self.conv_manager.add_message(
			self.conversation, "system", "debug trace data",
			provider, model, self.agent_name,
			context_policy="exclude"
		)
		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 0)

	def test_transient_only_policy(self):
		"""Transient-only policy: message omitted from future history."""
		provider, model = self._get_provider_model()
		self.conv_manager.add_message(
			self.conversation, "user", "transient data",
			provider, model, self.agent_name,
			context_policy="transient_only"
		)
		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 0)

	def test_null_policy_backward_compat(self):
		"""NULL policy (legacy rows): treated as include_full, no regression."""
		# Directly insert a row without context_policy to simulate pre-Phase-1 data
		last_index = frappe.db.sql(
			"SELECT COALESCE(MAX(conversation_index), 0) FROM `tabAgent Message` WHERE conversation = %s",
			(self.conversation.name,)
		)[0][0]
		frappe.get_doc({
			"doctype": "Agent Message",
			"conversation": self.conversation.name,
			"role": "user",
			"content": "legacy message without policy",
			"conversation_index": last_index + 1,
			"is_agent_message": 0,
		}).insert(ignore_permissions=True)

		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertTrue(
			any(h["content"] == "legacy message without policy" for h in history),
			"Legacy rows (NULL policy) should appear as include_full"
		)

	def test_token_growth_bounded(self):
		"""Repeated large tool results with include_reference do not grow history size."""
		provider, model = self._get_provider_model()
		for i in range(3):
			self.conv_manager.add_message(
				self.conversation, "user", f"Question {i}",
				provider, model, self.agent_name,
				context_policy="include_full"
			)
			self.conv_manager.add_message(
				self.conversation, "tool", "Y" * 5000,
				provider, model, self.agent_name,
				kind="Tool Result",
				record_kind="tool_result",
				context_policy="include_reference",
				context_summary=f"large result turn {i}",
				reference_doctype="Agent Tool Call",
				reference_name=f"ATC-TEST-{i}"
			)

		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 6)  # 3 user + 3 tool reference lines

		total_content = "".join(h.get("content", "") for h in history)
		# 3 reference lines ≈ 100-150 chars each; full would be 3×5000=15000+
		self.assertLess(len(total_content), 2000,
			f"History should be compact with include_reference, got {len(total_content)} chars")

	def test_include_summary_policy(self):
		"""Summary policy: context_summary used instead of full content."""
		provider, model = self._get_provider_model()
		self.conv_manager.add_message(
			self.conversation, "agent", "very long agent response " * 100,
			provider, model, self.agent_name,
			context_policy="include_summary",
			context_summary="Agent provided a detailed answer about X."
		)
		history = self.conv_manager.get_conversation_history(self.conversation.name)
		self.assertEqual(len(history), 1)
		self.assertEqual(history[0]["content"], "Agent provided a detailed answer about X.")
		self.assertNotIn("very long agent response", history[0]["content"])


if __name__ == "__main__":
	unittest.main()
