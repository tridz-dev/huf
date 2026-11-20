# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Standalone replay-guard admission logic (Stage 2 of SafeDeoptCommittedGuardWiring).

This module is frappe-free by design -- it is the pure decision core the runtime's write
retry path (``procedure_runtime.py``'s ``RECOVERY_RETRY`` branch) will consult in a later
stage, but nothing in this module is imported or referenced by the runtime yet. Stage 2 is
standalone on purpose: it ports and adapts the admission rule already built and
18-test-verified in the research prototype at
``benchmarks/safe-deopt/conditions.py``'s ``ReplayGuard.attempt_write`` (see the
SafeDeoptCommittedGuardWiring PLAN.md, section 2, for the full rationale and the mapping
table from the prototype's shapes to the runtime's real ones).

Key adaptation from the prototype: the runtime's own failure model never lets an exception
escape ``_handle_tool_call`` for an ordinary node failure (``procedure_runtime.py``'s
``_default_route`` docstring is explicit that only ``RoutingError``/
``ProcedureLimitExceeded`` are allowed to propagate). The prototype's ``ReplayGuard``
raises ``ReplayRejected`` to refuse a retry; this module's :meth:`ReplayGuard.check`
instead RETURNS a :class:`GuardDecision` -- never raises for an ordinary admission
rejection -- so a future caller can turn ``not decision.allowed`` into "skip the retry,
keep the original failed invocation" without any new exception-handling machinery.

Second adaptation, driven by the plan's risk items 6 and 7 (found in the Opus-low review
gate, both required fixes before Stage 3 wiring):

- **Risk 6 (idempotency-reservation release-on-rejection)**: today, ``_handle_tool_call``
  releases its dedup reservation (``release_idempotency_key``) unconditionally on every
  path, including a guard-rejected retry -- which would let a later, separate attempt at
  the SAME ``operation_key`` freely re-invoke with no memory of this run's rejection. The
  fix decided in the plan is that a guard rejection must NOT release the reservation, so a
  same-key retry from any later attempt still hits the reservation's own protection until
  the dedup window expires. ``GuardDecision`` carries ``still_reserved: bool`` so Stage 3's
  caller knows, straight from the decision object, whether to skip the release call --
  without having to duplicate this module's admission logic at the call site to re-derive
  it. A decision that rejects a retry always has ``still_reserved=True``; a decision that
  allows a retry always has ``still_reserved=False`` (the retry proceeds and the ordinary
  release-after-attempt behaviour applies, exactly as it does today for an ungated retry).
- **Risk 7 (pre-guard dedup duplicate-success bypass)**: the existing ``if not reserved:``
  branch in ``procedure_runtime.py`` returns a duplicate-success outcome before any tool
  invocation and before the guard is ever consulted, for ANY declared guarantee including
  ``none``. This module does not attempt to close that gap itself -- it is a decision about
  a different code path (the reservation check, not the retry gate) that the plan defers to
  Stage 3 with an explicit, reviewed decision one way or the other (see plan section 7, risk
  7). This module's job is only to make sure ITS OWN decision object carries enough
  information (``still_reserved``) for whichever choice Stage 3 makes about that separate
  branch to be implemented without re-deriving guard state.
