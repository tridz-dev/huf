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


def handle_list_document_artifacts(**kwargs) -> str:
	"""List document/markdown artifacts in a conversation, for the model to
	discover an artifact_id before calling export_artifact/redline_artifact.

	Artifacts are only persisted after the message that created them is
	saved - a model cannot know the id of a document it is emitting in the
	CURRENT turn's <artifact type="document"> tag, since that tag has not
	been parsed into an Artifact row yet. This tool lets a LATER turn look
	up the id of a document created earlier in the same conversation
	(including one created just now, in the previous assistant turn) rather
	than requiring the user to paste an id by hand.

	Args (via kwargs):
		conversation_id (str): The conversation to list artifacts for.

	Returns:
		JSON string with success=True + artifacts (list of {id, title,
		created} for document/markdown-type artifacts only, newest first) on
		success, or success=False + error on failure.
	"""
	conversation_id = (kwargs.get("conversation_id") or "").strip()
	if not conversation_id:
		return json.dumps({"success": False, "error": "'conversation_id' is required"})

	from huf.ai.artifact_api import list_conversation_artifacts

	try:
		rows = list_conversation_artifacts(conversation_id)
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to list artifacts for this conversation."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	documents = [
		{"id": row["name"], "title": row.get("title") or row["artifact_type"], "created": str(row.get("creation") or "")}
		for row in rows
		if row.get("artifact_type") in ("document", "markdown")
	]
	documents.sort(key=lambda d: d["created"], reverse=True)

	return json.dumps({"success": True, "artifacts": documents})


def handle_show_artifact(**kwargs) -> str:
	"""Open a document Artifact in the user's right-side preview pane, without
	requiring the user to click anything.

	``conversation_id`` is injected automatically from the run context (see
	huf.ai.sdk_tools._merge_run_context) rather than supplied by the model, so
	it reflects the conversation the agent is actually running in - the model
	cannot point the pane at a conversation it does not otherwise have access
	to just by asserting a different id.

	Args (via kwargs):
		artifact_id (str): The Artifact's name/id. As with export_artifact and
			redline_artifact, a document's id is not known until the message
			that created it has been saved - use list_document_artifacts first
			if the id is not already known from an earlier turn.

	Returns:
		JSON string with success=True on success, or success=False + error on
		failure (including permission denial, a missing artifact, and an
		artifact that belongs to a different conversation) - never raises.
	"""
	artifact_id = (kwargs.get("artifact_id") or "").strip()
	run_conversation_id = (kwargs.get("conversation_id") or "").strip()

	if not artifact_id:
		return json.dumps({"success": False, "error": "'artifact_id' is required"})

	from huf.ai.artifact_api import _check_conversation_access

	try:
		artifact = frappe.get_doc("Artifact", artifact_id)

		# The conversation is derived from the ARTIFACT, never taken on the
		# model's word, and is not required in kwargs at all.
		#
		# Relying on the injected conversation_id was wrong: _merge_run_context
		# only reaches handlers on some execution paths, and on the path this
		# bench actually runs the tool arrived with no conversation_id, so
		# every call failed with "'conversation_id' is required" - while the
		# agent cheerfully told the user it had opened the panel. Deriving it
		# here works on every path and removes a parameter the model would
		# otherwise have to guess (the sibling list_document_artifacts tool
		# does ask the model for one, and was observed guessing it wrong).
		#
		# This is also the stricter choice: access is checked against the
		# artifact's OWN conversation, so an agent cannot reach a document
		# outside conversations this user may read, whatever it passes.
		conversation_id = artifact.conversation
		if not conversation_id:
			return json.dumps({"success": False, "error": "This artifact is not linked to a conversation."})

		_check_conversation_access(conversation_id)

		# When the run context DID supply a conversation, the artifact must
		# belong to it - an agent running in conversation A should not push a
		# pane open for the user's unrelated conversation B.
		if run_conversation_id and artifact.conversation != run_conversation_id:
			return json.dumps({"success": False, "error": "This artifact does not belong to the current conversation."})
	except frappe.DoesNotExistError:
		return json.dumps({"success": False, "error": f"No artifact found with id {artifact_id}"})
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to view this conversation."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	frappe.publish_realtime(
		event=f"conversation:{conversation_id}",
		message={
			"type": "open_artifact_pane",
			"artifact_id": artifact.name,
			"conversation_id": conversation_id,
			"artifact_type": artifact.artifact_type,
			"title": artifact.title or "",
		},
		user=frappe.session.user,
	)

	return json.dumps({"success": True, "artifact_id": artifact.name})


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


def _find_artifact_by_title(title: str, conversation_id: str = ""):
	"""Newest document/markdown artifact whose title matches, that the caller may read.

	An exact (case-insensitive) title match wins over a substring match. When the run's
	conversation is known the search is restricted to it, so "the report" means the report
	in THIS chat and not one from an unrelated conversation.
	"""
	from huf.ai.artifact_api import _check_conversation_access

	filters = {"artifact_type": ["in", ["document", "markdown"]]}
	if conversation_id:
		filters["conversation"] = conversation_id
	rows = frappe.get_all(
		"Artifact",
		filters=filters,
		fields=["name", "title", "conversation"],
		order_by="creation desc",
		limit=200,
	)
	wanted = title.strip().lower()
	ordered = [r for r in rows if (r.title or "").strip().lower() == wanted] + [
		r for r in rows if wanted in (r.title or "").strip().lower() and (r.title or "").strip().lower() != wanted
	]
	for row in ordered:
		try:
			_check_conversation_access(row.conversation)
		except frappe.PermissionError:
			continue
		return frappe.get_doc("Artifact", row.name)
	return None


