"""Per-step validator checks: tool ids, app-registered step types and the flow-level ``error_handler``."""

from __future__ import annotations

from huf.ai.graph.validation.result import ValidationError


def registered_node_types() -> frozenset[str]:
	"""Step types installed apps register through the ``huf_flow_nodes`` hook."""
	from huf.ai.flow.catalog import node_registry

	return frozenset(node_registry.registered_types())


def check_app_node_validators(nodes: list[dict], profile: str) -> list[ValidationError]:
	"""Each app step type's own ``validate`` hook (Flow profile, publish only)."""
	if profile != "flow":
		return []
	from huf.ai.flow.catalog import node_registry

	return [
		ValidationError("NODE_CONFIG", node.get("id"), "config", problem)
		for node in nodes
		if isinstance(node, dict)
		for problem in node_registry.validate_node_config(node)
	]


def check_error_handler_target(graph: dict, nodes_by_id: dict[str, dict]) -> list[ValidationError]:
	"""``error_handler.next`` must point at a step that exists."""
	handler_id = (graph.get("error_handler") or {}).get("next")
	if handler_id and handler_id not in nodes_by_id:
		return [
			ValidationError(
				"DANGLING_TARGET",
				None,
				"error_handler.next",
				f"error_handler.next points at node id {handler_id!r}, which does not exist in this graph",
			)
		]
	return []


def check_tool_ids_literal(nodes: list[dict]) -> list[ValidationError]:
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
