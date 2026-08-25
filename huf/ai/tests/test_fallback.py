# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for huf.ai.graph.fallback (T-32).

Frappe-free, mirroring huf.ai.tests.test_procedure_runtime: :func:`execute_procedure` is
driven directly with a hand-written ``FakeInvoker`` (no frappe, no bench) to produce a real
``ProcedureOutcome``, which is then fed into ``huf.ai.graph.fallback``'s builders. This
proves the fallback module against genuine runtime output, not a hand-rolled stand-in for
it.

Two things this file exists to prove, per T-32's acceptance criteria:

1. An induced failure at EACH Procedure node type (tool.call, transform, condition,
   foreach, validate, output) yields an actionable structured payload -- one test class
   per node type below.
2. Applicability rejection performs provably ZERO side effects: zero tool invocations
   (the stand-in for "zero Agent Tool Call records" in this frappe-free harness -- the
   real ``Agent Tool Call`` doctype is only written by ``huf.ai.tool_invocation`` when a
   tool is actually invoked, so "the fake invoker was never called" is the frappe-free
   proof of the same fact) and the NOT_APPLICABLE payload's shape itself carries no
   partial-state keys at all.
"""

from __future__ import annotations

import copy
import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_standalone_frappe_stub():
	"""See huf.ai.tests.test_graph_permissions._install_standalone_frappe_stub -- same
	underlying gap: this module transitively imports huf.ai.graph.permissions, which
	imports huf.ai.tool_registry, which does ``from frappe.utils import now_datetime`` at
	top level. conftest.py's stub runs too late for the same reason documented there, so
	this file installs its own narrow stub before any ``huf.*`` import, exactly like
	test_graph_permissions.py.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.fallback import (
	PROCEDURE_FAILED_MID_RUN,
	PROCEDURE_NOT_APPLICABLE,
	BoundResult,
	build_fallback,
	build_mid_run_fallback,
	build_not_applicable_fallback,
	classify_write_tool,
)
from huf.ai.graph.permissions import ToolPermission
from huf.ai.graph.procedure_runtime import ProcedureOutcome, ToolInvocation, execute_procedure
from huf.ai.output_budget import OutputBudget

# ---------------------------------------------------------------------------
# Shared fixtures (mirrors test_procedure_runtime.py)
# ---------------------------------------------------------------------------


def _contract(**limits) -> dict:
	defaults = dict(
		max_nodes=50,
		max_rows=1000,
		max_output_bytes=1_000_000,
		max_parallel_calls=4,
		max_foreach_iterations=100,
		max_external_calls=20,
		max_writes=0,
		max_wall_time_ms=30_000,
		fail_closed=True,
	)
	defaults.update(limits)
	return {
		"input_schema": {},
		"output_schema": {},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": defaults,
	}


def _pin(graph: dict) -> PinnedVersion:
	return PinnedVersion.pin(graph)


class FakeInvoker:
	"""Same hand-written double as test_procedure_runtime.py -- no MagicMock affordances."""

	def __init__(self, table: dict[str, object]):
		self.table = table
		self.calls: list[tuple[str, dict]] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append((tool_id, copy.deepcopy(args)))
		if tool_id not in self.table:
			return ToolInvocation(tool_id, args, success=False, error=f"no such tool {tool_id!r}")
		value = self.table[tool_id]
		result = value(args) if callable(value) else value
		return ToolInvocation(tool_id, args, success=True, result=result)


# ``get_customer`` is read, ``update_ledger`` / ``send_notice`` are writes -- a plain dict
# classifier, no frappe.get_cached_doc involved, matching the ToolClassifier contract.
_TOOL_PERMS = {
	"get_customer": ToolPermission(ptype="read", doctype="Customer"),
	"list_invoices": ToolPermission(ptype="read", doctype="Sales Invoice"),
	"update_ledger": ToolPermission(ptype="write", doctype="GL Entry"),
	"send_notice": ToolPermission(ptype="create", doctype="Communication"),
	"unclassifiable": None,  # forces classify_tool to raise -- see fake_classifier
}


def fake_classifier(tool_id: str) -> ToolPermission:
	perm = _TOOL_PERMS.get(tool_id)
	if perm is None:
		raise KeyError(tool_id)
	return perm


# ---------------------------------------------------------------------------
# Applicability rejection -- zero side effects, structurally distinct shape.
# ---------------------------------------------------------------------------


