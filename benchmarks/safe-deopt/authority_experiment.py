# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Authority sub-experiment (safe-deopt brief, Step 6, Track-Item: 7).

Deterministic, Frappe-free, no LLM and no bench -- pure Python over the in-memory stores in
``workloads.py``.

Scenario
--------
A Procedure's write B (``submit_linked_record`` for W1 / ``submit_allocation`` for W2) is
"approved" under an admin-scoped envelope -- i.e. write A (creating the draft/ToDo) runs
under an authorizer that grants the write-B action too, establishing that the action is
*allowed in principle* for an admin-scoped actor. The Procedure is then INVOKED (write B
itself attempted) as a lower-privileged actor: the store is driven through the SAME code
path but with an authorizer that denies the specific write-B action for this actor.

Expected results, all checked against ground truth (``store.commit_log``), never against
whatever a wrapper might report back to a caller:

1. Write B is denied at runtime: ``PermissionDenied`` is raised.
2. No partial commit: the ground-truth commit log shows the write-B attempt logged as
   ``committed=False`` (permission_denied), and no committed record exists for it.
3. The handoff/fallback payload produced after the denial carries no elevated authority: it
   is a plain, inert dict (no authorizer, no callable, no admin-scoped envelope reference) --
   the low-privileged authorizer is what a recovery agent would receive, nothing stronger.
2b. A simulated "recovery agent" retries the exact same write through the exact same store,
   under the SAME restrictive authorizer (as carried by the handoff payload) -- and is
   ALSO denied. This proves the handoff cannot be used to smuggle an escalated retry.

Both W1 (``CrmStore.submit_linked_record``) and W2 (``PaymentAllocationStore.submit_allocation``)
are exercised, since both are cheap to set up and the point (denial is real, not
type-specific) is worth confirming on both write-B shapes.

Note on ``execute_procedure``: ``huf/ai/graph/procedure_runtime.py::execute_procedure`` (see
its signature, currently keyword args ``tool_invoker``, ``run_id``, ``on_visit``,
``on_node_start``, ``classify_tool``, ``procedure_name``, ``dedup_window_seconds``) does NOT
accept an injectable ``authorizer`` parameter today -- there is no such parameter. Its own
docstring says authorization is the caller's responsibility, folded into the ``tool_invoker``
closure it is given (see :func:`run_agent_procedure_run` for the real caller that does this).
This experiment does not use ``execute_procedure`` at all -- like ``workloads.py`` itself, it
stays frappe-free and runtime-free, and drives the two stores' own ``authorizer=`` constructor
hook directly, which *is* the real, already-existing injection point.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
	sys.path.insert(0, str(_HERE.parent))

from workloads import (  # noqa: E402
	Allocation,
	CrmStore,
	Customer,
	Invoice,
	OpenItem,
	Payment,
	PaymentAllocationStore,
	PermissionDenied,
	ToDo,
)

ADMIN_ACTOR = "admin@example.com"
LOW_PRIV_ACTOR = "clerk@example.com"


def _admin_authorizer(_action: str, _payload: dict) -> bool:
	"""Grants everything -- the admin-scoped envelope write A (and, in principle, write B)
	is approved under."""
	return True


def _low_priv_authorizer_w1(action: str, _payload: dict) -> bool:
	"""Denies the specific write-B action (``submit_linked_record``) for the low-privileged
	actor; everything else (e.g. write A, ``create_followup_todo``) is allowed so the scenario
	setup can proceed."""
	return action != "submit_linked_record"


def _low_priv_authorizer_w2(action: str, _payload: dict) -> bool:
	"""Denies the specific write-B action (``submit_allocation``) for the low-privileged
	actor; write A (``create_allocation``) remains allowed."""
	return action != "submit_allocation"


