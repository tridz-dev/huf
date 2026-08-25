# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Flow -> Procedure conversion (T-52).

*Flow is what you draw, Procedure is what it compiles to -- the same picture at two
stages.* Flow and Procedure already share one IR (spec/graph-ir.md) and one executor
(``huf.ai.graph.executor``); this module is the bridge that turns a deterministic Flow
Definition's graph into an Agent Procedure graph.

This is a **conversion**, not the trace-mining compiler described in GOAL.md Phase 4 --
compiling a Procedure from *observed* Agent Run trajectories stays explicitly out of
scope (PLAN.md 9). The only input here is a Flow's own authored graph.

Frappe-free by design (mirrors ``huf.ai.graph.transforms`` / ``expressions.py`` / the
frappe-free half of ``permissions.py``): everything in this module is pure functions
over plain dicts, so the conversion and refusal logic can be unit tested with plain
``pytest``, no bench required. The whitelisted API wrapper (``huf.ai.flow_api``) is the
only layer that touches ``frappe``.

Two-step contract:

1. :func:`analyze_conversion` -- read-only. Tells you whether a Flow graph is
   convertible, and if not, exactly why (I8-adjacent: never guess, never partially
   convert). If convertible, also returns the compiled Procedure graph and a
   human-facing summary (reads/writes/estimated reduction), ready to hand to a review
   UI before anything is persisted.
2. The caller (``huf.ai.flow_api.convert_flow_to_procedure``) is responsible for
   actually creating the ``Agent Procedure`` document -- always via the normal
   ``Agent Procedure`` creation path (``frappe.get_doc({...}).insert()``), always with
   ``tier="Draft"`` and never ``status="Active"`` (I8: no automatic activation).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from huf.ai.graph.permissions import compute_static_envelope, default_tool_classifier
from huf.ai.graph.validator import ValidationError, validate_graph
from huf.ai.procedure_versioning import compute_fingerprint

# The three node types PLAN.md's T-52 task card names as disqualifying for determinism.
# A Flow containing any of these cannot be converted -- it genuinely needs an LLM or a
# human in the loop at that point, which a Procedure (by construction, I4) cannot express.
BLOCKING_NODE_TYPES: frozenset[str] = frozenset({"agent.run", "router.llm", "human.approval"})

# Flow-only entry points (spec/graph-ir.md section 1). Not a determinism problem -- a
# trigger is just how the Flow starts -- but the Procedure profile has no trigger nodes
# at all (its entry is always exactly one non-trigger node), so these are stripped and
# their `next` pointer becomes the Procedure's entry, rather than being treated as a
# reason to refuse.
TRIGGER_NODE_TYPES: frozenset[str] = frozenset({"trigger.webhook", "trigger.schedule", "trigger.doc-event"})

_GRAPH_FIELDS = ("schema_version", "profile", "fingerprint", "entry", "nodes", "contract")


class NotConvertibleError(Exception):
	"""Raised when a Flow cannot become a Procedure. Always carries a specific reason --
	never raised for "unknown"/"maybe" cases; callers that want the reason without an
	exception should call :func:`analyze_conversion` instead and check ``.convertible``.
	"""

	def __init__(self, reason: str, *, blocking_nodes: tuple[tuple[str | None, str], ...] = ()):
		self.reason = reason
		self.blocking_nodes = blocking_nodes
		super().__init__(reason)


@dataclasses.dataclass(frozen=True)
class ConversionSummary:
	"""The GOAL.md 6 "Optimization opportunity" card content, computed from the compiled
	Procedure graph -- never phrased in terms of nodes/IR/schema internals (huf/CLAUDE.md:
	no implementation detail in user-facing copy).
	"""

	reads: tuple[str, ...]
	writes: tuple[str, ...]
	atomic_operations: int
	estimated_round_trip_reduction_pct: int

	def as_dict(self) -> dict:
		return {
			"reads": list(self.reads),
			"writes": list(self.writes),
			"atomic_operations": self.atomic_operations,
			"estimated_round_trip_reduction_pct": self.estimated_round_trip_reduction_pct,
		}


@dataclasses.dataclass(frozen=True)
class ConversionResult:
	"""Outcome of :func:`analyze_conversion`. ``procedure_graph`` and ``summary`` are
	populated only when ``convertible`` is true -- symmetrical with
	``ValidationResult.envelope`` in ``huf.ai.graph.validator``: a refused conversion
	never carries a half-built result a caller could accidentally persist.
	"""

	convertible: bool
	reason: str | None = None
	blocking_nodes: tuple[tuple[str | None, str], ...] = ()
	procedure_graph: dict | None = None
	summary: ConversionSummary | None = None
	validation_errors: tuple[ValidationError, ...] = ()