class TestNotApplicableHasNoSideEffects(unittest.TestCase):
	def _graph_with_a_write_that_must_never_run(self):
		return {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "would_write",
			"contract": {**_contract(), "applies_when": ['input["overdue_days"]']},
			"nodes": [
				{
					"id": "would_write",
					"type": "tool.call",
					"config": {"tool_id": "update_ledger", "input": {}},
				}
			],
		}

	def test_applies_when_false_means_zero_tool_invocations(self):
		"""The frappe-free stand-in for "zero Agent Tool Call records": the fake invoker,
		which is the only side-effecting seam ``execute_procedure`` has, is never called.
		"""
		graph = self._graph_with_a_write_that_must_never_run()
		invoker = FakeInvoker({"update_ledger": "should never run"})
		outcome = execute_procedure(_pin(graph), {"overdue_days": 0}, tool_invoker=invoker)

		self.assertEqual(outcome.status, ProcedureOutcome.NOT_APPLICABLE)
		self.assertEqual(invoker.calls, [])  # zero "Agent Tool Call" equivalent records
		self.assertEqual(outcome.node_visits, [])  # zero nodes visited -- no partial execution
		self.assertEqual(outcome.tool_invocations, [])
		self.assertEqual(outcome.node_outputs, {})

	def test_payload_shape_carries_no_partial_state_keys(self):
		"""The NOT_APPLICABLE payload's own shape is the second half of the proof: even a
		caller that never inspected node_visits cannot mistake this for a mid-run failure,
		because the keys that would imply partial state are not present at all.
		"""
		payload = build_not_applicable_fallback(procedure_id="proc-1", version="v1", run="RUN-1")

		self.assertEqual(payload["status"], PROCEDURE_NOT_APPLICABLE)
		self.assertEqual(payload["procedure"], "proc-1")
		self.assertEqual(payload["version"], "v1")
		self.assertEqual(payload["run"], "RUN-1")
		for absent_key in (
			"completed_steps",
			"failed_step",
			"committed_writes",
			"pending_writes",
			"intermediate_outputs",
			"error",
			"safe_recovery_actions",
			"available_atomic_tools",
		):
			self.assertNotIn(absent_key, payload, f"{absent_key!r} must not appear on a not-applicable payload")

	def test_build_fallback_dispatches_not_applicable_from_outcome_alone(self):
		graph = self._graph_with_a_write_that_must_never_run()
		invoker = FakeInvoker({})
		outcome = execute_procedure(_pin(graph), {"overdue_days": 0}, tool_invoker=invoker)

		result = build_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome
		)
		self.assertIsInstance(result, BoundResult)
		self.assertEqual(result.fallback_class, PROCEDURE_NOT_APPLICABLE)
		self.assertNotIn("completed_steps", result.payload)


# ---------------------------------------------------------------------------
# Mid-run failure: one test class per Procedure node type (acceptance criterion).
# ---------------------------------------------------------------------------


class _MidRunFailureCase(unittest.TestCase):
	"""Shared assertions every "failed mid-run" test makes: the payload is the full
	GOAL.md ss2.4 shape, bounded, and distinct from the not-applicable shape.
	"""

	def _assert_actionable_mid_run_payload(self, payload: dict, *, expected_failed_step: str):
		self.assertEqual(payload["status"], PROCEDURE_FAILED_MID_RUN)
		self.assertEqual(payload["failed_step"], expected_failed_step)
		self.assertIsInstance(payload["completed_steps"], list)
		self.assertIsInstance(payload["committed_writes"], list)
		self.assertIsInstance(payload["pending_writes"], list)
		self.assertIsInstance(payload["intermediate_outputs"], dict)
		# BoundedResult.to_dict() shape -- see huf.ai.output_budget.BoundedResult.
		for key in ("summary", "rows", "metadata", "dataset_handle"):
			self.assertIn(key, payload["intermediate_outputs"])
		self.assertTrue(payload["error"])
		self.assertTrue(payload["safe_recovery_actions"], "must give the Agent something actionable")
		self.assertIsInstance(payload["available_atomic_tools"], list)
		# The failed node must never appear in completed_steps.
		self.assertNotIn(
			expected_failed_step, [s["node_id"] for s in payload["completed_steps"]]
		)


