"""
Whitelisted API endpoints for Huf Flow Engine.

Provides REST-style APIs for:
- Flow Definition management (get, save)
- Flow Run lifecycle (run, get, list, resume, approve, reject)
- Webhook trigger endpoint
- Agent tools (run_flow, get_flow_run, resume_flow_run, approve/reject)
"""

from __future__ import annotations

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
		"description": doc.description or "",
		"category": doc.category or "",
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

	from huf.ai.flow.engine import create_flow_run, run_flow as engine_run_flow

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

	from huf.ai.flow.engine import resume_flow_run as engine_resume

	engine_resume(flow_run_id, user_input=input)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	return {
		"flow_run_id": doc.name,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
	}


def _decide_flow_run(flow_run_id: str, decision: str, comment: str | None) -> dict:
	"""Shared approve/reject path.

	Authorisation is the engine's approver check (declared role / users; System Manager when none
	is declared) -- Flow Run read/write permission is deliberately not what gates a decision.
	The check runs here first so the caller gets a precise error, and again inside the engine
	before anything is mutated.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.AuthenticationError)
	if not frappe.db.exists("Flow Run", flow_run_id):
		frappe.throw(_("Flow Run '{0}' not found").format(flow_run_id), frappe.DoesNotExistError)

	from huf.ai.flow import engine

	flow_run = frappe.get_doc("Flow Run", flow_run_id)
	if flow_run.status != "Waiting Approval":
		frappe.throw(
			_("Flow Run '{0}' is not waiting for approval (status: {1})").format(flow_run_id, flow_run.status)
		)
	engine.verify_approval_permission(flow_run)

	engine.approve_flow_run(flow_run_id, decision=decision, comment=comment)

	doc = frappe.get_doc("Flow Run", flow_run_id)
	return {
		"flow_run_id": doc.name,
		"status": doc.status,
		"current_node_id": doc.current_node_id,
	}


@frappe.whitelist()
def approve_flow_run(flow_run_id: str, comment: str | None = None) -> dict:
	"""Approve a flow run waiting for approval (caller must be a permitted approver)."""
	return _decide_flow_run(flow_run_id, "approved", comment)


@frappe.whitelist()
def reject_flow_run(flow_run_id: str, comment: str | None = None) -> dict:
	"""Reject a flow run waiting for approval (caller must be a permitted approver)."""
	return _decide_flow_run(flow_run_id, "rejected", comment)


# ---------------------------------------------------------------------------
# Webhook trigger endpoint
# ---------------------------------------------------------------------------


WEBHOOK_SECRET_HEADER = "X-Huf-Secret"
WEBHOOK_FLOW_HEADER = "X-Huf-Flow-Id"


def _request_headers() -> dict:
	request = getattr(frappe, "request", None)
	if not request:
		return {}
	return getattr(request, "headers", {}) or {}


def _request_method() -> str | None:
	"""HTTP method of the current request, or None when not inside an HTTP request."""
	request = getattr(frappe, "request", None)
	method = getattr(request, "method", None) if request else None
	return method.upper() if isinstance(method, str) else None


def _presented_secret() -> str | None:
	"""The webhook secret the caller sent: ``X-Huf-Secret`` header or ``?secret=`` query parameter."""
	headers = _request_headers()
	value = headers.get(WEBHOOK_SECRET_HEADER)
	if value:
		return value
	request = getattr(frappe, "request", None)
	args = getattr(request, "args", None) if request else None
	return (args.get("secret") if args else None) or None


def _parse_webhook_payload() -> dict:
	payload = {}
	if not getattr(frappe, "request", None):
		return payload

	try:
		raw = frappe.request.get_data(as_text=True)
		if raw:
			payload = frappe.parse_json(raw)
	except (json.JSONDecodeError, TypeError):
		frappe.log_error(frappe.get_traceback(), "Flow Webhook Payload Parse Error")
		payload = {}

	if not payload:
		if frappe.request.form:
			payload = dict(frappe.request.form)
		else:
			exclude = {"cmd", "flow_id", "secret"}
			payload = {k: v for k, v in frappe.local.form_dict.items() if k not in exclude}

	return payload if isinstance(payload, dict) else {"payload": payload}


def _extract_flow_id(explicit_flow_id: str | None = None) -> str | None:
	if explicit_flow_id:
		return explicit_flow_id
	request = getattr(frappe, "request", None)
	if request and getattr(request, "args", None) and request.args.get("flow_id"):
		return request.args.get("flow_id")
	return _request_headers().get(WEBHOOK_FLOW_HEADER) or None


class WebhookDenied(frappe.AuthenticationError):
	"""Rejected webhook call. Frappe answers with the exception's own ``http_status_code`` (401 for a
	plain AuthenticationError, which also advertises an OAuth challenge), so pin it to 403."""

	http_status_code = 403


class WebhookMethodNotAllowed(frappe.PermissionError):
	"""Wrong HTTP method for the webhook trigger: answer 405, not the 403 a PermissionError implies."""

	http_status_code = 405


def _webhook_denied():
	"""Single generic rejection so a caller cannot tell unknown, inactive and wrong-secret flows apart."""
	frappe.throw(_("Webhook request not permitted"), WebhookDenied)


def _resolve_flow_by_secret(secret: str | None) -> str:
	from huf.ai.flow.triggers import active_webhook_flows, match_webhook_trigger

	if not secret:
		_webhook_denied()
	matches = [
		name
		for name, _owner, defn in active_webhook_flows()
		if match_webhook_trigger(defn, secret, None)[0] is not None
	]
	if len(matches) != 1:
		# none: wrong secret; several: ambiguous. Either way nothing is started.
		_webhook_denied()
	return matches[0]


def _run_flow_webhook(flow_id: str | None, secret: str | None, payload: dict | None = None) -> dict:
	from huf.ai.flow.triggers import match_webhook_trigger, parse_definition, start_flow_run

	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		_webhook_denied()
	status, owner, definition_json = frappe.db.get_value(
		"Flow Definition", flow_id, ["status", "owner", "definition_json"]
	)
	# Disabled / unpublished flows never accept webhooks.
	if status != "Active":
		_webhook_denied()

	node, reason = match_webhook_trigger(parse_definition(definition_json), secret, _request_method())
	if node is None:
		if reason == "bad_method":
			frappe.throw(_("Webhook method not allowed"), WebhookMethodNotAllowed)
		_webhook_denied()

	# Execute as the flow owner, never Guest. The secret check above authorises the trigger;
	# resolve_run_identity_and_authorize only resolves who the run executes as.
	from huf.ai.agent.access import TRIGGER_FLOW_WEBHOOK, resolve_run_identity_and_authorize

	identity = resolve_run_identity_and_authorize(None, TRIGGER_FLOW_WEBHOOK, {"owner": owner})

	if payload is None:
		payload = _parse_webhook_payload()

	flow_run = start_flow_run(
		flow_id,
		payload,
		"Webhook",
		trigger_node_id=node["id"],
		user=identity.run_as_user,
		enqueue=True,
		commit_first=True,
	)
	return {"flow_run_id": flow_run.name, "status": flow_run.status}


@frappe.whitelist(allow_guest=True)
def flow_webhook(flow_id: str | None = None, secret: str | None = None) -> dict:
	"""
	Webhook trigger endpoint for flows.

	Authenticates with the per-flow ``secret`` from the ``trigger.webhook`` node config, sent as the
	``X-Huf-Secret`` header or the ``?secret=`` query parameter (constant-time compare, fails closed).
	The HTTP method must equal the node's configured ``method``. Only Active flows accept webhooks.
	"""
	return _run_flow_webhook(_extract_flow_id(flow_id), _presented_secret() or secret)


@frappe.whitelist(allow_guest=True)
def flow_webhook_clean(flow_id: str | None = None, secret: str | None = None) -> dict:
	"""
	Clean URL webhook receiver for providers that reject query parameters.

	The secret comes from the ``X-Huf-Secret`` header (or ``?secret=``). ``flow_id`` is taken from the
	argument, ``?flow_id=`` or the ``X-Huf-Flow-Id`` header; if absent, Huf finds the single Active
	``trigger.webhook`` flow whose configured secret equals the presented one.
	"""
	presented = _presented_secret() or secret
	resolved_flow_id = _extract_flow_id(flow_id) or _resolve_flow_by_secret(presented)
	return _run_flow_webhook(resolved_flow_id, presented)


# ---------------------------------------------------------------------------
# Flow triggers (schedule / doc event) -- an Automation bound to the Flow's Procedure
# ---------------------------------------------------------------------------
#
# Flow triggers are not a separate scheduler: a Flow with a schedule or doc-event trigger
# is converted to an Agent Procedure (the run path in use) and an Automation that targets
# that Procedure carries the trigger, so it fires through the same dispatchers
# (automation.scheduler.run_due_automations / automation.hooks.run_hooked_automations).
# The Automation is only Active once the Procedure is Testing/Active -- conversion never
# activates a Procedure (I8), so a fresh trigger sits in Draft until a human enables it.

_FLOW_TRIGGER_TYPES = {"schedule": "Schedule", "doc_event": "Doc Event", "doc event": "Doc Event"}
_FLOW_AUTOMATION_PREFIX = "Flow Trigger: "


def _flow_automation_name(flow_id: str) -> str:
	return f"{_FLOW_AUTOMATION_PREFIX}{flow_id}"


def _flow_trigger_row(automation_name: str):
	name = frappe.db.get_value("Automation Trigger", {"automation": automation_name}, "name")
	return frappe.get_doc("Automation Trigger", name) if name else None


def _graph_matches_fingerprint(procedure_graph: dict, procedure) -> bool:
	"""True when the converted Flow graph hashes to the bound procedure row's fingerprint."""
	from huf.ai.procedure.versioning import compute_fingerprint

	graph = dict(procedure_graph)
	graph["profile"] = "procedure"
	graph["schema_version"] = procedure.schema_version or graph.get("schema_version") or "1.0.0"
	return compute_fingerprint(graph) == procedure.fingerprint


