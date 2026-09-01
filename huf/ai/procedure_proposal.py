# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Run & Propose Procedure -- compile one Agent Run's tool-call trace into a proposed
graph-IR Agent Procedure for human review.

This is a narrow, deliberately conservative first slice of the trace-mining compiler
GOAL.md sketches as Phase 4 / 4A-4D and PLAN.md ss9 explicitly defers ("Compiling from
observed runs stays out of scope" -- ``huf.ai.procedure_conversion``'s own docstring says
the same thing about itself). It is NOT that compiler: there is no pattern mining across
many runs (4A), no cross-run parameterization or dedup (4B/4C), no optimization pass
(4D). The input is exactly one already-completed ``Agent Run`` and its own ordered
``Agent Tool Call`` rows; the output is a single candidate Procedure graph, or a specific
refusal reason. Multi-run generalization is future work this module does not attempt.

Two-step contract, mirroring ``huf.ai.procedure_conversion`` / ``huf.ai.flow_api``'s
analyze/convert split for Flow-to-Procedure conversion:

1. :func:`propose_procedure_from_run` -- read-only. Loads the run's tool-call trace,
   compiles a candidate Procedure graph, validates it, and returns it as a PREVIEW.
   Saves nothing.
2. :func:`accept_procedure_proposal` -- the user has reviewed the preview (and may have
   edited the graph client-side) and clicked Accept. Re-validates the graph exactly as
   step 1 did -- never trusts a client-round-tripped graph -- and only then persists it,
   via the same ``frappe.get_doc({...}).insert()`` shape as
   ``huf.ai.flow_api.convert_flow_to_procedure``: ``tier="Draft"``, ``status="Draft"``.
   Neither step ever activates a procedure (I8); a human enables it separately.

THE KEY DESIGN PROBLEM this module exists to solve is value binding: a tool call's
recorded arguments are *this run's* concrete values, not a template. Baking them in
verbatim would produce a procedure that looks deterministic but is actually just replaying
one run's hidden judgment -- exactly the failure mode a Procedure profile (I4: no LLM
inside Procedure execution) exists to rule out. So every argument value is either:

  (a) traced to the run's own ``prompt`` text -> becomes ``{"$from": "input.<field>"}``,
      making the compiled procedure reusable with different inputs, not hardcoded to this
      one run;
  (b) traced to an EARLIER tool call's recorded ``tool_result`` -> becomes
      ``{"$from": "<earlier_node_id>.<json_path>"}``, an ordinary intra-graph reference;
  (c) a small, genuinely-constant-looking literal (empty string, ``0``, ``false``/``none``
      and their near-synonyms, or an empty list/dict) -> kept as a literal; or
  (d) none of the above -> the WHOLE PROPOSAL is refused, naming the exact step and
      argument, rather than silently guessing. See :func:`_bind_argument_value` for the
      precise rules. Bias is deliberately toward refusing over guessing (task instruction);
      this module never widens (c) beyond what is explicitly listed there.

Frappe-free by design where it matters: :func:`compile_procedure_from_trace` (and every
helper it calls) is pure -- plain dicts and strings in, a :class:`ProposalResult` out --
so the compilation and refusal logic is unit-testable with plain ``pytest``/``unittest``,
no bench required, exactly the split ``huf.ai.procedure_conversion`` uses for the
Flow-to-Procedure direction. Only the two ``@frappe.whitelist()`` entry points
(:func:`propose_procedure_from_run`, :func:`accept_procedure_proposal`) and their small
frappe-touching helpers (:func:`_load_tool_calls`, :func:`_load_agent_run`) import or call
``frappe``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.graph.permissions import ToolClassifier, compute_static_envelope, default_tool_classifier
from huf.ai.graph.validator import GraphValidationError, validate_graph
from huf.ai.procedure_versioning import compute_fingerprint

# Statuses that count as "this tool call finished cleanly" (Agent Tool Call.status).
# Anything else (Started/Queued/Failed, or missing entirely) is a hard stop per the task
# spec: the run did not cleanly finish that call, so it cannot be trusted as a step in a
# deterministic replay of the run -- never silently skipped.
_CLEAN_STATUS = "Completed"

