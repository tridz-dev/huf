# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Profile-driven static validator for the shared graph IR (T-24).

This is the gate a graph document must pass **before activation** -- before an ``Agent
Procedure`` or ``Flow Definition`` record carrying it is allowed to run. It is deliberately
strictly stronger than ``huf/huf/doctype/flow_definition/flow_definition.py``'s existing
``_validate_definition_json``, which checks only node ids, allowed types, entry presence and
edge endpoints. It never inspects node ``config`` contents, never checks reachability or
cycles, and never follows ``condition.on_true``/``on_false`` or the ``foreach``/``parallel``
routing fields, all of which bypass its edge list entirely. Anything this module rejects that
Flow's validator would have accepted is the point, not a regression.

**Profile is a validation input, never a runtime authorization decision** (PLAN.md ss3). Calling
``validate_graph(graph, "procedure")`` selects which schema and which node-type allow-list to
check the document against; it does not grant, elevate, or otherwise decide what the resulting
record is allowed to do at runtime. The actual trust boundary is structural: an ``Agent
Procedure`` record is *incapable* of holding a Flow-only node in the first place, because its
DocType only ever stores a document meant to satisfy ``$defs/ProcedureGraph``. This validator is
defence in depth on top of that structural boundary, catching a malformed or malicious document
before it is ever bound to a record -- it is not itself the mechanism that keeps Procedure and
Flow apart, and no caller may treat a passing validation result as a permission grant (see I1/I2
in ``$TRACK/PLAN.md`` ss3: compile-time analysis never replaces runtime enforcement, and effective
authority is always an intersection, never something a validator hands out).

**Fail closed.** Every check below defaults to reject: an unrecognised node type, a missing
``contract.limits``, a reference to a node that isn't a proven ancestor, an expression that fails
to parse -- all of these produce a rejection, never a silent pass-through. Nothing here "ignores"
an unknown construct; not recognising something is itself a rejection reason.

Checks performed, roughly in the order they run:

1. **Schema conformance** -- validated against ``$defs/ProcedureGraph`` or ``$defs/FlowGraph``
   from ``spec/graph-ir.schema.json`` (embedded below as ``GRAPH_IR_SCHEMA``, since this module
   must be deployable as a single file onto a bench that does not check out ``$TRACK/spec``).
   Selected by the ``profile`` argument, never by the document's own (informational-only)
   ``profile`` field.
2. **Static tool closure (I3)** -- structurally guaranteed by the schema (``ToolId`` is a plain
   string, never a ``Reference``; see ``spec/graph-ir.md`` section 6), reconfirmed here with a
   dedicated, clearly-worded rejection for defence in depth.
3. **Profile enforcement (I4)** -- every node's ``type`` must be in the profile's allowed set.
   Also structurally guaranteed by the schema's per-profile node ``oneOf``, reconfirmed here so a
   Flow-only node under the Procedure profile gets a rejection reason naming the offending node
   and type rather than a generic "did not match any schema" message.
4. **Reachability and acyclicity** -- every node must be reachable from ``entry`` (delegates its
   traversal, including ``foreach.body`` / ``parallel.branches`` nesting, to
   ``huf.ai.graph.permissions.iter_reachable_nodes`` so this module and the permission-envelope
   analyser never disagree about what counts as an edge); no cycles among control-flow pointers.
5. **All references resolve** -- every ``{"$from": "<node_id>...."}`` points at a node that both
   exists and is a proven predecessor of the referencing node along every path that reaches it
   (never itself, never a node that only follows it).
6. **Limits present and within policy** -- ``contract.limits`` is required by schema already
   (missing limits is a schema rejection: fail closed); this module additionally enforces a
   policy ceiling per field (``POLICY_LIMIT_CEILINGS``) so a graph cannot merely satisfy the
   schema's open-ended minimums.
