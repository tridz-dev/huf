# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_DECIDED_STATUSES = ("Approved", "Rejected")
_TERMINAL_STATUSES = ("Approved", "Rejected", "Expired", "Consumed")


def is_allowed_status_transition(previous: str | None, current: str | None) -> bool:
	"""Return whether an approval may move from ``previous`` to ``current``.

	Pending may move to any status. Once decided, a status is final, except that an
	Approved approval may be Consumed exactly once.
	"""
	if previous == current or previous not in _TERMINAL_STATUSES:
		return True
	return previous == "Approved" and current == "Consumed"


class ExternalActionApproval(Document):
	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		# System Manager always has full access.
		if "System Manager" in frappe.get_roles(user):
			return True

		# Read is allowed to the user who owns the linked external session.
		# Decisions go through server API code that checks approver authority,
		# so every write path is closed to everyone else here.
		if permission_type == "read":
			return self._session_user() == user

		return False

	def validate(self):
		# Decisions are made through huf.ai.external.approvals.decide_approval, which checks
		# authority. The agent has no capability that reaches it, so the connected user
		# approving from Huf is the intended flow.
		if self.status in _DECIDED_STATUSES and not self.decided_by:
			self.decided_by = frappe.session.user

		if self.is_new():
			self._verify_args_hash()
			return

		previous = self.get_doc_before_save()
		if previous and not is_allowed_status_transition(previous.status, self.status):
			frappe.throw(_("Approval status cannot change once decided."))

	def _verify_args_hash(self):
		import json

		from huf.ai.external.core.idempotency import args_hash

		if self.args_hash != args_hash(json.loads(self.args or "{}")):
			frappe.throw(_("Approval does not match its arguments."))

	def _session_user(self) -> str | None:
		if not self.session:
			return None
		return frappe.db.get_value("External Agent Session", self.session, "user")
