# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""HUF Document: a durable, shareable, hierarchical workspace document.

Default access is owner + explicit DocShare (no workspace-wide role read).
"""

import frappe
from frappe import _
from frappe.model.document import Document


class HUFDocument(Document):
	def validate(self):
		self.title = (self.title or "").strip()
		if not self.title:
			frappe.throw(_("Title is required"), frappe.ValidationError)
		self._check_parent_cycle()
		self._check_parent_readable()
		# body_html is a server-side render cache written only by get_document_html
		# (via db.set_value, bypassing validate). Any save through the controller or
		# REST discards whatever the client sent; the cache regenerates lazily.
		self.body_html = None

	def _check_parent_readable(self):
		if not self.parent_document:
			return
		if not self.is_new() and not self.has_value_changed("parent_document"):
			return
		if not frappe.db.exists("HUF Document", self.parent_document) or not frappe.has_permission(
			"HUF Document", "read", self.parent_document
		):
			frappe.throw(
				_("You do not have permission to use the selected parent document"),
				frappe.ValidationError,
			)

	def _check_parent_cycle(self):
		if not self.parent_document:
			return
		if self.parent_document == self.name:
			frappe.throw(_("A document cannot be its own parent"), frappe.ValidationError)
		seen = set()
		current = self.parent_document
		while current:
			if current == self.name:
				frappe.throw(_("Parent document would create a cycle"), frappe.ValidationError)
			if current in seen:
				break
			seen.add(current)
			current = frappe.db.get_value("HUF Document", current, "parent_document")

	def on_trash(self):
		count = frappe.db.count("HUF Document", {"parent_document": self.name})
		if count:
			frappe.throw(
				_("Cannot delete a document that has {0} child document(s). Move or delete them first.").format(count),
				frappe.ValidationError,
			)


def _is_system_manager(user):
	return "System Manager" in frappe.get_roles(user)


def get_permission_query_conditions(user=None):
	"""Non-System-Managers see only documents they own or that are shared with them."""
	user = user or frappe.session.user
	if user == "Administrator" or _is_system_manager(user):
		return ""
	u = frappe.db.escape(user)
	return (
		f"(`tabHUF Document`.`owner` = {u} or exists (select 1 from `tabDocShare` "
		f"where `tabDocShare`.`share_doctype` = 'HUF Document' "
		f"and `tabDocShare`.`share_name` = `tabHUF Document`.`name` "
		f"and `tabDocShare`.`user` = {u} and `tabDocShare`.`read` = 1))"
	)


def has_permission(doc, ptype=None, user=None, **kwargs):
	user = user or frappe.session.user
	if user == "Administrator" or _is_system_manager(user):
		return True
	if doc.owner == user:
		return True
	if ptype in (None, "read", "select"):
		return bool(
			frappe.db.exists(
				"DocShare",
				{"share_doctype": "HUF Document", "share_name": doc.name, "user": user, "read": 1},
			)
		)
	return None  # let framework (incl. DocShare write/share flags) decide
