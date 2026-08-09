"""Single source of truth for "can user X run/access Agent Y".

Replaces the previously duplicated, divergent logic in Agent.has_permission()
(huf/huf/doctype/agent/agent.py) and _is_user_allowed() (huf/ai/agent_integration.py).
"""

import frappe
from frappe import _


def check_agent_access(agent_doc, user, *, for_execution=True) -> bool:
	"""Return True if `user` may access/run `agent_doc`.

	Rules (confirmed product semantics):
	- System Manager and the document owner always have access.
	- Guest access depends solely on allow_guest; allowed_users/allowed_roles
	  are never consulted for Guest.
	- If both allowed_users and allowed_roles are empty, every authenticated
	  user is allowed.
	- Otherwise, allowed if the user is listed in allowed_users or holds any
	  role in allowed_roles.
	"""
	# for_execution is currently unused: access rules are identical for viewing/
	# editing and for running the agent. Reserved in case execution ever needs
	# stricter or looser rules than general document access.

	if user == "Guest":
		return bool(agent_doc.allow_guest)

	if agent_doc.owner == user or "System Manager" in frappe.get_roles(user):
		return True

	allowed_users = agent_doc.allowed_users or []
	allowed_roles = agent_doc.allowed_roles or []

	if not allowed_users and not allowed_roles:
		return True

	allowed_user_names = [u.user for u in allowed_users]
	if user in allowed_user_names:
		return True

	allowed_role_names = [r.role for r in allowed_roles]
	user_roles = frappe.get_roles(user)
	if any(role in user_roles for role in allowed_role_names):
		return True

	return False


def assert_agent_access(agent_doc, user=None, *, for_execution=True) -> None:
	"""Throw frappe.PermissionError if `user` (default: current session user)
	may not access/run `agent_doc`."""
	user = user or frappe.session.user

	if not check_agent_access(agent_doc, user, for_execution=for_execution):
		frappe.throw(_("You do not have access to run this agent."), frappe.PermissionError)
