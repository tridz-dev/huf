"""The flow-level ``error_handler`` chain: runs once after a failure the graph did not route."""

from __future__ import annotations


def first_error(flow_run, settings, fallback):
	"""The first failure stored by the error handler (a ``{node_id, message}`` dict), else ``fallback``.

	``error`` is an ordinary variable name, so a value a step wrote there does not count.
	"""
	from huf.ai.flow import engine

	err = engine._context_of(flow_run, settings).data.get("error")
	if isinstance(err, dict) and "node_id" in err and "message" in err:
		return err["message"] or fallback
	return fallback


def run_error_handler(flow_run, program, router, handlers, policy, settings, node_id, message):
	"""Run the flow's ``error_handler`` chain once after a failure the graph did not route.

	Returns ``None`` when the caller should go on to fail the run (no handler, the failure came from
	the handler chain itself, or the chain ended or failed): the run always ends ``Failed``, the handler
	only gets to react first. Returns the executor result if the handler chain parked the run; when it
	later resumes and ends, the run still ends ``Failed``: ``context.data["error"]`` carries the first
	failure across the park.
	"""
	from huf.ai.flow import engine
	from huf.ai.graph.executor import ExecutionResult, ExecutionState, GraphExecutor

	run_ctx = engine._run_context(settings)
	graph = run_ctx.version.graph if run_ctx is not None and run_ctx.version is not None else {}
	handler_id = (graph.get("error_handler") or {}).get("next")
	if not handler_id or handler_id not in program.nodes:
		return None

	context = engine._context_of(flow_run, settings)
	if first_error(flow_run, settings, None):
		return None  # already inside the handler chain: no recursion
	context.data["error"] = {"node_id": node_id, "message": message}
	context.dirty = True

	state = ExecutionState(cursor=handler_id, hop_count=getattr(flow_run, "hop_count", 0) or 0, status="running")
	flow_run.db_set("current_node_id", handler_id)
	result = GraphExecutor(
		program,
		handlers,
		router=router,
		policy=policy,
		store=engine._FlowStateStore(flow_run, settings),
		listener=engine._FlowEventListener(flow_run),
	).run(context, state)
	engine._persist_context(flow_run, context, settings)
	return result if result.status == ExecutionResult.PAUSED else None
