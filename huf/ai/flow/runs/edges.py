"""Decode a graph's node-native routing pointers into the edge list the router routes over."""

from __future__ import annotations


def edges_from_nodes(nodes: list) -> list[dict]:
	"""Decode the graph IR's node-native routing pointers into ``{from, to, type, meta}`` edges.

	``next`` and ``on_error`` apply to every node; the self-routing types carry their targets in
	``config``: ``condition.on_true`` / ``on_false`` / ``fallback_next``, ``router.llm`` / ``router.decision``
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
			if config.get("fallback_next"):
				edges.append({"from": node_id, "to": config["fallback_next"], "type": "always", "meta": {"label": "fallback"}})
		elif node_type in ("router.llm", "router.decision", "split"):
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
