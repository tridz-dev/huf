"""
Huf Flow Engine -- the ``FlowRuntime`` adapter over the shared graph executor.

Execution itself lives in :mod:`huf.ai.graph.executor`, which both this module
and (T-23) ``ProcedureRuntime`` drive. This module is the Flow-profile adapter:
it owns the ``Flow Definition`` / ``Flow Run`` documents, the Flow node
executors, Flow's realtime events, and Flow's approval lifecycle -- and nothing
about how a graph is walked.

The graph shape and every node's config field names are defined by
``huf/ai/graph/graph_ir.schema.json`` (``$defs/FlowGraph``) and documented in
``docs/flow/FIELD_CONTRACT.md``. Every executor reads exactly those names; there
are no aliases or legacy shapes (the product is pre-release).

What changed in T-22, and why (defect ids are from the track plan):

* **F-1 -- versioning.** ``Flow Definition.version`` was an integer bumped on
  every save, with no content identity, and ``run_flow`` re-fetched the
  *current* definition every time -- so a run resumed after an edit executed
  the new graph. A run now pins an immutable, content-addressed
  :class:`~huf.ai.graph.executor.PinnedVersion` (see :func:`_pinned_version`)
  and executes that exact graph for its whole life.
* **F-2 -- interpolation.** Four divergent ``{{...}}`` implementations with
  different semantics per node type are gone. ``{{var}}`` is NOT supported
  anywhere. Values come from the executor's single structured reference form,
  ``{"$from": "node.path"}``, and ``{"$template": "x {n}", "vars": {...}}``
  (see :meth:`~huf.ai.graph.executor.GraphContext.resolve`). The one place a
  plain string carries ``{name}`` placeholders is ``agent.run.prompt``, which
  is rendered from ``prompt_bindings`` by :func:`render_agent_prompt` with the
  same renderer as ``$template``.
* **F-3 -- loops.** Loop iteration no longer burns the run's hop budget; a
  bounded foreach carries its own iteration budget in the executor.
* **F-4 -- concurrency.** ``run_flow`` takes a distributed lock, and the
  executor refuses to advance a run that is not in an advanceable state, so
  two concurrent callers cannot both move the same cursor.
* **F-9 -- context.** ``context_json`` was re-parsed at roughly fifteen call
  sites. It is now parsed once per run into a
  :class:`~huf.ai.graph.executor.GraphContext` carried by
  :class:`FlowRunContext` and threaded through every executor.
* **I5 -- telemetry.** ``Agent Tool Call`` records are emitted by
  ``huf.ai.tools.invocation`` (through ``flow_tool_executor``), not assembled
  here. Exactly one record per atomic operation.
"""

import json
import re
import threading

import frappe
from frappe import _
from frappe.realtime import get_doc_room, get_user_room
from frappe.utils import now_datetime

from huf.ai.flow import state as flow_state  # noqa: F401  tests patch engine.flow_state
from huf.ai.flow.app_scope.access import flow_access
from huf.ai.flow.catalog import node_registry
from huf.ai.flow.engine_parts.code_run import (  # noqa: F401  moved out of this module; kept importable here
	_exec_code_run,
	_finish_code_step,
	_json_dict,
	fail_waiting_code_run,
	resume_code_node,
)
from huf.ai.flow.engine_parts.router_llm import _exec_router_llm, _router_llm_ai_block  # noqa: F401  moved out of this module; kept importable here
from huf.ai.flow.engine_parts.run_lock import (  # noqa: F401  moved out of this module; kept importable here
	_acquire_run_lock,
	_release_run_lock,
	_run_lock_key,
	_start_run_lock_heartbeat,
	_stop_run_lock_heartbeat,
)
from huf.ai.flow.engine_parts.state_nodes import (  # noqa: F401  moved out of this module; kept importable here
	_exec_state_delete,
	_exec_state_get,
	_exec_state_set,
	_state_node,
)
from huf.ai.flow.integrations import friendly_tool_error
from huf.ai.flow.nodes import adapters, subflow
from huf.ai.flow.nodes.routing.condition import exec_facts_condition
from huf.ai.flow.nodes.error_handler import first_error, run_error_handler
from huf.ai.flow.nodes.retry import policy_of as retry_policy_of
from huf.ai.flow.nodes.retry import run_with_retry
from huf.ai.flow.nodes.wait import exec_wait
from huf.ai.flow.orchestrator import (
	build_flow_context_system_message,
	build_router_prompt,
)
from huf.ai.flow.runs import member as flow_member
from huf.ai.flow.runs.edges import edges_from_nodes
from huf.ai.flow.runs.outcome import record_outcome
from huf.ai.flow.support import facts
from huf.ai.flow.support.approval_card import waiting_fields
from huf.ai.flow.support.approval_notifications import _clear_flow_notifications, _send_approval_notifications
from huf.ai.flow.support.approvals.approver_veto import refuse_if_vetoed
from huf.ai.flow.support.approvals.approvers import approval_expired, check_approver, evaluate_approval_policy
from huf.ai.flow.support.pii import log_flow_error, mask_text
from huf.ai.flow.support.plain.transform_text import plain_transform_error
from huf.ai.flow.support.redact import pinned_json
from huf.ai.flow.support.router_text import (
	_router_completion,
	build_router_llm_prompt,
	choose_option,
	render_text_refs,
	resolve_router_model,
)
from huf.ai.flow.support.results.tool_result import normalize_tool_result
from huf.ai.flow.support.results.turned_off import is_turned_off, turned_off_result
from huf.ai.flow.testrun import gate as test_gate
from huf.ai.flow.testrun import stored_mode
from huf.ai.flow.tool_executor import execute as execute_tool
from huf.ai.flow.tool_executor import tool_run_context, with_step_limit
from huf.ai.gateways.slack import flow_hooks
from huf.ai.graph.error_copy import (
	approval_timeout_message,
	describe_exception,
	describe_run_error,
	no_route_message,
	plain_error,
	step_failed_sentence,
	step_ref,
	step_title,
	tool_timeout_message,
)
from huf.ai.graph.executor import (
	ExecutionPolicy,
	ExecutionResult,
	ExecutionState,
	GraphContext,
	GraphExecutor,
	GraphProgram,
	NodeSpec,
	Outcome,
	PauseRequest,
	PinnedVersion,
	Router,
	RoutingError,
	RoutingMode,
)
from huf.ai.graph.expressions import ExpressionLimitError, evaluate_bool, parse_expression
from huf.ai.graph.templates import TemplateError, render_template
from huf.ai.graph.transforms import Limits as TransformLimits
from huf.ai.graph.transforms import run_transform
from huf.ai.output_budget import OutputBudget, OutputBudgetExceeded, enforce_output_budget
from huf.ai.tools.invocation import RunContext
from huf.ai.transaction import commit_if_background

DEFAULT_MAX_HOPS = 100

RUN_LOCK_STEP_SECONDS = 90
"""The step duration the run lock TTL is sized for. Not a limit: longer steps are covered by the heartbeat."""

RUN_LOCK_MARGIN_SECONDS = 30

RUN_LOCK_TTL_SECONDS = RUN_LOCK_STEP_SECONDS + RUN_LOCK_MARGIN_SECONDS
"""How long a run lock survives if its holder dies mid-execution: step time + margin.

The lock is held for a whole walk of the graph, and a step (agent, tool, code) has no hard upper bound, so the
TTL alone must never decide whether a worker is alive: the holder refreshes it from a heartbeat thread every
:data:`RUN_LOCK_HEARTBEAT_SECONDS`. A killed worker takes the thread with it and the lock expires within the TTL.
"""

RUN_LOCK_HEARTBEAT_SECONDS = RUN_LOCK_TTL_SECONDS / 4

_run_lock_heartbeats: dict[str, threading.Event] = {}

_run_lock_tokens: dict[str, str] = {}
"""The owner token this process wrote into each run lock it holds (key -> token)."""

# Compare-and-delete / compare-and-expire: act on the key only while it still holds our token, so a
# holder whose lock expired (and was taken by another worker) can neither extend nor release it.
_RELEASE_IF_OWNER = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"
_EXPIRE_IF_OWNER = (
	"if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) end return 0"
)

WAITING_STATUSES = ("Waiting User", "Waiting Approval", "Waiting Code", "Waiting Timer")

ADVANCEABLE_STATUSES = ("Running", "Queued")

#: How each Flow node type resolves its successor. One table, consulted in one
#: place by the executor's Router -- replacing the pre-T-22 split between the
#: ``_execute_node`` dispatch table and a type-switch inside ``_execute_loop``
#: (structural knot 3).
NODE_ROUTING = {
	"condition": RoutingMode.SELF_ROUTED,
	"router.llm": RoutingMode.SELF_ROUTED,
	"router.decision": RoutingMode.SELF_ROUTED,
	"split": RoutingMode.SELF_ROUTED,
	"wait": RoutingMode.SELF_ROUTED,
	"handoff": RoutingMode.SELF_ROUTED,
	# "output" is always terminal per spec/graph-ir.md section 2 ("next must be
	# absent or null") -- true for both the Procedure and Flow profiles.
	"output": RoutingMode.TERMINAL,
}

#: Node types whose handler may be paused by another subsystem writing the
#: ``Flow Run`` status (an agent asking the user a question, for instance).
#: For these -- and only these -- the adapter converts that external state
#: into a typed pause outcome, so the executor core still sees a value rather
#: than a status string it has to reload (structural knot 2).
EXTERNALLY_PAUSABLE_TYPES = ("agent.run",)


# ---------------------------------------------------------------------------
# Run-scoped context (F-9, structural knot 1)
# ---------------------------------------------------------------------------


class FlowRunContext(dict):
	"""Everything a node executor needs about the run it is part of.

	It subclasses ``dict`` and carries the definition's ``settings`` as its
	mapping content, so it is drop-in wherever a bare ``settings`` dict used
	to be passed -- including from tests that pass ``{}``. What it adds is the
	run-scoped state the executors used to dig out of the ``Flow Run``
	Document one field at a time: the parsed context, the pinned version, the
	flow id, the mode, the shared conversation (structural knot 1), and the
	fact that the context is parsed exactly once per run (F-9).
	"""

	def __init__(self, settings=None, *, flow_run=None, version=None, context=None):
		super().__init__(settings or {})
		self.flow_run = flow_run
		self.version = version
		self.context = context if context is not None else GraphContext()
		if version:
			self.context.step_ids = _step_ids(version.graph)
		self.flow_id = getattr(flow_run, "flow_id", None)
		self.run_id = getattr(flow_run, "name", None)
		self.mode = (getattr(flow_run, "mode", "") or "normal").lower()
		self.conversation = getattr(flow_run, "conversation", None)
		self.agent = getattr(flow_run, "agent", None) or None  # whose AI policy applies (huf_ai_feature_map)

	@property
	def budget(self):
		"""The run budget set in this worker (deadline, spend cap), or None."""
		from huf.ai.run_budget import peek_current_budget

		return peek_current_budget()

	@property
	def definition(self) -> dict:
		return self.version.graph if self.version else {}

	@property
	def edges(self) -> list:
		return effective_edges(self.definition)

	def save_context(self) -> None:
		"""Write the in-memory context back to the ``Flow Run``."""
		if self.flow_run is None:
			return
		self.flow_run.db_set("context_json", dump_context(self.context))
		self.context.dirty = False


NODE_OUTPUTS_KEY = "__node_outputs__"
"""Reserved key under which earlier nodes' outputs are stored inside ``context_json``.

``{"$from": "<node_id>"}`` reads those outputs. They live in memory on the
:class:`~huf.ai.graph.executor.GraphContext`, so without persisting them a run
resumed after a pause (human approval) would lose every earlier node's output.
The key is split back out by :func:`load_context` and is never visible as run input.
"""


