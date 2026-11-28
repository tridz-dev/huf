"""Whom the steps of an app-owned flow may reach.

A live ``handoff`` marks a contact ``handed_off`` and may copy their transcript to CRM or helpdesk. So in an
app-owned flow it may only name the run's own member: ``recipient: "$member"``, no ``conversation``, and an empty
``message``. The Gateway of a ``handoff`` or ``send.message`` step is written in the flow, never computed while it
runs. An app editor may keep a Gateway the flow already uses; another one must be listed by the flow's app
(:mod:`huf.ai.flow.app_scope.gateways`).
"""

import frappe

from huf.ai.channels import recipient_binder
from huf.ai.flow.app_scope.gateways import app_gateways

GATEWAY_STEP_TYPES = frozenset({"handoff", "send.message"})


def _steps(nodes) -> list[tuple[dict, dict]]:
	return [
		(node, node["config"] if isinstance(node.get("config"), dict) else {})
		for node in nodes
		if isinstance(node, dict) and node.get("type") in GATEWAY_STEP_TYPES
	]


def targets_only_member(config: dict) -> bool:
	"""Whether a ``handoff`` config can reach nobody but the run's member, and sends them nothing."""
	return (
		recipient_binder.is_member_ref(config.get("recipient"))
		and config.get("conversation") in (None, "")
		and config.get("message") == ""
	)


def handoff_problems(nodes) -> list[str]:
	"""Ids of the ``handoff`` steps that could reach someone else or send a message."""
	return [
		node.get("id")
		for node, config in _steps(nodes)
		if node["type"] == "handoff" and not targets_only_member(config)
	]


def computed_gateways(nodes) -> list[str]:
	"""Ids of the steps whose Gateway is not a name written in the flow."""
	return [
		node.get("id")
		for node, config in _steps(nodes)
		if config.get("gateway") is not None
		and (not isinstance(config["gateway"], str) or config["gateway"].lstrip().startswith("{"))
	]


def gateway_names(nodes) -> set[str]:
	return {
		config["gateway"]
		for _node, config in _steps(nodes)
		if isinstance(config.get("gateway"), str) and config["gateway"].strip()
	}


def unauthorised_gateways(old_nodes, new_nodes, app: str, user: str) -> list[str]:
	"""Gateways ``new_nodes`` adds to the flow that ``app`` does not let ``user`` pick (or that do not exist)."""
	added = gateway_names(new_nodes) - gateway_names(old_nodes)
	if not added:
		return []
	allowed = app_gateways(app, user)
	return sorted(name for name in added if name not in allowed or not frappe.db.exists("Gateway", name))
