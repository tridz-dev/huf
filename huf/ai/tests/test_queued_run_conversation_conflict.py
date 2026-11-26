"""A write to the conversation row by another request must not fail a run that is executing.

MariaDB with ``innodb_snapshot_isolation`` rejects (error 1020) an update of a row that was
committed after the transaction's read snapshot was taken. These tests use two real connections.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_queued_run_conversation_conflict
"""

import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.agent.integration import _execute_agent_run, run_agent_sync
from huf.testing.factories import (
	make_agent,
	make_agent_conversation,
	make_agent_run,
	make_ai_provider_and_model,
)


def _write_from_other_connection(conversation_id, value):
	"""Commit a change to the conversation row on a separate DB connection."""
	site = frappe.local.site

	def _worker():
		frappe.init(site)
		frappe.connect()
		try:
			frappe.db.set_value("Agent Conversation", conversation_id, "title", value)
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