def dump_context(ctx: GraphContext) -> str:
	"""Serialise the run context together with the node outputs recorded so far."""
	payload = dict(ctx.data)
	payload.pop(NODE_OUTPUTS_KEY, None)  # only recorded outputs are ever stored under it
	if ctx.node_outputs:
		payload[NODE_OUTPUTS_KEY] = ctx.node_outputs
	return json.dumps(payload, default=str)


GATEWAY_EVENT_KEY = "gateway_event"
"""Payload key naming the Gateway Event a run answers; it selects the run's trusted send binding."""


ENGINE_KEYS = frozenset(
	{
		NODE_OUTPUTS_KEY,
		GATEWAY_EVENT_KEY,  # set by gateway ingestion through ``create_flow_run``
		"_schedule_trigger",
		"_doc_event_trigger",
	}
)
"""Context keys only the engine writes (with ``_huf_*`` and ``_WRITES_KEY``)."""


def _step_ids(graph: dict | None) -> frozenset:
	"""Ids of the steps whose output is read by name: every node of ``graph`` that is not a trigger."""
	return frozenset(
		node.get("id")
		for node in (graph or {}).get("nodes") or []
		if not str(node.get("type") or "").startswith("trigger.")
	)


def strip_reserved_keys(values: dict, graph: dict | None = None, trigger_type: str | None = None) -> dict:
	"""``values`` from a caller without anything the engine owns, so they are never read as the run's own state
	(a forged approval decision, a skipped error handler, a borrowed gateway send binding).

	Dropped: :data:`ENGINE_KEYS`, ``_huf_*`` run state, the document write counter, ``_trigger`` unless a Doc Event
	run is being created, and objects shaped like an engine record: the error handler's ``error``, a decision under a
	step's name, ``member`` with ``vars``, a ``foreach`` frame.

	Everything else is the caller's data and is kept, even under a step's name or ``member``: ``input.<key>`` reads it,
	and :meth:`GraphContext.resolve_reference` never answers a step, member or loop reference from it.
	"""
	steps = _step_ids(graph)

	def owned(key, value) -> bool:
		if key in ENGINE_KEYS or key == _WRITES_KEY or str(key).startswith("_huf_"):
			return True
		if key == "_trigger":
			return trigger_type != "Doc Event"
		if not isinstance(value, dict):
			return False
		if key == "error":
			return "node_id" in value and "message" in value
		if key == "member":
			return "vars" in value
		if key == "foreach":
			return "item" in value or "index" in value
		return key in steps and "decision" in value

	return {key: value for key, value in values.items() if not owned(key, value)}


def load_context(raw, **kwargs) -> GraphContext:
	"""Inverse of :func:`dump_context`: parse once, restore node outputs."""
	context = GraphContext.from_json(raw, **kwargs)
	outputs = context.data.pop(NODE_OUTPUTS_KEY, None)
	if isinstance(outputs, dict):
		context.node_outputs = outputs
	return context


def _run_context(settings) -> FlowRunContext | None:
	"""The run context, when the caller threaded one through."""
	return settings if isinstance(settings, FlowRunContext) else None


def _context_of(flow_run, settings) -> GraphContext:
	"""The run's :class:`GraphContext`, parsed once where one exists.

	Callers that predate the run context (and the frappe-free tests) get a
	context built from the document on the spot, so every executor has
	exactly one way to read run state either way.
	"""
	run_ctx = _run_context(settings)
	if run_ctx is not None:
		return run_ctx.context
	context = load_context(getattr(flow_run, "context_json", None))
	# e.g. outbox delivery: references resolve by the same rules as during the run
	version = PinnedVersion.from_json(getattr(flow_run, "pinned_definition", None))
	if version:
		context.step_ids = _step_ids(version.graph)
	return context


def _persist_context(flow_run, ctx: GraphContext, settings=None) -> None:
	"""Persist the context blob and commit if we are in a background job."""
	run_ctx = _run_context(settings)
	if run_ctx is not None:
		run_ctx.save_context()
	else:
		flow_run.db_set("context_json", dump_context(ctx))
	commit_if_background()


# ---------------------------------------------------------------------------
# Version identity (F-1)
# ---------------------------------------------------------------------------


def load_definition(flow_id: str) -> dict:
	"""
	Load and return a parsed FlowDefinition.

	This returns whatever the definition record currently holds. Execution
	never calls it mid-run: a run resolves its graph once, through
	:func:`_pinned_version`, and keeps it (F-1).

	Args:
	    flow_id: The flow_id (= FlowDefinition name)

	Returns:
	    dict: Parsed definition JSON
	"""
	doc = frappe.get_doc("Flow Definition", flow_id)
	if doc.status != "Active":
		frappe.throw(_("This flow is not published yet. Publish it before running it."))

	defn = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	return defn


class FlowDefinitionGone(Exception):
	"""A run woke up after its Flow Definition was deleted and carries no pinned snapshot."""


def _pinned_version(flow_run) -> PinnedVersion:
	"""The exact graph this run executes, for the whole life of the run.

	If the run already carries a pinned snapshot, that snapshot is returned
	verbatim -- an edit to the ``Flow Definition`` since the run started
	cannot change what this run executes. If it does not (a run created
	before pinning existed, or a site whose ``Flow Run`` schema predates the
	snapshot field), the current definition is pinned now and recorded, so
	the very next step is already immune.
	"""
	pinned = PinnedVersion.from_json(getattr(flow_run, "pinned_definition", None))
	if pinned is not None:
		return pinned

	flow_id = getattr(flow_run, "flow_id", None)
	if not frappe.db.exists("Flow Definition", flow_id):
		raise FlowDefinitionGone(_("This flow was deleted, so the run cannot continue."))
	version = PinnedVersion.pin(load_definition(flow_id))
	_store_pin(flow_run, version)
	return version


def _store_pin(flow_run, version: PinnedVersion) -> None:
	"""Record a pin on the run, where the schema can hold one.

	Guarded rather than assumed: a site whose ``Flow Run`` has not been
	migrated yet simply keeps resolving the pin per run instead of erroring.
	"""
	try:
		if not frappe.db.has_column("Agent Flow Run", "pinned_definition"):
			return
		flow_run.db_set({"pinned_fingerprint": version.fingerprint, "pinned_definition": pinned_json(version)})
	except Exception:
		# Pin persistence is an optimisation over re-resolving; never let it
		# take down a run.
		pass


# ---------------------------------------------------------------------------
# Run lock (F-4)
# ---------------------------------------------------------------------------


#: A Flow Run left in Queued/Running for longer than this (no change, no live run lock) lost its
#: worker; the every-5-minutes sweeper (:func:`sweep_stale_runs`) fails it.
STALE_RUN_SWEEP_MINUTES = 30
STALE_RUN_SWEEP_REASON = "The run stopped before it finished, probably because the server restarted. Run it again."


def sweep_stale_runs(now=None, minutes: int | None = None) -> list[str]:
	"""Scheduler entry (every 5 minutes): fail Flow Runs stuck in Queued/Running.

	A run qualifies when it has not been modified for ``minutes`` (default
	:data:`STALE_RUN_SWEEP_MINUTES`) and no worker holds its run lock. Waiting runs (approval,
	user input) are never touched. A manual "Mark as failed" exists in ``api.py``.
	"""
	from datetime import timedelta

	cutoff = (now or now_datetime()) - timedelta(minutes=minutes or STALE_RUN_SWEEP_MINUTES)
	names = frappe.get_all(
		"Agent Flow Run",
		filters={"status": ["in", ["Queued", "Running"]], "modified": ["<", cutoff]},
		pluck="name",
		limit_page_length=200,
	)
	failed: list[str] = []
	for name in names:
		try:
			if frappe.cache().get(_run_lock_key(name)):
				continue  # a worker is still advancing it
			flow_run = frappe.get_doc("Agent Flow Run", name)
			if flow_run.status not in ("Queued", "Running"):
				continue
			_fail_flow_run(flow_run, STALE_RUN_SWEEP_REASON)
			failed.append(name)
		except Exception:
			log_flow_error(frappe.get_traceback(), f"Flow stale run sweep: {name}")
	return failed


#: A run in one of these statuses is finished: nothing may move it again.
TERMINAL_STATUSES = ("Success", "Failed", "Cancelled")


def _transition_run(
	flow_run,
	values: dict,
	*,
	from_statuses: tuple | list | None = None,
	not_from_statuses: tuple | list | None = None,
	bump_hop: bool = False,
) -> bool:
	"""Atomically move a Flow Run, only if it is still in the expected status.

	One ``UPDATE ... WHERE name = %s AND status IN (...)`` (or ``NOT IN``): the database, not a
	earlier read, decides. Two callers racing for the same transition (two approvers, an approver
	and the timeout sweep, a live worker and "Mark as failed") cannot both win, whatever snapshot
	of the row each of them read before. Returns True when this call made the change; on success
	the in-memory document is updated to match.
	"""
	table = frappe.qb.DocType("Agent Flow Run")
	query = frappe.qb.update(table)
	for field, value in values.items():
		query = query.set(table[field], value)
	if bump_hop:
		query = query.set(table.hop_count, table.hop_count + 1)
	query = query.set(table.modified, now_datetime()).where(table.name == flow_run.name)
	if from_statuses:
		query = query.where(table.status.isin(list(from_statuses)))
	if not_from_statuses:
		query = query.where(table.status.notin(list(not_from_statuses)))
	try:
		query.run()
	except frappe.QueryDeadlockError:
		# MariaDB with snapshot isolation refuses an UPDATE on a row another transaction changed since
		# this one first read it ("Record has changed since last read", error 1020). That is the same
		# answer as "0 rows matched": somebody else already moved this run.
		return False
	changed = (getattr(getattr(frappe.db, "_cursor", None), "rowcount", 0) or 0) > 0
	if changed:
		for field, value in values.items():
			flow_run.set(field, value) if hasattr(flow_run, "set") else setattr(flow_run, field, value)
		if bump_hop:
			flow_run.hop_count = (flow_run.hop_count or 0) + 1
	return changed


def run_cancelled(flow_run_name: str, *, lock: bool = False) -> bool:
	"""Whether the run was cancelled while this worker holds it.

	With ``lock`` the run row stays locked until the transaction ends, so a send queued in it is committed before
	a cancel can happen, and that cancel withdraws it.
	"""
	commit_if_background()  # a fresh snapshot
	return frappe.db.get_value("Agent Flow Run", flow_run_name, "status", for_update=lock) == "Cancelled"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


#: Flow Run ``trigger_type`` -> the trigger node type that starts such a run.
TRIGGER_NODE_TYPES = {
	"Webhook": "trigger.webhook",
	"Schedule": "trigger.schedule",
	"Doc Event": "trigger.doc-event",
	"Gateway": ("trigger.gateway", "trigger.whatsapp", "trigger.telegram"),
	"App": "trigger.app",
}