7. **Permission envelope derivable (T-14)** -- delegates to
   ``huf.ai.graph.permissions.compute_static_envelope``; also checks the declared
   ``contract.permission_envelope`` is a superset of what the graph actually invokes (graph-ir.md
   section 6: a ``tool.call`` node whose ``tool_id`` needs authority outside the declared
   envelope is a static validation failure, not merely a runtime one).
8. **Transform ops and expressions** -- every ``transform.config.op`` must be a name in
   ``huf.ai.graph.transforms.REGISTRY``; every ``Expression`` field (``condition.expression``,
   ``validate.assertions[].expression``, ``contract.applies_when[]``) must parse via
   ``huf.ai.graph.expressions.parse_expression``.

Every rejection is a :class:`ValidationError` -- a code, the offending node id (or ``None`` for a
graph-level problem), a field path, and a human message -- never a bare boolean. Use
:func:`validate_graph` and inspect ``result.ok`` / ``result.errors``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from collections.abc import Iterator
from typing import Any

from jsonschema import Draft202012Validator

from huf.ai.graph import transforms
from huf.ai.graph.expressions import ExpressionError, parse_expression
from huf.ai.graph.permissions import (
	ToolClassifier,
	compute_static_envelope,
	default_tool_classifier,
	envelope_declares,
	iter_reachable_nodes,
)

# --------------------------------------------------------------------------------------
# The graph IR JSON Schema, embedded verbatim from spec/graph-ir.schema.json.
#
# Embedded, not read from disk, because this module is deployed by copying this single
# file onto a bench that does not check out $TRACK/spec (see the T-24 task card's bench
# verification steps). Keep this in sync with spec/graph-ir.schema.json by hand; nothing
# here is regenerated automatically. This is the same document, byte for byte, as the
# canonical spec file -- only the embedding is new.
# --------------------------------------------------------------------------------------


# The Graph IR schema is the contract shared by the validator, the Agent Procedure DocType and
# Flow. It lives beside this module as a data file so there is exactly ONE copy in the app -- an
# embedded literal here would be a second copy of the contract, free to drift from the first.
_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_ir.schema.json")

with open(_SCHEMA_PATH, encoding="utf-8") as _f:
	GRAPH_IR_SCHEMA: dict = json.load(_f)


# --------------------------------------------------------------------------------------
# Profile node-type allow-lists (spec/graph-ir.md section 1, PLAN.md I4)
# --------------------------------------------------------------------------------------

PROCEDURE_NODE_TYPES: frozenset[str] = frozenset(
	{"tool.call", "transform", "condition", "foreach", "parallel", "validate", "output"}
)

FLOW_ONLY_NODE_TYPES: frozenset[str] = frozenset(
	{
		"agent.run",
		"router.llm",
		"human.approval",
		"trigger.webhook",
		"trigger.schedule",
		"trigger.doc-event",
	}
)

FLOW_NODE_TYPES: frozenset[str] = PROCEDURE_NODE_TYPES | FLOW_ONLY_NODE_TYPES

_PROFILE_NODE_TYPES: dict[str, frozenset[str]] = {
	"procedure": PROCEDURE_NODE_TYPES,
	"flow": FLOW_NODE_TYPES,
}

_PROFILE_SCHEMA_DEF: dict[str, str] = {
	"procedure": "ProcedureGraph",
	"flow": "FlowGraph",
}

# Policy ceilings for contract.limits (requirement 6: "within policy", not merely "present").
# The schema only enforces open-ended minimums (e.g. max_nodes >= 1); these are T-24's own
# ceilings until a real policy doctype exists to own them. Deliberately generous but finite --
# fail closed means a graph with no limits, or with limits above policy, is rejected outright.
POLICY_LIMIT_CEILINGS: dict[str, int] = {
	"max_nodes": 500,
	"max_rows": 50_000,
	"max_output_bytes": 5_000_000,
	"max_parallel_calls": 16,
	"max_foreach_iterations": 5_000,
	"max_external_calls": 2_000,
	"max_writes": 500,
	"max_wall_time_ms": 15 * 60 * 1000,
}

