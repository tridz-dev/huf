# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Schema stage of the graph validator, and the two strengths it can be read at.

Split out of ``validator.py``, which re-exports every public name here. ``draft`` mode (UX-17) lets a half-built
flow through the schema stage: a step that is merely missing a setting, or has it empty, is not a reason to refuse
the save. Everything else the schema says (wrong types, unknown settings, unknown step types) still refuses.
"""

from __future__ import annotations

import json
import os

from jsonschema import Draft202012Validator

from huf.ai.graph.validation.result import ValidationError

# The Graph IR schema is the contract shared by the validator, the Agent Procedure DocType and
# Flow. It lives beside the validator as a data file so there is exactly ONE copy in the app -- an
# embedded literal here would be a second copy of the contract, free to drift from the first.
_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graph_ir.schema.json")

with open(_SCHEMA_PATH, encoding="utf-8") as _f:
	GRAPH_IR_SCHEMA: dict = json.load(_f)

_PROFILE_SCHEMA_DEF: dict[str, str] = {
	"procedure": "ProcedureGraph",
	"flow": "FlowGraph",
}

#: How strictly :func:`validate_graph` reads a document. ``publish`` is the full gate a graph must pass before
#: it may run or go live. ``draft`` accepts a half-built flow (steps may lack required settings, nothing
#: needs to be connected yet) and only refuses a document that is structurally broken: unreadable shape,
#: unknown step types, duplicate ids, links to steps that do not exist, limits over policy.
MODE_DRAFT = "draft"
MODE_PUBLISH = "publish"

#: JSON-schema keywords that only say "this setting is missing or empty": fine in a draft, fatal on publish.
_UNFINISHED_KEYWORDS: frozenset[str] = frozenset({"required", "minLength", "minItems"})


# --------------------------------------------------------------------------------------
# 1. Schema conformance
# --------------------------------------------------------------------------------------


def _node_defs_by_type(profile: str) -> dict[str, str]:
	"""``node type -> $defs name`` for the profile's node union (``FlowNode`` / ``ProcedureNode``)."""
	union = "FlowNode" if profile == "flow" else "ProcedureNode"
	defs = GRAPH_IR_SCHEMA["$defs"]
	out: dict[str, str] = {}
	for branch in defs[union]["oneOf"]:
		name = branch["$ref"].rsplit("/", 1)[-1]
		for part in defs[name].get("allOf", []):
			const = (part.get("properties") or {}).get("type", {}).get("const")
			if const:
				out[const] = name
	return out


def _leaf_error(err):
	"""The deepest (most specific) jsonschema error under ``err``."""
	if err.context:
		return _leaf_error(max(err.context, key=lambda sub: len(list(sub.absolute_path))))
	return err


def _is_unfinished(err, prefix: list) -> bool:
	"""True when ``err`` only says a step setting is missing or empty (``nodes[i].config...``).

	``prefix`` is the path of the document ``err`` was raised against, relative to the graph root (empty for the graph itself).
	"""
	leaf = _leaf_error(err)
	full_path = prefix + list(leaf.absolute_path)
	if not (len(full_path) >= 3 and full_path[0] == "nodes" and full_path[2] == "config" and leaf.validator in _UNFINISHED_KEYWORDS):
		return False
	# "Too short" only counts as unfinished when there is nothing there yet. A secret that is typed but weak
	# is a wrong value, never stored (WP11).
	if leaf.validator == "minLength":
		return leaf.instance == ""
	if leaf.validator == "minItems":
		return leaf.instance == []
	return True


def _check_schema(graph: dict, profile: str, draft: bool = False) -> list[ValidationError]:
	def_name = _PROFILE_SCHEMA_DEF[profile]
	subschema = {"$defs": GRAPH_IR_SCHEMA["$defs"], "$ref": f"#/$defs/{def_name}"}
	validator = Draft202012Validator(subschema)
	node_defs = _node_defs_by_type(profile)
	errors: list[ValidationError] = []
	for err in sorted(validator.iter_errors(graph), key=lambda e: [str(p) for p in e.path]):
		path = list(err.path)
		if err.context and len(path) == 2 and path[0] == "nodes" and isinstance(path[1], int):
			# A node failed the node-type ``oneOf``: jsonschema flattens every branch's errors
			# together, which is useless for naming the real problem. Re-validate against the one
			# definition that matches the node's own type instead.
			node = graph["nodes"][path[1]]
			ntype = node.get("type") if isinstance(node, dict) else None
			if ntype not in node_defs:
				errors.append(
					ValidationError(
						code="SCHEMA",
						node_id=_node_id_from_path(graph, path),
						field="type",
						message=f"node type {ntype!r} is not a supported node type",
					)
				)
				continue
			node_validator = Draft202012Validator({"$defs": GRAPH_IR_SCHEMA["$defs"], "$ref": f"#/$defs/{node_defs[ntype]}"})
			for sub in sorted(node_validator.iter_errors(node), key=lambda e: [str(p) for p in e.path]):
				full = path + list(sub.absolute_path)
				if draft and _is_unfinished(sub, path):
					continue
				errors.append(
					ValidationError(
						code="SCHEMA",
						node_id=_node_id_from_path(graph, full),
						field=_field_from_path(full),
						message=_leaf_message(sub),
					)
				)
			continue
		if draft and _is_unfinished(err, []):
			continue
		errors.append(
			ValidationError(
				code="SCHEMA",
				node_id=_node_id_from_path(graph, path),
				field=_field_from_path(path),
				message=_leaf_message(err),
			)
		)
	return errors


def _leaf_message(err) -> str:
	"""Deepest (most specific) message of a jsonschema error (recurses into ``.context``)."""
	if err.context:
		best = max(err.context, key=lambda sub: len(list(sub.absolute_path)))
		return _leaf_message(best)
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
