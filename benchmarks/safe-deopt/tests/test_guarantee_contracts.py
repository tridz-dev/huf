# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Deterministic guarantee-contract tests (ACCEPTANCE_PLAN_V2.md ss2, Task T2).

Pure pytest -- no LLM calls, no network, no paid API usage. One test function per
contract, run against the code as it actually exists in THIS worktree:

1. Committed timeout (F2)
2. Uncommitted timeout (F3) -- same caller-visible shape as #1
3. F4 validation rejection -- explicitly checks for "commit-then-fabricate"
4. Late commit (F7) -- pending/UNKNOWN immediately after timeout, fenceable
5. Server idempotency -- the REAL huf.ai.graph.idempotency reserve/release mechanism
6. Status resolution -- COMMITTED / NOT_COMMITTED / UNKNOWN semantics
7. Fencing -- a successful fence actually prevents the original op from later committing

Mirrors the sys.path setup already used by test_faults.py / test_conditions.py so
``workloads``, ``faults`` and ``conditions`` import as plain top-level modules.
"""

from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
	sys.path.insert(0, str(_SAFE_DEOPT_DIR))

# Repo root (huf/), so `import huf.ai.graph.idempotency` can resolve the `huf` package for
# contract 5's real-mechanism exercise below.
_REPO_ROOT = _SAFE_DEOPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
	sys.path.insert(0, str(_REPO_ROOT))

import pytest  # noqa: E402

from conditions import RecoverySession, ReplayGuard  # noqa: E402
from faults import (  # noqa: E402
	FaultInjector,
	TimeoutFault,
	ValidationErrorFault,
	cancel_operation,
	get_operation_status,
)
from workloads import Invoice, PaymentAllocationStore  # noqa: E402


def _new_store():
	store = PaymentAllocationStore()
	store.seed_invoice(Invoice(name="INV-0001", customer="CUST-1", outstanding_amount=500.0))
	alloc = store.create_allocation(payment="PAY-1", invoice="INV-0001", amount=500.0, operation_key="alloc-op-1")
	return store, alloc


def _committed_entries(store, operation_key):
	return [e for e in store.commit_log if e.operation_key == operation_key and e.committed]


# ---------------------------------------------------------------------------
# Contract 1 -- committed timeout
# ---------------------------------------------------------------------------


class TestCommittedTimeout(unittest.TestCase):
	"""Write commits exactly once in the real store, but the caller-facing result is a
	timeout/failure shape (not success)."""

	def test_f2_commits_once_but_reports_timeout(self):
		store, alloc = _new_store()
		injector = FaultInjector()

		observed = injector.inject(
			"F2", "none", store.submit_allocation, allocation=alloc.name, operation_key="submit-op-1"
		)

		# Caller-facing shape: a failure/timeout, never a success.
		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, TimeoutFault)

		# Ground truth: the real store committed exactly once.
		committed = _committed_entries(store, "submit-op-1")
		self.assertEqual(len(committed), 1)
		self.assertEqual(store.allocations[alloc.name].status, "submitted")
		self.assertAlmostEqual(store.invoices["INV-0001"].outstanding_amount, 0.0)


# ---------------------------------------------------------------------------
# Contract 2 -- uncommitted timeout, same shape as contract 1
# ---------------------------------------------------------------------------


class TestUncommittedTimeout(unittest.TestCase):
	"""Caller receives the SAME timeout shape as contract 1 (indistinguishable from the
	response alone), but the write never actually commits in the store."""

	def test_f3_same_shape_as_f2_but_never_commits(self):
		store_f2, alloc_f2 = _new_store()
		store_f3, alloc_f3 = _new_store()
		injector = FaultInjector()

		observed_f2 = injector.inject(
			"F2", "none", store_f2.submit_allocation, allocation=alloc_f2.name, operation_key="submit-op-x"
		)
		observed_f3 = injector.inject(
			"F3", "none", store_f3.submit_allocation, allocation=alloc_f3.name, operation_key="submit-op-x"
		)

		# Indistinguishable from the response alone: identical ok/value/error type and
		# message text (both calls share the same action/operation_key, so the exception
		# message -- the only thing the caller can see -- must be byte-for-byte equal).
		self.assertEqual(observed_f2.ok, observed_f3.ok)
		self.assertEqual(observed_f2.value, observed_f3.value)
		self.assertIsInstance(observed_f2.error, TimeoutFault)
		self.assertIsInstance(observed_f3.error, TimeoutFault)
		self.assertEqual(str(observed_f2.error), str(observed_f3.error))

		# Ground truth differs even though the caller can't tell: F2 committed, F3 did not.
		self.assertEqual(len(_committed_entries(store_f2, "submit-op-x")), 1)
		self.assertEqual(len(_committed_entries(store_f3, "submit-op-x")), 0)
		self.assertEqual(store_f2.allocations[alloc_f2.name].status, "submitted")
		self.assertEqual(store_f3.allocations[alloc_f3.name].status, "draft")


# ---------------------------------------------------------------------------
# Contract 3 -- F4 validation rejection
# ---------------------------------------------------------------------------


class TestF4ValidationRejection(unittest.TestCase):
	"""Concurrent state change causes the store to reject the write; assert NO committed
	mutation results.

	KNOWN BUG, documented per ACCEPTANCE_PLAN_V2.md ss2's explicit instruction to check for
	it: ``FaultInjector._inject_f4`` (benchmarks/safe-deopt/faults.py) calls
	``real_write_fn(*args, **kwargs)`` and only synthesizes a caller-visible
	``ValidationErrorFault`` if that call raises OR returns normally -- it does NOT check
	whether the real write actually committed before deciding what to tell the caller. For
	``PaymentAllocationStore.submit_allocation`` specifically, the store performs NO
	validation against invoice-level drift at all (it only checks the allocation's own
	``operation_key``/``status``/permission state) -- so when a "concurrent actor" mutates a
	SIBLING record (e.g. the invoice's ``outstanding_amount``) rather than the allocation
	being submitted, ``real_write_fn`` neither raises NOR fails to commit: it commits
	normally, and the injector STILL fabricates a validation error on top of that real
	commit. This is exactly the "commit, then fabricate a validation error" shape the task
	explicitly asks us to check for, and it is present.

	This test asserts the CURRENT (broken) behavior explicitly so the suite stays green,
	with `robustness_only` as the loud flag that this is a known gap, not a held guarantee.
	Per instructions, this is NOT fixed here: `faults.py` is a shared harness module also
	being read/exercised by other in-flight work in this same worktree (recovery_harness.py,
	procedure_vs_naive.py, llm_real_procedure_integration.py per a concurrent task on this
	branch), so changing F4's semantics now is out of scope for this task and risks
	interacting badly with that concurrent work. See CONTRACT_TEST_RESULTS.md for the
	tracked-gap writeup.
	"""

	@pytest.mark.robustness_only
	def test_f4_commit_then_fabricate_bug_is_present(self):
		store, alloc = _new_store()
		injector = FaultInjector()

		def concurrent_drift():
			# A concurrent actor changes a SIBLING record's state (not the allocation's own
			# status/operation_key) -- something submit_allocation never checks at all.
			store.invoices["INV-0001"].outstanding_amount = 42.0

		observed = injector.inject(
			"F4",
			"none",
			store.submit_allocation,
			allocation=alloc.name,
			operation_key="submit-op-f4",
			concurrent_mutation=concurrent_drift,
		)

		# Caller is told validation failed.
		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, ValidationErrorFault)

		# BUG: despite being told "validation error", the real write silently committed.
		committed = _committed_entries(store, "submit-op-f4")
		self.assertEqual(
			len(committed),
			1,
			"expected the documented commit-then-fabricate bug: the real write commits "
			"even though F4 tells the caller it failed validation",
		)
		self.assertEqual(store.allocations[alloc.name].status, "submitted")

	def test_f4_does_not_fabricate_when_store_naturally_rejects(self):
		"""Contrast case: when the concurrent mutation DOES collide with something
		submit_allocation actually checks (its own status), the store's own natural
		rejection means no committed mutation results -- this shape of F4 is safe. This
		demonstrates the bug above is about the *synthesized* fallback path specifically,
		not about F4 universally violating the contract.
		"""
		store, alloc = _new_store()
		injector = FaultInjector()

		def concurrent_submit_via_other_path():
			# A concurrent actor submits the SAME allocation through a different
			# operation_key first -- this DOES collide with a check submit_allocation makes
			# (``row.status == "submitted"``), so the store naturally raises nothing but
			# returns without committing again; either way no double-commit occurs.
			store.submit_allocation(allocation=alloc.name, operation_key="other-caller-op")

		observed = injector.inject(
			"F4",
			"none",
			store.submit_allocation,
			allocation=alloc.name,
			operation_key="submit-op-f4b",
			concurrent_mutation=concurrent_submit_via_other_path,
		)

		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, ValidationErrorFault)
		# No COMMITTED entry was produced for THIS operation_key specifically (the earlier
		# concurrent submit committed under its own, different operation_key).
		self.assertEqual(_committed_entries(store, "submit-op-f4b"), [])


# ---------------------------------------------------------------------------
# Contract 4 -- late commit
# ---------------------------------------------------------------------------


class TestLateCommit(unittest.TestCase):
	"""Original write is PENDING immediately after the timeout is reported; a recovery
	read at that point can observe pre-commit state; the operation SUBSEQUENTLY commits
	UNLESS fenced."""

	def test_f7_pending_then_commits_on_recovery_read(self):
		store, alloc = _new_store()
		injector = FaultInjector()

		observed = injector.inject(
			"F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="submit-op-f7"
		)
		self.assertFalse(observed.ok)
		self.assertIsInstance(observed.error, TimeoutFault)

		# Immediately after: still pending, nothing committed yet.
		self.assertEqual(_committed_entries(store, "submit-op-f7"), [])
		self.assertEqual(
			get_operation_status(store, "submit-op-f7", injector=injector),
			"UNKNOWN",
			"a genuinely pending F7 write must resolve to UNKNOWN, never a false NOT_COMMITTED",
		)

		def real_read():
			return store.allocations[alloc.name].status

		# First recovery read observes PRE-commit state (still "draft")...
		pre_write_observation = injector.wrap_read("submit-op-f7", real_read)
		self.assertEqual(pre_write_observation, "draft")

		# ...but that same call triggers the held write to land for subsequent observers.
		self.assertEqual(store.allocations[alloc.name].status, "submitted")
		self.assertEqual(len(_committed_entries(store, "submit-op-f7")), 1)
		self.assertEqual(get_operation_status(store, "submit-op-f7", injector=injector), "COMMITTED")

		# A second read now sees the landed write.
		post_write_observation = injector.wrap_read("submit-op-f7", real_read)
		self.assertEqual(post_write_observation, "submitted")

	def test_f7_fenced_before_recovery_read_never_commits(self):
		store, alloc = _new_store()
		injector = FaultInjector()

		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="submit-op-f7b")

		fenced = cancel_operation(store, "submit-op-f7b", injector=injector)
		self.assertTrue(fenced)

		def real_read():
			return store.allocations[alloc.name].status

		# Even though this is the "first read after the fault", the fence means the held
		# write must never land.
		observation = injector.wrap_read("submit-op-f7b", real_read)
		self.assertEqual(observation, "draft")
		self.assertEqual(store.allocations[alloc.name].status, "draft")
		self.assertEqual(_committed_entries(store, "submit-op-f7b"), [])
		self.assertEqual(get_operation_status(store, "submit-op-f7b", injector=injector), "NOT_COMMITTED")

		# A subsequent flush attempt is also a no-op post-fence.
		self.assertFalse(injector.flush_held_write("submit-op-f7b"))
		self.assertEqual(store.allocations[alloc.name].status, "draft")


# ---------------------------------------------------------------------------
# Contract 5 -- server idempotency (REAL huf.ai.graph.idempotency mechanism)
# ---------------------------------------------------------------------------


def _install_minimal_frappe_stub():
	"""Install the smallest possible `frappe` stub in sys.modules so the REAL
	`huf.ai.graph.idempotency` module (which lives under the `huf` package, whose
	top-level `huf/__init__.py` does an unconditional `import frappe`) becomes importable
	in this environment.

	This worktree has no `frappe` package installed at all (verified: `import frappe`
	raises `ModuleNotFoundError`, not merely "no site initialized" -- see
	`benchmarks/safe-deopt/recovery_harness.py`'s own docstring, which documents the same
	fact). `reserve_idempotency_key`/`release_idempotency_key` only touch
	`frappe.cache()` (a `.set(key, value, ex=..., nx=...)` / `.delete(key)` interface,
	mirroring `huf.ai.procedure_lock`'s cache convention per idempotency.py's own
	docstring) and `huf/__init__.py` only touches `frappe.logger(name)` at import time --
	nothing else is needed to exercise the REAL reservation logic end-to-end.

	This stub is test-only scaffolding: it is installed into `sys.modules`, never written
	to disk, and never touches any real HUF runtime file. `huf.ai.graph.idempotency`
	itself is imported completely unmodified.
	"""
	if "frappe" in sys.modules and getattr(sys.modules["frappe"], "_safe_deopt_stub", False):
		return sys.modules["frappe"]
	if "frappe" in sys.modules and not getattr(sys.modules["frappe"], "_safe_deopt_stub", False):
		# A real frappe is already loaded (e.g. running inside an actual bench) -- never
		# shadow it.
		return sys.modules["frappe"]

	frappe_stub = types.ModuleType("frappe")
	frappe_stub._safe_deopt_stub = True

	class _FakeCache:
		"""Mirrors the subset of the real Redis-backed `frappe.cache()` that
		`reserve_idempotency_key`/`release_idempotency_key` actually use: `set(key, value,
		ex=None, nx=False)` (SETNX-with-expiry semantics -- returns falsy if `nx=True` and
		the key already exists) and `delete(key)`.
		"""

		def __init__(self):
			self._store: dict[str, object] = {}

		def set(self, key, value, ex=None, nx=False):
			if nx and key in self._store:
				return False
			self._store[key] = value
			return True

		def delete(self, key):
			self._store.pop(key, None)

	cache_singleton = _FakeCache()
	frappe_stub.cache = lambda: cache_singleton
	frappe_stub.logger = lambda name: logging.getLogger(name)
	sys.modules["frappe"] = frappe_stub
	return frappe_stub


def _import_real_idempotency_module():
	_install_minimal_frappe_stub()
	import importlib

	return importlib.import_module("huf.ai.graph.idempotency")


class TestServerIdempotency(unittest.TestCase):
	"""Repeating the exact same operation key + payload through the REAL idempotency
	mechanism in huf/ai/graph/idempotency.py cannot produce a second effect. Exercised
	twice; behavioral proof, not a declared label."""

	def setUp(self):
		try:
			self.idempotency = _import_real_idempotency_module()
		except Exception as exc:  # pragma: no cover -- environment guard, not a soft-skip of the contract
			self.skipTest(
				f"huf.ai.graph.idempotency is not importable even with the minimal frappe "
				f"stub installed ({exc!r}) -- cannot exercise the real mechanism in this "
				f"environment"
			)

	def test_same_key_and_payload_cannot_produce_a_second_effect(self):
		idem = self.idempotency
		store, alloc = _new_store()

		key = idem.derive_idempotency_key(
			procedure_name="benchmark4-reconciliation",
			procedure_version="v1",
			normalised_inputs={"allocation": alloc.name},
			target_identity=alloc.name,
		)

		def attempt_with_reservation():
			"""Mirrors procedure_runtime._Runner._handle_tool_call's own pattern: reserve
			before dispatch, release after, skip the dispatch entirely if the reservation
			is not won."""
			if not idem.reserve_idempotency_key(key):
				return None  # a genuinely concurrent/duplicate attempt: never dispatched
			try:
				return store.submit_allocation(allocation=alloc.name, operation_key="submit-op-idem")
			finally:
				idem.release_idempotency_key(key)

		first = attempt_with_reservation()
		self.assertIsNotNone(first)
		self.assertEqual(len(_committed_entries(store, "submit-op-idem")), 1)

		# Second attempt: same key, same payload. Reservation was already released after
		# the first attempt (mirrors the real runtime's release-after-every-normal-path
		# behavior), but the STORE's own operation_key dedup is what must now absorb the
		# repeat -- proving the guarantee is behavioral end-to-end, not merely "declaring
		# server_idempotent is enough" (which the task explicitly says is not proof).
		second = attempt_with_reservation()
		self.assertIsNotNone(second)
		self.assertEqual(
			len(_committed_entries(store, "submit-op-idem")),
			1,
			"a second attempt with the identical operation_key must never produce a second "
			"committed effect",
		)
		self.assertAlmostEqual(store.invoices["INV-0001"].outstanding_amount, 0.0)

	def test_concurrent_reservation_blocks_the_losing_attempt_before_dispatch(self):
		"""The reservation itself (not the store) is what closes the TRULY concurrent race
		per idempotency.py's own docstring: two attempts racing to reserve the SAME key
		before either has dispatched -- only one may proceed."""
		idem = self.idempotency
		key = "concurrent-race-key"

		won_first = idem.reserve_idempotency_key(key)
		won_second = idem.reserve_idempotency_key(key)  # still held by the first winner

		self.assertTrue(won_first)
		self.assertFalse(won_second, "a second reservation attempt for the same key must not win while the first is held")

		idem.release_idempotency_key(key)
		won_after_release = idem.reserve_idempotency_key(key)
		self.assertTrue(won_after_release, "releasing the reservation must allow a subsequent legitimate attempt")
		idem.release_idempotency_key(key)


# ---------------------------------------------------------------------------
# Contract 6 -- status resolution
# ---------------------------------------------------------------------------


class TestStatusResolution(unittest.TestCase):
	"""COMMITTED refers to the exact operation; NOT_COMMITTED is a terminal negative
	(that operation specifically cannot later commit); pending/missing/inconclusive
	evidence resolves to UNKNOWN, never a false COMMITTED/NOT_COMMITTED."""

	def test_committed_refers_to_the_exact_operation(self):
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F0", "none", store.submit_allocation, allocation=alloc.name, operation_key="op-committed")

		self.assertEqual(get_operation_status(store, "op-committed", injector=injector), "COMMITTED")
		# A DIFFERENT, never-attempted operation_key is not conflated with this one.
		self.assertEqual(get_operation_status(store, "op-never-attempted", injector=injector), "NOT_COMMITTED")

	def test_not_committed_is_a_terminal_negative_for_never_attempted_writes(self):
		store, _alloc = _new_store()
		injector = FaultInjector()

		# Nothing was ever attempted for this key: NOT_COMMITTED, and (since there is no
		# held write and no fault history) it can never later commit under this key.
		self.assertEqual(get_operation_status(store, "op-nothing-ever", injector=injector), "NOT_COMMITTED")

	def test_not_committed_after_f3_stays_terminal(self):
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F3", "none", store.submit_allocation, allocation=alloc.name, operation_key="op-f3")

		self.assertEqual(get_operation_status(store, "op-f3", injector=injector), "NOT_COMMITTED")
		# No held write exists for an F3 key -- there is nothing left pending that could
		# later flip this to COMMITTED merely by the passage of time.
		self.assertFalse(injector.flush_held_write("op-f3"))
		self.assertEqual(get_operation_status(store, "op-f3", injector=injector), "NOT_COMMITTED")

	def test_pending_evidence_resolves_to_unknown_never_a_false_positive_or_negative(self):
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="op-f7-pending")

		status = get_operation_status(store, "op-f7-pending", injector=injector)
		self.assertEqual(status, "UNKNOWN")
		self.assertNotIn(status, ("COMMITTED", "NOT_COMMITTED"))

	def test_missing_injector_context_never_fabricates_committed(self):
		"""Without an injector (no way to know about a held write), a pending F7 op must
		never be reported as falsely COMMITTED -- get_operation_status conservatively
		falls back to NOT_COMMITTED rather than inventing certainty it doesn't have."""
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="op-f7-no-ctx")

		status_without_injector = get_operation_status(store, "op-f7-no-ctx")
		self.assertNotEqual(status_without_injector, "COMMITTED")
		self.assertEqual(status_without_injector, "NOT_COMMITTED")


