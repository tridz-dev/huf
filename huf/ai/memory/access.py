"""Read rule for personal rows during an agent run (no manager bypass).

An in-run read acts for the run's user (the conversation owner), not for the
session user, which differs in background drains. Rows written by an agent on
the default policy stay private to that agent.
"""

import frappe

from huf.ai.memory.defaults import uses_default_memory_for
from huf.ai.memory.subject import may_recall_for, resolve_memory_subject


def can_read_in_run(row, conversation_id=None, agent_name=None):
	"""True or False when per user and agent rules decide; None to apply the scope rules."""
	getter = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)
	scope_type = getter("scope_type")
	row_agent = getter("agent")

	if scope_type != "User":
		return False if uses_default_memory_for(agent_name) else None
	if conversation_id:
		reader = resolve_memory_subject(conversation_id)
		if not may_recall_for(reader):
			return False
	else:
		reader = frappe.session.user
	if getter("scope_key") != reader:
		return False
	if row_agent == agent_name:
		return True
	return not (uses_default_memory_for(agent_name) or uses_default_memory_for(row_agent))
