# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Read-only Artifact APIs backing the conversation artifacts panel and the
per-artifact permalink page.

Both endpoints are conversation-scoped: a caller may list or read artifacts
only for a conversation they can open in chat, so an artifact id alone is never
enough to read someone else's work. Anything that changes or exports an
artifact stays limited to the conversation owner and System Manager.
"""

import frappe
from frappe import _


def _get_conversation(conversation: str):
	if not conversation:
		frappe.throw(_("Conversation is required"), frappe.ValidationError)

	return frappe.get_doc("Agent Conversation", conversation)


def _is_owner_or_system_manager(conv_doc) -> bool:
	return conv_doc.owner == frappe.session.user or "System Manager" in frappe.get_roles()


def _deny():
	frappe.throw(_("You do not have permission to view this conversation."), frappe.PermissionError)


def _check_conversation_access(conversation: str) -> None:
	"""Raise ``frappe.PermissionError`` unless the user owns ``conversation`` or is a System Manager.

	The strict check, used by export, save and agent-tool paths. Mirrors the
	ownership check already used for conversation file uploads in
	``huf.ai.agent.chat``.
	"""
	if not _is_owner_or_system_manager(_get_conversation(conversation)):
		_deny()


def _check_conversation_read_access(conversation: str) -> None:
	"""Raise ``frappe.PermissionError`` unless the user may read ``conversation``.

	Read-only paths use this so they agree with the chat view, which loads the
	conversation through its document permission (role permission plus the
	``has_permission`` hook, e.g. ``chat.view_all``).
	"""
	conv_doc = _get_conversation(conversation)

	if _is_owner_or_system_manager(conv_doc):
		return

	if not frappe.has_permission("Agent Conversation", "read", doc=conv_doc):
		_deny()


@frappe.whitelist()
def list_conversation_artifacts(conversation: str) -> list[dict]:
	"""Return compact artifact rows for the conversation artifacts side panel.

	Excludes ``content`` — the panel only needs the small display fields, and
	an artifact's content can be large.
	"""
	if not conversation:
		return []

	_check_conversation_read_access(conversation)

	return frappe.get_all(
		"Artifact",
		filters={"conversation": conversation},
		fields=[
			"name",
			"title",
			"artifact_type",
			"language",
			"message",
			"message_index",
			"size_bytes",
			"creation",
		],
		order_by="creation asc, message_index asc",
	)


@frappe.whitelist()
def get_artifact(name: str) -> dict:
	"""Return one artifact in full, including ``content``, for the per-artifact permalink page."""
	if not name:
		frappe.throw(_("Artifact name is required"), frappe.ValidationError)

	artifact = frappe.get_doc("Artifact", name)

	_check_conversation_read_access(artifact.conversation)

	return {
		"name": artifact.name,
		"title": artifact.title,
		"artifact_type": artifact.artifact_type,
		"language": artifact.language,
		"content": artifact.content,
		"message": artifact.message,
		"message_index": artifact.message_index,
		"size_bytes": artifact.size_bytes,
		"creation": artifact.creation,
		"conversation": artifact.conversation,
		"content_hash": artifact.content_hash,
		"agent": artifact.agent,
	}