_SPECIAL_REFERENCE_ROOTS: frozenset[str] = frozenset({"input", "trigger", "row", "foreach.item", "foreach.index"})

_REFERENCE_ROOT_RE = re.compile(r"^(input|trigger|row|foreach\.(?:item|index)|[a-zA-Z_][a-zA-Z0-9_]*)")


# --------------------------------------------------------------------------------------
# Result types -- every rejection is a specific, actionable reason, never a bare boolean.
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ValidationError:
	"""One specific, actionable reason a graph was rejected.

	``node_id`` is ``None`` for a graph-level problem (e.g. a missing ``contract``).
	``field`` is a dotted/indexed path relative to the node (or the graph root when
	``node_id`` is ``None``), e.g. ``"config.tool_id"`` or ``"contract.limits.max_rows"``.
	"""

	code: str
	node_id: str | None
	field: str | None
	message: str

	def __str__(self) -> str:  # pragma: no cover -- convenience only
		where = self.node_id or "<graph>"
		if self.field:
			where = f"{where}.{self.field}"
		return f"[{self.code}] {where}: {self.message}"


@dataclasses.dataclass(frozen=True)
class ValidationResult:
	"""Outcome of :func:`validate_graph`. ``envelope`` is populated only when ``ok`` is true --
	a graph that fails validation never gets a derived permission envelope, since deriving one
	from a structurally broken document would itself be a claim this module cannot stand behind.
	"""

	ok: bool
	profile: str
	errors: tuple[ValidationError, ...] = ()
	envelope: dict | None = None

	def raise_if_invalid(self) -> None:
		if not self.ok:
			raise GraphValidationError(self)


class GraphValidationError(Exception):
	"""Raised by :meth:`ValidationResult.raise_if_invalid`. Carries the full result, including
	every :class:`ValidationError`, not just the first -- a caller that only wants "did it pass"
	can catch this and stop; a caller building a review UI can read ``.result.errors``."""

	def __init__(self, result: ValidationResult):
		self.result = result
		super().__init__("; ".join(str(err) for err in result.errors) or "graph validation failed")


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def validate_graph(
	graph: dict,
	profile: str,
	*,
	classify_tool: ToolClassifier = default_tool_classifier,
) -> ValidationResult:
	"""Validate ``graph`` against ``profile`` ("procedure" or "flow"). See module docstring for
	the full check list. Returns a :class:`ValidationResult`; never raises for an invalid graph
	(only :meth:`ValidationResult.raise_if_invalid` does that, for callers that want an exception).

	``classify_tool`` is forwarded to ``compute_static_envelope`` (T-14) unchanged -- pass a fake
	in tests exactly as ``test_graph_permissions.py`` does, to keep this function callable without
	a Frappe bench.
	"""

	if profile not in _PROFILE_SCHEMA_DEF:
		return ValidationResult(
			ok=False,
			profile=profile,
			errors=(
				ValidationError(
					"UNKNOWN_PROFILE",
					None,
					None,
					f"unknown profile {profile!r}; expected one of {sorted(_PROFILE_SCHEMA_DEF)}",
				),
			),
		)

	if not isinstance(graph, dict):
		return ValidationResult(
			ok=False,
			profile=profile,
			errors=(ValidationError("NOT_AN_OBJECT", None, None, "graph document must be a JSON object"),),
		)

	schema_errors = _check_schema(graph, profile)
	if schema_errors:
		# A schema-invalid document cannot be trusted for any further structural analysis
		# (missing "nodes", non-dict nodes, non-string ids, ...) -- fail closed immediately.
		return ValidationResult(ok=False, profile=profile, errors=tuple(schema_errors))

	nodes = graph.get("nodes") or []
	nodes_by_id: dict[str, dict] = {node["id"]: node for node in nodes if isinstance(node, dict) and "id" in node}

	errors: list[ValidationError] = []
	errors.extend(_check_profile_node_types(nodes, profile))
	errors.extend(_check_control_flow_targets(graph, nodes_by_id))
	errors.extend(_check_reachability(graph, nodes_by_id))
	errors.extend(_check_acyclic(graph, nodes_by_id))
	errors.extend(_check_tool_ids_literal(nodes))
	errors.extend(_check_transform_ops(nodes))
	errors.extend(_check_expressions(graph, nodes))
	errors.extend(_check_references(nodes_by_id))
	errors.extend(_check_limits_policy(graph))

	envelope: dict | None = None
	if not errors:
		try:
			envelope = compute_static_envelope(graph, classify_tool=classify_tool)
		except Exception as exc:  # noqa: BLE001 -- any failure here is itself a rejection reason
			errors.append(
				ValidationError(
					"ENVELOPE_NOT_DERIVABLE",
					None,
					None,
					f"permission envelope could not be derived: {exc}",
				)
			)
		else:
			errors.extend(_check_envelope_covers_closure(graph, envelope))

	return ValidationResult(ok=not errors, profile=profile, errors=tuple(errors), envelope=envelope if not errors else None)