def _iter_all_nodes(graph: dict) -> list[dict]:
	"""Every node in the graph's top-level ``nodes`` array. A flat scan is sufficient --
	the spec requires ``foreach.config.body`` / ``parallel.config.branches`` members to
	be referenced by id from the same top-level array, never nested inline (spec/graph-
	ir.md 2.1/2.2/6), so this already reaches every node exactly the way
	``huf.ai.procedure_versioning._iter_all_nodes`` does for the equivalent Procedure-
	side check.
	"""
	nodes = graph.get("nodes")
	if not isinstance(nodes, list):
		return []
	return [n for n in nodes if isinstance(n, dict)]


def find_blocking_nodes(flow_graph: dict) -> list[tuple[str | None, str]]:
	"""Return ``(node_id, node_type)`` for every node whose type is in
	:data:`BLOCKING_NODE_TYPES`. Empty means the Flow is deterministic and, modulo the
	rest of :func:`analyze_conversion`'s checks, convertible.
	"""
	return [
		(n.get("id"), n.get("type"))
		for n in _iter_all_nodes(flow_graph)
		if n.get("type") in BLOCKING_NODE_TYPES
	]


def _entry_roots(graph: dict) -> list[Any]:
	entry = graph.get("entry")
	return list(entry) if isinstance(entry, list) else [entry]


def _strip_triggers_and_rewire_entry(flow_graph: dict) -> tuple[Any, list[dict]]:
	"""Drop every trigger.* node and compute the Procedure's single entry point.

	Raises :class:`NotConvertibleError` for the two shapes a Procedure graph cannot
	represent: more than one entry root (a Procedure has exactly one entry, spec section
	2), or a trigger node with nothing after it (nothing left to run).
	"""
	nodes = _iter_all_nodes(flow_graph)
	nodes_by_id = {n.get("id"): n for n in nodes}
	roots = _entry_roots(flow_graph)

	if len(roots) != 1:
		raise NotConvertibleError(  # noqa: TRY003 -- user-facing refusal reason, not exception boilerplate
			f"This flow starts from {len(roots)} separate triggers. A procedure has exactly one "
			"entry point, so a multi-trigger flow cannot be converted as-is."
		)

	root_id = roots[0]
	root_node = nodes_by_id.get(root_id)
	if root_node is not None and root_node.get("type") in TRIGGER_NODE_TYPES:
		new_entry = root_node.get("next")
		if not new_entry:
			raise NotConvertibleError(  # noqa: TRY003 -- user-facing refusal reason, not exception boilerplate
				"This flow's trigger has nothing after it -- there is no work to convert."
			)
	else:
		new_entry = root_id

	kept_nodes = [n for n in nodes if n.get("type") not in TRIGGER_NODE_TYPES]
	return new_entry, kept_nodes


def convert_flow_graph(flow_graph: dict) -> dict:
	"""Compile a (already-blocking-node-free) Flow graph into a Procedure graph.

	Does not itself check for :data:`BLOCKING_NODE_TYPES` -- call
	:func:`find_blocking_nodes` first (``analyze_conversion`` does). Raises
	:class:`NotConvertibleError` for entry-shape problems (see
	``_strip_triggers_and_rewire_entry``). Does not validate the result against the
	Procedure schema -- the caller runs :func:`~huf.ai.graph.validator.validate_graph`
	on the return value, exactly as it would for any other candidate Procedure graph.
	"""
	entry, nodes = _strip_triggers_and_rewire_entry(flow_graph)

	procedure_graph = {
		"schema_version": flow_graph.get("schema_version") or "1.0.0",
		"profile": "procedure",
		"entry": entry,
		"nodes": nodes,
		"contract": flow_graph.get("contract") or {},
	}
	# additionalProperties: false at the graph root (spec section 2) -- only the six
	# fields above may survive. Anything Flow-only (settings, metadata, trigger
	# payload shape, ...) is deliberately dropped here, not carried over.
	procedure_graph = {k: procedure_graph[k] for k in _GRAPH_FIELDS if k != "fingerprint"}
	procedure_graph["fingerprint"] = compute_fingerprint(procedure_graph)
	return procedure_graph


