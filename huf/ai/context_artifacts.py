# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Generic ``Agent Context Artifact`` producer and reader (T-11, F-14/F-15).

Before this module, the *only* code path that created an ``Agent Context
Artifact`` was the code-execution write-back in
``huf/ai/tools/code_execution.py``, which hardcodes ``artifact_type="File"``
and reads from a filesystem path. The ``JSON`` and ``Text`` values the
``artifact_type`` enum declares were never produced by anything, and nothing
ever told the model an artifact existed (see GT-06 in
``Tracks/safwan-erooth.DeterministicAgent/PLAN.md``).

:func:`create_context_artifact` is the one place that should insert an
``Agent Context Artifact`` from now on: it is usable from any tool or budget
"spill" callback (see ``huf.ai.output_budget``), supports all three
``artifact_type`` values, and — unless told not to — writes the ``Agent
Message`` handle (``reference_doctype="Agent Context Artifact"``,
``context_policy="include_reference"``) that makes the artifact visible to
the model. Without that message, an artifact is invisible: the LLM has no
handle to ask ``get_result_context`` for.

:func:`read_context_artifact_payload` is the matching read side used by
``huf.ai.sdk_tools.handle_get_result_context`` (F-12): it knows how to pull
content back out of ``payload_file`` (the File-backed case, which is what
every artifact that has ever existed in production actually is) as well as
inline ``payload_json``, with bounded offset/limit/slice arguments so a
drill-down read can never itself become an unbounded payload.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils.file_manager import save_file

# Above this many characters, a JSON/Text payload is spilled to a File
# instead of stored inline in payload_json -- mirrors
# code_execution.ARTIFACT_TEXT_INLINE_BYTES so both producers agree on what
# "small enough to inline" means.
INLINE_PAYLOAD_CHAR_LIMIT = 8000

_VALID_ARTIFACT_TYPES = ("JSON", "Text", "File")


