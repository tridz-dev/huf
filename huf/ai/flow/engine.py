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

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.desk.doctype.notification_settings.notification_settings import is_email_notifications_enabled

from huf.ai.flow import create_doc as flow_create_doc, state as flow_state
from huf.ai.gateways.slack import flow_hooks
from huf.ai.graph.permissions import envelope_declares
from huf.ai.flow.orchestrator import (
	build_flow_context_system_message,
	build_router_prompt,
)
from huf.ai.flow.tool_executor import execute as execute_tool
from huf.ai.flow.tool_executor import tool_run_context
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
	RoutingError,
	RoutingMode,
	Router,
)
from huf.ai.graph.expressions import evaluate_bool, parse_expression
from huf.ai.graph.transforms import Limits as TransformLimits
from huf.ai.graph.templates import TemplateError, render_template
from huf.ai.graph.transforms import run_transform
from huf.ai.output_budget import OutputBudget, OutputBudgetExceeded, enforce_output_budget
from huf.ai.tools.invocation import RunContext
from huf.ai.transaction import commit_if_background


DEFAULT_MAX_HOPS = 100

RUN_LOCK_TTL_SECONDS = 600
"""How long a run lock survives if its holder dies mid-execution."""

WAITING_STATUSES = ("Waiting User", "Waiting Approval")

ADVANCEABLE_STATUSES = ("Running", "Queued")

