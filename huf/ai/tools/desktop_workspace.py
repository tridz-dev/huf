"""
Desktop workspace tools — 10 handlers for file operations and command execution
on the user's local machine via Huf Desktop.

All paths are workspace-relative POSIX strings. Parameter validation rejects
absolute paths, backslashes, NUL bytes, and paths over 1024 chars. Total params
must not exceed 512 KB.

Every handler returns the ``desktop_executor.dispatch`` result UNCHANGED:
``{ok, op, workspace, data | error{code,message}, truncated, duration_ms,
untrusted_content, note}``. The error code and the untrusted marking (set for
ws.info, fs.list, fs.read, fs.search, exec.run) therefore always reach the model.

Identity (``agent_run_id``, ``conversation_id``, ``call_id``, ``_dx_*``) is pinned by
``sdk_tools.create_function_tool`` and is never taken from the model: none of these
appear in the tool schemas, and the pinning code overwrites anything the model sends.

Each handler is split in two so blocking work stays off shared DB connections:
``handler.prepare(**kwargs)`` validates parameters and the run context (reads the
Agent Run) and MUST run on the loop/main thread; ``handler.execute(prepared)`` only
talks to Redis and runs in ``asyncio.to_thread``. Calling ``handler(**kwargs)``
does both in sequence (tests, plain callers).

Pin token (N8). The handlers refuse to run unless the call carries ``_dx_pin``, an HMAC
that only ``sdk_tools`` (the ``pin_run_context`` path of a Desktop-pinned agent run) can
mint, bound to the run, executor and user. Flows, procedures, ``tool_invocation.invoke_tool``
and direct API calls cannot mint it, so they cannot drive a desktop with self-chosen ids.

See PLAN.md §3.7-3.8 for limits and specifications.
"""

import functools
import hashlib
import hmac
import json
import os
import re
import unicodedata

import frappe
from frappe import _

# Limits from the spec (§3.7)
MAX_PATH_LENGTH = 1024
MAX_PARAMS_BYTES = 512 * 1024  # 512 KB
MAX_WRITE_CONTENT_BYTES = 256 * 1024  # 256 KB
MAX_FS_TIMEOUT_MS = 20000
DEFAULT_EXEC_TIMEOUT_SECONDS = 60
MIN_EXEC_TIMEOUT_SECONDS = 1
MAX_EXEC_TIMEOUT_SECONDS = 120


def _validate_path(path: str) -> str:
	"""Validate a workspace-relative POSIX path.

	Rejects:
	- Absolute paths (starting with /)
	- Paths with backslashes (Windows-style)
	- Paths with NUL bytes
	- Paths longer than 1024 chars
	- Empty paths

	- Leading/trailing whitespace, drive letters (C:), non-NFC text

	Converts to string to handle LLM stringification of numbers. This check is
	best-effort; the desktop enforces the real workspace boundary.
	"""
	path = str(path or "")

	if not path.strip():
		frappe.throw(_("Path cannot be empty."))

	if path != path.strip():
		frappe.throw(_("Paths must not start or end with whitespace."))

	if len(path) > MAX_PATH_LENGTH:
		frappe.throw(
			_("Path exceeds maximum length of {0} characters.").format(MAX_PATH_LENGTH)
		)

	if path.startswith("/"):
		frappe.throw(_("Absolute paths are not allowed. Use workspace-relative paths."))

	if "\\" in path:
		frappe.throw(_("Windows-style paths (backslashes) are not allowed. Use forward slashes."))

	if "\0" in path:
		frappe.throw(_("Paths with NUL bytes are not allowed."))

	if re.match(r"^[A-Za-z]:", path):
		frappe.throw(_("Drive-letter paths are not allowed. Use workspace-relative paths."))

	if unicodedata.normalize("NFC", path) != path:
		frappe.throw(_("Paths must be NFC-normalized."))

	return path


def _validate_params_size(params: dict) -> None:
	"""Reject if total params exceed 512 KB."""
	try:
		params_json = json.dumps(params)
		if len(params_json.encode("utf-8")) > MAX_PARAMS_BYTES:
			frappe.throw(
				_("Parameters exceed maximum size of {0} KB.").format(
					MAX_PARAMS_BYTES // 1024
				)
			)
	except Exception as e:
		if "exceed" not in str(e).lower():
			frappe.log_error(title="desktop_workspace: param size validation error")
		raise


