# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""
huf/ai/record_access.py

Shared home for permission_query_conditions / has_permission style helpers
that scope reads of Huf child/log records (Agent Run Feedback, and friends)
to their owner unless the caller holds System Manager or the relevant
"view_all" capability.

Coordination note (ST-R4.1 / WP-R4): this module is also where Remediation
WP-01 / ST-01.1 is planned to add its own record-access helpers
(``user_can_read_run``, ``user_can_read_message``, etc.). If this WP lands
first, Remediation WP-01 should add its helpers here alongside
``get_feedback_permission_conditions`` rather than inventing a second
module. If WP-01 lands first and this file already exists with a different
set of helpers, this function should be added alongside them instead.

Pattern mirrors the existing ``get_*_permission_conditions`` functions in
``huf/ai/agent_integration.py`` (e.g. ``get_run_permission_conditions``).
"""

import frappe

from huf.permissions import SYSTEM_MANAGER, has_capability


def get_feedback_permission_conditions(user):
	"""Return a condition scoping feedback reads to the user who created them."""
	if not user:
		user = frappe.session.user

	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "agent.view_all"):
		return None

	return f"`tabAgent Run Feedback`.owner = {frappe.db.escape(user)}"
