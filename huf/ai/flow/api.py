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
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, now_datetime


# ---------------------------------------------------------------------------
# Time helpers
#
# Frappe stores and returns datetimes as naive strings in the *site* time zone
# (System Settings -> Time Zone). Browsers cannot know that zone, so everything
# this module sends to the UI is converted to a time-zone-aware UTC ISO string.
# ---------------------------------------------------------------------------

# A Queued/Running Flow Run that has not changed for this long is offered
# "Mark as failed" to System Managers (the worker that owned it is gone).
STALE_RUN_MINUTES = 15
STALE_STATUSES = ("Queued", "Running")


def _utc_iso(value) -> str | None:
	"""Naive site-time-zone datetime (or its string) -> ``2026-10-28T01:45:00Z``. None stays None."""
	if not value:
		return None
	from datetime import timezone

	from frappe.utils import get_datetime, get_system_timezone

	try:
		import zoneinfo

		dt = get_datetime(value)
		if dt.tzinfo is None:
			dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(get_system_timezone()))
		return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
	except Exception:
		return str(value)


def _expire_overdue_approvals(flow_run_id: str | None = None) -> None:
	"""Lazy approval expiry: an approval whose deadline has passed is routed on its timeout edge
	before it is read, so the answer never depends on the scheduler tick alone.

	One run (``flow_run_id``) or every overdue run. The continuation is queued to a worker. A
	failure here must never break the read.
	"""
	try:
		from huf.ai.flow import engine, triggers

		if flow_run_id:
			waiting = frappe.db.get_value("Flow Run", {"name": flow_run_id, "status": "Waiting Approval"}, "waiting")
			if not waiting:
				return
			try:
				data = json.loads(waiting)
			except (TypeError, ValueError):
				return
			if isinstance(data, dict) and engine.approval_expired(data, now_datetime()):
				engine.expire_approval(flow_run_id, enqueue=True)
		else:
			triggers.expire_due_approvals(enqueue=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Flow lazy approval expiry")


def _is_stale(status: str | None, modified) -> bool:
	"""True for a Queued/Running run whose last change is older than STALE_RUN_MINUTES."""
	if status not in STALE_STATUSES or not modified:
		return False
	from frappe.utils import get_datetime

	return get_datetime(modified) < add_to_date(now_datetime(), minutes=-STALE_RUN_MINUTES)


def _can_mark_failed() -> bool:
	return "System Manager" in frappe.get_roles(frappe.session.user)


# Step title shown when a saved step has no title of its own (flows written outside the editor).
_STEP_TYPE_TITLES = {
	"agent.run": "Run agent",
	"tool.call": "Call tool",
	"router.llm": "LLM Router",
	"condition": "Condition (If/Else)",
	"foreach": "Loop",
	"human.approval": "Human in Loop",
	"end": "End",
	"transform": "Transform data",
}


def _node_labels(flow_id: str | None) -> dict:
	"""``{node_id: step title}`` from the flow's saved definition (UI titles live in ``_label``)."""
	if not flow_id or not frappe.db.exists("Flow Definition", flow_id):
		return {}
	raw = frappe.db.get_value("Flow Definition", flow_id, "definition_json")
	try:
		defn = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except (json.JSONDecodeError, TypeError):
		return {}
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	return {
		n["id"]: (n.get("_label") or _STEP_TYPE_TITLES.get(n.get("type")) or n["id"])
		for n in (nodes or [])
		if isinstance(n, dict) and n.get("id")
	}


def _trigger_event(doc, payload: dict) -> str | None:
	"""Document event (``after_insert``, ``on_submit``...) that started a Doc Event run, read from the flow's data trigger.

	The event is not part of the document payload, so it comes from the data trigger of the flow's definition that
	matches the document type (the definition the run was pinned to when there is one).
	"""
	if doc.trigger_type != "Doc Event":
		return None
	raw = doc.pinned_definition or frappe.db.get_value("Flow Definition", doc.flow_id, "definition_json")
	try:
		defn = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except (json.JSONDecodeError, TypeError):
		return None
	if isinstance(defn, dict) and isinstance(defn.get("graph"), dict):
		defn = defn["graph"]  # a pinned definition wraps the graph with its fingerprint
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	triggers = [
		n.get("config") or {}
		for n in (nodes or [])
		if isinstance(n, dict) and n.get("type") == "trigger.doc-event"
	]
	doctype = payload.get("doctype") if isinstance(payload, dict) else None
	for cfg in triggers:
		if cfg.get("doctype") == doctype and cfg.get("event"):
			return cfg["event"]
	return next((c["event"] for c in triggers if c.get("event")), None)


def _flow_names(flow_ids) -> dict:
	flow_ids = list({f for f in flow_ids if f})
	if not flow_ids:
		return {}
	return {
		r.flow_id: r.flow_name
		for r in frappe.get_all(
			"Flow Definition", filters={"flow_id": ["in", flow_ids]}, fields=["flow_id", "flow_name"]
		)
	}


@frappe.whitelist()
def get_site_timezone() -> str:
	"""IANA name of the site time zone (System Settings), for rendering naive Frappe datetimes."""
	from frappe.utils import get_system_timezone

	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.AuthenticationError)
	return get_system_timezone()


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


