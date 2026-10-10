# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

HOST_FIELDS = ("execution_host", "host_device_id", "host_workspace_fingerprint", "host_label")
HOST_WRITE_FLAG = "huf_desktop_host_write"


def _host_value(value, fieldname):
	if value in (None, ""):
		return "server" if fieldname == "execution_host" else ""
	return value


class AgentConversation(Document):
	def validate(self):
		self._guard_desktop_host_fields()

	def _guard_desktop_host_fields(self):
		"""The host of a conversation is set by the server when a desktop creates it and is never
		editable afterwards (a conversation never migrates between host types). Only
		``huf.ai.desktop_sessions`` sets ``flags.huf_desktop_host_write``; every other write,
		including a web session's ``frappe.client.set_value`` on its own conversation, is refused."""
		if self.flags.get(HOST_WRITE_FLAG):
			return
		if self.is_new():
			changed = [f for f in HOST_FIELDS if _host_value(self.get(f), f) != _host_value(None, f)]
		else:
			before = self.get_doc_before_save()
			changed = [
				f
				for f in HOST_FIELDS
				if before is not None and _host_value(before.get(f), f) != _host_value(self.get(f), f)
			]
		if changed:
			frappe.throw(
				_("The desktop host of a conversation cannot be set or changed here."),
				frappe.PermissionError,
			)

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