def _flow_trigger_is_stale(flow_id: str, procedure_name: str) -> bool:
	"""True when the Flow's current graph no longer matches the procedure the trigger is bound to."""
	from huf.ai.procedure.conversion import analyze_conversion

	bound = frappe.db.get_value(
		"Agent Procedure", procedure_name, ["name", "fingerprint", "schema_version"], as_dict=True
	)
	if not bound:
		return True
	try:
		_doc, flow_graph = _load_flow_graph(flow_id)
		result = analyze_conversion(flow_graph)
	except Exception:  # noqa: BLE001 -- an unreadable/unconvertible flow cannot match
		return True
	return not result.convertible or not _graph_matches_fingerprint(result.procedure_graph, bound)


def _ensure_flow_procedure(flow_id: str) -> str:
	"""Return the name of an Agent Procedure version matching the Flow's current
	definition, converting (a new immutable Draft version) only if none does."""
	from huf.ai.procedure.conversion import analyze_conversion

	_doc, flow_graph = _load_flow_graph(flow_id)
	result = analyze_conversion(flow_graph)
	if not result.convertible:
		frappe.throw(
			_("Flow '{0}' cannot take a schedule or doc-event trigger: {1}").format(flow_id, result.reason),
			title=_("Flow Is Not Convertible"),
		)

	procedure_id = f"{flow_id}-procedure"
	latest = frappe.db.get_value(
		"Agent Procedure",
		{"procedure_id": procedure_id},
		["name", "fingerprint", "schema_version"],
		order_by="version desc",
		as_dict=True,
	)
	if latest and _graph_matches_fingerprint(result.procedure_graph, latest):
		return latest.name

	return convert_flow_to_procedure(flow_id, procedure_id=procedure_id)["name"]