@frappe.whitelist()
def get_trigger_doctype_info(doctype: str) -> dict:
	"""What a Data trigger needs to know about a document type: whether it can be submitted (and so cancelled)."""
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Document type {0} was not found").format(doctype), frappe.DoesNotExistError)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return {"doctype": doctype, "is_submittable": bool(frappe.get_meta(doctype).is_submittable)}


def _set_flow_status(flow_id: str, status: str) -> dict:
	"""Switch a Flow Definition between Draft and Active; the write permission is checked on the document."""
	if not frappe.db.exists("Flow Definition", flow_id):
		frappe.throw(_("Flow {0} was not found").format(flow_id), frappe.DoesNotExistError)
	doc = frappe.get_doc("Flow Definition", flow_id)
	if not frappe.has_permission("Flow Definition", "write", doc=doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doc.status != status:
		doc.status = status
		doc.save()
	# Publishing / unpublishing changes which flows document events may start; do not wait for the cache to expire.
	from huf.ai.flow.triggers import clear_trigger_cache

	clear_trigger_cache()
	return {"flow_id": doc.flow_id, "status": doc.status}


@frappe.whitelist()
def publish_flow(flow_id: str) -> dict:
	"""Publish a flow (status Active): its triggers start firing. Refused with a readable message if the flow is not runnable."""
	return _set_flow_status(flow_id, "Active")


@frappe.whitelist()
def unpublish_flow(flow_id: str) -> dict:
	"""Take a published flow back to Draft: webhook calls are refused and schedule / document-event triggers stop firing.

	Runs already in progress finish; nothing is deleted. Publish again to restore the triggers.
	"""
	return _set_flow_status(flow_id, "Draft")


# ---------------------------------------------------------------------------
# Flow Run APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def run_flow(
	flow_id: str,
	payload: str | dict | None = None,
) -> dict:
	"""
	Start a new flow run.

	Args:
	    flow_id: Flow ID to run
	    payload: Initial input (JSON string or dict)

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

	_expire_overdue_approvals(flow_run_id)
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

	stale = _is_stale(doc.status, doc.modified)
	return {
		"flow_run_id": doc.name,
		"flow_id": doc.flow_id,
		"flow_name": _flow_names([doc.flow_id]).get(doc.flow_id) or doc.flow_id,
		"flow_version": doc.flow_version,
		"mode": doc.mode,
		"status": doc.status,
		"trigger_type": doc.trigger_type,
		"current_node_id": doc.current_node_id,
		"hop_count": doc.hop_count,
		"context_json": ctx,
		"waiting": waiting,
		"node_labels": _node_labels(doc.flow_id),
		"trigger_event": _trigger_event(doc, ctx),
		"last_error": doc.last_error,
		"last_agent_run": doc.last_agent_run,
		"started_at": _utc_iso(doc.started_at),
		"completed_at": _utc_iso(doc.completed_at),
		"stale": stale,
		"can_mark_failed": stale and _can_mark_failed(),
		"stale_after_minutes": STALE_RUN_MINUTES,
	}


@frappe.whitelist()
def mark_flow_run_failed(flow_run_id: str) -> dict:
	"""Fail a Flow Run that is stuck in Queued/Running (System Manager only).

	Only a run that has not changed for ``STALE_RUN_MINUTES`` can be failed this way; a run that is
	really progressing, or already finished, is left alone with a clear message.
	"""
	if not _can_mark_failed():
		frappe.throw(_("Only a System Manager can mark a run as failed."), frappe.PermissionError)
	if not frappe.db.exists("Flow Run", flow_run_id):
		frappe.throw(_("Flow Run '{0}' not found").format(flow_run_id), frappe.DoesNotExistError)

	from huf.ai.flow import engine

	# Same lock a live worker holds while it advances the run: if it is held, the run is not stuck.
	if not engine._acquire_run_lock(flow_run_id):
		frappe.throw(_("This run is being worked on right now, so it cannot be marked as failed."))
	try:
		doc = frappe.get_doc("Flow Run", flow_run_id)
		if doc.status not in STALE_STATUSES:
			frappe.throw(
				_("This run is {0}, so it cannot be marked as failed. Only runs stuck in Queued or Running can.").format(
					doc.status
				)
			)
		if not _is_stale(doc.status, doc.modified):
			frappe.throw(
				_("This run changed less than {0} minutes ago and may still be working. Try again later.").format(
					STALE_RUN_MINUTES
				)
			)

		# Conditional on the run not being finished: a worker that completed it meanwhile wins.
		failed = engine._fail_flow_run(
			doc, _("Marked as failed by {0}: the run was stuck in {1}.").format(frappe.session.user, doc.status)
		)
		if not failed:
			frappe.throw(_("This run has already finished, so it was left as it is."))
		frappe.db.commit()  # nosemgrep -- the change must be durable before the lock is released
	finally:
		engine._release_run_lock(flow_run_id)
	doc.reload()
	return {"flow_run_id": doc.name, "status": doc.status}


_FLOW_RUN_LIST_FIELDS = [
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
	"modified",
]


def _shape_run_rows(rows: list) -> list:
	names = _flow_names(r.flow_id for r in rows)
	can_fail = _can_mark_failed()
	for r in rows:
		r["flow_name"] = names.get(r.flow_id) or r.flow_id
		r["stale"] = _is_stale(r.status, r.modified)
		r["can_mark_failed"] = r["stale"] and can_fail
		r["started_at"] = _utc_iso(r.started_at)
		r["completed_at"] = _utc_iso(r.completed_at)
		r["modified"] = _utc_iso(r.modified)
	return rows


@frappe.whitelist()
def list_flow_runs(flow_id: str | None = None, status: str | None = None, limit: int = 20) -> list:
	"""
	List flow runs with optional filters.

	Args:
	    flow_id: Filter by flow_id
	    status: Filter by status
	    limit: Max results (default 20)

	Returns:
	    list of flow run summaries (times are UTC ISO strings)
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	_expire_overdue_approvals()
	filters = {}
	if flow_id:
		filters["flow_id"] = flow_id
	if status:
		filters["status"] = status

	runs = frappe.get_all(
		"Flow Run",
		filters=filters,
		fields=_FLOW_RUN_LIST_FIELDS,
		order_by="modified desc",
		limit_page_length=limit,
	)

	return _shape_run_rows(runs)


