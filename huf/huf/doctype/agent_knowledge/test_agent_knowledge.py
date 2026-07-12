# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentKnowledge(HufTestSuite):
	"""`Agent Knowledge` is a child table (istable=1) of the `agent_knowledge`
	field on the `Agent` doctype, so it is tested as rows on a parent Agent."""

	def _make_knowledge_source(self, source_name="_Test Knowledge Source"):
		return frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": source_name,
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

	def _link_knowledge(self, knowledge_source=None, **row_kwargs):
		# Reload rather than mutate self.bootstrap.agent directly: it's a
		# class-level object shared across every test method, and tearDown's
		# db.rollback() only undoes DB state — it doesn't undo in-memory
		# .append() calls on that shared instance, which would otherwise leak
		# rows into later tests.
		agent = frappe.get_doc("Agent", self.bootstrap.agent.name)
		row = {"doctype": "Agent Knowledge"}
		if knowledge_source is not None:
			row["knowledge_source"] = knowledge_source
		row.update(row_kwargs)
		agent.append("agent_knowledge", row)
		agent.save(ignore_permissions=True)
		return agent

	def test_knowledge_row_saved_on_agent(self):
		source = self._make_knowledge_source()
		agent = self._link_knowledge(source.name)

		self.assertEqual(len(agent.agent_knowledge), 1)
		row = agent.agent_knowledge[0]
		self.assertEqual(row.knowledge_source, source.name)
		self.assertEqual(row.parenttype, "Agent")
		self.assertEqual(row.parent, agent.name)
		# field defaults from the child table schema
		self.assertEqual(row.mode, "Optional")

	def test_knowledge_source_required(self):
		with self.assertRaises(frappe.MandatoryError):
			self._link_knowledge()

	def test_invalid_knowledge_source_link_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			self._link_knowledge("_Nonexistent Knowledge Source")

	def test_mandatory_mode_and_budget_fields(self):
		source = self._make_knowledge_source()
		agent = self._link_knowledge(
			source.name,
			mode="Mandatory",
			priority=10,
			max_chunks=3,
			token_budget=500,
		)

		row = agent.agent_knowledge[0]
		self.assertEqual(row.mode, "Mandatory")
		self.assertEqual(row.priority, 10)
		self.assertEqual(row.max_chunks, 3)
		self.assertEqual(row.token_budget, 500)

	def test_multiple_knowledge_rows_keep_order(self):
		first = self._make_knowledge_source("_Test Knowledge Source First")
		second = self._make_knowledge_source("_Test Knowledge Source Second")

		agent = frappe.get_doc("Agent", self.bootstrap.agent.name)
		agent.append("agent_knowledge", {
			"doctype": "Agent Knowledge",
			"knowledge_source": first.name,
		})
		agent.append("agent_knowledge", {
			"doctype": "Agent Knowledge",
			"knowledge_source": second.name,
		})
		agent.save(ignore_permissions=True)

		self.assertEqual(len(agent.agent_knowledge), 2)
		self.assertEqual(agent.agent_knowledge[0].knowledge_source, first.name)
		self.assertEqual(agent.agent_knowledge[1].knowledge_source, second.name)
		self.assertEqual(agent.agent_knowledge[0].idx, 1)
		self.assertEqual(agent.agent_knowledge[1].idx, 2)
