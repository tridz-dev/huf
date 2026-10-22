"""
Desktop local-capability tools: local skills, background processes, local MCP and browser.

Skills are folders the local user enabled inside Huf Desktop. They are addressed by
id (``local:<dirLabel>/<name>``) and by paths relative to the skill directory; absolute
paths never leave the machine. Every handler uses the same ``_desktop_tool`` machinery as
the workspace tools (:mod:`huf.ai.tools.desktop_workspace`): ``prepare`` validates on the
loop thread and verifies the ``_dx_pin`` token and the run's pinned executor, ``execute``
talks to Redis in a worker thread, and the ``desktop_executor.dispatch`` result is returned
UNCHANGED (``untrusted_content`` / ``trust`` labels and error codes reach the model).

The catalog the run is pinned to (``runtime_context.desktop.catalog_hash``) is read by
``dispatch``: a skill that is not in it is refused with ``tool_unavailable`` before anything
is published.

Server skills win. ``sdk_tools`` passes ``_dx_hidden_skills`` (local skill ids shadowed by an
attached server skill of the same name, pinned like the other ``_dx_*`` values) and the
read/run handlers refuse those ids.

Processes (``proc.*``): four tools over the desktop's process supervisor. Names are
``^[a-z0-9-]{1,32}$``, every start is approved by the user on the desktop, and ``proc.logs``
output is untrusted.

Local MCP and browser (``mcp.call``): ``handle_mcp_tool_call`` backs the eager ``lmcp__*`` and
``lbrowser__*`` tools that ``sdk_tools`` builds from the catalog pinned to the run;
``handle_mcp_call`` backs ``desktop_mcp_call`` (arguments nested in one object) and
``handle_mcp_find`` answers from the pinned catalog without touching the desktop. The agent
name, server and tool of an eager tool are pinned by ``sdk_tools`` (``_dx_*``) and are never
taken from the model. ``dispatch`` re-checks everything against the pinned catalog and validates
``arguments`` against the pinned input schema before publishing.
"""

import functools
import json
import re

import frappe
from frappe import _

from huf.ai.tools import desktop_workspace
from huf.ai.tools.desktop_workspace import (
	DEFAULT_EXEC_TIMEOUT_SECONDS,
	MAX_EXEC_TIMEOUT_SECONDS,
	MIN_EXEC_TIMEOUT_SECONDS,
	_as_int,
	_desktop_tool,
	_validate_executor_context,
	_validate_path,
)

MAX_LIST_LIMIT = 50
DEFAULT_LIST_LIMIT = 20
MAX_READ_LINES = 2000
MAX_SCRIPT_ARGS = 32
MAX_SCRIPT_ARGS_BYTES = 4 * 1024
MAX_QUERY_CHARS = 200
SKILL_ID_RE = re.compile(r"^local:[a-z0-9_-]{1,48}/[a-z0-9_-]{1,48}$")


def _validate_skill_id(skill) -> str:
	skill = str(skill or "").strip()
	if not SKILL_ID_RE.match(skill):
		frappe.throw(_("skill must be a local skill id such as local:<dir>/<name>."))
	return skill


def _skill_tool(op: str):
	"""``_desktop_tool`` plus the server-skill-wins check on the pinned ``skill`` id."""

	def decorator(build):
		inner = _desktop_tool(op)(build)

		def prepare(**kwargs):
			hidden = kwargs.pop("_dx_hidden_skills", None) or ()
			prepared = inner.prepare(**kwargs)
			skill = prepared["params"].get("skill")
			if skill and skill in tuple(hidden):
				frappe.throw(
					_("A server skill with the same name is attached to this agent; use that one instead.")
				)
			return prepared

		@functools.wraps(build)
		def handler(**kwargs):
			return inner.execute(prepare(**kwargs))

		handler.prepare = prepare
		handler.execute = inner.execute
		return handler

	return decorator


@_skill_tool("skill.list")
def handle_skill_list(query: str = "", limit: int = DEFAULT_LIST_LIMIT, **_ignored):
	"""Search enabled local skills (limit clamped to 1-50)."""
	params = {"limit": max(1, min(MAX_LIST_LIMIT, _as_int(limit, "limit")))}
	query = " ".join(str(query or "").split())[:MAX_QUERY_CHARS]
	if query:
		params["query"] = query
	return params


@_skill_tool("skill.read")
def handle_skill_read(
	skill: str, path: str = "SKILL.md", offset: int = 0, limit: int = MAX_READ_LINES, **_ignored
):
	"""Read SKILL.md or a bundled file of an enabled local skill: ``offset`` (>= 0) and ``limit`` (1-2000) count lines."""
	return {
		"skill": _validate_skill_id(skill),
		"path": _validate_path(path or "SKILL.md"),
		"offset": max(0, _as_int(offset, "offset")),
		"limit": max(1, min(MAX_READ_LINES, _as_int(limit, "limit"))),
	}