#: How each Flow node type resolves its successor. One table, consulted in one
#: place by the executor's Router -- replacing the pre-T-22 split between the
#: ``_execute_node`` dispatch table and a type-switch inside ``_execute_loop``
#: (structural knot 3).
NODE_ROUTING = {
	"condition": RoutingMode.SELF_ROUTED,
	"router.llm": RoutingMode.SELF_ROUTED,
	"router.decision": RoutingMode.SELF_ROUTED,
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
		self.flow_id = getattr(flow_run, "flow_id", None)
		self.run_id = getattr(flow_run, "name", None)
		self.mode = (getattr(flow_run, "mode", "") or "normal").lower()
		self.conversation = getattr(flow_run, "conversation", None)

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
	if ctx.node_outputs:
		payload[NODE_OUTPUTS_KEY] = ctx.node_outputs
	return json.dumps(payload, default=str)


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
	return load_context(getattr(flow_run, "context_json", None))


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
		frappe.throw(_("Flow '{0}' is not active (status: {1})").format(flow_id, doc.status))

	defn = json.loads(doc.definition_json) if isinstance(doc.definition_json, str) else doc.definition_json
	return defn


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

	version = PinnedVersion.pin(load_definition(getattr(flow_run, "flow_id", None)))
	_store_pin(flow_run, version)
	return version


def _store_pin(flow_run, version: PinnedVersion) -> None:
	"""Record a pin on the run, where the schema can hold one.

	Guarded rather than assumed: a site whose ``Flow Run`` has not been
	migrated yet simply keeps resolving the pin per run instead of erroring.
	"""
	try:
		if not frappe.db.has_column("Flow Run", "pinned_definition"):
			return
		flow_run.db_set(
			{
				"pinned_fingerprint": version.fingerprint,
				"pinned_definition": version.to_json(),
			}
		)
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
STALE_RUN_SWEEP_REASON = "Run did not complete (worker stopped)"


def sweep_stale_runs(now=None, minutes: int | None = None) -> list[str]:
	"""Scheduler entry (every 5 minutes): fail Flow Runs stuck in Queued/Running.

	A run qualifies when it has not been modified for ``minutes`` (default
	:data:`STALE_RUN_SWEEP_MINUTES`) and no worker holds its run lock. Waiting runs (approval,
	user input) are never touched. A manual "Mark as failed" exists in ``api.py``.
	"""
	from datetime import timedelta

	cutoff = (now or now_datetime()) - timedelta(minutes=minutes or STALE_RUN_SWEEP_MINUTES)
	names = frappe.get_all(
		"Flow Run",
		filters={"status": ["in", ["Queued", "Running"]], "modified": ["<", cutoff]},
		pluck="name",
		limit_page_length=200,
	)
	failed: list[str] = []
	for name in names:
		try:
			if frappe.cache().get(_run_lock_key(name)):
				continue  # a worker is still advancing it
			flow_run = frappe.get_doc("Flow Run", name)
			if flow_run.status not in ("Queued", "Running"):
				continue
			_fail_flow_run(flow_run, STALE_RUN_SWEEP_REASON)
			failed.append(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow stale run sweep: {name}")
	return failed


def _run_lock_key(flow_run_name: str) -> str:
	return f"huf:flow:run_lock:{flow_run_name}"


def _acquire_run_lock(flow_run_name: str) -> bool:
	"""Take the single-writer lock for a run.

	Same shape as the distributed lock in ``agent/integration.py``: a Redis
	``SET key value EX ttl NX``, which is atomic, so exactly one of two
	concurrent callers gets ``True``. Before T-22 ``run_flow`` took no lock at
	all and two concurrent calls could both advance the same cursor (F-4).
	"""
	try:
		return bool(frappe.cache().set(_run_lock_key(flow_run_name), 1, ex=RUN_LOCK_TTL_SECONDS, nx=True))
	except Exception:
		# A cache that cannot serve the lock must not silently serialize
		# nothing *and* block execution; the executor's status guard is the
		# second line of defence.
		return True


def _release_run_lock(flow_run_name: str) -> None:
	try:
		# ``delete`` (raw key), not ``delete_value``: the lock is taken with a raw
		# ``SET NX``, while ``delete_value`` removes the site-prefixed key, so the lock
		# would otherwise survive until its TTL and silently block approve/resume.
		frappe.cache().delete(_run_lock_key(flow_run_name))
	except Exception:
		pass


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


#: Flow Run ``trigger_type`` -> the trigger node type that starts such a run.
TRIGGER_NODE_TYPES = {
	"Webhook": "trigger.webhook",
	"Schedule": "trigger.schedule",
	"Doc Event": "trigger.doc-event",
}


def select_entry_node(defn: dict, trigger_type: str = "Manual") -> str:
	"""The node id a new run starts at.

	``entry`` is one node id or, when the flow starts from triggers, an array
	(one id per trigger). A Webhook / Schedule / Doc Event run starts at the
	trigger node of that type; a Manual or Gateway run (and a flow whose entry
	is not a trigger at all) starts at the first entry. Fails closed when the
	flow only has triggers of other types.
	"""
	entry = defn.get("entry")
	entries = [entry] if isinstance(entry, str) else [e for e in (entry or []) if isinstance(e, str)]
	if not entries:
		raise ValueError("Flow definition has no entry node")
	wanted = TRIGGER_NODE_TYPES.get(trigger_type)
	if wanted is None:
		return entries[0]
	types = {n.get("id"): n.get("type") for n in defn.get("nodes", []) if isinstance(n, dict)}
	for node_id in entries:
		if types.get(node_id) == wanted:
			return node_id
	if all(not str(types.get(e) or "").startswith("trigger.") for e in entries):
		return entries[0]
	raise ValueError(f"Flow has no {wanted} entry for a {trigger_type} run")


def create_flow_run(
	flow_id: str,
	payload: dict | None = None,
	trigger_type: str = "Manual",
	ignore_permissions: bool = False,
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

	Returns:
	    Flow Run document
	"""
	defn_doc = frappe.get_doc("Flow Definition", flow_id)
	defn = json.loads(defn_doc.definition_json) if isinstance(defn_doc.definition_json, str) else defn_doc.definition_json

	from huf.huf.doctype.flow_definition.activation_rules import entry_is_unset

	if entry_is_unset(defn):
		frappe.throw(_("Flow {0} has no trigger configured (trigger.unset is not runnable)").format(flow_id))

	try:
		entry_node = select_entry_node(defn, trigger_type)
	except ValueError as exc:
		frappe.throw(_("Cannot start flow {0}: {1}").format(flow_id, str(exc)))

	version = PinnedVersion.pin(defn)

	resolved_mode = "normal"
	max_hops = DEFAULT_MAX_HOPS

	# Every run owns a shared conversation for its agent steps
	conversation = _create_flow_conversation(flow_id, entry_node)

	fields = {
		"doctype": "Flow Run",
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
		"trigger_payload": json.dumps(payload or {}),
		"conversation": conversation.name if conversation else None,
		"started_at": now_datetime(),
	}
	if _has_pin_columns():
		fields["pinned_fingerprint"] = version.fingerprint
		fields["pinned_definition"] = version.to_json()

	flow_run = frappe.get_doc(fields)
	# Authenticated callers are already verified by the public API.
	# Webhook triggers run as Guest after HMAC validation, so the internal
	# Flow Run record must be created on behalf of the system.
	if ignore_permissions or frappe.session.user == "Guest":
		flow_run.insert(ignore_permissions=True)
	else:
		if not frappe.has_permission("Flow Run", "create", doc=flow_run):
			frappe.throw(_("Not permitted to create Flow Run"), frappe.PermissionError)
		flow_run.insert()
	commit_if_background()

	return flow_run


def _has_pin_columns() -> bool:
	try:
		return bool(frappe.db.has_column("Flow Run", "pinned_definition"))
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
		flow_run = frappe.get_doc("Flow Run", flow_run_name)
		if flow_run.status in WAITING_STATUSES:
			# A queued job for a run that has since paused again: only approve / resume / expiry move a
			# waiting run (they set it Running first). Re-entering here would run the paused step twice.
			return
		version = _pinned_version(flow_run)
		defn = version.graph

		nodes_map = {n["id"]: n for n in defn.get("nodes", [])}
		edges_list = effective_edges(defn)
		run_ctx = _build_run_context(flow_run, version)

		flow_run.db_set({"status": "Running", "last_error": ""})
		commit_if_background()

		try:
			_execute_loop(flow_run, nodes_map, edges_list, run_ctx)
		except Exception as e:
			_fail_flow_run(flow_run, str(e))
			frappe.log_error(f"Flow engine error: {frappe.get_traceback()}", "Flow Engine")
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
	return FlowRunContext(
		{},
		flow_run=flow_run,
		version=version,
		context=context,
	)


def resume_flow_run(flow_run_name: str, user_input: dict | None = None):
	"""
	Resume a paused flow run (Waiting User / Waiting Approval).

	A pause records where to continue (structural knot 2), so resuming
	*advances past* the node that paused rather than re-executing it. That is
	both the correct semantics -- re-running a node that already produced its
	side effects is a bug -- and what keeps a resumed run independent of any
	edit made to the definition while it was waiting (F-1).

	Args:
	    flow_run_name: Name of the Flow Run
	    user_input: Optional input to merge into context
	"""
	flow_run = frappe.get_doc("Flow Run", flow_run_name)

	if flow_run.status not in WAITING_STATUSES:
		frappe.throw(_("Flow Run is not in a waiting state (status: {0})").format(flow_run.status))
	if flow_run.status == "Waiting Approval":
		# An approval is only ever resolved by approve_flow_run, which checks the approver.
		frappe.throw(_("Flow Run is waiting for approval; use approve_flow_run"), frappe.PermissionError)

	version = _pinned_version(flow_run)
	run_ctx = _build_run_context(flow_run, version)

	if user_input:
		run_ctx.context.update(user_input)
		run_ctx.save_context()

	waiting = _load_waiting(flow_run)
	paused_node = flow_run.current_node_id
	next_node_id = waiting.get("resume_node") or _evaluate_edges(
		flow_run, paused_node, {"status": "success"}, run_ctx.edges
	)

	flow_run.db_set({"waiting": None, "status": "Running"})
	commit_if_background()

	if not next_node_id:
		# The node that paused was the last step on its chain.
		_complete_flow_run(flow_run)
		return

	flow_run.db_set("current_node_id", next_node_id)
	flow_run.db_set("hop_count", (flow_run.hop_count or 0) + 1)
	commit_if_background()

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


@frappe.whitelist()
def approve_flow_run(flow_run_name: str, decision: str, comment: str | None = None):
	"""
	Approve or reject a flow run waiting on a ``human.approval`` node.

	The approver is checked first (fail closed, see :func:`check_approver`) for
	BOTH decisions. The decision record
	``{"decision", "comment", "decided_by", "decided_at"}`` becomes the approval
	node's output, so downstream nodes read it as ``{"$from": "<approval_node_id>"}``.
	Routing is the node's own ``approve_next`` / ``reject_next``.

	Args:
	    flow_run_name: Name of the Flow Run
	    decision: "approved" or "rejected"
	    comment: Optional comment
	"""
	if decision not in APPROVAL_DECISIONS:
		frappe.throw(_("decision must be 'approved' or 'rejected'"))

	flow_run = frappe.get_doc("Flow Run", flow_run_name)

	if flow_run.status != "Waiting Approval":
		frappe.throw(_("Flow Run is not waiting for approval (status: {0})").format(flow_run.status))

	# Permission is verified before anything is mutated.
	waiting = _load_waiting(flow_run)
	verify_approval_permission(waiting)

	version = _pinned_version(flow_run)
	run_ctx = _build_run_context(flow_run, version)
	edges_list = run_ctx.edges
	current_node = flow_run.current_node_id

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

	router = _build_router(flow_run, run_ctx, edges_list, ExecutionState(cursor=current_node))
	next_node = router.resolve_labelled(current_node, decision)

	if not next_node:
		flow_run.db_set("waiting", None)
		_fail_flow_run(flow_run, f"No route for approval outcome '{decision}' from node '{current_node}'")
		_clear_flow_notifications(flow_run)
		return

	flow_run.db_set({"current_node_id": next_node, "waiting": None, "status": "Running"})
	flow_run.db_set("hop_count", (flow_run.hop_count or 0) + 1)
	commit_if_background()

	_clear_flow_notifications(flow_run)

	run_flow(flow_run.name)


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
		flow_run = frappe.get_doc("Flow Run", flow_run_name)
		if flow_run.status != "Waiting Approval":
			return False
		waiting = _load_waiting(flow_run)
		if not approval_expired(waiting, now or now_datetime()):
			return False

		timeout_next = waiting.get("timeout_next")
		node_id = flow_run.current_node_id
		if not timeout_next:
			flow_run.db_set("waiting", None)
			_fail_flow_run(flow_run, f"Approval timed out at node '{node_id}'")
			_clear_flow_notifications(flow_run)
			return True

		version = _pinned_version(flow_run)
		run_ctx = _build_run_context(flow_run, version)
		run_ctx.context.record_output(
			node_id, {"decision": "timeout", "comment": None, "decided_by": None, "decided_at": _utc_now_iso()}
		)
		run_ctx.save_context()
		flow_run.db_set({"current_node_id": timeout_next, "waiting": None, "status": "Running"})
		flow_run.db_set("hop_count", (flow_run.hop_count or 0) + 1)
		commit_if_background()
		_clear_flow_notifications(flow_run)
	finally:
		_release_run_lock(flow_run_name)

	if enqueue:
		# The transition must be visible to the worker before it starts: a read request commits only
		# when it ends, so commit now, otherwise the job would see the run still waiting and run the
		# approval step again.
		frappe.db.commit()  # nosemgrep
		frappe.enqueue("huf.ai.flow.engine.run_flow", queue="default", flow_run_name=flow_run_name)
	else:
		run_flow(flow_run_name)
	return True


def approval_expired(waiting: dict, now) -> bool:
	"""True when the approval's recorded ``timeout_at`` (ISO string) is in the past."""
	raw = (waiting or {}).get("timeout_at")
	if not raw:
		return False
	from datetime import datetime

	try:
		deadline = datetime.fromisoformat(str(raw))
	except ValueError:
		return False
	if isinstance(now, str):
		now = datetime.fromisoformat(now)
	return now >= deadline


def check_approver(waiting: dict, user: str, roles) -> str | None:
	"""Fail-closed approver check. Returns None when allowed, else a denial reason.

	* ``approver_type == "role"``: ``user`` must hold ``approver_role``.
	* ``approver_type == "user"``: ``user`` must be in ``approver_users``.
	* anything else (absent included), or a type whose list/role is empty: only a
	  ``System Manager`` may decide.
	The same check applies to approve and reject.
	"""
	waiting = waiting or {}
	roles = set(roles or ())
	approver_type = waiting.get("approver_type")
	if approver_type == "role" and waiting.get("approver_role"):
		if waiting["approver_role"] in roles:
			return None
		return "You do not have the required role '%s' to decide this approval" % waiting["approver_role"]
	if approver_type == "user" and waiting.get("approver_users"):
		if user in set(waiting["approver_users"]):
			return None
		return "You are not an authorised approver for this flow run"
	if "System Manager" in roles:
		return None
	return "Only a System Manager may decide this approval"


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
			routing=NODE_ROUTING.get(node_type, RoutingMode.DEFAULT),
			raw=node,
		)
	return GraphProgram(version, specs, _first_entry(version.graph), settings=dict(settings or {}))


def _first_entry(graph: dict) -> str | None:
	entry = graph.get("entry")
	if isinstance(entry, list):
		return entry[0] if entry else None
	return entry


def _build_router(
	flow_run, settings, edges_list: list, state: ExecutionState, unhandled_failures: list | None = None
) -> Router:
	"""One routing path for every node type (structural knots 3 and 4).

	``unhandled_failures`` collects ``"<node id>: <error>"`` for every failed node whose
	chosen successor is not one of its ``on_failure`` edges (an ``on_error`` target is
	one), so the run can still end ``Failed`` after an ``always`` edge ran cleanup nodes.
	"""
	def default_resolver(node: NodeSpec, outcome: Outcome, context: GraphContext):
		chosen = _resolve_default(node, outcome, context)
		if outcome.status == "failed" and unhandled_failures is not None:
			# No edge chosen -> the executor falls back to the node's ``on_error``.
			handled = (chosen is None and bool(node.raw.get("on_error"))) or any(
				e.get("from") == node.id and e.get("to") == chosen and e.get("type") == "on_failure"
				for e in edges_list
			)
			if not handled:
				unhandled_failures.append(f"Node '{node.id}' failed: {outcome.error or 'unknown error'}")
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

	def __init__(self, flow_run):
		self.flow_run = flow_run

	def save_cursor(self, cursor: str) -> None:
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
	record["error"] = str(outcome.error or record.get("error") or "The step failed")
	return record


def _make_node_handler(flow_run, settings):
	"""Bridge one Flow node executor into the executor's handler contract."""

	def handler(node: NodeSpec, context: GraphContext, state: ExecutionState):
		try:
			result = _execute_node(flow_run, node.raw, settings)
		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), f"Flow node {node.id} raised")
			result = {"status": "failed", "error": str(exc) or exc.__class__.__name__}
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
		return outcome

	return handler


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
	router = _build_router(flow_run, settings, edges_list, state, unhandled_failures)
	handler = _make_node_handler(flow_run, settings)
	handlers = {node_type: handler for node_type in _NODE_TYPES}

	policy = ExecutionPolicy(
		max_hops=getattr(flow_run, "max_hops", None) or DEFAULT_MAX_HOPS,
	)

	executor = GraphExecutor(
		program,
		handlers,
		router=router,
		policy=policy,
		store=_FlowStateStore(flow_run),
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
		_publish_flow_event(
			flow_run,
			"flow_paused",
			{"node_id": result.node_id, "status": getattr(flow_run, "status", None)},
		)
		return result

	if result.status == ExecutionResult.FAILED:
		_publish_flow_event(flow_run, "flow_error", {"error": result.error})
		_fail_flow_run(flow_run, result.error)
		return result

	if unhandled_failures:
		# A failure no on_failure/on_error route handled: cleanup nodes may have run
		# via an ``always`` edge, but the run is still Failed (first failure wins).
		_publish_flow_event(flow_run, "flow_error", {"error": unhandled_failures[0]})
		_fail_flow_run(flow_run, unhandled_failures[0])
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

	executor = _NODE_EXECUTORS.get(node_type)
	if not executor:
		frappe.throw(_("Unknown node type: {0}").format(node_type))

	try:
		return executor(flow_run, node, config, settings)
	except TemplateError as exc:
		# Authoring error in a {"$template": ...} value: fail this node (so on_error applies).
		return {"status": "failed", "error": f"Template error: {exc}"}


def _exec_trigger_webhook(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute trigger.webhook node - mostly a passthrough for UI clarity."""
	ctx = _context_of(flow_run, settings)
	return {"status": "success", "output": ctx.as_dict()}


def _exec_trigger_unset(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""trigger.unset is a placeholder with no trigger configured; it is not runnable."""
	return {"status": "failed", "error": "trigger.unset is not runnable: configure a trigger for this flow"}


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

	The payload (``trigger`` and ``doc``) is set at flow run creation by the trigger entry point
	(``huf.ai.flow.triggers.run_flow_from_trigger``); this executor enriches it with event
	metadata for downstream nodes.
	"""
	ctx = _context_of(flow_run, settings)

	trigger_info = ctx.get("trigger") or {}
	doc_data = ctx.get("doc") or {}

	doc_event_info = {
		"trigger_type": "doc_event",
		"triggered_at": str(now_datetime()),
		"doctype": trigger_info.get("doctype", ctx.get("doctype")),
		"docname": trigger_info.get("docname", ctx.get("docname")),
		"event": trigger_info.get("event", ctx.get("event")),
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
	return render_template(config.get("prompt") or "", bindings if isinstance(bindings, dict) else {})


def _exec_agent_run(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute agent.run node (config: ``agent``, ``prompt``, ``prompt_bindings``).

	Output (``{"$from": "<node_id>"}``) is the agent's response text.
	"""
	agent_name = config.get("agent")
	if not agent_name:
		return {"status": "failed", "error": "agent.run node missing agent in config"}
	if not config.get("prompt"):
		return {"status": "failed", "error": "agent.run node missing prompt in config"}

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
		return {"status": "failed", "error": str(e)}


def _bound_gateway(flow_run, run_id: str = ""):
	"""Trusted gateway for the WhatsApp tool: the gateway that started this flow.

	Model/tool arguments never select it, and no node config does (the schema has no gateway
	field); empty means the tool fails closed (gateway_context_required).
	"""
	from huf.ai.tools.whatsapp import trusted_gateway

	gateway = ""
	contact = ""
	try:
		payload = flow_run.get("trigger_payload")
		payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
		event = payload.get("gateway_event") if isinstance(payload, dict) else None
		if event:
			row = frappe.db.get_value("Gateway Event", event, ["gateway", "sender_id"], as_dict=True) or {}
			gateway = row.get("gateway") or ""
			contact = row.get("sender_id") or ""
	except Exception:
		gateway, contact = "", ""
	return trusted_gateway(gateway, run_id=run_id, contact=contact)


def normalize_tool_result(raw) -> dict:
	"""Collapse whatever a tool returned into ``{"success", "result", "error"}``.

	The invocation layer wraps results as ``{"success", "result", "error"}``, but many tools
	return a JSON *string* such as ``{"success": false, "error": "..."}`` (or ``{"error": ...}``)
	as their ``result`` and the wrapper still says success. A tool that reports ``success: false``,
	or carries a truthy ``error`` key, is a failure here, so the node is marked failed instead of
	green. A JSON string result is parsed so later nodes can read fields with ``{"$from": "<node>.x"}``.
	"""
	if isinstance(raw, dict) and "success" in raw:
		success = bool(raw.get("success"))
		inner = raw.get("result")
		error = raw.get("error") or ""
	else:
		success, inner, error = True, raw, ""

	if isinstance(inner, str) and inner.lstrip()[:1] in ("{", "["):
		try:
			inner = json.loads(inner)
		except (ValueError, TypeError):
			pass

	if isinstance(inner, dict):
		reported_error = inner.get("error")
		if inner.get("success") is False or reported_error:
			success = False
			if not error:
				error = str(reported_error or inner.get("message") or "tool reported failure")

	if not success and not error:
		error = "tool failed"
	return {"success": success, "result": inner, "error": error if not success else ""}


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
		return {"status": "failed", "error": "tool.call node missing tool_id in config"}

	run_ctx = _run_context(settings)
	ctx = _context_of(flow_run, settings)
	args = ctx.resolve(dict(config.get("input") or {}))

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
			from huf.ai.mcp_client import execute_mcp_tool

			import asyncio

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
				raw = {"success": False, "error": f"tool '{tool_name}' timed out after {config['timeout_ms']} ms"}
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
					"error": " ".join(t for t in texts if t) or "MCP tool reported an error" if is_error else "",
				}
		else:
			with tool_run_context(invocation_ctx), _bound_gateway(flow_run, getattr(run_doc, "name", "") or ""):
				raw = execute_tool(tool_name, args)

		result = normalize_tool_result(raw)
		is_success = result["success"]
		error_msg = result["error"]

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
		if tool_call_doc is not None:
			tool_call_doc.update({"status": "Failed", "error_message": str(e)})
			tool_call_doc.save(ignore_permissions=True)
		run_doc.db_set({"status": "Failed", "error_message": str(e), "end_time": now_datetime()})
		commit_if_background()
		return {"status": "failed", "error": str(e)}


def build_router_llm_prompt(prompt: str, options: list, context: dict) -> str:
	"""Prompt asking the model to pick exactly one option label."""
	labels = [str((o or {}).get("label")) for o in options]
	return "\n".join(
		[
			"You are a routing step in a workflow. Choose exactly one option for the situation below.",
			"Reply with ONLY the option label, exactly as written, and nothing else.",
			"",
			"## Instruction",
			str(prompt),
			"",
			"## Options",
			*[f"- {label}" for label in labels],
			"",
			"## Workflow input",
			json.dumps(context, default=str)[:4000],
		]
	)


def choose_option(text: str, options: list) -> dict | None:
	"""Map the model's reply onto one option (``{"label", "node_id"}``), or None.

	Accepts the bare label, a quoted label, a JSON object with ``label``, or a reply that mentions
	exactly one label. Ambiguity or no match is None (the caller routes to ``default``).
	"""
	if not isinstance(text, str) or not text.strip():
		return None
	by_label = {str((o or {}).get("label", "")).strip().lower(): o for o in options if (o or {}).get("node_id")}
	candidate = text.strip().strip("`\"' \n.")
	if candidate.startswith("{"):
		try:
			parsed = json.loads(text.strip().strip("`"))
			if isinstance(parsed, dict):
				candidate = str(parsed.get("label", "")).strip()
		except ValueError:
			pass
	if candidate.lower() in by_label:
		return by_label[candidate.lower()]
	lowered = text.lower()
	hits = [o for label, o in by_label.items() if label and label in lowered]
	return hits[0] if len(hits) == 1 else None


def _run_coroutine(coro):
	import asyncio

	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(coro)
	finally:
		loop.close()


def resolve_router_model(model_name: str | None = None) -> tuple[str, str]:
	"""``(provider, model)`` for a router step.

	``model_name`` is the name of an AI Model record: its provider is used. Without one, the first
	keyed provider's default chat model is used. A named model that is missing, or whose provider has
	no API key, is an authoring error and raises (the router then routes to its default).
	"""
	from huf.ai.app_seeding.hub_orchestrator import (
		_default_model_for_provider,
		_find_keyed_provider,
		_provider_has_key,
	)

	if model_name:
		provider = frappe.db.get_value("AI Model", model_name, "provider")
		if not provider:
			raise RuntimeError(f"AI model '{model_name}' was not found")
		if not _provider_has_key(provider):
			raise RuntimeError(f"AI provider '{provider}' for model '{model_name}' has no API key")
		return provider, model_name

	provider = _find_keyed_provider()
	model = _default_model_for_provider(provider) if provider else None
	if not provider or not model:
		raise RuntimeError("no AI Provider with an API key and a chat model is configured")
	return provider, model


def _router_completion(prompt_text: str, provider: str, model: str) -> str:
	"""One direct LLM completion (no agent involved) with the given provider and model."""
	from huf.ai.providers.litellm import get_simple_completion

	return _run_coroutine(get_simple_completion(model, [{"role": "user", "content": prompt_text}], provider))


_TEXT_REF_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)\}(?!\})")


