"""Run-context helpers shared by the SDK tool wrappers."""


def _frappe_run_context_dict(ctx) -> dict:
    """Huf run context may be a dict or an Agents SDK ToolContext wrapping that dict."""
    if ctx is None:
        return {}
    if isinstance(ctx, dict):
        return ctx
    inner = getattr(ctx, "context", None)
    return inner if isinstance(inner, dict) else {}


def _pin_code_execution_identity(args_dict: dict, ctx) -> dict:
    """Overwrite ``conversation`` / ``agent_run`` (run_python's audit linkage) from the run
    context, discarding model-supplied values for them and for the ``*_id`` aliases."""
    huf_ctx = _frappe_run_context_dict(ctx)
    for key in ("conversation", "agent_run", "conversation_id", "agent_run_id"):
        args_dict.pop(key, None)
    if huf_ctx.get("conversation_id"):
        args_dict["conversation"] = huf_ctx["conversation_id"]
        args_dict["conversation_id"] = huf_ctx["conversation_id"]
    if huf_ctx.get("agent_run_id"):
        args_dict["agent_run"] = huf_ctx["agent_run_id"]
        args_dict["agent_run_id"] = huf_ctx["agent_run_id"]
    return args_dict
