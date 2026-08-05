# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Durable identity for a rendered artifact produced inside a conversation.

Artifacts used to exist only as client-side parses of ``Agent Message.content``
with browser-generated ids (``artifact-${Date.now()}-${index}``), so they had no
stable identity and could not be linked to or listed. This DocType gives each
parsed block a server-owned name, which is what the per-artifact URL resolves.

Identity rule: an artifact is identified by ``(message, message_index)``. Re-parsing
the same message must update the existing row rather than insert a duplicate, so
message edits and agent re-runs stay idempotent.
"""

import hashlib

import frappe
from frappe.model.document import Document


def content_hash(content: str) -> str:
	"""SHA-256 of the artifact body, used to detect unchanged content."""
	return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


class Artifact(Document):
	def before_save(self):
		body = self.content or ""
		self.content_hash = content_hash(body)
		self.size_bytes = len(body.encode("utf-8"))

	def validate(self):
		self._validate_conversation_matches_message()

	def _validate_conversation_matches_message(self):
		"""An artifact must belong to the conversation of its source message.

		Guards against a caller linking an artifact to a conversation it did not
		come from, which would leak it into another conversation's artifact list.
		"""
		if not self.message:
			return

		message_conversation = frappe.db.get_value("Agent Message", self.message, "conversation")
		if message_conversation and message_conversation != self.conversation:
			frappe.throw(
				f"Artifact conversation ({self.conversation}) does not match "
				f"the conversation of its source message ({message_conversation}).",
				title="Conversation Mismatch",
			)
