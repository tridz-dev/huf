"""Utilities for finding Decision Policy references in active Flow Definitions.

Provides `get_policy_references()` for scanning Flow Definitions to locate
router.decision nodes that reference a given policy by name.
"""

import json
import frappe
from typing import List, Dict, Any


def get_policy_references(policy_name: str) -> List[Dict[str, Any]]:
	"""Find all active Flow Definitions that reference a Decision Policy.

	Scans active Flow Definition rows, parses their definition_json graphs,
	and identifies all router.decision nodes that reference the given policy_name.

	Args:
		policy_name: The name of the Decision Policy to search for.

	Returns:
		List of dicts with keys:
		- flow_id: str, the Flow Definition flow_id
		- flow_name: str, the Flow Definition flow_name
		- node_id: str, the node_id of the router.decision node
		- node_label: str, human-readable label if available
		- flow_def_name: str, the Flow Definition document name (usually same as flow_id)

		Empty list if no references found.
	"""
	if not policy_name:
		return []

	references = []

	# Query all active Flow Definitions
	flow_definitions = frappe.get_all(
		"Flow Definition",
		filters={"status": "Active"},
		fields=["name", "flow_id", "flow_name", "definition_json"],
		limit_page_length=None,
	)

	for flow_def in flow_definitions:
		try:
			# Parse the definition_json to check for router.decision nodes
			definition = json.loads(flow_def.get("definition_json", "{}"))
			if not isinstance(definition, dict):
				continue

			# The graph is typically under definition["graph"]["nodes"] or similar
			# Check both direct nodes and nested graphs
			nodes = _extract_nodes_from_graph(definition)

			for node in nodes:
				if _is_decision_router_node(node, policy_name):
					references.append({
						"flow_id": flow_def.get("flow_id"),
						"flow_name": flow_def.get("flow_name"),
						"node_id": node.get("id", "unknown"),
						"node_label": node.get("label", node.get("id", "unknown")),
						"flow_def_name": flow_def.get("name"),
					})
		except (json.JSONDecodeError, ValueError, KeyError):
			# Skip malformed definitions
			continue

	return references


def _extract_nodes_from_graph(definition: Dict[str, Any]) -> List[Dict[str, Any]]:
	"""Extract all nodes from a flow definition graph.

	Handles nested graph structures (graph.nodes, or direct nodes list).

	Args:
		definition: The parsed definition_json dict.

	Returns:
		List of node dicts.
	"""
	nodes = []

	# Check if definition has a "graph" key (most common)
	if "graph" in definition and isinstance(definition["graph"], dict):
		graph = definition["graph"]
		if "nodes" in graph and isinstance(graph["nodes"], list):
			nodes.extend(graph["nodes"])
		# Also check for direct properties if it looks like the graph itself is nodes
		if "type" in graph and graph["type"] == "FlowGraph":
			# Might be nodes at a different level
			pass

	# Also check for nodes at the root level (some formats)
	if "nodes" in definition and isinstance(definition["nodes"], list):
		nodes.extend(definition["nodes"])

	return nodes


def _is_decision_router_node(node: Dict[str, Any], policy_name: str) -> bool:
	"""Check if a node is a router.decision node that references the policy.

	Args:
		node: The node dict from the graph.
		policy_name: The policy name to match.

	Returns:
		True if the node is a router.decision referencing the policy_name.
	"""
	if not isinstance(node, dict):
		return False

	# Check if it's a router.decision node
	if node.get("type") != "router.decision":
		return False

	# Check if the config has a policy field matching policy_name
	config = node.get("config", {})
	if isinstance(config, dict):
		return config.get("policy") == policy_name

	return False