def _clean_args(args) -> list:
	if args is None or args == "":
		return []
	if isinstance(args, str):
		try:
			args = json.loads(args)
		except (TypeError, ValueError):
			frappe.throw(_("args must be a list of strings."))
	if not isinstance(args, (list, tuple)):
		frappe.throw(_("args must be a list of strings."))
	if len(args) > MAX_SCRIPT_ARGS:
		frappe.throw(_("args may have at most {0} entries.").format(MAX_SCRIPT_ARGS))
	out = []
	for item in args:
		if isinstance(item, (dict, list, tuple)):
			frappe.throw(_("args entries must be strings."))
		text = str(item)
		if "\0" in text:
			frappe.throw(_("args must not contain NUL bytes."))
		out.append(text)
	if sum(len(a.encode("utf-8")) for a in out) > MAX_SCRIPT_ARGS_BYTES:
		frappe.throw(_("args exceed {0} bytes in total.").format(MAX_SCRIPT_ARGS_BYTES))
	return out


@_skill_tool("skill.exec")
def handle_skill_run(
	skill: str,
	script: str,
	args=None,
	timeout_seconds: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
	**_ignored,
):
	"""Run a script bundled in an enabled local skill, without a shell (timeout clamped to 1-120)."""
	timeout_seconds = max(
		MIN_EXEC_TIMEOUT_SECONDS,
		min(MAX_EXEC_TIMEOUT_SECONDS, _as_int(timeout_seconds, "timeout_seconds")),
	)
	params = {
		"skill": _validate_skill_id(skill),
		"script": _validate_path(script),
		"args": _clean_args(args),
		"timeout_seconds": timeout_seconds,
	}
	# The desktop needs the script's own timeout plus a buffer.
	return params, timeout_seconds * 1000 + 5000


# --------------------------------------------------------------------------
# Background processes
# --------------------------------------------------------------------------

PROC_NAME_RE = re.compile(r"^[a-z0-9-]{1,32}$")
MAX_PROC_COMMAND_CHARS = 8 * 1024
MAX_READY_PATTERN_CHARS = 200
DEFAULT_READY_TIMEOUT_S = 30
MAX_READY_TIMEOUT_S = 60
MAX_TAIL_LINES = 400
DEFAULT_TAIL_LINES = 100
PROC_STREAMS = ("both", "stdout", "stderr")


def _validate_proc_name(name) -> str:
	name = str(name or "").strip()
	if not PROC_NAME_RE.match(name):
		frappe.throw(_("name must be 1-32 characters: lowercase letters, digits and dashes."))
	return name


@_desktop_tool("proc.start")
def handle_process_start(
	name: str,
	command: str,
	cwd: str = ".",
	ready_pattern: str = None,
	ready_timeout_s: int = DEFAULT_READY_TIMEOUT_S,
	port_hint: int = None,
	**_ignored,
):
	"""Start a background process (ready_timeout_s clamped to 1-60, port_hint 1024-65535)."""
	command = str(command or "").strip()
	if not command:
		frappe.throw(_("command cannot be empty."))
	if "\0" in command:
		frappe.throw(_("command must not contain NUL bytes."))
	if len(command) > MAX_PROC_COMMAND_CHARS:
		frappe.throw(_("command exceeds {0} characters.").format(MAX_PROC_COMMAND_CHARS))
	ready_timeout_s = max(1, min(MAX_READY_TIMEOUT_S, _as_int(ready_timeout_s, "ready_timeout_s")))
	params = {
		"name": _validate_proc_name(name),
		"command": command,
		"cwd": _validate_path(cwd or "."),
		"ready_timeout_s": ready_timeout_s,
	}
	pattern = str(ready_pattern or "").strip()
	if pattern:
		if "\0" in pattern or len(pattern) > MAX_READY_PATTERN_CHARS:
			frappe.throw(_("ready_pattern must be at most {0} characters.").format(MAX_READY_PATTERN_CHARS))
		params["ready_pattern"] = pattern
	if port_hint not in (None, ""):
		port = _as_int(port_hint, "port_hint")
		if not 1024 <= port <= 65535:
			frappe.throw(_("port_hint must be between 1024 and 65535."))
		params["port_hint"] = port
	# The desktop waits for readiness (at most ready_timeout_s) plus its own start-up time.
	return params, ready_timeout_s * 1000 + 10000


