"""Shared graph execution core for the Procedure and Flow profiles.

This module is the T-22 seam: one executor, two runtimes. ``FlowRuntime``
(``huf/ai/flow_engine.py``) and ``ProcedureRuntime`` (T-23) are adapters over
``GraphExecutor``; the executor itself knows nothing about Flow Run documents,
Frappe, or persistence.

Frappe-free by design (see ``huf/ai/graph/__init__.py``): nothing here may
import ``frappe``. Persistence is opt-in through the :class:`StateStore`
protocol -- the default :class:`InMemoryStateStore` is what gives a Procedure
its low-overhead synchronous path, while ``FlowRuntime`` supplies a store that
writes through to its ``Flow Run`` document.

What this module owns, and which defect each part repairs:

* :func:`fingerprint` / :class:`PinnedVersion` -- immutable, content-addressed
  version identity (spec section 7, defect F-1). A run pins a fingerprint and
  keeps the exact graph it started with; there is no "current definition" to
  re-fetch mid-run.
* :class:`GraphContext` -- the run-scoped context object, parsed once and
  passed through (defect F-9, structural knot 1). It also owns the *single*
  reference mechanism, ``{"$from": "node_id.path"}`` (defect F-2).
* :class:`Outcome` -- a typed node result carrying pause as a value rather
  than a status string another layer has to re-read from storage (knot 2).
* :class:`Router` -- one next-node resolution path for every node type,
  including outcome-labelled routing such as approve/reject (knots 3 and 4).
* :class:`GraphExecutor` -- the loop: hop budget, foreach budget (defect F-3),
  terminal detection, and a single-writer guard (defect F-4).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
	"ExecutionPolicy",
	"ExecutionResult",
	"ExecutionState",
	"GraphContext",
	"GraphExecutor",
	"GraphProgram",
	"InMemoryStateStore",
	"NodeSpec",
	"Outcome",
	"PauseRequest",
	"PinnedVersion",
	"RoutingError",
	"RoutingMode",
	"StateStore",
	"canonical_json",
	"fingerprint",
]


# ---------------------------------------------------------------------------
# Version identity (spec section 7 / F-1)
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
	"""Deterministic serialization used for content addressing.

	Object keys sorted at every level, no insignificant whitespace, UTF-8.
	Equivalent in effect to RFC 8785 for the JSON subset a graph can contain
	(the spec explicitly leaves the canonicalizer an implementation choice,
	provided it is deterministic and applied identically everywhere).
	"""
	return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def fingerprint(graph: Mapping[str, Any]) -> str:
	"""sha256 hex digest over the canonical form of ``graph``.

	The ``fingerprint`` key itself is removed first -- it cannot be
	self-referential. Two graphs with the same content always produce the
	same digest, and any edit at all produces a different one. This replaces
	``flow_definition.py``'s integer ``version`` bump, which carried no
	content identity and therefore could not pin anything (F-1).
	"""
	body = {k: v for k, v in dict(graph).items() if k != "fingerprint"}
	return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PinnedVersion:
	"""An immutable (graph, fingerprint) pair, as pinned by a run.

	Once created, the graph it holds is the graph that run executes -- for
	its whole life, including after a pause and resume, and regardless of
	what the definition record says by then.
	"""

	graph: dict
	fingerprint: str

	@classmethod
	def pin(cls, graph: Mapping[str, Any]) -> PinnedVersion:
		snapshot = json.loads(canonical_json(graph))
		return cls(graph=snapshot, fingerprint=fingerprint(snapshot))

	def matches(self, other_graph: Mapping[str, Any]) -> bool:
		"""True when ``other_graph`` is byte-for-byte the pinned content."""
		return fingerprint(other_graph) == self.fingerprint

	def to_json(self) -> str:
		return canonical_json({"fingerprint": self.fingerprint, "graph": self.graph})

	@classmethod
	def from_json(cls, raw: str | None) -> PinnedVersion | None:
		if not raw:
			return None
		try:
			data = json.loads(raw) if isinstance(raw, str) else raw
		except (json.JSONDecodeError, TypeError):
			return None
		if not isinstance(data, dict) or not isinstance(data.get("graph"), dict):
			return None
		return cls(graph=data["graph"], fingerprint=data.get("fingerprint") or fingerprint(data["graph"]))


# ---------------------------------------------------------------------------
# Context (F-9, knot 1, F-2)
# ---------------------------------------------------------------------------



def resolve_path(root: Any, path: str) -> Any:
	"""Resolve a dotted/indexed path. Missing keys resolve to ``None``.

	Grammar per spec section 4.1: ``segment := "." identifier | "[" int "]"``.
	Nothing here ever raises -- an unknown key, an index past the end, or a
	path that walks through a scalar all resolve to ``None``.
	"""
	current = root
	for segment in _split_path(path):
		if isinstance(segment, int):
			if isinstance(current, (list, tuple)) and -len(current) <= segment < len(current):
				current = current[segment]
			else:
				return None
		elif isinstance(current, Mapping):
			current = current.get(segment)
		else:
			return None
	return current


def _split_path(path: str) -> list[str | int]:
	segments: list[str | int] = []
	buffer = ""
	index = 0
	while index < len(path):
		char = path[index]
		if char == ".":
			if buffer:
				segments.append(buffer)
				buffer = ""
		elif char == "[":
			if buffer:
				segments.append(buffer)
				buffer = ""
			close = path.find("]", index)
			if close == -1:
				return segments
			raw = path[index + 1 : close].strip()
			try:
				segments.append(int(raw))
			except ValueError:
				segments.append(raw.strip("'\""))
			index = close
		else:
			buffer += char
		index += 1
	if buffer:
		segments.append(buffer)
	return segments


class GraphContext:
	"""Run-scoped state, built once and threaded through every node.

	Before T-22 the Flow context was re-parsed out of ``flow_run.context_json``
	at roughly fifteen call sites, and every executor reached into the
	``Flow Run`` Document for ``mode``/``conversation``/``flow_id`` as well
	(F-9, knot 1). This object is the replacement: parse once, mutate in
	memory, and let the runtime's :class:`StateStore` decide when a snapshot
	is written back.
	"""

	def __init__(
		self,
		data: Mapping[str, Any] | None = None,
		*,
		run_id: str | None = None,
		mode: str = "normal",
		metadata: Mapping[str, Any] | None = None,
	):
		self.data: dict = dict(data or {})
		self.run_id = run_id
		self.mode = (mode or "normal").lower()
		self.metadata: dict = dict(metadata or {})
		self.node_outputs: dict = {}
		self.foreach_frames: list[dict] = []
		self.dirty = False

	# -- construction -----------------------------------------------------

	@classmethod
	def from_json(cls, raw: Any, **kwargs) -> GraphContext:
		"""Parse a stored context blob once. Malformed input yields an empty
		context rather than raising -- the surrounding run is still valid.
		"""
		if not raw:
			return cls({}, **kwargs)
		try:
			parsed = json.loads(raw) if isinstance(raw, str) else raw
		except (json.JSONDecodeError, TypeError):
			return cls({}, **kwargs)
		return cls(parsed if isinstance(parsed, dict) else {}, **kwargs)

	# -- reads ------------------------------------------------------------

	def get(self, path: str, default: Any = None) -> Any:
		value = resolve_path(self.data, path)
		return default if value is None else value

	def as_dict(self) -> dict:
		return self.data

	def to_json(self) -> str:
		return json.dumps(self.data, default=str)

	# -- writes -----------------------------------------------------------

	def set(self, key: str, value: Any) -> None:
		self.data[key] = value
		self.dirty = True

	def update(self, values: Mapping[str, Any]) -> None:
		if not values:
			return
		self.data.update(values)
		self.dirty = True

	def pop(self, key: str, default: Any = None) -> Any:
		self.dirty = True
		return self.data.pop(key, default)

	def record_output(self, node_id: str, output: Any) -> None:
		"""Record a node's output so ``{"$from": "<node_id>.<path>"}`` can
		reach it. Node outputs are addressed by node id, never merged into
		the flat context namespace.
		"""
		self.node_outputs[node_id] = output

	# -- the single reference mechanism (F-2) -----------------------------

	def reference_roots(self) -> dict:
		roots: dict = {
			"input": self.data,
			"trigger": self.data.get("trigger"),
			"context": self.data,
		}
		roots.update(self.node_outputs)
		if self.foreach_frames:
			roots["foreach"] = self.foreach_frames[-1]
		return roots

	def resolve_reference(self, expr: str) -> Any:
		"""Resolve one ``<root>.<path>`` reference expression."""
		roots = self.reference_roots()
		segments = _split_path(expr)
		if not segments:
			return None
		head = segments[0]
		if head == "foreach" and len(segments) > 1:

			base = roots.get("foreach") or {}
			value = base.get(str(segments[1])) if isinstance(base, Mapping) else None
			rest = segments[2:]
		elif head in roots:
			value = roots[head]
			rest = segments[1:]
		else:
			# An unqualified path falls back to the flat context namespace,
			# which is what a Flow-profile graph's own keys live in.
			value = self.data
			rest = segments
		for segment in rest:
			if isinstance(segment, int):
				if isinstance(value, (list, tuple)) and -len(value) <= segment < len(value):
					value = value[segment]
				else:
					return None
			elif isinstance(value, Mapping):
				value = value.get(segment)
			else:
				return None
		return value

	def resolve(self, value: Any) -> Any:
		"""Recursively resolve ``{"$from": ...}`` references in a config value.

		This is the *only* way a node config pulls a value from elsewhere in
		the graph. The four divergent ``{{...}}`` string-interpolation
		implementations this replaces are described in GT-04; nothing here
		does string templating.
		"""
		if isinstance(value, Mapping):
			if set(value.keys()) == {"$from"} and isinstance(value["$from"], str):
				return self.resolve_reference(value["$from"])
			return {key: self.resolve(item) for key, item in value.items()}
		if isinstance(value, list):
			return [self.resolve(item) for item in value]
		return value

	# -- foreach frames (F-3) --------------------------------------------

	def push_foreach(self, item: Any, index: int) -> None:
		self.foreach_frames.append({"item": item, "index": index})

	def pop_foreach(self) -> None:
		if self.foreach_frames:
			self.foreach_frames.pop()


# ---------------------------------------------------------------------------
# Node outcomes (knot 2)
# ---------------------------------------------------------------------------


@dataclass
class PauseRequest:
	"""Why and how a node paused, carried in the outcome itself.

	Before T-22 a pause was discovered by reloading the ``Flow Run`` document
	and comparing its status string to two literals (knot 2). A node now
	*returns* the fact that it paused, together with where to continue when
	it is released -- so resuming never has to re-execute the node that
	paused, and never has to re-read the definition to find out what it was.
	"""

	kind: str = "user"
	payload: dict = field(default_factory=dict)
	resume_node: str | None = None
	status_label: str | None = None


@dataclass
class Outcome:
	"""A typed node result."""

	status: str = "success"
	output: Any = None
	error: str | None = None
	next_node_id: str | None = None
	pause: PauseRequest | None = None
	label: str | None = None
	extra: dict = field(default_factory=dict)

	@classmethod
	def succeeded(cls, output: Any = None, **kwargs) -> Outcome:
		return cls(status="success", output=output, **kwargs)

	@classmethod
	def failed(cls, error: str, **kwargs) -> Outcome:
		return cls(status="failed", error=error, **kwargs)

	@classmethod
	def paused(cls, pause: PauseRequest, **kwargs) -> Outcome:
		return cls(status="paused", pause=pause, **kwargs)

	@property
	def is_paused(self) -> bool:
		return self.status == "paused"

	@property
	def is_success(self) -> bool:
		return self.status == "success"

	@classmethod
	def from_mapping(cls, data: Any) -> Outcome:
		"""Adapt a plain dict result (the shape Flow's node executors return
		and the shape T-01's tests assert on) into a typed outcome.
		"""
		if isinstance(data, Outcome):
			return data
		if not isinstance(data, Mapping):
			return cls.succeeded(output=data)
		status = data.get("status", "success")
		pause = None
		if status in ("waiting_approval", "waiting_user"):
			pause = PauseRequest(kind="approval" if status == "waiting_approval" else "user")
			status = "paused"
		return cls(
			status=status,
			output=data.get("output", data.get("result")),
			error=data.get("error"),
			next_node_id=data.get("next_node_id"),
			pause=pause,
			label=data.get("branch"),
			extra=dict(data),
		)


# ---------------------------------------------------------------------------
# Program: the pinned graph plus its routing spec (knot 3)
# ---------------------------------------------------------------------------


class RoutingMode:
	"""How a node's successor is determined.

	One enum, consulted in one place. The pre-T-22 engine decided this in two
	places that had drifted apart -- a dispatch table in ``_execute_node`` and
	a type-switch inside ``_execute_loop`` -- plus a third, entirely separate
	inline implementation in ``approve_flow_run`` (knots 3 and 4).
	"""

	DEFAULT = "default"
	"""Ask the graph's edge/pointer resolution for the successor."""

	SELF_ROUTED = "self_routed"
	"""The node's own outcome names the successor and MUST name one."""

	SELF_ROUTED_OPTIONAL = "self_routed_optional"
	"""The node's own outcome names the successor; naming none ends the run."""

	TERMINAL = "terminal"
	"""The node ends the run successfully."""


class RoutingError(Exception):
	"""A node that was required to resolve a successor did not."""


@dataclass
class NodeSpec:
	"""A node plus the executor-visible facts about how it routes."""

	id: str
	type: str
	config: dict = field(default_factory=dict)
	routing: str = RoutingMode.DEFAULT
	raw: dict = field(default_factory=dict)
	loop_body: str | None = None
	"""For a bounded ``foreach``/``loop`` node: the id of its body chain."""


class GraphProgram:
	"""A pinned graph, indexed for execution.

	Construction is where a profile's own graph shape is normalized into the
	executor's vocabulary, so the executor itself has no per-profile branches.
	"""

	def __init__(
		self,
		version: PinnedVersion,
		nodes: Mapping[str, NodeSpec],
		entry: str | None,
		*,
		settings: Mapping[str, Any] | None = None,
	):
		self.version = version
		self.nodes = dict(nodes)
		self.entry = entry
		self.settings = dict(settings or {})

	@property
	def fingerprint(self) -> str:
		return self.version.fingerprint

	@property
	def graph(self) -> dict:
		return self.version.graph

	def node(self, node_id: str | None) -> NodeSpec | None:
		if not node_id:
			return None
		return self.nodes.get(node_id)

	def __contains__(self, node_id: object) -> bool:
		return node_id in self.nodes

	def __iter__(self) -> Iterable[NodeSpec]:
		return iter(self.nodes.values())


class Router:
	"""The one next-node resolution path.

	``resolve`` covers every routing mode, and ``resolve_labelled`` covers
	outcome-labelled routing (approve/reject and anything shaped like it) --
	which is what folds ``approve_flow_run``'s third inline implementation
	into this one (knot 4).
	"""

	def __init__(
		self,
		program: GraphProgram,
		*,
		default_resolver: Callable[[NodeSpec, Outcome, GraphContext], str | None] | None = None,
		labelled_resolver: Callable[[str, str], str | None] | None = None,
	):
		self.program = program
		self._default_resolver = default_resolver
		self._labelled_resolver = labelled_resolver

	def resolve(self, node: NodeSpec, outcome: Outcome, context: GraphContext) -> str | None:
		mode = node.routing
		if mode == RoutingMode.TERMINAL:
			return None
		if mode in (RoutingMode.SELF_ROUTED, RoutingMode.SELF_ROUTED_OPTIONAL):
			next_id = outcome.next_node_id
			if not next_id and mode == RoutingMode.SELF_ROUTED:
				raise RoutingError(f"Node '{node.id}' of type '{node.type}' did not resolve a successor")
			return next_id
		if self._default_resolver is None:
			# Fail closed by default (I7). Without this, a caller that supplies no resolver would
			# follow a FAILED node's ``next`` pointer exactly as if it had succeeded, so `validate`
			# would not be a gate at all. Callers wanting different failure semantics -- Flow routes
			# on_failure edges, for instance -- supply their own resolver.
			if outcome.status == "failed":
				on_error = node.raw.get("on_error")
				if on_error:
					return on_error
				raise RoutingError(
					f"Node '{node.id}' of type '{node.type}' failed and declares no on_error successor"
				)
			return node.raw.get("next")
		return self._default_resolver(node, outcome, context)

	def resolve_labelled(self, node_id: str, label: str) -> str | None:
		"""Resolve a successor by outcome label (for example ``"approved"``)."""
		if self._labelled_resolver is None:
			return None
		return self._labelled_resolver(node_id, label)


# ---------------------------------------------------------------------------
# Policy, state, persistence
# ---------------------------------------------------------------------------


DEFAULT_MAX_HOPS = 100
DEFAULT_MAX_FOREACH_ITERATIONS = 1000
DEFAULT_MAX_FOREACH_STEPS = 100_000


@dataclass
class ExecutionPolicy:
	"""Resource ceilings. Fail closed (I7).

	``max_hops`` and ``max_foreach_iterations`` are deliberately *separate*
	budgets. Under the pre-T-22 engine a loop burned one hop per iteration
	against the same 100-hop ceiling that bounded the whole run, so a
	150-item loop could not finish (GT-11 / F-3). A bounded foreach now
	carries its own iteration budget and never touches the hop budget.
	"""

	max_hops: int = DEFAULT_MAX_HOPS
	max_foreach_iterations: int = DEFAULT_MAX_FOREACH_ITERATIONS
	max_foreach_steps: int = DEFAULT_MAX_FOREACH_STEPS
	fail_closed: bool = True

	@classmethod
	def from_settings(cls, settings: Mapping[str, Any] | None, **overrides) -> ExecutionPolicy:
		settings = settings or {}
		values = {
			"max_hops": settings.get("max_hops") or DEFAULT_MAX_HOPS,
			"max_foreach_iterations": settings.get("max_foreach_iterations")
			or DEFAULT_MAX_FOREACH_ITERATIONS,
		}
		values.update({k: v for k, v in overrides.items() if v is not None})
		return cls(**values)


@dataclass
class ExecutionState:
	"""Where a run is. Held in memory; persisted only if a store says so."""

	cursor: str | None = None
	hop_count: int = 0
	status: str = "running"
	completed_nodes: list = field(default_factory=list)
	foreach_active: str | None = None
	foreach_iterations: dict = field(default_factory=dict)
	foreach_steps: int = 0
	error: str | None = None


class StateStore(Protocol):
	"""Persistence seam. The executor calls these; what they do is the
	runtime's business. ``ProcedureRuntime`` uses the in-memory default and
	therefore never touches a database on its hot path.
	"""

	def save_cursor(self, cursor: str) -> None: ...

	def save_hops(self, hop_count: int) -> None: ...


class InMemoryStateStore:
	"""Default store: keeps nothing beyond the in-memory state object."""

	def save_cursor(self, cursor: str) -> None:
		return None

	def save_hops(self, hop_count: int) -> None:
		return None


class ExecutionListener(Protocol):
	"""Observability seam (realtime events, step records)."""

	def node_start(self, node: NodeSpec) -> None: ...

	def node_end(self, node: NodeSpec, outcome: Outcome) -> None: ...


class NullListener:
	def node_start(self, node: NodeSpec) -> None:
		return None

	def node_end(self, node: NodeSpec, outcome: Outcome) -> None:
		return None


@dataclass
class ExecutionResult:
	"""Terminal (or paused) result of driving a graph."""

	status: str
	error: str | None = None
	node_id: str | None = None
	hop_count: int = 0
	completed_nodes: list = field(default_factory=list)
	pause: PauseRequest | None = None

	SUCCESS = "success"
	FAILED = "failed"
	PAUSED = "paused"
	REFUSED = "refused"


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------


NodeHandler = Callable[[NodeSpec, GraphContext, ExecutionState], Any]


class GraphExecutor:
	"""Drives a pinned graph to completion, a pause, or a bounded failure.

	The executor never reaches for the "current" definition: it holds a
	:class:`GraphProgram` built from a :class:`PinnedVersion`, so an edit to
	the definition record while this run is in flight cannot change what this
	run executes (F-1).
	"""

	RUNNABLE_STATUSES = ("running", "queued", "pending")

	def __init__(
		self,
		program: GraphProgram,
		handlers: Mapping[str, NodeHandler],
		*,
		router: Router | None = None,
		policy: ExecutionPolicy | None = None,
		store: StateStore | None = None,
		listener: ExecutionListener | None = None,
	):
		self.program = program
		self.handlers = dict(handlers)
		self.router = router or Router(program)
		self.policy = policy or ExecutionPolicy()
		self.store = store or InMemoryStateStore()
		self.listener = listener or NullListener()

	# -- public seam ------------------------------------------------------

	def execute(self, context: GraphContext, state: ExecutionState | None = None) -> ExecutionResult:
		"""Run from ``state.cursor`` (or the program entry) until done."""
		state = state or ExecutionState(cursor=self.program.entry)
		if state.cursor is None:
			state.cursor = self.program.entry
		return self.run(context, state)

	def resume(self, context: GraphContext, state: ExecutionState) -> ExecutionResult:
		"""Continue a paused run. The caller has already moved the cursor
		past the node that paused -- a pause carries its continuation in the
		outcome (knot 2), so resuming never re-executes it.
		"""
		state.status = "running"
		return self.run(context, state)

	def run(self, context: GraphContext, state: ExecutionState) -> ExecutionResult:
		if state.status not in self.RUNNABLE_STATUSES:
			# Single-writer guard (F-4): a run that has already reached a
			# terminal or waiting state cannot be advanced again, so a second
			# concurrent caller working from a stale cursor cannot re-run a
			# step the first caller already ran.
			return ExecutionResult(
				status=ExecutionResult.REFUSED,
				error=f"Run is not advanceable (status: {state.status})",
				node_id=state.cursor,
				hop_count=state.hop_count,
			)

		while True:
			node = self.program.node(state.cursor)
			if node is None:
				return self._fail(state, f"Node '{state.cursor}' not found in definition")

			charges_hop = self._charges_hop(node, state)
			if charges_hop and state.hop_count >= self.policy.max_hops:
				return self._fail(state, f"Hop limit reached ({self.policy.max_hops})")

			handler = self.handlers.get(node.type)
			if handler is None:
				return self._fail(state, f"Unknown node type: {node.type}")

			self.listener.node_start(node)
			outcome = Outcome.from_mapping(handler(node, context, state))
			self.listener.node_end(node, outcome)

			if outcome.is_paused:
				state.status = "paused"
				return ExecutionResult(
					status=ExecutionResult.PAUSED,
					node_id=node.id,
					hop_count=state.hop_count,
					completed_nodes=list(state.completed_nodes),
					pause=outcome.pause,
				)

			context.record_output(node.id, outcome.output)
			state.completed_nodes.append(node.id)
			self._charge_budget(node, state, charges_hop)

			if node.routing == RoutingMode.TERMINAL:
				return self._complete(state, node.id)

			try:
				next_node_id = self.router.resolve(node, outcome, context)
			except RoutingError as exc:
				return self._fail(state, str(exc))

			self._update_foreach(node, next_node_id, state)

			if not next_node_id:
				return self._complete(state, node.id)

			state.cursor = next_node_id
			self.store.save_cursor(next_node_id)

	# -- budgets (F-3) ----------------------------------------------------

	def _charges_hop(self, node: NodeSpec, state: ExecutionState) -> bool:
		"""Iterating a bounded foreach does not consume the run's hop budget.

		A node charges a hop only when no foreach is currently iterating. The
		loop node's own first visit does charge one (it is a step of the main
		chain); every visit after that belongs to the iteration budget.
		"""
		return state.foreach_active is None

	def _charge_budget(self, node: NodeSpec, state: ExecutionState, charges_hop: bool) -> None:
		if charges_hop:
			state.hop_count += 1
			self.store.save_hops(state.hop_count)
		else:
			state.foreach_steps += 1

	def _update_foreach(self, node: NodeSpec, next_node_id: str | None, state: ExecutionState) -> None:
		"""Open or close the current foreach frame, and bound both."""
		if node.loop_body is None:
			return
		if next_node_id and next_node_id == node.loop_body:
			state.foreach_active = node.id
			state.foreach_iterations[node.id] = state.foreach_iterations.get(node.id, 0) + 1
		else:
			state.foreach_active = None

	# -- terminals --------------------------------------------------------

	def _complete(self, state: ExecutionState, node_id: str | None) -> ExecutionResult:
		state.status = "success"
		return ExecutionResult(
			status=ExecutionResult.SUCCESS,
			node_id=node_id,
			hop_count=state.hop_count,
			completed_nodes=list(state.completed_nodes),
		)

	def _fail(self, state: ExecutionState, error: str) -> ExecutionResult:
		state.status = "failed"
		state.error = error
		return ExecutionResult(
			status=ExecutionResult.FAILED,
			error=error,
			node_id=state.cursor,
			hop_count=state.hop_count,
			completed_nodes=list(state.completed_nodes),
		)
