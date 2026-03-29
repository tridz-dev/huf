"""
Huf Flow Engine v0.2

Core graph orchestration engine that:
- Loads and validates FlowDefinition JSON
- Creates FlowRun instances
- Executes nodes (agent.run, tool.call, router.llm, human.approval,
  http_request, condition, transform, loop, end)
- Evaluates edges (always, on_success, on_failure, expression)
- Persists FlowRun state after each step
- Publishes Frappe Realtime events for live UI tracking
- Supports normal and agentic execution modes
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.flow_eval import safe_eval_expression
from huf.ai.flow_orchestrator import (
	build_flow_context_system_message,
	build_orchestrator_prompt,
	build_router_prompt,
	parse_decision,
)
from huf.ai.flow_tool_executor import execute as execute_tool

DEFAULT_MAX_HOPS = 100


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def load_definition(flow_id: str) -> dict:
	"""
	Load and return a parsed FlowDefinition.

	Args:
	    flow_id: The flow_id (= FlowDefinition name)

	Returns:
	    dict: Parsed definition JSON
	"""
	doc = frappe.get_doc("Flow Definition", flow_id)
	if doc.status != "Active":
		frappe.throw(_("Flow '{0}' is not active (status: {1})").format(flow_id, doc.status))

	defn = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	return defn


def create_flow_run(
	flow_id: str,
	payload: dict | None = None,
	mode: str | None = None,
	conversation_mode: str | None = None,
	trigger_type: str = "Manual",
) -> "frappe.Document":
	"""
	Create a new FlowRun document from a FlowDefinition.

	Args:
	    flow_id: The flow_id to run
	    payload: Initial trigger payload / input
	    mode: Override mode (normal/agentic). If None, uses definition settings.
	    conversation_mode: Override conversation_mode. If None, uses definition settings.
	    trigger_type: Manual / Webhook / Schedule / Doc Event

	Returns:
	    Flow Run document
	"""
	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json

	settings = defn.get("settings", {})
	resolved_mode = mode or settings.get("mode", "normal")
	max_hops = settings.get("max_hops", DEFAULT_MAX_HOPS)

	# Create shared conversation if configured
	conversation = None
	conv_mode = conversation_mode or settings.get("conversation_mode", "flow_shared")
	if conv_mode == "flow_shared":
		conversation = _create_flow_conversation(flow_id, defn.get("entry"))

	flow_run = frappe.get_doc(
		{
			"doctype": "Flow Run",
			"flow_definition": flow_id,
			"flow_id": flow_id,
			"flow_version": defn_doc.version,
			"mode": resolved_mode.capitalize(),
			"status": "Queued",
			"current_node_id": defn.get("entry"),
			"hop_count": 0,
			"max_hops": max_hops,
			"context_json": json.dumps(payload or {}),
			"trigger_type": trigger_type,
			"trigger_payload": json.dumps(payload or {}),
			"conversation": conversation.name if conversation else None,
			"started_at": now_datetime(),
		}
	)
	flow_run.insert(ignore_permissions=True)
	frappe.db.commit()

	return flow_run


def run_flow(flow_run_name: str):
	"""
	Execute a flow run from its current position until completion or pause.

	This is the main execution loop. It:
	1. Loads the definition and flow run
	2. Starts at current_node_id
	3. Executes the node
	4. Evaluates outgoing edges
	5. Moves to the next node
	6. Repeats until end, pause, or hop limit

	Args:
	    flow_run_name: Name of the Flow Run document
	"""
	flow_run = frappe.get_doc("Flow Run", flow_run_name)
	defn = load_definition(flow_run.flow_id)

	# Build lookup maps
	nodes_map = {n["id"]: n for n in defn.get("nodes", [])}
	edges_list = defn.get("edges", [])
	settings = defn.get("settings", {})

	# Update status to Running
	flow_run.db_set({"status": "Running", "last_error": ""})
	frappe.db.commit()

	try:
		_execute_loop(flow_run, nodes_map, edges_list, settings)
	except Exception as e:
		_fail_flow_run(flow_run, str(e))
		frappe.log_error(f"Flow engine error: {frappe.get_traceback()}", "Flow Engine")


def resume_flow_run(flow_run_name: str, user_input: dict | None = None):
	"""
	Resume a paused flow run (Waiting User status).

	Args:
	    flow_run_name: Name of the Flow Run
	    user_input: Optional input to merge into context
	"""
	flow_run = frappe.get_doc("Flow Run", flow_run_name)

	if flow_run.status not in ("Waiting User", "Waiting Approval"):
		frappe.throw(_("Flow Run is not in a waiting state (status: {0})").format(flow_run.status))

	# Merge user input into context
	if user_input:
		ctx = _load_context(flow_run)
		ctx.update(user_input)
		flow_run.db_set("context_json", json.dumps(ctx, default=str))

	# Clear waiting state
	flow_run.db_set({"waiting": None, "status": "Running"})
	frappe.db.commit()

	# Continue execution
	run_flow(flow_run_name)


def approve_flow_run(flow_run_name: str, decision: str, comment: str | None = None):
	"""
	Approve or reject a flow run waiting for approval.

	Args:
	    flow_run_name: Name of the Flow Run
	    decision: "approved" or "rejected"
	    comment: Optional comment
	"""
	flow_run = frappe.get_doc("Flow Run", flow_run_name)

	if flow_run.status != "Waiting Approval":
		frappe.throw(_("Flow Run is not waiting for approval (status: {0})").format(flow_run.status))

	# Verify current user has approval permissions
	waiting = json.loads(flow_run.waiting) if flow_run.waiting else {}
	_verify_approval_permission(waiting)

	# Store decision in context
	ctx = _load_context(flow_run)
	store_key = waiting.get("store_decision_in_context", "approval")
	ctx[store_key] = {
		"decision": decision,
		"comment": comment,
		"approved_by": frappe.session.user,
		"approved_at": str(now_datetime()),
	}
	flow_run.db_set("context_json", json.dumps(ctx, default=str))

	# Find the outgoing edge matching the outcome
	defn = load_definition(flow_run.flow_id)
	edges_list = defn.get("edges", [])
	current_node = flow_run.current_node_id

	next_node = None
	for edge in edges_list:
		if edge.get("from") != current_node:
			continue
		edge_meta = edge.get("meta", {})
		if edge_meta.get("outcome") == decision:
			next_node = edge.get("to")
			break

	if not next_node:
		_fail_flow_run(flow_run, f"No edge found for outcome '{decision}' from node '{current_node}'")
		return

	# Move to the next node and resume
	flow_run.db_set({"current_node_id": next_node, "waiting": None, "status": "Running"})
	flow_run.db_set("hop_count", (flow_run.hop_count or 0) + 1)
	frappe.db.commit()

	run_flow(flow_run.name)


# ---------------------------------------------------------------------------
# Core execution loop
# ---------------------------------------------------------------------------


def _execute_loop(flow_run, nodes_map: dict, edges_list: list, settings: dict):
	"""Main execution loop - runs nodes and follows edges until done."""
	is_agentic = (flow_run.mode or "").lower() == "agentic"
	orch_policy = settings.get("orchestrator_call_policy", "after_each_node")
	completed_nodes = []

	while True:
		node_id = flow_run.current_node_id
		node = nodes_map.get(node_id)

		if not node:
			_publish_flow_event(flow_run, "flow_error", {"error": f"Node '{node_id}' not found"})
			_fail_flow_run(flow_run, f"Node '{node_id}' not found in definition")
			return

		# Check hop limit
		if (flow_run.hop_count or 0) >= (flow_run.max_hops or DEFAULT_MAX_HOPS):
			_publish_flow_event(flow_run, "flow_error", {"error": f"Hop limit reached ({flow_run.max_hops})"})
			_fail_flow_run(flow_run, f"Hop limit reached ({flow_run.max_hops})")
			return

		# Publish node start event for live UI tracking
		_publish_flow_event(flow_run, "flow_node_start", {
			"node_id": node_id,
			"node_type": node.get("type"),
			"node_label": node.get("_label", node_id),
		})

		# Execute the node
		node_result = _execute_node(flow_run, node, settings)

		# Publish node end event
		result_status = node_result.get("status", "success") if isinstance(node_result, dict) else "success"
		_publish_flow_event(flow_run, "flow_node_end", {
			"node_id": node_id,
			"node_type": node.get("type"),
			"status": result_status,
		})

		# Check if flow was paused (approval/user wait)
		flow_run.reload()
		if flow_run.status in ("Waiting Approval", "Waiting User"):
			_publish_flow_event(flow_run, "flow_paused", {
				"node_id": node_id,
				"status": flow_run.status,
			})
			return

		# Update hop count and completed list
		completed_nodes.append(node_id)
		flow_run.db_set("hop_count", (flow_run.hop_count or 0) + 1)
		frappe.db.commit()

		# Check for end node
		if node.get("type") == "end":
			_complete_flow_run(flow_run)
			_publish_flow_event(flow_run, "flow_completed", {
				"node_id": node_id,
				"status": "Success",
			})
			return

		# Determine next node
		next_node_id = None

		if node.get("type") == "router.llm":
			# Router already determined next_node_id via LLM
			next_node_id = node_result.get("next_node_id") if isinstance(node_result, dict) else None
			if not next_node_id:
				_fail_flow_run(flow_run, "Router node did not return a next_node_id")
				_publish_flow_event(flow_run, "flow_error", {"error": "Router did not return next_node_id"})
				return

		elif node.get("type") == "condition":
			# Condition node already evaluated and returns next_node_id
			next_node_id = node_result.get("next_node_id") if isinstance(node_result, dict) else None
			if not next_node_id:
				_fail_flow_run(flow_run, "Condition node did not resolve a branch")
				return

		elif node.get("type") == "human.approval":
			# Already paused above; this shouldn't be reached
			return

		elif is_agentic and _should_call_orchestrator(orch_policy, completed_nodes):
			# Agentic mode: ask orchestrator for next node
			candidates = _get_outgoing_edges(node_id, edges_list)
			if not candidates:
				_complete_flow_run(flow_run)
				return

			next_node_id = _call_orchestrator(
				flow_run, node_id, node_result, candidates, settings, completed_nodes
			)
			if not next_node_id:
				_fail_flow_run(flow_run, "Orchestrator did not return a valid next_node_id")
				return
		else:
			# Normal mode: evaluate edges deterministically
			next_node_id = _evaluate_edges(flow_run, node_id, node_result, edges_list)

		if not next_node_id:
			# No outgoing edges matched - flow is done
			_complete_flow_run(flow_run)
			_publish_flow_event(flow_run, "flow_completed", {"status": "Success"})
			return

		# Move to next node
		flow_run.db_set("current_node_id", next_node_id)
		frappe.db.commit()


# ---------------------------------------------------------------------------
# Node executors
# ---------------------------------------------------------------------------


def _execute_node(flow_run, node: dict, settings: dict) -> dict:
	"""
	Execute a single node and return the result.

	Dispatches to the appropriate executor based on node type.
	"""
	node_type = node.get("type")
	config = node.get("config", {})
	node_id = node.get("id")

	executors = {
		"trigger.webhook": _exec_trigger_webhook,
		"agent.run": _exec_agent_run,
		"tool.call": _exec_tool_call,
		"router.llm": _exec_router_llm,
		"human.approval": _exec_human_approval,
		"http_request": _exec_http_request,
		"condition": _exec_condition,
		"transform": _exec_transform,
		"loop": _exec_loop_node,
		"end": _exec_end,
	}

	executor = executors.get(node_type)
	if not executor:
		frappe.throw(_("Unknown node type: {0}").format(node_type))

	return executor(flow_run, node, config, settings)


def _exec_trigger_webhook(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute trigger.webhook node - mostly a passthrough for UI clarity."""
	# The trigger payload is already in the flow run context
	ctx = _load_context(flow_run)
	return {"status": "success", "output": ctx}


