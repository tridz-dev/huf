"""A write to the conversation row by another request must not fail a run that is executing.

MariaDB with ``innodb_snapshot_isolation`` rejects (error 1020) an update of a row that was
committed after the transaction's read snapshot was taken. These tests use two real connections.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_queued_run_conversation_conflict
"""

import unittest
from concurrent.futures import ThreadPoolExecutor, wait
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.agent.integration import (
	_execute_agent_run,
	_save_partial_reply,
	generate_conversation_title,
	run_agent_sync,
)
from huf.ai.conversation_manager import ConversationManager
from huf.testing.factories import (
	make_agent,
	make_agent_conversation,
	make_agent_run,
	make_ai_provider_and_model,
)


def _write_from_other_connection(conversation_id, value, field="title"):
	"""Commit a change to the conversation row on a separate DB connection."""
	site = frappe.local.site

	def _worker():
		frappe.init(site)
		frappe.connect()
		try:
			frappe.db.set_value("Agent Conversation", conversation_id, field, value)
			frappe.db.commit()  # nosemgrep: test needs a second, committed transaction
		finally:
			frappe.destroy()

	with ThreadPoolExecutor(max_workers=1) as executor:
		executor.submit(_worker).result(timeout=30)


def _read_row(conversation_id):
	"""A consistent read, which opens this transaction's snapshot."""
	return frappe.db.sql("select title from `tabAgent Conversation` where name=%s", conversation_id)


class TestQueuedRunConversationConflict(unittest.TestCase):
	def setUp(self):
		if not frappe.db.sql("show variables like 'innodb_snapshot_isolation'"):
			self.skipTest("database has no innodb_snapshot_isolation")
		frappe.db.sql("set session innodb_snapshot_isolation=ON")
		self.provider, self.model = make_ai_provider_and_model()
		self.agent = make_agent(provider=self.provider, model=self.model)
		self.conversation = make_agent_conversation(agent=self.agent.name, model=self.model)
		self.run = make_agent_run(
			conversation=self.conversation.name,
			agent=self.agent.name,
			provider=self.provider,
			model=self.model,
			status="Queued",
			prompt="hello",
		)
		frappe.db.commit()  # nosemgrep: fixtures must be visible to the second connection
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.rollback()
		for doctype in ("Agent Message", "Agent Run"):
			frappe.db.delete(doctype, {"agent": self.agent.name})
		frappe.db.delete("Agent Conversation", {"agent": self.agent.name})
		frappe.db.delete("Agent", {"name": self.agent.name})
		frappe.db.delete("AI Model", {"name": self.model})
		frappe.db.delete("AI Provider", {"name": self.provider})
		frappe.db.commit()  # nosemgrep: remove committed fixtures

	def _execute(self, during_provider_call=None):
		async def _provider(*args, **kwargs):
			if during_provider_call:
				during_provider_call()
			return SimpleNamespace(
				final_output="the reply",
				new_items=[],
				usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
				cost=0,
			)

		with patch("huf.ai.agent.integration.RunProvider.run", new=_provider):
			return _execute_agent_run(
				agent_name=self.agent.name,
				run_id=self.run.name,
				conversation_id=self.conversation.name,
				prompt="hello",
				provider=self.provider,
				model=self.model,
				channel_id="api",
			)

	def _assert_reply_kept(self, result):
		self.assertTrue(result.get("success"), result.get("error"))
		self.assertEqual(frappe.db.get_value("Agent Run", self.run.name, "status"), "Success")
		self.assertEqual(frappe.db.get_value("Agent Run", self.run.name, "response"), "the reply")
		self.assertEqual(frappe.db.get_value("Agent Conversation", self.conversation.name, "total_tokens"), 5)

	def test_row_changed_during_provider_call(self):
		result = self._execute(lambda: _write_from_other_connection(self.conversation.name, "second"))
		self._assert_reply_kept(result)

	def test_row_changed_just_before_token_totals_update(self):
		def _cost(*args, **kwargs):
			_read_row(self.conversation.name)
			_write_from_other_connection(self.conversation.name, "second")
			return 0.0, "test"

		with patch("huf.ai.cost_calculator.calculate_cost", new=_cost):
			result = self._execute()
		self._assert_reply_kept(result)

	def test_queued_submit_leaves_conversation_row_alone_when_model_is_unchanged(self):
		before = frappe.db.get_value("Agent Conversation", self.conversation.name, "modified")
		with patch("huf.ai.agent.integration.frappe.enqueue"):
			result = run_agent_sync(
				agent_name=self.agent.name, prompt="second", conversation_id=self.conversation.name
			)
		self.assertTrue(result.get("queued"))
		self.assertEqual(
			frappe.db.get_value("Agent Conversation", self.conversation.name, "modified"), before
		)

	def test_partial_reply_saved_after_row_changed_under_open_snapshot(self):
		conversation = frappe.get_doc("Agent Conversation", self.conversation.name)
		_read_row(conversation.name)  # the stream's snapshot, older than the next write
		_write_from_other_connection(conversation.name, "second")
		saved = _save_partial_reply(
			ConversationManager(agent_name=self.agent.name),
			conversation,
			"partial",
			self.provider,
			self.model,
			self.agent.name,
			self.run.name,
		)
		self.assertTrue(saved)
		self.assertTrue(frappe.db.exists("Agent Message", {"agent_run": self.run.name, "content": "partial"}))

	def test_partial_reply_saved_when_another_write_arrives_mid_save(self):
		conversation = frappe.get_doc("Agent Conversation", self.conversation.name)
		has_permission = frappe.has_permission
		writer = ThreadPoolExecutor(max_workers=1)
		self.addCleanup(writer.shutdown)
		writes = []

		def _write_mid_save(*args, **kwargs):
			if not writes:  # does not return until the save commits if the row is locked
				writes.append(writer.submit(_write_from_other_connection, conversation.name, "second"))
				wait(writes, timeout=2)
			return has_permission(*args, **kwargs)

		with patch("frappe.has_permission", new=_write_mid_save):
			saved = _save_partial_reply(
				ConversationManager(agent_name=self.agent.name),
				conversation,
				"partial",
				self.provider,
				self.model,
				self.agent.name,
				self.run.name,
			)
		frappe.db.commit()  # nosemgrep: release the row lock for the second connection
		writes[0].result(timeout=30)
		self.assertTrue(saved)

	def _generate_title(self, field, value):
		"""Run title generation while another request writes ``field`` during the model call."""
		name = self.conversation.name
		frappe.db.set_value("Agent Conversation", name, "title", "Chat with test")
		frappe.db.commit()  # nosemgrep: fixture must be visible to the second connection

		async def _completion(*args, **kwargs):
			_write_from_other_connection(name, value, field)
			return "Generated title"

		history = [{"role": "user", "content": "hello"}]
		with (
			patch.object(ConversationManager, "get_conversation_history", return_value=history),
			patch("huf.ai.providers.litellm.get_simple_completion", new=_completion),
		):
			generate_conversation_title(name, self.agent.name)
		frappe.db.rollback()
		return frappe.db.get_value("Agent Conversation", name, "title")

	def test_title_saved_when_row_changes_during_generation(self):
		self.assertEqual(self._generate_title("total_messages", 7), "Generated title")

	def test_title_generation_keeps_a_rename_made_during_the_call(self):
		self.assertEqual(self._generate_title("title", "My name"), "My name")
