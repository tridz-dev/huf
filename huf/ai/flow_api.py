"""
Whitelisted API endpoints for Huf Flow Engine.

Provides REST-style APIs for:
- Flow Definition management (get, save)
- Flow Run lifecycle (run, get, list, resume, approve, reject)
- Webhook trigger endpoint
- Agent tools (run_flow, get_flow_run, resume_flow_run, approve/reject)
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime


# ---------------------------------------------------------------------------
# Flow Definition APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_flow_definition(flow_id: str) -> dict:
	"""
	Get a flow definition.

	Args:
	    flow_id: Flow ID

	Returns:
	    dict with definition_json, version, status
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Flow Definition", flow_id)
	return {
		"flow_id": doc.flow_id,
		"flow_name": doc.flow_name,
		"definition_json": json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json,
		"version": doc.version,
		"schema_version": doc.schema_version,
		"status": doc.status,
	}


@frappe.whitelist()
def save_flow_definition(flow_id: str, definition_json: str | dict) -> dict:
	"""
	Save/update a flow definition. Validates schema and bumps version.

	Args:
	    flow_id: Flow ID
	    definition_json: Full graph JSON (string or dict)

	Returns:
	    dict with version number
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Normalize to string
	if isinstance(definition_json, dict):
		definition_json = json.dumps(definition_json)

	if frappe.db.exists("Flow Definition", flow_id):
		doc = frappe.get_doc("Flow Definition", flow_id)
		doc.definition_json = definition_json
		doc.save()
	else:
		defn = json.loads(definition_json)
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": flow_id,
				"flow_name": defn.get("metadata", {}).get("name", flow_id),
				"definition_json": definition_json,
				"status": "Draft",
			}
		)
		doc.insert()

	frappe.db.commit()
	return {"flow_id": doc.flow_id, "version": doc.version}


# ---------------------------------------------------------------------------
# Flow Run APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def run_flow(
	flow_id: str,
	payload: str | dict | None = None,
	mode: str | None = None,
	conversation_mode: str | None = None,
) -> dict:
	"""
	Start a new flow run.

	Args:
	    flow_id: Flow ID to run
	    payload: Initial input (JSON string or dict)
	    mode: Optional mode override (normal/agentic)
	    conversation_mode: Optional conversation_mode override

	Returns:
	    dict with flow_run_id, status, current_node_id
	"""
	if not frappe.has_permission("Flow Run", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Parse payload
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except (json.JSONDecodeError, TypeError):
			payload = {}
	payload = payload or {}

	from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

	flow_run = create_flow_run(
		flow_id=flow_id,
		payload=payload,
		mode=mode,
		conversation_mode=conversation_mode,
		trigger_type="Manual",
	)

	# Run synchronously for now; can be enqueued for background execution later
	engine_run_flow(flow_run.name)

	# Reload to get final state
	flow_run.reload()
	return {
		"flow_run_id": flow_run.name,
		"status": flow_run.status,
		"current_node_id": flow_run.current_node_id,
	}


@frappe.whitelist()
def get_flow_run(flow_run_id: str) -> dict:
	"""
	Get flow run status and details.

	Args:
	    flow_run_id: Flow Run name

	Returns:
	    dict with status, current_node_id, context_json, waiting state
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	ctx = {}
	try:
		ctx = json.loads(doc.context_json) if doc.context_json else {}
	except (json.JSONDecodeError, TypeError):
		pass

	waiting = {}
	try:
		waiting = json.loads(doc.waiting) if doc.waiting else {}
	except (json.JSONDecodeError, TypeError):
		pass

	return {
		"flow_run_id": doc.name,
		"flow_id": doc.flow_id,
		"flow_version": doc.flow_version,
		"mode": doc.mode,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
		"hop_count": doc.hop_count,
		"context_json": ctx,
		"waiting": waiting,
		"last_error": doc.last_error,
		"last_agent_run": doc.last_agent_run,
		"started_at": str(doc.started_at) if doc.started_at else None,
		"completed_at": str(doc.completed_at) if doc.completed_at else None,
	}


