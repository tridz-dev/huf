# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Export a document Artifact's markdown content as a downloadable PDF/DOCX/HTML file.

Reuses the conversation-ownership check from ``huf.ai.artifact_api`` — a
caller must own the artifact's conversation (or hold System Manager) to
export it, exactly as for reading it.

Rendering pipeline: markdown -> sanitized HTML (``artifacts.render.html``) ->
PDF/DOCX bytes (``artifacts.render.pdf`` / ``artifacts.render.docx``). Each
export is saved as a private Frappe File attached to the Artifact; a stale
File from a prior export is deleted first so re-export after a content edit
always reflects the current artifact content rather than a cached copy.
"""

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

from huf.ai.artifact_api import _check_conversation_access
from huf.ai.artifacts.render.docx import html_to_docx
from huf.ai.artifacts.render.html import render_document_html
from huf.ai.artifacts.render.pdf import html_to_pdf

#: Supported export formats and how to turn rendered HTML into file bytes.
_FORMATS = ("pdf", "docx", "html")

#: Artifact types whose content is markdown source the render pipeline can consume.
_EXPORTABLE_ARTIFACT_TYPES = ("document", "markdown")


@frappe.whitelist()
def export_artifact(name: str, format: str) -> dict:
	"""Export an Artifact as pdf, docx, or html. Returns {"file_url": str}."""
	if not name:
		frappe.throw(_("Artifact name is required"), frappe.ValidationError)

	if format not in _FORMATS:
		frappe.throw(
			_("Unsupported export format: {0}. Must be one of {1}.").format(format, ", ".join(_FORMATS)),
			frappe.ValidationError,
		)

	artifact = frappe.get_doc("Artifact", name)

	_check_conversation_access(artifact.conversation)

	if artifact.artifact_type not in _EXPORTABLE_ARTIFACT_TYPES:
		frappe.throw(
			_("Artifact type {0} cannot be exported — only document/markdown artifacts are supported.").format(
				artifact.artifact_type
			),
			frappe.ValidationError,
		)

	html = render_document_html(artifact.content, title=artifact.title or artifact.name)

	if format == "html":
		rendered_bytes = html.encode("utf-8")
	elif format == "pdf":
		rendered_bytes = html_to_pdf(html)
	else:
		rendered_bytes = html_to_docx(html)

	_delete_existing_export(name, format)

	file_doc = save_file(f"{artifact.name}.{format}", rendered_bytes, "Artifact", name, is_private=True)

	return {"file_url": file_doc.file_url, "format": format}


def _delete_existing_export(artifact_name: str, format: str) -> None:
	"""Remove any previously exported File for this (artifact, format) pair, if any.

	A caller may re-export after editing the artifact's content, so any stale
	File for the same (artifact, format) pair must go before saving the fresh
	one — otherwise a naive re-save could leave two File rows, or callers
	could observe stale content. Always regenerating (rather than trying to
	match content hashes) keeps this correctness-first.

	Matched by extension rather than the exact requested file_name: Frappe's
	save_file() gives private files (is_private=True) a randomized on-disk
	name for URL-guessing protection, so the "<artifact_name>.<format>" name
	passed to save_file is never actually what ends up stored in the File
	doctype's own file_name field either - only the extension survives.
	`format` is validated against a fixed whitelist before this is called, so
	the LIKE pattern below is not attacker-controlled.
	"""
	existing = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Artifact",
			"attached_to_name": artifact_name,
			"file_name": ["like", f"%.{format}"],
		},
		fields=["name"],
	)
	for row in existing:
		frappe.delete_doc("File", row.name, ignore_permissions=True, force=True)
