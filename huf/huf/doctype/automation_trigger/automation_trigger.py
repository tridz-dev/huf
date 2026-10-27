# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AutomationTrigger(Document):
	def validate(self):
		self._validate_system_agent_lock()
		self._validate_cron()
		self._set_initial_next_execution()

	def _validate_cron(self):
		if self.trigger_type != "Schedule" or self.schedule_type != "Cron":
			return
		from croniter import croniter

		if not self.cron_expression or not croniter.is_valid(self.cron_expression):
			frappe.throw(_("Invalid cron expression: {0}").format(self.cron_expression or ""))

	def _set_initial_next_execution(self):
		"""Schedule-type triggers are only ever picked up by
		automation.scheduler.run_due_automations() via a
		``next_execution <= now`` filter, which excludes NULL in SQL. A
		freshly created (or re-enabled) Schedule trigger with no
		next_execution yet would therefore never fire -- compute an initial
		one here, the same way the scheduler advances it after each run.

		Also recomputed whenever the schedule definition (type, cron, interval)
		changes, otherwise an edited cron would keep firing on the old cadence
		until the stale next_execution elapsed. Cron expressions are evaluated in
		the system time zone (``now_datetime()``), not a per-trigger time zone.
		"""
		if self.trigger_type != "Schedule":
			return
		schedule_changed = not self.is_new() and any(
			self.has_value_changed(f)
			for f in ("schedule_type", "cron_expression", "scheduled_interval", "interval_count")
		)
		if self.next_execution and not schedule_changed:
			return
		from huf.ai.automation.scheduler import compute_next_execution

		self.next_execution = compute_next_execution(self.as_dict(), now_datetime())

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