@frappe.whitelist()
def list_flow_runs(flow_id: str | None = None, status: str | None = None, limit: int = 20) -> list:
	"""
	List flow runs with optional filters.

	Args:
	    flow_id: Filter by flow_id
	    status: Filter by status
	    limit: Max results (default 20)

	Returns:
	    list of flow run summaries
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = {}
	if flow_id:
		filters["flow_id"] = flow_id
	if status:
		filters["status"] = status

	runs = frappe.get_all(
		"Flow Run",
		filters=filters,
		fields=[
			"name",
			"flow_id",
			"flow_version",
			"mode",
			"status",
			"current_node_id",
			"hop_count",
			"trigger_type",
			"started_at",
			"completed_at",
		],
		order_by="modified desc",
		limit_page_length=limit,
	)

	return runs


# ---------------------------------------------------------------------------
# Resume / Approval APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def resume_flow_run(flow_run_id: str, input: str | dict | None = None) -> dict:
	"""
	Resume a flow run that is waiting for user input.

	Args:
	    flow_run_id: Flow Run name
	    input: Optional input to merge into context

	Returns:
	    dict with status and current_node_id
	"""
	if not frappe.has_permission("Flow Run", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Parse input
	if isinstance(input, str):
		try:
			input = json.loads(input)
		except (json.JSONDecodeError, TypeError):
			input = {}

	from huf.ai.flow_engine import resume_flow_run as engine_resume

	engine_resume(flow_run_id, user_input=input)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	return {
		"flow_run_id": doc.name,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
	}


@frappe.whitelist()
def approve_flow_run(flow_run_id: str, comment: str | None = None) -> dict:
	"""
	Approve a flow run waiting for approval.

	Args:
	    flow_run_id: Flow Run name
	    comment: Optional comment

	Returns:
	    dict with status and current_node_id
	"""
	if not frappe.has_permission("Flow Run", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.flow_engine import approve_flow_run as engine_approve

	engine_approve(flow_run_id, decision="approved", comment=comment)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	return {
		"flow_run_id": doc.name,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
	}


@frappe.whitelist()
def reject_flow_run(flow_run_id: str, comment: str | None = None) -> dict:
	"""
	Reject a flow run waiting for approval.

	Args:
	    flow_run_id: Flow Run name
	    comment: Optional comment

	Returns:
	    dict with status and current_node_id
	"""
	if not frappe.has_permission("Flow Run", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.flow_engine import approve_flow_run as engine_approve

	engine_approve(flow_run_id, decision="rejected", comment=comment)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	return {
		"flow_run_id": doc.name,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
	}


# ---------------------------------------------------------------------------
# Webhook trigger endpoint
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def flow_webhook(flow_id: str, webhook_key: str | None = None) -> dict:
	"""
	Webhook trigger endpoint for flows.

	Validates webhook auth and starts a flow run.

	Args:
	    flow_id: Flow ID to trigger
	    webhook_key: Authentication key

	Returns:
	    dict with flow_run_id and status
	"""
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)

	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	if defn_doc.status != "Active":
		frappe.throw(_("Flow '{0}' is not active").format(flow_id))

	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json

	# Validate webhook auth
	nodes = defn.get("nodes", [])
	entry_node = None
	for n in nodes:
		if n.get("id") == defn.get("entry") and n.get("type") == "trigger.webhook":
			entry_node = n
			break

	if entry_node:
		expected_auth = entry_node.get("config", {}).get("auth")
		if expected_auth and webhook_key != expected_auth:
			frappe.throw(_("Invalid webhook key"), frappe.AuthenticationError)

	# Get payload from request
	payload = {}
	if frappe.request:
		try:
			raw = frappe.request.get_data(as_text=True)
			if raw:
				payload = frappe.parse_json(raw)
		except Exception:
			pass

		if not payload:
			if frappe.request.form:
				payload = dict(frappe.request.form)
			else:
				exclude = {'cmd', 'flow_id', 'webhook_key'}
				payload = {k: v for k, v in frappe.local.form_dict.items() if k not in exclude}

	from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

	flow_run = create_flow_run(
		flow_id=flow_id,
		payload=payload,
		trigger_type="Webhook",
	)

	# Run in background for webhooks
	frappe.enqueue(
		"huf.ai.flow_engine.run_flow",
		queue="default",
		flow_run_name=flow_run.name,
	)

	return {
		"flow_run_id": flow_run.name,
		"status": flow_run.status,
	}


@frappe.whitelist()
def schedule_flow(flow_id: str, cron: str, schedule_name: str | None = None, timezone: str = "UTC") -> dict:
	"""
	Schedule a flow to run periodically via Frappe Scheduler.
	
	Creates a Scheduled Job Type that will trigger the flow execution
	at the specified cron interval.
	
	Args:
	    flow_id: Flow ID to schedule
	    cron: Cron expression (e.g., "*/5 * * * *" for every 5 minutes)
	    schedule_name: Optional name for the schedule (defaults to flow_id)
	    timezone: Timezone for schedule execution (default: UTC)
	
	Returns:
	    dict with schedule_id, status, and next_execution
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)
	
	# Validate cron expression format (basic validation)
	cron_parts = cron.split()
	if len(cron_parts) != 5:
		frappe.throw(
			_("Invalid cron expression. Expected 5 parts (minute hour day month day_of_week), got {0}").format(len(cron_parts))
		)
	
	schedule_name = schedule_name or f"Flow Schedule: {flow_id}"
	job_id = f"huf.flow.schedule.{flow_id}"
	
	# Check if schedule already exists
	existing = frappe.db.get_value("Scheduled Job Type", {"name": job_id}, "name")
	
	if existing:
		# Update existing schedule
		doc = frappe.get_doc("Scheduled Job Type", existing)
		doc.cron_format = cron
		doc.save()
	else:
		# Create new Scheduled Job Type
		doc = frappe.get_doc({
			"doctype": "Scheduled Job Type",
			"name": job_id,
			"method": "huf.ai.flow_api.execute_scheduled_flow",
			"kwargs": json.dumps({"flow_id": flow_id}),
			"cron_format": cron,
			"frequency": "Cron",
			"create_log": 1,
		})
		doc.insert()
	
	frappe.db.commit()
	
	return {
		"schedule_id": doc.name,
		"flow_id": flow_id,
		"cron": cron,
		"status": "scheduled",
		"message": _("Flow '{0}' scheduled successfully with cron: {1}").format(flow_id, cron),
	}


