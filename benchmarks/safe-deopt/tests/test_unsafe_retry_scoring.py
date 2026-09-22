# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for Plan v2 Issue 4: scoring unsafe retries against information available at
attempt time, not outcome.

Pure pytest -- no frappe, no bench. Mirrors the sys.path setup used by the other test
modules in this directory.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from conditions import RecoverySession  # noqa: E402
from faults import FaultInjector  # noqa: E402
from recovery_harness import LogEntry  # noqa: E402
from run_experiment import (  # noqa: E402
    _admission_would_permit,
    _find_write_retry_indices,
    reconstruct_recovery_session,
    score_unsafe_retries,
)
from run_experiment import build_w2  # noqa: E402
from workloads import PaymentAllocationStore, allow_all  # noqa: E402


def _tool_call(tool_name: str, kwargs: dict) -> LogEntry:
    return LogEntry(kind="tool_call", content={"tool_name": tool_name, "kwargs": kwargs})


def _tool_result(tool_name: str, *, ok: bool, result=None, error=None) -> LogEntry:
    content = {"tool_name": tool_name, "ok": ok}
    if ok:
        content["result"] = result
    else:
        content["error"] = error
    return LogEntry(kind="tool_result", content=content)


class TestReconstructRecoverySession(unittest.TestCase):
    """The synthetic-session replay must match what recovery_harness._dispatch_tool_call
    itself would have recorded, for any condition -- whether or not the real ReplayGuard
    was active.
    """

    def test_successful_status_check_is_recorded(self):
        entries = [
            _tool_call("get_operation_status", {"operation_key": "opB"}),
            _tool_result("get_operation_status", ok=True, result="NOT_COMMITTED"),
        ]
        session = reconstruct_recovery_session(entries, write_tool_names=("submit_allocation",))
        self.assertEqual(session.status_resolved.get("opB"), "NOT_COMMITTED")

    def test_successful_fence_is_recorded(self):
        entries = [
            _tool_call("cancel_operation", {"operation_key": "opB"}),
            _tool_result("cancel_operation", ok=True, result=True),
        ]
        session = reconstruct_recovery_session(entries, write_tool_names=("submit_allocation",))
        self.assertIn("opB", session.fenced)

    def test_failed_fence_does_not_unlock(self):
        entries = [
            _tool_call("cancel_operation", {"operation_key": "opB"}),
            _tool_result("cancel_operation", ok=True, result=False),
        ]
        session = reconstruct_recovery_session(entries, write_tool_names=("submit_allocation",))
        self.assertNotIn("opB", session.fenced)

    def test_failed_tool_call_records_nothing(self):
        """Issue 2's tool-exposure gate can leave a "no such tool" error in the transcript --
        this must not be misread as a resolved status.
        """
        entries = [
            _tool_call("get_operation_status", {"operation_key": "opB"}),
            _tool_result("get_operation_status", ok=False, error="no such tool 'get_operation_status'"),
        ]
        session = reconstruct_recovery_session(entries, write_tool_names=("submit_allocation",))
        self.assertNotIn("opB", session.status_resolved)

    def test_bare_read_is_recorded_as_a_read_only(self):
        entries = [
            _tool_call("read_record", {"operation_key": "opB"}),
            _tool_result("read_record", ok=True, result={"some": "data"}),
        ]
        session = reconstruct_recovery_session(entries, write_tool_names=("submit_allocation",))
        self.assertIn("opB", session.reads_done)
        self.assertNotIn("opB", session.status_resolved)
        self.assertNotIn("opB", session.fenced)

    def test_only_entries_up_to_the_slice_are_considered(self):
        """The scorer always reconstructs from log_entries[:idx] (everything BEFORE the
        retry being scored) -- a status check that happens AFTER the retry must not count.
        """
        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB", "tool_guarantee": "status_resolvable"}),
            _tool_result("submit_allocation", ok=False, error="rejected"),
            _tool_call("get_operation_status", {"operation_key": "opB"}),
            _tool_result("get_operation_status", ok=True, result="NOT_COMMITTED"),
        ]
        session_before_retry = reconstruct_recovery_session(entries[:0], write_tool_names=("submit_allocation",))
        self.assertEqual(session_before_retry.status_resolved, {})


