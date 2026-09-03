"""
Whitelisted API endpoints for Huf Flow Engine.

Provides REST-style APIs for:
- Flow Definition management (get, save)
- Flow Run lifecycle (run, get, list, resume, approve, reject)
- Webhook trigger endpoint
- Agent tools (run_flow, get_flow_run, resume_flow_run, approve/reject)
"""

from __future__ import annotations

import hmac
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
	if not frappe.has_permission("Flow Run", "read"):
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


def _webhook_key_is_valid(defn: dict, webhook_key: str | None) -> bool:
	"""Return True only if the flow's entry node is a webhook trigger with a
	non-empty configured auth key that matches webhook_key (constant-time).

	Fails closed: returns False if the entry node is missing, is not a
	trigger.webhook, or has no/empty auth configured.
	"""
	entry_id = defn.get("entry")
	entry_node = None
	for n in defn.get("nodes", []):
		if n.get("id") == entry_id and n.get("type") == "trigger.webhook":
			entry_node = n
			break

	if entry_node is None:
		return False

	# The webhook auth key is written as "auth" by RightSidebar.tsx but as
	# "apiKey" by NodeSelectionModal.tsx (frontend inconsistency, not a
	# backend redundancy) - accept either so a webhook configured through
	# either UI path can authenticate. "auth" takes precedence when both
	# are somehow present.
	node_config = entry_node.get("config", {})
	expected_auth = node_config.get("auth") or node_config.get("apiKey")
	if not expected_auth:
		return False

	return hmac.compare_digest(str(webhook_key or ""), str(expected_auth))


def _webhook_entry_auth(defn: dict) -> str | None:
	entry_id = defn.get("entry")
	for node in defn.get("nodes", []):
		if node.get("id") == entry_id and node.get("type") == "trigger.webhook":
			node_config = node.get("config", {})
			# See _webhook_key_is_valid for why both keys are checked.
			return node_config.get("auth") or node_config.get("apiKey")
	return None


def _request_headers() -> dict:
	request = getattr(frappe, "request", None)
	if not request:
		return {}
	return getattr(request, "headers", {}) or {}


def _header_value(*names: str) -> str | None:
	headers = _request_headers()
	for name in names:
		value = headers.get(name)
		if value:
			return value
	return None


def _bearer_token(value: str | None) -> str | None:
	if not value:
		return None
	parts = value.split(None, 1)
	if len(parts) == 2 and parts[0].lower() == "bearer":
		return parts[1].strip() or None
	return None


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
			exclude = {"cmd", "flow_id", "webhook_key", "key", "secret", "token"}
			payload = {k: v for k, v in frappe.local.form_dict.items() if k not in exclude}

	return payload if isinstance(payload, dict) else {"payload": payload}


def _extract_webhook_key(payload: dict | None = None, explicit_key: str | None = None) -> str | None:
	if explicit_key:
		return explicit_key

	request = getattr(frappe, "request", None)
	if request and getattr(request, "args", None):
		for key in ("webhook_key", "key", "secret", "token"):
			if request.args.get(key):
				return request.args.get(key)

	headers_key = _header_value(
		"X-Webhook-Secret",
		"X-Huf-Webhook-Key",
		"X-Webhook-Key",
		"X-Hub-Signature",
	)
	if headers_key:
		return headers_key

	bearer = _bearer_token(_header_value("Authorization"))
	if bearer:
		return bearer

	if request and getattr(request, "form", None):
		for key in ("webhook_key", "key", "secret", "token"):
			if request.form.get(key):
				return request.form.get(key)

	if payload:
		for key in ("webhook_key", "key", "secret", "token"):
			if payload.get(key):
				return payload.get(key)

	return None


def _extract_flow_id(payload: dict | None = None, explicit_flow_id: str | None = None) -> str | None:
	if explicit_flow_id:
		return explicit_flow_id

	request = getattr(frappe, "request", None)
	if request and getattr(request, "args", None) and request.args.get("flow_id"):
		return request.args.get("flow_id")

	header_flow_id = _header_value("X-Huf-Flow-Id", "X-Flow-Id")
	if header_flow_id:
		return header_flow_id

	if request and getattr(request, "form", None) and request.form.get("flow_id"):
		return request.form.get("flow_id")

	if payload and payload.get("flow_id"):
		return payload.get("flow_id")

	return None


def _load_active_flow_definition(flow_id: str) -> tuple[object, dict]:
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)

	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	if defn_doc.status != "Active":
		frappe.throw(_("Flow '{0}' is not active").format(flow_id))

	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json
	return defn_doc, defn


