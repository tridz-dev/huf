# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


RUNNABLE_PROCEDURE_STATUSES = ("Testing", "Active")


def assert_procedure_runnable(procedure_name):
	"""Throw unless ``procedure_name`` exists and is Testing/Active."""
	status = frappe.db.get_value("Agent Procedure", procedure_name, "status")
	if status is None:
		frappe.throw(_("Agent Procedure {0} does not exist.").format(procedure_name))
	if status not in RUNNABLE_PROCEDURE_STATUSES:
		frappe.throw(
			_("Agent Procedure {0} is {1}; it must be Testing or Active to be run by an Active Automation.").format(
				procedure_name, status
			),
			title=_("Procedure Not Runnable"),
		)


class Automation(Document):
	def validate(self):
		self._validate_target()
		self._validate_system_agent_lock()
		self._validate_run_as_user()

	def _validate_run_as_user(self):
		"""Only a System Manager may set ``run_as_user`` to anyone but themselves.

		Records who set it (``run_as_set_by``) so the fire-time check in
		automation.runner authorises the run identity against the user who chose
		it, not merely the (possibly more privileged) owner. Without this a Huf
		Manager could edit a System Manager's automation and point it at
		Administrator.
		"""
		if (
			frappe.flags.in_seeding
			or frappe.flags.in_install
			or frappe.flags.in_migrate
			or frappe.flags.in_patch
		):
			return
		if not self.run_as_user:
			self.run_as_set_by = None
			return
		if not self.is_new() and not self.has_value_changed("run_as_user"):
			return
		user = frappe.session.user
		if self.run_as_user != user and "System Manager" not in frappe.get_roles(user):
			frappe.throw(
				_("Only System Managers can set an automation to run as another user."),
				frappe.PermissionError,
			)
		self.run_as_set_by = user

	def _validate_target(self):
		"""Exactly one executor: an Agent, or a pinned Agent Procedure version.

		A Procedure target must be runnable (Testing/Active) before the
		Automation itself may be Active, so Draft procedures -- e.g. fresh
		Flow conversions awaiting human review (I8) -- can be bound to a
		Draft automation but never fire automatically.
		"""
		self.target_type = self.target_type or "Agent"
		if self.target_type == "Agent Procedure":
			if self.agent:
				frappe.throw(_("An Automation targets either an Agent or an Agent Procedure, not both. Clear Agent."))
			if not self.procedure:
				frappe.throw(_("Procedure is required when Target Type is Agent Procedure."))
			if self.status == "Active":
				assert_procedure_runnable(self.procedure)
		else:
			if self.procedure:
				frappe.throw(_("An Automation targets either an Agent or an Agent Procedure, not both. Clear Procedure."))
			if not self.agent:
				frappe.throw(_("Agent is required when Target Type is Agent."))

	def _validate_system_agent_lock(self):
		"""Block non-admins from creating/editing an Automation that targets
		a locked system agent.

		Lives here, not only in huf/ai/automation/api.py's whitelisted
		wrappers, because a generic Frappe REST/RPC call (e.g. a direct
		POST/PUT to /api/resource/Automation, or any other caller with plain
		doctype "write"/"create" permission on Automation -- Huf Manager has
		both by default) bypasses those wrappers entirely and goes straight
		through this controller. automation/api.py's guard is real defense
		in depth for the whitelisted path, but this is the one that actually
		closes the gap for every path, mirroring how
		Agent._validate_system_agent_immutability() itself lives in the
		Agent doctype controller rather than only in an API layer.
		"""
		if not self.agent:
			return
		if (
			frappe.flags.in_seeding
			or frappe.flags.in_install
			or frappe.flags.in_migrate
			or frappe.flags.in_patch
			or "System Manager" in frappe.get_roles()
		):
			return
		is_system = frappe.db.get_value("Agent", self.agent, "is_system")
		if is_system:
			frappe.throw(
				_(
					"Only System Managers can create or modify automations for the "
					"system agent '{0}'."
				).format(self.agent),
				frappe.PermissionError,
				title=_("System Agent Protected"),
			)
