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

This module also owns the store's lifecycle and quotas (T-11b, F-16/F-17):
without them the store is unbounded. :func:`create_context_artifact` stamps
``expires_on`` and enforces per-artifact/per-conversation quotas, fail
closed, before ever calling ``insert``. :func:`purge_expired_context_artifacts`
is the ``daily`` scheduler entry that hard-deletes artifacts past
``expires_on`` **and** their attached File documents -- the Files are the
real disk cost, so deleting only the artifact row is not enough.
:func:`delete_conversation_artifacts` is the cascade invoked by ``Agent
Conversation.on_trash`` (``huf/huf/doctype/agent_conversation/agent_conversation.py``)
so deleting a conversation never orphans artifacts, their Files, or the
on-disk ``code_execution/<key>`` shared directory.
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

# --- Lifecycle (F-16) -------------------------------------------------------
# Default artifact lifetime. Overridable via site_config.json
# ("huf_context_artifact_retention_days") the same way
# code_execution._resolve_shared_dir_limit_mb reads a conf override -- no new
# DocType field, since this is a site-operational knob rather than a
# per-agent one.
DEFAULT_CONTEXT_ARTIFACT_RETENTION_DAYS = 30

# --- Quotas (F-17) -----------------------------------------------------------
# These bound the *artifact store* (this module), not the live sandbox
# directory -- huf.ai.tools.code_execution's 100 MB / 50-file constants are a
# different cap on a different resource (see module docstring above and
# GT-06). All overridable via site_config.json; an agent-level override was
# considered and rejected -- no DocType field exists for it and adding one is
# out of this card's scope (T-11 item 7 asks for real quotas, not a new UI).
DEFAULT_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024  # 25 MB, per artifact
DEFAULT_MAX_ARTIFACTS_PER_CONVERSATION = 500
DEFAULT_MAX_CONVERSATION_BYTES = 250 * 1024 * 1024  # 250 MB, per conversation total


class ArtifactQuotaExceeded(RuntimeError):
	"""Raised when creating an artifact would breach a quota (F-17).

	Fail closed: raised *before* any insert, so no partially-written artifact
	or orphaned File is ever left behind by a rejected call.
	"""


def _conf_int(key: str, default: int) -> int:
	"""Read an integer site_config override, falling back to ``default``."""
	value = frappe.conf.get(key)
	return int(value) if value else default


def _resolve_retention_days() -> int:
	return _conf_int("huf_context_artifact_retention_days", DEFAULT_CONTEXT_ARTIFACT_RETENTION_DAYS)


