# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime


class AutomationTrigger(Document):
	def validate(self):
		self._validate_system_agent_lock()
		self._set_initial_next_execution()

	def _set_initial_next_execution(self):
		"""Schedule-type triggers are only ever picked up by
		automation_scheduler.run_due_automations() via a
		``next_execution <= now`` filter, which excludes NULL in SQL. A
		freshly created (or re-enabled) Schedule trigger with no
		next_execution yet would therefore never fire -- compute an initial
		one here, the same way the scheduler advances it after each run.
		"""
		if self.trigger_type != "Schedule" or self.next_execution:
			return
		interval = self.interval_count or 1
		si = (self.scheduled_interval or "").lower()
		self.next_execution = add_to_date(
			now_datetime(),
			hours=interval if si == "hourly" else 0,
			days=interval if si == "daily" else 0,
			weeks=interval if si == "weekly" else 0,
			months=interval if si == "monthly" else 0,
			years=interval if si == "yearly" else 0,
		)

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
