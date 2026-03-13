"""
Flow Engine tool definitions for the huf_tools hook.

Registers flow-related tools (run_flow, get_flow_run, resume_flow_run,
approve_flow_run) so agents can interact with flows.
"""

flow_tool_definitions = [
	{
		"tool_name": "run_flow",
		"description": "Start a flow execution. Creates a new Flow Run and executes the flow graph. Returns the flow_run_id, status, and current_node_id.",
		"function_path": "ivendnext_ai_agents.ai.flow_api.handle_run_flow",
		"parameters": [
			{
				"parameter_name": "flow_id",
				"type": "string",
				"description": "The Flow ID to run",
				"required": 1,
			},
			{
				"parameter_name": "payload",
				"type": "string",
				"description": "Initial payload/input for the flow (JSON object or string)",
				"required": 0,
			},
			{
				"parameter_name": "mode",
				"type": "string",
				"description": "Execution mode override: 'normal' or 'agentic'",
				"required": 0,
			},
		],
	},
	{
		"tool_name": "get_flow_run",
		"description": "Get the current status and details of a flow run. Returns status, current_node_id, context summary, and waiting state.",
		"function_path": "ivendnext_ai_agents.ai.flow_api.handle_get_flow_run",
		"parameters": [
			{
				"parameter_name": "flow_run_id",
				"type": "string",
				"description": "The Flow Run ID to check",
				"required": 1,
			},
		],
	},
	{
		"tool_name": "resume_flow_run",
		"description": "Resume a flow run that is waiting for user input. Optionally merge additional input into the flow context.",
		"function_path": "ivendnext_ai_agents.ai.flow_api.handle_resume_flow_run",
		"parameters": [
			{
				"parameter_name": "flow_run_id",
				"type": "string",
				"description": "The Flow Run ID to resume",
				"required": 1,
			},
			{
				"parameter_name": "input",
				"type": "object",
				"description": "Input data to merge into flow context (JSON object)",
				"required": 0,
			},
		],
	},
	{
		"tool_name": "approve_flow_run",
		"description": "Approve or reject a flow run that is waiting for human approval. The decision must be 'approved' or 'rejected'.",
		"function_path": "ivendnext_ai_agents.ai.flow_api.handle_approve_flow_run",
		"parameters": [
			{
				"parameter_name": "flow_run_id",
				"type": "string",
				"description": "The Flow Run ID to approve/reject",
				"required": 1,
			},
			{
				"parameter_name": "decision",
				"type": "string",
				"description": "The approval decision: 'approved' or 'rejected'",
				"required": 1,
			},
			{
				"parameter_name": "comment",
				"type": "string",
				"description": "Optional comment explaining the decision",
				"required": 0,
			},
		],
	},
]