def _flow_trigger_summary(flow_id: str) -> dict | None:
	automation_name = _flow_automation_name(flow_id)
	if not frappe.db.exists("Automation", automation_name):
		return None
	automation = frappe.get_doc("Automation", automation_name)
	trigger = _flow_trigger_row(automation_name)
	if not trigger:
		return None
	procedure_status = frappe.db.get_value("Agent Procedure", automation.procedure, "status")
	out = {
		"flow_id": flow_id,
		"trigger_type": trigger.trigger_type,
		"automation": automation.name,
		"automation_trigger": trigger.name,
		"automation_status": automation.status,
		"procedure": automation.procedure,
		"procedure_status": procedure_status,
		"enabled": bool(automation.status == "Active" and not trigger.disabled),
		"stale": _flow_trigger_is_stale(flow_id, automation.procedure),
		"next_run": str(trigger.next_execution) if trigger.next_execution else None,
		"last_run": str(trigger.last_execution) if trigger.last_execution else None,
	}
	if automation.status != "Active":
		from huf.huf.doctype.automation.automation import RUNNABLE_PROCEDURE_STATUSES

		if procedure_status in RUNNABLE_PROCEDURE_STATUSES:
			# The procedure is ready: the flow itself is what is not live yet.
			out["activation_required"] = _("Publish this flow to start the trigger.")
		else:
			out["activation_required"] = _(
				"Procedure {0} is {1}. Enable it (Testing or Active) and activate the automation for this trigger to fire."
			).format(automation.procedure, procedure_status)
	if trigger.trigger_type == "Schedule":
		out.update(
			schedule_type=trigger.schedule_type,
			cron=trigger.cron_expression,
		)
	else:
		out.update(
			reference_doctype=trigger.reference_doctype,
			doc_event=trigger.doc_event,
			condition=trigger.condition,
		)
	return out