def _resolve_flow_by_webhook_key(webhook_key: str | None) -> str:
	if not webhook_key:
		frappe.throw(_("Webhook key is required"), frappe.AuthenticationError)

	matches = []
	for row in frappe.get_all(
		"Flow Definition",
		filters={"status": "Active"},
		fields=["name", "definition_json"],
	):
		name = row.get("name") if isinstance(row, dict) else row.name
		definition_json = row.get("definition_json") if isinstance(row, dict) else row.definition_json
		defn = json.loads(definition_json) if isinstance(definition_json, str) else definition_json
		expected_auth = _webhook_entry_auth(defn or {})
		if expected_auth and hmac.compare_digest(str(webhook_key), str(expected_auth)):
			matches.append(name)

	if not matches:
		frappe.throw(_("Invalid webhook key"), frappe.AuthenticationError)
	if len(matches) > 1:
		frappe.throw(_("Webhook key matches multiple active flows; provide flow_id"))
	return matches[0]


def _run_flow_webhook(flow_id: str, webhook_key: str | None, payload: dict | None = None) -> dict:
	defn_doc, defn = _load_active_flow_definition(flow_id)

	# Validate webhook auth - mandatory, fail closed.
	if not _webhook_key_is_valid(defn, webhook_key):
		frappe.throw(_("Invalid webhook key"), frappe.AuthenticationError)

	# Switch execution identity to the flow owner so the run does not execute as Guest
	frappe.set_user(defn_doc.owner or "Administrator")

	if payload is None:
		payload = _parse_webhook_payload()

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
	# Frappe's make_form_dict drops query string arguments if the request has a JSON body.
	# We must manually extract webhook_key from request.args if it's missing.
	if webhook_key is None and getattr(frappe, "request", None) and frappe.request.args:
		webhook_key = frappe.request.args.get("webhook_key")

	return _run_flow_webhook(flow_id, webhook_key)


@frappe.whitelist(allow_guest=True)
def flow_webhook_clean(flow_id: str | None = None, webhook_key: str | None = None) -> dict:
	"""
	Clean URL webhook receiver for providers that reject query parameters.

	Key resolution is intentionally versatile while still failing closed:
	- Frappe Cloud/Press: X-Webhook-Secret header.
	- Huf/native callers: X-Huf-Webhook-Key or X-Huf-Flow-Id headers.
	- Generic providers: Authorization: Bearer <key>, form fields, JSON body, or legacy args.

	If flow_id is omitted, Huf resolves it by finding exactly one active
	trigger.webhook flow whose configured auth matches the resolved key.
	"""
	payload = _parse_webhook_payload()
	resolved_key = _extract_webhook_key(payload, webhook_key)
	resolved_flow_id = _extract_flow_id(payload, flow_id) or _resolve_flow_by_webhook_key(resolved_key)
	return _run_flow_webhook(resolved_flow_id, resolved_key, payload)


