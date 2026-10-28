"""Flow trigger dispatch: webhook matching, schedule (cron) and doc-event runs.

Source of truth for trigger config is ``docs/flow/FIELD_CONTRACT.md`` / ``graph_ir.schema.json``:

* ``trigger.webhook``   ``{method: GET|POST, secret}``
* ``trigger.schedule``  ``{cron}``            5-part cron, evaluated in server system time
* ``trigger.doc-event`` ``{doctype, event}``  event in ``DOC_EVENT_MAP``

Everything here is dispatch only. The run itself is created and executed by the engine
(``create_flow_run`` / ``run_flow``); ``start_flow_run`` is the single adapter onto it.

The functions that need no database (``match_webhook_trigger``, ``cron_is_due``,
``trigger_nodes``, ``build_doc_event_index``) are pure and unit tested without a bench.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta

import frappe

WEBHOOK_TYPE = "trigger.webhook"
SCHEDULE_TYPE = "trigger.schedule"
DOC_EVENT_TYPE = "trigger.doc-event"

MIN_SECRET_LENGTH = 8

# Schema event enum (graph_ir.schema.json TriggerDocEventNode.config.event) -> the Frappe
# doc_events method name that fires it. Identical names today; the map is explicit so the
# schema enum and the hook wiring in hooks.py can never drift silently (see tests).
DOC_EVENT_MAP = {
	"after_insert": "after_insert",
	"on_update": "on_update",
	"on_submit": "on_submit",
	"on_cancel": "on_cancel",
	"on_trash": "on_trash",
}

# Doctypes whose events must never start a flow: Huf's own bookkeeping (a flow reacting to
# the rows its own run writes would loop). Everything in the "Huf" module is skipped too.
RECURSION_SKIP_DOCTYPES = frozenset(
	{
		"Flow Run",
		"Flow Definition",
		"Agent Run",
		"Agent Run Event",
		"Agent Conversation",
		"Agent Message",
		"Error Log",
		"Comment",
		"Version",
		"Activity Log",
		"Access Log",
		"Scheduled Job Log",
		"Email Queue",
	}
)
HUF_MODULE = "Huf"

DOC_EVENT_CACHE_KEY = "huf:flow_doc_event_index"
DOC_EVENT_CACHE_TTL = 300


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_definition(definition_json) -> dict:
	if isinstance(definition_json, dict):
		return definition_json
	try:
		parsed = json.loads(definition_json or "{}")
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def trigger_nodes(defn: dict, node_type: str) -> list[dict]:
	"""Trigger nodes of ``node_type`` that are entry points of the graph (``entry`` is an id or a list)."""
	entry = defn.get("entry")
	entry_ids = set(entry) if isinstance(entry, list) else {entry}
	return [
		n
		for n in defn.get("nodes", []) or []
		if isinstance(n, dict) and n.get("type") == node_type and n.get("id") in entry_ids
	]


def match_webhook_trigger(defn: dict, presented_secret: str | None, method: str | None):
	"""Find the ``trigger.webhook`` node a request is allowed to start.

	Returns ``(node, reason)``; ``node`` is None on rejection and ``reason`` is one of
	``no_trigger`` / ``bad_secret`` / ``bad_method`` (``ok`` on success). Fails closed:
	a node with a missing or too-short secret never matches. The method is only checked after the
	secret matched, so an unauthenticated caller cannot probe a flow's configured method.
	``method=None`` means "not an HTTP request" (direct Python call) and skips the method check.
	"""
	nodes = trigger_nodes(defn, WEBHOOK_TYPE)
	if not nodes:
		return None, "no_trigger"

	presented = str(presented_secret or "").encode()
	matched = None
	for node in nodes:
		expected = (node.get("config") or {}).get("secret")
		if not isinstance(expected, str) or len(expected) < MIN_SECRET_LENGTH:
			continue
		# Evaluate every node (no early exit) so timing does not reveal which one matched.
		if hmac.compare_digest(presented, expected.encode()) and matched is None:
			matched = node
	if matched is None:
		return None, "bad_secret"

	if method is not None:
		configured = str((matched.get("config") or {}).get("method") or "").upper()
		if configured not in ("GET", "POST") or str(method).upper() != configured:
			return None, "bad_method"
	return matched, "ok"


def cron_is_due(cron: str, minute: datetime) -> bool:
	"""True when the 5-part ``cron`` fires exactly at ``minute`` (seconds are ignored)."""
	from croniter import croniter

	if not isinstance(cron, str) or len(cron.split()) != 5 or not croniter.is_valid(cron):
		return False
	minute = minute.replace(second=0, microsecond=0)
	# Previous fire time strictly before (minute + 1s) is `minute` iff the cron matches `minute`.
	return croniter(cron, minute + timedelta(seconds=1)).get_prev(datetime) == minute


def latest_due_minute(cron: str, now: datetime, window_seconds: int = 60) -> datetime | None:
	"""The most recent minute at or before ``now`` (and after ``now - window_seconds``) on which ``cron`` fires.

	The scheduler only ticks every ``scheduler_tick_interval`` seconds (Frappe default: 240), so asking
	"does the cron match this exact minute" would miss most runs (a daily 09:00 flow would fire on one
	tick in four). Looking back over one tick window fires each due minute exactly once.
	"""
	from croniter import croniter

	if not isinstance(cron, str) or len(cron.split()) != 5 or not croniter.is_valid(cron):
		return None
	now = now.replace(second=0, microsecond=0)
	latest = croniter(cron, now + timedelta(seconds=1)).get_prev(datetime)
	return latest if latest > now - timedelta(seconds=max(window_seconds, 60)) else None


def build_doc_event_index(rows) -> dict:
	"""``rows`` = iterable of ``(flow_id, owner, definition)`` -> ``{doctype: {frappe_event: [entry]}}``.

	Each entry is ``{"flow", "owner", "node"}``. Unknown events and malformed nodes are dropped.
	"""
	index: dict = {}
	for flow_id, owner, defn in rows:
		for node in trigger_nodes(defn, DOC_EVENT_TYPE):
			config = node.get("config") or {}
			doctype = config.get("doctype")
			frappe_event = DOC_EVENT_MAP.get(config.get("event"))
			if not doctype or not frappe_event:
				continue
			index.setdefault(doctype, {}).setdefault(frappe_event, []).append(
				{"flow": flow_id, "owner": owner, "node": node.get("id")}
			)
	return index


def is_recursion_skipped(doctype: str, module: str | None = None) -> bool:
	return doctype in RECURSION_SKIP_DOCTYPES or module == HUF_MODULE


# ---------------------------------------------------------------------------
# Engine adapter
# ---------------------------------------------------------------------------


def start_flow_run(
	flow_id: str,
	payload: dict,
	trigger_type: str,
	trigger_node_id: str | None = None,
	user: str | None = None,
	enqueue: bool = True,
):
	"""Create a Flow Run and run it (queued by default). The only place that talks to the engine.

	The row is created for the trusted dispatcher (activation of the flow by its owner already
	authorised the trigger); execution identity is ``user``. When the graph has several triggers the
	run starts at the one that fired (``trigger_node_id``).
	"""
	from huf.ai.flow import engine

	if user:
		frappe.set_user(user)
	flow_run = engine.create_flow_run(
		flow_id=flow_id, payload=payload, trigger_type=trigger_type, ignore_permissions=True
	)
	if trigger_node_id and flow_run.current_node_id != trigger_node_id:
		flow_run.db_set("current_node_id", trigger_node_id)
	if enqueue:
		frappe.enqueue("huf.ai.flow.engine.run_flow", queue="default", flow_run_name=flow_run.name)
	else:
		engine.run_flow(flow_run.name)
	return flow_run


def run_trigger_job(flow_id: str, payload: dict, trigger_type: str, trigger_node_id: str, run_as: str):
	"""Background job: start (and run) one triggered flow as ``run_as``."""
	frappe.set_user(run_as)
	frappe.flags.huf_flow_run_origin = True  # docs written by this run must not re-trigger flows
	start_flow_run(flow_id, payload, trigger_type, trigger_node_id, user=run_as, enqueue=False)


# ---------------------------------------------------------------------------
# Active flow lookup
# ---------------------------------------------------------------------------


def _active_flows_with(trigger_type: str):
	rows = frappe.get_all(
		"Flow Definition",
		filters={"status": "Active", "definition_json": ["like", f"%{trigger_type}%"]},
		fields=["name", "owner", "definition_json"],
	)
	for row in rows:
		yield row["name"], row["owner"], parse_definition(row["definition_json"])


def active_webhook_flows():
	return _active_flows_with(WEBHOOK_TYPE)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def _legacy_trigger_automation_active(flow_id: str) -> bool:
	"""set_flow_trigger() binds an Automation that fires this flow's schedule itself; do not double fire."""
	return bool(frappe.db.exists("Automation", {"name": f"Flow Trigger: {flow_id}", "status": "Active"}))