@frappe.whitelist()
def set_flow_trigger(
	flow_id: str,
	trigger_type: str,
	cron: str | None = None,
	reference_doctype: str | None = None,
	doc_event: str | None = None,
	condition: str | None = None,
	run_as_user: str | None = None,
	disabled: int = 0,
) -> dict:
	"""Create or replace the single schedule / doc-event trigger of a Flow.

	Converts the Flow to an Agent Procedure if needed (refusing, with the conversion's
	reason, when the Flow contains agent.run / router.llm / human.approval), then
	creates/updates an Automation targeting that Procedure plus its Automation Trigger.

	Args:
	    flow_id: Flow Definition name.
	    trigger_type: "schedule" or "doc_event".
	    cron: for schedule -- a 5-part cron expression (evaluated in system time). Cron
	        only: the Flow's trigger.schedule node config needs ``cron``, so interval
	        schedules could not be mirrored into it.
	    reference_doctype / doc_event / condition: for doc_event.
	    run_as_user: identity the Procedure runs as (default: the caller).

	Returns:
	    the get_flow_trigger() summary, including ``next_run`` for schedules.
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Automation", "write") or not frappe.has_permission("Automation Trigger", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)
	if not frappe.has_permission("Flow Definition", "write", flow_id):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	resolved_type = _FLOW_TRIGGER_TYPES.get((trigger_type or "").strip().lower())
	if not resolved_type:
		frappe.throw(_("trigger_type must be 'schedule' or 'doc_event'"))

	trigger_fields: dict = {"trigger_type": resolved_type}
	if resolved_type == "Schedule":
		if not cron:
			frappe.throw(_("A schedule trigger needs a cron expression."))
		if len(cron.split()) != 5:
			frappe.throw(_("Invalid cron expression. Expected 5 parts (minute hour day month day_of_week)."))
		trigger_fields.update(schedule_type="Cron", cron_expression=cron)
		trigger_fields["next_execution"] = None
	else:
		if not reference_doctype or not doc_event:
			frappe.throw(_("A doc_event trigger needs reference_doctype and doc_event."))
		if not frappe.db.exists("DocType", reference_doctype):
			frappe.throw(_("DocType '{0}' not found").format(reference_doctype))
		from huf.ai.automation.hooks import SUPPORTED_DOC_EVENTS

		if doc_event not in SUPPORTED_DOC_EVENTS:
			frappe.throw(_("Unsupported doc_event '{0}'").format(doc_event))
		trigger_fields.update(reference_doctype=reference_doctype, doc_event=doc_event, condition=condition or None)

	procedure_name = _ensure_flow_procedure(flow_id)
	procedure_status = frappe.db.get_value("Agent Procedure", procedure_name, "status")
	from huf.huf.doctype.automation.automation import RUNNABLE_PROCEDURE_STATUSES

	automation_name = _flow_automation_name(flow_id)
	automation_fields = {
		"target_type": "Agent Procedure",
		"procedure": procedure_name,
		"agent": None,
		"run_as_user": run_as_user or frappe.session.user,
		# Only a runnable procedure on an Active flow may fire; Draft/Archived flows stay Draft.
		"status": "Active"
		if procedure_status in RUNNABLE_PROCEDURE_STATUSES
		and frappe.db.get_value("Flow Definition", flow_id, "status") == "Active"
		else "Draft",
	}
	if frappe.db.exists("Automation", automation_name):
		automation = frappe.get_doc("Automation", automation_name)
		automation.update(automation_fields)
		automation.save()
	else:
		automation = frappe.get_doc(
			{"doctype": "Automation", "automation_name": automation_name, **automation_fields}
		)
		automation.insert()

	trigger = _flow_trigger_row(automation_name)
	if trigger:
		# A trigger type change must not leave the old type's fields behind.
		for fieldname in (
			"schedule_type", "cron_expression", "scheduled_interval", "interval_count",
			"next_execution", "reference_doctype", "doc_event", "condition",
		):
			trigger.set(fieldname, None)
		trigger.update({**trigger_fields, "disabled": int(bool(disabled))})
		trigger.save()
	else:
		trigger = frappe.get_doc(
			{
				"doctype": "Automation Trigger",
				"trigger_name": f"{flow_id} trigger",
				"automation": automation_name,
				"disabled": int(bool(disabled)),
				**trigger_fields,
			}
		)
		trigger.insert()
	frappe.cache().delete_key("huf:doc_event_automation_triggers")

	return _flow_trigger_summary(flow_id)


@frappe.whitelist()
def get_flow_trigger(flow_id: str) -> dict | None:
	"""Return the Flow's schedule / doc-event trigger summary, or None if it has none."""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return _flow_trigger_summary(flow_id)