@frappe.whitelist()
def schedule_flow(flow_id: str, cron: str, schedule_name: str | None = None, timezone: str = "UTC") -> dict:
	"""
	Schedule a flow to run periodically via Frappe Scheduler.

	DEPRECATED (Track-Item: G-TRIGGERS): scheduling now goes through Agent Trigger
	(see set_flow_schedule / get_flow_trigger / clear_flow_trigger below), which is
	dispatched by huf.ai.agent_scheduler.run_scheduled_agents and shares one
	mechanism with Agent scheduling. This Scheduled-Job-Type-based path is kept
	working, unmodified, for any pre-existing schedules created through it, but
	new callers should use set_flow_schedule instead.

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



# ---------------------------------------------------------------------------
# Flow Trigger APIs (Agent Trigger-backed; Track-Item: G-TRIGGERS)
# ---------------------------------------------------------------------------
#
# Contract for the flow builder UI:
#
#   set_flow_schedule(flow_id, scheduled_interval, interval_count=1, trigger_name=None)
#       Create or update a Schedule-type Agent Trigger targeting this flow
#       (target_type="Flow"). scheduled_interval is one of
#       Hourly/Daily/Weekly/Monthly/Yearly (matches Agent Trigger's own
#       `scheduled_interval` Select options). Idempotent: pass the
#       `trigger_name` returned by a prior call (or by get_flow_trigger) to
#       update that same trigger in place instead of creating a new one.
#       Returns {"trigger_name", "flow_id", "trigger_type": "Schedule",
#       "scheduled_interval", "interval_count", "next_execution", "disabled"}.
#
#   set_flow_doc_event_trigger(flow_id, reference_doctype, doc_event,
#                               condition=None, trigger_name=None)
#       Create or update a Doc Event-type Agent Trigger targeting this flow.
#       doc_event must be one of Agent Trigger's own `doc_event` Select
#       options (before_insert, after_insert, validate, before_save,
#       after_save, before_submit, on_submit, on_update, after_submit,
#       on_cancel, before_rename, after_rename, on_trash, after_delete).
#       condition is an optional Python expression evaluated against `doc`
#       (same semantics as Agent Trigger's existing condition field).
#       Returns {"trigger_name", "flow_id", "trigger_type": "Doc Event",
#       "reference_doctype", "doc_event", "condition", "disabled"}.
#
#   get_flow_trigger(flow_id)
#       Returns a list of every Agent Trigger row targeting this flow
#       (target_type="Flow"), each as a dict with the fields relevant to its
#       trigger_type (Schedule or Doc Event), plus trigger_name, disabled,
#       last_execution. Empty list if the flow has no triggers.
#
#   clear_flow_trigger(trigger_name)
#       Delete the named Agent Trigger, but ONLY if it targets a Flow
#       (target_type="Flow") — refuses (frappe.throw) to delete an
#       Agent-targeted trigger through this endpoint, to keep this surface
#       scoped to flows. Returns {"status": "deleted", "trigger_name"} or
#       {"status": "not_found", "trigger_name"}.


def _flow_trigger_row_to_dict(doc) -> dict:
	base = {
		"trigger_name": doc.name,
		"flow_id": doc.flow,
		"trigger_type": doc.trigger_type,
		"disabled": doc.disabled,
		"disabled_reason": doc.disabled_reason,
	}
	if doc.trigger_type == "Schedule":
		base.update({
			"scheduled_interval": doc.scheduled_interval,
			"interval_count": doc.interval_count,
			"next_execution": str(doc.next_execution) if doc.next_execution else None,
			"last_execution": str(doc.last_execution) if doc.last_execution else None,
		})
	elif doc.trigger_type == "Doc Event":
		base.update({
			"reference_doctype": doc.reference_doctype,
			"doc_event": doc.doc_event,
			"condition": doc.condition,
		})
	return base


@frappe.whitelist()
def set_flow_schedule(flow_id: str, scheduled_interval: str, interval_count: int = 1, trigger_name: str | None = None) -> dict:
	"""
	Create or update a Schedule-type Agent Trigger that starts Flow Runs for
	`flow_id`. See the "Flow Trigger APIs" contract above.
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)

	valid_intervals = {"Hourly", "Daily", "Weekly", "Monthly", "Yearly"}
	if scheduled_interval not in valid_intervals:
		frappe.throw(_("scheduled_interval must be one of {0}").format(", ".join(sorted(valid_intervals))))

	if trigger_name and frappe.db.exists("Agent Trigger", trigger_name):
		doc = frappe.get_doc("Agent Trigger", trigger_name)
		if doc.target_type != "Flow" or doc.flow != flow_id:
			frappe.throw(_("Trigger '{0}' does not target flow '{1}'").format(trigger_name, flow_id))
	else:
		doc = frappe.new_doc("Agent Trigger")
		doc.trigger_name = trigger_name or f"Flow Schedule: {flow_id} ({frappe.generate_hash(length=6)})"
		doc.target_type = "Flow"
		doc.flow = flow_id
		doc.trigger_type = "Schedule"

	doc.scheduled_interval = scheduled_interval
	doc.interval_count = interval_count or 1
	if not doc.next_execution:
		doc.next_execution = now_datetime()
	doc.save()

	return _flow_trigger_row_to_dict(doc)


