# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Read-only Artifact APIs backing the conversation artifacts panel and the
per-artifact permalink page.

Both endpoints are conversation-scoped: a caller must own the conversation
(or hold System Manager) to list or read its artifacts, so an artifact id
alone is never enough to read someone else's work.
"""

import frappe
from frappe import _


def _check_conversation_access(conversation: str) -> None:
	"""Raise ``frappe.PermissionError`` unless the current user may view ``conversation``.

	Allowed when the user owns the conversation or holds the System Manager
	role. Mirrors the ownership check already used for conversation file
	uploads in ``huf.ai.agent_chat``.
	"""
	if not conversation:
		frappe.throw(_("Conversation is required"), frappe.ValidationError)

	conv_doc = frappe.get_doc("Agent Conversation", conversation)

	if conv_doc.owner == frappe.session.user or "System Manager" in frappe.get_roles():
		return

	frappe.throw(_("You do not have permission to view this conversation."), frappe.PermissionError)


@frappe.whitelist()
def list_conversation_artifacts(conversation: str) -> list[dict]:
	"""Return compact artifact rows for the conversation artifacts side panel.

	Excludes ``content`` — the panel only needs the small display fields, and
	an artifact's content can be large.
	"""
	if not conversation:
		return []

	_check_conversation_access(conversation)

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

	_check_conversation_access(artifact.conversation)

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
