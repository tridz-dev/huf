"""Thin lazy wrappers the flow engine and tool layer call into the gateway layer with."""


def notify_approvers(flow_run) -> None:
	"""db_set does not fire doc events: offer Slack approval cards to linked approvers."""
	try:
		from huf.ai.gateways.approvals import notify_flow_run_approvers

		notify_flow_run_approvers(flow_run)
	except Exception:
		pass


def notify_failure(flow_run_name: str) -> None:
	"""db_set does not fire doc events, so tell gateway-originated senders explicitly."""
	try:
		from huf.ai.gateways.flow_reply import notify_flow_failure

		notify_flow_failure(flow_run_name)
	except Exception:
		pass


def tool_gate(name, args_dict, run_ctx: dict, requires_confirmation: bool):
	"""Gateway tool policy / confirm gate result string, or None to proceed (no-op outside gateway runs).

	The run id comes from the trusted run context, never from LLM-supplied args. An agent step of a test run
	gets a simulated answer instead of running any tool that would send or change something.
	"""
	from huf.ai.flow.testrun.gate import agent_tool_gate

	if (simulated := agent_tool_gate(name, args_dict, run_ctx)) is not None:
		return simulated
	from huf.ai.gateways import tool_policy

	return tool_policy.check_tool_call(name, args_dict, run_ctx.get("agent_run_id"), requires_confirmation)


def tool_executed(name, run_ctx: dict) -> None:
	from huf.ai.gateways import tool_policy

	tool_policy.note_tool_executed(name, run_ctx.get("agent_run_id"))
