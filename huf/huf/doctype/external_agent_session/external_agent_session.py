# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ExternalAgentSession(Document):
	def before_insert(self):
		if not self.session_token:
			self.session_token = frappe.generate_hash(length=40)

	def validate(self):
		if self.is_new():
			return

		previous = self.get_doc_before_save()
		if not previous:
			return

		old_state = previous.state
		new_state = self.state
		if old_state == new_state:
			return

		from huf.ai.external.states import assert_transition

		assert_transition(old_state, new_state)

	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		if "System Manager" in frappe.get_roles(user):
			return True

		# Owners may read their own session; all mutations stay with System Manager.
		if permission_type in ("read", None) and self.user == user:
			return True

		return False
