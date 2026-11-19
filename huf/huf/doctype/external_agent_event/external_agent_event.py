# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ExternalAgentEvent(Document):
	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		if "System Manager" in frappe.get_roles(user):
			return True

		# Event owners may read the events of their own external agent session.
		if permission_type in ("read", None):
			if not self.session:
				return False
			owner = frappe.db.get_value("External Agent Session", self.session, "user")
			return bool(owner) and owner == user

		return False


def on_doctype_update():
	frappe.db.add_unique("External Agent Event", ["session", "seq"], constraint_name="unique_session_seq")
	frappe.db.add_index("External Agent Event", ["session", "idempotency_key"])
