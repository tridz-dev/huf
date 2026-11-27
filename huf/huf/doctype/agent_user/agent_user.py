# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

APPROVAL = "Agent Execution Approval"


class AgentUser(Document):
	"""A row under an ``Agent Execution Approval`` says who may decide it, so only server code writes it.

	``validate`` and ``on_trash`` run only when the row itself is addressed (a parent save never calls them), so they
	catch direct writes; the parent controller covers writes through the approval. Rows of other parents are untouched.
	"""

	def validate(self):
		if _is_approval(self.parenttype) or _is_approval(self._stored_parent()[0]):
			self._require_server_write()

	def on_trash(self):
		if _is_approval(self.parenttype):
			self._require_server_write()

	def before_discard(self):
		# discard writes docstatus with db_set, so ``validate`` never runs
		if _is_approval(self.parenttype):
			self._require_server_write()

	def db_update(self):
		# Saving any parent that names this row rewrites it by name and runs no child hook.
		parenttype, parent = self._stored_parent()
		if _is_approval(parenttype) and (self.parenttype, str(self.parent)) != (parenttype, parent):
			self._refuse()
		super().db_update()

	def _stored_parent(self) -> tuple:
		return (self.name and frappe.db.get_value(self.doctype, self.name, ["parenttype", "parent"])) or (None, None)

	def _require_server_write(self):
		from huf.ai.flow.runs.write_guard import require_server_write

		require_server_write(self)

	def _refuse(self):
		from huf.ai.flow.runs.write_guard import refuse

		refuse(self)


def _is_approval(parenttype) -> bool:
	"""Match as the database does: the collation ignores case, accents and trailing spaces, so a row stored under such
	a spelling is still loaded as an approver row."""
	return bool(parenttype) and frappe.db.get_value("DocType", {"name": str(parenttype)}, "name") == APPROVAL
