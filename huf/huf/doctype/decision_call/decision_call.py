# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
import frappe
from frappe.model.document import Document


class DecisionCall(Document):
	pass


def has_permission(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access a Decision Call document.
	
	Visibility rules (D5):
	- decision.admin or System Manager: see all
	- Others: see calls where:
	  - User owns the origin run (Agent Run / Flow Run / Automation), OR
	  - User owns the call and it has no origin (Playground, API)
	
	Args:
		doc: Decision Call document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)
	
	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.permissions import has_capability, SYSTEM_MANAGER
	
	user = user or frappe.session.user
	
	# Only read and select are restricted; other operations follow default
	if ptype not in ("read", "select"):
		return None
	
	# Admin sees all
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "decision.admin"):
		return True
	
	# For calls with origin, check if user owns the origin run
	if doc.agent_run:
		owner = frappe.db.get_value("Agent Run", doc.agent_run, "owner")
		if owner == user:
			return True
	
	if doc.flow_run:
		owner = frappe.db.get_value("Flow Run", doc.flow_run, "owner")
		if owner == user:
			return True
	
	if doc.automation:
		owner = frappe.db.get_value("Automation", doc.automation, "owner")
		if owner == user:
			return True
	
	# For calls with no origin (Playground, API), check if user owns it
	if not doc.agent_run and not doc.flow_run and not doc.automation:
		if doc.owner_user == user:
			return True
	
	# Default: deny access
	return False


def get_permission_query_conditions(user=None):
	"""Generate SQL to filter Decision Call rows by user permissions.

	Returns None for admins (see all), or a SQL WHERE clause for non-admins.

	Visibility rules (D5):
	- decision.admin or System Manager: return None (see all)
	- Others: see calls where:
	  - User can read the origin run (Agent Run / Flow Run / Automation via subquery), OR
	  - User owns the call and it has no origin (Playground, API)
	"""
	from huf.permissions import has_capability, SYSTEM_MANAGER

	if not user:
		user = frappe.session.user

	# Admin sees all
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None
	if has_capability(user, "decision.admin"):
		return None

	# Non-admin: build SQL condition
	# Allow if:
	# 1. User owns it AND it has no origin (Playground/API case)
	no_origin_condition = (
		f"`tabDecision Call`.owner_user = {frappe.db.escape(user)} "
		"AND `tabDecision Call`.agent_run IS NULL "
		"AND `tabDecision Call`.flow_run IS NULL "
		"AND `tabDecision Call`.automation IS NULL"
	)

	# 2. User can read the Agent Run origin
	agent_run_condition = (
		f"`tabDecision Call`.agent_run IN ("
		f"SELECT name FROM `tabAgent Run` "
		f"WHERE owner = {frappe.db.escape(user)}"
		")"
	)

	# 3. User can read the Flow Run origin
	# Flow Run permissions: owner or System Manager (built-in Frappe permissions)
	flow_run_condition = (
		f"`tabDecision Call`.flow_run IN ("
		f"SELECT name FROM `tabFlow Run` "
		f"WHERE owner = {frappe.db.escape(user)}"
		")"
	)

	# 4. User can read the Automation origin
	# Automation permissions: owner or System Manager (built-in Frappe permissions)
	automation_condition = (
		f"`tabDecision Call`.automation IN ("
		f"SELECT name FROM `tabAutomation` "
		f"WHERE owner = {frappe.db.escape(user)}"
		")"
	)

	# Combine all conditions with OR
	return (
		f"("
		f"{no_origin_condition} OR "
		f"{agent_run_condition} OR "
		f"{flow_run_condition} OR "
		f"{automation_condition}"
		f")"
	)
