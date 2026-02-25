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
		if frappe.request.is_json:
			payload = frappe.request.get_json(silent=True) or {}
		else:
			payload = dict(frappe.request.form) if frappe.request.form else {}

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