@frappe.whitelist()
def clear_flow_trigger(flow_id: str) -> dict:
	"""Remove the Flow's trigger (its Automation and Automation Trigger). The Procedure stays."""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	automation_name = _flow_automation_name(flow_id)
	if not frappe.db.exists("Automation", automation_name):
		return {"status": "not_found", "flow_id": flow_id}

	# Procedure runs are history: keep them, drop only their link to the trigger/automation
	# so the delete is not blocked by Frappe's linked-document check.
	frappe.db.set_value(
		"Agent Procedure Run",
		{"automation": automation_name},
		{"automation": None, "automation_trigger": None},
		update_modified=False,
	)
	for trigger_name in frappe.get_all("Automation Trigger", {"automation": automation_name}, pluck="name"):
		frappe.delete_doc("Automation Trigger", trigger_name)
	frappe.delete_doc("Automation", automation_name)
	frappe.cache().delete_key("huf:doc_event_automation_triggers")
	return {"status": "cleared", "flow_id": flow_id}


# ---------------------------------------------------------------------------
# Node Schema API (for dynamic UI construction)
# ---------------------------------------------------------------------------


# Display metadata only. Every config field below the node is generated from graph_ir.schema.json.
_NODE_DISPLAY = {
	"trigger.webhook": ("Webhook Trigger", "Webhook", "trigger"),
	"trigger.schedule": ("Schedule Trigger", "Clock", "trigger"),
	"trigger.doc-event": ("Doc Event Trigger", "FileText", "trigger"),
	"trigger.unset": ("Unset Trigger", "CircleDashed", "trigger"),
	"agent.run": ("Run Agent", "SquareAsterisk", "ai"),
	"tool.call": ("Call Tool", "Wrench", "ai"),
	"router.llm": ("LLM Router", "GitBranch", "control"),
	"router.decision": ("Decision Router", "GitBranch", "control"),
	"human.approval": ("Human Approval", "UserCheck", "control"),
	"condition": ("Condition (IF)", "GitFork", "control"),
	"foreach": ("Loop", "RotateCw", "control"),
	"parallel": ("Parallel", "Split", "control"),
	"validate": ("Validate", "ShieldCheck", "control"),
	"output": ("End", "CheckCircle2", "control"),
	"transform": ("Transform Data", "Repeat", "transform"),
	"state.get": ("Get State", "DatabaseZap", "state"),
	"state.set": ("Set State", "Database", "state"),
	"state.delete": ("Delete State", "Trash2", "state"),
	"doc.create": ("Create Document", "FilePlus", "data"),
}

_SCHEMA_FILE = None


def _graph_schema() -> dict:
	global _SCHEMA_FILE
	if _SCHEMA_FILE is None:
		import os

		path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graph", "graph_ir.schema.json")
		with open(path, encoding="utf-8") as fh:
			_SCHEMA_FILE = json.load(fh)
	return _SCHEMA_FILE


def _ref_name(schema: dict) -> str | None:
	ref = schema.get("$ref") if isinstance(schema, dict) else None
	return ref.rsplit("/", 1)[-1] if ref else None


def _field_type(schema: dict) -> dict:
	"""Map one JSON-schema property to a UI field descriptor (type + constraints)."""
	ref = _ref_name(schema)
	if ref == "NodeId":
		return {"type": "node_select"}
	if ref == "Expression":
		return {"type": "expression"}
	if ref == "Reference":
		return {"type": "reference"}
	if ref == "ToolId":
		return {"type": "tool_select"}
	if ref == "Value":
		return {"type": "value"}
	if "enum" in schema:
		return {"type": "select", "options": list(schema["enum"])}
	if "const" in schema:
		return {"type": "select", "options": [schema["const"]], "default": schema["const"]}
	if "anyOf" in schema:
		return {"type": "value"}
	kind = schema.get("type")
	if kind == "string":
		out = {"type": "string"}
		for src, dst in (("minLength", "min_length"), ("maxLength", "max_length")):
			if src in schema:
				out[dst] = schema[src]
		return out
	if kind == "integer":
		out = {"type": "number"}
		for src, dst in (("minimum", "min"), ("maximum", "max")):
			if src in schema:
				out[dst] = schema[src]
		return out
	if kind == "boolean":
		return {"type": "boolean"}
	if kind == "array":
		item = schema.get("items", {})
		if _ref_name(item) == "NodeId":
			return {"type": "node_list"}
		if item.get("type") == "string":
			return {"type": "string_list"}
	return {"type": "json"}


