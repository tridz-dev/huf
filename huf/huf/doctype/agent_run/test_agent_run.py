# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe
from frappe.utils import now_datetime

from huf.tests.utils import HufTestSuite


class TestAgentRun(HufTestSuite):
	def _make_conversation(self, session_id="test:run-session"):
		return frappe.get_doc({
			"doctype": "Agent Conversation",
			"title": "Run Test Conversation",
			"agent": self.bootstrap.agent.name,
			"model": self.bootstrap.model.name,
			"session_id": session_id,
			"channel": "test",
		}).insert(ignore_permissions=True)

	def _make_run(self, **overrides):
		doc = {
			"doctype": "Agent Run",
			"agent": self.bootstrap.agent.name,
			"prompt": "What is the weather?",
			"status": "Started",
			"start_time": now_datetime(),
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_run_for_agent(self):
		conversation = self._make_conversation()
		run = self._make_run(conversation=conversation.name)

		self.assertTrue(run.name)
		self.assertEqual(run.agent, self.bootstrap.agent.name)
		self.assertEqual(run.conversation, conversation.name)
		self.assertEqual(run.prompt, "What is the weather?")

	def test_run_kind_defaults_to_agent(self):
		run = self._make_run()

		self.assertEqual(run.run_kind, "agent")

	def test_run_status_lifecycle(self):
		run = self._make_run()

		run.status = "Success"
		run.response = "It is sunny."
		run.input_tokens = 120
		run.output_tokens = 30
		run.cached_tokens = 50
		run.cost = 0.0025
		run.end_time = now_datetime()
		run.save(ignore_permissions=True)
		run.reload()

		self.assertEqual(run.status, "Success")
		self.assertEqual(run.response, "It is sunny.")
		self.assertEqual(run.input_tokens, 120)
		self.assertEqual(run.output_tokens, 30)
		self.assertEqual(run.cached_tokens, 50)
		self.assertEqual(run.cost, 0.0025)
		self.assertTrue(run.end_time)

	def test_child_run_references_parent(self):
		parent = self._make_run()
		child = self._make_run(
			prompt="Step 1 of plan",
			parent_run=parent.name,
			is_child=1,
			run_kind="tool",
		)

		self.assertEqual(child.parent_run, parent.name)
		self.assertEqual(child.is_child, 1)
		self.assertEqual(child.run_kind, "tool")

	def test_invalid_agent_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_run(agent="_Nonexistent Agent")

	def test_knowledge_usage_fields(self):
		sources = [{"source": "_Test Knowledge", "chunks": 3}]
		run = self._make_run(
			knowledge_sources_used=json.dumps(sources),
			chunks_injected=3,
		)

		self.assertEqual(json.loads(run.knowledge_sources_used), sources)
		self.assertEqual(run.chunks_injected, 3)
