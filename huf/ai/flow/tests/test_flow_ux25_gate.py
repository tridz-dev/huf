"""Security round 2 (DECISIONS 13): the test-run gate fails CLOSED, and a step's preview never promises a harmless read."""

import json
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import frappe

from huf.ai.flow.testrun import gate
from huf.ai.flow.testrun.step_test import describe_step


def _boom(*a, **kw):
	raise RuntimeError("database went away")


class TestGateFailsClosed(unittest.TestCase):
	def test_a_failed_lookup_is_treated_as_a_test(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=_boom), patch.object(gate, "_log_doubt") as logged:
			self.assertTrue(gate.agent_run_is_test("AR-1"))
		logged.assert_called_once()
		self.assertIn("AR-1", logged.call_args.args[0])

	def test_the_doubt_is_logged(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=_boom), patch("frappe.logger") as logger:
			self.assertTrue(gate.agent_run_is_test("AR-2"))
		self.assertTrue(logger.return_value.warning.called)
		self.assertIn("treating the call as a test", logger.return_value.warning.call_args.args[0])

	def test_a_failed_second_lookup_is_also_a_test(self):
		calls = iter(["FR-1"])

		def second_fails(doctype, name, field):
			if doctype == "Agent Run":
				return next(calls)
			raise RuntimeError("timeout")

		with patch.object(gate.frappe.db, "get_value", side_effect=second_fails):
			self.assertTrue(gate.agent_run_is_test("AR-3"))

	def test_a_run_that_is_not_a_test_still_runs_for_real(self):
		def lookup(doctype, name, field):
			return {"Agent Run": "FR-9", "Flow Run": "Real"}[doctype]

		with patch.object(gate.frappe.db, "get_value", side_effect=lookup):
			self.assertFalse(gate.agent_run_is_test("AR-4"))
		with patch.object(gate.frappe.db, "get_value", return_value=None):
			self.assertFalse(gate.agent_run_is_test("AR-5"))
		self.assertFalse(gate.agent_run_is_test(None))

	def test_a_test_flow_run_is_a_test(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=lambda dt, n, f: {"Agent Run": "FR-1", "Flow Run": "Test"}[dt]):
			self.assertTrue(gate.agent_run_is_test("AR-6"))

	def test_an_unreadable_step_test_flag_means_test(self):
		fake = MagicMock()
		type(fake.local).flags = PropertyMock(side_effect=RuntimeError("no local"))
		with patch.object(gate, "frappe", fake), patch.object(gate, "_log_doubt") as logged:
			self.assertTrue(gate.step_test_active())
		logged.assert_called_once()

	def test_an_agents_sending_tool_is_simulated_when_the_lookup_fails(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=_boom):
			out = gate.agent_tool_gate("gmail_send_email", {"to": "x@example.invalid"}, {"agent_run_id": "AR-7"})
		self.assertIsNotNone(out)
		self.assertTrue(json.loads(out)["simulated"])

	def test_an_agents_read_still_runs_when_the_lookup_fails(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=_boom):
			self.assertIsNone(gate.agent_tool_gate("gsheets_read", {}, {"agent_run_id": "AR-8"}))

	def test_a_tool_step_whose_inputs_cannot_be_read_is_not_run_if_it_sends(self):
		node = {"type": "tool.call", "config": {"tool_id": "gmail_send_email", "input": {"to": {"$from": "input.email"}, "subject": "Hi"}}}
		out = gate.simulate_node(node, _boom)
		self.assertIsNotNone(out)
		self.assertTrue(out["simulated"])

	def test_a_tool_step_whose_inputs_cannot_be_read_but_only_reads_goes_on_to_say_so(self):
		node = {"type": "tool.call", "config": {"tool_id": "gsheets_read", "input": {"sheet": {"$from": "input.s"}}}}
		self.assertIsNone(gate.simulate_node(node, _boom))

	def test_no_exception_handler_in_the_gate_returns_the_real_answer(self):
		"""Guard for the next change: every `except` in the package that decides test-or-real must log or answer 'test'."""
		import ast
		import pathlib

		for path in pathlib.Path(gate.__file__).parent.glob("*.py"):
			tree = ast.parse(path.read_text())
			for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("agent_run_is_test", "step_test_active")]:
				for handler in [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]:
					returns = [n.value.value for n in ast.walk(handler) if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)]
					self.assertNotIn(False, returns, f"{path.name}:{fn.name} must not fail open")