def _node_config_schema(node_def: dict) -> tuple[str | None, dict, bool]:
	"""``(node_type, config_schema, forbids_next)`` for one FlowGraph node definition."""
	node_type, config, forbids_next = None, {}, False
	for part in node_def.get("allOf", [node_def]):
		props = part.get("properties") or {}
		if "type" in props and "const" in props["type"]:
			node_type = props["type"]["const"]
			config = props.get("config", {})
		if part.get("not", {}).get("required") == ["next"]:
			forbids_next = True
	return node_type, config, forbids_next


def build_node_schemas(schema: dict | None = None) -> dict:
	"""Node-type -> UI descriptor, generated from ``graph_ir.schema.json`` (FlowGraph node list)."""
	schema = schema or _graph_schema()
	defs = schema["$defs"]
	out: dict = {}
	for entry in defs["FlowNode"]["oneOf"]:
		node_def = defs[_ref_name(entry)]
		node_type, config, forbids_next = _node_config_schema(node_def)
		if not node_type:
			continue
		required = set(config.get("required", []))
		fields = []
		for name, prop in (config.get("properties") or {}).items():
			descriptor = _field_type(prop)
			descriptor.update(
				{"name": name, "label": name.replace("_", " ").title(), "required": name in required}
			)
			if prop.get("description"):
				descriptor["description"] = prop["description"]
			if "default" in prop:
				descriptor["default"] = prop["default"]
			fields.append(descriptor)
		label, icon, category = _NODE_DISPLAY.get(node_type, (node_type, "Circle", "other"))
		out[node_type] = {
			"label": label,
			"icon": icon,
			"category": category,
			"description": node_def.get("description") or label,
			"has_backend": True,
			"routing": {"next": not forbids_next, "on_error": True},
			"config_schema": fields,
			"json_schema": config,
		}
	return out


@frappe.whitelist()
def get_node_schemas() -> dict:
	"""
	Return field definitions for every flow node type, generated from the graph IR schema
	(``huf/ai/graph/graph_ir.schema.json``, the source of truth; see docs/flow/FIELD_CONTRACT.md).

	Returns:
	    dict keyed by node type; each value has label, icon, category, description, has_backend,
	    routing ({next, on_error}: whether the node may carry those pointers), config_schema (list of
	    field descriptors: name, label, type, required, options/min/max/default) and json_schema
	    (the raw config JSON schema).
	"""
	return build_node_schemas()


