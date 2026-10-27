# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Manual-approval gate for write Agent Procedures.

Agent Procedure Binding refuses to bind/enable any Procedure with ``is_read_only=0``
(I8: no automatic activation of write Procedures -- see
``huf.huf.doctype.agent_procedure_binding.agent_procedure_binding``). That guard is
intentional and correct, but on its own it leaves no path at all for a write Procedure
(T-40's write runtime -- ``huf.ai.graph.procedure_runtime`` -- is built and tested) to
ever become bindable, not even after a human has reviewed it. This module is that path:
a deliberately narrow, two-step manual gate.

  1. :func:`request_procedure_approval` -- any authenticated user with read access to
     Agent Procedure can flag a write Procedure as ready for review. Sets
     ``approval_status = "Pending Review"``. Does not grant anything by itself.

  2. :func:`approve_procedure` -- restricted to System Manager / Huf Manager (checked
     explicitly here, not delegated to DocType-level permissions, because this is the
     entire point of the gate: an ordinary author can request review but cannot grant
     it to themselves). Sets ``approval_status`` to ``Approved`` or ``Rejected``, and
     stamps ``approved_by``/``approved_at``.

Only once ``approval_status == "Approved"`` does
``agent_procedure_binding.AgentProcedureBinding._guard_read_only`` allow a binding to be
enabled for that write Procedure -- as an explicit *additional* allowance alongside the
existing read-only-only path, not a replacement for it.

Read-only Procedures (``is_read_only=1``) never enter this flow: they can already be
bound directly, so both functions here reject them outright -- there is nothing to
approve.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

#: Roles allowed to approve/reject a write Procedure. Mirrors huf.ai.hub_api's
#: _MODEL_MANAGER_ROLES pattern -- System Manager (Frappe role) or Huf Manager (Huf role).
APPROVAL_MANAGER_ROLES = ("System Manager", "Huf Manager")


def _require_procedure_read() -> None:
	if not frappe.has_permission("Agent Procedure", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_approval_manager() -> None:
	"""Explicit role check -- this is the whole point of the gate, never skip it."""
	if not set(frappe.get_roles()).intersection(APPROVAL_MANAGER_ROLES):
		frappe.throw(
			_("Only System Managers or Huf Managers can approve or reject a Procedure."),
			frappe.PermissionError,
		)


def _get_procedure(procedure_name: str):
	if not procedure_name:
		frappe.throw(_("procedure_name is required"))
	if not frappe.db.exists("Agent Procedure", procedure_name):
		frappe.throw(_("Agent Procedure {0} does not exist").format(procedure_name))
	return frappe.get_doc("Agent Procedure", procedure_name)


def _guard_write_tier(procedure) -> None:
	"""Only a write Procedure (is_read_only=0) is eligible for this flow at all --
	read-only Procedures already bind directly and have nothing to approve."""
	if procedure.is_read_only:
		frappe.throw(
			_(
				"Agent Procedure {0} is read-only and can already be bound directly -- there is "
				"nothing to approve."
			).format(procedure.name),
			title=_("Nothing To Approve"),
		)


@frappe.whitelist()
def request_procedure_approval(procedure_name: str) -> dict:
	"""Flag a write Procedure as ready for manual review.

	Any user with Agent Procedure read access may call this (in practice, the Huf User
	role and above). It only moves ``approval_status`` to "Pending Review" -- it grants
	no binding rights by itself; only :func:`approve_procedure` can do that.
	"""
	_require_procedure_read()
	procedure = _get_procedure(procedure_name)
	_guard_write_tier(procedure)

	if procedure.approval_status == "Approved":
		# Idempotency: already approved, requesting review again is a clean no-op.
		return {
			"procedure_name": procedure.name,
			"approval_status": procedure.approval_status,
			"changed": False,
		}

	procedure.approval_status = "Pending Review"
	procedure.save(ignore_permissions=True)

	return {
		"procedure_name": procedure.name,
		"approval_status": procedure.approval_status,
		"changed": True,
	}


@frappe.whitelist()
def approve_procedure(procedure_name: str, approve: bool = True, note: str = "") -> dict:
	"""Approve or reject a write Procedure for binding. Manager-only (I8 gate).

	Args:
	    procedure_name: name of the Agent Procedure to decide on.
	    approve: True to set ``approval_status = "Approved"``, False to set
	        ``"Rejected"``.
	    note: optional free-text reviewer note, stored on ``approval_note``.

	Idempotency: calling this again on an already-``Approved`` Procedure with
	``approve=True`` is a clean no-op that returns the current state rather than
	throwing -- re-approving something already approved is not an error.
	"""
	_require_approval_manager()
	procedure = _get_procedure(procedure_name)
	_guard_write_tier(procedure)

	approve = frappe.parse_json(approve) if isinstance(approve, str) else bool(approve)

	if approve and procedure.approval_status == "Approved":
		return {
			"procedure_name": procedure.name,
			"approval_status": procedure.approval_status,
			"approved_by": procedure.approved_by,
			"approved_at": procedure.approved_at,
			"changed": False,
		}

	procedure.approval_status = "Approved" if approve else "Rejected"
	procedure.approved_by = frappe.session.user
	procedure.approved_at = now_datetime()
	if note:
		procedure.approval_note = note
	procedure.save(ignore_permissions=True)

	return {
		"procedure_name": procedure.name,
		"approval_status": procedure.approval_status,
		"approved_by": procedure.approved_by,
		"approved_at": procedure.approved_at,
		"changed": True,
	}
