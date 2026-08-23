# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Whitelisted API surface for the T-50 validation harness (``huf.ai.graph.validation_harness``).

The harness itself (``aggregate_runs`` / ``evaluate_promotion``) is pure and frappe-free: it
turns a caller-supplied ``NRunReport`` into a :class:`PromotionDecision`. Nothing in this repo
yet wires a live agentic-vs-deterministic N-run comparison for an arbitrary ``Agent Procedure``
-- that comparison only exists today against the four hand-built benchmark fixtures exercised
by this track's own tests (see ``huf/ai/tests/test_procedure_runtime.py`` and friends), each of
which needs a bespoke fake tool layer that has no generic, Procedure-name-driven equivalent.

So rather than fabricate a report (which the harness's own MEASUREMENT HONESTY principle
forbids -- see the ``validation_harness`` module docstring), this module does the honest thing
available today: it surfaces the Procedure's real ``Agent Procedure Run`` history as per-run
pass/fail, and it always calls :func:`huf.ai.graph.validation_harness.evaluate_promotion` with
``report=None`` -- which the harness itself fails closed on ("no N-run report supplied --
absence of evidence is not evidence of readiness (I10)"). That keeps the promotion decision
genuinely governed by the harness's own logic (not reimplemented here) while being truthful
that no live N-run comparison has been wired for this Procedure yet. When that wiring lands,
this function is the seam a future change plugs a real ``NRunReport`` into.
"""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.graph.validation_harness import (
	MIN_REPRESENTATIVE_RUNS,
	evaluate_promotion,
)

#: Statuses an ``Agent Procedure Run`` can settle into; anything else is still in flight.
_TERMINAL_STATUSES = ("Completed", "Failed", "Cancelled")


@frappe.whitelist()
def run_validation_harness(procedure_name: str, runs: int = MIN_REPRESENTATIVE_RUNS) -> dict:
	"""Run the T-50 promotion gate for one ``Agent Procedure`` and return its result.

	Args:
	    procedure_name: name (``Agent Procedure.name``) of the Procedure to evaluate.
	    runs: how many of the Procedure's most recent terminal ``Agent Procedure Run`` records
	        to surface as per-run pass/fail evidence. Defaults to the harness's own
	        ``MIN_REPRESENTATIVE_RUNS`` floor.

	Returns:
	    dict with:
	      - ``procedure_name``, ``is_read_only``, ``contains_writes``: the Procedure's own flags,
	        read straight off the doc (these drive the harness's write checklist gate).
	      - ``runs``: list of ``{run_name, status, passed, error, started_at, completed_at}``,
	        most-recent first, drawn from real ``Agent Procedure Run`` history.
	      - ``promotion``: ``{approved, reasons}`` from
	        :func:`huf.ai.graph.validation_harness.evaluate_promotion` -- always rejected today
	        (no live N-run report is wired yet), with the harness's own reasons surfaced verbatim.
	      - ``diagnostics``: human-readable notes on what this endpoint did and did not measure.
	"""
	if not frappe.has_permission("Agent Procedure", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	runs = int(runs) if runs else MIN_REPRESENTATIVE_RUNS

	procedure = frappe.get_doc("Agent Procedure", procedure_name)

	run_rows = frappe.get_all(
		"Agent Procedure Run",
		filters={"procedure": procedure.name, "status": ["in", _TERMINAL_STATUSES]},
		fields=["name", "status", "error", "started_at", "completed_at"],
		order_by="creation desc",
		limit_page_length=runs,
	)
	run_results = [
		{
			"run_name": row.name,
			"status": row.status,
			"passed": row.status == "Completed",
			"error": row.error,
			"started_at": row.started_at,
			"completed_at": row.completed_at,
		}
		for row in run_rows
	]

	decision = evaluate_promotion(None, contains_writes=bool(procedure.contains_writes))

	diagnostics = [
		f"found {len(run_results)} terminal run(s) out of {runs} requested",
		(
			"no live N-run report is wired for this Procedure yet -- promotion is evaluated "
			"with report=None, which the harness itself fails closed on (I10)"
		),
	]
	if len(run_results) < MIN_REPRESENTATIVE_RUNS:
		diagnostics.append(
			f"fewer than the harness's minimum of {MIN_REPRESENTATIVE_RUNS} representative runs exist"
		)

	return {
		"procedure_name": procedure.name,
		"is_read_only": bool(procedure.is_read_only),
		"contains_writes": bool(procedure.contains_writes),
		"runs": run_results,
		"promotion": {
			"approved": decision.approved,
			"reasons": decision.reasons,
		},
		"diagnostics": diagnostics,
	}