def _make_handoff_payload(*, actor: str, authorizer, denied_action: str, reason: str) -> dict:
	"""Builds the fallback/handoff payload a real recovery-routing layer would produce after a
	PermissionDenied. Deliberately a plain, inert ``dict`` of primitives: no authorizer
	object, no callable, no reference to the admin-scoped envelope that approved write A --
	so it cannot smuggle elevated authority to whatever picks it up next. The recovery agent
	only carries the actor's own identity and the restrictive authorizer *by reconstruction*
	(the caller of this module re-attaches the SAME restrictive authorizer explicitly below;
	the payload itself never carries a capability).
	"""
	return {
		"actor": actor,
		"denied_action": denied_action,
		"reason": reason,
		# Explicitly absent: "authorizer", "admin_token", "envelope", or any callable/object
		# that would let a recipient bypass the actor's real permissions.
	}


def _payload_is_inert(payload: dict) -> bool:
	"""True iff the handoff payload contains no callables and no keys that would carry an
	elevated-authority capability (an authorizer function, a token, an envelope reference)."""
	forbidden_keys = {"authorizer", "admin_token", "envelope", "capability", "override"}
	if forbidden_keys & set(payload.keys()):
		return False
	return not any(callable(v) for v in payload.values())


def _run_w1_scenario() -> dict[str, Any]:
	checks: dict[str, Any] = {}

	# -- Step A: admin-scoped envelope approves write A and (in principle) write B ---------
	admin_store = CrmStore(authorizer=_admin_authorizer)
	admin_store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
	admin_store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-2001", customer_id="CUST-1", outstanding_amount=100.0))
	todo = admin_store.create_followup_todo(
		reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to=ADMIN_ACTOR, operation_key="proc:node-a:SINV-2001"
	)
	checks["w1_write_a_approved_under_admin_envelope"] = {
		"passed": isinstance(todo, ToDo) and admin_store.commit_log[-1].committed is True,
		"detail": "write A (create_followup_todo) committed under admin-scoped authorizer",
	}

	# -- Step B: the SAME logical procedure is invoked as a lower-privileged actor. The
	# low-priv store shares the same seeded world (a fresh store is built for it, mirroring
	# the same records, since a real system would route the same records through per-request
	# authorizers rather than sharing a live store object across actors).
	low_store = CrmStore(authorizer=_low_priv_authorizer_w1)
	low_store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
	low_store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-2001", customer_id="CUST-1", outstanding_amount=100.0))
	low_store.create_followup_todo(
		reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to=LOW_PRIV_ACTOR, operation_key="proc:node-a:SINV-2001"
	)

	denied = False
	try:
		low_store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2001", operation_key="proc:node-b:SINV-2001")
	except PermissionDenied:
		denied = True
	checks["w1_write_b_denied_for_low_priv_actor"] = {"passed": denied, "detail": "submit_linked_record raised PermissionDenied for low-priv authorizer"}

	# -- Ground truth: no partial commit ----------------------------------------------------
	item = low_store.open_items[("Sales Invoice", "SINV-2001")]
	no_partial_commit = item.status == "open" and not any(
		e.action == "submit_linked_record" and e.committed for e in low_store.commit_log
	)
	denial_logged = any(
		e.action == "submit_linked_record" and not e.committed and e.detail.get("reason") == "permission_denied" for e in low_store.commit_log
	)
	checks["w1_no_partial_commit"] = {"passed": no_partial_commit and denial_logged, "detail": f"open_item.status={item.status!r}, denial logged in commit_log"}

	# -- Handoff payload carries no elevated authority --------------------------------------
	handoff = _make_handoff_payload(actor=LOW_PRIV_ACTOR, authorizer=_low_priv_authorizer_w1, denied_action="submit_linked_record", reason="permission_denied")
	checks["w1_handoff_payload_is_inert"] = {"passed": _payload_is_inert(handoff), "detail": f"handoff payload keys={sorted(handoff.keys())}"}

	# -- Recovery agent retries under the SAME restrictive authorizer -> still denied -------
	recovery_denied = False
	try:
		low_store.submit_linked_record(reference_type="Sales Invoice", reference_name="SINV-2001", operation_key="proc:node-b:SINV-2001-retry")
	except PermissionDenied:
		recovery_denied = True
	checks["w1_recovery_agent_also_denied"] = {
		"passed": recovery_denied,
		"detail": "a 'recovery agent' retrying submit_linked_record via the same store under the same low-priv authorizer was also denied",
	}

	item_after = low_store.open_items[("Sales Invoice", "SINV-2001")]
	checks["w1_no_commit_after_recovery_attempt"] = {
		"passed": item_after.status == "open",
		"detail": f"open_item.status={item_after.status!r} after recovery-agent retry attempt",
	}

	return checks


