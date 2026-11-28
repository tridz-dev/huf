"""App-registered Flow step types, declared through the ``huf_flow_nodes`` hook.

An installed app adds a step type by listing it in its ``hooks.py`` (a dict, a list of dicts, or a dotted path to
either, like ``huf_tools``)::

	huf_flow_nodes = [{
		"type": "myapp.send_sms",            # "<app>.<name>", must start with the declaring app's name
		"label": "Send SMS", "category": "Actions", "icon": "message-square", "description": "...",
		"config_schema": {"type": "object", "properties": {...}},   # JSON Schema (draft 2020-12) for ``config``
		"handler": "myapp.flow_nodes.send_sms",                      # fn(ctx: NodeCallContext) -> dict | Outcome
		"routing": "next",                   # "next" | "self_routed" | "terminal"
		"outputs": [],                       # branch labels, for self_routed steps
		"can_wait": False,                   # True lets the handler call ``ctx.park(...)``
		"test_simulate": "skip",             # "skip" (default) | "run" | dotted path to fn(ctx) used in test runs
		"validate": "myapp.flow_nodes.check",  # optional: fn(node: dict) -> list[str] of problems, run on publish
	}]

Trust boundary. A step type is trusted exactly as far as the app that declares it, because the handler runs in
the Flow worker with the run user's permissions and Python's full power. Nothing the flow author controls ever
names code: a Flow Definition stores only the type id, and the id is resolved here against hook declarations
(``frappe.get_hooks``, i.e. apps installed on this site). The dotted handler / validate / test_simulate paths are
read only from those declarations and imported lazily with ``frappe.get_attr``. Ids must be namespaced by the
declaring app and may not collide with a built-in type, so an app cannot shadow or hijack a core step. Entries
that break a rule are skipped and logged, never partially registered. Uninstalling the app removes the type:
pinned flows keep the id, and the step fails at run time with "no longer available".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

import frappe

from huf.ai.flow.nodes import split as split_node
from huf.ai.flow.support import step_keys
from huf.ai.flow.support.pii import log_flow_error
from huf.ai.graph.error_copy import describe_exception, step_failed_sentence
from huf.ai.graph.executor import Outcome, RoutingMode

HOOK = "huf_flow_nodes"
_ROUTING = {
	"next": RoutingMode.DEFAULT,
	"self_routed": RoutingMode.SELF_ROUTED,
	"terminal": RoutingMode.TERMINAL,
}
_TEST_MODES = ("skip", "run")

#: Built-in types the app-scoped (embed) palette may offer (docs/flow/BUILDER_EMBED.md section 3). Generic write paths
#: (``code.run``, ``tool.call``, ``doc.create``, ``doc.update``) stay out; a new built-in is excluded until added here.
EMBED_BUILTIN_TYPES = (
	"trigger.unset", "trigger.schedule", "trigger.doc-event", "trigger.app", "condition", "router.decision", "transform", "foreach",
	"wait", "stop", "output", "human.approval", "member.set", "send.message", "knowledge.search", "split",
	# Member-only in an app flow: see huf/ai/flow/app_scope/targets.py.
	"handoff",
)


@dataclass
class NodeCallContext:
	"""What an app handler receives."""

	config: dict  # the step's settings with ``$from`` / ``$template`` values already resolved
	refs: dict  # the run's reference roots (earlier steps' outputs, trigger, member, ...)
	run_id: str
	member: dict | None
	park: Callable[..., Outcome]  # park(resume_at=None, token=False); only for ``can_wait`` types
	is_resume: bool  # True when the run was woken after this step parked
	waiting: dict | None  # the park record (``woke`` holds the wake reason and payload) when ``is_resume``
	node_id: str = ""  # the step's id in the flow (H-W2-13)
	step_key: str = ""  # idempotency token for this try of this step (H-W2-13, CONTRACTS section 12)
	live: bool = False  # live_send AND NOT dry_run (G3); False in test runs and before live_send is on
	holdout: bool = False  # the run was held out by a split node (H-W2-07, CONTRACTS section 16)


@dataclass(frozen=True)
class NodeType:
	type: str
	app: str
	label: str
	category: str
	icon: str
	description: str
	config_schema: dict
	handler: str
	routing: str
	outputs: list = field(default_factory=list)
	can_wait: bool = False
	test_simulate: str = "skip"
	validate: str | None = None
	profiles: tuple = ("flow",)

	@property
	def routing_mode(self) -> RoutingMode:
		return _ROUTING[self.routing]


def builtin_types() -> frozenset[str]:
	from huf.ai.graph.validator import FLOW_ONLY_NODE_TYPES, PROCEDURE_NODE_TYPES

	return PROCEDURE_NODE_TYPES | FLOW_ONLY_NODE_TYPES


def embed_builtin_types() -> list[str]:
	"""The allow-listed built-ins that exist on this version."""
	existing = builtin_types()
	return [t for t in EMBED_BUILTIN_TYPES if t in existing]


def _entries(value) -> list[dict]:
	"""Flatten one hook value (dict, list, or dotted path to either) into entry dicts."""
	if isinstance(value, str):
		try:
			value = frappe.get_attr(value)
		except (ImportError, AttributeError):
			return []
	if isinstance(value, dict):
		return [value]
	if isinstance(value, (list, tuple)):
		return [entry for item in value for entry in _entries(item)]
	return []


def _normalize(raw: dict, app: str, builtins: frozenset[str]) -> NodeType | None:
	type_id = str(raw.get("type") or "").strip()
	problem = None
	if not type_id.startswith(f"{app}.") or len(type_id) <= len(app) + 1:
		problem = f"the id must start with the declaring app's name ({app}.)"
	elif type_id in builtins:
		problem = "the id collides with a built-in step type"
	elif not isinstance(raw.get("handler"), str) or "." not in raw["handler"]:
		problem = "handler must be a dotted path declared in the hook"
	elif raw.get("routing", "next") not in _ROUTING:
		problem = "routing must be next, self_routed or terminal"
	elif not isinstance(raw.get("config_schema", {}), dict):
		problem = "config_schema must be a JSON Schema object"
	elif raw.get("test_simulate", "skip") not in _TEST_MODES and "." not in str(raw.get("test_simulate")):
		problem = "test_simulate must be skip, run or a dotted path"
	elif "flow" not in (raw.get("profiles") or ["flow"]):
		problem = "only the flow profile is supported"
	if problem:
		log_flow_error(f"{HOOK}: ignored {type_id or raw!r} from {app}: {problem}", "Flow node hook")
		return None
	return NodeType(
		type=type_id,
		app=app,
		label=str(raw.get("label") or type_id),
		category=str(raw.get("category") or "Apps"),
		icon=str(raw.get("icon") or ""),
		description=str(raw.get("description") or ""),
		config_schema=raw.get("config_schema") or {"type": "object"},
		handler=raw["handler"],
		routing=raw.get("routing", "next"),
		outputs=list(raw.get("outputs") or []),
		can_wait=bool(raw.get("can_wait")),
		test_simulate=str(raw.get("test_simulate") or "skip"),
		validate=raw.get("validate") if isinstance(raw.get("validate"), str) else None,
	)


def registered_types() -> dict[str, NodeType]:
	"""``type id -> NodeType`` for every valid declaration by an installed app.

	``frappe.get_hooks`` is itself cached per site and cleared with the hooks cache, so this keeps no cache of
	its own to invalidate: an uninstalled app's types vanish with its hooks.
	"""
	builtins = builtin_types()
	found: dict[str, NodeType] = {}
	for app in frappe.get_installed_apps():
		for raw_hook in frappe.get_hooks(HOOK, app_name=app) or []:
			for raw in _entries(raw_hook):
				node_type = _normalize(raw, app, builtins)
				if node_type and node_type.type not in found:
					found[node_type.type] = node_type
	return found


def get_type(type_id: str | None) -> NodeType | None:
	return registered_types().get(type_id) if type_id else None


def routing_for(type_id: str | None, builtin_routing: dict) -> RoutingMode:
	"""Routing of a step type: built-ins win, then the registry, else the default."""
	if type_id in builtin_routing:
		return builtin_routing[type_id]
	node_type = get_type(type_id)
	return node_type.routing_mode if node_type else RoutingMode.DEFAULT


def can_wait(type_id: str | None) -> bool:
	node_type = get_type(type_id)
	return bool(node_type and node_type.can_wait)


APP_TRIGGER_TYPE = "trigger.app"


def _exec_trigger_app(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""trigger.app: a passthrough for runs its app started (trigger_type "App") and for dry runs; anything else fails."""
	from huf.ai.flow.engine import _context_of
	from huf.ai.flow.testrun import gate as test_gate

	if str(getattr(flow_run, "trigger_type", "") or "") != "App" and not test_gate.is_dry_run(flow_run):
		app = str((config or {}).get("app") or "its app")
		return {"status": "failed", "error": frappe._("This flow is started by {0} only.").format(app)}
	return {"status": "success", "output": _context_of(flow_run, settings).as_dict()}


