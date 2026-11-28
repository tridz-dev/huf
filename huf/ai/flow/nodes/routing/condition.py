# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""A condition that reads ``facts.<name>`` (H-W2-22): facts come from app providers for this evaluation only.

Anything that stops the facts from being known takes the node's ``fallback_next`` branch and records a reason code
under ``context_json._huf_reasons[node id]``; it never counts as true. Only the yes/no result is stored.
"""

from huf.ai.flow.support import facts
from huf.ai.graph.expressions import evaluate_bool

REASONS_KEY = "_huf_reasons"


def exec_facts_condition(flow_run, node: dict, config: dict, ctx, parsed) -> dict:
	names, dynamic = facts.names_used(parsed)
	node_id = node.get("id")
	_clear_reason(ctx, node_id)

	values, reason = None, facts.FACTS_ERROR
	if not dynamic:
		values, reason = facts.lookup(
			getattr(flow_run, "flow_id", None), getattr(flow_run, "member_key", None), names
		)
	if reason is None:
		try:
			result = evaluate_bool(parsed, {**ctx.reference_roots(), facts.ROOT: values}, raise_limits=True)
		except Exception:  # noqa: BLE001 - fail closed, without a message that could hold a value
			reason = facts.FACTS_ERROR
		else:
			return {
				"status": "success",
				"result": result,
				"output": result,
				"branch": "true" if result else "false",
				"next_node_id": config["on_true"] if result else config["on_false"],
			}

	ctx.set(REASONS_KEY, {**(ctx.data.get(REASONS_KEY) or {}), node_id: reason})
	fallback = config.get("fallback_next")
	if not fallback:
		return {
			"status": "failed",
			"error": "The facts this check needs could not be read, and no fallback step is chosen.",
			"reason_code": reason,
		}
	return {
		"status": "success",
		"result": False,
		"output": False,
		"branch": "fallback",
		"next_node_id": fallback,
		"reason_code": reason,
	}


def _clear_reason(ctx, node_id) -> None:
	reasons = ctx.data.get(REASONS_KEY)
	if isinstance(reasons, dict) and node_id in reasons:
		ctx.set(REASONS_KEY, {k: v for k, v in reasons.items() if k != node_id})