def render_text_refs(text: str, ctx: GraphContext) -> str:
	"""Fill ``{input.field}`` / ``{node_id.field}`` / ``{foreach.item}`` placeholders in a plain-text field.

	Used for ``router.llm.prompt`` and ``human.approval.message`` (the Insert data picker writes these).
	A placeholder that does not resolve is left as written, so ordinary braces in a message never fail a run.
	"""
	from huf.ai.graph.templates import _stringify

	def sub(match: re.Match) -> str:
		path = match.group(1)
		if path.split(".")[0].split("[")[0] not in ctx.reference_roots():
			return match.group(0)
		value = ctx.resolve_reference(path)
		return match.group(0) if value is None else _stringify(value)

	return _TEXT_REF_RE.sub(sub, text or "")


def _exec_router_llm(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute router.llm node (config: ``prompt``, ``options[{label,node_id}]``, ``default``, ``model``).

	The model picks an option by label; no match, an unusable reply, or any failure routes to
	``default`` (required, so routing is total). ``model`` is an optional AI Model name; absent means
	the first keyed provider's default chat model. Output is
	``{"label", "node_id", "reason", "model", "provider"}`` (``model`` is the one used, or attempted).
	"""
	options = [o for o in (config.get("options") or []) if isinstance(o, dict) and o.get("node_id")]
	default = config.get("default")
	if not default:
		return {"status": "failed", "error": "router.llm node missing default in config"}
	if not options:
		return {"status": "failed", "error": "router.llm node has no options"}

	ctx = _context_of(flow_run, settings)
	chosen, reason = None, ""
	provider, model = None, config.get("model") or None
	try:
		provider, model = resolve_router_model(model)
		reply = _router_completion(
			build_router_llm_prompt(
				render_text_refs(config.get("prompt") or "", ctx),
				options,
				{"input": ctx.as_dict(), "steps": ctx.node_outputs},
			),
			provider,
			model,
		)
		if not reply:
			reason = "llm_failed: the model returned no reply"
		else:
			chosen = choose_option(reply, options)
			reason = "matched" if chosen else "no_match"
	except Exception as e:
		reason = f"llm_failed: {e}"

	if chosen:
		node_id, label = chosen["node_id"], chosen.get("label")
	else:
		node_id, label = default, "default"
	return {
		"status": "success",
		"next_node_id": node_id,
		"output": {"label": label, "node_id": node_id, "reason": reason, "model": model, "provider": provider},
	}


def _exec_router_decision(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute router.decision node (config: ``policy``, ``options``, ``default``).

	Not offered by the UI and never activates a provider: it always routes to ``default``
	(routing is total) and says so in its output.
	"""
	default = config.get("default")
	if not default:
		return {"status": "failed", "error": "router.decision node missing default in config"}
	valid_node_ids = {o["node_id"] for o in (config.get("options") or []) if isinstance(o, dict) and o.get("node_id")}
	if not valid_node_ids:
		return {"status": "failed", "error": "router.decision node has no options"}

	return {
		"status": "success",
		"next_node_id": default,
		"output": {"node_id": default, "reason": "router.decision is not enabled for this Flow run"},
	}


def _exec_human_approval(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""Execute human.approval node - pause for human decision.

	Config: ``message``, ``approve_next``, ``reject_next``, ``timeout_next``, ``timeout_ms``,
	``approver_type`` (``role`` / ``user``), ``approver_role``, ``approver_users``. Without a
	declared approver only a System Manager can decide (:func:`check_approver`). Returns a pause
	as a *value*; the executor never has to reload the document and compare status strings to
	notice (structural knot 2). The decision record is the node's output once decided.
	"""
	if flow_run.status == "Waiting Approval" and flow_run.current_node_id == node.get("id"):
		return {"status": "waiting_approval"}

	ctx = _context_of(flow_run, settings)

	timeout_ms = config.get("timeout_ms")
	timeout_at = None
	if timeout_ms:
		from datetime import timedelta

		timeout_at = (now_datetime() + timedelta(milliseconds=timeout_ms)).isoformat()

	waiting_data = {
		"type": "approval",
		"node_id": node.get("id"),
		"message": render_text_refs(config.get("message", ""), ctx),
		"approver_type": config.get("approver_type"),
		"approver_role": config.get("approver_role"),
		"approver_users": config.get("approver_users") or [],
		"timeout_next": config.get("timeout_next"),
		"timeout_ms": timeout_ms,
		"timeout_at": timeout_at,
	}

	# Persist earlier nodes' outputs so downstream {"$from": ...} still resolves after the pause.
	_persist_context(flow_run, ctx, settings)
	flow_run.db_set({"status": "Waiting Approval", "waiting": json.dumps(waiting_data)})
	commit_if_background()
	_send_approval_notifications(flow_run, node, config, waiting_data)
	flow_hooks.notify_approvers(flow_run)
	return {"status": "waiting_approval"}


def _exec_condition(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	Execute condition node (config: ``expression``, ``on_true``, ``on_false``).

	The expression is the shared graph-IR expression language
	(``huf.ai.graph.expressions``, e.g. ``input['amount'] > 100``) evaluated against the run's
	reference roots (``input``, ``trigger``, earlier node ids, ``foreach``). Both targets are
	required by the schema; the chosen one is the node's successor.
	"""
	expression = config.get("expression", "")
	true_node = config.get("on_true")
	false_node = config.get("on_false")

	if not expression:
		return {"status": "failed", "error": "condition node missing 'expression' in config"}
	if not true_node or not false_node:
		return {"status": "failed", "error": "condition node needs both 'on_true' and 'on_false'"}

	ctx = _context_of(flow_run, settings)

	try:
		result = evaluate_bool(parse_expression(expression), ctx.reference_roots())
	except Exception as e:
		return {"status": "failed", "error": f"Condition evaluation failed: {str(e)}"}

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
		return {"status": "failed", "error": err.message if err else f"transform '{config.get('op')}' failed"}

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
			return {"status": "failed", "error": f"sub-chain exceeded its hop budget ({max_hops})"}

		node = by_id.get(cursor)
		if node is None:
			return {"status": "failed", "error": f"sub-chain references unknown node '{cursor}'"}
		if node.get("type") == "human.approval":
			return {"status": "failed", "error": f"human.approval '{cursor}' cannot run inside a loop body"}

		last_result = _execute_node(flow_run, node, settings)
		ctx.record_output(cursor, last_result.get("output", last_result.get("result")))
		if last_result.get("status") == "failed":
			on_error = node.get("on_error")
			if not on_error:
				return last_result
			cursor = on_error
			continue

		if NODE_ROUTING.get(node.get("type")) == RoutingMode.SELF_ROUTED:
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
		return {"status": "failed", "error": f"foreach node '{node_id}' 'items' did not resolve to a list"}

	run_ctx = _run_context(settings)
	contract_limits = ((run_ctx.definition.get("contract") or {}).get("limits") or {}) if run_ctx is not None else {}
	caps = [c for c in (config.get("max_iterations"), contract_limits.get("max_foreach_iterations")) if c is not None]
	effective_cap = min(caps) if caps else len(items)
	if len(items) > effective_cap:
		return {
			"status": "failed",
			"error": f"foreach '{node_id}' has {len(items)} items, exceeds max_iterations ({effective_cap})",
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
						"error": f"foreach '{node_id}' item {index} failed: {outcome.get('error')}",
					}
				results.append(ctx.resolve(collect_ref) if collect_ref is not None else None)
			finally:
				ctx.pop_foreach()
	finally:
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
			truthy = evaluate_bool(parsed, bindings)
		except Exception as e:
			return {
				"status": "failed",
				"error": f"validate node '{node.get('id')}' assertion expression failed: {e}",
			}
		if not truthy:
			failures.append({"code": assertion["code"], "message": assertion["message"]})

	if failures:
		return {"status": "failed", "error": json.dumps(failures)}
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
			return {"status": "failed", "error": str(exc)}
	elif isinstance(value, dict):
		size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
		if size > budget.max_bytes:
			return {
				"status": "failed",
				"error": f"output node '{node.get('id')}' value is {size} bytes, exceeds max_output_bytes ({budget.max_bytes}); refusing to truncate",
			}
		for key, field_value in value.items():
			if isinstance(field_value, list) and len(field_value) > budget.max_rows:
				return {
					"status": "failed",
					"error": f"output node '{node.get('id')}' field '{key}' has {len(field_value)} rows, exceeds max_rows ({budget.max_rows}); refusing to truncate",
				}

	return {"status": "success", "output": value, "result": value}


# ---------------------------------------------------------------------------
# Per-key flow state (state.get / state.set / state.delete)
# ---------------------------------------------------------------------------


def _state_node(flow_run, node: dict, config: dict, settings: dict, allowed: set, op):
	"""Shared shell: validate config keys, resolve inputs, scope to the *running* flow."""
	unknown = sorted(set(config) - allowed)
	if unknown:
		return {"status": "failed", "error": f"{node.get('type')}: unsupported config {unknown}"}
	flow_id = getattr(flow_run, "flow_id", None)
	ctx = _context_of(flow_run, settings)
	resolved = {k: ctx.resolve(v) for k, v in config.items()}
	try:
		output = op(flow_id, resolved)
	except flow_state.FlowStateError as exc:
		return {"status": "failed", "error": f"{node.get('type')}: {exc}"}
	return {"status": "success", "result": output, "output": output}


def _exec_state_get(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.get``: config ``key`` (required), ``default``. Output ``{"found": bool, "value": ...}``."""

	def op(flow_id, cfg):
		found, value = flow_state.get_state(flow_id, cfg.get("key"))
		return {"found": found, "value": value if found else cfg.get("default")}

	return _state_node(flow_run, node, config, settings, {"key", "default"}, op)


def _exec_state_set(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.set``: config ``key``, ``value``, ``ttl_seconds`` (default 24h). Output ``{"stored": true}``."""

	def op(flow_id, cfg):
		flow_state.set_state(flow_id, cfg.get("key"), cfg.get("value"), cfg.get("ttl_seconds"))
		return {"stored": True}

	return _state_node(flow_run, node, config, settings, {"key", "value", "ttl_seconds"}, op)


def _exec_state_delete(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.delete``: config ``key``. Output ``{"deleted": bool}``."""

	def op(flow_id, cfg):
		return {"deleted": flow_state.delete_state(flow_id, cfg.get("key"))}

	return _state_node(flow_run, node, config, settings, {"key"}, op)


# ---------------------------------------------------------------------------
# doc.create -- insert an allow-listed document as the run's user
# ---------------------------------------------------------------------------

_WRITES_KEY = "_doc_create_count"


def _exec_doc_create(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""
	``doc.create``: config ``doctype`` (literal) and ``fields`` (object of values / references).
	Output ``{"doctype", "name"}`` so later nodes can use ``{"$from": "<node>.name"}``.

	Policy lives in :mod:`huf.ai.flow.create_doc` (allow-list, field validation, no
	``ignore_permissions``). Each created document also counts against the graph contract's
	``limits.max_writes`` for the run (absent or 0 means no writes are allowed).
	"""
	unknown = sorted(set(config) - {"doctype", "fields"})
	if unknown or "doctype" not in config or "fields" not in config:
		return {"status": "failed", "error": "doc.create requires exactly doctype and fields (got unsupported keys: %s)" % unknown}
	ctx = _context_of(flow_run, settings)
	run_ctx = _run_context(settings)
	limits = ((run_ctx.definition.get("contract") or {}).get("limits") or {}) if run_ctx is not None else {}
	max_writes = limits.get("max_writes") or 0
	envelope = ((run_ctx.definition.get("contract") or {}).get("permission_envelope") or {}) if run_ctx is not None else {}
	doctype = config["doctype"]
	try:  # the site allow-list first: its message is the clearer one for an unsupported doctype
		flow_create_doc.check_doctype(doctype, flow_create_doc.allowed_doctypes(frappe.conf))
	except flow_create_doc.CreateDocError as exc:
		return {"status": "failed", "error": f"doc.create: {exc}"}
	if not isinstance(doctype, str) or not envelope_declares(envelope, ptype="create", doctype=doctype):
		return {"status": "failed", "error": f"doc.create: contract permission_envelope.write does not grant {doctype!r}"}
	done = ctx.data.get(_WRITES_KEY) or 0
	if done >= max_writes:
		return {"status": "failed", "error": f"doc.create exceeds contract limits.max_writes ({max_writes})"}
	try:
		result = flow_create_doc.create_document(config["doctype"], ctx.resolve(config["fields"]))
	except flow_create_doc.CreateDocError as exc:
		return {"status": "failed", "error": f"doc.create: {exc}"}
	except frappe.PermissionError as exc:
		return {"status": "failed", "error": f"doc.create: permission denied ({exc})"}
	ctx.set(_WRITES_KEY, done + 1)
	return {"status": "success", "result": result, "output": result}


_NODE_EXECUTORS = {
	"trigger.webhook": _exec_trigger_webhook,
	"trigger.schedule": _exec_trigger_schedule,
	"trigger.unset": _exec_trigger_unset,
	"trigger.doc-event": _exec_trigger_doc_event,
	"agent.run": _exec_agent_run,
	"tool.call": _exec_tool_call,
	"router.llm": _exec_router_llm,
	"router.decision": _exec_router_decision,
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


def edges_from_nodes(nodes: list) -> list[dict]:
	"""Decode the graph IR's node-native routing pointers into ``{from, to, type, meta}`` edges.

	``next`` and ``on_error`` apply to every node; the self-routing types carry their targets in
	``config``: ``condition.on_true`` / ``on_false``, ``router.llm`` / ``router.decision``
	``options[].node_id`` / ``default``, ``human.approval.approve_next`` / ``reject_next`` /
	``timeout_next``. ``foreach.body`` is not an edge: the body is run inline by the loop and
	``next`` is the loop's done edge. The edge list is what the router
	and the approval flow route over.
	"""
	edges: list[dict] = []
	for node in nodes:
		if not isinstance(node, dict):
			continue
		node_id = node.get("id")
		node_type = node.get("type")
		config = node.get("config") or {}

		if node_type == "condition":
			if config.get("on_true"):
				edges.append({"from": node_id, "to": config["on_true"], "type": "always", "meta": {"label": "true"}})
			if config.get("on_false"):
				edges.append({"from": node_id, "to": config["on_false"], "type": "always", "meta": {"label": "false"}})
		elif node_type in ("router.llm", "router.decision"):
			for option in config.get("options") or []:
				to = (option or {}).get("node_id")
				if to:
					edges.append({"from": node_id, "to": to, "type": "always", "meta": {"label": (option or {}).get("label")}})
			default = config.get("default")
			if default:
				edges.append({"from": node_id, "to": default, "type": "always", "meta": {"label": "default"}})
		elif node_type == "human.approval":
			if config.get("approve_next"):
				edges.append(
					{"from": node_id, "to": config["approve_next"], "type": "outcome", "meta": {"outcome": "approved"}}
				)
			if config.get("reject_next"):
				edges.append(
					{"from": node_id, "to": config["reject_next"], "type": "outcome", "meta": {"outcome": "rejected"}}
				)
			if config.get("timeout_next"):
				edges.append(
					{"from": node_id, "to": config["timeout_next"], "type": "outcome", "meta": {"outcome": "timeout"}}
				)
		else:
			next_id = node.get("next")
			if next_id:
				edges.append({"from": node_id, "to": next_id, "type": "always"})

		on_error = node.get("on_error")
		if on_error:
			edges.append({"from": node_id, "to": on_error, "type": "on_failure"})

	return edges


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
# Approval notifications
# ---------------------------------------------------------------------------


def _send_approval_notifications(flow_run, node: dict, config: dict, waiting_data: dict):
	"""
	Send notification to approvers when a flow reaches human.approval node.
	
	Supports two notification methods:
	1. Frappe Notification Log (bell icon in UI)
	2. Email notification (if email is configured)
	
	Args:
		flow_run: The Flow Run document
		node: The current node dict
		config: Node configuration
		waiting_data: The waiting state data
	"""
	approver_type = waiting_data.get("approver_type")
	approvers = []

	# Same rule as check_approver: no declared approver means System Manager only.
	if approver_type == "role" and waiting_data.get("approver_role"):
		approver_role = waiting_data.get("approver_role")
	elif approver_type == "user" and waiting_data.get("approver_users"):
		approver_role = None
	else:
		approver_type, approver_role = "role", "System Manager"

	if approver_type == "role":
		if approver_role:
			# Optimized role lookup: Get all users with this role directly from Has Role table
			approver_names = frappe.get_all(
				"Has Role",
				filters={"role": approver_role, "parenttype": "User"},
				pluck="parent"
			)
			if approver_names:
				# Filter to ensure we only notify enabled System Users
				approvers = frappe.get_all(
					"User",
					filters={
						"name": ["in", approver_names],
						"enabled": 1,
						"user_type": "System User",
					},
					pluck="name"
				)
	elif approver_type == "user":
		approvers = list(waiting_data.get("approver_users") or [])
	
	# Ensure unique recipients to avoid duplicate emails
	if approvers:
		approvers = list(set(approvers))
	
	if not approvers:
		frappe.log_error(
			title="Flow Approval Notification",
			message=f"No approvers found for flow run {flow_run.name}",
		)
		return
	
	title = "Approval Required"
	instructions = waiting_data.get("message") or "Please review and approve this flow."
	
	flow_run_path = f"/huf/flows/{flow_run.flow_id}?run={flow_run.name}"
	
	_host = (frappe.conf.get("host_name") or frappe.utils.get_url()).rstrip("/")
	flow_run_url = f"{_host}{flow_run_path}"

	
	# Create notification for each approver
	for user in approvers:
		try:
			# Get user email for notification (enqueue_create_notification expects emails)
			user_email = frappe.db.get_value("User", user, "email") or user
			
			# 1. Create Frappe Notification Log (appears in bell icon)
			enqueue_create_notification(user_email, {
				"type": "Assignment",
				"document_type": "Flow Run",
				"document_name": flow_run.name,
				"subject": _("Approval Required: {0}").format(title),
				"email_content": f"""
					<p>{instructions}</p>
					<p><strong>{_("Flow")}:</strong> {flow_run.flow_id}</p>
					<p><strong>{_("Run ID")}:</strong> {flow_run.name}</p>
					<p><a href="{flow_run_url}">{_("View Flow Run")}</a></p>
				""",
			})
			
			if is_email_notifications_enabled(user):
				user_doc = frappe.get_doc("User", user)
				if user_doc.email:
					frappe.sendmail(
						recipients=[user_doc.email],
						subject=_("[HUF] Approval Required: {0}").format(title),
						message=f"""
							<p>{_("Dear")} {user_doc.full_name or user},</p>
							<p>{_("A flow is waiting for your approval.")}</p>
							<hr>
							<p><strong>{_("Flow")}:</strong> {flow_run.flow_id}</p>
							<p><strong>{_("Run ID")}:</strong> {flow_run.name}</p>
							<p><strong>{_("Instructions")}:</strong></p>
							<p>{instructions}</p>
							<hr>
							<p>
								<a href="{flow_run_url}" 
								   style="background-color: #171717; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
									{_("Review Approval")}
								</a>
							</p>
							<p style="color: #666; font-size: 12px;">
								{_("This is an automated message from the HUF Flow Engine.")}
							</p>
						""",
						delayed=True,
					)
		except Exception as e:
			# Log error but don't fail the flow
			frappe.log_error(
				title=_("Flow Approval Notification"),
				message=f"Failed to send approval notification to {user}: {str(e)}",
			)


def _clear_flow_notifications(flow_run):
	"""
	Mark all notifications for a specific flow run as read.
	Called when a human decision is made.
	"""
	try:
		# Standard Frappe approach: find notification log entries for this document
		# and mark them as read for all users who were notified.
		frappe.db.set_value(
			"Notification Log",
			{
				"document_type": "Flow Run",
				"document_name": flow_run.name,
				"read": 0
			},
			"read",
			1,
			update_modified=False
		)
		commit_if_background()
	except Exception:
		# Cleanup is best-effort
		pass


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
	# Flow conversations are created by the engine. Authenticated callers
	# use standard permissions; Guest/webhook triggers rely on the system.
	if frappe.session.user == "Guest":
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


def _complete_flow_run(flow_run, reply_text: str | None = None):
	"""Mark a flow run as successfully completed."""
	flow_run.db_set({"status": "Success", "completed_at": now_datetime()})
	commit_if_background()
	_sync_gateway_event(flow_run, "Success", reply_text)


def _fail_flow_run(flow_run, error_msg: str):
	"""Mark a flow run as failed."""
	flow_run.db_set({"status": "Failed", "last_error": error_msg, "completed_at": now_datetime()})
	commit_if_background()
	_sync_gateway_event(flow_run, "Failed", error=error_msg)
	_publish_flow_event(flow_run, "flow_failed", {"error": error_msg})
	flow_hooks.notify_failure(flow_run.name)


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