def _exec_agent_run(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute agent.run node - runs a Huf agent."""
	agent_name = config.get("agent_name")
	if not agent_name:
		return {"status": "failed", "error": "agent.run node missing agent_name in config"}

	ctx = _load_context(flow_run)

	# Build prompt from template or context
	prompt = _build_agent_prompt(config, ctx)

	# Determine conversation mode
	conv_mode = config.get("conversation_mode", "flow_shared")
	conversation_id = flow_run.conversation if conv_mode == "flow_shared" else None

	# Optionally inject flow context as system message
	inject_context = config.get("input", {}).get("inject_flow_context", False)
	if (flow_run.mode or "").lower() == "agentic":
		inject_context = config.get("input", {}).get("inject_flow_context", True)

	try:
		from huf.ai.agent_integration import run_agent_sync

		result = run_agent_sync(
			agent_name=agent_name,
			prompt=prompt,
			conversation_id=conversation_id,
			channel_id="flow",
			flow_run_id=flow_run.name,
			flow_node_id=node.get("id"),
			run_kind="agent",
		)

		# Update last_agent_run
		if result and result.get("agent_run_id"):
			flow_run.db_set("last_agent_run", result["agent_run_id"])

		# Save response to context if configured
		output_config = config.get("output", {})
		if output_config.get("save_response_to_context"):
			ctx[output_config["save_response_to_context"]] = result.get("response", "")
			flow_run.db_set("context_json", json.dumps(ctx, default=str))

		frappe.db.commit()

		return {
			"status": "success" if result.get("success") else "failed",
			"response": result.get("response", ""),
			"agent_run_id": result.get("agent_run_id"),
			"error": result.get("error"),
		}
	except Exception as e:
		return {"status": "failed", "error": str(e)}


def _exec_tool_call(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute tool.call node - deterministic tool execution."""
	tool_name = config.get("tool_name")
	if not tool_name:
		return {"status": "failed", "error": "tool.call node missing tool_name in config"}

	# Build args, potentially with context interpolation
	# Support both 'args' (preferred) and 'parameters' (legacy)
	args = dict(config.get("args") or config.get("parameters") or {})
	ctx = _load_context(flow_run)

	# Recursive context variable substitution
	import re
	
	def _substitute(data):
		if isinstance(data, dict):
			return {k: _substitute(v) for k, v in data.items()}
		elif isinstance(data, list):
			return [_substitute(v) for v in data]
		elif isinstance(data, str):
			# Handle inline templates like "Hello {{name}}"
			def replace_var(match):
				var_name = match.group(1).strip()
				return str(ctx.get(var_name, match.group(0)))
			return re.sub(r'\{\{(.*?)\}\}', replace_var, data)
		return data

	args = _substitute(args)

	# Create an Agent Run for auditing
	run_doc = _create_flow_agent_run(
		flow_run=flow_run,
		node=node,
		run_kind="tool",
		prompt=f"Tool: {tool_name}\nArgs: {json.dumps(args, default=str)}",
	)

	try:
		result = execute_tool(tool_name, args)

		# Update the agent run
		run_doc.db_set(
			{
				"status": "Success" if result.get("success") else "Failed",
				"response": json.dumps(result, default=str),
				"error_message": result.get("error", ""),
				"end_time": now_datetime(),
			}
		)
		flow_run.db_set("last_agent_run", run_doc.name)

		# Save result to context if configured
		output_config = config.get("output", {})
		if output_config.get("save_result_to_context"):
			ctx[output_config["save_result_to_context"]] = result.get("result", result)
			flow_run.db_set("context_json", json.dumps(ctx, default=str))

		frappe.db.commit()

		return {
			"status": "success" if result.get("success") else "failed",
			"result": result.get("result"),
			"error": result.get("error"),
		}
	except Exception as e:
		run_doc.db_set({"status": "Failed", "error_message": str(e), "end_time": now_datetime()})
		frappe.db.commit()
		return {"status": "failed", "error": str(e)}


def _exec_router_llm(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute router.llm node - LLM-based routing."""
	router_agent_name = config.get("router_agent_name")
	if not router_agent_name:
		return {"status": "failed", "error": "router.llm node missing router_agent_name in config"}

	ctx = _load_context(flow_run)
	defn = load_definition(flow_run.flow_id)
	edges_list = defn.get("edges", [])

	# Get candidates from outgoing edges
	candidates = _get_outgoing_edges(node.get("id"), edges_list)
	if not candidates:
		return {"status": "failed", "error": "router.llm node has no outgoing edges"}

	valid_node_ids = {c["to"] for c in candidates}

	# Build router prompt
	prompt = build_router_prompt(
		node_config=config,
		candidates=candidates,
		flow_context=ctx,
		last_node_result=None,
	)

	# Determine conversation mode
	conv_mode = config.get("conversation_mode", "flow_shared")
	conversation_id = flow_run.conversation if conv_mode == "flow_shared" else None

	# Call the router agent
	try:
		from huf.ai.agent_integration import run_agent_sync

		result = run_agent_sync(
			agent_name=router_agent_name,
			prompt=prompt,
			conversation_id=conversation_id,
			channel_id="flow_router",
			flow_run_id=flow_run.name,
			flow_node_id=node.get("id"),
			run_kind="orchestrator",
		)

		if not result.get("success"):
			return {"status": "failed", "error": result.get("error", "Router agent failed")}

		# Parse the decision
		decision = parse_decision(result.get("response", ""), valid_node_ids)

		# Apply context patch
		if decision.get("context_patch"):
			ctx.update(decision["context_patch"])
			flow_run.db_set("context_json", json.dumps(ctx, default=str))

		flow_run.db_set("last_agent_run", result.get("agent_run_id"))
		frappe.db.commit()

		return {
			"status": "success",
			"next_node_id": decision["next_node_id"],
			"message": decision.get("message", ""),
			"reason": decision.get("reason", ""),
		}
	except Exception as e:
		return {"status": "failed", "error": str(e)}


def _exec_human_approval(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute human.approval node - pause for human decision."""
	# Interpolate context_summary, reference_name if they contain {{variables}}
	ctx = _load_context(flow_run)
	context_summary = config.get("context_summary", "")
	reference_name = config.get("reference_name", "")
	if context_summary:
		context_summary = _interpolate_string(context_summary, ctx)
	if reference_name:
		reference_name = _interpolate_string(reference_name, ctx)

	waiting_data = {
		"type": "approval",
		"node_id": node.get("id"),
		"approval_type": config.get("approval_type", "role"),
		"approver_role": config.get("approver_role"),
		"approver_users": config.get("approver_users", []),
		"title": config.get("title", "Approval Required"),
		"instructions": config.get("instructions", ""),
		"context_summary": context_summary,
		"reference_doctype": config.get("reference_doctype", ""),
		"reference_name": reference_name,
		"store_decision_in_context": config.get("store_decision_in_context", "approval"),
	}

	flow_run.db_set(
		{
			"status": "Waiting Approval",
			"waiting": json.dumps(waiting_data),
		}
	)
	frappe.db.commit()

	return {"status": "waiting_approval"}


def _exec_http_request(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute http_request node - makes an HTTP request.

	Config keys:
	    url (str): Target URL (supports {{ }} variable interpolation)
	    method (str): GET, POST, PUT, DELETE (default: GET)
	    headers (dict): Optional request headers
	    body (dict|str): Optional request body for POST/PUT
	    timeout (int): Request timeout in seconds (default: 30)
	    save_result_to_context (str): Context key to store result
	"""
	import requests as http_lib

	url = config.get("url")
	if not url:
		return {"status": "failed", "error": "http_request node missing 'url' in config"}

	ctx = _load_context(flow_run)

	# Interpolate variables in url, headers, and body
	url = _interpolate_string(url, ctx)
	method = (config.get("method") or "GET").upper()
	headers = config.get("headers", {})
	if isinstance(headers, dict):
		headers = {k: _interpolate_string(str(v), ctx) for k, v in headers.items()}

	body = config.get("body")
	if isinstance(body, dict):
		body = _substitute_dict(body, ctx)
	elif isinstance(body, str):
		body = _interpolate_string(body, ctx)

	timeout = config.get("timeout", 30)

	try:
		kwargs = {"headers": headers, "timeout": timeout}
		if method in ("POST", "PUT", "PATCH") and body:
			if isinstance(body, dict):
				kwargs["json"] = body
			else:
				kwargs["data"] = body

		resp = http_lib.request(method, url, **kwargs)

		try:
			result_data = resp.json()
		except Exception:
			result_data = resp.text

		result = {
			"status_code": resp.status_code,
			"data": result_data,
			"headers": dict(resp.headers),
		}

		# Save to context if configured
		save_key = config.get("save_result_to_context")
		if save_key:
			ctx[save_key] = result
			flow_run.db_set("context_json", json.dumps(ctx, default=str))

		frappe.db.commit()

		is_success = 200 <= resp.status_code < 400
		return {
			"status": "success" if is_success else "failed",
			"result": result,
		}
	except Exception as e:
		return {"status": "failed", "error": str(e)}


def _exec_condition(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute condition node - evaluates a boolean expression and routes
	to true_branch or false_branch.

	This is HUF's equivalent to n8n's IF node with explicit branch ports.

	Config keys:
	    expression (str): Boolean expression to evaluate against context
	    true_node (str): Node ID to go to if expression is true
	    false_node (str): Node ID to go to if expression is false
	"""
	expression = config.get("expression", "")
	true_node = config.get("true_node")
	false_node = config.get("false_node")

	if not expression:
		return {"status": "failed", "error": "condition node missing 'expression' in config"}

	if not true_node and not false_node:
		return {"status": "failed", "error": "condition node needs at least one of 'true_node' or 'false_node'"}

	ctx = _load_context(flow_run)

	try:
		result = safe_eval_expression(expression, ctx)
		chosen_node = true_node if result else false_node

		if not chosen_node:
			# If we evaluated to a branch that has no target, consider it done
			return {"status": "success", "result": result, "next_node_id": None}

		return {
			"status": "success",
			"result": result,
			"branch": "true" if result else "false",
			"next_node_id": chosen_node,
		}
	except Exception as e:
		return {"status": "failed", "error": f"Condition evaluation failed: {str(e)}"}


def _exec_transform(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute transform node - applies data transformations to context.

	Config keys:
	    transformations (list): List of transformation operations
	        Each with: source_field, target_field, operation (copy|map|template)
	    save_result_to_context (str): Optional key to store result
	"""
	ctx = _load_context(flow_run)
	transformations = config.get("transformations", [])

	results = {}
	for t in transformations:
		source = t.get("source_field", "")
		target = t.get("target_field", "")
		operation = t.get("operation", "copy")

		if not source or not target:
			continue

		try:
			if operation == "copy":
				# Direct copy from context
				value = _resolve_context_path(ctx, source)
				ctx[target] = value
				results[target] = value
			elif operation == "template":
				# Interpolate a template string
				value = _interpolate_string(source, ctx)
				ctx[target] = value
				results[target] = value
			elif operation == "map":
				# Map/rename: get source data and store under target
				value = _resolve_context_path(ctx, source)
				ctx[target] = value
				results[target] = value
		except Exception as e:
			results[target] = f"Error: {str(e)}"

	flow_run.db_set("context_json", json.dumps(ctx, default=str))
	frappe.db.commit()

	return {"status": "success", "result": results}


def _exec_loop_node(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute loop node - iterates over an array in context.

	The loop node works by checking if there are remaining items to iterate.
	If yes, it sets the current item in context and returns the loop_node (body).
	If no, it returns the done_node.

	Config keys:
	    iterate_over (str): Context key containing the array to iterate
	    item_key (str): Context key to store current item (default: 'loop_item')
	    index_key (str): Context key to store current index (default: 'loop_index')
	    loop_node (str): Node ID to execute for each iteration (loop body)
	    done_node (str): Node ID to go to when iteration is complete
	    max_iterations (int): Safety limit (default: 100)
	"""
	ctx = _load_context(flow_run)

	iterate_over = config.get("iterate_over", "")
	item_key = config.get("item_key", "loop_item")
	index_key = config.get("index_key", "loop_index")
	loop_node = config.get("loop_node")
	done_node = config.get("done_node")
	max_iter = config.get("max_iterations", 100)

	if not iterate_over:
		return {"status": "failed", "error": "loop node missing 'iterate_over' in config"}

	# Get the array to iterate over
	items = _resolve_context_path(ctx, iterate_over)
	if not isinstance(items, list):
		return {"status": "failed", "error": f"'{iterate_over}' is not a list in context"}

	# Get current iteration index
	current_index = ctx.get(index_key, 0)
	if not isinstance(current_index, int):
		current_index = 0

	# Safety check
	if current_index >= max_iter:
		ctx.pop(item_key, None)
		ctx.pop(index_key, None)
		flow_run.db_set("context_json", json.dumps(ctx, default=str))
		frappe.db.commit()
		return {"status": "success", "result": "max_iterations reached", "next_node_id": done_node}

	if current_index < len(items):
		# Set current item and advance index
		ctx[item_key] = items[current_index]
		ctx[index_key] = current_index + 1
		flow_run.db_set("context_json", json.dumps(ctx, default=str))
		frappe.db.commit()
		return {"status": "success", "result": items[current_index], "next_node_id": loop_node}
	else:
		# Iteration complete - clean up loop variables
		ctx.pop(item_key, None)
		ctx.pop(index_key, None)
		flow_run.db_set("context_json", json.dumps(ctx, default=str))
		frappe.db.commit()
		return {"status": "success", "result": "iteration_complete", "next_node_id": done_node}


def _exec_end(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute end node - marks success."""
	return {"status": "success", "output": "flow_complete"}


# ---------------------------------------------------------------------------
# Edge evaluation
# ---------------------------------------------------------------------------


def _evaluate_edges(flow_run, node_id: str, node_result: dict, edges_list: list) -> str | None:
	"""
	Evaluate outgoing edges from a node and return the next node ID.

	Edges are sorted by priority (desc) and the first matching edge wins.
	"""
	outgoing = [e for e in edges_list if e.get("from") == node_id]
	if not outgoing:
		return None

	# Sort by priority descending
	outgoing.sort(key=lambda e: e.get("priority", 0), reverse=True)

	ctx = _load_context(flow_run)
	node_status = node_result.get("status", "success") if isinstance(node_result, dict) else "success"

	for edge in outgoing:
		edge_type = edge.get("type", "always")

		if edge_type == "always":
			return edge.get("to")

		elif edge_type == "on_success":
			if node_status == "success":
				return edge.get("to")

		elif edge_type == "on_failure":
			if node_status == "failed":
				return edge.get("to")

		elif edge_type == "expression":
			condition = edge.get("condition", "")
			try:
				if safe_eval_expression(condition, ctx):
					return edge.get("to")
			except Exception as e:
				frappe.log_error(
					f"Edge expression error ({condition}): {str(e)}",
					"Flow Engine Edge Eval",
				)

	return None


def _get_outgoing_edges(node_id: str, edges_list: list) -> list[dict]:
	"""Get outgoing edges from a node as candidate list."""
	candidates = []
	for edge in edges_list:
		if edge.get("from") == node_id:
			candidates.append(
				{
					"to": edge.get("to"),
					"edge_id": edge.get("id"),
					"label": edge.get("meta", {}).get("label", ""),
					"meta": edge.get("meta", {}),
				}
			)
	return candidates


# ---------------------------------------------------------------------------
# Agentic mode helpers
# ---------------------------------------------------------------------------


def _should_call_orchestrator(policy: str, completed_nodes: list) -> bool:
	"""Determine if orchestrator should be called based on policy."""
	if policy == "start_and_after_each_node":
		return True
	if policy == "after_each_node":
		return len(completed_nodes) > 0
	return False


def _call_orchestrator(
	flow_run, current_node_id: str, node_result: dict, candidates: list, settings: dict, completed_nodes: list
) -> str | None:
	"""Call the orchestrator agent and return the chosen next_node_id."""
	orchestrator_agent = settings.get("orchestrator_agent")
	if not orchestrator_agent:
		frappe.log_error("Agentic mode requires orchestrator_agent in settings", "Flow Engine")
		return None

	ctx = _load_context(flow_run)
	valid_node_ids = {c["to"] for c in candidates}

	prompt = build_orchestrator_prompt(
		current_node_id=current_node_id,
		current_node_result=node_result,
		flow_context=ctx,
		candidates=candidates,
		completed_summary=", ".join(completed_nodes),
	)

	conv_mode = settings.get("conversation_mode", "flow_shared")
	conversation_id = flow_run.conversation if conv_mode == "flow_shared" else None

	try:
		from huf.ai.agent_integration import run_agent_sync

		result = run_agent_sync(
			agent_name=orchestrator_agent,
			prompt=prompt,
			conversation_id=conversation_id,
			channel_id="flow_orchestrator",
			flow_run_id=flow_run.name,
			flow_node_id=current_node_id,
			run_kind="orchestrator",
		)

		if not result.get("success"):
			frappe.log_error(f"Orchestrator failed: {result.get('error')}", "Flow Engine Orchestrator")
			return None

		decision = parse_decision(result.get("response", ""), valid_node_ids)

		# Apply context patch
		if decision.get("context_patch"):
			ctx.update(decision["context_patch"])
			flow_run.db_set("context_json", json.dumps(ctx, default=str))

		flow_run.db_set("last_agent_run", result.get("agent_run_id"))
		frappe.db.commit()

		return decision["next_node_id"]

	except Exception as e:
		frappe.log_error(f"Orchestrator error: {str(e)}", "Flow Engine Orchestrator")
		return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_context(flow_run) -> dict:
	"""Load the flow context from the flow run document."""
	if not flow_run.context_json:
		return {}
	try:
		ctx = json.loads(flow_run.context_json) if isinstance(flow_run.context_json, str) else flow_run.context_json
		return ctx if isinstance(ctx, dict) else {}
	except (json.JSONDecodeError, TypeError):
		return {}


def _build_agent_prompt(config: dict, context: dict) -> str:
	"""Build agent prompt from config template and context."""
	input_config = config.get("input", {})
	prompt_template = input_config.get("prompt_template")

	if prompt_template:
		# Simple template variable substitution
		prompt = prompt_template
		for key, value in context.items():
			placeholder = "{{" + key + "}}"
			if placeholder in prompt:
				prompt = prompt.replace(placeholder, str(value) if not isinstance(value, str) else value)
		return prompt

	# Default: serialize the context as the prompt
	return json.dumps(context, indent=2, default=str)


def _create_flow_agent_run(flow_run, node: dict, run_kind: str, prompt: str = "") -> "frappe.Document":
	"""Create an Agent Run document linked to a flow run."""
	run_doc = frappe.get_doc(
		{
			"doctype": "Agent Run",
			"status": "Started",
			"prompt": prompt,
			"flow_run": flow_run.name,
			"flow_node_id": node.get("id"),
			"flow_id": flow_run.flow_id,
			"run_kind": run_kind,
			"start_time": now_datetime(),
		}
	)
	run_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return run_doc


def _create_flow_conversation(flow_id: str, entry_node_id: str) -> "frappe.Document":
	"""Create a shared Agent Conversation for a flow run."""
	from uuid import uuid4

	conv = frappe.get_doc(
		{
			"doctype": "Agent Conversation",
			"title": f"Flow: {flow_id}",
			"session_id": f"flow:{flow_id}:{uuid4().hex[:8]}",
			"is_active": 1,
		}
	)
	conv.insert(ignore_permissions=True)
	frappe.db.commit()
	return conv


def _verify_approval_permission(waiting: dict):
	"""Verify that the current user has permission to approve."""
	approval_type = waiting.get("approval_type", "role")
	user = frappe.session.user

	if approval_type == "user":
		approver_users = waiting.get("approver_users", [])
		if approver_users and user not in approver_users:
			frappe.throw(
				_("You are not authorized to approve this flow run"),
				frappe.PermissionError,
			)
	elif approval_type == "role":
		approver_role = waiting.get("approver_role")
		if approver_role:
			user_roles = frappe.get_roles(user)
			if approver_role not in user_roles:
				frappe.throw(
					_("You do not have the required role '{0}' to approve").format(approver_role),
					frappe.PermissionError,
				)


def _complete_flow_run(flow_run):
	"""Mark a flow run as successfully completed."""
	flow_run.db_set(
		{
			"status": "Success",
			"completed_at": now_datetime(),
		}
	)
	frappe.db.commit()


def _fail_flow_run(flow_run, error_msg: str):
	"""Mark a flow run as failed."""
	flow_run.db_set(
		{
			"status": "Failed",
			"last_error": error_msg,
			"completed_at": now_datetime(),
		}
	)
	frappe.db.commit()
	_publish_flow_event(flow_run, "flow_failed", {"error": error_msg})


# ---------------------------------------------------------------------------
# Realtime event publishing
# ---------------------------------------------------------------------------


def _publish_flow_event(flow_run, event_type: str, data: dict):
	"""Publish a Frappe Realtime event for live flow UI tracking."""
	try:
		frappe.publish_realtime(
			event=event_type,
			message={
				"flow_run_id": flow_run.name,
				"flow_id": flow_run.flow_id,
				**data,
			},
			after_commit=False,
		)
	except Exception:
		# Realtime is best-effort; don't break execution if it fails
		pass


# ---------------------------------------------------------------------------
# Additional string/context helpers
# ---------------------------------------------------------------------------


def _interpolate_string(template: str, ctx: dict) -> str:
	"""Replace {{ key }} placeholders in a string with values from context."""
	import re

	def replacer(match):
		key = match.group(1).strip()
		value = _resolve_context_path(ctx, key)
		return str(value) if value is not None else match.group(0)

	return re.sub(r"\{\{\s*(.+?)\s*\}\}", replacer, template)


def _substitute_dict(data, ctx: dict):
	"""Recursively substitute {{ key }} in dict/list/str values."""
	if isinstance(data, dict):
		return {k: _substitute_dict(v, ctx) for k, v in data.items()}
	elif isinstance(data, list):
		return [_substitute_dict(v, ctx) for v in data]
	elif isinstance(data, str) and "{{" in data and "}}" in data:
		return _interpolate_string(data, ctx)
	return data


def _resolve_context_path(ctx: dict, path: str):
	"""Resolve a dotted path like 'user_data.email' from context dict."""
	parts = path.split(".")
	current = ctx
	for part in parts:
		if isinstance(current, dict):
			current = current.get(part)
		else:
			return None
	return current