def select_entry_node(defn: dict, trigger_type: str = "Manual", event: dict | None = None) -> str:
	"""The node id a new run starts at (``entry`` is one id or one per trigger).
	Webhook / Schedule / Doc Event runs start at their trigger node; a Gateway run at the first gateway trigger matching
	``event`` (the run payload), else the first entry; Manual at the first entry. Fails closed when no trigger fits.
	"""
	entry = defn.get("entry")
	entries = [entry] if isinstance(entry, str) else [e for e in (entry or []) if isinstance(e, str)]
	if not entries:
		raise ValueError("This flow has no starting step. Add a trigger and try again.")
	wanted = TRIGGER_NODE_TYPES.get(trigger_type)
	if wanted is None:
		return entries[0]
	types = {n.get("id"): n.get("type") for n in defn.get("nodes", []) if isinstance(n, dict)}
	if trigger_type == "Gateway":
		from huf.ai.flow.gateways.dispatch import pick_gateway_entry
		return pick_gateway_entry(defn, entries, types, event)
	for node_id in entries:
		if types.get(node_id) == wanted:
			return node_id
	if all(not str(types.get(e) or "").startswith("trigger.") for e in entries):
		return entries[0]
	raise ValueError(f"This flow does not start from a {trigger_type} trigger, so it cannot be run that way.")


def create_flow_run(
	flow_id: str,
	payload: dict | None = None,
	trigger_type: str = "Manual",
	ignore_permissions: bool = False,
	mode: str = "real",
	member_key: str | None = None,
	gateway_event: str | None = None,
	entry_marker: str | None = None,
) -> "frappe.Document":
	"""
	Create a new FlowRun document from a FlowDefinition. This is the public
	"start a run" entry point; call :func:`run_flow` with the returned
	document's ``name`` to execute it (typically enqueued).

	The run starts at the trigger node matching ``trigger_type``
	(see :func:`select_entry_node`).

	The run pins the definition's content fingerprint at creation, and stores
	the graph itself alongside it, so the run is immune to later edits (F-1).

	Args:
	    flow_id: The flow_id to run
	    payload: Initial trigger payload / input
	    trigger_type: Manual / Webhook / Schedule / Doc Event / Gateway
	    ignore_permissions: for trusted callers that already authorised the route (Gateway)
	    mode: ``"real"`` or ``"test"``. A test run skips every step that would send or change something
	        outside the flow (see :mod:`huf.ai.flow.testrun`); every later continuation reads it from the run.
	    member_key: the member a real run is about, when the caller knows it (``runs.start``); otherwise it is
	        told from the trigger.
	    gateway_event: the inbound Gateway Event this run answers. Only gateway ingestion passes it; the same
	        key in ``payload`` is dropped.
	    entry_marker: ``runs.start``'s once-per-entry marker; the same key in ``payload`` is dropped.

	Returns:
	    Flow Run document
	"""
	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json

	if isinstance(payload, dict):
		payload = strip_reserved_keys(payload, defn, trigger_type)
	if gateway_event:
		payload = {**(payload or {}), GATEWAY_EVENT_KEY: gateway_event}
	if entry_marker:
		from huf.ai.flow.runs.start import ENTRY_MARKER

		payload = {**(payload or {}), ENTRY_MARKER: entry_marker}

	from huf.ai.graph.validation.flow_validation import check_runnable
	from huf.huf.doctype.flow_definition.activation_rules import entry_is_unset

	if entry_is_unset(defn):
		frappe.throw(_("This flow has no trigger yet. Choose what starts it, then run it again."))

	check_runnable(defn)  # a draft may be saved half-built; a run needs every step finished (UX-17)
	try:
		entry_node = select_entry_node(defn, trigger_type, payload)
	except ValueError as exc:
		frappe.throw(_("This flow cannot be started. {0}").format(plain_error(str(exc))))

	from huf.ai.flow import code_node
	from huf.ai.flow.gateways.dispatch import require_live_for_gateway

	if trigger_type == "Gateway" and (payload or {}).get("gateway_event"):
		require_live_for_gateway(defn_doc.status)  # TOCTOU: a message may only start a flow that is still Active
	if code_node.code_nodes(defn) and defn_doc.status != "Active":  # code runs only from a published flow
		frappe.throw(_("Publish this flow before running it: it has an Execute code step."))

	version = PinnedVersion.pin(defn)

	resolved_mode = "normal"
	max_hops = DEFAULT_MAX_HOPS

	# Every run owns a shared conversation for its agent steps
	conversation = _create_flow_conversation(flow_id, entry_node, ignore_permissions)

	fields = {
		"doctype": "Agent Flow Run",
		"flow_definition": flow_id,
		"flow_id": flow_id,
		"flow_version": defn_doc.version,
		"mode": resolved_mode.capitalize(),
		"status": "Queued",
		"current_node_id": entry_node,
		"hop_count": 0,
		"max_hops": max_hops,
		"context_json": json.dumps(payload or {}),
		"trigger_type": trigger_type,
		"run_mode": stored_mode(mode),
		"trigger_payload": json.dumps(payload or {}),
		"conversation": conversation.name if conversation else None,
		"started_at": now_datetime(),
	}
	if _has_pin_columns():
		fields["pinned_fingerprint"] = version.fingerprint
		fields["pinned_definition"] = pinned_json(version)

	member_key = member_key or flow_member.key_for_new_run(trigger_type, payload, mode)
	if member_key:
		fields["member_key"] = member_key

	flow_run = frappe.get_doc(fields)
	# Authenticated callers are already verified by the public API.
	# Webhook triggers run as Guest after HMAC validation, so the internal
	# Flow Run record must be created on behalf of the system.
	if ignore_permissions or frappe.session.user == "Guest":
		flow_run.insert(ignore_permissions=True)
	else:
		if not frappe.has_permission("Agent Flow Run", "create", doc=flow_run):
			frappe.throw(_("You do not have permission to run flows. Ask an admin for access."), frappe.PermissionError)
		# checked above; the controller only accepts inserts made by server code (runs.write_guard)
		flow_run.insert(ignore_permissions=True)
		flow_run.flags.ignore_permissions = False  # later saves of the returned document are checked again
	if member_key:
		flow_member.upsert_member(flow_id, member_key, flow_run.name)
	commit_if_background()

	return flow_run


def _has_pin_columns() -> bool:
	try:
		return bool(frappe.db.has_column("Agent Flow Run", "pinned_definition"))
	except Exception:
		return False


def run_flow(flow_run_name: str):
	"""
	Execute a flow run from its current position until completion or pause.

	Loads the run's *pinned* graph, takes the run lock, and hands the walk to
	the shared :class:`~huf.ai.graph.executor.GraphExecutor`.

	Args:
	    flow_run_name: Name of the Flow Run document
	"""
	if not _acquire_run_lock(flow_run_name):
		# Another worker is already advancing this run; a second cursor
		# writer is exactly the race F-4 describes.
		return

	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
		if flow_run.status in TERMINAL_STATUSES:
			return  # finished or cancelled while this job was queued: never revive it
		if flow_run.status in WAITING_STATUSES:
			# A queued job for a run that has since paused again: only approve / resume / expiry move a
			# waiting run (they set it Running first). Re-entering here would run the paused step twice.
			return
		try:
			version = _pinned_version(flow_run)
		except FlowDefinitionGone as e:
			_fail_flow_run(flow_run, str(e))
			return
		defn = version.graph

		nodes_map = {n["id"]: n for n in defn.get("nodes", [])}
		edges_list = effective_edges(defn)
		run_ctx = _build_run_context(flow_run, version)

		if flow_run.status in TERMINAL_STATUSES:
			return  # finished (or failed by an operator) while this job was queued: never revive it
		if not _transition_run(flow_run, {"status": "Running", "last_error": ""}, not_from_statuses=TERMINAL_STATUSES):
			return
		commit_if_background()

		try:
			from huf.ai.channels.outbound import guard

			with guard.batch():  # one run's sends share template reads and consent allows (H-W2-19)
				_execute_loop(flow_run, nodes_map, edges_list, run_ctx)
		except Exception as e:
			_fail_flow_run(flow_run, describe_exception(e))
			log_flow_error(f"Flow engine error: {frappe.get_traceback()}", "Flow Engine")
	finally:
		_release_run_lock(flow_run_name)


def _build_run_context(flow_run, version: PinnedVersion) -> FlowRunContext:
	"""Build the run-scoped context once, for the whole run (F-9)."""
	context = load_context(
		getattr(flow_run, "context_json", None),
		run_id=getattr(flow_run, "name", None),
		mode=(getattr(flow_run, "mode", "") or "normal"),
		metadata={
			"flow_id": getattr(flow_run, "flow_id", None),
			"conversation": getattr(flow_run, "conversation", None),
			"fingerprint": version.fingerprint,
		},
	)
	context.member = flow_member.run_member_context(flow_run)
	return FlowRunContext(
		{},
		flow_run=flow_run,
		version=version,
		context=context,
	)


def resume_flow_run(flow_run_name: str, user_input: dict | None = None):
	"""
	Resume a paused flow run (Waiting User).

	A pause records where to continue (structural knot 2), so resuming
	*advances past* the node that paused rather than re-executing it. That is
	both the correct semantics -- re-running a node that already produced its
	side effects is a bug -- and what keeps a resumed run independent of any
	edit made to the definition while it was waiting (F-1).

	Runs under the run lock and leaves the waiting state with one conditional UPDATE, so two
	concurrent resumes cannot both advance the run.

	Args:
	    flow_run_name: Name of the Flow Run
	    user_input: Optional input to merge into context
	"""
	if not _acquire_run_lock(flow_run_name):
		frappe.throw(_("This run is being updated right now. Refresh to see where it stands."))

	complete = False
	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)

		if flow_run.status not in WAITING_STATUSES:
			frappe.throw(_("This run is not waiting for anything right now."))
		if flow_run.status == "Waiting Approval":
			# An approval is only ever resolved by approve_flow_run, which checks the approver.
			frappe.throw(_("This run is waiting for approval. An approver has to approve or reject it."), frappe.PermissionError)

		waiting = _load_waiting(flow_run)
		if approval_expired(waiting, now_datetime()):
			frappe.throw(_("This request has expired and can no longer be answered."))

		version = _pinned_version(flow_run)
		run_ctx = _build_run_context(flow_run, version)
		paused_node = flow_run.current_node_id
		next_node_id = waiting.get("resume_node") or _evaluate_edges(
			flow_run, paused_node, {"status": "success"}, run_ctx.edges
		)

		values = {"waiting": None, "status": "Running"}
		if next_node_id:
			values["current_node_id"] = next_node_id
		if not _transition_run(flow_run, values, from_statuses=("Waiting User",), bump_hop=bool(next_node_id)):
			frappe.throw(_("This run was already resumed by someone else."))

		if user_input:
			run_ctx.context.update(strip_reserved_keys(dict(user_input), version.graph))
			run_ctx.save_context()
		complete = not next_node_id
		if complete:
			# The node that paused was the last step on its chain.
			_complete_flow_run(flow_run)
		# The claim must be durable before the lock goes, or a second caller could take it again.
		frappe.db.commit()  # nosemgrep
	finally:
		_release_run_lock(flow_run_name)

	if not complete:
		run_flow(flow_run_name)


def _load_waiting(flow_run) -> dict:
	raw = getattr(flow_run, "waiting", None)
	if not raw:
		return {}
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except (json.JSONDecodeError, TypeError):
		return {}
	return data if isinstance(data, dict) else {}


APPROVAL_DECISIONS = ("approved", "rejected")
DECISION_NOT_SAVED = "Your decision could not be saved. Nothing changed; please try again."


