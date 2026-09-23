"""Spend accounting for decision calls (PLAN.md §4.7 step 8, D15).

Two entry points, both called from :mod:`huf.ai.decision.service`'s ``_execute_inline`` (the
shared core for Enforce, Advise, Manual and Shadow -- PLAN.md §4.7):

- :func:`precheck_spend` runs before the runtime evaluates the deployment chain (before any
  provider network call). An origin with an ``agent_run`` counts against that chain's
  :class:`~huf.ai.run_budget.RunBudget`; everything else (Flow Run, Automation, Playground,
  API) has no RunBudget today and always proceeds -- decision spend is still recorded on the
  run record for those origins, it just is not counted against a cap (PLAN.md §4.7 step 8:
  "counted against the cap only when the call happens inside an Agent chain").
- :func:`record_call` runs after every completed call (success or a billed failure) and
  atomically increments decision totals on the origin's Agent Run / Flow Run / Automation.

Both Enforce (same process as the caller) and Shadow (a separate ``frappe.enqueue`` worker,
T2A.11) go through the same code path, so every increment here uses
``UPDATE ... SET x = x + %s`` (``frappe.db.sql``) rather than a Python-side read-modify-write:
two Shadow jobs for the same Agent Run can complete in either order, or genuinely
concurrently, and a read-modify-write would silently drop one job's contribution.
"""

from __future__ import annotations

import frappe

from huf.ai.decision.types import DecisionOrigin, DecisionUsage
from huf.ai.run_budget import RunBudget, RunBudgetExceeded, get_current_budget

#: Decision calls are small classification/selection prompts (PLAN.md §3.6), not full agent
#: turns -- and the pre-check runs before ``load_chain`` resolves a deployment, so there is no
#: per-model price to look up yet. A conservative flat estimate is enough to catch a chain
#: that is already at or effectively at its cap without a pricing lookup on the hot path; the
#: real cost is recorded exactly by :func:`record_call` once the response comes back.
DEFAULT_CALL_COST_ESTIMATE_USD = 0.01


def precheck_spend(origin: DecisionOrigin) -> bool:
	"""Return ``True`` if a call for this origin may proceed, ``False`` if it would exceed
	the origin's Agent Run spend cap (``Agent Settings.spend_cap_usd``, D15).

	Only Agent Run chains have a :class:`~huf.ai.run_budget.RunBudget` today; an origin with
	no ``agent_run`` (Flow Run, Automation, Playground, API) always returns ``True``.
	"""
	if not origin.agent_run:
		return True
	budget = _resolve_budget(origin.agent_run)
	try:
		budget.check_spend(DEFAULT_CALL_COST_ESTIMATE_USD)
	except RunBudgetExceeded:
		return False
	return True


def _resolve_budget(agent_run: str) -> RunBudget:
	"""Rebuild the :class:`~huf.ai.run_budget.RunBudget` from the persisted Agent Run
	fields when possible -- the concurrency-safe source of truth, since :func:`record_call`
	increments ``budget_spend_usd`` atomically via SQL and a Shadow job runs in a separate
	worker process where the in-process budget contextvar was never set (see
	:func:`~huf.ai.run_budget.get_current_budget`'s own docstring: "does not cross process
	boundaries"). Falls back to the in-process cache if the Agent Run cannot be loaded (e.g.
	it was deleted concurrently). Mirrors the existing spend-cap check in
	``huf.ai.automation_runner._execute`` (ST-09.6), which resolves the same way.
	"""
	try:
		run_doc = frappe.get_doc("Agent Run", agent_run)
		return RunBudget.from_run_doc(run_doc)
	except Exception:
		return get_current_budget()


def record_call(
	*,
	origin: DecisionOrigin,
	usage: DecisionUsage,
	cost: float,
	decision_call: str | None = None,
) -> None:
	"""Atomically record usage/cost totals for one completed decision call against its
	origin (PLAN.md §4.7 step 8, D15). Called for every completed call -- Enforce, Manual or
	Shadow, success or a billed failure; ``usage``/``cost`` are zero-valued for a call that
	never reached a provider (e.g. a timeout before any request went out), so the increments
	below are harmless no-ops for those beyond the call count.

	Playground and API calls (``origin.agent_run``, ``origin.flow_run`` and
	``origin.automation`` all unset) touch only the ``Decision Call`` row the runtime already
	persisted; there is nothing to increment here for them.
	"""
	input_tokens = int(usage.input_tokens or 0)
	output_tokens = int(usage.output_tokens or 0)
	cost = float(cost or 0.0)

	if origin.agent_run:
		_increment(
			"Agent Run",
			origin.agent_run,
			{
				"decision_call_count": 1,
				"decision_input_tokens": input_tokens,
				"decision_output_tokens": output_tokens,
				"decision_cost": cost,
				"budget_spend_usd": cost,
			},
		)
		# Keep the in-process RunBudget (if this call is running inside the same process as
		# the chain that started it -- true for the Enforce/Advise/Manual inline path, not
		# for a Shadow job in a different worker) in sync so a later check_spend() in this
		# same call stack sees this call's cost without re-reading the Agent Run.
		budget = get_current_budget()
		if budget is not None:
			budget.spend_so_far_usd += cost

	if origin.flow_run:
		_increment(
			"Flow Run",
			origin.flow_run,
			{
				"decision_call_count": 1,
				"decision_input_tokens": input_tokens,
				"decision_output_tokens": output_tokens,
				"decision_cost": cost,
			},
		)

	if origin.automation:
		_increment(
			"Automation",
			origin.automation,
			{"total_decision_calls": 1, "total_decision_cost": cost},
		)
		if decision_call:
			# Idempotent with huf.ai.automation_runner._update_automation_bookkeeping's own
			# last_decision_call write (T6.02) -- last write wins, and setting the same
			# value twice is harmless.
			frappe.db.set_value(
				"Automation", origin.automation, "last_decision_call", decision_call, update_modified=False
			)


def _increment(doctype: str, name: str, deltas: dict[str, float]) -> None:
	"""Atomically add each delta in ``deltas`` to the named document's fields.

	Uses ``UPDATE ... SET x = COALESCE(x, 0) + %s`` (``frappe.db.sql``) rather than
	``frappe.get_doc(...).save()`` or a Python-side read-modify-write, so concurrent writers
	(two Shadow jobs completing for the same run at once) each land their own contribution
	instead of one overwriting the other. Zero deltas are skipped; if every delta is zero
	(no tokens, no cost) nothing is written.
	"""
	if not name:
		return
	set_clauses = []
	params: list[float] = []
	for fieldname, delta in deltas.items():
		if not delta:
			continue
		set_clauses.append(f"`{fieldname}` = COALESCE(`{fieldname}`, 0) + %s")
		params.append(delta)
	if not set_clauses:
		return
	params.append(name)
	frappe.db.sql(
		f"UPDATE `tab{doctype}` SET {', '.join(set_clauses)} WHERE `name` = %s",
		params,
	)