class TestToolCallFailure(_MidRunFailureCase):
	def test_write_tool_call_failure_flags_possible_partial_commit(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "get_customer", "input": {}},
					"next": "write",
				},
				{
					"id": "write",
					"type": "tool.call",
					"config": {"tool_id": "update_ledger", "input": {}},
				},
			],
		}
		invoker = FakeInvoker({"get_customer": {"name": "Acme"}})  # update_ledger absent -> fails
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(outcome.node_id, "write")

		payload = build_mid_run_fallback(
			procedure_id="proc-1",
			version="v1",
			run="RUN-1",
			graph=graph,
			outcome=outcome,
			classify_tool=fake_classifier,
		)
		self._assert_actionable_mid_run_payload(payload, expected_failed_step="write")
		self.assertEqual(
			[s["node_id"] for s in payload["completed_steps"]], ["fetch"]
		)
		self.assertEqual(len(payload["committed_writes"]), 1)
		self.assertEqual(payload["committed_writes"][0]["node_id"], "write")
		self.assertEqual(payload["committed_writes"][0]["tool_id"], "update_ledger")
		self.assertFalse(payload["committed_writes"][0]["success"])
		self.assertTrue(
			any("retry" in a.lower() or "verify" in a.lower() for a in payload["safe_recovery_actions"])
		)

	def test_read_tool_call_failure_is_marked_safe_to_retry(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [{"id": "fetch", "type": "tool.call", "config": {"tool_id": "get_customer", "input": {}}}],
		}
		invoker = FakeInvoker({})  # get_customer absent -> fails, read-only
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		self._assert_actionable_mid_run_payload(payload, expected_failed_step="fetch")
		self.assertTrue(any("safe to retry" in a.lower() for a in payload["safe_recovery_actions"]))


class TestTransformFailure(_MidRunFailureCase):
	def test_transform_failure(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "list_invoices", "input": {}},
					"next": "bad_transform",
				},
				{
					"id": "bad_transform",
					"type": "transform",
					"config": {"op": "no_such_op", "input": {"rows": {"$from": "fetch"}}},
				},
			],
		}
		invoker = FakeInvoker({"list_invoices": [{"name": "INV-1"}]})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(outcome.node_id, "bad_transform")

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		self._assert_actionable_mid_run_payload(payload, expected_failed_step="bad_transform")
		self.assertEqual(payload["committed_writes"], [])  # transform never touches a write tool


class TestConditionFailure(_MidRunFailureCase):
	def test_condition_that_fails_to_resolve_a_successor(self):
		"""A condition node with no ``on_false`` successor: the node itself succeeds (it
		evaluates the expression cleanly) but the graph fails to route -- exactly the
		"node type: condition" failure this acceptance criterion asks for. See
		Router.resolve's SELF_ROUTED branch in huf.ai.graph.executor.
		"""
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "check",
			"contract": _contract(),
			"nodes": [
				{
					"id": "check",
					"type": "condition",
					"config": {"expression": 'input["flag"]', "on_true": "out", "on_false": None},
				},
				{"id": "out", "type": "output", "config": {"value": "ok"}},
			],
		}
		outcome = execute_procedure(_pin(graph), {"flag": False}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(outcome.node_id, "check")

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		self._assert_actionable_mid_run_payload(payload, expected_failed_step="check")


class TestValidateFailure(_MidRunFailureCase):
	def test_validate_assertion_failure(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "get_customer", "input": {}},
					"next": "check",
				},
				{
					"id": "check",
					"type": "validate",
					"config": {
						"assertions": [
							{
								"expression": 'fetch["active"]',
								"code": "customer_inactive",
								"message": "customer is not active",
							}
						]
					},
				},
			],
		}
		invoker = FakeInvoker({"get_customer": {"active": False}})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(outcome.node_id, "check")

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		self._assert_actionable_mid_run_payload(payload, expected_failed_step="check")
		self.assertTrue(any("hard stop" in a.lower() for a in payload["safe_recovery_actions"]))


class TestForeachFailure(_MidRunFailureCase):
	def test_foreach_exceeding_max_iterations(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "loop",
			"contract": _contract(),
			"nodes": [
				{
					"id": "loop",
					"type": "foreach",
					"config": {
						"items": {"$from": "input.rows"},
						"max_iterations": 1,
						"body": ["noop"],
						"collect": {"$from": "noop"},
					},
				},
				{"id": "noop", "type": "transform", "config": {"op": "select", "input": {"rows": [], "fields": []}}},
			],
		}
		outcome = execute_procedure(
			_pin(graph), {"rows": [1, 2, 3]}, tool_invoker=FakeInvoker({})
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		# A resource-limit breach can fire before any single node's outcome is recorded --
		# failed_step may be None, but the payload must still be present and actionable.
		self.assertEqual(payload["status"], PROCEDURE_FAILED_MID_RUN)
		self.assertTrue(payload["safe_recovery_actions"])
		self.assertTrue(payload["error"])


class TestOutputFailure(_MidRunFailureCase):
	def test_output_budget_breach_fails_closed(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(max_rows=1, max_output_bytes=1_000_000),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "list_invoices", "input": {}},
					"next": "out",
				},
				{"id": "out", "type": "output", "config": {"value": {"$from": "fetch"}}},
			],
		}
		invoker = FakeInvoker({"list_invoices": [{"name": "INV-1"}, {"name": "INV-2"}]})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		self.assertEqual(payload["status"], PROCEDURE_FAILED_MID_RUN)
		self.assertEqual(payload["committed_writes"], [])
		self.assertTrue(any("already committed" in a.lower() for a in payload["safe_recovery_actions"]))