@frappe.whitelist()
def unschedule_flow(flow_id: str) -> dict:
	"""
	Remove schedule for a flow.
	
	Args:
	    flow_id: Flow ID to unschedule

	Returns:
	    dict with status and message
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	
	job_id = f"huf.flow.schedule.{flow_id}"
	existing = frappe.db.get_value("Scheduled Job Type", {"name": job_id}, "name")
	
	if not existing:
		return {
			"status": "not_found",
			"message": _("No schedule found for flow '{0}'").format(flow_id),
		}
	
	frappe.delete_doc("Scheduled Job Type", existing, ignore_missing=True)
	frappe.db.commit()
	
	return {
		"status": "unscheduled",
		"message": _("Schedule removed for flow '{0}'").format(flow_id),
	}


@frappe.whitelist()
def get_flow_schedule(flow_id: str) -> dict | None:
	"""
	Get schedule details for a flow.
	
	Args:
	    flow_id: Flow ID to get schedule for

	Returns:
	    dict with schedule details or None if not scheduled
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	
	job_id = f"huf.flow.schedule.{flow_id}"
	existing = frappe.db.get_value(
		"Scheduled Job Type",
		{"name": job_id},
		["name", "cron_format", "last_execution", "next_execution", "disabled"],
		as_dict=True,
	)
	
	if not existing:
		return None
	
	return {
		"schedule_id": existing.name,
		"flow_id": flow_id,
		"cron": existing.cron_format,
		"last_execution": str(existing.last_execution) if existing.last_execution else None,
		"next_execution": str(existing.next_execution) if existing.next_execution else None,
		"disabled": existing.disabled,
		"status": "disabled" if existing.disabled else "active",
	}


