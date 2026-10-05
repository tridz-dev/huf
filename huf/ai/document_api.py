"""Whitelisted API for HUF Document (workspace documents)."""

from collections import Counter

import frappe
from frappe import _

from huf.ai.artifact_api import _check_conversation_access

_MARKDOWN_TYPES = ("markdown", "document")


@frappe.whitelist()
def save_artifact_as_document(artifact: str) -> dict:
	"""Copy an Artifact into a HUF Document. Idempotent via ``source_artifact``."""
	if not artifact:
		frappe.throw(_("Artifact is required"), frappe.ValidationError)
	art = frappe.get_doc("Artifact", artifact)
	_check_conversation_access(art.conversation)

	language = (art.language or "").lower()
	if art.artifact_type == "html" or language == "html":
		frappe.throw(
			_("Only markdown documents can be saved to the workspace (HTML is not supported yet)."),
			frappe.ValidationError,
		)
	if art.artifact_type not in _MARKDOWN_TYPES:
		frappe.throw(_("Only markdown documents can be saved to the workspace."), frappe.ValidationError)

	existing = frappe.db.get_value(
		"HUF Document", {"source_artifact": art.name, "owner": frappe.session.user}, "name"
	)
	if existing:
		doc = frappe.get_doc("HUF Document", existing)
		doc.check_permission("write")
		doc.title = art.title or doc.title
		doc.body_markdown = art.content or ""
	else:
		doc = frappe.new_doc("HUF Document")
		doc.title = art.title or _("Untitled")
		doc.body_markdown = art.content or ""
		doc.source_artifact = art.name
		doc.source_conversation = art.conversation
		doc.created_by_agent = art.agent
	doc.save() if existing else doc.insert()
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist()
def list_documents(parent: str | None = None, q: str | None = None, limit: int = 100) -> list[dict]:
	"""List permission-filtered documents; ``q`` searches title/keywords/body (LIKE)."""
	limit = max(1, min(int(limit or 100), 500))
	filters = {}
	or_filters = None
	q = (q or "").strip()[:200]
	if q:
		escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
		like = f"%{escaped}%"
		or_filters = [
			["title", "like", like],
			["keywords", "like", like],
			["body_markdown", "like", like],
		]
	elif parent:
		filters["parent_document"] = parent
	else:
		# Roots: no parent, or a parent this user cannot read.
		readable = frappe.get_list("HUF Document", pluck="name", limit_page_length=0)
		or_filters = [["parent_document", "is", "not set"]]
		if readable:
			or_filters.append(["parent_document", "not in", readable])
		else:
			or_filters.append(["parent_document", "is", "set"])

	rows = frappe.get_list(
		"HUF Document",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "title", "parent_document", "summary", "modified"],
		order_by="sort_order asc, modified desc",
		limit_page_length=limit,
	)
	if not rows:
		return rows
	children = frappe.get_list(
		"HUF Document",
		filters={"parent_document": ["in", [r.name for r in rows]]},
		fields=["parent_document"],
		limit_page_length=0,
		pluck="parent_document",
	)
	counts = Counter(children)
	for r in rows:
		r["child_count"] = counts.get(r.name, 0)
		r["can_write"] = bool(frappe.has_permission("HUF Document", "write", r.name))
	return rows


@frappe.whitelist()
def get_document_html(name: str) -> str:
	"""Return rendered HTML for a document, caching it in ``body_html``."""
	if not name:
		frappe.throw(_("Document name is required"), frappe.ValidationError)
	doc = frappe.get_doc("HUF Document", name)
	doc.check_permission("read")
	if doc.body_html:
		return doc.body_html

	from huf.ai.artifacts.render.html import render_document_html

	html = render_document_html(doc.body_markdown or "", doc.title or "", "markdown")
	frappe.db.set_value("HUF Document", doc.name, "body_html", html, update_modified=False)
	return html


def _clean_title(title) -> str:
	title = (title or "").strip()
	if not title:
		frappe.throw(_("Title is required"), frappe.ValidationError)
	return title


def _check_parent_writable(parent: str | None):
	if not parent:
		return
	if not frappe.db.exists("HUF Document", parent):
		frappe.throw(_("Parent document not found"), frappe.ValidationError)
	if not frappe.has_permission("HUF Document", "write", parent):
		frappe.throw(_("You do not have permission to add pages under this document"), frappe.PermissionError)


@frappe.whitelist()
def create_workspace_document(title: str, parent: str | None = None) -> dict:
	"""Create an empty-body document owned by the caller, optionally under a writable parent."""
	title = _clean_title(title)
	parent = parent or None
	_check_parent_writable(parent)
	doc = frappe.new_doc("HUF Document")
	doc.title = title
	doc.parent_document = parent
	doc.insert()
	return {"name": doc.name, "title": doc.title, "parent_document": doc.parent_document}


@frappe.whitelist()
def rename_document(name: str, title: str) -> dict:
	"""Rename a document (write permission required)."""
	if not name:
		frappe.throw(_("Document name is required"), frappe.ValidationError)
	title = _clean_title(title)
	doc = frappe.get_doc("HUF Document", name)
	doc.check_permission("write")
	doc.title = title
	doc.save()
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist()
def move_document(name: str, parent: str | None = None) -> dict:
	"""Re-parent a document; ``parent=None`` moves it to the root."""
	if not name:
		frappe.throw(_("Document name is required"), frappe.ValidationError)
	parent = parent or None
	doc = frappe.get_doc("HUF Document", name)
	doc.check_permission("write")
	old_parent = doc.parent_document
	if (
		old_parent
		and doc.owner != frappe.session.user
		and frappe.db.exists("HUF Document", old_parent)
		and not frappe.has_permission("HUF Document", "write", old_parent)
	):
		frappe.throw(
			_("You do not have permission to move this document out of its current parent"),
			frappe.PermissionError,
		)
	_check_parent_writable(parent)
	doc.parent_document = parent
	doc.save()
	return {"name": doc.name, "parent_document": doc.parent_document}