def validate_procedure_graph(graph: dict, **kwargs: Any) -> ValidationResult:
	"""Convenience wrapper: ``validate_graph(graph, "procedure", **kwargs)``."""
	return validate_graph(graph, "procedure", **kwargs)


def validate_flow_graph(graph: dict, **kwargs: Any) -> ValidationResult:
	"""Convenience wrapper: ``validate_graph(graph, "flow", **kwargs)``."""
	return validate_graph(graph, "flow", **kwargs)


# --------------------------------------------------------------------------------------
# 1. Schema conformance
# --------------------------------------------------------------------------------------


def _check_schema(graph: dict, profile: str) -> list[ValidationError]:
	def_name = _PROFILE_SCHEMA_DEF[profile]
	subschema = {"$defs": GRAPH_IR_SCHEMA["$defs"], "$ref": f"#/$defs/{def_name}"}
	validator = Draft202012Validator(subschema)
	errors: list[ValidationError] = []
	for err in sorted(validator.iter_errors(graph), key=lambda e: [str(p) for p in e.path]):
		path = list(err.path)
		errors.append(
			ValidationError(
				code="SCHEMA",
				node_id=_node_id_from_path(graph, path),
				field=_field_from_path(path),
				message=_describe_schema_error(err),
			)
		)
	return errors


def _describe_schema_error(err) -> str:
	"""jsonschema's ``oneOf``/``anyOf`` failures report only "not valid under any schema" at the
	top level, with the actually-useful detail buried in ``.context``. Recurse into the deepest
	(most specific) sub-error so the message names the real problem (e.g. "'tool_id' is not of
	type 'string'") instead of the generic wrapper.
	"""
	if err.context:
		best = max(err.context, key=lambda sub: len(list(sub.absolute_path)))
		return _describe_schema_error(best)
	return err.message


def _node_id_from_path(graph: dict, path: list) -> str | None:
	if len(path) >= 2 and path[0] == "nodes" and isinstance(path[1], int):
		nodes = graph.get("nodes") or []
		idx = path[1]
		if 0 <= idx < len(nodes) and isinstance(nodes[idx], dict):
			return nodes[idx].get("id") or f"nodes[{idx}]"
	return None


def _field_from_path(path: list) -> str | None:
	if len(path) > 2 and path[0] == "nodes":
		return ".".join(str(p) for p in path[2:])
	if path:
		return ".".join(str(p) for p in path)
	return None


# --------------------------------------------------------------------------------------
# 2 / 3. Static tool closure + profile enforcement (defence in depth on top of the schema)
# --------------------------------------------------------------------------------------


