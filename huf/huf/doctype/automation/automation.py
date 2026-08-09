# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Automation(Document):
	def validate(self):
		self._validate_system_agent_lock()

	def _validate_system_agent_lock(self):
		"""Block non-admins from creating/editing an Automation that targets
		a locked system agent.

		Lives here, not only in huf/ai/automation_api.py's whitelisted
		wrappers, because a generic Frappe REST/RPC call (e.g. a direct
		POST/PUT to /api/resource/Automation, or any other caller with plain
		doctype "write"/"create" permission on Automation -- Huf Manager has
		both by default) bypasses those wrappers entirely and goes straight
		through this controller. automation_api.py's guard is real defense
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