@frappe.whitelist()
def list_flow_runs_page(
	status: str | None = None,
	flow_id: str | None = None,
	search: str | None = None,
	from_date: str | None = None,
	start: int = 0,
	limit: int = 20,
) -> dict:
	"""Paged Flow Run list across all flows for the Executions page.

	``from_date`` is a UTC ISO string (what a browser sends); it is converted to the site time zone
	before comparing with the stored naive ``started_at``. ``search`` matches flow name or run id.
	Returns ``{"items": [...], "total": n}``.
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	_expire_overdue_approvals()
	start, limit = max(int(start or 0), 0), min(max(int(limit or 20), 1), 200)
	filters: list = []
	if status and status != "all":
		filters.append(["status", "=", status])
	if flow_id:
		filters.append(["flow_id", "=", flow_id])
	if from_date:
		from frappe.utils import convert_utc_to_system_timezone, get_datetime

		dt = get_datetime(from_date)
		if dt.tzinfo is not None:
			dt = convert_utc_to_system_timezone(dt).replace(tzinfo=None)
		filters.append(["started_at", ">=", dt])

	or_filters = None
	if search and search.strip():
		term = f"%{search.strip()}%"
		matching = [
			r.flow_id
			for r in frappe.get_all(
				"Flow Definition", filters={"flow_name": ["like", term]}, fields=["flow_id"], limit_page_length=500
			)
		]
		or_filters = [["name", "like", term]]
		if matching:
			or_filters.append(["flow_id", "in", matching])

	total = len(frappe.get_all("Flow Run", filters=filters, or_filters=or_filters, pluck="name"))
	rows = frappe.get_all(
		"Flow Run",
		filters=filters,
		or_filters=or_filters,
		fields=_FLOW_RUN_LIST_FIELDS,
		order_by="started_at desc, creation desc",
		limit_start=start,
		limit_page_length=limit,
	)
	return {"items": _shape_run_rows(rows), "total": total}


@frappe.whitelist()
def get_flow_step_labels(items: str | list) -> list:
	"""Readable "Flow: <name> > <step title>" labels for Agent Runs made by flow steps.

	``items`` is a list of ``{"flow_run": ..., "flow_node_id": ...}``; the result is aligned with it
	(``None`` where the run or flow is unknown).
	"""
	if not frappe.has_permission("Flow Run", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if isinstance(items, str):
		items = json.loads(items or "[]")

	run_flow_ids = {}
	for run_name in {i.get("flow_run") for i in items if i.get("flow_run")}:
		run_flow_ids[run_name] = frappe.db.get_value("Flow Run", run_name, "flow_id")
	names = _flow_names(run_flow_ids.values())
	labels = {fid: _node_labels(fid) for fid in set(run_flow_ids.values()) if fid}

	out = []
	for i in items:
		fid = run_flow_ids.get(i.get("flow_run"))
		if not fid:
			out.append(None)
			continue
		node_id = i.get("flow_node_id")
		step = labels.get(fid, {}).get(node_id) or node_id
		flow = names.get(fid) or fid
		out.append(f"Flow: {flow} > {step}" if step else f"Flow: {flow}")
	return out


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
	"""The webhook secret the caller sent: the ``X-Huf-Secret`` header only.

	A secret in the URL ends up in access logs, browser history and proxies, so ``?secret=`` is not
	accepted at all.
	"""
	return _request_headers().get(WEBHOOK_SECRET_HEADER) or None


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


#: Webhook endpoints are public, so they are throttled per caller address before anything else runs.
#: Over the limit Frappe answers 429 with a generic message, whatever the flow or secret.
WEBHOOK_RATE_LIMIT = 60
WEBHOOK_RATE_WINDOW_SECONDS = 60


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=WEBHOOK_RATE_LIMIT, seconds=WEBHOOK_RATE_WINDOW_SECONDS)
def flow_webhook(flow_id: str | None = None) -> dict:
	"""
	Webhook trigger endpoint for flows.

	The flow is named by ``flow_id`` (argument, ``?flow_id=`` or the ``X-Huf-Flow-Id`` header) and the
	caller authenticates with that flow's ``trigger.webhook`` secret, sent ONLY as the ``X-Huf-Secret``
	header (constant-time compare, fails closed; ``?secret=`` is not accepted). The HTTP method must
	equal the node's configured ``method``. Only Active flows accept webhooks. An unknown flow, an
	inactive flow and a wrong or missing secret all get the same 403. At most 60 calls a minute per
	caller address, then 429.
	"""
	return _run_flow_webhook(_extract_flow_id(flow_id), _presented_secret())


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=WEBHOOK_RATE_LIMIT, seconds=WEBHOOK_RATE_WINDOW_SECONDS)
def flow_webhook_clean(flow_id: str | None = None) -> dict:
	"""
	Webhook receiver for providers that cannot put the flow id in a query string.

	Same rules as :func:`flow_webhook`: the secret comes from the ``X-Huf-Secret`` header only, and
	the flow must be named (argument, ``?flow_id=`` or the ``X-Huf-Flow-Id`` header). A flow is never
	looked up by its secret.
	"""
	return _run_flow_webhook(_extract_flow_id(flow_id), _presented_secret())


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
def handle_run_flow(flow_id: str, payload: str | dict | None = None, **kwargs) -> dict:
	"""
	Agent tool: Start a flow from within an agent.

	Args:
	    flow_id: Flow ID to run
	    payload: Initial payload (dict or JSON string)

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

		flow_run = create_flow_run(flow_id=flow_id, payload=payload or {})
		
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
		_expire_overdue_approvals(flow_run_id)
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

	_expire_overdue_approvals()

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
			"started_at": _utc_iso(run.started_at),
			"waiting_since": _utc_iso(run.modified),
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


