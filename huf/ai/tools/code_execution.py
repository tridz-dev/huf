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
import shutil
import tempfile
from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.tools.execution_sandbox import (
	DEFAULT_MAX_OUTPUT_BYTES,
	DEFAULT_WALL_TIME_S,
	RQ_WALL_GRACE_S,
	ExecutionResult,
	run_sandboxed,
)
from huf.permissions import has_capability

#: Tool name recorded on the audit record when the caller does not supply one.
_TOOL_NAME = "run_python"

#: How long an ``Ask Every Time`` approval stays valid before expiring.
_APPROVAL_TTL_HOURS = 24


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

	# 2. Per-user capability (defense-in-depth; also enforced at tool-offer
	#    time in ``tool_registry.PermissionAwareToolRegistry``).
	if not has_capability(frappe.session.user, "code_execution.run"):
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

	# 5/6. Snapshot + code hash (raw code is never stored on the audit row).
	snapshot = _build_profile_snapshot(profile)
	code_ref = _sha256(code)

	# 7. Create the audit record (Started). ``tool_args`` references the hash,
	#    never the raw code. ``ignore_permissions`` is used because the audit
	#    row is created by the trusted dispatcher on behalf of the acting user,
	#    who is not expected to hold write perm on ``Agent Tool Call``.
	call = frappe.get_doc(
		{
			"doctype": "Agent Tool Call",
			"agent_run": _name_of(agent_run),
			"conversation": _name_of(conversation),
			"tool": kwargs.get("tool_name") or _TOOL_NAME,
			"is_mcp_tool": 0,
			"tool_args": json.dumps({"code_ref": code_ref}),
			"status": "Started",
			"call_id": kwargs.get("call_id") or kwargs.get("tool_call_id"),
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
				"expires_on": add_to_date(now_datetime(), hours=_APPROVAL_TTL_HOURS),
			}
		)
		approval.insert(ignore_permissions=True)

		# ``Agent Tool Call.status`` has no dedicated "waiting" option; "Queued"
		# is the closest available value, and the linked
		# ``Agent Execution Approval.status == "Pending"`` is the real
		# waiting-state signal. (Open question for review: add an explicit
		# "Waiting Approval" status in a later phase.)
		call.status = "Queued"
		call.save(ignore_permissions=True)

		# TODO(phase5): when ``approve_execution()`` transitions the approval to
		# "Approved" (huf.huf.doctype.agent_execution_approval...), the
		# resolution path must call
		# ``huf.ai.tools.code_execution.enqueue_execution(call.name, code, snapshot)``
		# to finally dispatch the RQ job. The raw ``code`` is NOT persisted on
		# the ``Agent Tool Call`` (only ``code_ref`` is), so Phase 5 must
		# re-supply it at approval time — e.g. from the pending tool invocation
		# context, or by re-issuing the tool call once the approval is granted.
		# OPEN QUESTION: where the raw code is held between park and approval.

		return {
			"success": True,
			"status": "Pending Approval",
			"agent_tool_call": call.name,
			"approval": approval.name,
			"code_ref": code_ref,
			"message": "Execution paused pending approval.",
		}

	# 8c. Auto Approve (default) — enqueue immediately.
	enqueue_execution(call.name, code, snapshot)

	call.status = "Queued"
	call.save(ignore_permissions=True)

	return {
		"success": True,
		"status": "Queued",
		"agent_tool_call": call.name,
		"code_ref": code_ref,
	}


# ---------------------------------------------------------------------------
# E2 — RQ enqueue
# ---------------------------------------------------------------------------


def enqueue_execution(
	agent_tool_call_name: str,
	code: str,
	profile_snapshot: dict,
) -> None:
	"""Enqueue :func:`execute_job` on the ``code-execution`` RQ queue.

	The job ``timeout`` is the profile's wall limit plus a fixed grace buffer so
	the RQ hard-timeout does not fire before the sandbox's own wall-clock kill.
	"""
	limits = (profile_snapshot or {}).get("limits") or {}
	wall = int(limits.get("max_wall_time_s") or DEFAULT_WALL_TIME_S)

	frappe.enqueue(
		"huf.ai.tools.code_execution.execute_job",
		queue="code-execution",
		timeout=wall + RQ_WALL_GRACE_S,
		agent_tool_call_name=agent_tool_call_name,
		code=code,
		profile_snapshot=profile_snapshot,
		now=bool(getattr(frappe.flags, "in_test", False)),
	)


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
) -> None:
	"""RQ worker: run the sandboxed interpreter and record the outcome.

	Runs inside a Frappe background worker process; the actual isolation happens
	in a fresh child interpreter spawned by :func:`run_sandboxed`.
	"""
	call = frappe.get_doc("Agent Tool Call", agent_tool_call_name)
	limits = (profile_snapshot or {}).get("limits") or {}
	max_output = int(limits.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)

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

	scratch_dir = tempfile.mkdtemp(prefix="huf-exec-")
	try:
		result: ExecutionResult = run_sandboxed(
			code, limits=limits, scratch_dir=scratch_dir
		)
		_apply_result(call, result, max_output)
	except Exception as exc:  # noqa: BLE001 - never leave the row stuck at Started
		call.status = "Failed"
		call.exit_status = "Error"
		call.error_message = _truncate(
			f"{type(exc).__name__}: {exc}\n{frappe.get_traceback()}", 60000
		)
		call.limits_hit = 0
		call.save(ignore_permissions=True)
		frappe.log_error(
			f"execute_job failed for {agent_tool_call_name}: {exc}",
			"Huf Code Execution",
		)
	finally:
		shutil.rmtree(scratch_dir, ignore_errors=True)


def _apply_result(call, result: ExecutionResult, max_output: int) -> None:
	"""Map an :class:`ExecutionResult` onto the ``Agent Tool Call`` audit row."""
	ok = result.exit_status == "Ok"

	call.status = "Completed" if ok else "Failed"
	call.exit_status = result.exit_status  # already Title Case (Ok/Timeout/...)
	call.limits_hit = 1 if result.limits_hit else 0
	call.resource_usage = {
		"cpu_s": round(result.cpu_s, 4),
		"wall_s": round(result.wall_s, 4),
		"mem_mb_peak": None if result.mem_mb_peak is None else round(result.mem_mb_peak, 2),
		"output_bytes": int(result.output_bytes),
	}
	# Match the codebase convention of wrapping scalar tool output as
	# {"output": "..."} (see ``agent_integration.process_tool_call``).
	call.tool_result = {"output": _truncate(result.stdout, max_output) or ""}

	if not ok:
		call.error_message = _truncate(result.stderr, 60000)
	else:
		call.error_message = None

	call.save(ignore_permissions=True)