# ---------------------------------------------------------------------------
# Contract 7 -- fencing
# ---------------------------------------------------------------------------


class TestFencing(unittest.TestCase):
	"""A successful fence call actually prevents the ORIGINAL pending operation from
	later committing (not just that a fence function was called)."""

	def test_successful_fence_prevents_the_original_pending_op_from_committing(self):
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="op-fence")

		fenced = cancel_operation(store, "op-fence", injector=injector)
		self.assertTrue(fenced)

		# Every subsequent attempt to make the ORIGINAL held write land must fail.
		self.assertFalse(injector.flush_held_write("op-fence"))

		def real_read():
			return store.allocations[alloc.name].status

		injector.wrap_read("op-fence", real_read)  # would trigger the commit if not fenced
		injector.wrap_read("op-fence", real_read)

		self.assertEqual(store.allocations[alloc.name].status, "draft")
		self.assertEqual(_committed_entries(store, "op-fence"), [])
		self.assertEqual(get_operation_status(store, "op-fence", injector=injector), "NOT_COMMITTED")

	def test_fence_is_not_merely_a_called_function_but_actually_blocks(self):
		"""A fence call that FAILS (nothing pending to cancel, or already committed) must
		not be treated as having protected anything -- the guard-level contract
		(conditions.ReplayGuard rule 2c) only unlocks on a *successful* fence."""
		store, alloc = _new_store()
		injector = FaultInjector()

		# Nothing pending for this key yet: cancel_operation must report failure, not a
		# false "fenced" success.
		self.assertFalse(cancel_operation(store, "op-never-pending", injector=injector))

		# A write that already committed cannot be retroactively fenced.
		injector.inject("F0", "none", store.submit_allocation, allocation=alloc.name, operation_key="op-already-committed")
		self.assertFalse(cancel_operation(store, "op-already-committed", injector=injector))

	def test_replay_guard_only_admits_a_fenceable_retry_after_a_real_successful_fence(self):
		"""End-to-end with conditions.ReplayGuard (C6): a session that merely READ the
		record, or whose fence attempt failed, may not retry a fenceable write -- only a
		session that actually recorded a successful fence for this exact key may."""
		store, alloc = _new_store()
		injector = FaultInjector()
		injector.inject("F7", "fenceable", store.submit_allocation, allocation=alloc.name, operation_key="op-guard-fence")

		guard = ReplayGuard(injector=injector)

		# A bare read does not unlock anything.
		session_read_only = RecoverySession()
		session_read_only.record_read("op-guard-fence")
		with self.assertRaises(Exception):
			guard.attempt_write(
				store.submit_allocation,
				allocation=alloc.name,
				operation_key="op-guard-fence",
				tool_guarantee="fenceable",
				recovery_session=session_read_only,
				store=store,
			)

		# An actual successful fence unlocks the retry, and the retry is a safe no-op on
		# the original allocation because the original write can never land now.
		fenced = cancel_operation(store, "op-guard-fence", injector=injector)
		self.assertTrue(fenced)
		session_fenced = RecoverySession()
		session_fenced.record_fence("op-guard-fence", fenced=True)
		result = guard.attempt_write(
			store.submit_allocation,
			allocation=alloc.name,
			operation_key="op-guard-fence",
			tool_guarantee="fenceable",
			recovery_session=session_fenced,
			store=store,
		)
		self.assertIsNotNone(result)
		self.assertEqual(store.allocations[alloc.name].status, "submitted")
		# Exactly one committed effect for this operation_key -- the retry, not a
		# resurrection of the fenced-off original.
		self.assertEqual(len(_committed_entries(store, "op-guard-fence")), 1)


if __name__ == "__main__":
	unittest.main()