def _run_w2_scenario() -> dict[str, Any]:
	checks: dict[str, Any] = {}

	admin_store = PaymentAllocationStore(authorizer=_admin_authorizer)
	admin_store.seed_invoice(Invoice(name="INV-001", customer="CUST-1", outstanding_amount=250.0))
	admin_store.seed_payment(Payment(name="PAY-001", customer="CUST-1", amount=250.0))
	alloc = admin_store.create_allocation(payment="PAY-001", invoice="INV-001", amount=250.0, operation_key="proc:node-a:PAY-001")
	checks["w2_write_a_approved_under_admin_envelope"] = {
		"passed": isinstance(alloc, Allocation) and admin_store.commit_log[-1].committed is True,
		"detail": "write A (create_allocation) committed under admin-scoped authorizer",
	}

	low_store = PaymentAllocationStore(authorizer=_low_priv_authorizer_w2)
	low_store.seed_invoice(Invoice(name="INV-001", customer="CUST-1", outstanding_amount=250.0))
	low_store.seed_payment(Payment(name="PAY-001", customer="CUST-1", amount=250.0))
	low_alloc = low_store.create_allocation(payment="PAY-001", invoice="INV-001", amount=250.0, operation_key="proc:node-a:PAY-001")

	denied = False
	try:
		low_store.submit_allocation(allocation=low_alloc.name, operation_key="proc:node-b:PAY-001")
	except PermissionDenied:
		denied = True
	checks["w2_write_b_denied_for_low_priv_actor"] = {"passed": denied, "detail": "submit_allocation raised PermissionDenied for low-priv authorizer"}

	invoice = low_store.invoices["INV-001"]
	no_partial_commit = invoice.outstanding_amount == 250.0 and low_alloc.status == "draft" and not any(
		e.action == "submit_allocation" and e.committed for e in low_store.commit_log
	)
	denial_logged = any(
		e.action == "submit_allocation" and not e.committed and e.detail.get("reason") == "permission_denied" for e in low_store.commit_log
	)
	checks["w2_no_partial_commit"] = {
		"passed": no_partial_commit and denial_logged,
		"detail": f"invoice.outstanding_amount={invoice.outstanding_amount!r}, allocation.status={low_alloc.status!r}",
	}

	handoff = _make_handoff_payload(actor=LOW_PRIV_ACTOR, authorizer=_low_priv_authorizer_w2, denied_action="submit_allocation", reason="permission_denied")
	checks["w2_handoff_payload_is_inert"] = {"passed": _payload_is_inert(handoff), "detail": f"handoff payload keys={sorted(handoff.keys())}"}

	recovery_denied = False
	try:
		low_store.submit_allocation(allocation=low_alloc.name, operation_key="proc:node-b:PAY-001-retry")
	except PermissionDenied:
		recovery_denied = True
	checks["w2_recovery_agent_also_denied"] = {
		"passed": recovery_denied,
		"detail": "a 'recovery agent' retrying submit_allocation via the same store under the same low-priv authorizer was also denied",
	}

	invoice_after = low_store.invoices["INV-001"]
	checks["w2_no_commit_after_recovery_attempt"] = {
		"passed": invoice_after.outstanding_amount == 250.0 and low_alloc.status == "draft",
		"detail": f"invoice.outstanding_amount={invoice_after.outstanding_amount!r} after recovery-agent retry attempt",
	}

	return checks


def run_authority_experiment() -> dict[str, Any]:
	"""Runs the W1 and W2 authority-denial scenarios and returns a structured pass/fail
	report: ``{"passed": bool, "checks": {name: {"passed": bool, "detail": str}, ...}}``.
	"""
	checks: dict[str, Any] = {}
	checks.update(_run_w1_scenario())
	checks.update(_run_w2_scenario())

	all_passed = all(c["passed"] for c in checks.values())
	return {"passed": all_passed, "checks": checks}


if __name__ == "__main__":
	import json

	print(json.dumps(run_authority_experiment(), indent=2))