@frappe.whitelist()
def execute_scheduled_flow(flow_id: str) -> dict:
	"""
	Execute a scheduled flow run.
	
	This method is called by the Frappe Scheduler when a scheduled
	job triggers. It creates and runs a flow run with schedule context.
	
	Args:
	    flow_id: Flow ID to execute

	Returns:
	    dict with flow_run_id and status
	"""
	from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow
	
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.log_error(f"Scheduled flow '{flow_id}' not found", "Flow Scheduler")
		return {"status": "error", "error": f"Flow '{flow_id}' not found"}
	
	# Check if flow is active
	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	if defn_doc.status != "Active":
		msg = f"Flow '{flow_id}' is not active (status: {defn_doc.status})"
		frappe.log_error(msg, "Flow Scheduler")
		return {"status": "error", "error": msg}
	
	# Create flow run with schedule trigger type
	payload = {
		"_triggered_by": "schedule",
		"_timestamp": str(now_datetime()),
	}
	
	try:
		flow_run = create_flow_run(
			flow_id=flow_id,
			payload=payload,
			trigger_type="Schedule",
		)
		
		# Run the flow
		engine_run_flow(flow_run.name)
		
		flow_run.reload()
		return {
			"flow_run_id": flow_run.name,
			"status": flow_run.status,
			"flow_id": flow_id,
		}
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Error executing scheduled flow '{flow_id}': {error_msg}", "Flow Scheduler")
		return {"status": "error", "error": error_msg, "flow_id": flow_id}