def executor_for(type_id: str | None):
	"""An engine executor ``(flow_run, node, config, settings) -> dict | Outcome`` for a registered type, else None.
	``trigger.app`` is a built-in served here so the engine needs no branch for it."""
	if type_id == APP_TRIGGER_TYPE:
		return _exec_trigger_app
	node_type = get_type(type_id)
	if node_type is None:
		return None

	def execute(flow_run, node: dict, config: dict, settings: dict):
		from huf.ai.flow.engine import _context_of, _transition_run
		from huf.ai.flow.runs import park
		from huf.ai.flow.testrun import gate as test_gate

		ctx = _context_of(flow_run, settings)
		refs = ctx.reference_roots()
		if test_gate.is_test_run(flow_run) and node_type.test_simulate == "skip":
			return {
				"status": "success",
				"output": {"note": "Test run: this step was skipped."},
				"next_node_id": node.get("next") if node_type.routing == "self_routed" else None,
			}
		waiting = park.is_reentry(flow_run, node) if node_type.can_wait else None
		if waiting:
			_transition_run(flow_run, {"waiting": None}, from_statuses=("Running",))

		def park_step(resume_at=None, token=False):
			if not node_type.can_wait:
				frappe.throw(f"{node_type.type} did not declare can_wait.")
			return park.park_run(
				flow_run,
				node,
				park.ParkRequest(
					reason="app", resume_at=resume_at, token=token, member_key=getattr(flow_run, "member_key", None)
				),
			)

		call = NodeCallContext(
			config=ctx.resolve(config),
			refs=refs,
			run_id=flow_run.name,
			member=refs.get("member"),
			park=park_step,
			is_resume=bool(waiting),
			waiting=waiting,
			live=test_gate.is_live(flow_run),
			holdout=split_node.is_holdout(ctx.data),
			node_id=node.get("id") or "",
			step_key=step_keys.key_of(node),
		)
		path = node_type.handler
		if test_gate.is_test_run(flow_run) and node_type.test_simulate not in _TEST_MODES:
			path = node_type.test_simulate
		try:
			result = frappe.get_attr(path)(call)
		except Exception as exc:  # the app's code failed: fail this step, never the worker
			log_flow_error(frappe.get_traceback(), f"Flow app step {node_type.type} raised")
			return {"status": "failed", "error": step_failed_sentence(node_type.label, describe_exception(exc))}
		if isinstance(result, (dict, Outcome)):
			return result
		return {"status": "success", "output": result}

	return execute


def validate_node_config(node: dict) -> list[str]:
	"""Problems the type's own ``validate`` hook reports for ``node`` (publish only). Never raises."""
	node_type = get_type(node.get("type"))
	if not node_type or not node_type.validate:
		return []
	try:
		problems = frappe.get_attr(node_type.validate)(node) or []
	except Exception as exc:
		return [f"{node_type.label} could not be checked: {exc}"]
	return [str(p) for p in problems]


def is_app_type_id(type_id: str | None) -> bool:
	"""True for an id shaped like an app step type (``<app>.<name>``) that is not a built-in."""
	return bool(type_id) and "." in type_id and type_id not in builtin_types()