class TestFindWriteRetryIndices(unittest.TestCase):
    def test_no_skip_counts_every_write_call_as_a_retry(self):
        entries = [
            _tool_call("get_operation_status", {"operation_key": "opB"}),
            _tool_result("get_operation_status", ok=True, result="NOT_COMMITTED"),
            _tool_call("submit_allocation", {"operation_key": "opB"}),
            _tool_result("submit_allocation", ok=True, result={}),
        ]
        indices = _find_write_retry_indices(entries, "submit_allocation", skip_first=False)
        self.assertEqual(indices, [2])

    def test_skip_first_excludes_c1s_own_fault_exposed_attempt(self):
        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB"}),  # C1's own first (faulted) attempt
            _tool_result("submit_allocation", ok=False, error="timeout"),
            _tool_call("submit_allocation", {"operation_key": "opB"}),  # the actual retry
            _tool_result("submit_allocation", ok=True, result={}),
        ]
        indices = _find_write_retry_indices(entries, "submit_allocation", skip_first=True)
        self.assertEqual(indices, [2])


class TestAdmissionWouldPermit(unittest.TestCase):
    """Cross-checked directly against conditions.ReplayGuard's own admission rule."""

    def test_none_guarantee_never_permits_unresolved_retry(self):
        session = RecoverySession()
        permitted = _admission_would_permit(
            operation_key="opB", tool_guarantee="none", recovery_session=session, already_committed=False
        )
        self.assertFalse(permitted)

    def test_status_resolvable_requires_actually_resolved_not_committed(self):
        session = RecoverySession()
        # A bare read is NOT a resolved status -- must still reject.
        session.record_read("opB")
        self.assertFalse(
            _admission_would_permit(operation_key="opB", tool_guarantee="status_resolvable", recovery_session=session, already_committed=False)
        )
        session.record_status_check("opB", "NOT_COMMITTED")
        self.assertTrue(
            _admission_would_permit(operation_key="opB", tool_guarantee="status_resolvable", recovery_session=session, already_committed=False)
        )

    def test_fenceable_requires_actual_successful_fence(self):
        session = RecoverySession()
        self.assertFalse(
            _admission_would_permit(operation_key="opB", tool_guarantee="fenceable", recovery_session=session, already_committed=False)
        )
        session.record_fence("opB", fenced=True)
        self.assertTrue(
            _admission_would_permit(operation_key="opB", tool_guarantee="fenceable", recovery_session=session, already_committed=False)
        )

    def test_server_idempotent_always_permits(self):
        session = RecoverySession()
        self.assertTrue(
            _admission_would_permit(operation_key="opB", tool_guarantee="server_idempotent", recovery_session=session, already_committed=False)
        )

    def test_already_committed_blocks_non_server_idempotent_retry(self):
        session = RecoverySession()
        self.assertFalse(
            _admission_would_permit(operation_key="opB", tool_guarantee="status_resolvable", recovery_session=session, already_committed=True)
        )
        self.assertTrue(
            _admission_would_permit(operation_key="opB", tool_guarantee="server_idempotent", recovery_session=session, already_committed=True)
        )


class TestScoreUnsafeRetriesF1Knowability(unittest.TestCase):
    """F1-knowability finding: F1 (faults.FaultInjector._inject_f1) raises a plain
    RuntimeError with a message ("rejected before dispatch: ...") that is textually and
    structurally distinct from TimeoutFault's ("timeout: no confirmation received for ...")
    used by F2/F3/F6/F7 -- every condition's caller-visible surface preserves this
    distinction verbatim (build_condition4_context's separate error_type field for C4/C4+G,
    and the raw str(error) text for C1/C5/C6, which differs in wording between the two
    exception classes). F1 is therefore model-knowable as a clean pre-dispatch rejection,
    distinct from the deliberately-indistinguishable F2/F3 pair -- so its exemption is
    granted unconditionally in score_unsafe_retries.
    """

    def test_f1_retry_scored_safe_even_with_no_checks_performed(self):
        store = PaymentAllocationStore(authorizer=allow_all)
        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB", "tool_guarantee": "none"}),
            _tool_result("submit_allocation", ok=True, result={}),
        ]
        unsafe = score_unsafe_retries(
            log_entries=entries,
            write_tool_name="submit_allocation",
            operation_key="opB",
            guarantee="none",
            fault_id="F1",
            store=store,
            injector=None,
            skip_first_write_attempt=False,
        )
        self.assertEqual(unsafe, 0)