def _summarize(procedure_graph: dict, envelope: dict) -> ConversionSummary:
	reads = tuple(sorted({d.get("doctype") for d in envelope.get("read", []) if d.get("doctype")}))
	writes = tuple(sorted({d.get("doctype") for d in envelope.get("write", []) if d.get("doctype")}))
	atomic_operations = sum(
		1 for n in procedure_graph.get("nodes", []) if n.get("type") in ("tool.call", "transform")
	)
	# Today an Agent would have to issue one model round trip per atomic operation to
	# reach the same result agentically; a bound Procedure collapses all of them into a
	# single deterministic call. Reported as a percentage so the UI never needs to know
	# "round trip" is really "node count" -- see ConversionSummary docstring.
	if atomic_operations > 1:
		reduction_pct = round((1 - 1 / atomic_operations) * 100)
	else:
		reduction_pct = 0
	return ConversionSummary(
		reads=reads,
		writes=writes,
		atomic_operations=atomic_operations,
		estimated_round_trip_reduction_pct=reduction_pct,
	)


def analyze_conversion(flow_graph: dict, *, classify_tool=default_tool_classifier) -> ConversionResult:
	"""The whole conversion decision, read-only. Never partially converts (PLAN.md task
	card warning): either ``convertible`` is true and ``procedure_graph`` + ``summary``
	are fully populated, or it is false and both are ``None``.

	Order of checks, each with its own specific refusal reason:

	1. The Flow graph itself must be schema-valid under the Flow profile. A malformed or
	   legacy-shaped Flow is refused here rather than silently reinterpreted -- this
	   module does not guess at what an invalid document "probably means".
	2. No :data:`BLOCKING_NODE_TYPES` node anywhere in the graph.
	3. Entry-shape must be convertible to a single Procedure entry point (trigger
	   stripping, see ``_strip_triggers_and_rewire_entry``).
	4. The compiled Procedure graph must itself pass
	   :func:`~huf.ai.graph.validator.validate_graph` under the ``"procedure"`` profile
	   (T-24) -- this is what actually derives the permission envelope (T-14) used in the
	   summary, and it is the same gate every other Procedure must pass before it may
	   ever be activated.
	"""
	if not isinstance(flow_graph, dict):
		return ConversionResult(convertible=False, reason="Flow definition is not a valid graph document.")

	flow_validation = validate_graph(flow_graph, "flow", classify_tool=classify_tool)
	if not flow_validation.ok:
		return ConversionResult(
			convertible=False,
			reason=(
				"This flow does not pass validation on its own terms, so it cannot be converted. "
				f"{len(flow_validation.errors)} problem(s) found; first: {flow_validation.errors[0]}"
				if flow_validation.errors
				else "This flow does not pass validation on its own terms."
			),
			validation_errors=flow_validation.errors,
		)

	blocking = find_blocking_nodes(flow_graph)
	if blocking:
		named = ", ".join(f"'{node_id}' ({node_type})" for node_id, node_type in blocking)
		return ConversionResult(
			convertible=False,
			reason=(
				"This flow uses steps that need a live decision -- an AI step, an AI-driven "
				f"router, or a human approval: {named}. Those cannot be converted to a fixed, "
				"deterministic procedure."
			),
			blocking_nodes=tuple(blocking),
		)

	try:
		procedure_graph = convert_flow_graph(flow_graph)
	except NotConvertibleError as exc:
		return ConversionResult(convertible=False, reason=exc.reason)

	procedure_validation = validate_graph(procedure_graph, "procedure", classify_tool=classify_tool)
	if not procedure_validation.ok:
		return ConversionResult(
			convertible=False,
			reason=(
				"The converted procedure did not pass validation. "
				f"{len(procedure_validation.errors)} problem(s) found; first: "
				f"{procedure_validation.errors[0]}"
				if procedure_validation.errors
				else "The converted procedure did not pass validation."
			),
			validation_errors=procedure_validation.errors,
		)

	envelope = procedure_validation.envelope or compute_static_envelope(
		procedure_graph, classify_tool=classify_tool
	)
	summary = _summarize(procedure_graph, envelope)

	return ConversionResult(
		convertible=True,
		procedure_graph=procedure_graph,
		summary=summary,
	)


__all__ = [
	"BLOCKING_NODE_TYPES",
	"TRIGGER_NODE_TYPES",
	"ConversionResult",
	"ConversionSummary",
	"NotConvertibleError",
	"analyze_conversion",
	"convert_flow_graph",
	"find_blocking_nodes",
]
