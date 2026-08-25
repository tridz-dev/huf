# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Agent Procedure Run (T-21).

Pins the exact definition it executes (I6, GT-01): ``pinned_definition_json`` /
``pinned_fingerprint`` are copied from the referenced ``Agent Procedure`` once, at
creation, and never re-derived from it afterwards -- ``validate()`` refuses to let
either field change on an existing row, and the runtime (T-23) must read
``pinned_definition_json`` off this document, never re-fetch ``procedure``.

Execution is serialized per-run with ``huf.ai.procedure_lock`` (GT-08): any code path
that advances this run's steps must first acquire
``huf.ai.procedure_lock.ProcedureRunLock(run.name)`` and bail out (not retry inline) if
it does not get the lock -- another worker already owns this run's advancement.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Fields pinned at creation and never mutated afterwards (I6). This is the "run pins the
# definition" half of the guarantee; huf.huf.doctype.agent_procedure enforces the other
# half (a version, once inserted, never changes underneath any run pointing at it).
PINNED_FIELDS = ("procedure", "pinned_fingerprint", "pinned_definition_json")


class AgentProcedureRun(Document):
	def validate(self):
		if self.is_new():
			self._pin_definition()
		else:
			self._guard_pinned_fields_unchanged()

		if self.status == "Running" and not self.started_at:
			self.started_at = now_datetime()
		if self.status in ("Completed", "Failed", "Cancelled") and not self.completed_at:
			self.completed_at = now_datetime()

	def _pin_definition(self):
		if not self.procedure:
			frappe.throw(_("procedure is required"))

		procedure = frappe.db.get_value(
			"Agent Procedure",
			self.procedure,
			["procedure_id", "definition_json", "fingerprint", "status"],
			as_dict=True,
		)
		if not procedure:
			frappe.throw(_("Agent Procedure {0} does not exist").format(self.procedure))

		self.procedure_id = procedure.procedure_id
		self.pinned_definition_json = procedure.definition_json
		self.pinned_fingerprint = procedure.fingerprint

	def _guard_pinned_fields_unchanged(self):
		if frappe.flags.in_install or frappe.flags.in_migrate:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [f for f in PINNED_FIELDS if self.get(f) != before.get(f)]
		if changed:
			frappe.throw(
				_(
					"Agent Procedure Run pins its definition at creation (I6). {0} cannot change "
					"on an existing run."
				).format(", ".join(changed)),
				title=_("Run Definition Pinned"),
			)
