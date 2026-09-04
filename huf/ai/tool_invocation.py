"""Instrumented tool-invocation service (T-10).

Single resolver plus single invocation path shared by the LLM tool path
(``huf.ai.sdk_tools``) and the deterministic Flow/Procedure tool path
(``huf.ai.flow_tool_executor``). Before this module the two paths had drifted
independently (GT-05 in ``TRACK/PLAN.md``): the type->handler map was
hand-duplicated in both files, and the deterministic path had none of the
permission machinery the LLM path enforces on every call.

See ``TRACK/spec/tool-invocation-seam.md`` for the audit this module resolves
(referenced below as "the seam audit") -- it documents, line by line, every
place the two paths disagreed and which side is authoritative.

Ownership split:

- This module owns: resolving a tool name/doc to a handler, deriving
  ``extra_args``, the permission gate (guest/mutating-type check,
  ``ignore_permissions`` stripping, guest doctype pinning), signature-aware
  argument filtering, async-native coroutine handling, and (opt-in per call)
  ``Agent Tool Call`` telemetry.
- Callers own: building a ``RunContext`` from their own state (Agents SDK
  ``ToolContext`` for the LLM path, Flow/Procedure run state for the
  deterministic path), and anything specific to their execution model (Agent
  Run bookkeeping, flow context writes, JSON-string wrapping for the SDK).
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import frappe

from huf.ai.tool_types import _GUEST_DOCTYPE_PINNED_TYPES, _GUEST_REPORT_PINNED_TYPES, MUTATING_TOOL_TYPES

logger = frappe.logger("huf")


# ---------------------------------------------------------------------------
# Resolver: tool type -> function_path (single source of truth)
#
# Previously hand-duplicated at sdk_tools.py:184-250 (the create_agent_tools
# if/elif chain) and flow_tool_executor.py:163-186 (_resolve_function_path's
# type_to_handler dict) -- the seam audit's §1. One dict, one place now.
# ---------------------------------------------------------------------------

TYPE_TO_FUNCTION_PATH: dict[str, str] = {
	"Get List": "huf.ai.sdk_tools.handle_get_list",
	"Get Document": "huf.ai.sdk_tools.handle_get_document",
	"Update Document": "huf.ai.sdk_tools.handle_update_document",
	"Create Document": "huf.ai.sdk_tools.handle_create_document",
	"Delete Document": "huf.ai.sdk_tools.handle_delete_document",
	"Get Multiple Documents": "huf.ai.sdk_tools.handle_get_documents",
	"Create Multiple Documents": "huf.ai.sdk_tools.handle_create_documents",
	"Update Multiple Documents": "huf.ai.sdk_tools.handle_update_documents",
	"Delete Multiple Documents": "huf.ai.sdk_tools.handle_delete_documents",
	"Submit Document": "huf.ai.sdk_tools.handle_submit_document",
	"Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
	"Get Value": "huf.ai.sdk_tools.handle_get_value",
	"Set Value": "huf.ai.sdk_tools.handle_set_value",
	"Get Report Result": "huf.ai.sdk_tools.handle_get_report_result",
	"GET": "huf.ai.http_handler.handle_get_request",
	"POST": "huf.ai.http_handler.handle_post_request",
	"Run Agent": "huf.ai.sdk_tools.handle_run_agent",
	"Attach File to Document": "huf.ai.sdk_tools.handle_attach_file_to_document",
	"Send Email": "huf.ai.sdk_tools.handle_send_email",
	"Get Conversation Data": "huf.ai.sdk_tools.handle_get_conversation_data",
	"Set Conversation Data": "huf.ai.sdk_tools.handle_set_conversation_data",
	"Load Conversation Data": "huf.ai.sdk_tools.handle_load_conversation_data",
	"Perplexity Search": "huf.ai.tools.perplexity.handle_perplexity_search",
	# Present on the LLM side (A) but absent from the deterministic side (B)
	# before this task -- seam audit §1. A Flow/Procedure node can now reach
	# these the same way the LLM can.
	"Save Memory Record": "huf.ai.memory_tools.handle_save_memory_record",
	"Search Memory Records": "huf.ai.memory_tools.handle_search_memory_records",
	"Get Memory Record": "huf.ai.memory_tools.handle_get_memory_record",
	"Archive Memory Record": "huf.ai.memory_tools.handle_archive_memory_record",
	"Promote Memory to Knowledge": "huf.ai.memory_tools.handle_promote_memory_to_knowledge",
}

# Resolved dynamically from the tool doc itself, not from the static map.
DYNAMIC_FUNCTION_PATH_TYPES = frozenset({"Custom Function", "App Provided"})

CLIENT_SIDE_TOOL_TYPE = "Client Side Tool"
CLIENT_SIDE_TOOL_FUNCTION_PATH = "huf.ai.client_side_tool.client_side_function"

# Types whose extra_args include a pinned reference_doctype (sdk_tools.py's
# two branches -- Attach File to Document plus the CRUD family -- collapsed
# into one set; both produced the same key).
REFERENCE_DOCTYPE_PIN_TYPES = frozenset({
	"Get Document", "Get Multiple Documents", "Get List",
	"Create Document", "Create Multiple Documents",
	"Update Document", "Update Multiple Documents",
	"Delete Document", "Delete Multiple Documents",
	"Submit Document", "Cancel Document", "Get Amended Document",
	"Attach File to Document",
	"Send Email",
})

# Bare tool-name aliases usable without a backing Agent Tool Function
# document (flow_tool_executor's former _resolve_standard_tool, seam audit
# §1/§4, tracked as F-21). The resolved tool_doc for these has no
# reference_doctype pin and allowed_for_guest=False, so the permission gate
# below (check_tool_permission + the guest doctype-pin check) applies to
# them exactly as it does to a real Agent Tool Function doc -- a Guest can
# never reach a mutating alias, and a pinned type with no pin is refused
# outright. This is what closes F-21 structurally rather than by convention.
STANDARD_TOOL_ALIASES: dict[str, str] = {
	"create_document": "Create Document",
	"get_document": "Get Document",
	"update_document": "Update Document",
	"delete_document": "Delete Document",
	"get_list": "Get List",
	"get_documents": "Get Multiple Documents",
	"create_documents": "Create Multiple Documents",
	"update_documents": "Update Multiple Documents",
	"delete_documents": "Delete Multiple Documents",
	"submit_document": "Submit Document",
	"cancel_document": "Cancel Document",
	"get_value": "Get Value",
	"set_value": "Set Value",
	"get_report_result": "Get Report Result",
	"attach_file_to_document": "Attach File to Document",
}


@dataclass
class RunContext:
	"""Normalized invocation context. Callers build this from their own state
	-- the Agents SDK's ToolContext for the LLM path, Flow/Procedure run
	state for the deterministic path -- the resolver never reaches back into
	caller-specific objects itself (seam audit's "stays with callers" list).
	"""

	conversation_id: str | None = None
	agent_run_id: str | None = None
	agent_name: str | None = None
	call_id: str | None = None
	user: str | None = None
	extra: dict = field(default_factory=dict)


def resolve_tool_doc(tool_name: str) -> dict | None:
	"""Look up a tool by its ``tool_name`` field.

	Returns a plain dict shape shared by both a real ``Agent Tool Function``
	row and a synthetic alias doc, so ``resolve_function_path``/
	``build_extra_args``/the permission gate below don't need to know which
	kind they got.
	"""
	doc = frappe.db.get_value(
		"Agent Tool Function",
		{"tool_name": tool_name},
		["name", "tool_name", "types", "function_path", "reference_doctype",
			"reference_report", "agent", "function_name", "allowed_for_guest", "blocking", "base_url"],
		as_dict=True,
	)
	if doc:
		return dict(doc)

	alias_type = STANDARD_TOOL_ALIASES.get(tool_name)
	if alias_type:
		return {
			"name": tool_name,
			"tool_name": tool_name,
			"types": alias_type,
			"function_path": None,
			"reference_doctype": None,
			"reference_report": None,
			"agent": None,
			"function_name": None,
			"allowed_for_guest": False,
			"blocking": False,
			"base_url": None,
		}
	return None


def resolve_function_path(tool_doc: dict) -> str | None:
	"""Pure resolution: tool type -> function_path. No execution, no I/O."""
	types = tool_doc.get("types")
	if types in DYNAMIC_FUNCTION_PATH_TYPES:
		return tool_doc.get("function_path")
	if types == CLIENT_SIDE_TOOL_TYPE:
		return CLIENT_SIDE_TOOL_FUNCTION_PATH if tool_doc.get("function_name") else None
	return TYPE_TO_FUNCTION_PATH.get(types)


def build_extra_args(tool_doc: dict) -> dict:
	"""Derive the extra_args template injected into every call of this tool.

	Standardized on the LLM path's *overwrite* semantics
	(``args_dict.update(extra_args)`` at sdk_tools.py:505-506) rather than
	flow_tool_executor's ``setdefault`` -- a setdefault pin is bypassable by
	upstream Flow/Procedure context that copies ``reference_doctype`` into
	args before calling a pinned tool; overwrite is not. This is a
	deliberate behavior change on the deterministic side, called out
	explicitly per the seam audit §2/"Recommended target shape" rather than
	silently inherited, since it is what keeps a pinned doctype actually
	pinned (security-relevant: the guest-doctype-pin check below assumes the
	pin cannot be overridden by caller-supplied args).

	Also fixes a latent bug in the old B-side GET/POST case (seam audit
	§2): B used ``tool_doc.get("name")``, which for a real Agent Tool
	Function doc is the Frappe docname (e.g. ``ATF-00042``), not the
	friendly tool name -- diverging from A, which always used
	``function_doc.tool_name``. This resolver always uses the friendly
	``tool_name``.
	"""
	types = tool_doc.get("types")
	extra: dict = {}

	if types in REFERENCE_DOCTYPE_PIN_TYPES and tool_doc.get("reference_doctype"):
		extra["reference_doctype"] = tool_doc["reference_doctype"]
	elif types in _GUEST_REPORT_PINNED_TYPES and tool_doc.get("reference_report"):
		extra["reference_report"] = tool_doc["reference_report"]
	elif types == CLIENT_SIDE_TOOL_TYPE and tool_doc.get("function_name"):
		extra["function_name"] = tool_doc["function_name"]
	elif types == "Run Agent" and tool_doc.get("agent"):
		extra["target_agent_name"] = tool_doc["agent"]

	if types in ("GET", "POST"):
		extra["tool_name"] = tool_doc.get("tool_name") or tool_doc.get("name")

	return extra


def check_tool_permission(tool_type: str | None, allowed_for_guest: bool = False) -> dict:
	"""Guard blocking Guest users from mutating tools unless explicitly
	allowed. Preserved byte-for-byte from ``sdk_tools._check_tool_permission``
	(seam audit: "not the resolver's job" changed nothing here -- it just
	moved, this is the piece that was A-only and is now shared).
	"""
	user = frappe.session.user

	if user == "Guest":
		if allowed_for_guest:
			return {"allowed": True}
		if tool_type in MUTATING_TOOL_TYPES:
			return {
				"allowed": False,
				"error": f"Guest users cannot use {tool_type} tools. Please log in.",
			}

	return {"allowed": True}


def _merge_run_context(args_dict: dict, ctx: RunContext) -> dict:
	"""Inject run-context values into tool args without clobbering the
	caller's own. Ported byte-for-byte from ``sdk_tools._merge_run_context``
	including the blank-string-counts-as-absent semantics documented there
	(a real production incident, not incidental -- see the seam audit's
	"must be preserved byte-for-byte" list).
	"""
	huf_ctx = {
		"conversation_id": ctx.conversation_id,
		"agent_run_id": ctx.agent_run_id,
		"agent_name": ctx.agent_name,
	}
	for key, value in huf_ctx.items():
		if value is None:
			continue
		current = args_dict.get(key)
		if current is None or (isinstance(current, str) and not current.strip()):
			args_dict[key] = value

	if ctx.call_id:
		args_dict.setdefault("call_id", ctx.call_id)

	return args_dict


@dataclass
class ToolResult:
	success: bool
	result: Any = None
	error: str | None = None
	denied: bool = False

	def as_dict(self) -> dict:
		out = {"success": self.success}
		if self.success:
			out["result"] = self.result
		else:
			out["error"] = self.error
			if self.denied:
				out["denied"] = True
		return out


def get_function_from_name(tool_name: str) -> Callable | None:
	"""Re-exported for callers that only need resolution, not invocation.
	The real implementation stays single-sourced in sdk_tools.py (seam
	audit §"Recommended target shape": "already single-sourced ... just
	needs to move if sdk_tools.py itself is refactored" -- it wasn't, so
	this module imports it lazily to avoid a sdk_tools<->tool_invocation
	import cycle (sdk_tools imports resolution helpers from this module).
	"""
	from huf.ai.sdk_tools import get_function_from_name as _impl
	return _impl(tool_name)


async def invoke_tool(
	tool_name: str,
	args: dict,
	*,
	ctx: RunContext | None = None,
	telemetry: bool = False,
	blocking: bool = False,
) -> ToolResult:
	"""Single call path: resolve -> permission check -> run-context merge ->
	extra_args injection -> ignore_permissions strip -> guest-doctype-pin
	enforcement -> signature-aware filtering -> call (async-native) ->
	result normalization -> optional Agent Tool Call telemetry.

	``telemetry`` defaults to False because the LLM path already has its own
	``Agent Tool Call`` telemetry, wired through the Agents SDK's own
	tool-call lifecycle (outside this module's scope -- see
	spec/tool-invocation-seam.md §6). Passing ``telemetry=True`` is how a
	caller that has none today (the deterministic path, GT-05) gets it.
	"""
	ctx = ctx or RunContext()

	tool_doc = resolve_tool_doc(tool_name)
	if not tool_doc:
		return ToolResult(success=False, error=f"Tool '{tool_name}' not found in Agent Tool Function")

	tool_type = tool_doc.get("types")
	allowed_for_guest = bool(tool_doc.get("allowed_for_guest"))

	perm_check = check_tool_permission(tool_type, allowed_for_guest=allowed_for_guest)
	if not perm_check["allowed"]:
		return ToolResult(success=False, error=perm_check["error"], denied=True)

	function_path = resolve_function_path(tool_doc)
	if not function_path:
		return ToolResult(success=False, error=f"Cannot resolve handler for tool type '{tool_type}'")

	handler = get_function_from_name(function_path)
	if not handler:
		return ToolResult(success=False, error=f"Handler function not found: {function_path}")

	args_dict = dict(args) if args else {}
	_merge_run_context(args_dict, ctx)

	extra_args = build_extra_args(tool_doc)
	if extra_args:
		args_dict.update(extra_args)

	# SECURITY (F-21, invariant I1): strip any caller-supplied
	# ignore_permissions unconditionally, on every path, before any handler
	# sees args_dict. Handlers in huf/ai/handlers/*.py declare
	# ``ignore_permissions=False, **kwargs`` -- because they accept
	# **kwargs, a caller-supplied ignore_permissions=True used to reach the
	# handler on the deterministic path (flow_tool_executor passed args
	# straight through) and disable permission checks. This is the one
	# sanctioned exception, set explicitly below for the guest-pin case
	# only -- never accepted from the caller.
	args_dict.pop("ignore_permissions", None)

	if allowed_for_guest and frappe.session.user == "Guest":
		if tool_type in _GUEST_DOCTYPE_PINNED_TYPES and not extra_args.get("reference_doctype"):
			return ToolResult(
				success=False,
				denied=True,
				error=(
					"This tool is not available for guest access: it has no "
					"fixed target doctype configured."
				),
			)
		if tool_type in _GUEST_REPORT_PINNED_TYPES and not extra_args.get("reference_report"):
			return ToolResult(
				success=False,
				denied=True,
				error=(
					"This tool is not available for guest access: it has no "
					"fixed target report configured."
				),
			)
		args_dict["ignore_permissions"] = True

	# Override report_name with reference_report if pinned for guest
	if extra_args.get("reference_report"):
		args_dict["report_name"] = extra_args["reference_report"]

	telemetry_doc = None
	if telemetry:
		telemetry_doc = _start_tool_call_telemetry(tool_name, args_dict, ctx)

	try:
		sig = inspect.signature(handler)
		accepts_kwargs = any(
			p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
		)
		if accepts_kwargs:
			call_kwargs = args_dict
		else:
			valid_params = set(sig.parameters.keys())
			call_kwargs = {k: v for k, v in args_dict.items() if k in valid_params}

		if blocking:
			# Client Side Tool calls block waiting for a browser-reported
			# result; run off the event loop so this doesn't stall the
			# whole run (mirrors sdk_tools.create_function_tool's
			# asyncio.to_thread escape hatch, preserved verbatim).
			raw_result = await asyncio.to_thread(handler, **call_kwargs)
		else:
			raw_result = handler(**call_kwargs)

		# Async-native: await in place if the handler happens to be a
		# coroutine function. No asyncio.new_event_loop()/run_until_complete
		# anywhere in this module -- the seam audit flagged the old
		# per-call throwaway loop in flow_tool_executor as a latent
		# thread-safety hazard (§3); callers that must invoke this from
		# synchronous code go through invoke_tool_sync's single, shared
		# event-loop-management utility instead.
		if asyncio.iscoroutine(raw_result):
			raw_result = await raw_result

		if hasattr(raw_result, "as_dict") and callable(getattr(raw_result, "as_dict", None)):
			raw_result = raw_result.as_dict()

		tool_result = ToolResult(success=True, result=raw_result)

	except Exception as e:
		logger.debug(f"tool_invocation: error invoking '{tool_name}': {e!s}\n{frappe.get_traceback()}")
		tool_result = ToolResult(success=False, error=str(e))

	if telemetry_doc is not None:
		_finalize_tool_call_telemetry(telemetry_doc, tool_result)

	return tool_result


def _run_coroutine_sync(coro):
	"""Run a coroutine to completion from synchronous code, at the outermost
	sync entry point -- one shared utility rather than a new event loop per
	tool call (the bug the seam audit flagged in the old
	flow_tool_executor.execute(), §3: a fresh ``asyncio.new_event_loop()`` +
	``asyncio.set_event_loop()`` per invocation, unsafe if the calling
	thread ever already has a running loop).
	"""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(coro)

	# Already inside a running loop on this thread (e.g. called from async
	# code) -- run on a fresh thread instead of nesting loops.
	import concurrent.futures

	with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
		return pool.submit(asyncio.run, coro).result()


def invoke_tool_sync(
	tool_name: str,
	args: dict,
	*,
	ctx: RunContext | None = None,
	telemetry: bool = False,
	blocking: bool = False,
) -> ToolResult:
	"""Synchronous wrapper around ``invoke_tool`` for callers (Flow Engine
	today) that are not themselves async.
	"""
	return _run_coroutine_sync(
		invoke_tool(tool_name, args, ctx=ctx, telemetry=telemetry, blocking=blocking)
	)


def _start_tool_call_telemetry(tool_name: str, args: dict, ctx: RunContext):
	"""Insert an ``Agent Tool Call`` record with status Started, before
	invocation. Ported from ``flow_engine._exec_tool_call``
	(flow_engine.py:599-630 on the base checkout) -- the seam this task
	moves per GT-05/I5, generalized so any caller gets it for free by
	passing ``telemetry=True`` instead of assembling this block itself.
	"""
	is_mcp_tool = 0
	mcp_server = None
	mcp_tool_entry = frappe.db.get_value(
		"MCP Server Tool", {"tool_name": tool_name, "enabled": 1}, "parent"
	)
	if mcp_tool_entry:
		is_mcp_tool = 1
		mcp_server = mcp_tool_entry

	call_id = ctx.call_id or f"call_{uuid4().hex[:12]}"
	ctx.call_id = call_id

	doc = frappe.get_doc({
		"doctype": "Agent Tool Call",
		"agent_run": ctx.agent_run_id,
		"conversation": ctx.conversation_id,
		"tool": tool_name,
		"is_mcp_tool": is_mcp_tool,
		"mcp_server": mcp_server,
		"tool_args": json.dumps(args, default=str) if args else None,
		"status": "Started",
		"call_id": call_id,
	})
	doc.insert(ignore_permissions=True)
	return doc


def _finalize_tool_call_telemetry(doc, tool_result: ToolResult) -> None:
	"""Finalize the Agent Tool Call record as Completed/Failed, after
	invocation. Never raises -- a telemetry write failure must not turn a
	successful tool call into a failed one.
	"""
	result_val = tool_result.result
	if isinstance(result_val, (dict, list)):
		formatted_result = result_val
	else:
		formatted_result = {"output": str(result_val)} if result_val is not None else None

	try:
		doc.update({
			"status": "Completed" if tool_result.success else "Failed",
			"tool_result": formatted_result,
			"error_message": (tool_result.error or None),
		})
		doc.save(ignore_permissions=True)
	except Exception as e:
		logger.debug(f"tool_invocation: failed to finalize Agent Tool Call telemetry: {e!s}")