@_desktop_tool("proc.list")
def handle_process_list(**_ignored):
	"""List the background processes of this workspace. No parameters."""
	return {}


@_desktop_tool("proc.logs")
def handle_process_logs(
	name: str,
	stream: str = "both",
	tail_lines: int = DEFAULT_TAIL_LINES,
	since_seq: int = None,
	**_ignored,
):
	"""Read process output: tail_lines clamped to 1-400, since_seq (>= 0) returns only newer lines."""
	stream = str(stream or "both").strip().lower()
	if stream not in PROC_STREAMS:
		stream = "both"
	params = {
		"name": _validate_proc_name(name),
		"stream": stream,
		"tail_lines": max(1, min(MAX_TAIL_LINES, _as_int(tail_lines, "tail_lines"))),
	}
	if since_seq not in (None, ""):
		params["since_seq"] = max(0, _as_int(since_seq, "since_seq"))
	return params


@_desktop_tool("proc.stop")
def handle_process_stop(name: str, **_ignored):
	"""Stop a background process."""
	return {"name": _validate_proc_name(name)}


# --------------------------------------------------------------------------
# Local MCP and browser
# --------------------------------------------------------------------------

MCP_CALL_TIMEOUT_MS = 60_000
MAX_SERVER_NAME_CHARS = 48
_MCP_NAME_RE = re.compile(r"^[a-z0-9_-]{1,48}$")
FIND_RESULT_MAX_BYTES = 48 * 1024
# Keys ``sdk_tools`` and the run context put next to a model's arguments; never model arguments.
_NON_ARGUMENT_KEYS = ("agent_name", "ignore_permissions", "tool_name")


def handle_local_mcp_grant(**_ignored):
	"""The ``desktop_local_mcp`` / ``desktop_browser`` grant rows are never callable: ``sdk_tools``
	replaces them with concrete tools at run start."""
	frappe.throw(_("This is an access grant, not a tool. Its tools are added when a run starts."))


def _mcp_name(value, what) -> str:
	value = str(value or "").strip()
	if not _MCP_NAME_RE.match(value):
		frappe.throw(_("{0} must be a name such as the one desktop_mcp_find returns.").format(what))
	return value


def _arguments_object(arguments) -> dict:
	if arguments is None or arguments == "":
		return {}
	if isinstance(arguments, str):
		try:
			arguments = json.loads(arguments)
		except (TypeError, ValueError):
			frappe.throw(_("arguments must be an object."))
	if not isinstance(arguments, dict):
		frappe.throw(_("arguments must be an object."))
	return arguments


def _mcp_tool(build):
	"""``_desktop_tool("mcp.call")`` plus the pinned agent name and a pre-dispatch refusal.

	``build(pinned, **model_kwargs) -> (params, refusal | None)``; ``pinned`` holds the
	server-owned ``_dx_mcp_server`` / ``_dx_mcp_tool`` / ``_dx_mcp_kind`` of an eager tool.
	A refusal is ``(code, message)`` and is returned as a normal desktop error result, after
	the run pin has been verified and before anything is published.
	"""

	def prepare(**kwargs):
		agent = kwargs.pop("_dx_agent", None)
		display = kwargs.pop("_dx_agent_display", None)
		pinned = {key: kwargs.pop(key, None) for key in ("_dx_mcp_server", "_dx_mcp_tool", "_dx_mcp_kind")}
		refusals = []

		def shaped(**model_kwargs):
			params, refusal = build(pinned, **model_kwargs)
			if refusal:
				refusals.append(refusal)
			return params, MCP_CALL_TIMEOUT_MS

		prepared = _desktop_tool("mcp.call")(shaped).prepare(**kwargs)
		# Pinned by sdk_tools from the agent document: dispatch checks it against the catalog's
		# per-agent list, and the desktop receives it in the request.
		prepared["agent_name"] = str(agent) if agent else None
		prepared["agent_display_name"] = str(display) if display else None
		if refusals:
			prepared["_refuse"] = refusals[0]
		return prepared

	def execute(prepared):
		prepared = dict(prepared)
		refusal = prepared.pop("_refuse", None)
		if refusal:
			from huf.ai import desktop_executor

			return desktop_executor._error(prepared["op"], prepared["ctx"].get("label"), *refusal)
		return desktop_workspace._import_dispatch_lazily()(**prepared)

	@functools.wraps(build)
	def handler(**kwargs):
		return execute(prepare(**kwargs))

	handler.prepare = prepare
	handler.execute = execute
	return handler


