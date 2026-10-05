# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""HUF Document Comment: a plain-text, whole-document comment.

Access is derived from the parent HUF Document (see has_permission); there are
no role rows besides System Manager.
"""

import frappe
from frappe import _
from frappe.model.document import Document
import re

MAX_BODY_LENGTH = 5000


_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# A tag is a name followed only by name=value attributes, so prose like "a<b and c>d"
# (valueless words after the name) is not treated as markup.
_TAG_RE = re.compile(
	r"</?[A-Za-z][A-Za-z0-9-]*(?:\s+[\w:.-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>\"']+))*\s*/?>"
)


def strip_markup(text: str) -> str:
	"""Remove real HTML only (script/style blocks with content, comments, tags).

	A bare "<" or ">" in prose such as "a<b and c>d" is preserved.
	"""
	text = _BLOCK_RE.sub("", text)
	text = _COMMENT_RE.sub("", text)
	return _TAG_RE.sub("", text)


def clean_body(body) -> str:
	text = strip_markup(str(body or "")).strip()
	if not text:
		frappe.throw(_("Comment cannot be empty"), frappe.ValidationError)
	if len(text) > MAX_BODY_LENGTH:
		frappe.throw(
			_("Comment is too long (max {0} characters)").format(MAX_BODY_LENGTH), frappe.ValidationError
		)
	return text


class HUFDocumentComment(Document):
	def validate(self):
		self.body = clean_body(self.body)


def _can_read_parent(parent, user):
	return bool(parent) and frappe.has_permission("HUF Document", "read", doc=parent, user=user)


def _can_write_parent(parent, user):
	return bool(parent) and frappe.has_permission("HUF Document", "write", doc=parent, user=user)


def check_permission(comment_owner, parent, ptype, user):
	"""Core rule set; comment_owner is None for a comment not yet created."""
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	if not frappe.db.exists("HUF Document", parent):
		return False
	is_author = comment_owner == user
	if ptype in (None, "read", "select", "create"):
		return _can_read_parent(parent, user)
	if ptype in ("write", "delete"):
		return is_author or _can_write_parent(parent, user)
	return False


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""
	from huf.huf.doctype.huf_document.huf_document import get_permission_query_conditions as doc_cond

	cond = doc_cond(user)
	if not cond:
		return ""
	return f"`tabHUF Document Comment`.`document` in (select `name` from `tabHUF Document` where {cond})"


def has_permission(doc, ptype=None, user=None, **kwargs):
	user = user or frappe.session.user
	return check_permission(doc.get("owner") if not doc.is_new() else None, doc.document, ptype, user)