def _already_fired(flow_id: str, node_id: str, scheduled_for: str) -> bool:
	"""Durable once-per-minute marker: the Flow Run created for that (node, minute) is the record."""
	return bool(
		frappe.db.exists(
			"Flow Run",
			[
				["flow_definition", "=", flow_id],
				["trigger_type", "=", "Schedule"],
				["trigger_payload", "like", f'%"trigger_node": "{node_id}"%'],
				["trigger_payload", "like", f'%"scheduled_for": "{scheduled_for}"%'],
			],
		)
	)


def run_due_schedule_flows(now: datetime | None = None) -> list[str]:
	"""Scheduler entry (every minute): start every Active flow whose ``trigger.schedule`` cron is due.

	Once per (flow, trigger node, due minute): a cache lock guards concurrent scheduler ticks and the
	Flow Run created for that minute is the durable marker (survives cache flush). A due minute is
	caught up if it fell inside the last scheduler tick window; older missed minutes (scheduler down)
	are not replayed.
	"""
	from frappe.utils import now_datetime

	minute = (now or now_datetime()).replace(second=0, microsecond=0)
	window = int(frappe.conf.get("scheduler_tick_interval") or 240)
	started: list[str] = []

	for flow_id, owner, defn in _active_flows_with(SCHEDULE_TYPE):
		if _legacy_trigger_automation_active(flow_id):
			continue
		for node in trigger_nodes(defn, SCHEDULE_TYPE):
			cron = (node.get("config") or {}).get("cron")
			try:
				due = latest_due_minute(cron, minute, window)
				if due is None:
					continue
				scheduled_for = due.strftime("%Y-%m-%d %H:%M:%S")
				if _already_fired(flow_id, node["id"], scheduled_for):
					continue
				lock_key = f"huf:flow_schedule:{flow_id}:{node['id']}:{scheduled_for}"
				if frappe.cache().get_value(lock_key):
					continue
				frappe.cache().set_value(lock_key, 1, expires_in_sec=120)
				frappe.enqueue(
					"huf.ai.flow.triggers.run_trigger_job",
					queue="default",
					flow_id=flow_id,
					payload={"scheduled_for": scheduled_for, "trigger_node": node["id"], "cron": cron},
					trigger_type="Schedule",
					trigger_node_id=node["id"],
					run_as=owner,
				)
				started.append(flow_id)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"Flow schedule dispatch: {flow_id}")
	return started