def _announce_exported_file(conversation_id: str, file_url: str, file_name: str, export_format: str) -> None:
	"""Ask the owner's open client to show a freshly exported file in the artifacts pane.

	A distinct event type (``open_file_artifact``) rather than ``open_artifact_pane``:
	that one carries an Artifact id and existing clients read it as such. Needs the run's
	conversation (injected from the run context on most paths); without one there is no
	channel to publish on and nothing is sent. Never raises.
	"""
	try:
		if not conversation_id or not frappe.db.exists("Agent Conversation", conversation_id):
			return
		frappe.publish_realtime(
			event=f"conversation:{conversation_id}",
			message={
				"type": "open_file_artifact",
				"conversation_id": conversation_id,
				"file_url": file_url,
				"file_name": file_name,
				"format": export_format,
			},
			user=frappe.session.user,
			after_commit=True,
		)
	except Exception:
		frappe.log_error(title="Exported file open event failed", message=frappe.get_traceback())


def handle_export_document(**kwargs) -> str:
	"""Produce a downloadable PDF / DOCX / HTML / Markdown file from a document.

	Two ways to say WHAT to export, so a single request such as "create a docx
	report" works without the two-turn dance export_artifact needs (a document
	emitted in the CURRENT response has no id yet):

	- ``content`` (+ optional ``title``, ``language``): render this text directly.
	- ``artifact_id_or_title``: an Artifact id, or a title / part of a title of a
	  document already in the conversation.

	Returns ``success``, ``file_url`` (a private Frappe File), ``file_name``,
	``format`` and ``markdown_link`` - a ready-made ``[name](url)`` the agent
	relays so the chat shows a download link instead of the document pasted as text.
	Never raises: every failure is a structured ``success: False`` result.
	"""
	from huf.ai.artifact_export_api import _FORMATS, _render_bytes, _normalize_language, export_filename

	export_format = (kwargs.get("format") or "").strip().lower()
	target = (kwargs.get("artifact_id_or_title") or kwargs.get("artifact_id") or "").strip()
	content = kwargs.get("content") or ""
	title = (kwargs.get("title") or "").strip()
	language = (kwargs.get("language") or "markdown").strip().lower()
	conversation_id = (kwargs.get("conversation_id") or "").strip()

	if export_format not in _FORMATS:
		return json.dumps({"success": False, "error": f"'format' must be one of {', '.join(_FORMATS)}"})
	if not target and not content:
		return json.dumps({"success": False, "error": "Give either 'content' (the document text) or 'artifact_id_or_title'."})

	try:
		if content and not target:
			from frappe.utils.file_manager import save_file

			if len(content.encode("utf-8")) > 200_000:
				return json.dumps({"success": False, "error": "Content is too large to export (200 KB limit)."})
			data = _render_bytes(content, title or "Document", _normalize_language(language), export_format)
			file_name = export_filename(title, export_format)
			if conversation_id and frappe.db.exists("Agent Conversation", conversation_id):
				file_doc = save_file(file_name, data, "Agent Conversation", conversation_id, is_private=True)
			else:
				file_doc = save_file(file_name, data, None, None, is_private=True)
			frappe.db.commit()
			file_url = file_doc.file_url
		else:
			from huf.ai.artifact_export_api import export_artifact

			artifact = None
			if frappe.db.exists("Artifact", target):
				artifact = frappe.get_doc("Artifact", target)
			else:
				artifact = _find_artifact_by_title(target, conversation_id)
			if artifact is None:
				return json.dumps({
					"success": False,
					"error": f"No document artifact matches '{target}'. Pass the document text as 'content' instead.",
				})
			result = export_artifact(artifact.name, export_format)
			file_url = result["file_url"]
			file_name = export_filename(artifact.title or artifact.name, export_format)
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to export this document."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	_announce_exported_file(conversation_id, file_url, file_name, export_format)

	return json.dumps({
		"success": True,
		"file_url": file_url,
		"file_name": file_name,
		"format": export_format,
		"markdown_link": f"[{file_name}]({file_url})",
	})


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
		# See the matching comment in artifact_export_api.export_artifact: a
		# write made through a GET-style whitelisted invocation is rolled
		# back at request teardown unless committed explicitly. This tool
		# handler is normally called by the agent runtime, not raw HTTP GET,
		# but committing explicitly here is correct regardless of caller and
		# costs nothing extra.
		frappe.db.commit()
	except frappe.PermissionError:
		return json.dumps({"success": False, "error": "You do not have permission to redline this artifact."})
	except Exception as e:
		return json.dumps({"success": False, "error": str(e)})

	return json.dumps({"success": True, "file_url": file_doc.file_url})
