"""has_permission hooks for runtime doctypes (Agent Run, Message, Conversation, Tool Call, Context Artifact).

These hooks enforce record-level authorization for single-document reads
via frappe.client.get, frappe.get_doc, and Document.check_permission().
They mirror the logic in permission_query_conditions hooks to ensure
consistent access control across both list and single-doc paths.
"""

import frappe


def has_permission_agent_run(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access an Agent Run document.

	Args:
		doc: Agent Run document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)

	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.ai.record_access import user_can_read_run

	user = user or frappe.session.user
	if ptype in ("read", "select"):
		return user_can_read_run(doc, user)
	elif ptype in ("write", "save"):
		# Only owner can write (or System Manager, which is checked by default)
		if "System Manager" in frappe.get_roles(user):
			return True
		return doc.owner == user
	elif ptype == "delete":
		# Only owner can delete (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		return doc.owner == user
	return None  # Let framework decide for other ptypes


def has_permission_agent_message(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access an Agent Message document.

	Args:
		doc: Agent Message document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)

	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.ai.record_access import user_can_read_message

	user = user or frappe.session.user
	if ptype in ("read", "select"):
		return user_can_read_message(doc, user)
	elif ptype in ("write", "save"):
		# Only conversation owner can write (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		conv_owner = frappe.db.get_value("Agent Conversation", doc.conversation, "owner")
		return conv_owner == user
	elif ptype == "delete":
		# Only conversation owner can delete (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		conv_owner = frappe.db.get_value("Agent Conversation", doc.conversation, "owner")
		return conv_owner == user
	return None  # Let framework decide for other ptypes


def has_permission_agent_conversation(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access an Agent Conversation document.

	Args:
		doc: Agent Conversation document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)

	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.ai.record_access import user_can_read_conversation

	user = user or frappe.session.user
	if ptype in ("read", "select"):
		return user_can_read_conversation(doc, user)
	elif ptype in ("write", "save"):
		# Only owner can write (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		return doc.owner == user
	elif ptype == "delete":
		# Only owner can delete (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		return doc.owner == user
	return None  # Let framework decide for other ptypes


def has_permission_agent_tool_call(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access an Agent Tool Call document.

	Args:
		doc: Agent Tool Call document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)

	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.ai.record_access import user_can_read_tool_call

	user = user or frappe.session.user
	if ptype in ("read", "select"):
		return user_can_read_tool_call(doc, user)
	elif ptype in ("write", "save"):
		# Only run owner can write (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		run_owner = frappe.db.get_value("Agent Run", doc.agent_run, "owner")
		return run_owner == user
	elif ptype == "delete":
		# Only run owner can delete (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		run_owner = frappe.db.get_value("Agent Run", doc.agent_run, "owner")
		return run_owner == user
	return None  # Let framework decide for other ptypes


def has_permission_agent_context_artifact(doc, ptype=None, user=None):
	"""Frappe hook: check if user can access an Agent Context Artifact document.

	Args:
		doc: Agent Context Artifact document
		ptype: Permission type ("read", "write", "delete", etc.)
		user: User to check (default: frappe.session.user)

	Returns:
		bool or None: True to allow, False to deny, None to let Frappe decide
	"""
	from huf.ai.record_access import user_can_read_context_artifact

	user = user or frappe.session.user
	if ptype in ("read", "select"):
		return user_can_read_context_artifact(doc, user)
	elif ptype in ("write", "save"):
		# Only conversation owner can write (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		conv_owner = frappe.db.get_value("Agent Conversation", doc.conversation, "owner")
		return conv_owner == user
	elif ptype == "delete":
		# Only conversation owner can delete (or System Manager)
		if "System Manager" in frappe.get_roles(user):
			return True
		conv_owner = frappe.db.get_value("Agent Conversation", doc.conversation, "owner")
		return conv_owner == user
	return None  # Let framework decide for other ptypes
