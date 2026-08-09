# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AutomationTrigger(Document):
	def validate(self):
		self._validate_system_agent_lock()

	def _validate_system_agent_lock(self):
		"""Same guard as Automation._validate_system_agent_lock(), applied
		here too since an Automation Trigger can be created/edited directly
		(generic REST, or any caller with doctype permission on Automation
		Trigger) without ever touching the parent Automation's own
		validate(). See Automation.py's docstring for the full rationale.
		"""
		if not self.automation:
			return
		if (
			frappe.flags.in_seeding
			or frappe.flags.in_install
			or frappe.flags.in_migrate
			or frappe.flags.in_patch
			or "System Manager" in frappe.get_roles()
		):
			return
		agent_name = frappe.db.get_value("Automation", self.automation, "agent")
		if not agent_name:
			return
		is_system = frappe.db.get_value("Agent", agent_name, "is_system")
		if is_system:
			frappe.throw(
				_(
					"Only System Managers can create or modify triggers for automations "
					"belonging to the system agent '{0}'."
				).format(agent_name),
				frappe.PermissionError,
				title=_("System Agent Protected"),
			)
