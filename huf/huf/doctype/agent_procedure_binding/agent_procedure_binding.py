# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Agent Procedure Binding -- pins a bound Procedure version onto an Agent (T-31).

Deliberately NOT an Agent Tool Function row per (agent, procedure) pair (GOAL.md ss3.1):
that would put a full tool-function definition in the model's static tool list forever.
Instead, this DocType only records the binding; huf.ai.graph.procedure_binding computes
the actual tool-like exposure at request time, from the set of *enabled* rows, and
huf.ai.sdk_tools.create_agent_tools wires that into the tool list it already assembles.

Two invariants this controller enforces, both at validate() time (defence in depth --
huf.ai.graph.procedure_binding re-checks both again at exposure time, fail closed):

  I8 -- No automatic activation of write Procedures. A binding may only ever point at a
  Procedure version with is_read_only=1. There is no bypass flag; a write Procedure is
  activated by hand, outside this feature, in a later wave.

  Per-agent cap -- Procedure schemas entering model context is exactly the context bloat
  this feature exists to remove (T-31 warning, PLAN.md). An agent may not hold more than
  get_binding_cap() *enabled* bindings at once; the cap is a floor under lazy discovery
  (GT-07), not a substitute for it.

Promotion / rollback (I6): a logical procedure's active version for an agent is changed
by editing this binding's `procedure` link (an atomic move of one row), never by mutating
the Agent Procedure version row itself -- those rows are structurally immutable (see
huf.huf.doctype.agent_procedure). Rollback is therefore just another binding move, to an
older version.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.graph.procedure_binding import get_binding_cap


class AgentProcedureBinding(Document):
	def validate(self):
		self._denormalize_from_procedure()
		self._guard_read_only(self._procedure_snapshot)
		self._guard_single_enabled_per_procedure_id()
		self._guard_per_agent_cap()

	def _denormalize_from_procedure(self):
		if not self.procedure:
			frappe.throw(_("procedure is required"))

		procedure = frappe.db.get_value(
			"Agent Procedure",
			self.procedure,
			["procedure_id", "version", "is_read_only", "status"],
			as_dict=True,
		)
		if not procedure:
			frappe.throw(_("Agent Procedure {0} does not exist").format(self.procedure))

		self.procedure_id = procedure.procedure_id
		self.version = procedure.version
		self._procedure_snapshot = procedure

	def _guard_read_only(self, procedure):
		if self.enabled and not procedure.is_read_only:
			frappe.throw(
				_(
					"Agent Procedure {0} is not read-only (I8). Only read-only Procedures may be "
					"bound and enabled in this wave -- write Procedures require manual activation "
					"outside Agent Procedure Binding."
				).format(self.procedure),
				title=_("Write Procedure Cannot Be Bound"),
			)

	def _guard_single_enabled_per_procedure_id(self):
		"""At most one *enabled* binding per (agent, procedure_id) at a time.

		Promotion/rollback is meant to be a single atomic move (I6) -- update this row's
		`procedure` link to the new version -- not "add a second enabled binding for the
		same logical procedure and hope the runtime picks the right one."
		"""
		if not self.enabled or not self.agent or not self.procedure_id:
			return

		other = frappe.db.exists(
			"Agent Procedure Binding",
			{
				"agent": self.agent,
				"procedure_id": self.procedure_id,
				"enabled": 1,
				"name": ("!=", self.name or ""),
			},
		)
		if other:
			frappe.throw(
				_(
					"Agent {0} already has an enabled binding ({1}) for procedure {2}. Promote by "
					"moving that binding's `procedure` link, or disable it first, instead of "
					"enabling a second binding for the same procedure_id."
				).format(self.agent, other, self.procedure_id),
				title=_("Duplicate Enabled Binding"),
			)

	def _guard_per_agent_cap(self):
		"""Fail closed (per T-31 warning): refuse to enable past the configured cap."""
		if not self.enabled or not self.agent:
			return

		cap = get_binding_cap()
		existing_enabled = frappe.db.count(
			"Agent Procedure Binding",
			{
				"agent": self.agent,
				"enabled": 1,
				"name": ("!=", self.name or ""),
			},
		)
		if existing_enabled + 1 > cap:
			frappe.throw(
				_(
					"Agent {0} already has {1} enabled Agent Procedure Binding(s), at the "
					"configured per-agent cap of {2}. Disable another binding before enabling "
					"this one."
				).format(self.agent, existing_enabled, cap),
				title=_("Procedure Binding Cap Exceeded"),
			)
