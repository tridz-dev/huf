"""``state.get`` / ``state.set`` / ``state.delete`` node execution: per-key flow state.

Moved out of ``huf.ai.flow.engine`` unchanged; ``engine`` re-exports these names. ``_context_of`` is reached through a
function-level ``from huf.ai.flow import engine`` to avoid an import cycle.
"""

import frappe

from huf.ai.flow import state as flow_state
from huf.ai.flow.runs import member as flow_member
from huf.ai.graph.error_copy import plain_error, step_ref


def _state_node(flow_run, node: dict, config: dict, settings: dict, allowed: set, op):
	"""Shared shell: validate config keys, resolve inputs, scope to the *running* flow."""
	from huf.ai.flow import engine

	unknown = sorted(set(config) - allowed - {"scope"})
	if unknown or config.get("scope") not in (None, "flow", "member"):
		return {"status": "failed", "error": f'{step_ref(node, True)} has settings this step does not use. Remove them and save again.'}
	flow_id = getattr(flow_run, "flow_id", None)
	ctx = engine._context_of(flow_run, settings)
	resolved = {k: ctx.resolve(v) for k, v in config.items() if k != "scope"}
	if config.get("scope") == "member":  # one value per person, kept apart from every other person's
		scoped = flow_member.scoped_state_key(flow_run, resolved.get("key"))
		if not scoped:
			return {"status": "failed", "error": f'{step_ref(node, True)} is saved per person, but this run does not know who it is about.'}
		resolved["key"] = scoped
	try:
		output = op(flow_id, resolved)
	except flow_state.FlowStateError as exc:
		return {"status": "failed", "error": plain_error(str(exc))}
	except frappe.QueryDeadlockError:  # another run saved the same key at the same moment
		return {"status": "failed", "error": f'{step_ref(node, True)} could not save because another run was saving the same data at that moment. Run it again.'}
	return {"status": "success", "result": output, "output": output}


def _exec_state_get(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.get``: config ``key`` (required), ``default``. Output ``{"found": bool, "value": ...}``."""

	def op(flow_id, cfg):
		found, value = flow_state.get_state(flow_id, cfg.get("key"))
		return {"found": found, "value": value if found else cfg.get("default")}

	return _state_node(flow_run, node, config, settings, {"key", "default"}, op)


def _exec_state_set(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.set``: config ``key``, ``value``, ``ttl_seconds`` (default 24h). Output ``{"stored": true}``."""

	def op(flow_id, cfg):
		flow_state.set_state(flow_id, cfg.get("key"), cfg.get("value"), cfg.get("ttl_seconds"))
		return {"stored": True}

	return _state_node(flow_run, node, config, settings, {"key", "value", "ttl_seconds"}, op)


def _exec_state_delete(flow_run, node: dict, config: dict, settings: dict) -> dict:
	"""``state.delete``: config ``key``. Output ``{"deleted": bool}``."""

	def op(flow_id, cfg):
		return {"deleted": flow_state.delete_state(flow_id, cfg.get("key"))}

	return _state_node(flow_run, node, config, settings, {"key"}, op)
