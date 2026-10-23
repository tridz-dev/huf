"""
Flow Orchestrator for Huf Flow Engine.

Handles prompt construction and strict JSON parsing/validation for
router.llm nodes and agentic mode orchestrator decisions.
"""

import json

import frappe
from frappe import _


def build_router_prompt(
	node_config: dict,
	candidates: list[dict],
	flow_context: dict,
	last_node_result: dict | None = None,
) -> str:
	"""
	Build the prompt for a router.llm node.

	Args:
	    node_config: The router node's config
	    candidates: List of candidate edges with {to, edge_id, label/meta}
	    flow_context: Current flow context
	    last_node_result: Result from the last executed node

	Returns:
	    str: Formatted prompt for the router agent
	"""
	include_context = node_config.get("inject", {}).get("include_context", True)
	include_last = node_config.get("inject", {}).get("include_last_node_result", True)
	include_candidates_flag = node_config.get("inject", {}).get("include_candidates", True)

	parts = [
		"You are a routing agent in a workflow. Your job is to decide which node to execute next.",
		"You MUST respond with ONLY a JSON object (no markdown, no explanation).",
		"",
		"Required response format:",
		'{',
		'  "next_node_id": "<one of the candidate node IDs>",',
		'  "context_patch": {},',
		'  "message": "<optional reasoning>",',
		'  "reason": "<optional audit note>"',
		'}',
		"",
	]

	if include_context and flow_context:
		parts.append("## Current Flow Context")
		parts.append("```json")
		parts.append(json.dumps(flow_context, indent=2, default=str))
		parts.append("```")
		parts.append("")

	if include_last and last_node_result:
		parts.append("## Last Node Result")
		parts.append("```json")
		parts.append(json.dumps(last_node_result, indent=2, default=str))
		parts.append("```")
		parts.append("")

	if include_candidates_flag and candidates:
		parts.append("## Candidate Destinations (you MUST choose one)")
		for c in candidates:
			label = c.get("label") or c.get("meta", {}).get("label", "")
			desc = f" - {label}" if label else ""
			parts.append(f"- Node ID: `{c['to']}`{desc}")
		parts.append("")

	parts.append("Choose the best next node based on the context and respond with ONLY the JSON object.")

	return "\n".join(parts)


def build_orchestrator_prompt(
	current_node_id: str,
	current_node_result: dict | None,
	flow_context: dict,
	candidates: list[dict],
	completed_summary: str | None = None,
) -> str:
	"""
	Build the prompt for agentic mode orchestrator.

	Args:
	    current_node_id: ID of the node that just completed
	    current_node_result: Result from the completed node
	    flow_context: Current flow context
	    candidates: Reachable outgoing edges
	    completed_summary: Optional summary of completed nodes

	Returns:
	    str: Formatted prompt for the orchestrator agent
	"""
	parts = [
		"You are the orchestrator of a workflow. A node has just completed.",
		"You must decide what to do next.",
		"Respond with ONLY a JSON object (no markdown, no explanation).",
		"",
		"Required response format:",
		'{',
		'  "next_node_id": "<one of the candidate node IDs>",',
		'  "context_patch": {},',
		'  "message": "<optional message>"',
		'}',
		"",
		f"## Completed Node: `{current_node_id}`",
		"",
	]

	if current_node_result:
		parts.append("### Node Result")
		parts.append("```json")
		parts.append(json.dumps(current_node_result, indent=2, default=str))
		parts.append("```")
		parts.append("")

	if completed_summary:
		parts.append(f"### Completed So Far: {completed_summary}")
		parts.append("")

	if flow_context:
		parts.append("## Current Flow Context")
		parts.append("```json")
		parts.append(json.dumps(flow_context, indent=2, default=str))
		parts.append("```")
		parts.append("")

	if candidates:
		parts.append("## Reachable Next Nodes (you MUST choose one)")
		for c in candidates:
			label = c.get("label") or c.get("meta", {}).get("label", "")
			desc = f" - {label}" if label else ""
			parts.append(f"- Node ID: `{c['to']}`{desc}")
		parts.append("")

	parts.append("Choose the best next node and respond with ONLY the JSON object.")

	return "\n".join(parts)


