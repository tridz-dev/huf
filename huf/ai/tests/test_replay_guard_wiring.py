# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""SafeDeoptCommittedGuardWiring, stage 3: wiring the opt-in replay guard into
``_Runner._handle_tool_call``'s ``RECOVERY_RETRY`` branch.

Frappe-free, standalone (mirrors ``test_benchmark3_write_runtime.py``'s harness): a
hand-rolled fake ``frappe`` module stands in for ``huf.ai.graph.idempotency``'s
``frappe.cache()`` calls, and a minimal single-write-node graph exercises the retry gate
directly rather than pulling in a whole benchmark fixture.

Coverage (see PLAN.md section 5, Stage 3.4 and the task's own required tests):

* flag-off (default) -> zero behaviour change, regardless of tool guarantee or session
  state -- the central safety property of the opt-in design (plan section 4/7).
* the guard's ``check()`` call site is reachable ONLY from inside the existing
  ``RECOVERY_RETRY`` branch, never from the first attempt (plan section 7, risk 5 --
  the single highest-severity risk called out in review).
* flag-on + a rejecting decision blocks the retry end-to-end through ``execute_procedure``
  and marks the outcome with ``guard_rejected`` (plan section 5.3).
* the idempotency reservation is held (not released) on a guard rejection, and released
  exactly as before on every other path -- success, non-guard failure, exhausted retry
  (plan section 7, risk 6).
* an undeclared tool defaults to the ``"none"`` guarantee once the flag is on (plan
  section 3).
"""

from __future__ import annotations

import copy
import sys
import unittest
from unittest.mock import MagicMock

from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.idempotency import derive_operation_key
from huf.ai.graph.procedure_runtime import (
	RECOVERY_ABORT,
	RECOVERY_RETRY,
	ProcedureOutcome,
	ToolInvocation,
	execute_procedure,
)
from huf.ai.graph.replay_guard import ReplayGuard

# ---------------------------------------------------------------------------
# Same hand-rolled Redis-like double as test_benchmark3_write_runtime.py, duplicated here
# (not imported) so this file stays independently runnable and does not depend on another
# test module's private helpers.
# ---------------------------------------------------------------------------


class _FakeCache:
	def __init__(self):
		self.store: dict[str, int] = {}

	def set(self, key, value, ex=None, nx=False):
		if nx and key in self.store:
			return False
		self.store[key] = value
		return True

	def delete(self, key):
		self.store.pop(key, None)


class _FakeFrappeModule:
	def __init__(self):
		self._cache = _FakeCache()

	def cache(self):
		return self._cache

	def logger(self, *_a, **_kw):
		return MagicMock()


_PREVIOUS_FRAPPE_MODULE = None


def _install_fake_frappe() -> _FakeFrappeModule:
	global _PREVIOUS_FRAPPE_MODULE
	_PREVIOUS_FRAPPE_MODULE = sys.modules.get("frappe")
	fake = _FakeFrappeModule()
	sys.modules["frappe"] = fake
	return fake


def _restore_real_stub() -> None:
	if _PREVIOUS_FRAPPE_MODULE is None:
		sys.modules.pop("frappe", None)
	else:
		sys.modules["frappe"] = _PREVIOUS_FRAPPE_MODULE


# ---------------------------------------------------------------------------
# Minimal single-write-node graph: write -> out. No foreach/parallel/conditions -- the
# retry gate itself is the thing under test, not the rest of the IR.
# ---------------------------------------------------------------------------

_PROCEDURE_NAME = "replay-guard-wiring-test"
_TOOL_ID = "the_write_tool"
_TARGET_IDENTITY = "TARGET-0001"
_OPERATION_KEY = derive_operation_key(procedure_name=_PROCEDURE_NAME, node_id="write", target_identity=_TARGET_IDENTITY)


def _contract(**limits) -> dict:
	defaults = dict(
		max_nodes=50,
		max_rows=1000,
		max_output_bytes=1_000_000,
		max_external_calls=100,
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


def _graph(*, recovery: str = RECOVERY_RETRY, contract_limits: dict | None = None) -> dict:
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "write",
		"contract": _contract(**(contract_limits or {})),
		"nodes": [
			{
				"id": "write",
				"type": "tool.call",
				"config": {
					"tool_id": _TOOL_ID,
					"recovery": recovery,
					"input": {
						"idempotency_key": "IK-0001",
						"operation_key": _OPERATION_KEY,
					},
				},
				"next": "out",
			},
			{"id": "out", "type": "output", "config": {"value": {"$from": "write"}}},
		],
	}


class _RecordingInvoker:
	"""Fake tool layer: fails the first N calls, then succeeds. Records every call."""

	def __init__(self, *, fail_count: int = 0):
		self.fail_count = fail_count
		self.calls: list[dict] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append(copy.deepcopy(args))
		call_number = len(self.calls)
		if call_number <= self.fail_count:
			return ToolInvocation(
				tool_id=tool_id, args=args, success=False, result=None, error="simulated in-doubt failure"
			)
		return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"written": True}, error=None)


class _AlwaysFailInvoker:
	def __init__(self):
		self.calls: list[dict] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append(copy.deepcopy(args))
		return ToolInvocation(tool_id=tool_id, args=args, success=False, result=None, error="always fails")


class _Perm:
	"""Duck-typed classify_tool result -- mirrors huf.ai.graph.permissions.ToolPermission's
	shape without importing that (frappe-backed) module, exactly like
	test_benchmark3_write_runtime.py's own ``_WriteClassifier`` fake.
	"""

	def __init__(self, ptype="create", recovery_guarantee=None):
		self.ptype = ptype
		self.recovery_guarantee = recovery_guarantee


class _Classifier:
	def __init__(self, recovery_guarantee=None):
		self._recovery_guarantee = recovery_guarantee

	def __call__(self, tool_id: str) -> _Perm:
		return _Perm(ptype="create", recovery_guarantee=self._recovery_guarantee)


class _UndeclaredClassifier:
	"""A classify_tool whose returned object has no ``recovery_guarantee`` attribute at
	all -- the "even more undeclared than an explicit None" shape, to prove
	``_recovery_guarantee`` degrades to "none" via getattr's default, not an AttributeError.
	"""

	class _BarePerm:
		def __init__(self):
			self.ptype = "create"

	def __call__(self, tool_id: str) -> "_UndeclaredClassifier._BarePerm":
		return self._BarePerm()


def _run(
	*,
	invoker,
	classify_tool,
	recovery: str = RECOVERY_RETRY,
	replay_guard_enabled: bool = False,
	contract_limits: dict | None = None,
	status_check_fn=None,
	fence_fn=None,
):
	graph = _graph(recovery=recovery, contract_limits=contract_limits)
	outcome = execute_procedure(
		PinnedVersion.pin(graph),
		{},
		tool_invoker=invoker,
		classify_tool=classify_tool,
		procedure_name=_PROCEDURE_NAME,
		replay_guard_enabled=replay_guard_enabled,
		status_check_fn=status_check_fn,
		fence_fn=fence_fn,
	)
	return outcome


class ReplayGuardFlagOffNoChangeTests(unittest.TestCase):
	"""Central safety property: with the flag off (the default), behaviour is byte-for-byte
	unchanged, regardless of the tool's declared recovery_guarantee or any session state.
	"""

	def setUp(self):
		_install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_default_no_kwarg_retry_heals_transient_failure_regardless_of_guarantee(self):
		# No replay_guard_enabled kwarg supplied at all -- proves the new parameter's own
		# default (False) preserves today's behaviour without a caller having to know it
		# exists.
		invoker = _RecordingInvoker(fail_count=1)
		graph = _graph(recovery=RECOVERY_RETRY)
		outcome = execute_procedure(
			PinnedVersion.pin(graph),
			{},
			tool_invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),  # worst-case guarantee
			procedure_name=_PROCEDURE_NAME,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)  # first attempt failed, retry succeeded

	def test_explicit_flag_false_retry_heals_even_for_undeclared_tool(self):
		invoker = _RecordingInvoker(fail_count=1)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee=None),
			replay_guard_enabled=False,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)

	def test_flag_off_exhausted_retry_still_releases_reservation(self):
		invoker = _AlwaysFailInvoker()
		outcome = _run(invoker=invoker, classify_tool=_Classifier(recovery_guarantee="none"), replay_guard_enabled=False)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 2)  # first attempt + one bounded retry, both failed
		entry = outcome.tool_invocations[0]
		self.assertNotIn("guard_rejected", entry)
		# Released -> a later attempt at the same key can reserve again.
		import frappe

		self.assertTrue(frappe.cache().set("agent_procedure_idempotency_IK-0001", 1, nx=True))


class ReplayGuardNeverGatesFirstAttemptTests(unittest.TestCase):
	"""Plan section 7, risk 5 (highest severity): the guard's check() call site must only
	ever be reached from inside the RECOVERY_RETRY branch, never from the first attempt --
	a bug that moved the flag check above the retry guard would block first-time writes
	entirely. Proven by patching ReplayGuard.check to raise if it is ever called, then
	confirming a first-time SUCCESSFUL write completes untouched with the flag on and the
	worst-case ("none") guarantee.
	"""

	def setUp(self):
		_install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_first_time_success_never_consults_the_guard(self):
		def _boom(self, **kwargs):
			raise AssertionError("ReplayGuard.check must never be called for a successful first attempt")

		original = ReplayGuard.check
		ReplayGuard.check = _boom
		self.addCleanup(setattr, ReplayGuard, "check", original)

		invoker = _RecordingInvoker(fail_count=0)  # succeeds immediately, no retry ever attempted
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			replay_guard_enabled=True,  # flag ON -- the guard is armed, but must not fire here
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 1)  # exactly one attempt, no retry

	def test_first_time_success_never_gated_regardless_of_recovery_mode(self):
		# Same property under RECOVERY_ABORT (no retry declared at all) -- belt and braces.
		def _boom(self, **kwargs):
			raise AssertionError("ReplayGuard.check must never be called when there is no retry to gate")

		original = ReplayGuard.check
		ReplayGuard.check = _boom
		self.addCleanup(setattr, ReplayGuard, "check", original)

		invoker = _RecordingInvoker(fail_count=0)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			recovery=RECOVERY_ABORT,
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 1)


class ReplayGuardRejectionEndToEndTests(unittest.TestCase):
	"""Flag on, a rejecting guard decision blocks the retry through execute_procedure."""

	def setUp(self):
		_install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_none_guarantee_blocks_retry_and_marks_guard_rejected(self):
		invoker = _RecordingInvoker(fail_count=2)  # would need 2 healed attempts; guard must stop it at 1
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		# Only the FIRST attempt happened -- the retry never fired.
		self.assertEqual(len(invoker.calls), 1)
		entry = outcome.tool_invocations[0]
		self.assertTrue(entry.get("guard_rejected"))
		self.assertTrue(entry.get("guard_rejection_reason"))

	def test_undeclared_tool_defaults_to_none_and_is_blocked(self):
		invoker = _RecordingInvoker(fail_count=2)
		outcome = _run(
			invoker=invoker,
			classify_tool=_UndeclaredClassifier(),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_server_idempotent_guarantee_always_allows_the_retry(self):
		invoker = _RecordingInvoker(fail_count=1)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="server_idempotent"),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)
		entry = outcome.tool_invocations[0]
		self.assertNotIn("guard_rejected", entry)


class ReplayGuardIdempotencyReleaseSkipTests(unittest.TestCase):
	"""Plan section 7, risk 6: release_idempotency_key must be skipped ONLY on a guard
	rejection, and must still fire exactly as today on every other path.
	"""

	def setUp(self):
		self.fake_frappe = _install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def _reserved(self) -> bool:
		"""True if the reservation for IK-0001 is currently held."""
		import frappe

		return not frappe.cache().set("agent_procedure_idempotency_IK-0001", 1, nx=True)

	def test_guard_rejection_holds_the_reservation(self):
		invoker = _RecordingInvoker(fail_count=2)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))
		# Reservation is STILL held -- a later, separate attempt at the same key must not
		# be free to re-invoke with no memory of this rejection.
		self.assertTrue(self._reserved())

	def test_success_path_still_releases(self):
		invoker = _RecordingInvoker(fail_count=1)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="server_idempotent"),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertFalse(self._reserved())

	def test_non_guard_failure_still_releases(self):
		# recovery == RECOVERY_ABORT -> no retry branch at all -> guard never consulted ->
		# ordinary failure path -> release runs exactly as before.
		invoker = _AlwaysFailInvoker()
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			recovery=RECOVERY_ABORT,
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertFalse(self._reserved())

	def test_exhausted_retry_with_flag_off_still_releases(self):
		invoker = _AlwaysFailInvoker()
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),
			replay_guard_enabled=False,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 2)
		self.assertFalse(self._reserved())

	def test_allowed_retry_that_still_fails_releases_normally(self):
		# Flag on, server_idempotent (always allowed) -- retry proceeds but also fails.
		# Not a guard rejection (decision.allowed was True), so release must still run.
		invoker = _AlwaysFailInvoker()
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="server_idempotent"),
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 2)
		self.assertNotIn("guard_rejected", outcome.tool_invocations[0])
		self.assertFalse(self._reserved())


class DedupDuplicateBypassUnaffectedTests(unittest.TestCase):
	"""Plan section 7, risk 7 decision: the pre-existing ``if not reserved:`` duplicate-
	success short-circuit is left unconsulted by the guard -- verify it still returns a
	duplicate success even when the flag is on and the tool is undeclared/"none", and that
	the tool is never actually invoked on that path (idempotency.py's own protection, not
	the guard's, is what is doing the work here).
	"""

	def setUp(self):
		_install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_concurrent_duplicate_bypasses_guard_entirely(self):
		import frappe

		# Simulate a truly concurrent second attempt: reserve the key before the run starts.
		frappe.cache().set("agent_procedure_idempotency_IK-0001", 1, nx=True)

		invoker = _RecordingInvoker(fail_count=0)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="none"),  # worst-case guarantee
			replay_guard_enabled=True,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 0)  # tool never invoked at all
		self.assertTrue(outcome.tool_invocations[0].get("duplicate"))
		self.assertNotIn("guard_rejected", outcome.tool_invocations[0])


class ReplayGuardStatusCheckAndFenceHookTests(unittest.TestCase):
	"""SafeDeoptCommittedGuardWiring, stage 4: the optional ``status_check_fn``/``fence_fn``
	hooks are what actually let a ``status_resolvable``/``fenceable`` tool's guarded retry
	be admitted -- see PLAN.md follow-up and ``_Runner._resolve_status_check``/
	``_resolve_fence``. Central properties:

	* a supplied hook that resolves the guard-unlocking outcome (NOT_COMMITTED / fenced)
	  admits the retry;
	* the same tool/hook resolving the guard-blocking outcome (COMMITTED / not fenced)
	  still rejects (or, for COMMITTED, is a guard-level no-op-not-needed rejection, which
	  is the guard's OWN documented rule, not a hook bug);
	* with no hook supplied at all (the default), both guarantee levels behave exactly like
	  ``none`` -- proving nothing broke for every existing caller.
	"""

	def setUp(self):
		_install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	# -- status_resolvable ---------------------------------------------------------------

	def test_status_resolvable_with_not_committed_hook_admits_retry(self):
		invoker = _RecordingInvoker(fail_count=1)
		calls: list[str] = []

		def status_check_fn(operation_key: str) -> str:
			calls.append(operation_key)
			return "NOT_COMMITTED"

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			status_check_fn=status_check_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)  # first attempt failed, retry admitted and succeeded
		self.assertEqual(calls, [_OPERATION_KEY])
		self.assertNotIn("guard_rejected", outcome.tool_invocations[0])

	def test_status_resolvable_with_committed_hook_rejects_retry(self):
		# COMMITTED + not server_idempotent -> guard's own rule 1: reject, nothing left to do.
		invoker = _RecordingInvoker(fail_count=2)

		def status_check_fn(operation_key: str) -> str:
			return "COMMITTED"

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			status_check_fn=status_check_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)  # retry never fired
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_status_resolvable_with_unknown_hook_still_rejects(self):
		invoker = _RecordingInvoker(fail_count=2)

		def status_check_fn(operation_key: str) -> str:
			return "UNKNOWN"

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			status_check_fn=status_check_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_status_resolvable_hook_raising_fails_closed(self):
		invoker = _RecordingInvoker(fail_count=2)

		def status_check_fn(operation_key: str) -> str:
			raise RuntimeError("boom")

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			status_check_fn=status_check_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	# -- fenceable ------------------------------------------------------------------------

	def test_fenceable_with_true_hook_admits_retry(self):
		invoker = _RecordingInvoker(fail_count=1)
		calls: list[str] = []

		def fence_fn(operation_key: str) -> bool:
			calls.append(operation_key)
			return True

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="fenceable"),
			replay_guard_enabled=True,
			fence_fn=fence_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)
		self.assertEqual(calls, [_OPERATION_KEY])
		self.assertNotIn("guard_rejected", outcome.tool_invocations[0])

	def test_fenceable_with_false_hook_rejects_retry(self):
		invoker = _RecordingInvoker(fail_count=2)

		def fence_fn(operation_key: str) -> bool:
			return False

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="fenceable"),
			replay_guard_enabled=True,
			fence_fn=fence_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_fenceable_hook_raising_fails_closed(self):
		invoker = _RecordingInvoker(fail_count=2)

		def fence_fn(operation_key: str) -> bool:
			raise RuntimeError("boom")

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="fenceable"),
			replay_guard_enabled=True,
			fence_fn=fence_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	# -- no hooks supplied: unchanged v1 fallback ------------------------------------------

	def test_status_resolvable_without_hook_still_behaves_like_none(self):
		invoker = _RecordingInvoker(fail_count=2)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			status_check_fn=None,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_fenceable_without_hook_still_behaves_like_none(self):
		invoker = _RecordingInvoker(fail_count=2)
		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="fenceable"),
			replay_guard_enabled=True,
			fence_fn=None,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertEqual(len(invoker.calls), 1)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_wrong_hook_for_guarantee_does_not_leak_across(self):
		# A fence_fn supplied for a status_resolvable tool must not be consulted -- only the
		# matching hook for the declared guarantee is ever invoked.
		invoker = _RecordingInvoker(fail_count=2)

		def fence_fn(operation_key: str) -> bool:
			raise AssertionError("fence_fn must never be called for a status_resolvable tool")

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=True,
			fence_fn=fence_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertTrue(outcome.tool_invocations[0].get("guard_rejected"))

	def test_hooks_supplied_but_flag_off_are_never_consulted(self):
		# replay_guard_enabled=False -> the whole gate (including the hooks) is skipped, and
		# the existing bounded retry heals the failure exactly as before this feature existed.
		invoker = _RecordingInvoker(fail_count=1)

		def status_check_fn(operation_key: str) -> str:
			raise AssertionError("status_check_fn must never be called with the flag off")

		def fence_fn(operation_key: str) -> bool:
			raise AssertionError("fence_fn must never be called with the flag off")

		outcome = _run(
			invoker=invoker,
			classify_tool=_Classifier(recovery_guarantee="status_resolvable"),
			replay_guard_enabled=False,
			status_check_fn=status_check_fn,
			fence_fn=fence_fn,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(invoker.calls), 2)


if __name__ == "__main__":
	unittest.main()