def create_context_artifact(
	conversation: str,
	agent_run: str | None = None,
	payload: Any = None,
	*,
	artifact_type: str = "JSON",
	summary: str | None = None,
	visibility: str = "user_visible",
	context_policy: str = "include_reference",
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	token_estimate: int | None = None,
	filename: str | None = None,
	emit_handle: bool = True,
) -> "frappe.model.document.Document":
	"""Create an ``Agent Context Artifact`` and (by default) a visible handle.

	Args:
		conversation: name of the owning ``Agent Conversation``. Required --
			this is what permission scoping (F-13) filters on.
		agent_run: optional ``Agent Run`` link.
		payload: the data to store. For ``artifact_type in ("JSON", "Text")``
			this is serialised inline when small, else spilled to an attached
			File (same fail-closed shape as a budget breach: never partially
			written). For ``artifact_type="File"`` pass raw ``bytes`` and this
			always attaches a File, matching the existing code-execution
			write-back behaviour.
		artifact_type: one of ``"JSON"``, ``"Text"``, ``"File"``.
		summary: short human/model-readable description. Falls back to a
			generated one when omitted.
		visibility: one of the ``Agent Context Artifact.visibility`` options.
		context_policy: policy used both on the artifact and (when
			``emit_handle``) the companion ``Agent Message``.
		reference_doctype / reference_name: optional link back to the record
			this artifact documents (e.g. an ``Agent Tool Call``).
		token_estimate: optional precomputed estimate; a cheap ``len(text)//4``
			estimate is used when omitted.
		filename: filename to attach under, when spilling to a File. Defaults
			to a name derived from the artifact.
		emit_handle: when True (default), also write the ``Agent Message``
			that surfaces this artifact's handle to the model (F-15). Set to
			False only when the caller emits its own handle message.

	Returns:
		The inserted ``Agent Context Artifact`` document.
	"""
	if artifact_type not in _VALID_ARTIFACT_TYPES:
		raise ValueError(f"artifact_type must be one of {_VALID_ARTIFACT_TYPES}, got {artifact_type!r}")
	if not conversation:
		raise ValueError("create_context_artifact requires a conversation")

	artifact = frappe.get_doc(
		{
			"doctype": "Agent Context Artifact",
			"conversation": conversation,
			"agent_run": agent_run,
			"artifact_type": artifact_type,
			"visibility": visibility,
			"context_policy": context_policy,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
	)

	if artifact_type == "File":
		if not isinstance(payload, (bytes, bytearray)):
			raise TypeError("artifact_type='File' requires payload to be bytes")
		content = bytes(payload)
		text_summary = summary or f"{filename or 'artifact'} ({len(content)} bytes)"
		artifact.summary = text_summary
		artifact.token_estimate = token_estimate or max(1, len(text_summary) // 4)
		artifact.insert(ignore_permissions=True)
		_attach_file(artifact, filename or f"{artifact.name}.bin", content)
	else:
		# JSON / Text: serialise, inline when small, else spill to a File --
		# same fail-closed shape as huf.ai.output_budget (never a truncated
		# inline blob standing in for the real payload).
		if artifact_type == "JSON":
			text = json.dumps(payload, default=str, ensure_ascii=False)
		else:
			text = payload if isinstance(payload, str) else str(payload)

		artifact.summary = summary or (text if len(text) <= 200 else text[:200] + "...")
		artifact.token_estimate = token_estimate or max(1, len(text) // 4)

		if len(text) <= INLINE_PAYLOAD_CHAR_LIMIT:
			artifact.payload_json = text
			artifact.insert(ignore_permissions=True)
		else:
			artifact.insert(ignore_permissions=True)
			ext = "json" if artifact_type == "JSON" else "txt"
			_attach_file(artifact, filename or f"{artifact.name}.{ext}", text.encode("utf-8"))

	if emit_handle:
		_emit_artifact_handle(artifact)

	return artifact


def _attach_file(artifact, filename: str, content: bytes) -> None:
	"""Attach ``content`` as a private File on ``artifact.payload_file``."""
	saved = save_file(filename, content, "Agent Context Artifact", artifact.name, is_private=True)
	file_url = getattr(saved, "file_url", None) or (saved.get("file_url") if isinstance(saved, dict) else None)
	if not file_url:
		raise ValueError(f"save_file returned no file_url for {filename!r}")
	artifact.payload_file = file_url
	artifact.save(ignore_permissions=True)


def _emit_artifact_handle(artifact) -> None:
	"""Write the ``Agent Message`` handle that makes ``artifact`` visible to the model.

	This is the fix for F-15: without a message carrying
	``reference_doctype="Agent Context Artifact"`` and
	``context_policy="include_reference"``, ``_message_to_context``
	(``huf/ai/conversation_manager.py:594``) never emits anything about the
	artifact and the model has no handle to hand to ``get_result_context``.
	"""
	if not artifact.conversation:
		return

	last_index = frappe.db.sql(
		"""
		SELECT MAX(conversation_index) as last_index
		FROM `tabAgent Message`
		WHERE conversation = %s
		""",
		(artifact.conversation,),
		as_dict=1,
	)
	next_index = (last_index[0].last_index or 0) + 1 if last_index else 1

	agent_name = frappe.db.get_value("Agent Conversation", artifact.conversation, "agent")

	message = frappe.get_doc(
		{
			"doctype": "Agent Message",
			"conversation": artifact.conversation,
			"role": "system",
			"content": artifact.summary or f"Context artifact {artifact.name} created.",
			"kind": "Status",
			"agent_run": artifact.agent_run,
			"agent": agent_name,
			"conversation_index": next_index,
			"record_kind": "artifact",
			"context_policy": "include_reference",
			"context_summary": artifact.summary,
			"reference_doctype": "Agent Context Artifact",
			"reference_name": artifact.name,
			"visibility": artifact.visibility,
			"token_estimate": artifact.token_estimate,
		}
	)
	message.insert(ignore_permissions=True)


def read_context_artifact_payload(
	doc,
	*,
	offset: int | None = None,
	limit: int | None = None,
) -> dict:
	"""Read ``doc`` (an ``Agent Context Artifact``) payload with bounded slicing.

	Fixes F-12: every artifact that exists in production is
	``artifact_type="File"`` with an empty ``payload_json``, so a reader that
	only ever looked at ``payload_json`` returned nothing. This reads
	``payload_file`` when present, else falls back to inline ``payload_json``.

	``offset``/``limit`` apply to *lines* of the underlying text (JSON
	payloads are pretty-printed one value per line by the producers above, so
	line slicing is meaningful for both JSON and Text artifacts without
	parsing the whole document into memory).

	Returns a dict: ``{"content": str, "total_lines": int, "offset": int,
	"limit": int|None, "truncated": bool}``. Never larger than
	``offset``..``offset+limit`` lines regardless of the source size.
	"""
	text = None

	if getattr(doc, "payload_file", None):
		file_doc = frappe.get_doc("File", {"file_url": doc.payload_file})
		with open(file_doc.get_full_path(), "rb") as fh:
			raw = fh.read()
		try:
			text = raw.decode("utf-8")
		except UnicodeDecodeError:
			return {
				"content": None,
				"total_lines": None,
				"offset": offset or 0,
				"limit": limit,
				"truncated": False,
				"error": "payload_file is binary and cannot be returned as text; "
				"download the attached File directly instead.",
			}
	elif getattr(doc, "payload_json", None):
		text = doc.payload_json

	if text is None:
		return {"content": "", "total_lines": 0, "offset": offset or 0, "limit": limit, "truncated": False}

	lines = text.splitlines()
	total_lines = len(lines)
	start = max(0, offset or 0)
	end = start + limit if limit else total_lines
	sliced = lines[start:end]

	return {
		"content": "\n".join(sliced),
		"total_lines": total_lines,
		"offset": start,
		"limit": limit,
		"truncated": end < total_lines,
	}