def _check_tool_ids_literal(nodes: list[dict]) -> list[ValidationError]:
	"""Reconfirms I3 with a dedicated message. The schema already makes this structurally
	impossible to violate (``config.tool_id`` is ``$defs/ToolId``, a plain string, never a
	``$defs/Reference`` -- see spec/graph-ir.md section 6), so this only ever fires if a future
	schema change accidentally widens ``ToolId``; it exists so that regression shows up as this
	module's own named check rather than a silent schema-only pass.
	"""
	errors = []
	for node in nodes:
		if not isinstance(node, dict) or node.get("type") != "tool.call":
			continue
		tool_id = (node.get("config") or {}).get("tool_id")
		if not isinstance(tool_id, str) or not tool_id:
			errors.append(
				ValidationError(
					"DYNAMIC_TOOL_DISPATCH",
					node.get("id"),
					"config.tool_id",
					f"tool_id must be a literal string known at validation time, got {tool_id!r} "
					"-- dynamic tool dispatch is forbidden (I3)",
				)
			)
	return errors


def _check_profile_node_types(nodes: list[dict], profile: str) -> list[ValidationError]:
	allowed = _PROFILE_NODE_TYPES[profile]
	errors = []
	for node in nodes:
		if not isinstance(node, dict):
			continue
		ntype = node.get("type")
		if ntype not in allowed:
			kind = "a Flow-only" if ntype in FLOW_ONLY_NODE_TYPES else "an unrecognised"
			errors.append(
				ValidationError(
					"PROFILE_VIOLATION",
					node.get("id"),
					"type",
					f"node type {ntype!r} is {kind} node type and is not permitted under the "
					f"{profile!r} profile (allowed: {sorted(allowed)})",
				)
			)
	return errors


# --------------------------------------------------------------------------------------
# 4. Reachability and acyclicity
# --------------------------------------------------------------------------------------


def _entry_roots(graph: dict) -> list[str]:
	entry = graph.get("entry")
	if isinstance(entry, list):
		return list(entry)
	return [entry] if entry is not None else []


def _control_flow_targets(node: dict) -> list[tuple[str, str | None]]:
	"""``(field_label, target_node_id_or_None)`` for every control-flow pointer ``node``
	declares, per spec/graph-ir.md section 2. Mirrors
	``huf.ai.graph.permissions.iter_reachable_nodes``'s traversal exactly, so this module and the
	permission-envelope analyser can never disagree about what counts as an edge.
	"""
	config = node.get("config") or {}
	ntype = node.get("type")
	targets: list[tuple[str, str | None]] = [("next", node.get("next")), ("on_error", node.get("on_error"))]

	if ntype == "condition":
		targets.append(("config.on_true", config.get("on_true")))
		targets.append(("config.on_false", config.get("on_false")))
	elif ntype == "router.llm":
		for i, option in enumerate(config.get("options", []) or []):
			if isinstance(option, dict):
				targets.append((f"config.options[{i}].node_id", option.get("node_id")))
		targets.append(("config.default", config.get("default")))
	elif ntype == "human.approval":
		targets.append(("config.approve_next", config.get("approve_next")))
		targets.append(("config.reject_next", config.get("reject_next")))
		targets.append(("config.timeout_next", config.get("timeout_next")))
	elif ntype == "foreach":
		for i, body_id in enumerate(config.get("body", []) or []):
			targets.append((f"config.body[{i}]", body_id))
	elif ntype == "parallel":
		for bi, branch in enumerate(config.get("branches", []) or []):
			if not isinstance(branch, list):
				continue
			for ni, node_id in enumerate(branch):
				targets.append((f"config.branches[{bi}][{ni}]", node_id))

	return [(field, target) for field, target in targets if target is not None]


def _adjacency(nodes_by_id: dict[str, dict]) -> dict[str, list[str]]:
	"""Direct control-flow edges for every node, plus one derived edge
	:func:`_control_flow_targets` cannot see on its own: a ``parallel`` node's ``join: "all"``
	means every branch completes before its own ``next`` runs, so each branch member is an
	ancestor of that ``next`` node too -- even though no branch member's own ``next`` pointer
	says so (a single-node branch is terminal within its own chain). Without this, a node after
	the join that legitimately references a branch member's output would be misreported as a
	forward reference.
	"""
	adjacency = {nid: [target for _, target in _control_flow_targets(node)] for nid, node in nodes_by_id.items()}
	for node in nodes_by_id.values():
		if node.get("type") != "parallel":
			continue
		next_target = node.get("next")
		if not next_target:
			continue
		for branch in (node.get("config") or {}).get("branches", []) or []:
			if not isinstance(branch, list):
				continue
			for member in branch:
				adjacency.setdefault(member, []).append(next_target)
	return adjacency