# ---------------------------------------------------------------------------
# Write/read classification and pending_writes.
# ---------------------------------------------------------------------------


class TestWriteClassification(unittest.TestCase):
	def test_classify_write_tool(self):
		self.assertTrue(classify_write_tool("update_ledger", fake_classifier))
		self.assertTrue(classify_write_tool("send_notice", fake_classifier))
		self.assertFalse(classify_write_tool("get_customer", fake_classifier))

	def test_unclassifiable_tool_fails_closed_as_a_write(self):
		self.assertTrue(classify_write_tool("unclassifiable", fake_classifier))
		self.assertTrue(classify_write_tool("totally_unknown", fake_classifier))

	def test_pending_writes_lists_write_nodes_never_attempted(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "get_customer", "input": {}},
					"next": "mid_write",
				},
				{
					"id": "mid_write",
					"type": "tool.call",
					"config": {"tool_id": "update_ledger", "input": {}},
					"next": "bad_transform",
				},
				{
					"id": "bad_transform",
					"type": "transform",
					"config": {"op": "no_such_op", "input": {}},
					"next": "final_write",
				},
				{
					"id": "final_write",
					"type": "tool.call",
					"config": {"tool_id": "send_notice", "input": {}},
				},
			],
		}
		invoker = FakeInvoker({"get_customer": {"name": "Acme"}, "update_ledger": "ok"})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(outcome.node_id, "bad_transform")

		payload = build_mid_run_fallback(
			procedure_id="proc-1", version="v1", run="RUN-1", graph=graph, outcome=outcome,
			classify_tool=fake_classifier,
		)
		# update_ledger already ran (committed); send_notice never got a chance to run.
		self.assertEqual([w["tool_id"] for w in payload["committed_writes"]], ["update_ledger"])
		self.assertEqual([w["node_id"] for w in payload["pending_writes"]], ["final_write"])
		self.assertEqual(payload["pending_writes"][0]["tool_id"], "send_notice")
		self.assertIn("get_customer", payload["available_atomic_tools"])
		self.assertIn("update_ledger", payload["available_atomic_tools"])
		self.assertIn("send_notice", payload["available_atomic_tools"])


# ---------------------------------------------------------------------------
# Output budget (I7): a fallback payload is never allowed to raise or to dump raw state.
# ---------------------------------------------------------------------------


class TestFallbackPayloadRespectsOutputBudget(unittest.TestCase):
	def test_intermediate_outputs_never_raises_and_never_exceeds_budget(self):
		big_rows = [{"idx": i, "padding": "x" * 200} for i in range(500)]
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "list_invoices", "input": {}},
					"next": "bad_transform",
				},
				{
					"id": "bad_transform",
					"type": "transform",
					"config": {"op": "no_such_op", "input": {}},
				},
			],
		}
		invoker = FakeInvoker({"list_invoices": big_rows})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)

		tiny_budget = OutputBudget(max_rows=5, max_bytes=200, max_inline_chars=100)
		# Must not raise (I9: never fails the Agent), even though the intermediate output
		# is far larger than the budget allows.
		payload = build_mid_run_fallback(
			procedure_id="proc-1",
			version="v1",
			run="RUN-1",
			graph=graph,
			outcome=outcome,
			classify_tool=fake_classifier,
			budget=tiny_budget,
		)
		intermediate = payload["intermediate_outputs"]
		self.assertIsNotNone(intermediate["dataset_handle"])
		self.assertTrue(intermediate["dataset_handle"].get("spilled"))
		# The raw 500-row payload must never appear inline.
		self.assertLess(len(intermediate["rows"]), 500)

	def test_build_fallback_rejects_success_outcome(self):
		outcome = ProcedureOutcome(status=ProcedureOutcome.SUCCESS, output={"ok": True})
		with self.assertRaises(ValueError):
			build_fallback(procedure_id="p", version="v1", run=None, graph={"entry": None, "nodes": []}, outcome=outcome)

	def test_build_mid_run_fallback_rejects_non_failed_outcome(self):
		outcome = ProcedureOutcome(status=ProcedureOutcome.NOT_APPLICABLE)
		with self.assertRaises(ValueError):
			build_mid_run_fallback(
				procedure_id="p", version="v1", run=None, graph={"entry": None, "nodes": []}, outcome=outcome
			)


if __name__ == "__main__":
	unittest.main()
