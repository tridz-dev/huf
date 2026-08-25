# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentConversation(Document):
	def on_trash(self):
		"""Cascade delete this conversation's Agent Context Artifacts (T-11b, F-16).

		Frappe runs ``on_trash`` before its own link-existence check
		(``frappe/model/delete_doc.py``), so without this, deleting a
		conversation either raises ``LinkExistsError`` (if artifacts still
		point at it) or -- via the generic
		``huf.ai.agent_chat._orphan_conversation_links`` sweep that runs ahead
		of ``frappe.delete_doc`` -- silently orphans the artifact rows, their
		attached private Files, and the on-disk ``code_execution/<key>``
		directory. This deletes them instead of merely clearing the link.
		"""
		from huf.ai.context_artifacts import delete_conversation_artifacts

		delete_conversation_artifacts(self.name)