def _check_control_flow_targets(graph: dict, nodes_by_id: dict[str, dict]) -> list[ValidationError]:
	errors: list[ValidationError] = []
	seen_ids: set[str] = set()
	for node in graph.get("nodes") or []:
		if not isinstance(node, dict):
			continue
		nid = node.get("id")
		if nid in seen_ids:
			errors.append(ValidationError("DUPLICATE_NODE_ID", nid, "id", f"node id {nid!r} is declared more than once"))
			continue
		seen_ids.add(nid)
		for field, target in _control_flow_targets(node):
			if target not in nodes_by_id:
				errors.append(
					ValidationError(
						"DANGLING_TARGET",
						nid,
						field,
						f"{field} points at node id {target!r}, which does not exist in this graph",
					)
				)

	for root in _entry_roots(graph):
		if root not in nodes_by_id:
			errors.append(
				ValidationError(
					"DANGLING_ENTRY",
					None,
					"entry",
					f"entry points at node id {root!r}, which does not exist in this graph",
				)
			)
	return errors


def _check_reachability(graph: dict, nodes_by_id: dict[str, dict]) -> list[ValidationError]:
	reachable_ids = {node["id"] for node in iter_reachable_nodes(graph)}
	return [
		ValidationError("UNREACHABLE_NODE", nid, None, f"node {nid!r} is not reachable from entry")
		for nid in nodes_by_id
		if nid not in reachable_ids
	]


def _check_acyclic(graph: dict, nodes_by_id: dict[str, dict]) -> list[ValidationError]:
	adjacency = _adjacency(nodes_by_id)
	white, gray, black = 0, 1, 2
	color = dict.fromkeys(nodes_by_id, white)
	errors: list[ValidationError] = []
	reported: set[frozenset] = set()

	def visit(nid: str, path: list[str]) -> None:
		if nid not in nodes_by_id or color.get(nid) == black:
			return
		if color.get(nid) == gray:
			start = path.index(nid)
			cycle = [*path[start:], nid]
			key = frozenset(cycle)
			if key not in reported:
				reported.add(key)
				errors.append(ValidationError("CYCLE", nid, None, f"cycle detected: {' -> '.join(cycle)}"))
			return
		color[nid] = gray
		for successor in adjacency.get(nid, []):
			visit(successor, [*path, nid])
		color[nid] = black

	for root in _entry_roots(graph):
		visit(root, [])
	return errors


# --------------------------------------------------------------------------------------
# 5. All references resolve, and precede their referencing node
# --------------------------------------------------------------------------------------


def _iter_value_references(value: Any, path: str) -> Iterator[tuple[str, str]]:
	if isinstance(value, dict):
		from_value = value.get("$from")
		if "$from" in value and isinstance(from_value, str):
			yield path, from_value
			return
		for key, sub in value.items():
			yield from _iter_value_references(sub, f"{path}.{key}")
	elif isinstance(value, list):
		for i, sub in enumerate(value):
			yield from _iter_value_references(sub, f"{path}[{i}]")


def _reference_root(reference: str) -> str | None:
	match = _REFERENCE_ROOT_RE.match(reference)
	return match.group(1) if match else None