def parse_decision(raw_response: str, valid_node_ids: set[str]) -> dict:
	"""
	Parse and validate a router/orchestrator JSON decision.

	Args:
	    raw_response: Raw text response from the LLM
	    valid_node_ids: Set of valid candidate node IDs

	Returns:
	    dict with keys:
	        next_node_id (str): Validated next node ID
	        context_patch (dict): Optional context update
	        message (str): Optional message
	        reason (str): Optional reason

	Raises:
	    frappe.ValidationError: If response is invalid or next_node_id is not reachable
	"""
	# Try to extract JSON from the response
	response_text = raw_response.strip()

	# Strip markdown code fences if present
	if response_text.startswith("```"):
		lines = response_text.split("\n")
		# Remove first and last lines if they're code fences
		if lines[0].startswith("```"):
			lines = lines[1:]
		if lines and lines[-1].strip() == "```":
			lines = lines[:-1]
		response_text = "\n".join(lines).strip()

	try:
		decision = json.loads(response_text)
	except json.JSONDecodeError:
		# Try to extract JSON object from surrounding text by finding balanced braces
		decision = _extract_json_object(response_text)
		if decision is None:
			frappe.throw(
				_("Router/orchestrator response does not contain valid JSON: {0}").format(
					response_text[:200]
				),
				frappe.ValidationError,
			)

	if not isinstance(decision, dict):
		frappe.throw(
			_("Router/orchestrator response must be a JSON object"),
			frappe.ValidationError,
		)

	next_node_id = decision.get("next_node_id")
	if not next_node_id:
		frappe.throw(
			_("Router/orchestrator response missing 'next_node_id'"),
			frappe.ValidationError,
		)

	if next_node_id not in valid_node_ids:
		frappe.throw(
			_("next_node_id '{0}' is not a valid candidate. Valid: {1}").format(
				next_node_id, ", ".join(sorted(valid_node_ids))
			),
			frappe.ValidationError,
		)

	# Validate context_patch is JSON-serializable
	context_patch = decision.get("context_patch", {})
	if context_patch and not isinstance(context_patch, dict):
		frappe.throw(
			_("context_patch must be a JSON object"),
			frappe.ValidationError,
		)

	return {
		"next_node_id": next_node_id,
		"context_patch": context_patch if isinstance(context_patch, dict) else {},
		"message": decision.get("message", ""),
		"reason": decision.get("reason", ""),
	}


def build_flow_context_system_message(flow_context: dict, current_node: str, completed_nodes: list) -> str:
	"""
	Build a system message to inject into agent runs within a flow.

	Used when running agents inside a flow (especially agentic mode)
	to give the agent awareness of the flow state.

	Args:
	    flow_context: Current flow context JSON
	    current_node: Current node ID
	    completed_nodes: List of completed node IDs

	Returns:
	    str: System message for injection
	"""
	parts = ["CURRENT FLOW CONTEXT:"]
	parts.append(json.dumps(flow_context, indent=2, default=str))
	parts.append("")
	parts.append(f"FLOW STATUS: Current node: {current_node}")
	if completed_nodes:
		parts.append(f"Completed nodes: {', '.join(completed_nodes)}")

	return "\n".join(parts)


def _extract_json_object(text: str) -> dict | None:
	"""
	Extract the first valid JSON object from text by finding balanced braces.

	Handles nested JSON objects correctly unlike simple regex.
	"""
	start = text.find("{")
	if start == -1:
		return None

	depth = 0
	in_string = False
	escape_next = False

	for i in range(start, len(text)):
		c = text[i]
		if escape_next:
			escape_next = False
			continue
		if c == "\\":
			escape_next = True
			continue
		if c == '"':
			in_string = not in_string
			continue
		if in_string:
			continue
		if c == "{":
			depth += 1
		elif c == "}":
			depth -= 1
			if depth == 0:
				try:
					return json.loads(text[start : i + 1])
				except json.JSONDecodeError:
					return None

	return None
