# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Real bench-based end-to-end regression test for TRK-20260924-4fb7
(Tracks/safwan-erooth.ProcedureWritePathBugs).

Unlike test_procedure_proposal.py / test_procedure_runtime.py (frappe-free, run with
plain pytest against hand-stubbed modules), this file needs a real bench and a real site
-- it exercises the full propose -> accept -> approve -> replay path through actual
frappe.get_doc(...).insert() calls, huf.ai.tools.builder, huf.ai.procedure_proposal,
huf.ai.procedure_approval_api, and huf.ai.graph.procedure_runtime.run_agent_procedure_run,
proving the fix works against the real ORM/DB, not just the pure compilation/execution
logic those other two files already cover.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_write_path_bench

Does not call any LLM: the "Agent Run" this test builds is a hand-inserted Agent Run +
Agent Tool Call pair with status="Completed", exactly the shape a real completed run
would have -- this fix touches propose/accept/runtime, not the LLM call itself, so a
live LLM key is not needed to prove it end to end (see Tracks/safwan-erooth
.ProcedureWritePathBugs/README.md "Evidence / how to reproduce" for the equivalent
manual walkthrough this test automates, including the real Google Gemini key run that
originally found both bugs).
"""

from __future__ import annotations

import json
import unittest

import frappe

from huf.ai.graph.procedure_runtime import ProcedureOutcome, run_agent_procedure_run
from huf.ai.procedure_approval_api import approve_procedure
from huf.ai.procedure_proposal import accept_procedure_proposal, propose_procedure_from_run
from huf.ai.tools.builder import create_agent_tool


class TestWritePathEndToEnd(unittest.TestCase):
	"""Propose -> accept -> approve -> replay, for a real write tool, against a real
	site. Bug 1 (schema forbade `recovery`) and Bug 2 (proposer never set
	`idempotency_key`) together made every step from `accept_procedure_proposal` onward
	impossible; this proves the whole chain now works and performs exactly one real
	write.
	"""

	TOOL_NAME = "e2e_create_todo_regression"

	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Agent Tool Function", cls.TOOL_NAME):
			create_agent_tool(
				tool_name=cls.TOOL_NAME,
				description="Create a ToDo (regression test fixture)",
				types="Create Document",
				reference_doctype="ToDo",
				confirm=True,
			)

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Agent Tool Function", cls.TOOL_NAME):
			frappe.delete_doc("Agent Tool Function", cls.TOOL_NAME, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _make_completed_run(self, description: str) -> tuple[str, str]:
		"""Insert an Agent Run + Agent Tool Call pair shaped exactly like a real
		completed run, backed by a REAL ToDo write (not a fake tool_result) -- this is
		what compile_procedure_from_trace consumes, whether the run was truly agentic
		or (as here) hand-built. Returns (agent_run_name, real_todo_name).
		"""
		real_todo = frappe.get_doc({"doctype": "ToDo", "description": description})
		real_todo.insert(ignore_permissions=True)

		run = frappe.get_doc(
			{
				"doctype": "Agent Run",
				"prompt": description,
				"response": f"Created a ToDo: {description}",
			}
		)
		run.insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Agent Tool Call",
				"agent_run": run.name,
				"tool": self.TOOL_NAME,
				"tool_args": json.dumps({"description": description}),
				"tool_result": json.dumps({"name": real_todo.name}),
				"status": "Completed",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return run.name, real_todo.name

	def test_propose_accept_approve_replay_performs_exactly_one_write(self):
		run_name, _real_todo = self._make_completed_run("call the customer (bench e2e test)")

		# 1. Propose: proposable, write node carries the safe default recovery and a
		# None idempotency_key placeholder (procedure_name/version aren't known yet).
		proposal = propose_procedure_from_run(run_name)
		self.assertTrue(proposal["proposable"], proposal.get("reason"))
		graph = proposal["procedure_graph"]
		write_node = graph["nodes"][0]
		self.assertEqual(write_node["config"]["recovery"], "abort")
		self.assertIsNone(write_node["config"]["input"]["idempotency_key"])

		# 2. Accept: the placeholder is replaced with a real, non-empty idempotency_key.
		accepted = accept_procedure_proposal(
			agent_run_name=run_name,
			procedure_graph=graph,
			procedure_name=f"E2E Create Todo {run_name}",
		)
		stored = frappe.db.get_value("Agent Procedure", accepted["name"], "definition_json")
		stored = json.loads(stored) if isinstance(stored, str) else stored
		stamped_node = stored["nodes"][0]
		self.assertEqual(stamped_node["config"]["recovery"], "abort")
		self.assertTrue(stamped_node["config"]["input"]["idempotency_key"])

		# 3. Approve.
		approval = approve_procedure(accepted["name"], approve=True, note="bench e2e test")
		self.assertEqual(approval["approval_status"], "Approved")

		# 4. Replay: this is the step Bug 1/Bug 2 made impossible in any form.
		replay_description = f"call the customer (replay {run_name})"
		proc_run = frappe.get_doc(
			{
				"doctype": "Agent Procedure Run",
				"procedure": accepted["name"],
				"input_payload": json.dumps({"description": replay_description}),
			}
		)
		proc_run.insert(ignore_permissions=True)
		frappe.db.commit()

		count_before = frappe.db.count("ToDo", {"description": replay_description})
		outcome = run_agent_procedure_run(proc_run.name)
		count_after = frappe.db.count("ToDo", {"description": replay_description})

		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS, outcome.error)
		self.assertEqual(count_after, count_before + 1, "expected exactly one real write")


if __name__ == "__main__":
	unittest.main()