@frappe.whitelist()
def approve_flow_run(flow_run_name: str, decision: str, comment: str | None = None):
	"""
	Approve or reject a flow run waiting on a ``human.approval`` node.

	The approver is checked first (fail closed, see :func:`check_approver`) for
	BOTH decisions. The decision record
	``{"decision", "comment", "decided_by", "decided_at"}`` becomes the approval
	node's output, so downstream nodes read it as ``{"$from": "<approval_node_id>"}``.
	Routing is the node's own ``approve_next`` / ``reject_next``.

	Concurrency: the decision runs under the run lock, re-reads the status under it, refuses an
	approval whose deadline has passed, and moves the run out of ``Waiting Approval`` with one
	conditional UPDATE. Exactly one of any number of simultaneous decisions (or a decision racing
	the timeout sweep) wins; the others are refused and nothing downstream runs twice.

	Args:
	    flow_run_name: Name of the Flow Run
	    decision: "approved" or "rejected"
	    comment: Optional comment
	"""
	from huf.ai.flow.app_scope.api_guards import guard_run
	guard_run(flow_run_name, "approve")
	if decision not in APPROVAL_DECISIONS:
		frappe.throw(_("Choose Approve or Reject."))

	if not _acquire_run_lock(flow_run_name):
		frappe.throw(_("Someone else is deciding this approval right now. Refresh to see the result."))

	next_node = None
	flow_run = None
	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)

		if flow_run.status != "Waiting Approval":
			frappe.throw(_("This run is not waiting for approval any more."))

		# Permission is verified before anything is mutated.
		waiting = _load_waiting(flow_run)
		verify_approval_permission(waiting)

		if approval_expired(waiting, now_datetime()):
			frappe.throw(_("This approval has expired"))

		# The owning app may refuse this decider; asked before anything is claimed or changed.
		refuse_if_vetoed(flow_run, frappe.session.user, decision)

		version = _pinned_version(flow_run)
		run_ctx = _build_run_context(flow_run, version)
		edges_list = run_ctx.edges
		current_node = flow_run.current_node_id

		router = _build_router(flow_run, run_ctx, edges_list, ExecutionState(cursor=current_node))
		next_node = router.resolve_labelled(current_node, decision)

		values = {"waiting": None, "status": "Running"}
		if next_node:
			values["current_node_id"] = next_node
		# The claim: only the caller whose UPDATE still finds the run waiting goes on.
		if not _transition_run(flow_run, values, from_statuses=("Waiting Approval",), bump_hop=bool(next_node)):
			_refuse_lost_claim(flow_run_name)

		run_ctx.context.record_output(
			current_node,
			{
				"decision": decision,
				"comment": comment,
				"decided_by": frappe.session.user,
				"decided_at": _utc_now_iso(),
			},
		)
		run_ctx.save_context()
		if not next_node:
			_fail_flow_run(flow_run, no_route_message(version.graph, current_node, decision))
		# The claim must be durable before the lock goes, or a second caller could decide again.
		frappe.db.commit()  # nosemgrep
		_ensure_claim_durable(flow_run_name)
	finally:
		_release_run_lock(flow_run_name)

	# Tidying the approvers' notifications is best effort and comes AFTER the decision is durable: it
	# updates rows a background job may be inserting, and a conflicting write there rolls back the whole
	# open transaction (MariaDB error 1020 / deadlock). Inside the decision's transaction that rollback
	# used to take the decision with it while the request still answered "approved".
	_clear_flow_notifications(flow_run)
	frappe.db.commit()  # nosemgrep  the downstream steps start on a fresh snapshot, not on the tidy-up's older one

	if next_node:
		run_flow(flow_run.name)


def _refuse_lost_claim(flow_run_name: str) -> None:
	"""Raise the refusal for a decision whose conditional UPDATE changed nothing: someone else already
	decided (or expired) the run, or the database refused the write itself (snapshot conflict) and the
	run is still waiting. Either way the caller gets an error, never a success."""
	frappe.db.rollback()  # nothing of this call is written yet; end the snapshot so the re-read is current
	if frappe.db.get_value("Agent Flow Run", flow_run_name, "status") == "Waiting Approval":
		frappe.throw(_(DECISION_NOT_SAVED))
	frappe.throw(_("This approval was already decided"))


def _ensure_claim_durable(flow_run_name: str) -> None:
	"""After the claim's commit the run must have left ``Waiting Approval``. The database can roll a
	transaction back behind the code's back (deadlock victim, snapshot conflict); the commit then commits
	nothing, so refuse instead of confirming a decision that was not recorded."""
	if frappe.db.get_value("Agent Flow Run", flow_run_name, "status") == "Waiting Approval":
		frappe.throw(_(DECISION_NOT_SAVED))


def run_moved_on(after, before) -> bool:
	"""False when a decision left the run exactly where it was (still waiting at the same step)."""
	return not (
		after.status == "Waiting Approval"
		and after.current_node_id == before.current_node_id
		and (after.hop_count or 0) <= (before.hop_count or 0)
	)


def _utc_now_iso() -> str:
	"""Now as a time-zone-aware UTC string (``2026-10-28T02:49:20Z``), the form the UI converts to the browser zone."""
	from datetime import datetime, timezone

	return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expire_approval(flow_run_name: str, now=None, enqueue: bool = False) -> bool:
	"""Apply ``timeout_next`` to an approval that has passed its ``timeout_ms`` deadline.

	Called by the every-minute sweeper and lazily whenever an approval-waiting run is read, so a
	timeout does not depend on the scheduler tick alone. Returns True when the run was advanced or
	failed, False when it is not (yet) expired or another caller already took it. With no
	``timeout_next`` the run fails ("approval timed out"). ``enqueue=True`` hands the continuation to
	a background worker (for read requests); otherwise it runs inline.
	"""
	if not _acquire_run_lock(flow_run_name):
		return False  # another caller is advancing this run right now
	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
		if flow_run.status != "Waiting Approval":
			return False
		waiting = _load_waiting(flow_run)
		if not approval_expired(waiting, now or now_datetime()):
			return False

		timeout_next = waiting.get("timeout_next")
		node_id = flow_run.current_node_id
		values = {"waiting": None, "status": "Running"}
		if timeout_next:
			values["current_node_id"] = timeout_next
		# Same conditional claim as a decision: if an approver got there first this loses quietly.
		if not _transition_run(flow_run, values, from_statuses=("Waiting Approval",), bump_hop=bool(timeout_next)):
			return False

		if not timeout_next:
			_fail_flow_run(flow_run, approval_timeout_message(_pinned_version(flow_run).graph, node_id))
			frappe.db.commit()  # nosemgrep
			_clear_flow_notifications(flow_run)  # best effort, after the outcome is durable (see approve_flow_run)
			return True

		version = _pinned_version(flow_run)
		run_ctx = _build_run_context(flow_run, version)
		run_ctx.context.record_output(
			node_id, {"decision": "timeout", "comment": None, "decided_by": None, "decided_at": _utc_now_iso()}
		)
		run_ctx.save_context()
		frappe.db.commit()  # nosemgrep
		_clear_flow_notifications(flow_run)  # best effort, after the outcome is durable (see approve_flow_run)
	finally:
		_release_run_lock(flow_run_name)

	if enqueue:
		# The transition must be visible to the worker before it starts: a read request commits only
		# when it ends, so commit now, otherwise the job would see the run still waiting and run the
		# approval step again.
		frappe.db.commit()  # nosemgrep
		# "short" is drained before "default": the timeout path is what the user is watching for.
		frappe.enqueue("huf.ai.flow.engine.run_flow", queue="short", flow_run_name=flow_run_name)
	else:
		run_flow(flow_run_name)
	return True


# ---------------------------------------------------------------------------
# Core execution -- the adapter onto GraphExecutor
# ---------------------------------------------------------------------------


def _build_program(nodes_map: dict, edges_list: list, settings) -> GraphProgram:
	"""Normalize a Flow graph into the executor's vocabulary.

	This is the whole of the Flow profile's shape knowledge: which node types
	route themselves, which are terminal, and which carry a bounded loop body.
	"""
	run_ctx = _run_context(settings)
	if run_ctx is not None and run_ctx.version is not None:
		version = run_ctx.version
	else:
		version = PinnedVersion.pin(
			{"nodes": list(nodes_map.values()), "edges": edges_list, "settings": dict(settings or {})}
		)

	specs = {}
	for node_id, node in nodes_map.items():
		config = node.get("config") or {}
		node_type = node.get("type")
		specs[node_id] = NodeSpec(
			id=node_id,
			type=node_type,
			config=config,
			routing=node_registry.routing_for(node_type, NODE_ROUTING),
			raw=node,
		)
	return GraphProgram(version, specs, _first_entry(version.graph), settings=dict(settings or {}))


def _first_entry(graph: dict) -> str | None:
	entry = graph.get("entry")
	if isinstance(entry, list):
		return entry[0] if entry else None
	return entry


def _build_router(
	flow_run,
	settings,
	edges_list: list,
	state: ExecutionState,
	unhandled_failures: list | None = None,
	failed_node_ids: list | None = None,
) -> Router:
	"""One routing path for every node type (structural knots 3 and 4).

	``unhandled_failures`` collects ``"<node id>: <error>"`` for every failed node whose
	chosen successor is not one of its ``on_failure`` edges (an ``on_error`` target is
	one), so the run can still end ``Failed`` after an ``always`` edge ran cleanup nodes.
	"""
	def default_resolver(node: NodeSpec, outcome: Outcome, context: GraphContext):
		if node.type == "human.approval" and outcome.status == "success" and outcome.extra.get("approval_outcome"):
			return labelled_resolver(node.id, outcome.extra["approval_outcome"])  # a policy skipped the wait
		chosen = _resolve_default(node, outcome, context)
		if outcome.status == "failed" and unhandled_failures is not None:
			# No edge chosen -> the executor falls back to the node's ``on_error``.
			handled = (chosen is None and bool(node.raw.get("on_error"))) or any(
				e.get("from") == node.id and e.get("to") == chosen and e.get("type") == "on_failure"
				for e in edges_list
			)
			if not handled:
				unhandled_failures.append(step_failed_sentence(step_title(node.raw), outcome.error))
				if failed_node_ids is not None:
					failed_node_ids.append(node.id)
		return chosen

	def _resolve_default(node: NodeSpec, outcome: Outcome, context: GraphContext):
		node_result = outcome.extra or {"status": outcome.status}
		return _evaluate_edges(flow_run, node.id, node_result, edges_list)

	def labelled_resolver(node_id: str, label: str):
		for edge in edges_list:
			if edge.get("from") != node_id:
				continue
			if (edge.get("meta") or {}).get("outcome") == label:
				return edge.get("to")
		return None

	program = _build_program({}, edges_list, settings)
	return Router(program, default_resolver=default_resolver, labelled_resolver=labelled_resolver)


def _flow_state(flow_run) -> ExecutionState:
	status = (getattr(flow_run, "status", "") or "").strip()
	return ExecutionState(
		cursor=getattr(flow_run, "current_node_id", None),
		hop_count=getattr(flow_run, "hop_count", 0) or 0,
		status="running" if status in ADVANCEABLE_STATUSES else status.lower(),
	)


class _FlowStateStore:
	"""Write-through persistence for the cursor and hop count.

	This is the opt-in half of the executor's persistence seam: Flow wants
	every step durable because a run can pause for days, while a Procedure
	(T-23) keeps the default in-memory store and never touches the database
	on its hot path.
	"""

	def __init__(self, flow_run, settings=None):
		self.flow_run = flow_run
		self.settings = settings

	def save_cursor(self, cursor: str) -> None:
		from huf.ai.flow.support import step_keys

		# the visit of the step being left counts now, in the same write as the cursor (G2)
		context = _context_of(self.flow_run, self.settings)
		if step_keys.advance(context.data, self.flow_run.current_node_id):
			self.flow_run.db_set({"current_node_id": cursor, "context_json": dump_context(context)})
		else:
			self.flow_run.db_set("current_node_id", cursor)

	def save_hops(self, hop_count: int) -> None:
		self.flow_run.db_set("hop_count", hop_count)


