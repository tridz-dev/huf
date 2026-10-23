# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for the T-32 fallback WIRING (as opposed to test_fallback.py, which covers the
payload builders themselves).

Two seams are exercised here:

1. ``huf.ai.graph.procedure_runtime.persist_fallback_state`` -- the frappe-free half of
   ``run_agent_procedure_run``'s persistence. Driven with a hand-written ``FakeRun``
   document double that records exactly which attributes were assigned, so
   "``completed_steps`` was never written" is a positive assertion rather than a check
   for a falsy value.

2. ``huf.ai.graph.procedure_binding.invoke_bound_procedure`` -- driven with a hand-written
   ``FakeFrappe`` double patched in via ``patch.object`` + ``addCleanup``. Nothing is ever
   assigned onto the real (or stubbed) ``frappe`` module, and no ``MagicMock``-only
   affordance (``.side_effect`` and friends) is relied on: the doubles are plain classes
   whose behaviour is explicit.

Both ``ProcedureOutcome`` values used below come from a real ``execute_procedure`` run
against a real graph, not from a hand-built outcome, so the wiring is proved against
genuine runtime output.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _install_standalone_frappe_stub():
	"""See huf.ai.tests.test_fallback._install_standalone_frappe_stub -- identical gap and
	identical narrow stub. On a real bench ``frappe`` has a ``__file__`` and is left alone.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: lambda f: f

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph import procedure_binding, procedure_runtime
from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.fallback import (
	PROCEDURE_FAILED_MID_RUN,
	PROCEDURE_NOT_APPLICABLE,
	build_fallback,
)
from huf.ai.graph.permissions import ToolPermission
from huf.ai.graph.procedure_binding import BoundProcedure, invoke_bound_procedure
from huf.ai.graph.procedure_runtime import (
	ProcedureOutcome,
	ToolInvocation,
	execute_procedure,
	persist_fallback_state,
)

_PARTIAL_STATE_FIELDS = (
	"completed_steps",
	"failed_step",
	"committed_writes",
	"pending_writes",
	"intermediate_outputs",
	"safe_recovery_actions",
)


def _contract(**overrides) -> dict:
	contract = {
		"input_schema": {},
		"output_schema": {},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": {
			"max_nodes": 50,
			"max_rows": 1000,
			"max_output_bytes": 1_000_000,
			"max_parallel_calls": 4,
			"max_foreach_iterations": 100,
			"max_external_calls": 20,
			"max_writes": 5,
			"max_wall_time_ms": 30_000,
			"fail_closed": True,
		},
	}
	contract.update(overrides)
	return contract


_TOOL_PERMS = {
	"update_ledger": ToolPermission(ptype="write", doctype="GL Entry"),
	"send_notice": ToolPermission(ptype="create", doctype="Communication"),
}


def fake_classifier(tool_id: str) -> ToolPermission:
	perm = _TOOL_PERMS.get(tool_id)
	if perm is None:
		raise KeyError(tool_id)
	return perm


def _failing_write_graph(*, applies_when: list[str] | None = None) -> dict:
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "post_ledger",
		"contract": _contract(applies_when=applies_when or []),
		"nodes": [
			{
				"id": "post_ledger",
				"type": "tool.call",
				"config": {"tool_id": "update_ledger", "input": {}},
				"next": "notify",
			},
			{"id": "notify", "type": "tool.call", "config": {"tool_id": "send_notice", "input": {}}},
		],
	}


class RecordingInvoker:
	"""Hand-written ``ToolInvoker``: ``update_ledger`` always reports failure."""

	def __init__(self):
		self.calls: list[str] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append(tool_id)
		return ToolInvocation(tool_id, args, success=False, error=f"{tool_id} rejected by ERP")


def _failed_outcome() -> ProcedureOutcome:
	invoker = RecordingInvoker()
	outcome = execute_procedure(PinnedVersion.pin(_failing_write_graph()), {}, tool_invoker=invoker)
	if outcome.status != ProcedureOutcome.FAILED:
		raise AssertionError(outcome)
	return outcome


def _not_applicable_outcome() -> tuple[ProcedureOutcome, RecordingInvoker]:
	invoker = RecordingInvoker()
	graph = _failing_write_graph(applies_when=['input["overdue"]'])
	outcome = execute_procedure(PinnedVersion.pin(graph), {"overdue": 0}, tool_invoker=invoker)
	if outcome.status != ProcedureOutcome.NOT_APPLICABLE:
		raise AssertionError(outcome)
	return outcome, invoker


class FakeRun:
	"""Stand-in for an ``Agent Procedure Run`` document.

	Records every attribute assignment in ``assigned`` so a test can assert a field was
	*never written*, which is a strictly stronger claim than "the field is falsy".
	"""

	def __init__(self, name="APR-0001", procedure="PROC-1", procedure_id="collections", fingerprint="fp1"):
		object.__setattr__(self, "assigned", set())
		self.name = name
		self.procedure = procedure
		self.procedure_id = procedure_id
		self.pinned_fingerprint = fingerprint
		object.__setattr__(self, "assigned", set())

	def __setattr__(self, key, value):
		self.assigned.add(key)
		object.__setattr__(self, key, value)

	def insert(self, ignore_permissions=False):
		return self

	def save(self, ignore_permissions=False):
		return self


# ---------------------------------------------------------------------------
# persist_fallback_state -- what lands on the run record.
# ---------------------------------------------------------------------------


class TestPersistMidRunFailure(unittest.TestCase):
	def _persist(self):
		outcome = _failed_outcome()
		run = FakeRun()
		result = build_fallback(
			procedure_id=run.procedure_id,
			version=run.pinned_fingerprint,
			run=run.name,
			graph=_failing_write_graph(),
			outcome=outcome,
			classify_tool=fake_classifier,
		)
		payload = persist_fallback_state(run, result)
		return run, payload

	def test_every_recovery_field_is_populated(self):
		run, payload = self._persist()
		self.assertEqual(payload["status"], PROCEDURE_FAILED_MID_RUN)
		for field in _PARTIAL_STATE_FIELDS:
			self.assertIn(field, run.assigned, f"{field} should be persisted on a mid-run failure")
		self.assertIn("error", run.assigned)

	def test_committed_writes_records_the_attempted_write(self):
		run, _payload = self._persist()
		committed = json.loads(run.committed_writes)
		self.assertEqual([w["tool_id"] for w in committed], ["update_ledger"])
		# The write reported failure, yet it is still recorded as attempted -- this is the
		# retry-duplicates-a-write guard.
		self.assertFalse(committed[0]["success"])
		self.assertEqual(run.failed_step, "post_ledger")

	def test_pending_write_is_the_node_that_never_ran(self):
		run, _payload = self._persist()
		pending = json.loads(run.pending_writes)
		self.assertEqual([p["node_id"] for p in pending], ["notify"])

	def test_intermediate_outputs_keep_the_output_budget_envelope(self):
		"""Persisted verbatim from the budget layer -- never a raw node_outputs blob.

		The presence of the budget's own ``summary``/``rows``/``metadata``/``dataset_handle``
		keys is the proof the value came through ``enforce_output_budget`` (I7) rather than
		being read off ``outcome.node_outputs`` directly.
		"""
		run, payload = self._persist()
		stored = json.loads(run.intermediate_outputs)
		self.assertEqual(set(stored), {"summary", "rows", "metadata", "dataset_handle"})
		self.assertEqual(stored, payload["intermediate_outputs"])

	def test_error_is_structured_and_actionable(self):
		run, _payload = self._persist()
		stored = json.loads(run.error)
		self.assertEqual(stored["status"], PROCEDURE_FAILED_MID_RUN)
		self.assertEqual(stored["failed_step"], "post_ledger")
		self.assertTrue(stored["error"])
		self.assertTrue(json.loads(run.safe_recovery_actions))


class TestPersistNotApplicableIsSideEffectFree(unittest.TestCase):
	def test_no_partial_state_field_is_ever_written(self):
		"""(c) + (d): the clean-rejection path writes ONLY output_payload.

		``FakeRun.assigned`` makes this an assertion about writes, not about values: an
		empty-but-present ``committed_writes = "[]"`` would fail this test, which is the
		point -- a retry path must be able to tell "nothing ran" from "a run happened and
		touched nothing".
		"""
		outcome, invoker = _not_applicable_outcome()
		self.assertEqual(invoker.calls, [])  # zero side effects at the only side-effecting seam

		run = FakeRun()
		result = build_fallback(
			procedure_id=run.procedure_id,
			version=run.pinned_fingerprint,
			run=run.name,
			graph=_failing_write_graph(applies_when=['input["overdue"]']),
			outcome=outcome,
			classify_tool=fake_classifier,
		)
		payload = persist_fallback_state(run, result)

		self.assertEqual(result.fallback_class, PROCEDURE_NOT_APPLICABLE)
		self.assertEqual(payload["status"], PROCEDURE_NOT_APPLICABLE)
		for field in (*_PARTIAL_STATE_FIELDS, "error"):
			self.assertNotIn(field, run.assigned, f"{field} must not be written on NOT_APPLICABLE")
			self.assertNotIn(field, payload, f"{field} must be absent from the NOT_APPLICABLE payload")
		self.assertEqual(run.assigned, {"output_payload"})
		# Actionable: the caller can branch on status and knows it may simply proceed.
		self.assertEqual(json.loads(run.output_payload)["status"], PROCEDURE_NOT_APPLICABLE)


# ---------------------------------------------------------------------------
# invoke_bound_procedure -- fallback_enabled, and I9 ("the agent must not break").
# ---------------------------------------------------------------------------


class FakeLogger:
	def __init__(self):
		self.messages: list[str] = []

	def warning(self, msg):
		self.messages.append(msg)

	def debug(self, msg):
		self.messages.append(msg)


class FakeFrappe:
	"""Explicit stand-in for the ``frappe`` module as procedure_binding uses it."""

	def __init__(self):
		self._logger = FakeLogger()

	def get_doc(self, spec):
		return FakeRun()

	def get_cached_doc(self, doctype, name):
		return object()

	def logger(self, _name):
		return self._logger

	def get_traceback(self):
		return "<traceback>"


def _bound(fallback_enabled: bool) -> BoundProcedure:
	return BoundProcedure(
		binding_name="APB-0001",
		agent="AGENT-1",
		procedure="PROC-1",
		procedure_id="collections",
		procedure_name="Collections",
		input_schema={"type": "object", "properties": {}},
		fallback_enabled=fallback_enabled,
	)


class _BindingTestCase(unittest.TestCase):
	def use_frappe(self, double):
		patcher = patch.object(procedure_binding, "frappe", double)
		patcher.start()
		self.addCleanup(patcher.stop)

	def use_runner(self, fn):
		patcher = patch.object(procedure_runtime, "run_agent_procedure_run", fn)
		patcher.start()
		self.addCleanup(patcher.stop)


class TestInvokeBoundProcedureFallbackEnabled(_BindingTestCase):
	def test_failure_returns_structured_payload_and_never_raises(self):
		outcome = _failed_outcome()
		outcome.fallback = build_fallback(
			procedure_id="collections",
			version="fp1",
			run="APR-0001",
			graph=_failing_write_graph(),
			outcome=outcome,
			classify_tool=fake_classifier,
		).payload

		self.use_frappe(FakeFrappe())
		self.use_runner(lambda run_name, agent_doc=None: outcome)

		result = invoke_bound_procedure(_bound(True), {"customer": "C-1"})

		# (d) actionable: a dict with a well-defined branch key, not a raised exception.
		self.assertIsInstance(result, dict)
		self.assertIs(result["ok"], False)
		self.assertEqual(result["status"], ProcedureOutcome.FAILED)
		self.assertEqual(result["fallback"]["status"], PROCEDURE_FAILED_MID_RUN)
		self.assertTrue(result["fallback"]["safe_recovery_actions"])
		self.assertTrue(result["fallback"]["available_atomic_tools"])

	def test_not_applicable_payload_is_the_clean_shape(self):
		outcome, _invoker = _not_applicable_outcome()
		outcome.fallback = build_fallback(
			procedure_id="collections",
			version="fp1",
			run="APR-0001",
			graph=_failing_write_graph(applies_when=['input["overdue"]']),
			outcome=outcome,
			classify_tool=fake_classifier,
		).payload

		self.use_frappe(FakeFrappe())
		self.use_runner(lambda run_name, agent_doc=None: outcome)

		result = invoke_bound_procedure(_bound(True), {})

		self.assertIs(result["ok"], False)
		self.assertEqual(result["status"], ProcedureOutcome.NOT_APPLICABLE)
		self.assertEqual(result["fallback"]["status"], PROCEDURE_NOT_APPLICABLE)
		for field in _PARTIAL_STATE_FIELDS:
			self.assertNotIn(field, result["fallback"])


class TestInvokeBoundProcedureFallbackDisabled(_BindingTestCase):
	def test_failure_is_a_plain_catchable_result_not_an_exception(self):
		outcome = _failed_outcome()
		outcome.fallback = {"status": PROCEDURE_FAILED_MID_RUN, "completed_steps": []}

		self.use_frappe(FakeFrappe())
		self.use_runner(lambda run_name, agent_doc=None: outcome)

		result = invoke_bound_procedure(_bound(False), {})

		self.assertIsInstance(result, dict)
		self.assertIs(result["ok"], False)
		self.assertEqual(result["status"], ProcedureOutcome.FAILED)
		self.assertIsNone(result["fallback"])  # withheld, not "not built"
		self.assertTrue(result["error"])  # plain, catchable error text
		self.assertEqual(result["run"], "APR-0001")


class TestInvokeBoundProcedureNeverBreaksTheAgent(_BindingTestCase):
	"""I9: whatever explodes inside the procedure, the caller gets a value, not a raise."""

	def _boom(self, run_name, agent_doc=None):
		raise RuntimeError("run lock is held by another worker")

	def test_runner_exception_becomes_a_result_under_both_settings(self):
		for enabled in (True, False):
			with self.subTest(fallback_enabled=enabled):
				self.use_frappe(FakeFrappe())
				self.use_runner(self._boom)

				result = invoke_bound_procedure(_bound(enabled), {})

				self.assertIsInstance(result, dict)
				self.assertIs(result["ok"], False)
				self.assertEqual(result["status"], "error")
				self.assertIn("run lock", result["error"])
				self.assertIsNone(result["fallback"])
				self.assertEqual(result["run"], "APR-0001")

	def test_run_insert_failure_also_becomes_a_result(self):
		class ExplodingFrappe(FakeFrappe):
			def get_doc(self, spec):
				raise RuntimeError("Agent Procedure Run could not be inserted")

		self.use_frappe(ExplodingFrappe())
		self.use_runner(lambda run_name, agent_doc=None: _failed_outcome())

		result = invoke_bound_procedure(_bound(True), {})

		self.assertIs(result["ok"], False)
		self.assertEqual(result["status"], "error")
		self.assertIsNone(result["run"])
		self.assertIn("could not be inserted", result["error"])

	def test_success_is_still_reported_as_ok(self):
		self.use_frappe(FakeFrappe())
		self.use_runner(
			lambda run_name, agent_doc=None: ProcedureOutcome(
				status=ProcedureOutcome.SUCCESS, output={"total": 3}
			)
		)

		result = invoke_bound_procedure(_bound(True), {})

		self.assertIs(result["ok"], True)
		self.assertEqual(result["output"], {"total": 3})
		self.assertIsNone(result["fallback"])


if __name__ == "__main__":
	unittest.main()