# ---------------------------------------------------------------------------
# Node Schema API (for dynamic UI construction)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_node_schemas() -> dict:
	"""
	Return JSON schema definitions for all available flow node types.

	This endpoint enables schema-driven UI construction. The frontend can
	query this to dynamically build configuration forms instead of
	hardcoding TypeScript interfaces per node type.

	Returns:
	    dict keyed by backend node type, each containing:
	        label (str): Display name
	        icon (str): Default icon name
	        category (str): Category for grouping in UI
	        description (str): Short description
	        has_backend (bool): Whether this node type has a backend executor
	        config_schema (list): List of field definitions for config form
	"""
	return {
		"trigger.webhook": {
			"label": "Webhook Trigger",
			"icon": "Webhook",
			"category": "trigger",
			"description": "Start flow from an incoming webhook",
			"has_backend": True,
			"config_schema": [
				{"name": "auth", "label": "Auth Key", "type": "string", "description": "Optional authentication key"},
				{"name": "method", "label": "HTTP Method", "type": "select", "options": ["GET", "POST", "PUT", "DELETE"], "default": "POST"},
			],
		},
		"trigger.schedule": {
			"label": "Schedule Trigger",
			"icon": "Clock",
			"category": "trigger",
			"description": "Start flow on a scheduled interval (cron)",
			"has_backend": True,
			"config_schema": [
				{"name": "cron", "label": "Cron Expression", "type": "string", "required": True, "description": "Cron expression e.g., */5 * * * * for every 5 minutes"},
				{"name": "schedule_name", "label": "Schedule Name", "type": "string", "description": "Optional name for this schedule"},
				{"name": "timezone", "label": "Timezone", "type": "string", "default": "UTC", "description": "Timezone for schedule execution"},
			],
		},
		"trigger.doc-event": {
			"label": "Doc Event Trigger",
			"icon": "FileText",
			"category": "trigger",
			"description": "Start flow when a document event occurs (create, update, delete)",
			"has_backend": True,
			"config_schema": [
				{"name": "doctype", "label": "DocType", "type": "doctype_select", "required": True, "description": "DocType to listen on (e.g., Sales Invoice, ToDo)"},
				{"name": "event", "label": "Event", "type": "select", "options": ["after_insert", "on_update", "on_submit", "on_cancel", "on_delete"], "required": True, "description": "Document event to trigger on"},
				{"name": "filters", "label": "Filters", "type": "json", "description": "Optional JSON filters to match documents (e.g., {\"status\": \"Draft\"})"},
			],
		},
		"agent.run": {
			"label": "Run Agent",
			"icon": "Bot",
			"category": "ai",
			"description": "Execute a HUF AI agent",
			"has_backend": True,
			"config_schema": [
				{"name": "agent_name", "label": "Agent", "type": "agent_select", "required": True},
				{"name": "input.prompt_template", "label": "Prompt Template", "type": "text", "supports_variables": True},
				{"name": "conversation_mode", "label": "Conversation Mode", "type": "select", "options": ["flow_shared", "isolated"], "default": "flow_shared"},
				{"name": "input.inject_flow_context", "label": "Inject Flow Context", "type": "boolean", "default": False},
				{"name": "output.save_response_to_context", "label": "Save Response To", "type": "string", "description": "Context key for result"},
			],
		},
		"tool.call": {
			"label": "Call Tool",
			"icon": "Wrench",
			"category": "ai",
			"description": "Execute a tool function deterministically",
			"has_backend": True,
			"config_schema": [
				{"name": "tool_name", "label": "Tool", "type": "tool_select", "required": True},
				{"name": "args", "label": "Arguments", "type": "dynamic_args", "description": "Loaded from tool definition"},
				{"name": "output.save_result_to_context", "label": "Save Result To", "type": "string", "description": "Context key for result"},
			],
		},
		"router.llm": {
			"label": "LLM Router",
			"icon": "GitBranch",
			"category": "control",
			"description": "Route flow using LLM-based decision making",
			"has_backend": True,
			"config_schema": [
				{"name": "router_agent_name", "label": "Routing Agent", "type": "agent_select", "required": True},
				{"name": "conversation_mode", "label": "Conversation Mode", "type": "select", "options": ["flow_shared", "isolated"], "default": "flow_shared"},
			],
		},
		"human.approval": {
			"label": "Human Approval",
			"icon": "UserCheck",
			"category": "control",
			"description": "Pause flow for human approval decision",
			"has_backend": True,
			"config_schema": [
				{"name": "title", "label": "Title", "type": "string", "default": "Approval Required"},
				{"name": "instructions", "label": "Instructions", "type": "text"},
				{"name": "context_summary", "label": "Context Summary", "type": "text", "supports_variables": True, "description": "Summary shown to approver with context variables"},
				{"name": "approval_type", "label": "Approval Type", "type": "select", "options": ["role", "user"], "default": "role"},
				{"name": "approver_role", "label": "Approver Role", "type": "role_select", "show_if": {"field": "approval_type", "value": "role"}},
				{"name": "approver_users", "label": "Approver Users", "type": "string", "show_if": {"field": "approval_type", "value": "user"}},
				{"name": "reference_doctype", "label": "Reference DocType", "type": "doctype_select", "description": "Link approval to a specific document type"},
				{"name": "reference_name", "label": "Reference Document", "type": "string", "supports_variables": True, "description": "Document name (supports {{variables}})"},
				{"name": "store_decision_in_context", "label": "Store Decision Key", "type": "string", "default": "approval"},
			],
		},
		"condition": {
			"label": "Condition (IF)",
			"icon": "GitFork",
			"category": "control",
			"description": "Branch flow based on a boolean expression (True/False)",
			"has_backend": True,
			"config_schema": [
				{"name": "expression", "label": "Condition Expression", "type": "expression", "required": True, "description": "e.g., context[\"status\"] == \"approved\""},
				{"name": "true_node", "label": "True Branch (Node ID)", "type": "node_select", "description": "Node to go to if condition is true"},
				{"name": "false_node", "label": "False Branch (Node ID)", "type": "node_select", "description": "Node to go to if condition is false"},
			],
		},
		"http_request": {
			"label": "HTTP Request",
			"icon": "Globe",
			"category": "integration",
			"description": "Make an HTTP request to an external API",
			"has_backend": True,
			"config_schema": [
				{"name": "url", "label": "URL", "type": "string", "required": True, "supports_variables": True},
				{"name": "method", "label": "Method", "type": "select", "options": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
				{"name": "headers", "label": "Headers", "type": "json", "description": "Request headers as JSON object"},
				{"name": "body", "label": "Body", "type": "json", "description": "Request body (POST/PUT only)", "supports_variables": True},
				{"name": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 30},
				{"name": "save_result_to_context", "label": "Save Result To", "type": "string", "description": "Context key for result"},
			],
		},
		"transform": {
			"label": "Transform Data",
			"icon": "Repeat",
			"category": "transform",
			"description": "Map, copy, or template data between context variables",
			"has_backend": True,
			"config_schema": [
				{"name": "transformations", "label": "Transformations", "type": "transform_list", "description": "List of {source_field, target_field, operation}"},
			],
		},
		"loop": {
			"label": "Loop",
			"icon": "RotateCw",
			"category": "control",
			"description": "Iterate over a list in context",
			"has_backend": True,
			"config_schema": [
				{"name": "iterate_over", "label": "Iterate Over", "type": "string", "required": True, "description": "Context key containing the array"},
				{"name": "item_key", "label": "Item Variable", "type": "string", "default": "loop_item", "description": "Context key for current item"},
				{"name": "index_key", "label": "Index Variable", "type": "string", "default": "loop_index"},
				{"name": "loop_node", "label": "Loop Body Node", "type": "node_select", "description": "Node to execute per iteration"},
				{"name": "done_node", "label": "Done Node", "type": "node_select", "description": "Node to go to when iteration completes"},
				{"name": "max_iterations", "label": "Max Iterations", "type": "number", "default": 100},
			],
		},
		"end": {
			"label": "End",
			"icon": "CheckCircle2",
			"category": "control",
			"description": "Mark flow as completed",
			"has_backend": True,
			"config_schema": [],
		},
	}


# ---------------------------------------------------------------------------
# Agent Tools (for agents to interact with flows)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def handle_run_flow(flow_id: str, payload: str | dict | None = None, mode: str | None = None, **kwargs) -> dict:
	"""
	Agent tool: Start a flow from within an agent.

	Args:
	    flow_id: Flow ID to run
	    payload: Initial payload (dict or JSON string)
	    mode: Optional mode override

	Returns:
	    dict with flow_run_id, status, message
	"""
	try:
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except Exception:
				payload = {}
				
		from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

		flow_run = create_flow_run(flow_id=flow_id, payload=payload or {}, mode=mode)
		
		# Execute synchronously so Chat agents can receive the result instead of just a queued message
		engine_run_flow(flow_run.name)
		
		flow_run.reload()

		return {
			"success": True,
			"flow_run_id": flow_run.name,
			"status": flow_run.status,
			"current_node_id": flow_run.current_node_id,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def handle_get_flow_run(flow_run_id: str, **kwargs) -> dict:
	"""
	Agent tool: Get flow run status.

	Args:
	    flow_run_id: Flow Run name

	Returns:
	    dict with status, context summary, waiting state
	"""
	try:
		doc = frappe.get_doc("Flow Run", flow_run_id)
		ctx = {}
		try:
			ctx = json.loads(doc.context_json) if doc.context_json else {}
		except (json.JSONDecodeError, TypeError):
			pass

		waiting = {}
		try:
			waiting = json.loads(doc.waiting) if doc.waiting else {}
		except (json.JSONDecodeError, TypeError):
			pass

		return {
			"success": True,
			"status": doc.status,
			"current_node_id": doc.current_node_id,
			"context_summary": {k: str(v)[:100] for k, v in ctx.items()},
			"waiting": waiting,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def handle_resume_flow_run(flow_run_id: str, input: dict | None = None, **kwargs) -> dict:
	"""
	Agent tool: Resume a waiting flow run.

	Args:
	    flow_run_id: Flow Run name
	    input: Optional input to merge

	Returns:
	    dict with updated status
	"""
	try:
		from huf.ai.flow_engine import resume_flow_run as engine_resume

		engine_resume(flow_run_id, user_input=input)
		doc = frappe.get_doc("Flow Run", flow_run_id)

		return {
			"success": True,
			"status": doc.status,
			"current_node_id": doc.current_node_id,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def handle_approve_flow_run(flow_run_id: str, decision: str = "approved", comment: str | None = None, **kwargs) -> dict:
	"""
	Agent tool: Approve or reject a flow run.

	Args:
	    flow_run_id: Flow Run name
	    decision: "approved" or "rejected"
	    comment: Optional comment

	Returns:
	    dict with updated status
	"""
	try:
		from huf.ai.flow_engine import approve_flow_run as engine_approve

		engine_approve(flow_run_id, decision=decision, comment=comment)
		doc = frappe.get_doc("Flow Run", flow_run_id)

		return {
			"success": True,
			"status": doc.status,
			"current_node_id": doc.current_node_id,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Pending Approvals API (for Approval Inbox)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_pending_approvals(limit: int = 50) -> list:
	"""
	Get list of flow runs waiting for approval that the current user can approve.
	
	This endpoint is used by the Approval Inbox feature to show users
	all pending approvals that require their attention.
	
	Args:
	    limit: Maximum number of results (default 50)
	
	Returns:
	    list of pending approval items with flow details
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	
	user = frappe.session.user
	user_roles = set(frappe.get_roles(user))
	
	# Get all flow runs waiting for approval
	pending_runs = frappe.get_all(
		"Flow Run",
		filters={"status": "Waiting Approval"},
		fields=[
			"name",
			"flow_id",
			"flow_version",
			"current_node_id",
			"status",
			"waiting",
			"started_at",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=limit,
	)
	
	results = []
	
	for run in pending_runs:
		try:
			waiting = json.loads(run.waiting) if run.waiting else {}
		except (json.JSONDecodeError, TypeError):
			waiting = {}
		
		approval_type = waiting.get("approval_type", "role")
		can_approve = False
		
		# Check if current user can approve this flow run
		if approval_type == "role":
			approver_role = waiting.get("approver_role")
			if approver_role and approver_role in user_roles:
				can_approve = True
		elif approval_type == "users":
			approver_users = waiting.get("approver_users", [])
			if isinstance(approver_users, str):
				approver_users = [u.strip() for u in approver_users.split(",") if u.strip()]
			if user in approver_users:
				can_approve = True
		
		if can_approve:
			results.append({
				"flow_run_id": run.name,
				"flow_id": run.flow_id,
				"flow_version": run.flow_version,
				"current_node_id": run.current_node_id,
				"title": waiting.get("title", "Approval Required"),
				"instructions": waiting.get("instructions", ""),
				"approval_type": approval_type,
				"approver_role": waiting.get("approver_role"),
				"approver_users": waiting.get("approver_users", []),
				"started_at": str(run.started_at) if run.started_at else None,
				"waiting_since": str(run.modified) if run.modified else None,
				"view_link": f"/huf/flows/{run.flow_id}?run={run.name}",
			})
	
	return results