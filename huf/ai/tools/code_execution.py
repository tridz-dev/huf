"""Python code execution tool — dispatcher, RQ enqueue, and worker (Phase 3).

This module is the ``function_path`` target for an ``Agent Tool Function`` of
type ``Code Execution`` (mirroring the other ``App Provided`` tools in
``huf/ai/tools/_registry.py``). The LLM-facing entrypoint is :func:`run_python`.

Flow:
  1. :func:`run_python` validates the site/agent/profile gates, snapshots the
     Execution Profile, creates an ``Agent Tool Call`` audit record, and either
     enqueues execution (Auto Approve), parks it behind an
     ``Agent Execution Approval`` record (Ask Every Time), or rejects it
     (Never Allow).
  2. :func:`enqueue_execution` submits :func:`execute_job` to the dedicated
     ``code-execution`` RQ queue.
  3. :func:`execute_job` (the RQ worker) subprocess-launches the isolated
     interpreter via :func:`huf.ai.tools.execution_sandbox.run_sandboxed` and
     writes the measured outcome back onto the ``Agent Tool Call``.

The actual isolation boundary lives in ``execution_sandbox.py`` (which is
frappe-free). This module is the only place that touches Frappe state.

Running a worker for the queue (operator note)::

    bench --site <site> worker --queue code-execution

``huf/hooks.py`` does not need to declare the queue — ``frappe.enqueue(...,
queue="code-execution")`` is sufficient as long as a worker listens on it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from typing import Any

import frappe
from frappe.utils.data import add_to_date, now_datetime


def get_files_path(is_private: bool = True) -> str:
	return frappe.get_site_path("private" if is_private else "public", "files")

from huf.ai.context_artifacts import create_context_artifact
from huf.ai.tools.execution.broker import (  # noqa: F401
	_authorize_egress,
	_make_broker_handler,
	_rule_host_matches,
	_rule_port_matches,
)
from huf.ai.tools.execution_sandbox import (
	DEFAULT_MAX_OUTPUT_BYTES,
	DEFAULT_WALL_TIME_S,
	MAX_SHARED_DIR_FILES,
	RQ_WALL_GRACE_S,
	DirCapExceeded,
	ExecutionResult,
	check_dir_caps,
	diff_dir_snapshots,
	measure_dir,
	run_sandboxed,
	snapshot_dir,
)
from huf.permissions import has_capability

#: Tool name recorded on the audit record when the caller does not supply one.
_TOOL_NAME = "run_python"

#: How long an ``Ask Every Time`` approval stays valid before expiring.
_APPROVAL_TTL_HOURS = 24

#: Effective default for the per-conversation shared directory size cap (MB).
#: The Execution Profile doctype carries no shared-dir field (see the Phase 4b
#: report), so this constant is the profile-level default the plan refers to;
#: ``Agent.execution_shared_dir_limit_mb`` may only override it DOWNWARD.
DEFAULT_SHARED_DIR_LIMIT_MB = 100

#: Files at or under this size that decode as UTF-8 text are written back with
#: ``context_policy="include_summary"`` (text inlined into ``summary``);
#: larger or binary files get ``include_reference``. Mirrors the Agent
#: ``max_context_chars`` default (2000) — the codebase's existing threshold for
#: inlining tool output into context vs. referencing it.
ARTIFACT_TEXT_INLINE_BYTES = 2000

#: Subdirectory of the site's private files area holding per-conversation
#: shared directories (alongside the knowledge system's artifacts).
_SHARED_DIR_SUBDIR = "code_execution"

#: Subdirectory of the site's private files area holding one throwaway scratch folder per Flow
#: step (``huf_scratch/<flow run>/<node>``), removed as soon as the step ends and swept daily.
SCRATCH_SUBDIR = "huf_scratch"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_site_enabled() -> bool:
	"""Read the site kill switch ``huf_python_execution_enabled`` (default off)."""
	val = frappe.conf.get("huf_python_execution_enabled")
	if isinstance(val, bool):
		return val
	if val is None:
		return False
	if isinstance(val, (int, float)):
		return bool(val)
	return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _name_of(obj: Any) -> str | None:
	"""Return the Frappe document name for a doc-or-name argument (or None)."""
	if obj is None:
		return None
	return getattr(obj, "name", None) or str(obj)


def _as_agent_doc(agent_doc: Any) -> Any:
	"""Resolve ``agent_doc`` (Document or name) to an ``Agent`` document."""
	if hasattr(agent_doc, "doctype"):
		return agent_doc
	return frappe.get_doc("Agent", agent_doc)


def _sha256(code: str) -> str:
	return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


def _parse_json_field(value: Any, default):
	"""Normalize a Frappe JSON field that may arrive as dict/list or string."""
	if value is None or value == "":
		return default
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except (TypeError, ValueError):
		return default


def _build_profile_snapshot(profile) -> dict:
	"""Build an immutable, JSON-serializable snapshot of an Execution Profile.

	Stored verbatim on the ``Agent Tool Call`` so later edits to the profile do
	not retroactively change the audit meaning of a past call.
	"""
	permissions = []
	for row in profile.permissions or []:
		permissions.append(
			{
				"capability": row.capability,
				"reference_doctype": row.reference_doctype or None,
				"is_read_only": bool(row.is_read_only),
			}
		)

	return {
		"profile_name": profile.profile_name,
		"is_builtin": bool(profile.is_builtin),
		"approval_mode": profile.approval_mode,
		"filesystem_policy": profile.filesystem_policy,
		"network_policy": profile.network_policy or None,
		"allowed_modules": _parse_json_field(profile.allowed_modules, []),
		"permissions": permissions,
		"limits": {
			"max_wall_time_s": int(profile.max_wall_time_s or 0),
			"max_cpu_seconds": int(profile.max_cpu_seconds or 0),
			"max_memory_mb": int(profile.max_memory_mb or 0),
			"max_output_bytes": int(profile.max_output_bytes or 0),
		},
	}


def _capability_summary(profile) -> str:
	"""Comma-joined broker capabilities granted by the profile (for approvals)."""
	caps = [r.capability for r in (profile.permissions or []) if r.capability]
	return ", ".join(caps) if caps else "code_execution.run"


def _truncate(text: str | None, limit: int) -> str | None:
	if text is None:
		return None
	if len(text) <= limit:
		return text
	return text[:limit] + f"\n... [truncated; {len(text) - limit} chars omitted]"


# ---------------------------------------------------------------------------
# Shared directory — per-conversation workspace + artifact write-back (Phase 4b)
#
# When the profile's ``filesystem_policy`` is "Shared Directory", sandboxed
# code works inside a real per-conversation directory under the site's private
# files area. The directory is stable across executions of the same
# conversation (a later message sees an earlier message's output files), is
# seeded with the conversation's File artifacts before each run, is capped in
# size and file count before AND after each run, and new/changed files are
# written back as ``Agent Context Artifact`` records after each run. Every
# failure here fails CLOSED: the call is rejected (audit row marked Failed)
# rather than allowed to proceed with a degraded workspace.
# ---------------------------------------------------------------------------


def _conversation_dir_key(conversation_name: str) -> str:
	"""Filesystem-safe, collision-proof directory key for a conversation name."""
	name = str(conversation_name or "")
	safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name)[:64].strip("._")
	digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
	return f"{safe or 'conv'}-{digest}"


def _shared_dir_for_conversation(conversation_name: str) -> str:
	"""Resolve (creating on first use) the per-conversation shared directory.

	Lives under the site's private files area (via ``get_files_path``, the same
	helper the knowledge system uses) so it sits alongside uploaded attachments
	and inherits the site's private-file storage/backup conventions. Keyed by
	conversation id, so it is stable across executions of the same
	conversation; never deleted between calls (nor by this module at all).
	"""
	base = get_files_path(is_private=True)
	path = os.path.join(base, _SHARED_DIR_SUBDIR, _conversation_dir_key(conversation_name))
	os.makedirs(path, exist_ok=True)
	return path


def _resolve_shared_dir_limit_mb(agent: Any) -> int:
	"""Effective per-conversation shared-dir cap (MB) for an agent.

	Falls back to :data:`DEFAULT_SHARED_DIR_LIMIT_MB` (the effective profile
	default) when the agent sets no override. An agent-level override may only
	LOWER the cap (plan: "overridable down only") — a higher override is an
	invalid configuration and is REJECTED with a ValidationError rather than
	silently clamped.
	"""
	agent = _as_agent_doc(agent)
	override = getattr(agent, "execution_shared_dir_limit_mb", None)
	if not override:
		return DEFAULT_SHARED_DIR_LIMIT_MB
	override = int(override)
	if override > DEFAULT_SHARED_DIR_LIMIT_MB:
		frappe.throw(
			f"Shared Dir Limit (MB) on Agent '{agent.name}' is {override} MB, above the "
			f"{DEFAULT_SHARED_DIR_LIMIT_MB} MB default. Agent-level limits may only override "
			"the default downward; lower the agent value to proceed.",
			frappe.ValidationError,
		)
	return override


def _fail_call(call, message: str, *, limits_hit: bool) -> None:
	"""Mark the audit row Failed around a rejected call (fail closed)."""
	call.status = "Failed"
	call.exit_status = "Error"
	call.limits_hit = 1 if limits_hit else 0
	call.error_message = _truncate(message, 60000)
	call.save(ignore_permissions=True)


def _seed_shared_dir(conversation_name: str, shared_dir: str) -> int:
	"""Materialize the conversation's File artifacts into ``shared_dir``.

	Copy, never symlink: the sandbox blocks symlink escapes by design (a
	symlinked seed would be unreadable from inside the sandbox anyway), and a
	plain copy is storage-agnostic (local or object-storage-backed File
	records). Artifacts are applied oldest-first so the newest version of a
	name wins; content already present in the persistent directory is never
	overwritten — the live workspace is authoritative over historical
	artifacts. Returns the number of files materialized this pass. An
	unresolvable File record or an unsafe file name raises (fail closed: the
	caller rejects the call).
	"""
	artifacts = frappe.get_all(
		"Agent Context Artifact",
		filters={"conversation": conversation_name, "artifact_type": "File"},
		fields=["name", "payload_file", "creation"],
		order_by="creation asc",
	)
	seeded_this_pass: set = set()
	count = 0
	for artifact in artifacts:
		payload_file = artifact.get("payload_file")
		if not payload_file:
			continue
		file_id = frappe.db.get_value("File", {"file_url": payload_file}, "name")
		if not file_id:
			raise FileNotFoundError(
				f"seed artifact {artifact['name']}: no File record for {payload_file!r}"
			)
		file_doc = frappe.get_doc("File", file_id)
		raw_name = file_doc.file_name or ""
		base_name = os.path.basename(raw_name)
		if not base_name or base_name != raw_name or base_name in (".", ".."):
			raise ValueError(f"seed artifact {artifact['name']}: unsafe file name {raw_name!r}")
		target = os.path.join(shared_dir, base_name)
		if base_name not in seeded_this_pass and os.path.lexists(target):
			# Pre-existing live workspace content wins over historical artifacts.
			continue
		with open(file_doc.get_full_path(), "rb") as fh:
			content = fh.read()
		with open(target, "wb") as fh:
			fh.write(content)
		seeded_this_pass.add(base_name)
		count += 1
	return count


def _classify_artifact(name: str, content: bytes) -> tuple:
	"""Pick ``(context_policy, summary, token_estimate)`` for a written-back file.

	Small UTF-8 text (≤ ``ARTIFACT_TEXT_INLINE_BYTES``) is inlined into
	``summary`` with ``include_summary``; anything larger or binary gets
	``include_reference`` with a size note, so the model sees a handle rather
	than a blob.
	"""
	if len(content) <= ARTIFACT_TEXT_INLINE_BYTES:
		try:
			text = content.decode("utf-8")
		except UnicodeDecodeError:
			text = None
		if text is not None and "\x00" not in text:
			return "include_summary", text, max(1, len(text) // 4)
	summary = (
		f"{name} ({len(content)} bytes) — binary or above the "
		f"{ARTIFACT_TEXT_INLINE_BYTES}-byte inline threshold"
	)
	return "include_reference", summary, max(1, len(summary) // 4)


def _write_back_artifacts(call, shared_dir: str, names: list) -> tuple:
	"""Create one ``Agent Context Artifact`` per name; return ``(written, error)``.

	Each file is attached through Frappe's normal private-file path
	(``save_file(..., is_private=True)``, the same helper chat uploads use) and
	linked on ``payload_file``. Stops at the first storage error and reports it
	— fail closed: the caller marks the call Failed rather than silently
	accepting a partial write-back. Files unchanged since the pre-execution
	snapshot never reach this function (the diff happens in the caller), so
	pre-existing seed files are not re-artifacted.
	"""
	written = 0
	for name in names:
		path = os.path.join(shared_dir, name)
		try:
			with open(path, "rb") as fh:
				content = fh.read()
			context_policy, summary, token_estimate = _classify_artifact(name, content)
			# Delegates to the generic producer (huf.ai.context_artifacts) so this
			# write-back also emits the Agent Message handle that makes the
			# artifact visible to the model (F-15) -- previously nothing did.
			create_context_artifact(
				call.conversation,
				agent_run=call.agent_run,
				payload=content,
				artifact_type="File",
				summary=summary,
				context_policy=context_policy,
				token_estimate=token_estimate,
				filename=name,
			)
			written += 1
		except Exception as exc:  # noqa: BLE001 - report and stop (fail closed)
			frappe.log_error(
				title="Huf Code Execution",
				message=f"artifact write-back failed for {name!r} in {shared_dir}: {exc}",
			)
			return written, f"{type(exc).__name__}: {exc}"
	return written, None


def _prepare_shared_dir(call) -> dict | None:
	"""Resolve, cap-check, seed and snapshot the per-conversation shared dir.

	Returns a context dict for :func:`_finalize_shared_dir` when execution may
	proceed, else ``None`` after marking the audit row Failed. Fails closed on:
	missing conversation/agent context, an over-ceiling agent limit override,
	a pre-existing cap violation, or any seed/storage error.
	"""
	conversation = call.conversation
	if not conversation:
		_fail_call(
			call,
			"Shared Directory filesystem policy requires a conversation context; "
			"this tool call has none.",
			limits_hit=False,
		)
		return None

	agent_name = frappe.db.get_value("Agent Conversation", conversation, "agent")
	if not agent_name:
		_fail_call(
			call,
			f"Shared Directory filesystem policy cannot resolve the agent for "
			f"conversation {conversation!r}.",
			limits_hit=False,
		)
		return None

	try:
		limit_mb = _resolve_shared_dir_limit_mb(agent_name)
	except frappe.ValidationError as exc:
		_fail_call(call, str(exc), limits_hit=False)
		return None

	limit_bytes = limit_mb * 1024 * 1024
	try:
		shared_dir = _shared_dir_for_conversation(conversation)
		# Pre-dispatch cap check: the persistent dir may already be over cap
		# from earlier runs or uploads.
		check_dir_caps(shared_dir, limit_bytes, MAX_SHARED_DIR_FILES)
		_seed_shared_dir(conversation, shared_dir)
		# Seed materialization is bounded by the same caps.
		check_dir_caps(shared_dir, limit_bytes, MAX_SHARED_DIR_FILES)
		before = snapshot_dir(shared_dir)
	except DirCapExceeded as exc:
		_fail_call(
			call,
			f"Shared directory cap exceeded before execution: {exc}. No files were deleted; "
			"reduce the directory contents or raise the limit.",
			limits_hit=True,
		)
		return None
	except Exception as exc:  # noqa: BLE001 - storage/seed errors fail closed
		frappe.log_error(
			title="Huf Code Execution",
			message=f"shared dir preparation failed for {call.name}: {exc}",
		)
		_fail_call(
			call,
			f"Shared directory could not be prepared: {type(exc).__name__}: {exc}",
			limits_hit=False,
		)
		return None

	return {"dir": shared_dir, "before": before, "limit_bytes": limit_bytes}


def _finalize_shared_dir(call, ctx: dict) -> None:
	"""Post-execution shared-dir handling; runs for every outcome (``finally``).

	1. Measure + re-check the caps: an execution that leaves the directory over
	   its size/file-count cap fails the call with ``limits_hit=1``. Nothing is
	   deleted and no artifacts are written back in that case.
	2. Otherwise diff against the pre-execution snapshot (content-hash based)
	   and write each new/changed file back as an ``Agent Context Artifact``.
	3. Fold ``shared_dir_bytes`` / ``artifacts_written`` into the existing
	   ``resource_usage`` JSON (no new DocType fields).

	Never raises: a finalizer bug must not mask the run's own outcome — it
	marks the call Failed with the error and logs instead.
	"""
	try:
		total_bytes, _count = measure_dir(ctx["dir"])
		artifacts_written = 0
		failure = None
		try:
			check_dir_caps(ctx["dir"], ctx["limit_bytes"], MAX_SHARED_DIR_FILES)
		except DirCapExceeded as exc:
			failure = (
				f"Shared directory cap exceeded by execution output: {exc}. "
				"No artifacts were written back and no files were deleted."
			)
			call.limits_hit = 1
		if failure is None:
			after = snapshot_dir(ctx["dir"])
			new_names, changed_names = diff_dir_snapshots(ctx["before"], after)
			artifacts_written, artifact_error = _write_back_artifacts(
				call, ctx["dir"], new_names + changed_names
			)
			if artifact_error:
				failure = (
					f"Artifact write-back failed after {artifacts_written} file(s): "
					f"{artifact_error}"
				)
		if failure is not None:
			call.status = "Failed"
			call.error_message = _truncate(
				((call.error_message or "") + "\n" + failure).strip(), 60000
			)
		usage = call.resource_usage
		if isinstance(usage, str):
			usage = _parse_json_field(usage, {})
		if not isinstance(usage, dict):
			usage = {}
		usage["shared_dir_bytes"] = int(total_bytes)
		usage["artifacts_written"] = int(artifacts_written)
		call.resource_usage = usage
		call.save(ignore_permissions=True)
	except Exception as exc:  # noqa: BLE001 - finalizer must never mask the run outcome
		frappe.log_error(
			title="Huf Code Execution",
			message=f"shared dir finalization failed for {call.name}: {exc}",
		)


# ---------------------------------------------------------------------------
# E1 — Dispatcher (LLM-facing tool entrypoint)
# ---------------------------------------------------------------------------


def run_python(
	code: str,
	agent_doc: Any,
	conversation: Any = None,
	agent_run: Any = None,
	**kwargs: Any,
) -> dict:
	"""Dispatch a Python code execution request from an agent.

	Args:
		code: The Python source to execute. Never persisted on the audit
			record; only its SHA-256 (``code_ref``) is stored.
		agent_doc: The ``Agent`` document (or its name) invoking the tool.
		conversation: The ``Agent Conversation`` doc/name (for audit linkage).
		agent_run: The ``Agent Run`` doc/name (for audit linkage).
		**kwargs: May carry ``call_id``/``tool_call_id``/``tool_name`` from the
			tool framework.

	Returns:
		A JSON-serializable dict describing the dispatched/parked call.

	Raises:
		frappe.ValidationError: kill switch off / agent not enabled / profile
			disabled.
		frappe.PermissionError: user lacks ``code_execution.run`` or the
			profile policy is ``Never Allow``.
	"""
	# 1. Site kill switch (checked before any DB lookup, mirroring
	#    Frappe's ``server_script_enabled`` gate).
	if not _is_site_enabled():
		frappe.throw(
			"Python code execution is disabled on this site.",
			frappe.ValidationError,
		)

	# The user driving this request. Captured NOW and threaded to the RQ
	# worker, because the worker runs as a privileged/system user and every
	# broker call must impersonate the original requester instead.
	acting_user = frappe.session.user

	# 2. Per-user capability (defense-in-depth; also enforced at tool-offer
	#    time in ``huf.ai.tools.registry.PermissionAwareToolRegistry``).
	if not has_capability(acting_user, "code_execution.run"):
		frappe.throw(
			"You do not have permission to run Python code.",
			frappe.PermissionError,
		)

	# 3. Per-agent enable + profile.
	agent = _as_agent_doc(agent_doc)
	if not getattr(agent, "allow_code_execution", None) or not getattr(
		agent, "execution_profile", None
	):
		frappe.throw(
			"Code execution is not enabled for this agent.",
			frappe.ValidationError,
		)

	# 4. Profile must be enabled.
	profile = frappe.get_doc("Execution Profile", agent.execution_profile)
	if profile.disabled:
		frappe.throw(
			"The selected Execution Profile is disabled.",
			frappe.ValidationError,
		)

	# 4b. Shared Directory policy (Phase 4b): an agent-level shared-dir limit
	#     may only override the default downward. Reject an over-ceiling config
	#     at dispatch so no audit row is created for an invalid configuration.
	if profile.filesystem_policy == "Shared Directory":
		_resolve_shared_dir_limit_mb(agent)

	return _dispatch(
		code,
		profile,
		acting_user,
		{
			"agent_run": _name_of(agent_run),
			"conversation": _name_of(conversation),
			"tool": kwargs.get("tool_name") or _TOOL_NAME,
			"call_id": kwargs.get("call_id") or kwargs.get("tool_call_id"),
		},
	)


def _dispatch(
	code: str,
	profile: Any,
	acting_user: str,
	audit_links: dict,
	*,
	inputs: dict | None = None,
	flow_ref: dict | None = None,
	approval_ttl_hours: int | None = None,
	wall_cap_s: int | None = None,
) -> dict:
	"""Shared core of both entry points: audit row, approval parking, enqueue.

	The caller (``run_python`` for an agent, ``run_flow_code`` for a Flow step) has already
	enforced its own gates (site switch, capability, agent / flow switches, profile enabled).
	What is common is everything from the profile snapshot on:

	* snapshot the Execution Profile and hash the code (the raw code is never stored on the
	  audit row; only ``code_ref``);
	* create exactly one ``Agent Tool Call`` audit row, linked through ``audit_links``
	  (``agent_run`` / ``conversation`` / ``tool`` / ``call_id``);
	* ``Never Allow`` -> fail the row and raise ``PermissionError``;
	* ``Ask Every Time`` -> park behind an ``Agent Execution Approval`` (the resumable payload,
	  including ``inputs`` and ``flow_ref``, is held in Redis, never in the database);
	* ``Auto Approve`` -> enqueue.

	``inputs`` (flow path only) is JSON data handed to the code as the ``inputs`` variable;
	``flow_ref`` (``{"flow_run", "node_id"}``) tells the worker where to put the scratch folder
	and whom to nudge when the call finishes. ``wall_cap_s`` lowers the profile's wall limit for
	this one call.
	"""
	# 5/6. Snapshot + code hash (raw code is never stored on the audit row).
	snapshot = _build_profile_snapshot(profile)
	if wall_cap_s:
		# A Flow step may ask for less time than its profile allows, never more.
		limits = snapshot["limits"]
		limits["max_wall_time_s"] = min(int(limits.get("max_wall_time_s") or wall_cap_s), int(wall_cap_s))
	code_ref = _sha256(code)

	# 7. Create the audit record (Started). ``tool_args`` references the hash,
	#    never the raw code. ``ignore_permissions`` is used because the audit
	#    row is created by the trusted dispatcher on behalf of the acting user,
	#    who is not expected to hold write perm on ``Agent Tool Call``.
	call = frappe.get_doc(
		{
			"doctype": "Agent Tool Call",
			"agent_run": audit_links.get("agent_run"),
			"conversation": audit_links.get("conversation"),
			"tool": audit_links.get("tool") or _TOOL_NAME,
			"is_mcp_tool": 0,
			"tool_args": json.dumps({"code_ref": code_ref}),
			"status": "Started",
			"call_id": audit_links.get("call_id"),
			"execution_profile": profile.name,
			"execution_profile_snapshot": snapshot,
			"code_ref": code_ref,
		}
	)
	call.insert(ignore_permissions=True)

	approval_mode = profile.approval_mode

	# 8a. Never Allow — hard deny, no enqueue.
	if approval_mode == "Never Allow":
		call.status = "Failed"
		call.error_message = "Execution not permitted by profile policy."
		call.save(ignore_permissions=True)
		frappe.throw(
			"Execution not permitted by profile policy.",
			frappe.PermissionError,
		)

	# 8b. Ask Every Time — park behind an approval record, do NOT enqueue.
	if approval_mode == "Ask Every Time":
		ttl_hours = approval_ttl_hours or _APPROVAL_TTL_HOURS
		# ``ignore_permissions=True`` is intentional and security-relevant: the
		# dispatcher is a trusted internal path that has already enforced the
		# kill switch + ``code_execution.run`` capability + agent/profile gates,
		# and the requesting user is not expected to hold the
		# ``execution.approve`` capability that
		# ``Agent Execution Approval.has_permission`` requires for manual create.
		# Recording a decision on that record still requires
		# ``execution.approve`` / a designated approver (see ``_can_decide``), so
		# the user who triggered execution cannot self-approve.
		approval = frappe.get_doc(
			{
				"doctype": "Agent Execution Approval",
				"agent_tool_call": call.name,
				"requested_capability": _capability_summary(profile),
				"code_ref": code_ref,
				"status": "Pending",
				"expires_on": add_to_date(now_datetime(), hours=ttl_hours),
				"requested_by": acting_user,
			}
		)
		original_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			approval.insert(ignore_permissions=True)
		finally:
			frappe.set_user(original_user)

		# Hold the resumable dispatch payload (raw code + snapshot + the
		# original ``acting_user``) in Redis for as long as the approval is
		# actionable — neither the approval row nor the audit row stores raw
		# code, only ``code_ref``. Resolution (Phase 5): ``approve_execution()``
		# (huf.huf.doctype.agent_execution_approval) validates this hold and
		# calls ``enqueue_approved_execution()``, which finally dispatches
		# ``enqueue_execution(call.name, code, snapshot, acting_user=...)``
		# impersonating the ORIGINAL requester captured above — never the
		# approver. A lapsed hold fails closed (the approval lapses to
		# Expired); rejection/expiry finalize the audit row without enqueueing.
		stash_pending_execution(
			approval.name,
			code=code,
			profile_snapshot=snapshot,
			acting_user=acting_user,
			inputs=inputs,
			flow_ref=flow_ref,
			ttl_hours=ttl_hours,
		)

		# ``Agent Tool Call.status`` has no dedicated "waiting" option; "Queued"
		# is the closest available value, and the linked
		# ``Agent Execution Approval.status == "Pending"`` is the real
		# waiting-state signal. (Open question for review: add an explicit
		# "Waiting Approval" status in a later phase.)
		call.status = "Queued"
		call.save(ignore_permissions=True)

		return {
			"success": True,
			"status": "Pending Approval",
			"agent_tool_call": call.name,
			"approval": approval.name,
			"expires_on": approval.expires_on,
			"code_ref": code_ref,
			"message": "Execution paused pending approval.",
		}

	# 8c. Auto Approve (default) — enqueue immediately. The row is marked Queued first: a fast
	#     worker (or an in-process run) must not have its outcome overwritten by this write.
	call.status = "Queued"
	call.save(ignore_permissions=True)
	enqueue_execution(
		call.name, code, snapshot, acting_user=acting_user, inputs=inputs, flow_ref=flow_ref
	)

	return {
		"success": True,
		"status": "Queued",
		"agent_tool_call": call.name,
		"code_ref": code_ref,
	}


def run_flow_code(
	flow_run: Any,
	node: dict,
	code: str,
	profile_name: str,
	inputs: dict | None = None,
	timeout_s: int | None = None,
) -> dict:
	"""Dispatch the code of one published ``code.run`` Flow step.

	The caller (the Flow engine) has already checked both switches, the flow owner's
	capabilities and the step's size / profile rules (``huf.ai.flow.code_node``); the two gates
	every execution path shares are repeated here as defence in depth. ``code`` and
	``profile_name`` MUST come from the run's pinned definition, never from run input;
	``inputs`` is plain data for the code.

	Exactly one ``Agent Tool Call`` audit row is written (profile snapshot + code hash), linked to
	the step's ``Agent Run`` (and so to the Flow Run). Returns the dispatch dict of
	:func:`_dispatch` plus ``agent_run``; raises ``PermissionError`` / ``ValidationError`` with a
	plain message when the run is not allowed.
	"""
	from uuid import uuid4

	if not _is_site_enabled():
		frappe.throw("Python code execution is disabled on this site.", frappe.ValidationError)
	acting_user = frappe.session.user
	if not has_capability(acting_user, "code_execution.run"):
		frappe.throw("You do not have permission to run Python code.", frappe.PermissionError)

	profile = frappe.get_doc("Execution Profile", profile_name)
	if profile.disabled:
		frappe.throw("The selected Execution Profile is disabled.", frappe.ValidationError)
	if profile.filesystem_policy == "Shared Directory":
		frappe.throw(
			"A Shared Directory profile needs an agent conversation, which a Flow step does not have. "
			"Pick a profile with a scratch folder.",
			frappe.ValidationError,
		)

	from huf.ai.flow.engine import _create_flow_agent_run

	run_doc = _create_flow_agent_run(
		flow_run=flow_run,
		node=node,
		run_kind="tool",
		prompt=f"Execute code ({profile.name}), {len((code or '').encode('utf-8'))} bytes",
	)
	flow_ref = {"flow_run": flow_run.name, "node_id": node.get("id")}
	out = _dispatch(
		code,
		profile,
		acting_user,
		{
			"agent_run": run_doc.name,
			"conversation": getattr(flow_run, "conversation", None),
			"tool": _TOOL_NAME,
			"call_id": f"call_{uuid4().hex[:12]}",
		},
		inputs=inputs or {},
		flow_ref=flow_ref,
		wall_cap_s=timeout_s,
	)
	out["agent_run"] = run_doc.name
	return out


# ---------------------------------------------------------------------------
# E2 — RQ enqueue
# ---------------------------------------------------------------------------


def enqueue_execution(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None = None,
	inputs: dict | None = None,
	flow_ref: dict | None = None,
) -> None:
	"""Enqueue :func:`execute_job` on the ``code-execution`` RQ queue.

	The job ``timeout`` is the profile's wall limit plus a fixed grace buffer so
	the RQ hard-timeout does not fire before the sandbox's own wall-clock kill.

	``acting_user`` is the session user captured at dispatch time. The worker
	impersonates it for every broker call — the worker itself runs as a
	privileged/system user and must never leak that identity into the broker.
	When it is missing the broker denies every call (fail closed).

	A Flow step (``flow_ref`` set) goes to the queue named by the site config
	``huf_flow_code_queue`` (default ``long``, which every standard deployment already works), and
	is enqueued only after the caller's transaction commits, so the run is already parked in
	``Waiting Code`` when the worker finishes. ``inputs`` is plain JSON data for the code.
	"""
	limits = (profile_snapshot or {}).get("limits") or {}
	wall = int(limits.get("max_wall_time_s") or DEFAULT_WALL_TIME_S)

	kwargs = {}
	queue = "code-execution"
	if flow_ref:
		queue = str(frappe.conf.get("huf_flow_code_queue") or "long")
		kwargs["enqueue_after_commit"] = True
	frappe.enqueue(
		"huf.ai.tools.code_execution.execute_job",
		queue=queue,
		timeout=wall + RQ_WALL_GRACE_S,
		agent_tool_call_name=agent_tool_call_name,
		code=code,
		profile_snapshot=profile_snapshot,
		acting_user=acting_user,
		inputs=inputs,
		flow_ref=flow_ref,
		now=bool(getattr(frappe.flags, "in_test", False)),
		**kwargs,
	)


# ---------------------------------------------------------------------------
# E2b — Pending-approval hold (Phase 5)
#
# An ``Ask Every Time`` dispatch parks the call behind an
# ``Agent Execution Approval`` record instead of enqueueing. The raw ``code``
# and the ``acting_user`` are deliberately NOT persisted on any DocType (the
# audit rows carry only ``code_ref``), so the resumable dispatch payload is
# held in Redis for exactly as long as the approval stays actionable
# (``expires_on`` == now + ``_APPROVAL_TTL_HOURS``; the hold TTL matches).
# ``approve_execution()`` resolves the hold and enqueues; a missing hold at
# approval time means the window lapsed (Redis TTL / eviction / restart) and
# the approval is treated as Expired. The hold is the ONLY source of the raw
# code and the original requester — a lost hold can never be substituted with
# the approver's identity or a re-supplied payload (fail closed).
# ---------------------------------------------------------------------------

#: Redis key prefix for parked (pending-approval) execution payloads.
_PENDING_EXECUTION_PREFIX = "huf_pending_execution"


class PendingExecutionExpired(Exception):
	"""The Redis hold for a parked execution lapsed before it was approved."""


def _pending_execution_key(approval_name: str) -> str:
	return f"{_PENDING_EXECUTION_PREFIX}:{approval_name}"


def stash_pending_execution(
	approval_name: str,
	*,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None,
	inputs: dict | None = None,
	flow_ref: dict | None = None,
	ttl_hours: int | None = None,
) -> None:
	"""Hold the resumable dispatch payload for a parked execution in Redis.

	Called by :func:`_dispatch` right after the ``Agent Execution Approval``
	row is inserted. The TTL mirrors the approval's ``expires_on`` so the hold
	never outlives the window in which the approval is actionable. The payload
	is the only place the raw code survives between park and approval; nothing
	is written to the database.
	"""
	payload = {
		"code": code,
		"code_ref": _sha256(code),
		"profile_snapshot": profile_snapshot or {},
		"acting_user": acting_user,
		"inputs": inputs,
		"flow_ref": flow_ref,
	}
	frappe.cache().set_value(
		_pending_execution_key(approval_name),
		json.dumps(payload, default=str),
		expires_in_sec=(ttl_hours or _APPROVAL_TTL_HOURS) * 3600,
	)


def load_pending_execution(approval_doc) -> dict:
	"""Load and validate the parked payload for an ``Agent Execution Approval``.

	Returns ``{"code", "profile_snapshot", "acting_user"}`` ready for
	:func:`enqueue_execution`. Fails closed at every step:
	  - missing/corrupt hold → :class:`PendingExecutionExpired` (the caller
	    lapses the approval to Expired);
	  - held code that no longer hashes to the approval's ``code_ref`` →
	    ``frappe.ValidationError`` (nothing is enqueued);
	  - missing/unresolvable ``acting_user`` → ``frappe.ValidationError``
	    (the approver's identity is NEVER substituted).
	"""
	raw = frappe.cache().get_value(_pending_execution_key(approval_doc.name))
	payload = None
	if raw:
		try:
			payload = json.loads(raw)
		except (TypeError, ValueError):
			payload = None
	if not isinstance(payload, dict):
		frappe.log_error(
			title="Huf Code Execution Approval",
			message=f"pending execution hold for approval {approval_doc.name} is missing or corrupt",
		)
		raise PendingExecutionExpired(approval_doc.name)

	code = payload.get("code")
	if not isinstance(code, str) or not code or _sha256(code) != (approval_doc.code_ref or ""):
		frappe.log_error(
			title="Huf Code Execution Approval",
			message=f"pending execution hold for approval {approval_doc.name} failed integrity check",
		)
		frappe.throw(
			"The parked execution payload failed its integrity check; refusing to enqueue.",
			frappe.ValidationError,
		)

	acting_user = payload.get("acting_user")
	if not isinstance(acting_user, str) or not acting_user:
		frappe.log_error(
			title="Huf Code Execution Approval",
			message=f"pending execution hold for approval {approval_doc.name} has no acting user",
		)
		frappe.throw(
			"The original requesting user for this execution is no longer resolvable; "
			"refusing to enqueue (the approver's identity is never substituted).",
			frappe.ValidationError,
		)

	snapshot = payload.get("profile_snapshot")
	inputs = payload.get("inputs")
	flow_ref = payload.get("flow_ref")
	return {
		"code": code,
		"profile_snapshot": snapshot if isinstance(snapshot, dict) else {},
		"acting_user": acting_user,
		"inputs": inputs if isinstance(inputs, dict) else None,
		"flow_ref": flow_ref if isinstance(flow_ref, dict) else None,
	}


def clear_pending_execution(approval_name: str) -> None:
	"""Drop the Redis hold for a parked execution (consumed, rejected, lapsed)."""
	frappe.cache().delete_key(_pending_execution_key(approval_name))


def enqueue_approved_execution(approval_doc, payload: dict) -> None:
	"""Enqueue the execution parked behind a just-approved ``approval_doc``.

	Called by ``approve_execution()`` only AFTER the approval row is saved as
	``Approved`` (the worker-side ``_approval_blocks`` safety net refuses to
	run otherwise). ``payload`` must come from :func:`load_pending_execution`
	(already validated); the hold is cleared once the job is enqueued.
	"""
	enqueue_execution(
		approval_doc.agent_tool_call,
		payload["code"],
		payload["profile_snapshot"],
		acting_user=payload["acting_user"],
		inputs=payload.get("inputs"),
		flow_ref=payload.get("flow_ref"),
	)
	clear_pending_execution(approval_doc.name)


# ---------------------------------------------------------------------------
# E3 — RQ worker entrypoint
# ---------------------------------------------------------------------------


def _approval_blocks(call_name: str) -> str | None:
	"""Return a blocking reason if an approval exists and is not Approved.

	Safety net for the Phase 5 approval→enqueue path: an execution that was
	parked must not run unless its ``Agent Execution Approval`` is "Approved".
	Auto-approve executions have no approval row, so they pass straight through.
	"""
	rows = frappe.get_all(
		"Agent Execution Approval",
		filters={"agent_tool_call": call_name},
		fields=["status"],
		limit=1,
	)
	if not rows:
		return None
	status = rows[0].status
	if status == "Approved":
		return None
	return f"Approval not granted (status: {status})."


def execute_job(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None = None,
	inputs: dict | None = None,
	flow_ref: dict | None = None,
) -> None:
	"""RQ worker: run the sandboxed interpreter and record the outcome.

	Runs inside a Frappe background worker process; the actual isolation happens
	in a fresh child interpreter spawned by :func:`run_sandboxed`. Broker RPCs
	from sandboxed code are authorized against ``profile_snapshot`` and executed
	impersonating ``acting_user`` (see :func:`_make_broker_handler`); when
	``acting_user`` is missing the broker denies every call (fail closed).

	The profile's ``filesystem_policy`` decides what (if anything) is mounted
	into the sandbox (Phase 4b):
	  * "Shared Directory" — the per-conversation shared directory is resolved,
	    cap-checked, seeded with the conversation's File artifacts, and
	    snapshotted before the run; after the run (always, via ``finally``) it
	    is cap-checked again and new/changed files are written back as
	    ``Agent Context Artifact`` records.
	  * "Scratch Only" — a throwaway directory, always deleted afterwards. For a Flow step
	    (``flow_ref``) it is ``<site>/private/files/huf_scratch/<flow run>/<node>``; for an agent a
	    temp directory.
	  * "None" — no filesystem access; ``run_sandboxed`` gets ``scratch_dir=None``.

	A Flow step (``flow_ref``) also gets ``inputs`` as the ``inputs`` variable, has its ``result``
	variable captured, and, whatever the outcome, schedules the continuation of the parked Flow Run
	once the audit row is final.
	"""
	try:
		_run_job(agent_tool_call_name, code, profile_snapshot, acting_user, inputs, flow_ref)
	finally:
		if flow_ref:
			from huf.ai.flow import code_node

			code_node.schedule_continue(flow_ref.get("flow_run"))


def _flow_scratch_dir(flow_ref: dict) -> str:
	"""The private scratch folder of one Flow step; created here, removed by the caller."""
	path = os.path.join(
		get_files_path(is_private=True),
		SCRATCH_SUBDIR,
		_conversation_dir_key(flow_ref.get("flow_run")),
		_conversation_dir_key(flow_ref.get("node_id")),
	)
	os.makedirs(path, exist_ok=True)
	return path


def _remove_flow_scratch(path: str) -> None:
	shutil.rmtree(path, ignore_errors=True)
	try:
		os.rmdir(os.path.dirname(path))  # the run's folder, once its last step folder is gone
	except OSError:
		pass


def _run_job(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
	acting_user: str | None,
	inputs: dict | None,
	flow_ref: dict | None,
) -> None:
	call = frappe.get_doc("Agent Tool Call", agent_tool_call_name)
	if flow_ref and call.status in ("Completed", "Failed"):
		return  # the step was already given up on (nobody picked it up in time): never run it late
	limits = (profile_snapshot or {}).get("limits") or {}
	max_output = int(limits.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)
	filesystem_policy = (profile_snapshot or {}).get("filesystem_policy") or "None"
	allowed_modules = (profile_snapshot or {}).get("allowed_modules") or []

	# Do not run if a (Phase 5) approval exists and was not granted.
	blocked = _approval_blocks(call.name)
	if blocked:
		call.status = "Failed"
		call.error_message = blocked
		call.exit_status = "Error"
		call.save(ignore_permissions=True)
		return

	call.status = "Started"
	call.save(ignore_permissions=True)

	broker_handler = _make_broker_handler(profile_snapshot, acting_user)

	scratch_dir = None
	flow_scratch = None
	shared_ctx = None
	if filesystem_policy == "Shared Directory":
		shared_ctx = _prepare_shared_dir(call)
		if shared_ctx is None:
			# Audit row already marked Failed (fail closed) — do not run.
			return
		mount_dir = shared_ctx["dir"]
	elif filesystem_policy == "Scratch Only":
		if flow_ref:
			flow_scratch = _flow_scratch_dir(flow_ref)
			mount_dir = flow_scratch
		else:
			scratch_dir = tempfile.mkdtemp(prefix="huf-exec-")
			mount_dir = scratch_dir
	else:  # "None": no filesystem mounted; the child exposes no file I/O
		mount_dir = None

	try:
		result: ExecutionResult = run_sandboxed(
			code,
			limits=limits,
			scratch_dir=mount_dir,
			allowed_modules=allowed_modules,
			broker_handler=broker_handler,
			broker_thread_start=broker_handler.thread_start,
			broker_thread_end=broker_handler.thread_end,
			inputs=(inputs or {}) if flow_ref else None,
			capture_result=bool(flow_ref),
		)
		_apply_result(
			call, result, max_output, broker_calls=broker_handler.call_counts, flow=bool(flow_ref)
		)
	except Exception as exc:  # noqa: BLE001 - never leave the row stuck at Started
		call.status = "Failed"
		call.exit_status = "Error"
		call.error_message = _truncate(
			f"{type(exc).__name__}: {exc}\n{frappe.get_traceback()}", 60000
		)
		call.limits_hit = 0
		call.save(ignore_permissions=True)
		frappe.log_error(
			title="Huf Code Execution",
			message=f"execute_job failed for {agent_tool_call_name}: {exc}",
		)
	finally:
		if shared_ctx is not None:
			_finalize_shared_dir(call, shared_ctx)
		if scratch_dir is not None:
			shutil.rmtree(scratch_dir, ignore_errors=True)
		if flow_scratch is not None:
			_remove_flow_scratch(flow_scratch)


def _apply_result(
	call,
	result: ExecutionResult,
	max_output: int,
	broker_calls: dict | None = None,
	flow: bool = False,
) -> None:
	"""Map an :class:`ExecutionResult` onto the ``Agent Tool Call`` audit row.

	A Flow step stores its whole step output on the row (``stdout``, ``result``, ``exit_status``,
	``truncated``) so the Flow Run can build the node output from the audit row alone.
	"""
	ok = result.exit_status == "Ok"

	call.status = "Completed" if ok else "Failed"
	call.exit_status = result.exit_status  # already Title Case (Ok/Timeout/...)
	call.limits_hit = 1 if result.limits_hit else 0
	call.resource_usage = {
		"cpu_s": round(result.cpu_s, 4),
		"wall_s": round(result.wall_s, 4),
		"mem_mb_peak": None if result.mem_mb_peak is None else round(result.mem_mb_peak, 2),
		"output_bytes": int(result.output_bytes),
		# Per-capability count of authorized broker calls (Phase 4a). Call
		# arguments and results are deliberately NOT recorded on the audit row.
		"broker_calls": {key: int(value) for key, value in sorted((broker_calls or {}).items())},
	}
	# Match the codebase convention of wrapping scalar tool output as
	# {"output": "..."} (see ``agent_integration.process_tool_call``).
	if flow:
		call.tool_result = {
			"stdout": result.stdout or "",
			"result": result.result,
			"exit_status": result.exit_status,
			"truncated": bool(result.output_truncated or result.result_truncated),
		}
	else:
		call.tool_result = {"output": _truncate(result.stdout, max_output) or ""}

	if not ok:
		call.error_message = _truncate(result.stderr, 60000)
	else:
		call.error_message = None

	call.save(ignore_permissions=True)