def _parse_runtime_context(value) -> dict:
	"""Parse ``Agent Run.runtime_context`` (JSON string, dict, or empty) into a dict."""
	if isinstance(value, dict):
		return value
	if not value or not isinstance(value, (str, bytes)):
		return {}
	try:
		parsed = frappe.parse_json(value)
	except Exception:
		return {}
	return parsed if isinstance(parsed, dict) else {}


# Process-local secret: the token is minted and checked inside the same worker process
# (``on_invoke_tool`` -> ``prepare``), and is never persisted or sent anywhere.
_PIN_SECRET = os.urandom(32)


def issue_pin_token(agent_run_id, executor_id, user) -> str:
	"""HMAC binding a desktop tool call to (run, executor, user). Minted by ``sdk_tools`` only."""
	message = "\0".join(str(part or "") for part in (agent_run_id, executor_id, user)).encode("utf-8")
	return hmac.new(_PIN_SECRET, message, hashlib.sha256).hexdigest()


def _pin_token_valid(token, agent_run_id, executor_id, user) -> bool:
	if not token or not isinstance(token, str):
		return False
	return hmac.compare_digest(token, issue_pin_token(agent_run_id, executor_id, user))


def _validate_executor_context(
	_dx_executor_id: str,
	_dx_fingerprint: str,
	_dx_user: str,
	agent_run_id: str,
	_dx_pin: str = None,
) -> dict:
	"""Verify that the pinned executor context belongs to this run.

	Reads the Agent Run (main thread only: it touches the database) to confirm:
	- the call carries a valid ``_dx_pin`` token (only ``sdk_tools`` mints it for a pinned run)
	- the session user is the pinned user, or Administrator (the system context that
	  drains queued runs; the run OWNER is what carries the identity)
	- the run owner is _dx_user
	- runtime_context.desktop.executor_id matches _dx_executor_id
	- runtime_context.desktop.user is the run owner

	Returns the canonical dispatch ctx ``{executor_id, fingerprint, user, label}``
	built from the run's pinned desktop context.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Desktop tools are not available in guest sessions."))

	# N8: only a Desktop-pinned agent run may call these handlers.
	if not _pin_token_valid(_dx_pin, agent_run_id, _dx_executor_id, _dx_user):
		frappe.throw(
			_("Desktop tools can only be used by an agent run that is pinned to Huf Desktop."),
			frappe.PermissionError,
		)

	if frappe.session.user not in (_dx_user, "Administrator"):
		frappe.throw(
			_("Executor belongs to a different user."),
			frappe.PermissionError,
		)

	if not agent_run_id:
		frappe.throw(_("Agent run not found."), frappe.DoesNotExistError)

	# Load the run to verify ownership and executor context
	try:
		run = frappe.get_doc("Agent Run", agent_run_id)
	except frappe.DoesNotExistError:
		frappe.throw(_("Agent run not found."), frappe.DoesNotExistError)

	if run.owner != _dx_user:
		frappe.throw(
			_("Agent run belongs to a different user."),
			frappe.PermissionError,
		)

	# runtime_context is a JSON field: usually a string, sometimes already a dict.
	runtime_context = _parse_runtime_context(run.get("runtime_context"))
	if not runtime_context:
		frappe.throw(_("Desktop context not found on this run."))

	desktop_ctx = runtime_context.get("desktop")
	if not desktop_ctx or not isinstance(desktop_ctx, dict):
		frappe.throw(_("Desktop context not found on this run."))

	pinned_executor_id = desktop_ctx.get("executor_id")
	if pinned_executor_id != _dx_executor_id:
		frappe.throw(_("Executor ID mismatch with the pinned context."))

	if desktop_ctx.get("user") != run.owner:
		frappe.throw(
			_("The pinned desktop user is not the owner of this run."),
			frappe.PermissionError,
		)

	# Canonical ctx for desktop_executor.dispatch: {executor_id, fingerprint, user, label}.
	# The fingerprint is the one pinned on the run at send time (not the live one).
	ctx = {
		"executor_id": pinned_executor_id,
		"fingerprint": desktop_ctx.get("fingerprint") or _dx_fingerprint or None,
		"user": run.owner,
		"label": desktop_ctx.get("label"),
	}
	# The local-capability catalog pinned when the run started (server-owned: read from the
	# persisted run, never from a tool argument).
	if desktop_ctx.get("catalog_hash"):
		ctx["catalog_hash"] = desktop_ctx["catalog_hash"]
	# Origin ("desktop" | "remote") and the agent's desktop policy are honoured only from a pin the
	# server signed at run start. ``Agent Run.runtime_context`` is writable by a Huf User on insert,
	# so an unsigned or altered pin is REMOTE with no policy (the dispatcher then needs remote control
	# on for the desktop and the agent). ``device_id`` rides the same signature.
	from huf.ai.desktop_executor import verify_pin

	from huf.ai.desktop_executor import pin_is_fresh

	if verify_pin(desktop_ctx, run.get("conversation") or "", run) and pin_is_fresh(run):
		ctx["origin"] = desktop_ctx.get("origin") if desktop_ctx.get("origin") in ("desktop", "remote") else "remote"
		if desktop_ctx.get("agent_policy"):
			ctx["agent_policy"] = desktop_ctx["agent_policy"]
		if desktop_ctx.get("device_id"):
			ctx["device_id"] = desktop_ctx["device_id"]
		if desktop_ctx.get("origin_ip"):
			ctx["origin_ip"] = desktop_ctx["origin_ip"]
		if ctx["origin"] == "desktop":
			# Desktop origin is single-use: only the execution that claimed the pin keeps it. Any
			# other execution of this run (re-queued, drained again) is remote against the agent's
			# policy as it is now.
			from huf.ai.desktop_executor import holds_pin_claim, replay_policy

			if not holds_pin_claim(desktop_ctx, run.name):
				ctx["origin"] = "remote"
				ctx.pop("origin_ip", None)
				ctx.pop("agent_policy", None)
				policy = replay_policy(run.get("agent"))
				if policy:
					ctx["agent_policy"] = policy
	else:
		ctx["origin"] = "remote"
	return ctx


def _in_web_request() -> bool:
	"""True inside a web request (SSE stream, ``now=1``); False in RQ jobs."""
	return bool(getattr(frappe.local, "request", None))


def _import_dispatch_lazily():
	"""Import dispatch lazily (kept as a seam so tests can substitute it)."""
	from huf.ai import desktop_executor

	return desktop_executor.dispatch


# Identity arguments: pinned server-side, never model-controlled.
_IDENTITY_KEYS = (
	"_dx_executor_id",
	"_dx_fingerprint",
	"_dx_user",
	"_dx_pin",
	"agent_run_id",
	"call_id",
	"conversation_id",
)


def _desktop_tool(op: str):
	"""Turn ``build(**tool_params) -> params | (params, timeout_ms)`` into a handler.

	The handler validates in ``prepare`` (main thread, may read the DB) and sends in
	``execute`` (thread-safe, Redis only). It returns the dispatch result unchanged.
	"""

	def decorator(build):
		def prepare(**kwargs):
			ident = {key: kwargs.pop(key, None) for key in _IDENTITY_KEYS}
			built = build(**kwargs)
			params, timeout_ms = built if isinstance(built, tuple) else (built, MAX_FS_TIMEOUT_MS)
			_validate_params_size(params)
			dx_ctx = _validate_executor_context(
				ident["_dx_executor_id"],
				ident["_dx_fingerprint"],
				ident["_dx_user"],
				ident["agent_run_id"],
				ident["_dx_pin"],
			)
			return {
				"op": op,
				"params": params,
				"ctx": dx_ctx,
				"call_id": ident["call_id"],
				"conversation_id": ident["conversation_id"],
				"agent_run_id": ident["agent_run_id"],
				"timeout_ms": timeout_ms,
				# Decided here (the handler runs on the request/job thread, ``execute`` in a worker).
				"web_request": _in_web_request(),
			}

		def execute(prepared):
			return _import_dispatch_lazily()(**prepared)

		@functools.wraps(build)
		def handler(**kwargs):
			return execute(prepare(**kwargs))

		handler.prepare = prepare
		handler.execute = execute
		return handler

	return decorator


def _as_int(value, name):
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, int):
		return value
	try:
		return int(value)
	except (ValueError, TypeError):
		frappe.throw(_("{0} must be an integer.").format(name))


@_desktop_tool("ws.info")
def handle_workspace_info(**_ignored) -> dict:
	"""Workspace info: label, mode, platform, exec availability, top-level listing. No parameters."""
	return {}


@_desktop_tool("fs.list")
def handle_list_files(path: str = ".", depth: int = 1, include_hidden: bool = False, **_ignored):
	"""List files in a directory (depth 1-3, default 1)."""
	depth = max(1, min(3, _as_int(depth, "depth")))
	return {"path": _validate_path(path), "depth": depth, "include_hidden": bool(include_hidden)}


@_desktop_tool("fs.read")
def handle_read_file(path: str, offset: int = 0, limit: int = 2000, **_ignored):
	"""Read file content: ``offset`` (>= 0) and ``limit`` (1-2000) count lines."""
	path = _validate_path(path)
	offset = max(0, _as_int(offset, "offset"))
	limit = max(1, min(2000, _as_int(limit, "limit")))
	return {"path": path, "offset": offset, "limit": limit}


@_desktop_tool("fs.search")
def handle_search_files(
	query: str,
	path: str = ".",
	mode: str = "name",
	glob: str = None,
	case_sensitive: bool = False,
	max_results: int = 100,
	**_ignored,
):
	"""Search files by name or content (max_results clamped to 1-100)."""
	query = str(query or "").strip()
	if not query:
		frappe.throw(_("search query cannot be empty."))
	path = _validate_path(path)
	if mode not in ("name", "content"):
		mode = "name"
	params = {
		"query": query,
		"path": path,
		"mode": mode,
		"case_sensitive": bool(case_sensitive),
		"max_results": max(1, min(100, _as_int(max_results, "max_results"))),
	}
	if glob:
		glob = str(glob).strip()
		if glob:
			params["glob"] = glob
	return params


@_desktop_tool("fs.write")
def handle_write_file(
	path: str, content: str, mode: str = "overwrite", expected_sha256: str = None, **_ignored
):
	"""Write or append to a file (content at most 256 KB)."""
	path = _validate_path(path)
	content = str(content or "")
	if len(content.encode("utf-8")) > MAX_WRITE_CONTENT_BYTES:
		frappe.throw(
			_("Content exceeds maximum size of {0} KB.").format(MAX_WRITE_CONTENT_BYTES // 1024)
		)
	if mode not in ("overwrite", "create", "append"):
		mode = "overwrite"
	params = {"path": path, "content": content, "mode": mode}
	if expected_sha256:
		params["expected_sha256"] = str(expected_sha256).strip()
	return params


@_desktop_tool("fs.edit")
def handle_edit_file(
	path: str,
	old_text: str,
	new_text: str,
	replace_all: bool = False,
	expected_sha256: str = None,
	**_ignored,
):
	"""Edit file content with exact text replacement."""
	path = _validate_path(path)
	old_text = str(old_text or "")
	new_text = str(new_text or "")
	if len(old_text.encode("utf-8")) > MAX_WRITE_CONTENT_BYTES:
		frappe.throw(_("old_text exceeds maximum size."))
	if len(new_text.encode("utf-8")) > MAX_WRITE_CONTENT_BYTES:
		frappe.throw(_("new_text exceeds maximum size."))
	params = {
		"path": path,
		"old_text": old_text,
		"new_text": new_text,
		"replace_all": bool(replace_all),
	}
	if expected_sha256:
		params["expected_sha256"] = str(expected_sha256).strip()
	return params


@_desktop_tool("fs.mkdir")
def handle_make_directory(path: str, **_ignored):
	"""Create a directory."""
	return {"path": _validate_path(path)}


@_desktop_tool("fs.move")
def handle_move_path(source: str, destination: str, overwrite: bool = False, **_ignored):
	"""Move or rename a file or directory."""
	return {
		"source": _validate_path(source),
		"destination": _validate_path(destination),
		"overwrite": bool(overwrite),
	}


@_desktop_tool("fs.trash")
def handle_delete_path(path: str, recursive: bool = False, **_ignored):
	"""Move a file or directory to the OS Trash."""
	return {"path": _validate_path(path), "recursive": bool(recursive)}


@_desktop_tool("exec.run")
def handle_run_command(
	command: str,
	cwd: str = ".",
	timeout_seconds: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
	**_ignored,
):
	"""Run a shell command in the workspace (timeout_seconds clamped to 1-120)."""
	command = str(command or "").strip()
	if not command:
		frappe.throw(_("command cannot be empty."))
	cwd = _validate_path(cwd)
	timeout_seconds = max(
		MIN_EXEC_TIMEOUT_SECONDS,
		min(MAX_EXEC_TIMEOUT_SECONDS, _as_int(timeout_seconds, "timeout_seconds")),
	)
	params = {"command": command, "cwd": cwd, "timeout_seconds": timeout_seconds}
	# The desktop needs the command's own timeout plus a buffer.
	return params, timeout_seconds * 1000 + 5000