# ptypes that count as a write for the max_writes-limit heuristic below. Mirrors
# huf.ai.graph.permissions._WRITE_PTYPES (private there; duplicated here rather than
# imported, matching that module's own docstring description of the set so the two never
# need to be kept in sync via a shared private name).
_WRITE_PTYPES = frozenset({"write", "create", "delete", "submit", "cancel"})

# Argument values treated as constants trivial enough to keep as a literal without
# requiring an explanation (task point 2(d)): the exact list the task spec names --
# empty string, 0, false, and a handful of extremely common words/near-synonyms -- plus
# empty list/dict as their structural equivalent (every tool's own "no filter" default).
# Deliberately NOT widened beyond this: the task instruction is to bias toward refusing
# over silently guessing, so anything not obviously trivial falls through to (a)/(b)/(d).
_TRIVIAL_WORDS = frozenset({"true", "false", "none", "null"})

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_NON_IDENTIFIER_CHARS_RE = re.compile(r"[^0-9a-zA-Z_]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


# --------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ProposalResult:
	"""Outcome of :func:`compile_procedure_from_trace`. ``procedure_graph`` and
	``input_schema`` are populated only when ``proposable`` is true -- symmetrical with
	``ConversionResult`` in ``huf.ai.procedure_conversion``: a refused proposal never
	carries a half-built graph a caller could accidentally persist.
	"""

	proposable: bool
	reason: str | None = None
	procedure_graph: dict | None = None
	input_schema: dict | None = None
	step_count: int = 0
	unconfirmed_input_fields: tuple[str, ...] = ()

	def as_dict(self, *, source_run: str) -> dict:
		return {
			"proposable": self.proposable,
			"reason": self.reason,
			"procedure_graph": self.procedure_graph,
			"input_schema": self.input_schema,
			"step_count": self.step_count,
			"source_run": source_run,
			"unconfirmed_input_fields": list(self.unconfirmed_input_fields),
		}


# --------------------------------------------------------------------------------------
# Value binding -- the key design problem (see module docstring)
# --------------------------------------------------------------------------------------


def _values_equal(a: Any, b: Any) -> bool:
	"""Equality for value-binding search, made type-safe against Python's ``True == 1``
	(a boolean value must never be treated as "found" against an integer leaf) and
	whitespace/case-tolerant for strings (an LLM-formatted result may differ from the
	prompt's own casing/spacing for what is clearly the same value)."""
	if isinstance(a, bool) != isinstance(b, bool):
		return False
	if isinstance(a, str) and isinstance(b, str):
		return a == b or a.strip().lower() == b.strip().lower()
	try:
		return a == b
	except Exception:  # noqa: BLE001 -- an incomparable pair is "not equal", not a crash
		return False


def _is_trivial_constant(value: Any) -> bool:
	"""True for the small, explicitly-enumerated set of constant-looking values the task
	spec allows to be kept as a literal without an explanation (point 2(d)). See the
	``_TRIVIAL_WORDS`` docstring above for why this list is not widened further."""
	if value is None:
		return True
	if isinstance(value, bool):
		return True
	if isinstance(value, (int, float)):
		return value == 0
	if isinstance(value, str):
		return value == "" or value.strip().lower() in _TRIVIAL_WORDS
	if isinstance(value, (list, dict)):
		return len(value) == 0
	return False


def _appears_in_prompt(value: Any, prompt: str | None) -> bool:
	"""True when ``value`` (or an unambiguous stringified form of it) appears in the run's
	own ``prompt`` text -- task point 2(a). Composite values (list/dict) are deliberately
	never prompt-matched: a structural sub-match against free text is too fragile to trust
	as "this came from what the user asked" (bias toward refusing/earlier-output-matching
	instead, per the task instruction)."""
	if not prompt or not isinstance(prompt, str):
		return False
	if value is None or isinstance(value, bool):
		return False
	if isinstance(value, str):
		stripped = value.strip()
		return bool(stripped) and stripped.lower() in prompt.lower()
	if isinstance(value, (int, float)):
		# Word-boundary match, not a bare substring check -- "0" is a substring of
		# "ACME-001" and "30" is a substring of "130", neither of which means the
		# *number* 0 or 30 appears in the prompt as its own token.
		return re.search(rf"(?<!\w){re.escape(str(value))}(?!\w)", prompt) is not None
	return False


def _find_in_value(value: Any, candidate: Any, path: str = "") -> str | None:
	"""Depth-first search for ``value`` inside ``candidate`` (a prior tool call's
	``tool_result``), returning the ``Reference`` path grammar segment leading to the
	match (``""`` for a match at ``candidate``'s own root), or ``None`` if not found.

	Only descends into dict keys that are themselves valid path identifiers
	(``$defs/Reference``'s path grammar has no way to address a key like ``"a b"``) --
	such a key is simply not reachable by any legal reference, so it is skipped rather
	than raising.
	"""
	if _values_equal(value, candidate):
		return path
	if isinstance(candidate, dict):
		for key, sub in candidate.items():
			if not isinstance(key, str) or not _IDENTIFIER_RE.match(key):
				continue
			found = _find_in_value(value, sub, f"{path}.{key}" if path else key)
			if found is not None:
				return found
	elif isinstance(candidate, list):
		for index, sub in enumerate(candidate):
			found = _find_in_value(value, sub, f"{path}[{index}]" if path else f"[{index}]")
			if found is not None:
				return found
	return None


def _find_earlier_reference(value: Any, earlier_calls: list[dict], earlier_node_ids: list[str]) -> str | None:
	"""Task point 2(b): search each EARLIER tool call's ``tool_result`` for ``value``,
	nearest call first (a later step's argument is more often explained by the step that
	immediately precedes it than by one further back), and return a full
	``"<node_id>[.<path>]"`` reference to the first match found, or ``None``.
	"""
	if value is None:
		return None
	for call, node_id in reversed(list(zip(earlier_calls, earlier_node_ids))):
		path = _find_in_value(value, call.get("tool_result"))
		if path is not None:
			return f"{node_id}.{path}" if path else node_id
	return None


class ProcedureNotProposableError(Exception):
	"""Raised internally when a single argument value cannot be explained. Always carries
	the specific, user-facing refusal reason (task point 2(d)); callers that want the
	reason without an exception should call :func:`compile_procedure_from_trace` instead
	and check ``.proposable``."""

	def __init__(self, reason: str):
		self.reason = reason
		super().__init__(reason)


def _bind_argument_value(
	*,
	step_index: int,
	tool_id: str,
	arg_name: str,
	value: Any,
	prompt: str | None,
	earlier_calls: list[dict],
	earlier_node_ids: list[str],
	allow_unconfirmed_inputs: bool = True,
) -> tuple[Any, str | None, str | None]:
	"""Decide where one ``tool_args`` value came from (task point 2), in the task's own
	priority order: (a) the run's prompt, (b) an earlier tool call's result, (c) a trivial
	constant, else (d) bind as unconfirmed input (if allowed) or refuse.

	Returns ``(bound_value, input_field_name_or_None, confidence_or_None)`` where:
	- ``input_field_name`` is set for (a) and (d) bindings, telling the caller which
	  ``input_schema`` field to register.
	- ``confidence`` indicates the binding's reliability: ``"prompt"`` for (a),
	  ``"unconfirmed"`` for (d), ``None`` for (b) and (c).

	Raises :class:`ProcedureNotProposableError` for (d) when ``allow_unconfirmed_inputs``
	is False, with the exact wording the task spec asks for so the user sees precisely
	which step/tool/argument was unexplainable.
	"""
	if _appears_in_prompt(value, prompt):
		field = _snake_case(arg_name)
		return {"$from": f"input.{field}"}, field, "prompt"

	ref = _find_earlier_reference(value, earlier_calls, earlier_node_ids)
	if ref is not None:
		return {"$from": ref}, None, None

	if _is_trivial_constant(value):
		return value, None, None

	if allow_unconfirmed_inputs:
		field = _snake_case(arg_name)
		return {"$from": f"input.{field}"}, field, "unconfirmed"

	raise ProcedureNotProposableError(  # noqa: TRY003 -- user-facing refusal reason, not exception boilerplate
		f"This run made a judgment call at step {step_index} ({tool_id}) when it chose the value "
		f"for {arg_name}. That value was not taken from your request and did not come from an "
		"earlier step, so it cannot be repeated reliably next time."
	)


# --------------------------------------------------------------------------------------
# Small pure formatting helpers
# --------------------------------------------------------------------------------------


def _snake_case(name: str) -> str:
	"""Best-effort ``snake_case`` for an ``input_schema`` field name. Most tool argument
	names are already Python kwargs (already snake_case); this also copes with a
	camelCase name from an MCP tool."""
	cleaned = _NON_IDENTIFIER_CHARS_RE.sub("_", name or "").strip("_")
	cleaned = _CAMEL_BOUNDARY_RE.sub("_", cleaned)
	return cleaned.lower() or "value"


def _json_type(value: Any) -> str:
	"""JSON Schema ``type`` name for an inferred ``input_schema`` property."""
	if value is None:
		return "null"
	if isinstance(value, bool):
		return "boolean"
	if isinstance(value, int):
		return "integer"
	if isinstance(value, float):
		return "number"
	if isinstance(value, str):
		return "string"
	if isinstance(value, list):
		return "array"
	if isinstance(value, dict):
		return "object"
	return "string"


def _unique_node_id(base: str, index: int, existing: list[str], *, prefix: str = "step") -> str:
	"""A ``$defs/NodeId``-legal, collision-free node id for step ``index``. Prefixing every
	tool.call node with its 1-based step index is what makes uniqueness structural (two
	steps can share a tool name; they can never share an index) rather than something this
	function has to detect after the fact."""
	safe = _NON_IDENTIFIER_CHARS_RE.sub("_", base or "node").strip("_") or "node"
	if safe[0].isdigit():
		safe = f"n_{safe}"
	candidate = f"{prefix}{index}_{safe}" if prefix else safe
	candidate = candidate[:64]
	while candidate in existing:
		candidate = (candidate[:63] + "_") if len(candidate) >= 64 else (candidate + "_")
	return candidate


# --------------------------------------------------------------------------------------
# Compilation -- pure, frappe-free
# --------------------------------------------------------------------------------------


def compile_procedure_from_trace(
	*,
	prompt: str | None,
	response: str | None,
	tool_calls: list[dict],
	classify_tool: ToolClassifier = default_tool_classifier,
	allow_unconfirmed_inputs: bool = True,
) -> ProposalResult:
	"""Compile ``tool_calls`` (already ordered oldest-first, as recorded for one Agent
	Run) into a candidate Procedure graph, or refuse with a specific reason. Pure: no
	frappe access of its own (``classify_tool``'s default does touch frappe when called --
	the frappe-free unit tests pass a fake, exactly as ``huf.ai.procedure_conversion``'s
	tests do for the same reason).

	``tool_calls[i]`` is expected to carry ``tool`` (str), ``tool_args`` (dict),
	``tool_result`` (any JSON value), ``status`` (str) and optionally ``error_message``.

	Task point 1's requirements, in order:

	* Zero tool calls -> refuse ("no tool calls to compile").
	* Any call not cleanly ``Completed`` with a recorded ``tool_result`` -> hard stop,
	  refuse the whole proposal (never silently skip it and compile around the gap).
	* Otherwise, one ``tool.call`` node per call, chained via ``next`` in trace order,
	  terminating in one ``output`` node whose value mirrors the final tool call's own
	  result (``{"$from": "<last_node_id>"}``) -- the run's own ``response`` is free text
	  the agent composed, not a value any node in the compiled graph actually produced, so
	  it cannot be referenced from an ``output`` node's config the way a prior node's
	  recorded output can; echoing the last tool's result is what stays inside the
	  reference mechanism graph-ir.md section 4.1 defines.
	"""
	if not tool_calls:
		return ProposalResult(
			proposable=False,
			reason="This run made no tool calls, so there is nothing to compile into a procedure.",
			step_count=0,
		)

	for i, call in enumerate(tool_calls, start=1):
		if call.get("status") != _CLEAN_STATUS or not call.get("tool_result"):
			return ProposalResult(
				proposable=False,
				reason=(
					f"Step {i} ({call.get('tool')}) did not finish cleanly - it ended as "
					f"{call.get('status')}. A procedure can only be built from an answer where "
					"every step completed, so that repeating it gives the same result."
				),
				step_count=len(tool_calls),
			)
		if not call.get("tool"):
			return ProposalResult(
				proposable=False,
				reason=(
					f"Step {i} did not record which action it took, so it cannot be repeated."
				),
				step_count=len(tool_calls),
			)

	def _register_input_field(
		base_field: str, confidence: str | None, value: Any
	) -> str:
		"""Register or reuse an input field, handling collisions between different
		confidence levels by suffixing (customer_id, customer_id_2, etc). Returns the
		final (possibly suffixed) field name to use in ``$from`` references and in
		``input_props``.
		"""
		if base_field not in input_props:
			field = base_field
		elif input_props[base_field].get("x-confidence") == confidence:
			return base_field  # same field, same confidence -- reuse as today
		else:
			field = base_field
			n = 2
			while field in input_props:
				field = f"{base_field}_{n}"
				n += 1
		# Register the field with its type and confidence
		type_info = {"type": _json_type(value)}
		if confidence is not None:
			type_info["x-confidence"] = confidence
		input_props[field] = type_info
		input_required.append(field)
		# Track unconfirmed fields
		if confidence == "unconfirmed":
			unconfirmed_fields.append(field)
		return field

	node_ids: list[str] = []
	nodes: list[dict] = []
	input_props: dict[str, dict] = {}
	input_required: list[str] = []
	unconfirmed_fields: list[str] = []

	for i, call in enumerate(tool_calls, start=1):
		tool_id = call["tool"]
		args = call.get("tool_args") or {}
		if not isinstance(args, dict):
			return ProposalResult(
				proposable=False,
				reason=(
					f"Step {i} ({tool_id}) recorded its settings in a form that cannot be turned "
					"into repeatable inputs."
				),
				step_count=len(tool_calls),
			)

		bound_input: dict[str, Any] = {}
		try:
			for arg_name, value in args.items():
				bound_value, input_field, confidence = _bind_argument_value(
					step_index=i,
					tool_id=tool_id,
					arg_name=arg_name,
					value=value,
					prompt=prompt,
					earlier_calls=tool_calls[: i - 1],
					earlier_node_ids=node_ids,
					allow_unconfirmed_inputs=allow_unconfirmed_inputs,
				)
				# Update bound_value with the final field name if it's an input reference
				if input_field is not None:
					final_field = _register_input_field(input_field, confidence, value)
					bound_value = {"$from": f"input.{final_field}"}
				bound_input[arg_name] = bound_value
		except ProcedureNotProposableError as exc:
			return ProposalResult(proposable=False, reason=exc.reason, step_count=len(tool_calls))

		node_id = _unique_node_id(tool_id, i, node_ids)
		nodes.append({"id": node_id, "type": "tool.call", "config": {"tool_id": tool_id, "input": bound_input}})
		node_ids.append(node_id)

	output_id = _unique_node_id("output", len(tool_calls) + 1, node_ids, prefix="")
	for idx in range(len(nodes) - 1):
		nodes[idx]["next"] = node_ids[idx + 1]
	nodes[-1]["next"] = output_id
	nodes.append(
		{
			"id": output_id,
			"type": "output",
			"config": {"value": {"$from": node_ids[-1]}},
		}
	)

	entry = node_ids[0]
	envelope = compute_static_envelope({"entry": entry, "nodes": nodes}, classify_tool=classify_tool)
	write_steps = sum(
		1
		for node in nodes
		if node["type"] == "tool.call" and classify_tool(node["config"]["tool_id"]).ptype in _WRITE_PTYPES
	)

	input_schema = {"type": "object", "properties": input_props, "required": list(input_required)}
	contract = {
		"input_schema": input_schema,
		"output_schema": {},
		"applies_when": [],
		"permission_envelope": envelope,
		"limits": {
			"max_nodes": max(len(nodes) + 5, 10),
			"max_rows": 500,
			"max_output_bytes": 65536,
			"max_parallel_calls": 1,
			"max_foreach_iterations": 0,
			"max_external_calls": max(len(tool_calls), 1),
			"max_writes": write_steps,
			"max_wall_time_ms": 60_000,
			"fail_closed": True,
		},
	}

	procedure_graph = {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": entry,
		"nodes": nodes,
		"contract": contract,
	}
	procedure_graph["fingerprint"] = compute_fingerprint(procedure_graph)

	validation = validate_graph(procedure_graph, "procedure", classify_tool=classify_tool)
	if not validation.ok:
		reason = (
			"These steps did not pass the safety checks a saved procedure has to meet "
			f"({len(validation.errors)} problem(s) found). First one: {validation.errors[0]}"
			if validation.errors
			else "These steps did not pass the safety checks a saved procedure has to meet."
		)
		return ProposalResult(proposable=False, reason=reason, step_count=len(tool_calls))

	return ProposalResult(
		proposable=True,
		procedure_graph=procedure_graph,
		input_schema=input_schema,
		step_count=len(tool_calls),
		unconfirmed_input_fields=tuple(unconfirmed_fields),
	)


# --------------------------------------------------------------------------------------
# Server-side re-validation for Accept -- pure except for provenance's own frappe reads
# --------------------------------------------------------------------------------------


def _revalidate_procedure_graph(
	graph: Any, *, classify_tool: ToolClassifier = default_tool_classifier
) -> dict:
	"""Parse (if needed) and re-validate a client-supplied procedure graph. Raises
	:class:`~huf.ai.graph.validator.GraphValidationError` (never trusts a
	client-round-tripped graph blindly -- the user could have tampered with it in devtools
	between propose and accept) and otherwise returns the parsed graph dict, unchanged.
	"""
	if isinstance(graph, str):
		try:
			parsed = json.loads(graph)
		except (TypeError, ValueError):
			parsed = None
	else:
		parsed = graph

	if not isinstance(parsed, dict):
		raise GraphValidationError(
			validate_graph({"not": "a graph document"}, "procedure", classify_tool=classify_tool)
		)

	result = validate_graph(parsed, "procedure", classify_tool=classify_tool)
	result.raise_if_invalid()
	return parsed


def _build_procedure_document_payload(
	*,
	agent_run_name: str,
	procedure_graph: Any,
	procedure_name: str,
	classify_tool: ToolClassifier = default_tool_classifier,
) -> dict:
	"""The frappe.get_doc(...) payload for Accept, built only after
	:func:`_revalidate_procedure_graph` has passed -- mirrors
	``huf.ai.flow_api.convert_flow_to_procedure``'s shape exactly (``tier="Draft"``,
	``status="Draft"``), with a provenance block naming this as a run-proposal instead of
	a flow-conversion.
	"""
	graph = _revalidate_procedure_graph(procedure_graph, classify_tool=classify_tool)

	return {
		"doctype": "Agent Procedure",
		"procedure_id": f"{agent_run_name}-procedure",
		"procedure_name": procedure_name,
		"definition_json": frappe.as_json(graph),
		"tier": "Draft",
		"status": "Draft",
		"provenance": frappe.as_json(
			{
				"source": "run_proposal",
				"source_agent_run": agent_run_name,
				"proposed_by": frappe.session.user,
				"proposed_at": str(now_datetime()),
			}
		),
	}


# --------------------------------------------------------------------------------------
# Frappe-touching loaders
# --------------------------------------------------------------------------------------


def _as_json(value: Any) -> Any:
	"""``Agent Tool Call.tool_args`` / ``.tool_result`` are ``JSON`` fields that may come
	back from ``frappe.get_all`` either already parsed or as their raw JSON text,
	depending on how they were written -- mirrors the same defensive parse
	``huf.ai.flow_api._load_flow_graph`` uses for ``definition_json``."""
	if isinstance(value, str):
		if not value.strip():
			return None
		try:
			return json.loads(value)
		except (TypeError, ValueError):
			return value
	return value


def _load_tool_calls(agent_run_name: str) -> list[dict]:
	rows = frappe.get_all(
		"Agent Tool Call",
		filters={"agent_run": agent_run_name},
		fields=["name", "tool", "tool_args", "tool_result", "status", "error_message"],
		order_by="creation asc",
	)
	return [
		{
			"name": row.get("name"),
			"tool": row.get("tool"),
			"tool_args": _as_json(row.get("tool_args")),
			"tool_result": _as_json(row.get("tool_result")),
			"status": row.get("status"),
			"error_message": row.get("error_message"),
		}
		for row in rows
	]


def _load_agent_run(agent_run_name: str):
	doc = frappe.get_doc("Agent Run", agent_run_name)
	if not frappe.has_permission("Agent Run", "read", doc=doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _require_procedure_create_permission() -> None:
	if not frappe.has_permission("Agent Procedure", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------------------------------------------------
# Whitelisted API
# --------------------------------------------------------------------------------------


@frappe.whitelist()
def propose_procedure_from_run(agent_run_name: str) -> dict:
	"""Read-only preview: compile ``agent_run_name``'s tool-call trace into a candidate
	Procedure graph. Saves nothing -- the returned ``procedure_graph`` is only persisted if
	the user later calls :func:`accept_procedure_proposal` with it.

	Requires ``Agent Run`` read permission on this specific run AND ``Agent Procedure``
	create permission (the user must already be allowed to do both halves of what this
	endpoint is a preview of).

	Returns ``{"proposable", "reason", "procedure_graph", "input_schema", "step_count",
	"source_run"}`` -- see :class:`ProposalResult.as_dict`.
	"""
	run_doc = _load_agent_run(agent_run_name)
	_require_procedure_create_permission()

	tool_calls = _load_tool_calls(agent_run_name)
	result = compile_procedure_from_trace(
		prompt=run_doc.prompt, response=run_doc.response, tool_calls=tool_calls
	)
	return result.as_dict(source_run=agent_run_name)


@frappe.whitelist()
def accept_procedure_proposal(agent_run_name: str, procedure_graph: dict | str, procedure_name: str) -> dict:
	"""Persist a previously-proposed Procedure graph as a Draft ``Agent Procedure``.

	Re-validates ``procedure_graph`` server-side before touching the database -- never
	trusts a client-round-tripped graph blindly, since the user could have tampered with
	it in devtools between the ``propose`` preview and this call. A graph that fails
	re-validation is rejected here with the same specificity
	:func:`propose_procedure_from_run` would have given it, and nothing is written.

	Same permission requirements as :func:`propose_procedure_from_run`. Returns the same
	shape ``huf.ai.flow_api.convert_flow_to_procedure`` returns: ``{"name",
	"procedure_id", "version", "status", "tier"}``.
	"""
	_load_agent_run(agent_run_name)
	_require_procedure_create_permission()

	try:
		payload = _build_procedure_document_payload(
			agent_run_name=agent_run_name,
			procedure_graph=procedure_graph,
			procedure_name=procedure_name,
		)
	except GraphValidationError as exc:
		frappe.throw(str(exc), title=_("Procedure Is Not Valid"))

	procedure = frappe.get_doc(payload)
	procedure.insert()

	return {
		"name": procedure.name,
		"procedure_id": procedure.procedure_id,
		"version": procedure.version,
		"status": procedure.status,
		"tier": procedure.tier,
	}


__all__ = [
	"ProcedureNotProposableError",
	"ProposalResult",
	"accept_procedure_proposal",
	"compile_procedure_from_trace",
	"propose_procedure_from_run",
]
