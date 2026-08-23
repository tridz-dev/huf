# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Pure, frappe-free helpers for Agent Procedure version identity (T-20).

This module deliberately has zero import-time dependency on ``frappe`` so it can be
unit-tested with plain ``pytest`` (no bench, no stub) as well as on a real bench. All
Frappe-specific plumbing (Document, frappe.throw, DB access) stays in
``huf/huf/doctype/agent_procedure/agent_procedure.py``, which imports this module and
wraps its exceptions.

Implements spec/graph-ir.md section 7 (version identity / fingerprint) and section 6 /
the T-20 task card requirement to structurally reject Flow-only node types.
"""

import hashlib
import json

# Node types that exist only in the Flow profile (spec/graph-ir.md section 1) and must
# never be reachable inside an Agent Procedure graph (I3, I4). ``trigger.*`` node types
# are Flow-only for the same reason (a Procedure graph has no trigger, per section 4.1)
# and are rejected alongside the three the task card names explicitly.
FLOW_ONLY_NODE_TYPES = frozenset(
	{
		"agent.run",
		"router.llm",
		"human.approval",
		"trigger.webhook",
		"trigger.schedule",
		"trigger.doc-event",
	}
)

# The three node types the T-20 task card names explicitly (a subset of
# FLOW_ONLY_NODE_TYPES) -- kept as a separate constant so error messages and tests can
# distinguish "the task card's three" from the superset this module additionally
# rejects for the same underlying reason.
TASK_CARD_FLOW_ONLY_NODE_TYPES = frozenset({"agent.run", "router.llm", "human.approval"})


class FlowOnlyNodeError(ValueError):
	"""Raised when a graph destined for the Procedure profile contains a Flow-only node."""

	def __init__(self, node_id, node_type):
		self.node_id = node_id
		self.node_type = node_type
		super().__init__(
			f"Node '{node_id}' has Flow-only type '{node_type}', not allowed in an Agent Procedure"
		)


def _iter_all_nodes(definition: dict):
	"""Yield every node dict in a graph, including ``foreach.body`` / ``parallel.branches``
	members (spec/graph-ir.md 2.1, 2.2, 6). These are stored in the top-level ``nodes``
	array (nodes are referenced by id from ``foreach``/``parallel`` config, not nested),
	so a flat walk of ``definition["nodes"]`` already reaches everything -- this helper
	exists to make that invariant explicit and to be the single place that changes if a
	future schema revision nests node bodies inline instead of by id-reference.
	"""
	nodes = definition.get("nodes")
	if not isinstance(nodes, list):
		return
	for node in nodes:
		if isinstance(node, dict):
			yield node


def find_flow_only_nodes(definition: dict) -> list:
	"""Return a list of (node_id, node_type) pairs for every Flow-only node present.

	Empty list means the graph is structurally valid for the Procedure profile.
	"""
	found = []
	for node in _iter_all_nodes(definition):
		node_type = node.get("type")
		if node_type in FLOW_ONLY_NODE_TYPES:
			found.append((node.get("id"), node_type))
	return found


def assert_no_flow_only_nodes(definition: dict) -> None:
	"""Raise FlowOnlyNodeError on the first Flow-only node found. No-op otherwise."""
	found = find_flow_only_nodes(definition)
	if found:
		node_id, node_type = found[0]
		raise FlowOnlyNodeError(node_id, node_type)


def canonical_json_bytes(definition: dict) -> bytes:
	"""Canonicalize a graph document for fingerprinting (spec/graph-ir.md section 7).

	- The ``fingerprint`` key is removed first (it cannot be self-referential).
	- Object keys are sorted lexicographically at every level (``sort_keys=True``).
	- No insignificant whitespace (compact separators).
	- UTF-8 bytes, non-ASCII left as-is (``ensure_ascii=False``) so the canonical form is
	  stable regardless of locale-driven escaping choices.

	This is not a full RFC 8785 (JSON Canonicalization Scheme) implementation -- in
	particular it does not re-serialize floats to JCS's exact minimal form -- but for
	graphs (which carry no floating-point node config in the benchmarks this IR targets)
	it is deterministic and produces identical bytes for identical content, which is the
	only property section 7 actually requires ("the exact library is a T-20/T-22
	implementation choice ... provided it is deterministic").
	"""
	without_fingerprint = {k: v for k, v in definition.items() if k != "fingerprint"}
	return json.dumps(
		without_fingerprint,
		sort_keys=True,
		separators=(",", ":"),
		ensure_ascii=False,
	).encode("utf-8")


def compute_fingerprint(definition: dict) -> str:
	"""sha256 hex digest of the canonical form. Deterministic: identical content in,
	identical fingerprint out, regardless of docname, site, or timestamps -- none of
	which are part of ``definition`` in the first place, which is what keeps the key
	namespace open to future site-scoped-plus-templates reuse (D4): the fingerprint
	identifies content, never where or how many times it is bound.
	"""
	return hashlib.sha256(canonical_json_bytes(definition)).hexdigest()


def extract_contract_fields(definition: dict) -> dict:
	"""Pull the denormalized query-convenience fields out of ``definition['contract']``.

	Agent Procedure stores these as first-class columns (input_schema, output_schema,
	applicability, permission_envelope, is_read_only, contains_writes, contains_code) so
	they are filterable/reportable without parsing JSON, but ``definition_json`` (via its
	embedded ``contract``) remains the single source of truth -- these are always derived,
	never edited independently.
	"""
	contract = definition.get("contract") or {}
	permission_envelope = contract.get("permission_envelope") or {}
	write = permission_envelope.get("write")
	code = permission_envelope.get("code")

	contains_writes = bool(write)
	contains_code = code not in (None, "none", [], "")

	return {
		"input_schema": contract.get("input_schema"),
		"output_schema": contract.get("output_schema"),
		"applicability": contract.get("applies_when"),
		"permission_envelope": permission_envelope,
		"contains_writes": contains_writes,
		"contains_code": contains_code,
		"is_read_only": not contains_writes,
	}


# Fields on the graph document (as embedded in definition_json) that participate in the
# content fingerprint and are therefore immutable once a version row has been inserted.
# Kept here (rather than duplicated in the controller) so the controller's structural
# immutability guard and this module's own fingerprinting agree on what "content" means.
CONTENT_FIELDS = (
	"definition_json",
	"input_schema",
	"output_schema",
	"applicability",
	"permission_envelope",
	"is_read_only",
	"contains_writes",
	"contains_code",
	"fingerprint",
	"schema_version",
	"procedure_id",
	"version",
)