@_mcp_tool
def handle_mcp_tool_call(pinned, /, **model_kwargs):
	"""Backs every eager ``lmcp__*`` / ``lbrowser__*`` tool: the model's top-level arguments
	are the MCP tool's arguments, the server and tool come from the pin."""
	from huf.ai import desktop_mcp

	server = _mcp_name(pinned.get("_dx_mcp_server"), "server")
	tool = _mcp_name(pinned.get("_dx_mcp_tool"), "tool")
	# ``_dx_*`` keys are server-owned pins (a model-sent one that ``sdk_tools`` did not overwrite,
	# such as ``_dx_hidden_skills``, must not leak into the MCP tool's arguments either).
	arguments = {
		k: v for k, v in model_kwargs.items() if k not in _NON_ARGUMENT_KEYS and not str(k).startswith("_dx_")
	}
	refusal = None
	if server == desktop_mcp.BROWSER_SERVER and pinned.get("_dx_mcp_kind") != "browser":
		refusal = ("denied_by_policy", "Browser tools are only available through the desktop_browser grant.")
	return {"server": server, "tool": tool, "arguments": arguments}, refusal


@_mcp_tool
def handle_mcp_call(pinned, /, server: str = None, tool: str = None, arguments=None, **_ignored):
	"""Call a local MCP tool that is not available directly. ``arguments`` is validated against the
	input schema pinned to the run before anything is sent."""
	from huf.ai import desktop_mcp

	server = _mcp_name(server, "server")
	tool = _mcp_name(tool, "tool")
	refusal = None
	if server == desktop_mcp.BROWSER_SERVER:
		refusal = ("denied_by_policy", "Browser tools are only available through the desktop_browser grant.")
	return {"server": server, "tool": tool, "arguments": _arguments_object(arguments)}, refusal


def handle_mcp_find(query: str = "", server: str = None, limit: int = 8, **kwargs):
	"""Search the local MCP tools of the catalog pinned to this run. Answered on the server: nothing
	is sent to the desktop."""
	return handle_mcp_find.execute(handle_mcp_find.prepare(query=query, server=server, limit=limit, **kwargs))


def _find_prepare(**kwargs):
	from huf.ai import desktop_executor as dx
	from huf.ai import desktop_mcp

	ident = {key: kwargs.pop(key, None) for key in desktop_workspace._IDENTITY_KEYS}
	agent = kwargs.pop("_dx_agent", None)
	kwargs.pop("_dx_agent_display", None)
	query = " ".join(str(kwargs.get("query") or "").split())[:MAX_QUERY_CHARS]
	server = str(kwargs.get("server") or "").strip() or None
	limit = max(1, min(desktop_mcp.MCP_FIND_MAX_RESULTS, _as_int(kwargs.get("limit") or 8, "limit")))
	ctx = _validate_executor_context(
		ident["_dx_executor_id"],
		ident["_dx_fingerprint"],
		ident["_dx_user"],
		ident["agent_run_id"],
		ident["_dx_pin"],
	)
	catalog = dx.get_catalog(ctx["executor_id"], ctx.get("catalog_hash"))
	base = {"op": "mcp.find", "workspace": ctx.get("label"), "truncated": False, "duration_ms": 0}
	if catalog is None:
		return {"result": {**base, "ok": False, "error": {
			"code": "tool_unavailable",
			"message": "No local MCP catalog is pinned to this run, or it is no longer available.",
		}}}
	plan = desktop_mcp.plan_mcp_group(catalog, agent, dx.sanitize_text)
	direct = {(s["server"], s["tool"]): s["name"] for s in plan["eager"]}
	rows, total_bytes, truncated = [], 0, False
	for srv, tool in desktop_mcp.find_matches(catalog, agent, query, server=server, limit=limit):
		entry = {
			"server": srv["server"],
			"tool": tool["name"],
			"description": desktop_mcp.model_description(srv["server"], tool, dx.sanitize_text),
			"input_schema": desktop_mcp.model_schema(tool, dx.sanitize_text),
		}
		if (srv["server"], tool["name"]) in direct:
			entry["callable_as"] = direct[(srv["server"], tool["name"])]
		size = len(json.dumps(entry, default=str))
		if total_bytes + size > FIND_RESULT_MAX_BYTES:
			truncated = True
			break
		total_bytes += size
		rows.append(entry)
	return {
		"result": {
			**base,
			"ok": True,
			"data": {"tools": rows},
			"truncated": truncated,
			"untrusted_content": True,
			"note": dx.UNTRUSTED_MCP_NOTE,
			"origin": "local_mcp",
		}
	}


def _find_execute(prepared):
	return prepared["result"]


handle_mcp_find.prepare = _find_prepare
handle_mcp_find.execute = _find_execute