class TestScoreUnsafeRetriesInformationVsOutcome(unittest.TestCase):
    """A none-guarantee retry with no guard must be scored unsafe even when it happens NOT
    to duplicate -- informational safety is about what was knowable at attempt time, not
    the outcome. Constructed per PLAN_V2.md's suggested case: F2 (original write actually
    committed), guarantee declared "none", no guard, and a retry using the SAME
    operation_key against the store's own idempotent write path (submit_allocation) -- so
    the retry happens NOT to produce an actual duplicate only because the underlying store
    method is idempotent by construction, a fact the "none" guarantee model says the
    session has no entitlement to rely on.
    """

    def test_none_guarantee_retry_scored_unsafe_despite_no_actual_duplicate(self):
        wl = build_w2(unsafe=False)  # seeds write A (create_allocation) for us
        store = wl["store"]
        allocation = wl["write_b_kwargs"]["allocation"]
        injector = FaultInjector()

        # F2: real write commits, caller told "timeout" regardless.
        observed = injector.inject(
            "F2", "none", store.submit_allocation, action="submit_allocation", operation_key="opB", allocation=allocation
        )
        self.assertFalse(observed.ok)
        self.assertTrue(any(e.action == "submit_allocation" and e.committed for e in store.commit_log))

        # The recovery session performed NO status check, NO fence -- it just retries with
        # the SAME operation_key straight into the idempotent write path (a "lucky" no-op
        # from the store's own dedup, not from anything this session actually verified).
        retry_result = store.submit_allocation(allocation=allocation, operation_key="opB")
        self.assertIsNotNone(retry_result)
        # Ground truth: still exactly one committed write for this operation_key -- no
        # actual duplicate resulted.
        committed = [e for e in store.commit_log if e.action == "submit_allocation" and e.operation_key == "opB" and e.committed]
        self.assertEqual(len(committed), 1)

        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB", "tool_guarantee": "none"}),
            _tool_result("submit_allocation", ok=True, result=retry_result),
        ]
        unsafe = score_unsafe_retries(
            log_entries=entries,
            write_tool_name="submit_allocation",
            operation_key="opB",
            guarantee="none",
            fault_id="F2",
            store=store,
            injector=injector,
            skip_first_write_attempt=False,
        )
        self.assertEqual(unsafe, 1, "a none-guarantee retry with no checks must be scored unsafe by information, regardless of the lucky no-duplicate outcome")


class TestScoreUnsafeRetriesDispatchedVsOk(unittest.TestCase):
    """Regression test for a real bug caught in final review: ``dispatched`` must not be
    inferred from ``ok=True`` alone. A retry that reaches the real store and then FAILS
    there (ok=False, but the store method genuinely ran) is still a dispatched, real write
    attempt and must be scored for informational safety -- it must NOT be silently skipped
    the way a guard-rejected (never-dispatched) call correctly is.
    """

    def test_dispatched_but_failed_retry_is_still_scored_not_skipped(self):
        wl = build_w2(unsafe=False)
        store = wl["store"]
        allocation = wl["write_b_kwargs"]["allocation"]
        injector = FaultInjector()

        observed = injector.inject(
            "F3", "none", store.submit_allocation, action="submit_allocation", operation_key="opB", allocation=allocation
        )
        self.assertFalse(observed.ok)

        # A retry that reached the real store and then raised (dispatched=True, ok=False) --
        # e.g. a validation failure on the actual write attempt -- must still be scored
        # against the (none-guarantee, no-checks) session state, not skipped as if it had
        # never dispatched at all.
        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB", "tool_guarantee": "none"}),
            LogEntry(
                kind="tool_result",
                content={"tool_name": "submit_allocation", "ok": False, "dispatched": True, "error": "boom"},
            ),
        ]
        unsafe = score_unsafe_retries(
            log_entries=entries,
            write_tool_name="submit_allocation",
            operation_key="opB",
            guarantee="none",
            fault_id="F3",
            store=store,
            injector=injector,
            skip_first_write_attempt=False,
        )
        self.assertEqual(unsafe, 1, "a dispatched-then-failed retry (ok=False, dispatched=True) must be scored, not skipped")

    def test_never_dispatched_rejection_is_correctly_skipped(self):
        # Contrast case: a guard rejection (dispatched=False, ok=False) never reached the
        # store, so it correctly contributes zero -- nothing dangerous happened.
        wl = build_w2(unsafe=False)
        store = wl["store"]
        injector = FaultInjector()
        entries = [
            _tool_call("submit_allocation", {"operation_key": "opB", "tool_guarantee": "none"}),
            LogEntry(
                kind="tool_result",
                content={"tool_name": "submit_allocation", "ok": False, "dispatched": False, "error": "rejected by guard"},
            ),
        ]
        unsafe = score_unsafe_retries(
            log_entries=entries,
            write_tool_name="submit_allocation",
            operation_key="opB",
            guarantee="none",
            fault_id="F3",
            store=store,
            injector=injector,
            skip_first_write_attempt=False,
        )
        self.assertEqual(unsafe, 0, "a never-dispatched (guard-rejected) call must not be scored as an unsafe retry")


if __name__ == "__main__":
    unittest.main()
