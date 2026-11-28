import frappe


# ---------------------------------------------------------------------------
# Permission query conditions — used by hooks.py permission_query_conditions
# These return SQL WHERE fragments so Frappe's list view only shows rows
# the current user is allowed to see.
# ---------------------------------------------------------------------------


def get_conversation_permission_conditions(user):
	"""
	Restrict Agent Conversation list to conversations the user owns,
	unless the user has chat.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "chat.view_all"):
		return None

	# Only own conversations
	return f"`tabAgent Conversation`.owner = {frappe.db.escape(user)}"


def get_message_permission_conditions(user):
	"""
	Restrict Agent Message list to messages from conversations the user owns,
	unless the user has chat.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "chat.view_all"):
		return None

	# Filter by conversation ownership
	return f"(`tabAgent Message`.conversation IN (SELECT name FROM `tabAgent Conversation` WHERE owner = {frappe.db.escape(user)}))"


def get_context_artifact_permission_conditions(user):
	"""
	Restrict Agent Context Artifact list to artifacts belonging to
	conversations the user owns, unless the user has chat.view_all
	capability. Mirrors get_conversation_permission_conditions.

	Fix for F-13: previously the only permission row on this DocType was
	System Manager, so ordinary users could never read their own
	conversation's artifacts while any System Manager could read everyone's.
	Re-evaluated against frappe.session.user (or the explicit ``user``
	argument) on every query -- there is no cached/stale authority here (I1,
	I2): a handle to an artifact never grants access beyond what the reader
	independently has on the owning conversation.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "chat.view_all"):
		return None

	return (
		"(`tabAgent Context Artifact`.conversation IN "
		f"(SELECT name FROM `tabAgent Conversation` WHERE owner = {frappe.db.escape(user)}))"
	)


def get_run_permission_conditions(user):
	"""
	Restrict Agent Run list to runs the user owns,
	unless the user has agent.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "agent.view_all"):
		return None

	return f"`tabAgent Run`.owner = {frappe.db.escape(user)}"


def get_tool_call_permission_conditions(user):
	"""
	Restrict Agent Tool Call list to calls from runs the user owns,
	unless the user has agent.view_all capability.

	Agent Tool Call has a direct `agent_run` link field; join to Agent Run's owner.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "agent.view_all"):
		return None

	# Agent Tool Call links directly to Agent Run; join on agent_run field.
	return f"`tabAgent Tool Call`.agent_run IN (SELECT name FROM `tabAgent Run` WHERE owner = {frappe.db.escape(user)})"


def get_prompt_snapshot_permission_conditions(user):
	"""
	Restrict Agent Run Prompt Snapshot list to snapshots from runs the user owns,
	unless the user has agent.view_all capability.
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import SYSTEM_MANAGER, has_capability
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return None

	if has_capability(user, "agent.view_all"):
		return None

	# Only own runs' snapshots
	return f"`tabAgent Run Prompt Snapshot`.agent_run IN (SELECT name FROM `tabAgent Run` WHERE owner = {frappe.db.escape(user)})"