# ---------------------------------------------------------------------------
# Approver roles
# ---------------------------------------------------------------------------

# Roles Frappe assigns automatically or reserves for the framework: nobody can be asked to
# "hold" them, so offering them as an approver is a trap (All/Guest match everyone or no one).
_AUTOMATIC_ROLES = frozenset({"All", "Guest", "Administrator"})

# Desk-only utility roles shipped by the Frappe framework. They gate Desk features (reports,
# scripts, dashboards, ...) and say nothing about who may approve a business step.
_DESK_ONLY_SYSTEM_ROLES = frozenset(
	{
		"Desk User",
		"Report Manager",
		"Script Manager",
		"Dashboard Manager",
		"Workspace Manager",
		"Prepared Report User",
		"Translator",
		"Inbox User",
		"Newsletter Manager",
		"Knowledge Base Contributor",
		"Knowledge Base Editor",
		"Blogger",
		"Website Manager",
		"Maintenance Manager",
		"Maintenance User",
	}
)

# Huf's own approver-capable roles, in display order. ``Huf Admin`` is backed by System Manager
# (huf.permissions.HUF_ROLE_FRAPPE_ROLE_MAP), so System Manager is what a person actually holds.
_HUF_APPROVER_ROLES = ("System Manager", "Huf Manager", "Huf User", "Huf Viewer")
_HUF_HIDDEN_ROLES = frozenset({"Huf Admin", "Huf Gateway User"})


@frappe.whitelist()
def get_approver_roles() -> list[dict]:
	"""Roles a Flow author may pick for a Human Approval step.

	Huf roles come first, then every other enabled role (custom and app-defined business roles),
	without the automatic roles (All, Guest, Administrator) and the framework's desk-only roles.
	Returns ``[{name, group}]`` with ``group`` ``"Huf"`` or ``"Other"``.
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	rows = frappe.get_all("Role", filters={"disabled": 0}, fields=["name"], order_by="name asc", limit_page_length=0)
	available = {row.name for row in rows}
	hidden = _AUTOMATIC_ROLES | _DESK_ONLY_SYSTEM_ROLES | _HUF_HIDDEN_ROLES

	result = [{"name": name, "group": "Huf"} for name in _HUF_APPROVER_ROLES if name in available]
	huf = {item["name"] for item in result}
	result.extend(
		{"name": row.name, "group": "Other"} for row in rows if row.name not in huf and row.name not in hidden
	)
	return result