class TestCodeInATestRun(unittest.TestCase):
	def _profile(self, **row):
		base = {"filesystem_policy": "Scratch Only", "network_policy": None, "allowed_modules": None}
		return patch.object(gate.frappe.db, "get_value", return_value=frappe._dict({**base, **row}))

	def test_the_shipped_scratch_profile_runs_for_real(self):
		with self._profile():
			self.assertTrue(gate.code_profile_is_scratch("Flow Scratch"))
			self.assertTrue(gate.code_profile_is_scratch(None))
			self.assertIsNone(gate.simulate_node({"type": "code.run", "config": {"profile": "Flow Scratch", "code": "x"}}, lambda v: v))

	def test_other_profiles_are_skipped(self):
		for name in ("Trusted", "Restricted", "My Net Profile"):
			out = gate.simulate_node({"type": "code.run", "config": {"profile": name, "code": "x"}}, lambda v: v)
			self.assertTrue(out["simulated"], name)

	def test_a_scratch_profile_that_was_given_network_or_modules_is_skipped(self):
		for row in ({"network_policy": "Allow Docs"}, {"allowed_modules": '["requests"]'}, {"allowed_modules": ["math"]}, {"filesystem_policy": "Shared Directory"}):
			with self._profile(**row):
				self.assertFalse(gate.code_profile_is_scratch("Flow Scratch"), row)
				self.assertTrue(gate.simulate_node({"type": "code.run", "config": {"profile": "Flow Scratch"}}, lambda v: v)["simulated"])

	def test_an_unreadable_profile_is_skipped(self):
		with patch.object(gate.frappe.db, "get_value", side_effect=_boom), patch.object(gate, "_log_doubt"):
			self.assertFalse(gate.code_profile_is_scratch("Flow Scratch"))

	def test_empty_allowed_modules_text_is_fine(self):
		with self._profile(allowed_modules="[]"):
			self.assertTrue(gate.code_profile_is_scratch("Flow Scratch"))


class TestPreviewLabelForTemplatedAction(unittest.TestCase):
	def _info(self, tool_id, **inputs):
		return describe_step({"type": "tool.call", "config": {"tool_id": tool_id, "input": inputs}})

	def test_a_filled_in_action_is_labelled_changes(self):
		for action in ({"$from": "input.action"}, {"$template": "{input.verb}_ticket"}, "{input.action}"):
			info = self._info("helpdesk", action=action)
			self.assertEqual((info["effect"], info["simulated"]), ("changes", True), action)

	def test_a_read_tool_with_a_filled_in_action_is_labelled_changes(self):
		info = self._info("gsheets_read", action={"$from": "input.action"}, sheet="s1")
		self.assertEqual((info["effect"], info["simulated"]), ("changes", True))
		self.assertEqual(self._info("gsheets_read", sheet="s1")["effect"], "reads")

	def test_a_typed_read_action_stays_a_read(self):
		info = self._info("helpdesk", action="list_tickets")
		self.assertEqual((info["effect"], info["simulated"]), ("reads", False))

	def test_a_typed_send_action_still_sends(self):
		self.assertEqual(self._info("telegram", action="send_message")["effect"], "sends")

	def test_a_filled_in_http_method_is_labelled_changes(self):
		info = self._info("http_request", url="https://example.com", method={"$from": "input.method"})
		self.assertEqual((info["effect"], info["simulated"]), ("changes", True))
		self.assertEqual(self._info("http_request", url="https://example.com", method="GET")["effect"], "reads")
		self.assertEqual(self._info("http_request", url={"$from": "input.url"})["effect"], "reads")
