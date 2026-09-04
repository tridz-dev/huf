"""Record-level access checks for runtime doctypes.

Helper functions used by both permission_query_conditions hooks (for list
scoping) and has_permission hooks (for single-doc reads), ensuring
consistent logic across both paths.
"""

import frappe


def user_can_read_run(run_doc, user=None):
	"""Return True if user can read the run (owner, System Manager, or has agent.view_all).

	Args:
		run_doc: Agent Run document or dict with owner field
		user: User to check (default: frappe.session.user)

	Returns:
		bool: True if user can read the run
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "agent.view_all"):
		return True
	return run_doc.owner == user


def user_can_read_message(message_doc, user=None):
	"""Return True if user can read the message (via owning conversation).

	Args:
		message_doc: Agent Message document or dict with conversation field
		user: User to check (default: frappe.session.user)

	Returns:
		bool: True if user can read the message
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "chat.view_all"):
		return True

	# Message owner is determined by its conversation owner
	conv = frappe.db.get_value("Agent Conversation", message_doc.conversation, "owner")
	return conv == user


def user_can_read_conversation(conversation_doc, user=None):
	"""Return True if user can read the conversation (owner or has chat.view_all).

	Args:
		conversation_doc: Agent Conversation document or dict with owner field
		user: User to check (default: frappe.session.user)

	Returns:
		bool: True if user can read the conversation
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "chat.view_all"):
		return True
	return conversation_doc.owner == user


def user_can_read_tool_call(tool_call_doc, user=None):
	"""Return True if user can read the tool call (via owning run).

	Args:
		tool_call_doc: Agent Tool Call document or dict with agent_run field
		user: User to check (default: frappe.session.user)

	Returns:
		bool: True if user can read the tool call
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "agent.view_all"):
		return True

	# Tool call owner is determined by its run owner
	run = frappe.db.get_value("Agent Run", tool_call_doc.agent_run, "owner")
	return run == user


def user_can_read_context_artifact(artifact_doc, user=None):
	"""Return True if user can read the context artifact (via owning conversation).

	Args:
		artifact_doc: Agent Context Artifact document or dict with conversation field
		user: User to check (default: frappe.session.user)

	Returns:
		bool: True if user can read the artifact
	"""
	if not user:
		user = frappe.session.user

	from huf.permissions import has_capability, SYSTEM_MANAGER
	if SYSTEM_MANAGER in frappe.get_roles(user):
		return True
	if has_capability(user, "chat.view_all"):
		return True

	# Artifact owner is determined by its conversation owner
	conv = frappe.db.get_value("Agent Conversation", artifact_doc.conversation, "owner")
	return conv == user