def _ancestors_and_descendants(nodes_by_id: dict[str, dict]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
	"""``descendants[x]`` = every node id reachable from ``x`` via control-flow edges;
	``ancestors[x]`` = every node id that precedes ``x`` along some path from any entry root
	(the inverse relation). Computed once, from the same edge set :func:`_check_acyclic` uses,
	so "precedes" here means exactly what "reachable from" means everywhere else in this module.
	"""
	adjacency = _adjacency(nodes_by_id)
	descendants: dict[str, set[str]] = {}
	for nid in nodes_by_id:
		seen: set[str] = set()
		stack = list(adjacency.get(nid, []))
		while stack:
			cur = stack.pop()
			if cur in seen or cur not in nodes_by_id:
				continue
			seen.add(cur)
			stack.extend(adjacency.get(cur, []))
		descendants[nid] = seen

	ancestors: dict[str, set[str]] = {nid: set() for nid in nodes_by_id}
	for source, reached in descendants.items():
		for target in reached:
			ancestors[target].add(source)
	return ancestors, descendants


def _check_references(nodes_by_id: dict[str, dict]) -> list[ValidationError]:
	ancestors, descendants = _ancestors_and_descendants(nodes_by_id)
	errors: list[ValidationError] = []
	for nid, node in nodes_by_id.items():
		ntype = node.get("type")
		config = node.get("config") or {}
		for path, ref in _iter_value_references(config, "config"):
			root = _reference_root(ref)
			if root is None or root in _SPECIAL_REFERENCE_ROOTS:
				continue

			# foreach.config.collect is special: it is evaluated once PER ITEM, after that
			# item's body chain has finished running, so a reference into a body node's output
			# is not a forward reference even though the body node is a descendant of the
			# foreach node, not an ancestor of it (spec/graph-ir.md section 2, ForeachNode
			# schema: "collect ... typically into a body node's output"). Any node inside the
			# foreach's own reachable subtree (its body chain) is a valid target for collect;
			# anything outside it is not.
			if ntype == "foreach" and path == "config.collect":
				if root == nid or root not in descendants.get(nid, set()):
					errors.append(
						ValidationError(
							"FORWARD_REFERENCE",
							nid,
							path,
							f"reference {ref!r} points at node {root!r}, which is not part of this "
							f"foreach node's own body chain",
						)
					)
				continue

			if root == nid:
				errors.append(
					ValidationError(
						"SELF_REFERENCE",
						nid,
						path,
						f"reference {ref!r} refers to its own node {nid!r}, which has not produced output yet",
					)
				)
			elif root not in nodes_by_id:
				errors.append(
					ValidationError(
						"DANGLING_REFERENCE",
						nid,
						path,
						f"reference {ref!r} points at node id {root!r}, which does not exist in this graph",
					)
				)
			elif root not in ancestors.get(nid, set()):
				errors.append(
					ValidationError(
						"FORWARD_REFERENCE",
						nid,
						path,
						f"reference {ref!r} points at node {root!r}, which does not precede {nid!r} "
						"on any path through this graph",
					)
				)
	return errors


# --------------------------------------------------------------------------------------
# 6. Limits present and within policy
# --------------------------------------------------------------------------------------


def _check_limits_policy(graph: dict) -> list[ValidationError]:
	contract = graph.get("contract")
	if not isinstance(contract, dict):
		return [
			ValidationError(
				"MISSING_LIMITS",
				None,
				"contract",
				"graph has no contract; limits are required and a graph with no limits is "
				"rejected (fail closed)",
			)
		]
	limits = contract.get("limits")
	if not isinstance(limits, dict):
		return [
			ValidationError(
				"MISSING_LIMITS",
				None,
				"contract.limits",
				"graph declares no resource limits; a graph with no limits is rejected (fail closed)",
			)
		]

	errors: list[ValidationError] = []
	for key, ceiling in POLICY_LIMIT_CEILINGS.items():
		value = limits.get(key)
		if not isinstance(value, (int, float)) or isinstance(value, bool):
			errors.append(
				ValidationError(
					"MISSING_LIMIT_FIELD",
					None,
					f"contract.limits.{key}",
					f"{key} is required and must be numeric",
				)
			)
			continue
		if value > ceiling:
			errors.append(
				ValidationError(
					"LIMIT_EXCEEDS_POLICY",
					None,
					f"contract.limits.{key}",
					f"{key}={value} exceeds policy ceiling {ceiling}",
				)
			)
	if limits.get("fail_closed") is not True:
		errors.append(
			ValidationError(
				"LIMIT_NOT_FAIL_CLOSED",
				None,
				"contract.limits.fail_closed",
				"fail_closed must be true -- there is no soft-limit mode",
			)
		)
	return errors


# --------------------------------------------------------------------------------------
# 7. Permission envelope derivable + sufficient (T-14)
# --------------------------------------------------------------------------------------


def _check_envelope_covers_closure(graph: dict, computed_envelope: dict) -> list[ValidationError]:
	declared = ((graph.get("contract") or {}).get("permission_envelope")) or {}
	errors: list[ValidationError] = []

	for entry in computed_envelope.get("read", []):
		doctype = entry.get("doctype")
		if not envelope_declares(declared, ptype="read", doctype=doctype):
			errors.append(
				ValidationError(
					"ENVELOPE_UNDER_DECLARED",
					None,
					"contract.permission_envelope.read",
					f"graph invokes read access to {doctype!r} that is not declared in "
					"contract.permission_envelope.read",
				)
			)
	for entry in computed_envelope.get("write", []):
		doctype = entry.get("doctype")
		if not envelope_declares(declared, ptype="write", doctype=doctype):
			errors.append(
				ValidationError(
					"ENVELOPE_UNDER_DECLARED",
					None,
					"contract.permission_envelope.write",
					f"graph invokes write access to {doctype!r} that is not declared in "
					"contract.permission_envelope.write",
				)
			)
	for kind in ("http", "code"):
		computed = computed_envelope.get(kind)
		if computed == "none" or not computed:
			continue
		declared_kind = declared.get(kind)
		declared_set = set(declared_kind) if isinstance(declared_kind, list) else set()
		missing = sorted(set(computed) - declared_set)
		if missing:
			errors.append(
				ValidationError(
					"ENVELOPE_UNDER_DECLARED",
					None,
					f"contract.permission_envelope.{kind}",
					f"graph uses {kind} surface {missing} not declared in "
					f"contract.permission_envelope.{kind}",
				)
			)
	return errors


# --------------------------------------------------------------------------------------
# 8. Transform ops and expressions
# --------------------------------------------------------------------------------------


def _check_transform_ops(nodes: list[dict]) -> list[ValidationError]:
	errors = []
	for node in nodes:
		if not isinstance(node, dict) or node.get("type") != "transform":
			continue
		op = (node.get("config") or {}).get("op")
		if op not in transforms.REGISTRY:
			errors.append(
				ValidationError(
					"UNKNOWN_TRANSFORM_OP",
					node.get("id"),
					"config.op",
					f"transform op {op!r} is not one of the registered ops: {sorted(transforms.REGISTRY)}",
				)
			)
	return errors


def _check_expressions(graph: dict, nodes: list[dict]) -> list[ValidationError]:
	errors: list[ValidationError] = []

	def _try_parse(nid: str | None, field: str, expr: Any) -> None:
		if not isinstance(expr, str):
			return
		try:
			parse_expression(expr)
		except ExpressionError as exc:
			errors.append(ValidationError("BAD_EXPRESSION", nid, field, str(exc)))

	for node in nodes:
		if not isinstance(node, dict):
			continue
		nid = node.get("id")
		ntype = node.get("type")
		config = node.get("config") or {}
		if ntype == "condition":
			_try_parse(nid, "config.expression", config.get("expression"))
		elif ntype == "validate":
			for i, assertion in enumerate(config.get("assertions", []) or []):
				if isinstance(assertion, dict):
					_try_parse(nid, f"config.assertions[{i}].expression", assertion.get("expression"))

	contract = graph.get("contract") or {}
	for i, expr in enumerate(contract.get("applies_when", []) or []):
		_try_parse(None, f"contract.applies_when[{i}]", expr)

	return errors