class _FlowEventListener:
	"""Publishes the realtime events the Flow UI subscribes to."""

	def __init__(self, flow_run):
		self.flow_run = flow_run

	def node_start(self, node: NodeSpec) -> None:
		_publish_flow_event(
			self.flow_run,
			"flow_node_start",
			{
				"node_id": node.id,
				"node_type": node.type,
				"node_label": node.raw.get("_label", node.id),
			},
		)

	def node_end(self, node: NodeSpec, outcome: Outcome) -> None:
		_publish_flow_event(
			self.flow_run,
			"flow_node_end",
			{"node_id": node.id, "node_type": node.type, "status": outcome.status},
		)


def failed_node_record(outcome: Outcome) -> dict:
	"""The stored result of a failed node: ``{"status": "failed", "error": "<readable reason>"}``.

	It replaces whatever partial output the node returned, so the Run details step card can show
	why the step failed (read from ``context_json.__node_outputs__[<node id>].error``). Other
	keys a node may have returned are kept next to these two.
	"""
	record = dict(outcome.output) if isinstance(outcome.output, dict) else {}
	if outcome.output is not None and not isinstance(outcome.output, dict):
		record["result"] = outcome.output
	record["status"] = "failed"
	record["error"] = mask_text(str(outcome.error or record.get("error") or "The step failed"))
	return record


def _with_step_key(flow_run, node: dict, settings) -> dict:
	"""``node`` carrying its step key (H-W2-13): completed visits folded with the retry attempt."""
	from huf.ai.flow.runs import park
	from huf.ai.flow.support import step_keys

	waiting = park.is_reentry(flow_run, node) or {}
	retry = int((waiting.get("extra") or {}).get("attempt") or 0) + 1 if waiting.get("reason") == "retry" else 1
	data = _context_of(flow_run, settings).data
	return step_keys.with_key(node, step_keys.key_for(flow_run.name, node.get("id") or "", data, retry))


def _decided_send(flow_run, node: dict, settings) -> dict | None:
	"""The recorded result of a send step already decided (blocked, queued, sent), or None (G2).

	A re-delivered job replays its own step key. Inside the error-handler chain, a send step reached again
	replays its previous visit as well: a handler, retry or republish path never sends twice.
	"""
	from huf.ai.flow.nodes import send
	from huf.ai.flow.nodes.error_handler import first_error
	from huf.ai.flow.support import step_keys

	data = _context_of(flow_run, settings).data
	node_id = node.get("id") or ""
	done = step_keys.replay(data, step_keys.key_of(node))
	visits = step_keys.visits(data, node_id)
	if done is None and visits and first_error(flow_run, settings, None):
		previous = step_keys.step_key(flow_run.name, node_id, (visits - 1) * step_keys.VISIT_STRIDE + 1)
		done = step_keys.replay(data, previous)
	if done is None or (done.get("output") or {}).get("status") not in send.FINAL_STATUSES:
		return None
	return done


def _make_node_handler(flow_run, settings):
	"""Bridge one Flow node executor into the executor's handler contract."""

	def handler(node: NodeSpec, context: GraphContext, state: ExecutionState):
		# stop here: no step of a cancelled run starts ("Cancelled" in memory: an earlier step reloaded the run)
		status = getattr(flow_run, "status", None)
		if status == "Cancelled" or (status == "Running" and run_cancelled(flow_run.name)):
			flow_run.status = "Cancelled"
			return Outcome.paused(PauseRequest(kind="user", status_label="Cancelled"))
		raw = _with_step_key(flow_run, node.raw, settings)
		if node.type == "send.message":
			decided = _decided_send(flow_run, raw, settings)
			if decided is not None:
				return _with_reason_code(Outcome.from_mapping(decided))

		def run_once():
			try:
				return _execute_node(flow_run, raw, settings)
			except Exception as exc:
				log_flow_error(frappe.get_traceback(), f"Flow node {node.id} raised")
				return {"status": "failed", "error": describe_exception(exc)}

		result = run_with_retry(flow_run, node.raw, settings, run_once)
		if isinstance(result, Outcome):  # parked for a retry
			return result
		outcome = Outcome.from_mapping(result)
		if outcome.status == "failed":
			outcome.output = failed_node_record(outcome)
		if not outcome.is_paused and node.type in EXTERNALLY_PAUSABLE_TYPES:
			# Another subsystem may have parked this run while the node ran.
			# Convert that into a typed pause here, in the adapter, so the
			# executor core never reads a status string (structural knot 2).
			try:
				flow_run.reload()
			except Exception:
				pass
			if getattr(flow_run, "status", None) in WAITING_STATUSES:
				return Outcome.paused(PauseRequest(kind="user", status_label=flow_run.status))
		return _with_reason_code(outcome)

	return handler


def _with_reason_code(outcome: Outcome) -> Outcome:
	"""Stamp the step record with its registered reason code (H-W2-11): blocked, deferred, skipped steps (G2)."""
	from huf.ai.flow.support import reason_codes

	outcome.output = reason_codes.stamp(outcome.output)
	if outcome.output is None and outcome.extra.get("skipped") is True:
		# a turned-off step keeps its None output (later steps read it); its code goes on the outcome record
		outcome.extra = reason_codes.stamp(outcome.extra)
	return outcome


def _loop_node_types() -> tuple:
	"""Every step type the run loop can execute: engine built-ins, ``trigger.app`` and app-registered types."""
	return (*_NODE_TYPES, node_registry.APP_TRIGGER_TYPE, *node_registry.registered_types())


def _execute_loop(flow_run, nodes_map: dict, edges_list: list, settings: dict):
	"""Drive a Flow run to completion, a pause, or a failure.

	Everything about *how* the graph is walked -- hop budget, foreach budget,
	terminal detection, routing -- belongs to
	:class:`~huf.ai.graph.executor.GraphExecutor`. What is left here is
	Flow-specific: mapping the executor's result onto the ``Flow Run``
	document's status vocabulary.
	"""
	program = _build_program(nodes_map, edges_list, settings)
	state = _flow_state(flow_run)
	unhandled_failures: list = []
	failed_node_ids: list = []
	router = _build_router(flow_run, settings, edges_list, state, unhandled_failures, failed_node_ids)
	handler = _make_node_handler(flow_run, settings)
	handlers = {node_type: handler for node_type in _loop_node_types()}

	policy = ExecutionPolicy(
		max_hops=getattr(flow_run, "max_hops", None) or DEFAULT_MAX_HOPS,
	)

	executor = GraphExecutor(
		program,
		handlers,
		router=router,
		policy=policy,
		store=_FlowStateStore(flow_run, settings),
		listener=_FlowEventListener(flow_run),
	)

	result = executor.run(_context_of(flow_run, settings), state)

	if result.status == ExecutionResult.REFUSED:
		# The run is not advanceable (already finished, or being advanced by
		# another writer). Leave it exactly as it is (F-4).
		return result

	# Keep every step's output on the run (paused, failed or finished) so the Flow Run view can show them.
	_persist_context(flow_run, _context_of(flow_run, settings), settings)

	if result.status == ExecutionResult.PAUSED:
		if getattr(flow_run, "status", None) == "Cancelled":
			return result  # the cancel already published its own event
		_publish_flow_event(
			flow_run,
			"flow_paused",
			{"node_id": result.node_id, "status": getattr(flow_run, "status", None)},
		)
		return result

	if result.status == ExecutionResult.FAILED:
		_publish_flow_event(flow_run, "flow_error", {"error": result.error})
		message = describe_run_error(result.error, {i: step_title(n.raw) for i, n in program.nodes.items()})
		paused = run_error_handler(flow_run, program, router, handlers, policy, settings, result.node_id, message)
		if paused is not None:
			return paused
		_fail_flow_run(flow_run, first_error(flow_run, settings, message))
		return result

	if unhandled_failures:
		# A failure no on_failure/on_error route handled: cleanup nodes may have run
		# via an ``always`` edge, but the run is still Failed (first failure wins).
		_publish_flow_event(flow_run, "flow_error", {"error": unhandled_failures[0]})
		paused = run_error_handler(
			flow_run, program, router, handlers, policy, settings, failed_node_ids[0], unhandled_failures[0]
		)
		if paused is not None:
			return paused
		_fail_flow_run(flow_run, first_error(flow_run, settings, unhandled_failures[0]))
		return result

	handled = first_error(flow_run, settings, None)
	if handled:  # the error handler parked, then resumed to its end: the run still ends Failed
		_publish_flow_event(flow_run, "flow_error", {"error": handled})
		_fail_flow_run(flow_run, handled)
		return result

	_complete_flow_run(flow_run, reply_text=_flow_reply_text(flow_run, settings, result))
	_publish_flow_event(flow_run, "flow_completed", {"node_id": result.node_id, "status": "Success"})
	return result


# ---------------------------------------------------------------------------
# Node executors
# ---------------------------------------------------------------------------


def _execute_node(flow_run, node: dict, settings: dict) -> dict:
	"""
	Execute a single node and return the result.

	Dispatches to the appropriate executor based on node type. This table is
	now purely a dispatch table: it no longer also decides routing, which
	lives in :data:`NODE_ROUTING` and the executor's Router (knot 3).
	"""
	node_type = node.get("type")
	config = node.get("config", {})

	executor = _NODE_EXECUTORS.get(node_type) or node_registry.executor_for(node_type)
	if executor is None:
		if node_registry.is_app_type_id(node_type):
			return {"status": "failed", "error": _("This step type is no longer available ({0}). The app that provided it may have been uninstalled.").format(node_type)}
		frappe.throw(_("Unknown node type: {0}").format(node_type))

	if is_turned_off(node):
		return turned_off_result()

	if test_gate.is_test_run(flow_run):
		simulated = test_gate.simulate_node(node, _context_of(flow_run, settings).resolve)
		if simulated is not None:
			return simulated
	try:
		return executor(flow_run, node, config, settings)
	except TemplateError as exc:
		# Authoring error in a {"$template": ...} value: fail this node (so on_error applies).
		return {"status": "failed", "error": plain_error(str(exc))}


