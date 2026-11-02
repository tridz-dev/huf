"""Who may point a flow at a chat channel, at save and at publish.

A chat trigger starts runs from messages strangers send, as the flow's owner. So: the saver must be able to write the
Gateway it names, a WhatsApp or Telegram node needs a Gateway of that provider, and a published flow's owner must still
be able to use that Gateway (else the flow would silently never start). Chat triggers also count as sensitive in
``publish_guard`` (``flows.publish_sensitive``). Warnings (double reply) never block.
"""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.flow.gateways.registry import GATEWAY_NODE_TYPES, provider_for_node_type

REPLY_TOOLS = frozenset({"gateway_send", "gateway_reply", "whatsapp", "telegram", "messenger"})
OUTPUT_TYPE = "output"


def gateway_nodes(defn) -> list[tuple[dict, str]]:
	"""``[(node, gateway_name)]`` for every chat trigger node of ``defn`` (gateway may be blank)."""
	found = []
	for node in (defn.get("nodes") or []) if isinstance(defn, dict) else []:
		if isinstance(node, dict) and node.get("type") in GATEWAY_NODE_TYPES:
			config = node.get("config") if isinstance(node.get("config"), dict) else {}
			found.append((node, str(config.get("gateway") or "").strip()))
	return found


def provider_lookup(name):
	return frappe.db.get_value("Gateway", name, "provider") if name else None


def check_gateway_authority(defn, user: str | None = None, owner: str | None = None) -> None:
	"""Raise PermissionError / ValidationError unless ``user`` may bind every chat trigger's Gateway.

	A blank gateway is fine in a draft (publish reports it). ``owner`` (the flow's owner, when it is not the saver and
	the flow is going live) must also be able to write the Gateway.
	"""
	user = user or frappe.session.user
	for node, gateway in gateway_nodes(defn):
		if not gateway:
			continue
		if not frappe.db.exists("Gateway", gateway) or not frappe.has_permission("Gateway", "write", doc=gateway, user=user):
			frappe.throw(_("Node {0}: you need write access to Gateway {1} to use it as a trigger.").format(node.get("id"), gateway), frappe.PermissionError)
		wanted = provider_for_node_type(node.get("type"))
		if wanted and provider_lookup(gateway) != wanted:
			frappe.throw(_("Node {0}: {1} is not a {2} channel.").format(node.get("id"), gateway, wanted), frappe.ValidationError)
		if owner and owner != user and not frappe.has_permission("Gateway", "write", doc=gateway, user=owner):
			frappe.throw(
				_("The owner of this flow cannot use {0}, so it would never start. Ask {1} to publish it, or make yourself its owner.").format(gateway, owner),
				frappe.PermissionError,
			)


def trigger_problems(defn) -> list[str]:
	"""Provider-aware option problems (the generic node knows its channel's provider). Not repeated from the plain check."""
	from huf.ai.flow.gateways.registry import gateway_trigger_problems

	return gateway_trigger_problems(defn, provider_lookup)


def double_reply_warning(defn) -> str | None:
	"""Warn (never block) when a flow both sends a reply itself and ends with an output the channel would also send."""
	if not gateway_nodes(defn):
		return None
	nodes = defn.get("nodes") or []
	sends = any(isinstance(n, dict) and n.get("type") == "tool.call" and (n.get("config") or {}).get("tool_id") in REPLY_TOOLS for n in nodes)
	has_output = any(isinstance(n, dict) and n.get("type") == OUTPUT_TYPE and (n.get("config") or {}).get("value") not in (None, "") for n in nodes)
	if sends and has_output:
		return _("This flow sends a reply itself and also ends with an answer. The person may be told twice; the reply sent by the step wins.")
	return None