"""

from __future__ import annotations

import dataclasses

__all__ = [
	"GUARANTEE_LEVELS",
	"GuardDecision",
	"RecoverySession",
	"ReplayGuard",
]


# The four declared recovery-guarantee levels a tool may carry (mirrors
# ``Agent Tool Function.recovery_guarantee``'s Select options, Stage 1). Re-declared here,
# not imported from the benchmark -- the benchmark's ``faults.py`` must never become a
# runtime dependency (plan section 5, Stage 2).
GUARANTEE_LEVELS = ("server_idempotent", "status_resolvable", "fenceable", "none")


@dataclasses.dataclass(frozen=True)
class GuardDecision:
	"""The result of a single :meth:`ReplayGuard.check` admission decision.

	Never raised -- always returned, per this module's frappe-free/no-exceptions design
	(see module docstring). ``allowed`` says whether the retry may proceed; ``reason`` is a
	human-readable explanation suitable for an audit field or a fallback-payload hint.

	``still_reserved`` is the plan's risk-item-6 fix surface: it tells the caller whether
	the underlying idempotency reservation for this ``operation_key`` should be treated as
    STILL held after this decision, i.e. whether the caller must SKIP its normal
	release-the-reservation step. It is always the logical negation of ``allowed`` --
	spelled out as its own field (rather than left for the caller to infer from ``allowed``)
	so Stage 3's wiring reads as "do what the decision says," not "re-derive guard
	semantics at the call site."
	"""

	allowed: bool
	reason: str
	still_reserved: bool

	def __post_init__(self) -> None:
		# Invariant, not just a convention: a rejected decision must always report the
		# reservation as still held, and an allowed decision must always report it as no
		# longer needing special handling (the ordinary post-attempt release path applies).
		# Enforced here so a future edit to this module cannot silently desynchronize the
		# two fields.
		expected = not self.allowed
		if self.still_reserved != expected:
			raise ValueError(
				f"GuardDecision inconsistent: allowed={self.allowed!r} requires "
				f"still_reserved={expected!r}, got {self.still_reserved!r}"
			)


def _decision(*, allowed: bool, reason: str) -> GuardDecision:
	return GuardDecision(allowed=allowed, reason=reason, still_reserved=not allowed)


@dataclasses.dataclass
class RecoverySession:
	"""Mutable bookkeeping for what a SINGLE recovery session has actually done so far.

	Ported near-verbatim from ``conditions.py``'s ``RecoverySession`` (same three fields,
	same recording helpers, same session-scoped-not-store-scoped-or-global design intent).

	Fields
	------
	- ``reads_done``: operation_keys this session has performed *some* read against.
	  Recorded for audit/observability only -- see :class:`ReplayGuard`'s docstring for why
	  this field, by itself, NEVER unlocks anything.
	- ``status_resolved``: operation_key -> the definitive ``"COMMITTED"``/
	  ``"NOT_COMMITTED"`` outcome this session obtained by actually recording a status
	  check for that key. A key absent from this dict, or present only because of an
	  ``"UNKNOWN"`` result, does not count as resolved.
	- ``fenced``: operation_keys this session has fenced off via a successfully recorded
	  cancel/fence operation before attempting the retry.
	"""

	reads_done: set[str] = dataclasses.field(default_factory=set)
	status_resolved: dict[str, str] = dataclasses.field(default_factory=dict)
	fenced: set[str] = dataclasses.field(default_factory=set)

	def record_read(self, operation_key: str) -> None:
		self.reads_done.add(operation_key)

	def record_status_check(self, operation_key: str, status: str) -> None:
		"""Record the result of an ACTUAL status-check call. Only "COMMITTED" and
		"NOT_COMMITTED" are meaningful resolutions; "UNKNOWN" is recorded too (so a caller
		can see it was checked) but never satisfies the guard's resolved-NOT_COMMITTED
		rule.
		"""
		self.status_resolved[operation_key] = status

	def record_fence(self, operation_key: str, *, fenced: bool) -> None:
		"""Record the result of an ACTUAL fence/cancel call. Only a successful fence
		(``fenced=True``) adds the key to ``self.fenced``; a failed/no-op cancel attempt
		does NOT unlock anything, and any previously recorded fence is not removed by a
		later failed attempt.
		"""
		if fenced:
			self.fenced.add(operation_key)


class ReplayGuard:
	"""The guard that decides whether a retry of a write may proceed at all.

	Adapted from ``conditions.py``'s ``ReplayGuard.attempt_write`` (see module docstring for
	the exception-vs-decision adaptation). This class does not itself invoke any write --
	it is a pure admission check; the caller is responsible for actually retrying (or not)
	based on the returned :class:`GuardDecision`.

	THE ADMISSION RULE (ported from the prototype, narrowed per the v1 scope note below)
	-------------------------------------------------------------------------------------
	1. A resolved-COMMITTED outcome (``recovery_session.status_resolved[operation_key] ==
	   "COMMITTED"``) is allowed to retry ONLY when the tool is ``server_idempotent`` (the
	   store's own dedup absorbs the redundant call safely); for any other guarantee level
	   a resolved-COMMITTED outcome REJECTS the retry outright -- there is nothing left to
	   accomplish and no idempotent protection if it is somehow called again.

	   v1 scope note (plan section 2): unlike the prototype, this module has NO ground-truth
	   status oracle (no ``store``/``get_operation_status`` side channel) -- COMMITTED is
	   only ever knowable via ``recovery_session.status_resolved``, exactly like
	   NOT_COMMITTED. This is a strictly narrower, still-safe subset of the prototype's rule:
	   dropping the free oracle lookup only makes this guard MORE conservative (it rejects a
	   retry the prototype might allow, never the reverse).

	2. Otherwise (outcome not resolved COMMITTED) a retry is allowed ONLY when one of:
	   a. ``tool_guarantee == "server_idempotent"``: always allowed, unconditionally -- the
	      store's own operation_key-based dedup makes a retry safe regardless of session
	      state.
	   b. ``tool_guarantee == "status_resolvable"`` AND
	      ``recovery_session.status_resolved.get(operation_key) == "NOT_COMMITTED"``: the
	      session must have ACTUALLY recorded a definitive NOT_COMMITTED status check for
	      this exact key -- not "UNKNOWN", not "a read happened", not "resolved for some
	      other key".
	   c. ``tool_guarantee == "fenceable"`` AND ``operation_key in recovery_session.fenced``:
	      the session must have ACTUALLY recorded a successful fence for this exact key
	      before the retry.

	   Otherwise (including ``tool_guarantee == "none"``, and including
	   ``status_resolvable``/``fenceable`` tools whose guarantee-specific check was never
	   actually exercised by this session) the guard REJECTS unconditionally.

	3. A bare "a read happened" (``recovery_session.reads_done``) NEVER by itself unlocks a
	   retry of an unresolved-outcome write, for ANY guarantee level, including ``none``.
	   Only an actual resolved-guarantee use (2a/2b/2c above) does.

	4. ``tool_guarantee == "none"``: the retry is REJECTED unconditionally for any outcome
	   that is not resolved COMMITTED -- there is no guarantee-specific escape hatch to
	   exercise for ``none``.
	"""

	def check(
		self,
		*,
		operation_key: str,
		tool_guarantee: str,
		recovery_session: RecoverySession,
	) -> GuardDecision:
		"""Decide whether a retry for ``operation_key`` may proceed.

		Never raises for an ordinary admission outcome -- always returns a
		:class:`GuardDecision`. Raises :class:`ValueError` only for a caller bug (an
		unknown ``tool_guarantee`` string outside :data:`GUARANTEE_LEVELS`), which is a
		programming error, not a runtime admission outcome.
		"""
		if tool_guarantee not in GUARANTEE_LEVELS:
			raise ValueError(f"unknown tool_guarantee {tool_guarantee!r}, expected one of {GUARANTEE_LEVELS}")

		resolved_status = recovery_session.status_resolved.get(operation_key)
		ground_truth_committed = resolved_status == "COMMITTED"

		# -- rule 1: known-COMMITTED -----------------------------------------------------
		if ground_truth_committed:
			if tool_guarantee == "server_idempotent":
				return _decision(
					allowed=True,
					reason="operation_key resolved COMMITTED but tool is server_idempotent; "
					"retry is a safe no-op via the store's own dedup",
				)
			return _decision(
				allowed=False,
				reason="operation_key is already known COMMITTED and the tool is not "
				"server_idempotent; no further retry is needed or permitted",
			)

		# -- rule 4: no guarantee at all --------------------------------------------------
		if tool_guarantee == "none":
			return _decision(
				allowed=False,
				reason="tool declares no recovery guarantee; an unresolved-outcome write may "
				"never be retried -- only reads, compensating actions, or escalation are "
				"permitted",
			)

		# -- rule 2a: server_idempotent ----------------------------------------------------
		if tool_guarantee == "server_idempotent":
			return _decision(
				allowed=True,
				reason="tool is server_idempotent; retry is always safe via the store's own dedup",
			)

		# -- rule 2b: status_resolvable, actually resolved NOT_COMMITTED -------------------
		if tool_guarantee == "status_resolvable":
			if resolved_status == "NOT_COMMITTED":
				return _decision(
					allowed=True,
					reason="operation_key resolved NOT_COMMITTED for this session; retry is safe",
				)
			return _decision(
				allowed=False,
				reason="the recovery session has not actually resolved this operation_key's "
				"status to NOT_COMMITTED; a bare read does not count",
			)

		# -- rule 2c: fenceable, actually fenced --------------------------------------------
		if tool_guarantee == "fenceable":
			if operation_key in recovery_session.fenced:
				return _decision(
					allowed=True,
					reason="operation_key has been successfully fenced for this session; retry is safe",
				)
			return _decision(
				allowed=False,
				reason="the recovery session has not successfully fenced this operation_key "
				"before attempting the retry",
			)

		# Unreachable: every GUARANTEE_LEVELS value is handled above.
		raise AssertionError(f"unhandled tool_guarantee {tool_guarantee!r}")
