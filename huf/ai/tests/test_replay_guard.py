# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.graph.replay_guard (SafeDeoptCommittedGuardWiring, Stage 2).

Pure pytest -- no frappe, no bench. Adapted from the research prototype's
``benchmarks/safe-deopt/tests/test_conditions.py`` (``TestReplayGuard``), ported from its
raise-based ``ReplayRejected`` API to this module's ``GuardDecision``-returning API. Every
(``tool_guarantee`` x outcome-state) branch from the prototype's 18-case coverage is
represented here, adapted to the narrower (no ground-truth-oracle) v1 shape described in
the PLAN.md section 2 v1 scope note: COMMITTED is only ever knowable via
``recovery_session.status_resolved``, never via a ``store``/``get_operation_status`` side
channel (this module has no such parameter at all).
"""

from __future__ import annotations

import unittest

from huf.ai.graph.replay_guard import GUARANTEE_LEVELS, GuardDecision, RecoverySession, ReplayGuard


class TestGuardDecision(unittest.TestCase):
	def test_allowed_decision_reports_reservation_not_still_held(self):
		decision = GuardDecision(allowed=True, reason="ok", still_reserved=False)
		self.assertTrue(decision.allowed)
		self.assertFalse(decision.still_reserved)

	def test_rejected_decision_reports_reservation_still_held(self):
		decision = GuardDecision(allowed=False, reason="no", still_reserved=True)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_inconsistent_decision_is_rejected_by_the_dataclass_invariant(self):
		"""Risk item 6's fix surface: still_reserved must always be the negation of
		allowed. A caller cannot silently construct a decision that lies about it.
		"""
		with self.assertRaises(ValueError):
			GuardDecision(allowed=True, reason="bug", still_reserved=True)
		with self.assertRaises(ValueError):
			GuardDecision(allowed=False, reason="bug", still_reserved=False)


class TestReplayGuardCheck(unittest.TestCase):
	def setUp(self):
		self.guard = ReplayGuard()

	# -- unknown tool_guarantee is a programming error, not an admission outcome --------

	def test_unknown_tool_guarantee_raises_value_error(self):
		session = RecoverySession()
		with self.assertRaises(ValueError):
			self.guard.check(operation_key="k0", tool_guarantee="bogus", recovery_session=session)

	def test_guarantee_levels_are_the_four_declared_strings(self):
		self.assertEqual(GUARANTEE_LEVELS, ("server_idempotent", "status_resolvable", "fenceable", "none"))

	# -- COMMITTED, any guarantee -> rejected unless server_idempotent ------------------

	def test_committed_plus_none_is_rejected(self):
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		decision = self.guard.check(operation_key="k1", tool_guarantee="none", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_committed_plus_status_resolvable_is_rejected(self):
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		decision = self.guard.check(
			operation_key="k1", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_committed_plus_fenceable_is_rejected(self):
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		# Even a successfully-fenced key must still be rejected once COMMITTED is resolved
		# and the tool is not server_idempotent -- rule 1 takes precedence over rule 2c.
		session.record_fence("k1", fenced=True)
		decision = self.guard.check(operation_key="k1", tool_guarantee="fenceable", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_committed_plus_server_idempotent_is_allowed_as_safe_noop(self):
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		decision = self.guard.check(
			operation_key="k1", tool_guarantee="server_idempotent", recovery_session=session
		)
		self.assertTrue(decision.allowed)
		self.assertFalse(decision.still_reserved)

	# -- UNKNOWN outcome, none -> always rejected ---------------------------------------

	def test_unknown_plus_none_is_rejected(self):
		session = RecoverySession()
		decision = self.guard.check(operation_key="k2", tool_guarantee="none", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_unknown_plus_none_rejected_even_with_a_bare_read_recorded(self):
		"""Hard rule: a bare read is NOT sufficient to unlock a none/unresolved retry."""
		session = RecoverySession()
		session.record_read("k2")
		decision = self.guard.check(operation_key="k2", tool_guarantee="none", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	# -- UNKNOWN outcome, server_idempotent -> always allowed ---------------------------

	def test_unknown_plus_server_idempotent_is_allowed(self):
		session = RecoverySession()
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="server_idempotent", recovery_session=session
		)
		self.assertTrue(decision.allowed)
		self.assertFalse(decision.still_reserved)

	def test_unknown_plus_server_idempotent_allowed_even_with_no_session_state_at_all(self):
		"""No session state is required for server_idempotent -- it never depends on it."""
		session = RecoverySession()
		self.assertEqual(session.status_resolved, {})
		self.assertEqual(session.fenced, set())
		decision = self.guard.check(
			operation_key="unseen-key", tool_guarantee="server_idempotent", recovery_session=session
		)
		self.assertTrue(decision.allowed)

	# -- UNKNOWN outcome, status_resolvable ----------------------------------------------

	def test_unknown_plus_status_resolvable_resolved_not_committed_is_allowed(self):
		session = RecoverySession()
		session.record_status_check("k2", "NOT_COMMITTED")
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertTrue(decision.allowed)
		self.assertFalse(decision.still_reserved)

	def test_unknown_plus_status_resolvable_unresolved_is_rejected(self):
		"""Never actually recorded a status check for this key -- must reject."""
		session = RecoverySession()
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_unknown_plus_status_resolvable_recorded_for_a_different_key_is_rejected(self):
		"""Resolved status for a DIFFERENT operation_key must not leak into this decision."""
		session = RecoverySession()
		session.record_status_check("other-key", "NOT_COMMITTED")
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)

	def test_unknown_plus_status_resolvable_unknown_status_is_rejected(self):
		session = RecoverySession()
		session.record_status_check("k2", "UNKNOWN")
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_unknown_plus_status_resolvable_resolved_committed_is_rejected(self):
		"""This is really the COMMITTED case (rule 1), reached via status_resolvable."""
		session = RecoverySession()
		session.record_status_check("k1", "COMMITTED")
		decision = self.guard.check(
			operation_key="k1", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)

	# -- UNKNOWN outcome, fenceable -------------------------------------------------------

	def test_unknown_plus_fenceable_fenced_is_allowed(self):
		session = RecoverySession()
		session.record_fence("k2", fenced=True)
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertTrue(decision.allowed)
		self.assertFalse(decision.still_reserved)

	def test_unknown_plus_fenceable_not_fenced_is_rejected(self):
		session = RecoverySession()
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_fence_attempt_that_fails_does_not_unlock(self):
		session = RecoverySession()
		session.record_fence("k2", fenced=False)  # cancel/fence call returned False
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertFalse(decision.allowed)
		self.assertTrue(decision.still_reserved)

	def test_fenceable_fenced_for_a_different_key_is_rejected(self):
		session = RecoverySession()
		session.record_fence("other-key", fenced=True)
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertFalse(decision.allowed)

	def test_fence_recorded_false_after_a_true_does_not_remove_the_earlier_fence(self):
		"""record_fence(fenced=False) must never erase a previously-successful fence."""
		session = RecoverySession()
		session.record_fence("k2", fenced=True)
		session.record_fence("k2", fenced=False)
		self.assertIn("k2", session.fenced)
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertTrue(decision.allowed)

	# -- reads never unlock anything, for any guarantee level ----------------------------

	def test_bare_read_never_unlocks_status_resolvable(self):
		session = RecoverySession()
		session.record_read("k2")
		decision = self.guard.check(
			operation_key="k2", tool_guarantee="status_resolvable", recovery_session=session
		)
		self.assertFalse(decision.allowed)

	def test_bare_read_never_unlocks_fenceable(self):
		session = RecoverySession()
		session.record_read("k2")
		decision = self.guard.check(operation_key="k2", tool_guarantee="fenceable", recovery_session=session)
		self.assertFalse(decision.allowed)


if __name__ == "__main__":
	unittest.main()
