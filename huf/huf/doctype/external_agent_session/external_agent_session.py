# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ExternalAgentSession(Document):
	def before_insert(self):
		if not self.session_token:
			self.session_token = frappe.generate_hash(length=40)

	def validate(self):
		from huf.ai.external.core.states import assert_transition, is_terminal

		previous = None if self.is_new() else self.get_doc_before_save()
		acked_seq = self.acked_seq or 0
		if acked_seq > (self.last_seq or 0) or (previous and acked_seq < (previous.acked_seq or 0)):
			frappe.throw(_("Invalid acknowledgement sequence."))

		if previous and previous.state != self.state:
			try:
				assert_transition(previous.state, self.state)
			except ValueError as exc:
				frappe.throw(str(exc), frappe.ValidationError)

		if is_terminal(self.state) and not self.ended_at:
			self.ended_at = now_datetime()

	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		if "System Manager" in frappe.get_roles(user):
			return True

		# Owners may read their own session; all mutations stay with System Manager.
		if permission_type in ("read", None) and self.user == user:
			return True

		return False