def _exec_trigger_webhook(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute a trigger.webhook (or chat trigger: gateway, whatsapp, telegram) node - a passthrough for UI clarity."""
	ctx = _context_of(flow_run, settings)
	return {"status": "success", "output": ctx.as_dict()}


def _exec_trigger_unset(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""trigger.unset is a placeholder with no trigger configured; it is not runnable."""
	return {"status": "failed", "error": "This flow has no trigger yet. Choose what starts it, then run it again."}


def _exec_trigger_schedule(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute trigger.schedule node (config: ``cron``) - passthrough for scheduled execution.

	The actual scheduling is handled externally via Frappe Scheduler. This
	executor records when the schedule fired.
	"""
	ctx = _context_of(flow_run, settings)

	schedule_info = {
		"trigger_type": "schedule",
		"triggered_at": str(now_datetime()),
		"cron": config.get("cron", ""),
	}

	ctx.set("_schedule_trigger", schedule_info)
	_persist_context(flow_run, ctx, settings)

	return {"status": "success", "trigger_type": "schedule", "schedule_info": schedule_info}


def _exec_trigger_doc_event(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute trigger.doc-event node (config: ``doctype``, ``event``) - pass through with doc context.

	The payload (the document's fields and ``_trigger``) is set at flow run creation by the trigger entry point
	(``huf.ai.flow.triggers.run_flow_from_trigger``); this executor enriches it with event
	metadata for downstream nodes.
	"""
	ctx = _context_of(flow_run, settings)

	trigger_info = ctx.get("_trigger") or {}
	doc_data = ctx.get("doc") or {}

	doc_event_info = {
		"trigger_type": "doc_event",
		"triggered_at": str(now_datetime()),
		"doctype": trigger_info.get("doctype", ctx.get("doctype")),
		"docname": trigger_info.get("docname", ctx.get("name")),
		"event": trigger_info.get("event", ctx.get("event")),
		"owner": trigger_info.get("owner"),
		"timestamp": trigger_info.get("timestamp"),
	}

	ctx.set("_doc_event_trigger", doc_event_info)
	if doc_data and not ctx.get("doc"):
		ctx.set("doc", doc_data)

	_persist_context(flow_run, ctx, settings)

	return {"status": "success", "trigger_type": "doc_event", "doc_event_info": doc_event_info}


def render_agent_prompt(config: dict, ctx: GraphContext) -> str:
	"""Render ``agent.run`` ``prompt``: ``{name}`` placeholders filled from ``prompt_bindings``.

	Each binding is a Value (literal, ``{"$from": ...}``, ``$template``) resolved through the
	executor's single resolver. ``{{`` / ``}}`` are literal braces; a placeholder with no binding
	is an authoring error (``TemplateError`` fails the node).
	"""
	bindings = ctx.resolve(config.get("prompt_bindings") or {})
	return render_template(config.get("prompt") or "", bindings if isinstance(bindings, dict) else {}, objects="json")


def _exec_agent_run(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute agent.run node (config: ``agent``, ``prompt``, ``prompt_bindings``).

	Output (``{"$from": "<node_id>"}``) is the agent's response text.
	"""
	agent_name = config.get("agent")
	if not agent_name:
		return {"status": "failed", "error": "Choose which agent this step should ask, then run again."}
	if not config.get("prompt"):
		return {"status": "failed", "error": "Write what this step should ask the agent, then run again."}

	run_ctx = _run_context(settings)
	ctx = _context_of(flow_run, settings)

	prompt = render_agent_prompt(config, ctx)
	conversation_id = _conversation_of(flow_run, run_ctx)

	try:
		from huf.ai.agent.integration import run_agent_sync

		result = run_agent_sync(
			agent_name=agent_name,
			prompt=prompt,
			conversation_id=conversation_id,
			channel_id="flow",
			flow_run_id=flow_run.name,
			flow_node_id=node.get("id"),
			run_kind="agent",
			now=True,
		)

		if result and result.get("agent_run_id"):
			flow_run.db_set("last_agent_run", result["agent_run_id"])

		commit_if_background()

		return {
			"status": "success" if result.get("success") else "failed",
			"response": result.get("response", ""),
			"output": result.get("response", ""),
			"agent_run_id": result.get("agent_run_id"),
			"error": result.get("error"),
		}
	except Exception as e:
		return {"status": "failed", "error": describe_exception(e)}


def _bound_gateway(flow_run, run_id: str = ""):
	"""Trusted gateway for the WhatsApp tool: the gateway that started this flow.

	Model/tool arguments never select it, and no node config does (the schema has no gateway
	field); empty means the tool fails closed (gateway_context_required). The event must name this run
	as its own (``Gateway Event.flow_run``, written by ingestion): the run row alone is not trusted.
	"""
	from huf.ai.tools.whatsapp import trusted_gateway

	gateway = ""
	contact = ""
	try:
		payload = flow_run.get("trigger_payload")
		payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
		event = payload.get("gateway_event") if isinstance(payload, dict) else None
		if event:
			row = frappe.db.get_value("Gateway Event", event, ["gateway", "sender_id", "flow_run"], as_dict=True) or {}
			if row.get("flow_run") != flow_run.name:
				row = {}
			gateway = row.get("gateway") or ""
			contact = row.get("sender_id") or ""
	except Exception:
		gateway, contact = "", ""
	return trusted_gateway(gateway, run_id=run_id, contact=contact)


def _exec_tool_call(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute tool.call node (config: ``tool_id``, ``input``, ``timeout_ms``, ``approved``).

	``input`` values resolve through the executor's single reference form (``$from`` /
	``$template``). A tool whose result reports failure (see :func:`normalize_tool_result`)
	fails the node. An MCP tool is found by its unique tool id
	(``find_unique_mcp_server_for_tool``); an id owned by several servers is never attributed to
	an arbitrary one.

	For a built-in tool, the ``Agent Tool Call`` telemetry record is emitted by the invocation
	service rather than assembled here -- exactly one record per call (I5, GT-05). An MCP tool
	bypasses that service (``execute_mcp_tool`` has no telemetry of its own), so this function owns
	its ``Agent Tool Call`` record for that path.

	``timeout_ms`` ("Wait up to") bounds how long the step waits for an MCP tool: past it the step
	fails with a readable message. It is NOT enforced for built-in tools. They run in the worker's
	own Frappe request context (``frappe.local``: DB connection, session, transaction) which is bound
	to the calling thread, so running one in a helper thread and abandoning it on timeout would leave
	a live, uncancellable call writing through a connection the run no longer owns. Built-in tools
	have their own limits (HTTP request timeouts, provider timeouts); the node's ``timeout_ms`` is
	ignored for them.
	"""
	tool_name = config.get("tool_id")
	if not tool_name:
		return {"status": "failed", "error": "Choose which action this step should do, then run again."}

	run_ctx = _run_context(settings)
	ctx = _context_of(flow_run, settings)
	args = with_step_limit(tool_name, ctx.resolve(dict(config.get("input") or {})), config)

	run_doc = _create_flow_agent_run(
		flow_run=flow_run,
		node=node,
		run_kind="tool",
		prompt=f"Tool: {tool_name}\nArgs: {json.dumps(args, default=str)}",
	)

	from huf.ai.mcp_client import find_unique_mcp_server_for_tool

	mcp_server = find_unique_mcp_server_for_tool(tool_name)

	invocation_ctx = RunContext(
		conversation_id=_conversation_of(flow_run, run_ctx),
		agent_run_id=getattr(run_doc, "name", None),
	)

	tool_call_doc = None
	if mcp_server:
		from uuid import uuid4

		tool_call_doc = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"agent_run": run_doc.name,
			"conversation": getattr(flow_run, "conversation", None),
			"tool": tool_name,
			"is_mcp_tool": 1,
			"mcp_server": mcp_server,
			"tool_args": json.dumps(args, default=str) if args else None,
			"status": "Started",
			"call_id": f"call_{uuid4().hex[:12]}",
		})
		tool_call_doc.insert(ignore_permissions=True)

	timeout_s = (config["timeout_ms"] / 1000.0) if config.get("timeout_ms") else None

	try:
		if mcp_server:
			import asyncio

			from huf.ai.mcp_client import execute_mcp_tool

			# A Requires Approval tool only runs when the node is explicitly marked
			# ``approved`` (the flow author places it behind a human.approval step).
			coro = execute_mcp_tool(
				server_name=mcp_server,
				tool_name=tool_name,
				arguments=args,
				approved=config.get("approved") is True,
			)
			if timeout_s:
				coro = asyncio.wait_for(coro, timeout=timeout_s)
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			try:
				raw = loop.run_until_complete(coro)
			except asyncio.TimeoutError:
				raw = {"success": False, "error": tool_timeout_message(config["timeout_ms"])}
			finally:
				loop.close()
			if not isinstance(raw, dict):
				raw = {"success": True, "result": raw}
			elif "success" not in raw and ("content" in raw or "isError" in raw):
				# A raw MCP tools/call payload has no ``success`` key.
				is_error = bool(raw.get("isError"))
				texts = [c.get("text", "") for c in (raw.get("content") or []) if isinstance(c, dict)]
				raw = {
					"success": not is_error,
					"result": raw,
					"error": " ".join(t for t in texts if t) or "The tool reported a problem without saying what." if is_error else "",
				}
		else:
			with tool_run_context(invocation_ctx), _bound_gateway(flow_run, getattr(run_doc, "name", "") or ""):
				raw = execute_tool(tool_name, args)

		result = normalize_tool_result(raw)
		is_success = result["success"]
		error_msg = friendly_tool_error(result["error"])

		if tool_call_doc is not None:
			tool_result = result["result"]
			if isinstance(tool_result, (dict, list)):
				formatted_result = tool_result
			else:
				formatted_result = {"output": str(tool_result)} if tool_result is not None else None
			tool_call_doc.update({
				"status": "Completed" if is_success else "Failed",
				"tool_result": formatted_result,
				"error_message": error_msg or None,
			})
			tool_call_doc.save(ignore_permissions=True)

		run_doc.db_set(
			{
				"status": "Success" if is_success else "Failed",
				"response": json.dumps(result, default=str),
				"error_message": error_msg,
				"end_time": now_datetime(),
			}
		)
		flow_run.db_set("last_agent_run", run_doc.name)

		commit_if_background()

		return {
			"status": "success" if is_success else "failed",
			"result": result["result"],
			"error": error_msg or None,
		}
	except Exception as e:
		error_text = friendly_tool_error(describe_exception(e))
		if tool_call_doc is not None:
			tool_call_doc.update({"status": "Failed", "error_message": error_text})
			tool_call_doc.save(ignore_permissions=True)
		run_doc.db_set({"status": "Failed", "error_message": error_text, "end_time": now_datetime()})
		commit_if_background()
		return {"status": "failed", "error": error_text}


_exec_router_decision = adapters.exec_router_decision
_exec_knowledge_search = adapters.exec_knowledge_search
_exec_handoff = adapters.exec_handoff
_exec_stop = adapters.exec_stop
_exec_member_set = adapters.exec_member_set
_exec_send_message = adapters.exec_send_message
_exec_split = adapters.exec_split
_exec_doc_get = adapters.exec_doc_get
_exec_doc_update = adapters.exec_doc_update
_exec_flow_call = adapters.exec_flow_call


def _exec_human_approval(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute human.approval node - pause for human decision.

	Config: ``message``, ``approve_next``, ``reject_next``, ``timeout_next``, ``timeout_ms``,
	``approver_type`` (``role`` / ``user``), ``approver_role``, ``approver_users``. Without a
	declared approver only a System Manager can decide (:func:`check_approver`). An app's
	``huf_flow_approval_policy`` hook may name the approver roles or say that no approval is needed;
	then the step records an automatic approval and takes ``approve_next``
	(:func:`evaluate_approval_policy`, fail closed). Returns a pause
	as a *value*; the executor never has to reload the document and compare status strings to
	notice (structural knot 2). The decision record is the node's output once decided.
	"""
	if flow_run.status == "Waiting Approval" and flow_run.current_node_id == node.get("id"):
		return {"status": "waiting_approval"}

	ctx = _context_of(flow_run, settings)

	policy = evaluate_approval_policy(
		flow_run.flow_id,
		node,
		{"flow_run": flow_run.name, "test_run": test_gate.is_test_run(flow_run), "data": ctx.reference_roots()},
	)
	# Without an approved route there is nowhere to go on automatically, so the step waits as usual.
	if not policy.required and config.get("approve_next"):
		return {
			"status": "success",
			"approval_outcome": "approved",
			"output": {
				"decision": "approved",
				"comment": None,
				"decided_by": None,
				"decided_at": _utc_now_iso(),
				"reason": policy.reason,
			},
		}

	timeout_ms = config.get("timeout_ms")
	timeout_at = None
	if timeout_ms:
		from datetime import timedelta

		timeout_at = (now_datetime() + timedelta(milliseconds=timeout_ms)).isoformat()

	waiting_data = {
		"type": "approval",
		"node_id": node.get("id"),
		**waiting_fields(flow_run, node, render_text_refs(config.get("message", ""), ctx), ctx.data, config, ctx, getattr(_run_context(settings), "definition", None)),
		**test_gate.approval_extras(flow_run),
		"approver_type": config.get("approver_type"),
		"approver_role": config.get("approver_role"),
		"approver_users": config.get("approver_users") or [],
		"timeout_next": config.get("timeout_next"),
		"timeout_ms": timeout_ms,
		"timeout_at": timeout_at,
		"policy_reason": policy.reason,
	}
	if policy.approver_roles:
		waiting_data.update(
			approver_type="role",
			approver_role=policy.approver_roles[0],
			approver_roles=list(policy.approver_roles),
			approver_users=[],
		)

	# Persist earlier nodes' outputs so downstream {"$from": ...} still resolves after the pause.
	_persist_context(flow_run, ctx, settings)
	if not _transition_run(
		flow_run, {"status": "Waiting Approval", "waiting": json.dumps(waiting_data)}, not_from_statuses=TERMINAL_STATUSES
	):
		return {"status": "waiting_approval"}  # the run finished meanwhile (operator action): do not revive it
	commit_if_background()
	if test_gate.is_test_run(flow_run):
		test_gate.notify_test_owner(flow_run, waiting_data)  # a test sends no email and no Slack card
		return {"status": "waiting_approval"}
	_send_approval_notifications(flow_run, node, config, waiting_data)
	flow_hooks.notify_approvers(flow_run)
	return {"status": "waiting_approval"}


def _exec_condition(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute condition node (config: ``expression``, ``on_true``, ``on_false``, ``fallback_next``).

	The expression is the shared graph-IR expression language
	(``huf.ai.graph.expressions``, e.g. ``input['amount'] > 100``) evaluated against the run's
	reference roots (``input``, ``trigger``, earlier node ids, ``foreach``). Both targets are
	required by the schema; the chosen one is the node's successor.
	"""
	expression = config.get("expression", "")
	true_node = config.get("on_true")
	false_node = config.get("on_false")

	if not expression:
		return {"status": "failed", "error": "Write the check this condition should make, then run again."}
	if not true_node or not false_node:
		return {"status": "failed", "error": "Choose the next step for both Yes and No, then run again."}

	ctx = _context_of(flow_run, settings)

	try:
		parsed = parse_expression(expression)
		if any(facts.names_used(parsed)):  # reads app facts: fetched for this evaluation only, fail closed
			return exec_facts_condition(flow_run, node, config, ctx, parsed)
		result = evaluate_bool(parsed, ctx.reference_roots(), raise_limits=True)
	except Exception as e:
		return {"status": "failed", "error": str(e) if isinstance(e, ExpressionLimitError) else "This condition could not be checked against the data it received. Check what you compare, and that earlier steps give it that data."}

	return {
		"status": "success",
		"result": result,
		"output": result,
		"branch": "true" if result else "false",
		"next_node_id": true_node if result else false_node,
	}


def _exec_transform(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute transform node - applies one of the shared graph-IR's
	:class:`~huf.ai.graph.transforms.TransformOp` operations to a resolved
	input mapping.

	Config keys (graph_ir.schema.json ``TransformNode``, ``additionalProperties: false``):
	    op (str): a ``TransformOp`` name (see ``huf.ai.graph.transforms``)
	    input (dict): values, each resolved via ``GraphContext.resolve`` against
	        the run's context, then passed to ``run_transform``

	``run_transform`` is the same function :mod:`huf.ai.graph.procedure_runtime` uses for the
	Procedure profile's ``transform`` node. The output (``{"$from": "<node_id>"}``) is the
	transform's value.
	"""
	ctx = _context_of(flow_run, settings)
	resolved_input = ctx.resolve(config.get("input") or {})
	result = run_transform(config.get("op"), resolved_input, TransformLimits())

	if not result.ok:
		err = result.error
		if not err:
			return {"status": "failed", "error": "This step could not change the data it received. Check its settings."}
		return {"status": "failed", "error": plain_transform_error(step_ref(node, True), err.code, err.message, err.op)}

	return {"status": "success", "result": result.value, "output": result.value}


def _flow_nodes_by_id(settings: dict) -> dict:
	"""Every node in the pinned graph, by id -- for looking up a ``foreach``
	``body`` member, which per spec/graph-ir.md
	section 2 lives in the same top-level ``nodes`` array as the main chain.
	"""
	run_ctx = _run_context(settings)
	graph = run_ctx.definition if run_ctx is not None else {}
	return {n["id"]: n for n in graph.get("nodes", []) if isinstance(n, dict) and "id" in n}


def _run_sub_chain(flow_run, settings: dict, node_ids: list) -> dict:
	"""Walk one self-contained chain of node ids (a ``foreach`` body) to completion, re-using :func:`_execute_node`'s own
	dispatch table so every node type -- including a nested ``condition`` --
	behaves exactly as it would on the main chain. Bounded by the chain's own
	length (+2 headroom, mirroring ``procedure_runtime._sub_executor``): this
	is a distinct budget from the run's ``max_hops``, never charged against it.

	Records each visited node's output into the shared ``GraphContext`` (the
	same ``node_id -> output`` bookkeeping ``GraphExecutor.run`` does for the
	main chain, executor.py:744) so a ``foreach.config.collect`` reference
	into a body node's output -- or any ``{"$from": "<node_id>...."}`` inside
	the chain itself -- resolves, instead of silently returning ``None``.
	"""
	ctx = _context_of(flow_run, settings)
	by_id = _flow_nodes_by_id(settings)
	cursor = node_ids[0] if node_ids else None
	max_hops = len(node_ids) + 2
	hops = 0
	last_result = {"status": "success"}

	while cursor is not None:
		hops += 1
		if hops > max_hops:
			return {"status": "failed", "error": "The steps inside this loop kept going without ending. Check how they are connected."}

		node = by_id.get(cursor)
		if node is None:
			return {"status": "failed", "error": "A step inside this loop points at a step that no longer exists. Reconnect it."}
		if node.get("type") == "human.approval":
			return {"status": "failed", "error": f'{step_ref(node, True)} waits for approval, which a loop cannot do. Move it outside the loop.'}
		if node.get("type") == "wait":
			return {"status": "failed", "error": f'{step_ref(node, True)} is a wait step. Wait steps cannot be used inside a loop. Move it outside the loop.'}
		if retry_policy_of(node):
			return {"status": "failed", "error": f'{step_ref(node, True)} is set to try again if it fails, which a loop cannot do. Remove the retry setting or move the step outside the loop.'}
		if node.get("type") == "code.run":
			return {"status": "failed", "error": f'{step_ref(node, True)} runs code, which a loop cannot do. Move it outside the loop.'}

		last_result = _execute_node(flow_run, node, settings)
		ctx.record_output(cursor, last_result.get("output", last_result.get("result")))
		if last_result.get("status") == "failed":
			on_error = node.get("on_error")
			if not on_error:
				return last_result
			cursor = on_error
			continue

		if node_registry.routing_for(node.get("type"), NODE_ROUTING) == RoutingMode.SELF_ROUTED:
			cursor = last_result.get("next_node_id")
		else:
			cursor = node.get("next")

	return last_result


def _exec_foreach(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute foreach node: run ``config.body`` once per element of ``config.items``
	(graph_ir.schema.json ``ForeachNode``).

	Config: ``items`` (reference to a list), ``body`` (node ids, chain order), ``max_iterations``,
	``on_item_error`` (``fail`` stops the loop and fails the node; ``skip`` drops that item and
	carries on), ``collect`` (reference evaluated after each successful item; the results form the
	node's output list), ``item_var`` / ``index_var`` (names the current item / index are also bound
	to in the run input while the body runs; ``foreach.item`` / ``foreach.index`` always work).
	The done edge is the node's own ``next``, taken by the router once this node succeeds.

	The body is a self-contained chain walked by :func:`_run_sub_chain`, never re-entering the main
	chain, and the iteration cap is its own budget, never the run's ``max_hops`` (spec/graph-ir.md
	section 2.1).
	"""
	node_id = node.get("id")
	ctx = _context_of(flow_run, settings)
	items = ctx.resolve(config.get("items"))
	if not isinstance(items, list):
		return {"status": "failed", "error": f'{step_ref(node, True)} needs a list to go through, but got something else. Choose a list from an earlier step.'}

	run_ctx = _run_context(settings)
	contract_limits = ((run_ctx.definition.get("contract") or {}).get("limits") or {}) if run_ctx is not None else {}
	caps = [c for c in (config.get("max_iterations"), contract_limits.get("max_foreach_iterations")) if c is not None]
	effective_cap = min(caps) if caps else len(items)
	if len(items) > effective_cap:
		return {
			"status": "failed",
			"error": f'{step_ref(node, True)} got {len(items)} items, but its limit is {effective_cap}. Raise the limit or send fewer items.',
		}

	body_ids = config.get("body") or []
	collect_ref = config.get("collect")
	on_item_error = config.get("on_item_error", "fail")
	item_var = config.get("item_var") or "item"
	index_var = config.get("index_var") or "index"

	_MISSING = object()
	saved = {k: ctx.data.get(k, _MISSING) for k in (item_var, index_var)}

	results = []
	skipped = []
	outer_vars = ctx.loop_vars
	ctx.loop_vars = outer_vars | {item_var, index_var}
	try:
		for index, item in enumerate(items):
			ctx.push_foreach(item, index)
			ctx.data[item_var] = item
			ctx.data[index_var] = index
			try:
				outcome = _run_sub_chain(flow_run, settings, body_ids)
				if outcome.get("status") != "success":
					if on_item_error == "skip":
						skipped.append({"index": index, "error": outcome.get("error")})
						continue
					return {
						"status": "failed",
						"error": f'{step_ref(node, True)} stopped at item {index + 1}: {outcome.get("error")}',
					}
				results.append(ctx.resolve(collect_ref) if collect_ref is not None else None)
			finally:
				ctx.pop_foreach()
	finally:
		ctx.loop_vars = outer_vars
		for key, value in saved.items():
			if value is _MISSING:
				ctx.data.pop(key, None)
			else:
				ctx.data[key] = value

	_persist_context(flow_run, ctx, settings)
	return {"status": "success", "result": results, "output": results, "skipped": skipped}


def _exec_validate(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute validate node - fails closed if any ``config.assertions`` entry
	evaluates falsy (graph_ir.schema.json ``ValidateNode``).

	``expression`` is a ``$defs/Expression`` -- "evaluated by the shared
	expression evaluator (graph-ir.md section 4)" per the schema's own
	description, i.e. ``huf.ai.graph.expressions.evaluate_bool``/
	``parse_expression`` against ``GraphContext.reference_roots()`` (the same
	evaluator ``procedure_runtime._handle_validate`` uses for the Procedure
	profile) -- the same evaluator ``condition`` uses.
	"""
	ctx = _context_of(flow_run, settings)
	bindings = ctx.reference_roots()
	failures = []
	for assertion in config.get("assertions", []):
		try:
			parsed = parse_expression(assertion["expression"])
			truthy = evaluate_bool(parsed, bindings, raise_limits=True)
		except Exception as e:
			return {
				"status": "failed",
				"error": f"{step_ref(node, True)}: {e}" if isinstance(e, ExpressionLimitError) else f'{step_ref(node, True)} could not check one of its rules against the data it received. Check the rule.',
			}
		if not truthy:
			failures.append({"code": assertion["code"], "message": assertion["message"]})

	if failures:
		return {"status": "failed", "error": " ".join(str(f.get("message") or "A check did not pass.") for f in failures)}
	return {"status": "success", "result": {"assertions_passed": len(config.get("assertions", []))}}


def _exec_output(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute output node - always terminal (see ``NODE_ROUTING``). Resolves
	``config.value`` and enforces the graph's output budget (I7, mirroring
	``procedure_runtime._Runner._handle_output``): a value that breaches
	``max_rows``/``max_output_bytes`` fails the node rather than being
	silently truncated.
	"""
	ctx = _context_of(flow_run, settings)
	value = ctx.resolve(config.get("value"))

	run_ctx = _run_context(settings)
	limits = ((run_ctx.definition.get("contract") or {}).get("limits") or {}) if run_ctx is not None else {}
	budget_kwargs = {}
	if limits.get("max_rows") is not None:
		budget_kwargs["max_rows"] = limits["max_rows"]
	if limits.get("max_output_bytes") is not None:
		budget_kwargs["max_bytes"] = limits["max_output_bytes"]
	budget = OutputBudget(**budget_kwargs) if budget_kwargs else OutputBudget()

	if isinstance(value, list):
		try:
			enforce_output_budget(value, budget=budget)
		except OutputBudgetExceeded as exc:
			return {"status": "failed", "error": plain_error(str(exc))}
	elif isinstance(value, dict):
		size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
		if size > budget.max_bytes:
			return {
				"status": "failed",
				"error": f'The result of {step_ref(node)} is too large ({size // 1024} KB, the limit is {budget.max_bytes // 1024} KB). Send less data.',
			}
		for key, field_value in value.items():
			if isinstance(field_value, list) and len(field_value) > budget.max_rows:
				return {
					"status": "failed",
					"error": f'The result of {step_ref(node)} has {len(field_value)} rows in "{key}", but the limit is {budget.max_rows}. Send fewer rows.',
				}

	record_outcome(flow_run, config.get("outcome"), ctx)
	return {"status": "success", "output": value, "result": value}



# ---------------------------------------------------------------------------
# doc.create -- insert an allow-listed document as the run's user
# ---------------------------------------------------------------------------

_WRITES_KEY = "_doc_create_count"


_exec_doc_create = adapters.exec_doc_create


_NODE_EXECUTORS = {
	"trigger.webhook": _exec_trigger_webhook,
	"trigger.schedule": _exec_trigger_schedule,
	"trigger.unset": _exec_trigger_unset,
	"trigger.doc-event": _exec_trigger_doc_event,
	**dict.fromkeys(("trigger.gateway", "trigger.whatsapp", "trigger.telegram"), _exec_trigger_webhook),
	"agent.run": _exec_agent_run,
	"tool.call": _exec_tool_call,
	"router.llm": _exec_router_llm,
	"router.decision": _exec_router_decision,
	"split": _exec_split,
	"human.approval": _exec_human_approval,
	"condition": _exec_condition,
	"transform": _exec_transform,
	"foreach": _exec_foreach,
	"validate": _exec_validate,
	"output": _exec_output,
	"state.get": _exec_state_get,
	"state.set": _exec_state_set,
	"state.delete": _exec_state_delete,
	"doc.create": _exec_doc_create,
	"code.run": _exec_code_run,
	"wait": exec_wait,
	"stop": _exec_stop,
	"member.set": _exec_member_set,
	"send.message": _exec_send_message,
	"doc.get": _exec_doc_get,
	"doc.update": _exec_doc_update,
	"flow.call": _exec_flow_call,
	"knowledge.search": _exec_knowledge_search,
	"handoff": _exec_handoff,
}

_NODE_TYPES = tuple(_NODE_EXECUTORS)


# ---------------------------------------------------------------------------
# Edge evaluation
# ---------------------------------------------------------------------------


def effective_edges(defn: dict) -> list[dict]:
	"""The internal edge list for a pinned graph, derived from its node pointers.

	The graph IR has no ``edges`` array: an edge is a node's ``next`` / ``on_error``
	or one of its per-type routing fields. See :func:`edges_from_nodes`.
	"""
	return edges_from_nodes(defn.get("nodes", []))


def _evaluate_edges(flow_run, node_id: str, node_result: dict, edges_list: list) -> str | None:
	"""
	Pick the successor of ``node_id`` for its result.

	A failed node follows only its ``on_failure`` edge (``on_error``); a successful one follows
	``always`` / ``on_success`` edges and never its error route. ``outcome`` edges (approval
	approve / reject / timeout) are resolved by label, never here. The first match wins.
	"""
	outgoing = [e for e in edges_list if e.get("from") == node_id]
	if not outgoing:
		return None

	failed = isinstance(node_result, dict) and node_result.get("status") == "failed"
	for edge in outgoing:
		edge_type = edge.get("type", "always")
		if failed:
			if edge_type == "on_failure":
				return edge.get("to")
		elif edge_type in ("always", "on_success"):
			return edge.get("to")
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
# Helpers
# ---------------------------------------------------------------------------


def _conversation_of(flow_run, run_ctx: FlowRunContext | None):
	if run_ctx is not None:
		return run_ctx.conversation
	return getattr(flow_run, "conversation", None)


def _mode_of(flow_run, run_ctx: FlowRunContext | None) -> str:
	if run_ctx is not None:
		return run_ctx.mode
	return (getattr(flow_run, "mode", "") or "").lower()


def _create_flow_agent_run(flow_run, node: dict, run_kind: str, prompt: str = "", agent_name: str = None) -> "frappe.Document":
	"""Create an Agent Run document linked to a flow run."""
	if not agent_name and node:
		config = node.get("config") or {}
		agent_name = config.get("agent")
	if not agent_name and getattr(flow_run, "last_agent_run", None):
		agent_name = frappe.db.get_value("Agent Run", flow_run.last_agent_run, "agent")

	run_doc = frappe.get_doc(
		{
			"doctype": "Agent Run",
			"agent": agent_name or None,
			"status": "Started",
			"prompt": prompt,
			"flow_run": flow_run.name,
			"conversation": getattr(flow_run, "conversation", None),
			"flow_node_id": node.get("id"),
			"flow_id": flow_run.flow_id,
			"run_kind": run_kind,
			"start_time": now_datetime(),
		}
	)
	# Agent Run records are internal execution logs. Authenticated users
	# create them through normal permission checks; Guest/webhook paths are
	# allowed because the engine is acting on behalf of the system.
	if frappe.session.user == "Guest":
		run_doc.insert(ignore_permissions=True)
	else:
		if not frappe.has_permission("Agent Run", "create", doc=run_doc):
			frappe.throw(_("Not permitted to create Agent Run"), frappe.PermissionError)
		run_doc.insert()
	commit_if_background()
	return run_doc


def _create_flow_conversation(flow_id: str, entry_node_id: str, ignore_permissions: bool = False) -> "frappe.Document":
	"""Create a shared Agent Conversation for a flow run (``ignore_permissions``: the caller already authorised the run)."""
	from uuid import uuid4

	conv = frappe.get_doc(
		{
			"doctype": "Agent Conversation",
			"title": f"Flow: {flow_id}",
			"session_id": f"flow:{flow_id}:{uuid4().hex[:8]}",
			"is_active": 1,
		}
	)
	# Flow conversations are created by the engine. Authenticated callers
	# use standard permissions; Guest/webhook triggers rely on the system.
	if ignore_permissions or frappe.session.user == "Guest":
		conv.insert(ignore_permissions=True)
	else:
		if not frappe.has_permission("Agent Conversation", "create", doc=conv):
			frappe.throw(_("Not permitted to create Agent Conversation"), frappe.PermissionError)
		conv.insert()
	commit_if_background()
	return conv


def verify_approval_permission(run, user: str | None = None):
	"""Raise PermissionError unless ``user`` (default: session user) may decide this run's approval.

	``run`` is the Flow Run document (or its parsed ``waiting`` dict). Fail closed: see
	:func:`check_approver`. Applies equally to approve and reject.
	"""
	waiting = run if isinstance(run, dict) else _load_waiting(run)
	user = user or frappe.session.user
	reason = check_approver(waiting, user, frappe.get_roles(user))
	if reason:
		frappe.throw(_(reason), frappe.PermissionError)


def _flow_reply_text(flow_run, settings, result) -> str | None:
	"""The text a Gateway-triggered run replies with: its final ``output`` node value (or ``reply`` in context)."""
	try:
		ctx = _context_of(flow_run, settings)
		node_id = getattr(result, "node_id", None)
		nodes = {n.get("id"): n for n in _pinned_version(flow_run).graph.get("nodes", [])}
		value = None
		if (nodes.get(node_id) or {}).get("type") == "output":
			value = ctx.node_outputs.get(node_id)
		if value is None:
			value = ctx.data.get("reply")
		if isinstance(value, dict):
			value = value.get("reply") or value.get("text") or value.get("message")
		return str(value) if isinstance(value, (str, int, float)) and str(value).strip() else None
	except Exception:
		return None


def _sync_gateway_event(flow_run, status: str, reply_text: str | None = None, error: str = ""):
	"""Gateway-triggered runs hand their outcome to the gateway reply pipeline."""
	if getattr(flow_run, "trigger_type", None) != "Gateway":
		return
	from huf.ai.gateway_service import finish_flow_event
	finish_flow_event(flow_run.name, status, reply_text, error)
	commit_if_background()


def _complete_flow_run(flow_run, reply_text: str | None = None) -> bool:
	"""Mark a flow run as successfully completed. A run that already finished is left alone (returns False)."""
	if not _transition_run(
		flow_run, {"status": "Success", "completed_at": now_datetime()}, not_from_statuses=TERMINAL_STATUSES
	):
		return False
	commit_if_background()
	_sync_gateway_event(flow_run, "Success", reply_text)
	subflow.on_child_finished(flow_run, "Success")
	return True


def _fail_flow_run(flow_run, error_msg: str) -> bool:
	"""Mark a flow run as failed. A run that already finished is left alone (returns False).

	The write is conditional on the run not being terminal already, so a live worker finishing a run
	cannot be overwritten by "Mark as failed" or the stale sweep, and neither can undo a finished run.
	"""
	if not _transition_run(
		flow_run,
		{"status": "Failed", "last_error": mask_text(error_msg), "completed_at": now_datetime()},
		not_from_statuses=TERMINAL_STATUSES,
	):
		return False
	commit_if_background()
	_sync_gateway_event(flow_run, "Failed", error=error_msg)
	_publish_flow_event(flow_run, "flow_failed", {"error": error_msg})
	flow_hooks.notify_failure(flow_run.name)
	subflow.on_child_finished(flow_run, "Failed", error_msg)
	return True


# ---------------------------------------------------------------------------
# Realtime event publishing
# ---------------------------------------------------------------------------


def _publish_flow_event(flow_run, event_type: str, data: dict):
	"""Publish a Frappe Realtime event for live flow UI tracking.

	Never to the site room (every desk user joins it). It goes to the run's document room, where subscribing
	needs read permission on the run, and to the person who started the run while they may still view its flow
	(app editors never read run documents, but follow their own runs on the canvas). Error text is masked.
	"""
	try:
		message = {"flow_run_id": flow_run.name, "flow_id": flow_run.flow_id, **data}
		if message.get("error"):
			message["error"] = plain_error(mask_text(str(message["error"])))
		for room in _flow_event_rooms(flow_run):
			# An explicit room: inside a background task Frappe would otherwise pick the task's room.
			frappe.publish_realtime(event=event_type, message=message, room=room, after_commit=False)
	except Exception:
		# Realtime is best-effort; don't break execution if it fails
		pass


def _flow_event_rooms(flow_run) -> list[str]:
	rooms = [get_doc_room("Agent Flow Run", flow_run.name)]
	user = flow_run.owner
	if user and user != "Guest" and flow_access(user, flow_run.flow_definition, "view"):
		rooms.append(get_user_room(user))
	return rooms