@frappe.whitelist()
def list_flow_tools() -> list:
	"""
	List all tools available to flow tool-call nodes: built-in Agent Tool
	Function records plus tools exposed by enabled MCP Server documents.

	Each dict:
	    {
	        "name": str,
	        "label": str,
	        "description": str,
	        "source": "builtin" | "mcp",
	        "mcp_server": str | None,
	        "params_json_schema": dict,
	    }

	Returns:
	    list[dict]
	"""
	if not frappe.has_permission("Agent Tool Function", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	tools = []

	# Built-in tools: Agent Tool Function.params is the authoritative JSON
	# Schema source (see huf/ai/sdk_tools.py:create_agent_tools, which is the
	# only code path that actually builds runtime tools from this doctype).
	# The "parameters" child table (Agent Function Params) is not read by
	# any conversion code in the app and is treated as stale/unused here.
	for row in frappe.get_all(
		"Agent Tool Function",
		fields=["name", "tool_name", "description", "params"],
		# Flow/Procedure runs have no Agent Execution Profile, so a Code Execution tool is
		# refused on every call (PermissionAwareToolRegistry._allows_code_execution); don't offer it.
		filters={"types": ["!=", "Code Execution"]},
	):
		params_json_schema = {}
		if row.params:
			try:
				params_json_schema = json.loads(row.params)
			except (json.JSONDecodeError, TypeError):
				params_json_schema = {}

		tools.append({
			"name": row.tool_name,
			"label": row.tool_name,
			"description": row.description or "",
			"source": "builtin",
			"mcp_server": None,
			"params_json_schema": params_json_schema if isinstance(params_json_schema, dict) else {},
		})

	# MCP tools: each enabled "MCP Server" document caches its tools in the
	# "tools" child table (MCP Server Tool: tool_name, description,
	# parameters JSON, enabled). "mcp_server" below is the MCP Server
	# document name (server_name, since autoname is field:server_name),
	# matching the identifier huf.ai.mcp_client.execute_mcp_tool expects
	# for its server_name argument.
	mcp_servers = frappe.get_all(
		"MCP Server",
		filters={"enabled": 1},
		fields=["name", "tool_namespace"],
	)
	for server in mcp_servers:
		tool_rows = frappe.get_all(
			"MCP Server Tool",
			filters={"parent": server.name, "parenttype": "MCP Server", "enabled": 1},
			fields=["tool_name", "description", "parameters"],
		)
		for tool_row in tool_rows:
			params_json_schema = {}
			if tool_row.parameters:
				try:
					params_json_schema = json.loads(tool_row.parameters)
				except (json.JSONDecodeError, TypeError):
					params_json_schema = {}

			label = tool_row.tool_name
			if server.tool_namespace:
				label = f"{server.tool_namespace}.{tool_row.tool_name}"

			tools.append({
				"name": tool_row.tool_name,
				"label": label,
				"description": tool_row.description or "",
				"source": "mcp",
				"mcp_server": server.name,
				"params_json_schema": params_json_schema if isinstance(params_json_schema, dict) else {},
			})

	return tools


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
	if not frappe.has_permission("Flow Run", "create"):
		return {"error": "Insufficient permissions to start flows"}

	try:
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except (json.JSONDecodeError, TypeError):
				payload = {}

		from huf.ai.flow.engine import create_flow_run, run_flow as engine_run_flow

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
		frappe.log_error(frappe.get_traceback(), "Run Flow Tool Error")
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
	if not frappe.has_permission("Flow Run", "read"):
		return {"error": "Insufficient permissions to view flow runs"}

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
		frappe.log_error(frappe.get_traceback(), "Get Flow Run Tool Error")
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
	if not frappe.has_permission("Flow Run", "write"):
		return {"error": "Insufficient permissions to resume flow runs"}

	try:
		from huf.ai.flow.engine import resume_flow_run as engine_resume

		engine_resume(flow_run_id, user_input=input)
		doc = frappe.get_doc("Flow Run", flow_run_id)

		return {
			"success": True,
			"status": doc.status,
			"current_node_id": doc.current_node_id,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Resume Flow Run Tool Error")
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
	if not frappe.has_permission("Flow Run", "read"):
		return {"error": "Insufficient permissions to approve flow runs"}

	try:
		from huf.ai.flow.engine import approve_flow_run as engine_approve, verify_approval_permission

		doc = frappe.get_doc("Flow Run", flow_run_id)
		verify_approval_permission(doc)

		engine_approve(flow_run_id, decision=decision, comment=comment)
		doc.reload()

		return {
			"success": True,
			"status": doc.status,
			"current_node_id": doc.current_node_id,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Approve Flow Run Tool Error")
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Pending Approvals API (for Approval Inbox)
# ---------------------------------------------------------------------------


# Re-enabled 2026-08-07. This was disabled on 2026-08-02 on the belief that it
# returned 403 even for Administrator. That was a misdiagnosis: the 403 came
# from an expired session (Frappe answers Guest with "not whitelisted"), not
# from the permission check below. Verified over HTTP with a live Administrator
# session — the endpoint answers 200 with a normal list.
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

	from huf.ai.flow import engine

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

	flow_names = {
		row.flow_id: row.flow_name
		for row in frappe.get_all(
			"Flow Definition",
			filters={"flow_id": ["in", list({r.flow_id for r in pending_runs})]},
			fields=["flow_id", "flow_name"],
		)
	} if pending_runs else {}

	results = []

	for run in pending_runs:
		try:
			waiting = json.loads(run.waiting) if run.waiting else {}
		except (json.JSONDecodeError, TypeError):
			waiting = {}

		# Same fail-closed rule as deciding: only runs the current user may decide are listed.
		if engine.check_approver(waiting, user, user_roles) is not None:
			continue

		approver_type = waiting.get("approver_type")
		results.append({
			"flow_run_id": run.name,
			"flow_id": run.flow_id,
			"flow_name": flow_names.get(run.flow_id) or run.flow_id,
			"flow_version": run.flow_version,
			"current_node_id": run.current_node_id,
			"node_id": waiting.get("node_id") or run.current_node_id,
			"title": "Approval Required",
			"message": waiting.get("message", ""),
			"instructions": waiting.get("message", ""),
			"approver_type": approver_type,
			"approval_type": approver_type,
			"approver_role": waiting.get("approver_role"),
			"approver_users": waiting.get("approver_users") or [],
			"timeout_next": waiting.get("timeout_next"),
			"timeout_ms": waiting.get("timeout_ms"),
			"timeout_at": waiting.get("timeout_at"),
			"started_at": str(run.started_at) if run.started_at else None,
			"waiting_since": str(run.modified) if run.modified else None,
			"view_link": f"/huf/flows/{run.flow_id}?run={run.name}",
		})

	return results


# ---------------------------------------------------------------------------
# Flow -> Procedure conversion (T-52)
#
# "Flow is what you draw, Procedure is what it compiles to -- the same picture
# at two stages." The determinism check, entry rewiring and Procedure-graph
# compilation live in huf.ai.procedure.conversion (frappe-free, unit tested on
# its own); this layer only adds permission checks and the Agent Procedure
# creation, following the same whitelisted-endpoint shape as the rest of this
# module.
# ---------------------------------------------------------------------------


def _load_flow_graph(flow_id: str) -> tuple[frappe.Document, dict]:
	doc = frappe.get_doc("Flow Definition", flow_id)
	defn = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	if not isinstance(defn, dict):
		frappe.throw(_("Flow '{0}' has no valid definition to convert").format(flow_id))
	return doc, defn


@frappe.whitelist()
def analyze_flow_conversion(flow_id: str) -> dict:
	"""
	Read-only preview of converting a Flow to an Agent Procedure. Creates nothing.

	Args:
	    flow_id: Flow Definition name

	Returns:
	    dict -- either {"convertible": False, "reason": "..."} or
	    {"convertible": True, "reads": [...], "writes": [...],
	     "atomic_operations": N, "estimated_round_trip_reduction_pct": N}
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.procedure.conversion import analyze_conversion

	_doc, flow_graph = _load_flow_graph(flow_id)
	result = analyze_conversion(flow_graph)

	if not result.convertible:
		return {"convertible": False, "reason": result.reason}

	return {"convertible": True, **result.summary.as_dict()}


@frappe.whitelist()
def convert_flow_to_procedure(flow_id: str, procedure_id: str | None = None) -> dict:
	"""
	Convert a deterministic Flow into a Draft Agent Procedure.

	Refuses -- with a specific reason, no partial conversion -- for any flow that is
	not structurally deterministic (contains an ``agent.run``, ``router.llm`` or
	``human.approval`` step) or that does not itself validate. The created record is
	always ``tier="Draft"``, ``status="Draft"`` -- this endpoint never activates a
	procedure (I8); a human reviews and enables it separately.

	Args:
	    flow_id: Flow Definition to convert
	    procedure_id: Logical procedure id to create/append a version to. Defaults to
	        ``"{flow_id}-procedure"``. Re-converting the same flow under the same
	        procedure_id creates a new, immutable version (T-20), it never edits one.

	Returns:
	    dict with the created Agent Procedure's name/procedure_id/version, plus the
	    same reads/writes/estimated-reduction summary as analyze_flow_conversion.
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Agent Procedure", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from huf.ai.procedure.conversion import analyze_conversion

	flow_doc, flow_graph = _load_flow_graph(flow_id)
	result = analyze_conversion(flow_graph)

	if not result.convertible:
		frappe.throw(result.reason, title=_("Flow Is Not Convertible"))

	resolved_procedure_id = procedure_id or f"{flow_id}-procedure"

	procedure = frappe.get_doc(
		{
			"doctype": "Agent Procedure",
			"procedure_id": resolved_procedure_id,
			"procedure_name": _("{0} (from Flow)").format(flow_doc.flow_name or flow_id),
			"definition_json": frappe.as_json(result.procedure_graph),
			"tier": "Draft",
			"status": "Draft",
			"provenance": frappe.as_json(
				{
					"source": "flow_conversion",
					"source_flow_id": flow_id,
					"source_flow_fingerprint": flow_graph.get("fingerprint"),
					"converted_by": frappe.session.user,
					"converted_at": str(now_datetime()),
				}
			),
		}
	)
	procedure.insert()

	return {
		"name": procedure.name,
		"procedure_id": procedure.procedure_id,
		"version": procedure.version,
		"status": procedure.status,
		"tier": procedure.tier,
		**result.summary.as_dict(),
	}
