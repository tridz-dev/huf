"""Deterministic tool executor for Flow Engine tool.call nodes.

Thin delegator onto ``huf.ai.tool_invocation`` -- the single resolve+invoke
path shared with the LLM tool path (``sdk_tools.py``). Resolution, the
permission gate (guest/mutating-type check, ``ignore_permissions``
stripping, guest doctype pinning), signature-aware argument filtering, and
coroutine handling all now live there; see ``tool_invocation.py`` and
``TRACK/spec/tool-invocation-seam.md`` for the audit this replaces.

Public contract is unchanged: ``execute(tool_name, args, user=None)`` still
returns ``{"success": bool, "result": Any, "error": str}``.
"""

import contextvars
from contextlib import contextmanager

import frappe

from huf.ai.tool_invocation import RunContext, invoke_tool_sync

_ambient_run_context: contextvars.ContextVar = contextvars.ContextVar(
	"huf_flow_tool_run_context", default=None
)


@contextmanager
def tool_run_context(ctx: RunContext):
	"""Bind a ``RunContext`` for tool calls made inside this block.

	``execute()`` owns telemetry now (I5/GT-05), so it needs the correlation
	ids -- conversation, Agent Run -- that only the caller knows. Passing them
	as an extra argument is not available to every caller (``flow_engine``
	invokes ``execute`` through a two-argument seam its test suite pins), so
	they are bound ambiently instead, for the duration of the call.
	"""
	token = _ambient_run_context.set(ctx)
	try:
		yield ctx
	finally:
		_ambient_run_context.reset(token)


def execute(
	tool_name: str,
	args: dict,
	user: str = None,
	*,
	ctx: RunContext = None,
	telemetry: bool = True,
) -> dict:
	"""
	Execute an Agent Tool Function deterministically.

	Finds the tool by tool_name, resolves its handler function via the
	shared ``huf.ai.tool_invocation`` resolver, and executes it with the
	provided arguments -- the same resolution and permission enforcement
	used by the LLM tool path (``sdk_tools.py``), so results and access
	control match agent tool calls exactly.

	Args:
	    tool_name: Must match an Agent Tool Function.tool_name (or one of
	        the built-in standard-tool aliases).
	    args: Arguments to pass to the tool handler.
	    user: User to execute as (defaults to current session user).
	    ctx: Optional RunContext (conversation_id/agent_run_id/agent_name/
	        call_id) for callers that want run-context injection and/or
	        telemetry correlation. Existing callers that don't pass one keep
	        working exactly as before.
	    telemetry: When True (the default since T-22), this call owns its
	        own ``Agent Tool Call`` Started/Completed-Failed record (GT-05,
	        invariant I5). ``flow_engine`` no longer assembles one itself, so
	        this is the single emission point for the deterministic path --
	        exactly one record per atomic operation. Pass False only from a
	        caller that genuinely owns its own telemetry.

	Returns:
	    dict with keys:
	        success (bool): Whether execution succeeded
	        result (any): Tool result if successful
	        error (str): Error message if failed
	"""
	if ctx is None:
		ctx = _ambient_run_context.get()

	if user:
		original_user = frappe.session.user
		frappe.set_user(user)

	try:
		result = invoke_tool_sync(tool_name, args, ctx=ctx, telemetry=telemetry)
		return result.as_dict()
	finally:
		if user:
			frappe.set_user(original_user)
