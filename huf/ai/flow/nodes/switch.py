"""``router.decision`` node: route by rule, first matching option wins.

Config: ``options`` (``[{label, node_id, expression}]``, checked in order) and ``default`` (a node id, taken when no
option matches or when there are no options). An option whose ``expression`` is empty never matches. The expression
language is the shared graph-IR language used by ``condition``. An expression that cannot be checked fails the node,
so the run follows its ``on_error`` route.
"""

from __future__ import annotations

from huf.ai.graph.expressions import ExpressionLimitError, evaluate_bool, parse_expression


def exec_switch(flow_run, node: dict, config: dict, settings: dict, context) -> dict:
	default = config.get("default")
	if not default:
		return {"status": "failed", "error": "Choose which path to take by default, then run again."}

	roots = context.reference_roots()
	for option in config.get("options") or []:
		if not isinstance(option, dict) or not option.get("node_id") or not option.get("expression"):
			continue
		try:
			matched = evaluate_bool(parse_expression(option["expression"]), roots, raise_limits=True)
		except Exception as e:
			return {
				"status": "failed",
				"error": str(e) if isinstance(e, ExpressionLimitError) else "This path rule could not be checked against the data it received. Check what you compare, and that earlier steps give it that data.",
			}
		if matched:
			label = option.get("label") or option["node_id"]
			return {
				"status": "success",
				"next_node_id": option["node_id"],
				"output": {"case": label, "node_id": option["node_id"]},
			}

	return {
		"status": "success",
		"next_node_id": default,
		"output": {"case": None, "node_id": default},
	}
