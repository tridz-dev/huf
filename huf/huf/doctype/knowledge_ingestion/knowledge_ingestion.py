# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

TERMINAL_STATUSES = ("Cancelled", "Completed", "Completed with Errors", "Failed")


class KnowledgeIngestion(Document):
	def validate(self):
		self.validate_source()
		self.apply_defaults()
		self.check_status_not_user_editable()

	def validate_source(self):
		if not self.knowledge_source:
			frappe.throw(_("Knowledge Source is required"))
		if not frappe.db.exists("Knowledge Source", self.knowledge_source):
			frappe.throw(_("Knowledge Source {0} does not exist").format(self.knowledge_source))

	def apply_defaults(self):
		if self.is_new():
			if not self.status:
				self.status = "Queued"
			if not self.submitted_by:
				self.submitted_by = frappe.session.user

	def check_status_not_user_editable(self):
		"""Ingestion status transitions are system-managed (bulk_api / bulk_runner).

		Internal callers set status via frappe.db.set_value, which bypasses
		validate(), so this only guards the desk form.
		"""
		if self.is_new():
			return
		db_status = frappe.db.get_value("Knowledge Ingestion", self.name, "status")
		if db_status and self.status != db_status:
			frappe.throw(_("Ingestion status is managed by the system and cannot be edited here"))
