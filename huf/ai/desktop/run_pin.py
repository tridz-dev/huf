"""Server-side run identity pinning for Desktop Workspace tool args (used by ``sdk_tools``)."""


def pin_run_identity(args_dict: dict, ctx, nonce: str = None) -> dict:
	"""Overwrite (never default) the run identity args from the server-side run context.

	Used by tools that must not trust the model for who/what run they act on
	(Desktop Workspace tools): ``agent_run_id`` and ``conversation_id`` come only from
	the run context, and ``call_id`` is derived deterministically from the run and the
	SDK ``tool_call_id`` so a redelivered or retried call dedupes. Anything the model
	sent for these keys is discarded.
	"""
	from huf.ai.desktop.executor import derive_call_id
	from huf.ai.sdk_tools import _frappe_run_context_dict

	huf_ctx = _frappe_run_context_dict(ctx)
	for key in ("agent_run_id", "conversation_id"):
		args_dict.pop(key, None)
		if huf_ctx.get(key):
			args_dict[key] = huf_ctx[key]
	args_dict.pop("call_id", None)
	args_dict.pop("_dx_pin", None)  # minted below by the caller, never taken from the model
	tool_call_id = getattr(ctx, "tool_call_id", None)
	if tool_call_id and args_dict.get("agent_run_id"):
		args_dict["call_id"] = derive_call_id(args_dict["agent_run_id"], tool_call_id, nonce)
	# The exact LLM-issued id, sent on its own so the desktop can join its feed to the chat row.
	args_dict.pop("tool_call_id", None)
	if tool_call_id and isinstance(tool_call_id, str):
		args_dict["tool_call_id"] = tool_call_id[:256]
	return args_dict