@frappe.whitelist()
def set_flow_doc_event_trigger(
	flow_id: str,
	reference_doctype: str,
	doc_event: str,
	condition: str | None = None,
	trigger_name: str | None = None,
) -> dict:
	"""
	Create or update a Doc Event-type Agent Trigger that starts Flow Runs for
	`flow_id`. See the "Flow Trigger APIs" contract above.
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow '{0}' not found").format(flow_id), frappe.DoesNotExistError)

	if trigger_name and frappe.db.exists("Agent Trigger", trigger_name):
		doc = frappe.get_doc("Agent Trigger", trigger_name)
		if doc.target_type != "Flow" or doc.flow != flow_id:
			frappe.throw(_("Trigger '{0}' does not target flow '{1}'").format(trigger_name, flow_id))
	else:
		doc = frappe.new_doc("Agent Trigger")
		doc.trigger_name = trigger_name or f"Flow Doc Event: {flow_id} ({frappe.generate_hash(length=6)})"
		doc.target_type = "Flow"
		doc.flow = flow_id
		doc.trigger_type = "Doc Event"

	doc.reference_doctype = reference_doctype
	doc.doc_event = doc_event
	doc.condition = condition
	doc.save()

	return _flow_trigger_row_to_dict(doc)


@frappe.whitelist()
def get_flow_trigger(flow_id: str) -> list:
	"""
	List every Agent Trigger targeting `flow_id`. See the "Flow Trigger APIs"
	contract above.
	"""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	names = frappe.get_all(
		"Agent Trigger",
		filters={"target_type": "Flow", "flow": flow_id},
		pluck="name",
	)
	return [_flow_trigger_row_to_dict(frappe.get_doc("Agent Trigger", n)) for n in names]


@frappe.whitelist()
def clear_flow_trigger(trigger_name: str) -> dict:
	"""
	Delete a Flow-targeted Agent Trigger. See the "Flow Trigger APIs"
	contract above. Refuses to delete an Agent-targeted trigger.
	"""
	if not frappe.has_permission("Agent Trigger", "delete"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Agent Trigger", trigger_name):
		return {"status": "not_found", "trigger_name": trigger_name}

	target_type = frappe.db.get_value("Agent Trigger", trigger_name, "target_type")
	if target_type != "Flow":
		frappe.throw(_("Trigger '{0}' does not target a Flow; refusing to delete via clear_flow_trigger").format(trigger_name))

	frappe.delete_doc("Agent Trigger", trigger_name, ignore_missing=True)
	return {"status": "deleted", "trigger_name": trigger_name}


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
		frappe.log_error(
			frappe.get_traceback(),
			f"Scheduled Flow Execution Error: {flow_id}",
		)
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
		from huf.ai.flow_engine import resume_flow_run as engine_resume

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
		from huf.ai.flow_engine import approve_flow_run as engine_approve, _verify_approval_permission

		doc = frappe.get_doc("Flow Run", flow_run_id)
		waiting = json.loads(doc.waiting) if doc.waiting else {}
		_verify_approval_permission(waiting)

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


# TEMPORARILY DISABLED (2026-08-02):
# get_pending_approvals returns 403 even for Administrator, so the Approval
# Inbox bell is disabled until the permission check is fixed/replaced.
# See UnifiedHeader.tsx and ApprovalsBell.tsx for the related UI removal.
# ---------------------------------------------------------------------------
# @frappe.whitelist()
# def get_pending_approvals(limit: int = 50) -> list:
# 	"""
# 	Get list of flow runs waiting for approval that the current user can approve.
# 	
# 	This endpoint is used by the Approval Inbox feature to show users
# 	all pending approvals that require their attention.
# 	
# 	Args:
# 	    limit: Maximum number of results (default 50)
# 	
# 	Returns:
# 	    list of pending approval items with flow details
# 	"""
# 	if not frappe.has_permission("Flow Run", "read"):
# 		frappe.throw(_("Not permitted"), frappe.PermissionError)
# 
# 	user = frappe.session.user
# 	user_roles = set(frappe.get_roles(user))
# 
# 	# Get all flow runs waiting for approval
# 	pending_runs = frappe.get_all(
# 		"Flow Run",
# 		filters={"status": "Waiting Approval"},
# 		fields=[
# 			"name",
# 			"flow_id",
# 			"flow_version",
# 			"current_node_id",
# 			"status",
# 			"waiting",
# 			"started_at",
# 			"modified",
# 		],
# 		order_by="modified desc",
# 		limit_page_length=limit,
# 	)
# 
# 	results = []
# 
# 	for run in pending_runs:
# 		try:
# 			waiting = json.loads(run.waiting) if run.waiting else {}
# 		except (json.JSONDecodeError, TypeError):
# 			waiting = {}
# 
# 		approval_type = waiting.get("approval_type", "role")
# 		can_approve = False
# 
# 		# Check if current user can approve this flow run
# 		if approval_type == "role":
# 			approver_role = waiting.get("approver_role")
# 			if approver_role and approver_role in user_roles:
# 				can_approve = True
# 		elif approval_type in ("user", "users"):
# 			approver_users = waiting.get("approver_users", [])
# 			if isinstance(approver_users, str):
# 				approver_users = [u.strip() for u in approver_users.split(",") if u.strip()]
# 			if user in approver_users:
# 				can_approve = True
# 
# 		if can_approve:
# 			results.append({
# 				"flow_run_id": run.name,
# 				"flow_id": run.flow_id,
# 				"flow_version": run.flow_version,
# 				"current_node_id": run.current_node_id,
# 				"title": waiting.get("title", "Approval Required"),
# 				"instructions": waiting.get("instructions", ""),
# 				"approval_type": approval_type,
# 				"approver_role": waiting.get("approver_role"),
# 				"approver_users": waiting.get("approver_users", []),
# 				"started_at": str(run.started_at) if run.started_at else None,
# 				"waiting_since": str(run.modified) if run.modified else None,
# 				"view_link": f"/huf/flows/{run.flow_id}?run={run.name}",
# 			})
# 
# 	return results