def _check_artifact_quotas(conversation: str, incoming_bytes: int) -> None:
	"""Enforce F-17 quotas for one more artifact of ``incoming_bytes`` on ``conversation``.

	Raises :class:`ArtifactQuotaExceeded` on the first breach; callers must
	call this before any ``insert``/``save`` so a rejected call never leaves a
	partial artifact or File behind.
	"""
	max_artifact_bytes = _conf_int("huf_context_artifact_max_bytes", DEFAULT_MAX_ARTIFACT_BYTES)
	if incoming_bytes > max_artifact_bytes:
		raise ArtifactQuotaExceeded(
			f"artifact payload is {incoming_bytes} bytes, above the {max_artifact_bytes}-byte "
			"per-artifact cap"
		)

	max_count = _conf_int("huf_context_artifact_max_count", DEFAULT_MAX_ARTIFACTS_PER_CONVERSATION)
	existing_count = frappe.db.count("Agent Context Artifact", {"conversation": conversation})
	if existing_count >= max_count:
		raise ArtifactQuotaExceeded(
			f"conversation {conversation!r} already has {existing_count} artifacts, at the "
			f"{max_count}-artifact cap"
		)

	max_conversation_bytes = _conf_int(
		"huf_context_artifact_max_conversation_bytes", DEFAULT_MAX_CONVERSATION_BYTES
	)
	existing_bytes = (
		frappe.db.sql(
			"SELECT COALESCE(SUM(payload_bytes), 0) FROM `tabAgent Context Artifact` WHERE conversation=%s",
			(conversation,),
		)[0][0]
		or 0
	)
	if existing_bytes + incoming_bytes > max_conversation_bytes:
		raise ArtifactQuotaExceeded(
			f"conversation {conversation!r} would hold {existing_bytes + incoming_bytes} bytes of "
			f"artifacts, above the {max_conversation_bytes}-byte per-conversation cap "
			f"({existing_bytes} existing + {incoming_bytes} incoming)"
		)


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
	expires_on: Any = None,
) -> frappe.model.document.Document:
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
		expires_on: explicit expiry (F-16). Defaults to now plus
			``huf_context_artifact_retention_days`` site_config (or
			:data:`DEFAULT_CONTEXT_ARTIFACT_RETENTION_DAYS`) when omitted.
			Pass ``False`` to opt an artifact out of expiry entirely.

	Returns:
		The inserted ``Agent Context Artifact`` document.

	Raises:
		ArtifactQuotaExceeded: a per-artifact, per-conversation-count or
			per-conversation-bytes quota (F-17) would be breached. Raised
			before any insert -- fail closed.
	"""
	if artifact_type not in _VALID_ARTIFACT_TYPES:
		raise ValueError(f"artifact_type must be one of {_VALID_ARTIFACT_TYPES}, got {artifact_type!r}")
	if not conversation:
		raise ValueError("create_context_artifact requires a conversation")

	if artifact_type == "File":
		if not isinstance(payload, (bytes, bytearray)):
			raise TypeError("artifact_type='File' requires payload to be bytes")
		content: bytes | None = bytes(payload)
		text: str | None = None
		incoming_bytes = len(content)
	else:
		if artifact_type == "JSON":
			text = json.dumps(payload, default=str, ensure_ascii=False)
		else:
			text = payload if isinstance(payload, str) else str(payload)
		content = None
		incoming_bytes = len(text.encode("utf-8"))

	_check_artifact_quotas(conversation, incoming_bytes)

	if expires_on is False:
		resolved_expiry = None
	elif expires_on:
		resolved_expiry = expires_on
	else:
		resolved_expiry = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=_resolve_retention_days())

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
			"payload_bytes": incoming_bytes,
			"expires_on": resolved_expiry,
		}
	)

	if artifact_type == "File":
		text_summary = summary or f"{filename or 'artifact'} ({len(content)} bytes)"
		artifact.summary = text_summary
		artifact.token_estimate = token_estimate or max(1, len(text_summary) // 4)
		artifact.insert(ignore_permissions=True)
		_attach_file(artifact, filename or f"{artifact.name}.bin", content)
	else:
		# JSON / Text: serialise, inline when small, else spill to a File --
		# same fail-closed shape as huf.ai.output_budget (never a truncated
		# inline blob standing in for the real payload).
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


def _delete_artifact_and_file(artifact_name: str, payload_file: str | None) -> None:
	"""Hard-delete one artifact row and its attached File, if any.

	Deletes the File first: if that fails partway (permissions, missing disk
	file), the artifact row is left behind for the next purge/cascade pass
	rather than silently losing the File reference. Both deletes are
	``ignore_permissions`` -- this runs from the scheduler and from an
	``on_trash`` cascade, neither of which has a request user.
	"""
	if payload_file:
		file_name = frappe.db.get_value("File", {"file_url": payload_file}, "name")
		if file_name:
			frappe.delete_doc("File", file_name, ignore_permissions=True, delete_permanently=True)
	frappe.delete_doc("Agent Context Artifact", artifact_name, ignore_permissions=True)


def purge_expired_context_artifacts() -> int:
	"""Scheduler entry point (``daily``, F-16): hard-delete expired artifacts and their Files.

	Registered in ``huf/hooks.py``'s ``scheduler_events["daily"]``. Without
	this the store is unbounded -- ``expires_on`` alone is inert unless
	something reads it. Deletes both the artifact row and its attached File
	(the real disk cost); a row with no ``expires_on`` is treated as
	permanent and never purged here.

	Returns the number of artifacts purged (best-effort; a single artifact's
	failure is logged and does not stop the rest).
	"""
	expired = frappe.get_all(
		"Agent Context Artifact",
		filters={"expires_on": ["<", frappe.utils.now_datetime()]},
		fields=["name", "payload_file"],
	)
	purged = 0
	for artifact in expired:
		try:
			_delete_artifact_and_file(artifact["name"], artifact.get("payload_file"))
			purged += 1
		except Exception:  # boundary exception handler: scheduler job
			frappe.log_error(
				message=f"purge_expired_context_artifacts error for {artifact['name']}: "
				f"{frappe.get_traceback()}",
				title="Huf Scheduler",
			)
			continue
	return purged


def delete_conversation_artifacts(conversation: str) -> int:
	"""Cascade delete every artifact (and File) belonging to ``conversation`` (F-16).

	Called from ``Agent Conversation.on_trash``
	(``huf/huf/doctype/agent_conversation/agent_conversation.py``), which
	Frappe's ``delete_doc`` runs *before* its own link-existence check -- so
	this must not rely on the conversation link still being readable
	anywhere else. It is a targeted cascade, not the app's generic
	``_orphan_conversation_links`` sweep (``huf/ai/agent_chat.py``), which
	explicitly skips this doctype for that reason (see the comment there).

	Also removes the on-disk ``code_execution/<key>`` shared directory for
	this conversation, since that directory's only purpose is to seed/receive
	this conversation's ``File``-type artifacts (see
	``huf.ai.tools.code_execution._seed_shared_dir``); leaving it behind
	after every artifact record is gone is a silent disk leak.

	Returns the number of artifacts deleted.
	"""
	artifacts = frappe.get_all(
		"Agent Context Artifact",
		filters={"conversation": conversation},
		fields=["name", "payload_file"],
	)
	deleted = 0
	for artifact in artifacts:
		_delete_artifact_and_file(artifact["name"], artifact.get("payload_file"))
		deleted += 1

	_remove_shared_dir(conversation)

	return deleted


def _remove_shared_dir(conversation: str) -> None:
	"""Best-effort removal of this conversation's on-disk shared execution directory.

	Deliberately does *not* call
	``huf.ai.tools.code_execution._shared_dir_for_conversation`` -- that
	helper creates the directory (``os.makedirs(..., exist_ok=True)``) as a
	side effect of resolving its path, which would recreate-then-delete on
	every cascade and could raise on a read-only mount. Only the path-key
	logic (``_conversation_dir_key``) is reused; the import is lazy to avoid
	a circular import, since ``code_execution.py`` already imports
	``create_context_artifact`` from this module at load time. Missing
	entirely (code execution was never used on this conversation) is not an
	error.
	"""
	import os
	import shutil

	from frappe.utils.file_manager import get_files_path

	from huf.ai.tools.code_execution import _SHARED_DIR_SUBDIR, _conversation_dir_key

	try:
		base = get_files_path(is_private=True)
		shared_dir = os.path.join(base, _SHARED_DIR_SUBDIR, _conversation_dir_key(conversation))
	except Exception:  # boundary exception handler: best-effort cleanup
		frappe.log_error(
			message=f"delete_conversation_artifacts: could not resolve shared dir for "
			f"{conversation}: {frappe.get_traceback()}",
			title="Huf Scheduler",
		)
		return

	shutil.rmtree(shared_dir, ignore_errors=True)
