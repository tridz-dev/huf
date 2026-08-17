# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ConversationPin(Document):
	def validate(self):
		self.validate_duplicate_pin()
		if not self.pinned_at:
			self.pinned_at = now_datetime()

	def validate_duplicate_pin(self):
		"""Enforce a unique (user, conversation) pair.

		Frappe DocType JSON has no native composite unique constraint, so this
		is enforced here instead.
		"""
		existing = frappe.db.exists(
			"Conversation Pin",
			{
				"user": self.user,
				"conversation": self.conversation,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				frappe._("{0} has already pinned this conversation.").format(self.user),
				frappe.ValidationError,
			)
