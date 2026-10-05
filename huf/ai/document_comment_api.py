"""Whole-document comments for HUF Documents (plain text, no anchoring, no notifications)."""

import frappe
from frappe import _

from huf.huf.doctype.huf_document_comment.huf_document_comment import check_permission, clean_body

DOCTYPE = "HUF Document Comment"


def _to_bool(value) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes")
	return bool(value)


def _require_document(document):
	if not document or not frappe.db.exists("HUF Document", document):
		frappe.throw(_("Document not found"), frappe.DoesNotExistError)
	return document


def _require_parent_read(document):
	_require_document(document)
	if not check_permission(None, document, "read", frappe.session.user):
		frappe.throw(_("You do not have permission to access this document"), frappe.PermissionError)


def _load(name):
	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("Comment not found"), frappe.DoesNotExistError)
	return frappe.get_doc(DOCTYPE, name)


def _require(comment, ptype):
	if not check_permission(comment.owner, comment.document, ptype, frappe.session.user):
		frappe.throw(_("You do not have permission for this comment"), frappe.PermissionError)


def _items(rows):
	owners = {r.owner for r in rows}
	names = {}
	if owners:
		names = dict(frappe.get_all("User", filters={"name": ("in", list(owners))}, fields=["name", "full_name"], as_list=True))
	user = frappe.session.user
	can_write_doc = {}

	def _can_edit(r):
		if r.owner == user:
			return True
		if r.document not in can_write_doc:
			can_write_doc[r.document] = bool(frappe.has_permission("HUF Document", "write", r.document))
		return can_write_doc[r.document]

	return [
		{
			"name": r.name,
			"document": r.document,
			"body": r.body,
			"author": r.owner,
			"author_full_name": names.get(r.owner) or r.owner,
			"creation": str(r.creation),
			"resolved": bool(r.resolved),
			"can_edit": _can_edit(r),
		}
		for r in rows
	]


@frappe.whitelist()
def list_document_comments(document: str) -> list[dict]:
	_require_parent_read(document)
	rows = frappe.get_all(
		DOCTYPE,
		filters={"document": document},
		fields=["name", "document", "body", "owner", "creation", "resolved"],
		order_by="creation asc, name asc",
		ignore_permissions=True,
	)
	return _items(rows)


@frappe.whitelist()
def add_document_comment(document: str, body: str) -> dict:
	_require_parent_read(document)
	doc = frappe.get_doc({"doctype": DOCTYPE, "document": document, "body": clean_body(body)})
	doc.insert(ignore_permissions=True)
	return _items([doc])[0]


@frappe.whitelist()
def set_comment_resolved(name: str, resolved: bool) -> dict:
	comment = _load(name)
	_require(comment, "write")
	flag = _to_bool(resolved)
	comment.resolved = 1 if flag else 0
	comment.resolved_by = frappe.session.user if flag else None
	comment.resolved_on = frappe.utils.now_datetime() if flag else None
	comment.save(ignore_permissions=True)
	return _items([comment])[0]


@frappe.whitelist()
def delete_document_comment(name: str) -> dict:
	comment = _load(name)
	_require(comment, "delete")
	frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)
	return {"name": name}
