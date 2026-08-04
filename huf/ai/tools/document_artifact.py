# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Agent-facing tool handlers for document Artifact export and redlining.

These wrap huf.ai.artifact_export_api.export_artifact and
huf.ai.artifacts.ooxml.redline.apply_redline in the ``handle_xxx(**kwargs) -> str``
contract huf.ai.tools._registry entries expect: kwargs matching the tool's
declared parameters, a JSON string response shaped
``{"success": bool, ...}`` on every path - never a raised exception, since a
raised exception from a tool handler surfaces to the model as an opaque
error rather than a structured, actionable result.
"""

import json

import frappe


def handle_export_artifact(**kwargs) -> str:
	"""Export a document Artifact as pdf, docx, or html.

	Args (via kwargs):
		artifact_id (str): The Artifact's name/id.
		format (str): One of "pdf", "docx", "html".

	Returns:
		JSON string with success=True + file_url + format on success, or
		success=False + error on failure (including permission denial and
		an unsupported artifact_type, both of which are expected, recoverable
		conditions the model should be able to see and react to - not just a
		stack trace).
	"""
	artifact_id = (kwargs.get("artifact_id") or "").strip()
	export_format = (kwargs.get("format") or "").strip().lower()

	if not artifact_id or not export_format:
		return json.dumps({"success": False, "error": "Both 'artifact_id' and 'format' are required"})

	from huf.ai.artifact_export_api import export_artifact

	try:
		result = export_artifact(artifact_id, export_format)
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to export this artifact."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	return json.dumps({"success": True, "file_url": result["file_url"], "format": result["format"]})


def handle_redline_artifact(**kwargs) -> str:
	"""Apply tracked-changes edits to a document Artifact's DOCX export.

	This produces a NEW derived .docx file with the edits marked as Word
	tracked changes (insertions/deletions attributed to the given author) -
	it does not modify the Artifact's own canonical ``content`` field. The
	original artifact and its plain exports are unaffected.

	Args (via kwargs):
		artifact_id (str): The Artifact's name/id.
		edits (list[dict] | str): List of {"find": str, "replace": str} dicts,
			or a JSON-encoded string of the same (some tool-calling paths pass
			complex arguments as JSON text rather than native structures).
		author (str): Attribution for the tracked changes. Defaults to the
			current session user if not given.

	Returns:
		JSON string with success=True + file_url on success, or
		success=False + error on failure.
	"""
	artifact_id = (kwargs.get("artifact_id") or "").strip()
	edits = kwargs.get("edits")
	author = (kwargs.get("author") or "").strip() or frappe.session.user

	if not artifact_id:
		return json.dumps({"success": False, "error": "'artifact_id' is required"})

	if isinstance(edits, str):
		try:
			edits = json.loads(edits)
		except (TypeError, ValueError):
			return json.dumps({"success": False, "error": "'edits' must be a list of {find, replace} dicts or valid JSON encoding one"})

	if not isinstance(edits, list) or not edits:
		return json.dumps({"success": False, "error": "'edits' must be a non-empty list of {find, replace} dicts"})

	from huf.ai.artifact_api import _check_conversation_access
	from huf.ai.artifacts.ooxml.redline import apply_redline
	from huf.ai.artifacts.render.docx import html_to_docx
	from huf.ai.artifacts.render.html import render_document_html
	from frappe.utils.file_manager import save_file

	try:
		artifact = frappe.get_doc("Artifact", artifact_id)
		_check_conversation_access(artifact.conversation)

		if artifact.artifact_type not in ("document", "markdown"):
			return json.dumps({"success": False, "error": f"Artifact type {artifact.artifact_type} cannot be redlined - only document/markdown artifacts are supported."})

		html = render_document_html(artifact.content, title=artifact.title or artifact.name)
		base_docx = html_to_docx(html)
		redlined_docx = apply_redline(base_docx, edits, author=author)

		# Redlined exports are a distinct derived file, named "<id>.redline.docx"
		# so they never collide with (or get silently overwritten by) the plain
		# ".docx" export _delete_existing_export/export_artifact manage.
		#
		# Matched for deletion by "%redline%" rather than the exact
		# "%.redline.docx" suffix: Frappe's save_file() -> get_file_name()
		# inserts a 6-char collision-avoidance hash immediately before the
		# final extension whenever a File with the exact requested name
		# already exists (frappe/utils/file_manager.py) - so after the first
		# redline export, the stored file_name becomes something like
		# "<id>.redline<hash6>.docx", not "<id>.redline.docx" verbatim. Since
		# that insertion point is always right before the LAST dot, "redline"
		# itself (which sits in the name's partial/stem portion, not the
		# extension) survives as a substring regardless of how many times
		# this collision-avoidance has fired - a plain "%.redline.docx"
		# suffix match does not, and silently stops matching after the first
		# collision, letting redline exports accumulate unbounded.
		file_name = f"{artifact.name}.redline.docx"
		existing = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Artifact", "attached_to_name": artifact.name, "file_name": ["like", "%redline%.docx"]},
			fields=["name"],
		)
		for row in existing:
			frappe.delete_doc("File", row.name, ignore_permissions=True, force=True)

		file_doc = save_file(file_name, redlined_docx, "Artifact", artifact.name, is_private=True)
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to redline this artifact."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	return json.dumps({"success": True, "file_url": file_doc.file_url})
