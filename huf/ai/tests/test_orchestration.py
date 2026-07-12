# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""
Tests for the orchestration backend (huf/ai/orchestration/):
- parse_plan_steps / create_orchestration (orchestrator.py)
- run_planning (planning.py)
- process_orchestrations (scheduler.py)

All provider calls (run_agent_sync / run_planning) are mocked — no live LLM
access is required. DB-backed tests use HufTestSuite's bootstrap agent.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_orchestration
"""

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime

from huf.ai.orchestration.orchestrator import create_orchestration, parse_plan_steps
from huf.ai.orchestration.planning import PLANNING_PROMPT, run_planning
from huf.ai.orchestration.scheduler import JOB_TIMEOUT_SECONDS, process_orchestrations
from huf.tests.utils import HufTestSuite


class TestParsePlanSteps(unittest.TestCase):
	"""parse_plan_steps converts an LLM-produced numbered list into a python
	list of step strings. The planner contract (PLANNING_PROMPT) demands a
	plain numbered list, so anything else — JSON, prose, bullets — must be
	rejected (yield []) rather than produce garbage steps."""

	# ------------------------------------------------------------------
	# Happy path
	# ------------------------------------------------------------------

	def test_standard_numbered_list(self):
		text = "1. Create the parent document\n2. Create the child document\n3. Submit the parent"
		self.assertEqual(
			parse_plan_steps(text),
			["Create the parent document", "Create the child document", "Submit the parent"],
		)

	def test_all_supported_separators(self):
		# ".", ")" and ":" are all recognised as number separators.
		text = "1. Period step\n2) Paren step\n3: Colon step"
		self.assertEqual(parse_plan_steps(text), ["Period step", "Paren step", "Colon step"])

	def test_multi_digit_step_numbers(self):
		text = "9. Ninth step\n10. Tenth step"
		self.assertEqual(parse_plan_steps(text), ["Ninth step", "Tenth step"])

	def test_period_separator_takes_priority(self):
		# Separators are tried in the order [".", ")", ":"]; a line that
		# contains both "." and ":" splits on the period first.
		self.assertEqual(parse_plan_steps("1. Do this: carefully"), ["Do this: carefully"])

	def test_internal_separator_text_preserved(self):
		# split(sep, 1) only splits on the first occurrence.
		self.assertEqual(parse_plan_steps("1. Step with 2. inner number"), ["Step with 2. inner number"])

	def test_falls_through_to_next_separator_when_prefix_not_numeric(self):
		# "1) Done. Next": the "." split yields prefix "1) Done" (not numeric),
		# so the parser continues and eventually splits on ")".
		self.assertEqual(parse_plan_steps("1) Done. Next"), ["Done. Next"])

	def test_whitespace_and_blank_lines_handled(self):
		text = "\n  1. First\n\n\t2. Second  \n"
		self.assertEqual(parse_plan_steps(text), ["First", "Second"])

	# ------------------------------------------------------------------
	# Empty / malformed input
	# ------------------------------------------------------------------

	def test_none_and_empty_input_return_empty(self):
		self.assertEqual(parse_plan_steps(None), [])
		self.assertEqual(parse_plan_steps(""), [])
		self.assertEqual(parse_plan_steps("   \n  \n"), [])

	def test_non_digit_lines_ignored(self):
		# Preamble, bullets, prose and closing remarks never produce steps.
		text = "Here is the plan:\n1. Real step\n- bullet\nStep 2: fake\n2. Another real step\nThanks!"
		self.assertEqual(parse_plan_steps(text), ["Real step", "Another real step"])

	def test_numbered_line_without_separator_skipped(self):
		self.assertEqual(parse_plan_steps("1 just do it"), [])
		self.assertEqual(parse_plan_steps("1"), [])

	def test_non_numeric_prefix_skipped(self):
		# Starts with a digit but the part before the separator is not purely
		# numeric, so it must not be treated as a step.
		self.assertEqual(parse_plan_steps("1a. Not a step"), [])

	def test_empty_step_text_after_separator_skipped(self):
		# "1." and "2.   " carry no instruction text and are dropped.
		text = "1.\n2.   \n3. Real step"
		self.assertEqual(parse_plan_steps(text), ["Real step"])

	def test_json_formatted_plan_yields_no_steps(self):
		# A model that ignores the numbered-list contract and answers with
		# JSON must result in an empty plan (which create_orchestration then
		# turns into a Failed orchestration), not bogus steps.
		pretty = '{\n  "steps": [\n    "1. Create parent",\n    "2. Create child"\n  ]\n}'
		self.assertEqual(parse_plan_steps(pretty), [])
		self.assertEqual(parse_plan_steps('{"steps": ["1. Create parent"]}'), [])

	# ------------------------------------------------------------------
	# Documented quirks of the digit-prefix heuristic
	# ------------------------------------------------------------------

	def test_year_like_prefix_parsed_as_step(self):
		# Any purely-numeric prefix qualifies, even a year.
		self.assertEqual(parse_plan_steps("2024. Annual review"), ["Annual review"])

	def test_decimal_number_splits_on_period(self):
		# "1.5 litres" starts with digit "1" and contains ".", so the first
		# split wins and the remainder becomes the step text.
		self.assertEqual(parse_plan_steps("1.5 litres of milk"), ["5 litres of milk"])


class TestRunPlanning(unittest.TestCase):
	"""run_planning wraps run_agent_sync with the planning prompt. Tests mock
	run_agent_sync — no live provider call — and cover the failure/exception
	fallbacks, which must return "" so callers fall into their empty-plan
	validation path."""

	@patch("huf.ai.agent_integration.run_agent_sync")
	def test_success_returns_response_text(self, mock_run):
		mock_run.return_value = {"success": True, "response": "1. Step one\n2. Step two"}
		result = run_planning("Test Agent", "Build a thing", "Test Provider", "Test Model",
			conversation_id="CONV-1")
		self.assertEqual(result, "1. Step one\n2. Step two")

		kwargs = mock_run.call_args.kwargs
		self.assertEqual(kwargs["agent_name"], "Test Agent")
		self.assertEqual(kwargs["provider"], "Test Provider")
		self.assertEqual(kwargs["model"], "Test Model")
		self.assertEqual(kwargs["channel_id"], "orchestration_planning")
		self.assertEqual(kwargs["conversation_id"], "CONV-1")
		# The prompt must carry both the planning contract and the objective.
		self.assertIn(PLANNING_PROMPT, kwargs["prompt"])
		self.assertIn("Build a thing", kwargs["prompt"])

	@patch("huf.ai.agent_integration.run_agent_sync")
	def test_success_without_response_key_returns_empty(self, mock_run):
		mock_run.return_value = {"success": True}
		self.assertEqual(run_planning("A", "obj", "P", "M"), "")

	@patch("frappe.log_error")
	@patch("huf.ai.agent_integration.run_agent_sync")
	def test_failure_logs_and_returns_empty(self, mock_run, mock_log):
		mock_run.return_value = {"success": False, "error": "rate limited"}
		self.assertEqual(run_planning("Test Agent", "obj", "P", "M"), "")
		mock_log.assert_called_once()
		self.assertIn("rate limited", mock_log.call_args.args[0])

	@patch("frappe.log_error")
	@patch("huf.ai.agent_integration.run_agent_sync")
	def test_exception_logs_and_returns_empty(self, mock_run, mock_log):
		mock_run.side_effect = RuntimeError("kaboom")
		self.assertEqual(run_planning("Test Agent", "obj", "P", "M"), "")
		mock_log.assert_called_once()
		self.assertIn("kaboom", mock_log.call_args.args[0])


class TestCreateOrchestration(HufTestSuite):
	"""DB-backed tests for create_orchestration's plan-selection order
	(override_plan > agent.default_plan > generated plan) and its empty-plan
	validation. run_planning is always mocked — no live LLM call."""

	def setUp(self):
		if not frappe.db.exists("DocType", "Agent Orchestration"):
			self.skipTest("Agent Orchestration DocType not installed")
		self._created_orchestrations = []
		self._created_agents = []

	def tearDown(self):
		# create_orchestration commits internally, so rollback alone cannot
		# undo it — remove created documents explicitly.
		for name in self._created_orchestrations:
			frappe.db.sql("DELETE FROM `tabAgent Orchestration Plan` WHERE parent = %s", name)
			frappe.db.sql("DELETE FROM `tabAgent Orchestration` WHERE name = %s", name)
		for name in self._created_agents:
			try:
				frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDown()

	def _bootstrap_agent_has_no_default_plan(self):
		agent = frappe.get_doc("Agent", self.bootstrap.AGENT_NAME)
		if agent.default_plan:
			self.skipTest("_Test Agent unexpectedly has a default_plan")
		return agent

	def test_override_plan_creates_running_orchestration(self):
		with patch("huf.ai.orchestration.orchestrator.run_planning") as mock_plan:
			name = create_orchestration(
				agent_name=self.bootstrap.AGENT_NAME,
				user_prompt="test objective",
				override_plan=["First step", "Second step"],
			)
		self._created_orchestrations.append(name)

		# An explicit override must never trigger planning.
		mock_plan.assert_not_called()

		orch = frappe.get_doc("Agent Orchestration", name)
		self.assertEqual(orch.status, "Running")
		self.assertEqual(orch.current_step, 0)
		self.assertEqual(len(orch.agent_orchestration_plan), 2)
		# Override steps are re-indexed 1..n in order.
		self.assertEqual(orch.agent_orchestration_plan[0].step_index, 1)
		self.assertEqual(orch.agent_orchestration_plan[0].instruction, "First step")
		self.assertEqual(orch.agent_orchestration_plan[0].status, "pending")
		self.assertEqual(orch.agent_orchestration_plan[1].step_index, 2)
		self.assertEqual(orch.agent_orchestration_plan[1].instruction, "Second step")

	def test_default_plan_reused_without_planning(self):
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "_Test Orch Agent",
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test agent.",
		})
		# Default-plan rows carry their own step_index values; the reuse path
		# copies them verbatim (unlike the override path, which re-indexes).
		agent.append("default_plan", {"step_index": 5, "instruction": "Reused step one", "status": "pending"})
		agent.append("default_plan", {"step_index": 9, "instruction": "Reused step two", "status": "pending"})
		agent.insert(ignore_permissions=True)
		frappe.db.commit()
		self._created_agents.append(agent.name)

		with patch("huf.ai.orchestration.orchestrator.run_planning") as mock_plan:
			name = create_orchestration(agent_name=agent.name, user_prompt="test objective")
		self._created_orchestrations.append(name)

		mock_plan.assert_not_called()
		orch = frappe.get_doc("Agent Orchestration", name)
		self.assertEqual(orch.status, "Running")
		self.assertEqual(len(orch.agent_orchestration_plan), 2)
		self.assertEqual(
			[s.step_index for s in orch.agent_orchestration_plan], [5, 9]
		)
		self.assertEqual(orch.agent_orchestration_plan[0].instruction, "Reused step one")

	def test_unparseable_plan_output_marks_failed(self):
		agent = self._bootstrap_agent_has_no_default_plan()
		# Model answers with JSON instead of the contracted numbered list:
		# parse_plan_steps yields [], so the orchestration must fail loudly.
		with patch("huf.ai.orchestration.orchestrator.run_planning",
				return_value='{"steps": ["a", "b"]}') as mock_plan:
			name = create_orchestration(agent_name=agent.name, user_prompt="test objective")
		self._created_orchestrations.append(name)

		mock_plan.assert_called_once()
		orch = frappe.get_doc("Agent Orchestration", name)
		self.assertEqual(orch.status, "Failed")
		self.assertEqual(len(orch.agent_orchestration_plan), 0)
		self.assertIn("Planning failed", orch.error_log)

	def test_empty_planning_response_marks_failed(self):
		agent = self._bootstrap_agent_has_no_default_plan()
		# run_planning returns "" on provider failure — same validation path.
		with patch("huf.ai.orchestration.orchestrator.run_planning", return_value="") as mock_plan:
			name = create_orchestration(agent_name=agent.name, user_prompt="test objective")
		self._created_orchestrations.append(name)

		mock_plan.assert_called_once()
		orch = frappe.get_doc("Agent Orchestration", name)
		self.assertEqual(orch.status, "Failed")
		self.assertEqual(len(orch.agent_orchestration_plan), 0)
		self.assertIn("Planning failed", orch.error_log)

	def test_empty_override_plan_falls_through_to_planning(self):
		agent = self._bootstrap_agent_has_no_default_plan()
		# Edge case: override_plan=[] is falsy, so it is NOT treated as an
		# override — the generated-plan path runs instead.
		with patch("huf.ai.orchestration.orchestrator.run_planning",
				return_value="1. Generated step") as mock_plan:
			name = create_orchestration(
				agent_name=agent.name, user_prompt="test objective", override_plan=[]
			)
		self._created_orchestrations.append(name)

		mock_plan.assert_called_once()
		orch = frappe.get_doc("Agent Orchestration", name)
		self.assertEqual(orch.status, "Running")
		self.assertEqual(len(orch.agent_orchestration_plan), 1)
		self.assertEqual(orch.agent_orchestration_plan[0].instruction, "Generated step")


class TestProcessOrchestrations(unittest.TestCase):
	"""process_orchestrations runs every minute: it must skip orchestrations
	with a live in-progress step, fail steps stuck past JOB_TIMEOUT_SECONDS,
	enqueue idle ones, and survive per-document errors. All frappe DB/queue
	calls are mocked so these tests need no site data."""

	def _make_step(self, status, modified=None, step_index=1):
		step = MagicMock()
		step.status = status
		step.modified = modified
		step.step_index = step_index
		return step

	def _make_orch(self, steps, name="ORCH-TEST-1", status="Running"):
		orch = MagicMock()
		orch.name = name
		orch.status = status
		orch.error_log = ""
		orch.agent_orchestration_plan = steps
		return orch

	def test_missing_doctype_short_circuits(self):
		with patch.object(frappe.db, "exists", return_value=False), \
				patch("frappe.get_all") as mock_get_all:
			process_orchestrations()
		mock_get_all.assert_not_called()

	def test_idle_orchestration_enqueued(self):
		orch = self._make_orch([
			self._make_step("pending"),
			self._make_step("pending", step_index=2),
		])
		with patch.object(frappe.db, "exists", return_value=True), \
				patch("frappe.get_all", return_value=[frappe._dict(name="ORCH-TEST-1")]), \
				patch("frappe.get_doc", return_value=orch), \
				patch("frappe.enqueue") as mock_enqueue:
			process_orchestrations()

		mock_enqueue.assert_called_once_with(
			"huf.ai.orchestration.orchestrator.execute_next_step",
			queue="default",
			timeout=1200,
			orch=orch,
			orch_name="ORCH-TEST-1",
		)

	def test_in_progress_step_within_timeout_not_enqueued(self):
		step = self._make_step("in_progress", modified=now_datetime())
		orch = self._make_orch([step])
		with patch.object(frappe.db, "exists", return_value=True), \
				patch("frappe.get_all", return_value=[frappe._dict(name="ORCH-TEST-1")]), \
				patch("frappe.get_doc", return_value=orch), \
				patch("frappe.enqueue") as mock_enqueue:
			process_orchestrations()

		# A step still inside its 15-minute budget is left alone.
		mock_enqueue.assert_not_called()
		orch.save.assert_not_called()
		self.assertEqual(step.status, "in_progress")
		self.assertEqual(orch.status, "Running")

	def test_stuck_in_progress_step_marked_failed(self):
		stuck_since = now_datetime() - timedelta(seconds=JOB_TIMEOUT_SECONDS + 60)
		step = self._make_step("in_progress", modified=stuck_since)
		orch = self._make_orch([step])
		with patch.object(frappe.db, "exists", return_value=True), \
				patch("frappe.get_all", return_value=[frappe._dict(name="ORCH-TEST-1")]), \
				patch("frappe.get_doc", return_value=orch), \
				patch("frappe.log_error") as mock_log, \
				patch.object(frappe.db, "commit"), \
				patch("frappe.enqueue") as mock_enqueue:
			process_orchestrations()

		self.assertEqual(step.status, "failed")
		self.assertEqual(orch.status, "Failed")
		self.assertIn("timed out", orch.error_log)
		orch.save.assert_called_once_with(ignore_permissions=True)
		mock_log.assert_called_once()
		mock_enqueue.assert_not_called()

	def test_doc_load_failure_logged_and_others_continue(self):
		good_orch = self._make_orch([self._make_step("pending")], name="GOOD")

		def fake_get_doc(doctype, name):
			if name == "BAD":
				raise Exception("corrupt row")
			return good_orch

		with patch.object(frappe.db, "exists", return_value=True), \
				patch("frappe.get_all", return_value=[frappe._dict(name="BAD"), frappe._dict(name="GOOD")]), \
				patch("frappe.get_doc", side_effect=fake_get_doc), \
				patch("frappe.log_error") as mock_log, \
				patch("frappe.enqueue") as mock_enqueue:
			process_orchestrations()

		# The failing document is logged, but the loop still enqueues the
		# healthy orchestration.
		mock_log.assert_called_once()
		mock_enqueue.assert_called_once()
		self.assertEqual(mock_enqueue.call_args.kwargs["orch_name"], "GOOD")


if __name__ == "__main__":
	unittest.main()