def due_approval_run_names(rows, now) -> list[str]:
	"""Names of Waiting Approval rows (``{"name", "waiting"}``) whose ``waiting.timeout_at`` has passed."""
	from huf.ai.flow.engine import approval_expired

	due = []
	for row in rows:
		try:
			waiting = json.loads(row.get("waiting") or "{}")
		except (TypeError, ValueError):
			continue
		if isinstance(waiting, dict) and approval_expired(waiting, now):
			due.append(row["name"])
	return due


def expire_due_approvals(now: datetime | None = None) -> list[str]:
	"""Scheduler entry (every minute): apply ``timeout_next`` (or fail) for approvals past ``timeout_at``."""
	from frappe.utils import now_datetime

	from huf.ai.flow.engine import expire_approval

	now = now or now_datetime()
	rows = frappe.get_all(
		"Flow Run",
		filters={"status": "Waiting Approval", "waiting": ["like", "%timeout_at%"]},
		fields=["name", "waiting"],
		limit_page_length=500,
	)
	expired: list[str] = []
	for name in due_approval_run_names(rows, now):
		try:
			if expire_approval(name, now):
				expired.append(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow approval expiry: {name}")
	return expired


# ---------------------------------------------------------------------------
# Doc event
# ---------------------------------------------------------------------------


def get_doc_event_index() -> dict:
	cached = frappe.cache().get_value(DOC_EVENT_CACHE_KEY)
	if cached is not None:
		return cached if isinstance(cached, dict) else json.loads(cached)
	index = build_doc_event_index(_active_flows_with(DOC_EVENT_TYPE))
	frappe.cache().set_value(DOC_EVENT_CACHE_KEY, json.dumps(index), expires_in_sec=DOC_EVENT_CACHE_TTL)
	return index


def clear_trigger_cache(doc=None, method=None):
	"""Flow Definition save/trash hook: drop the doctype -> flows lookup."""
	frappe.cache().delete_value(DOC_EVENT_CACHE_KEY)


def _skip_context() -> bool:
	flags = frappe.flags
	return bool(
		getattr(flags, "in_install", False)
		or getattr(flags, "in_migrate", False)
		or getattr(flags, "in_patch", False)
		or getattr(flags, "in_import", False)
		or getattr(flags, "huf_flow_run_origin", False)
	)


def run_doc_event_flows(doc, method=None, *args, **kwargs):
	"""doc_events ``"*"`` hook: enqueue every Active flow with a matching ``trigger.doc-event``.

	Cheap on the hot path: one cached dict lookup by doctype. Matching flows are enqueued (never run
	inline) after commit, as the flow owner, only if the owner may read the document.
	"""
	if _skip_context() or method not in DOC_EVENT_MAP.values():
		return
	doctype = doc.doctype
	by_event = get_doc_event_index().get(doctype)
	if not by_event or method not in by_event:
		return
	if is_recursion_skipped(doctype, frappe.get_meta(doctype).module):
		return

	payload = None
	for entry in by_event[method]:
		owner = entry["owner"]
		try:
			if not frappe.db.get_value("User", owner, "enabled"):
				continue
			if not frappe.has_permission(doctype, "read", doc=doc, user=owner):
				continue
			if payload is None:
				payload = json.loads(frappe.as_json(doc.as_dict()))
			frappe.enqueue(
				"huf.ai.flow.triggers.run_trigger_job",
				queue="default",
				enqueue_after_commit=True,
				flow_id=entry["flow"],
				payload=payload,
				trigger_type="Doc Event",
				trigger_node_id=entry["node"],
				run_as=owner,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow doc-event dispatch: {entry['flow']}")
