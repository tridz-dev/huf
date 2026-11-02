"""One-step "make this agent answer this channel credential" endpoints (see ``huf.ai.gateway_service``)."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
from huf.ai.gateway_core.redaction import _redact_error_text


def _provider_for_service(service: str) -> str | None:
	"""The ``Gateway.provider`` option whose canonical id is ``service`` (None when it isn't a channel)."""
	options = frappe.get_meta("Gateway").get_field("provider").options or ""
	for option in options.split("\n"):
		if option.strip() and provider_to_service_id(option.strip()) == service:
			return option.strip()
	return None


@frappe.whitelist(methods=["GET"])
def get_channel_agent_connection(integration_settings: str) -> dict:
	"""Which gateways use this channel credential and which agent each one answers with."""
	from huf.ai.gateway_service import _require_gateway_admin

	_require_gateway_admin()
	service = frappe.db.get_value("Integration Settings", integration_settings, "service")
	if not service:
		frappe.throw(_("Channel credential {0} not found.").format(integration_settings))
	gateways = frappe.get_all(
		"Gateway",
		filters={"integration_settings": integration_settings},
		fields=["name", "is_enabled", "default_target_type", "default_agent", "default_flow"],
		order_by="creation asc",
	)
	return {"service": service, "provider": _provider_for_service(service), "gateways": gateways}


@frappe.whitelist(methods=["POST"])
def connect_agent_to_channel(integration_settings: str, agent: str, gateway_name: str | None = None) -> dict:
	"""Make ``agent`` answer messages on a channel credential, in one step.

	Uses the credential's gateway (or ``gateway_name`` when several share it), creating one when there
	is none, sets the agent as its default route and attaches the channel's tools to the agent. A new
	gateway starts with the Pairing policy, so strangers still need approval.
	"""
	from huf.ai.gateway_service import _require_gateway_admin

	_require_gateway_admin()
	if not frappe.db.exists("Agent", agent):
		frappe.throw(_("Agent {0} not found.").format(agent))
	if not frappe.has_permission("Agent", "write", doc=agent):
		frappe.throw(_("You can't change agent {0}.").format(agent), frappe.PermissionError)
	settings = frappe.get_doc("Integration Settings", integration_settings)
	provider = _provider_for_service(settings.service)
	if not provider:
		frappe.throw(_("{0} is not a messaging channel.").format(settings.service))

	filters: dict[str, Any] = {"integration_settings": settings.name}
	if gateway_name:
		filters["name"] = gateway_name
	existing = frappe.get_all("Gateway", filters=filters, pluck="name", order_by="creation asc", limit=1)
	created = not existing
	if existing:
		gateway = frappe.get_doc("Gateway", existing[0])
		previous_agent = gateway.default_agent if gateway.default_target_type == "Agent" else None
	else:
		agent_label = frappe.db.get_value("Agent", agent, "agent_name") or agent
		name = f"{provider} - {agent_label}"
		if frappe.db.exists("Gateway", name):
			name = f"{name} ({settings.name})"
		gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": name,
				"provider": provider,
				"integration_settings": settings.name,
				"is_enabled": 0,
				"direct_policy": "Pairing",
				"execution_user": frappe.session.user,
			}
		)
		previous_agent = None
	gateway.default_target_type = "Agent"
	gateway.default_agent = agent
	gateway.default_flow = None
	gateway.flags.ignore_permissions = True
	gateway.save()

	enable_error = ""
	if not gateway.is_enabled:
		# Turn it on when everything it needs is in place; otherwise leave it off and say why.
		try:
			gateway.is_enabled = 1
			gateway.save()
		except frappe.ValidationError as exc:
			frappe.clear_last_message()
			gateway.reload()
			enable_error = _redact_error_text(str(exc))

	from huf.ai.tools.integration_utils import _get_tools_for_service

	tool_names = [t["name"] for t in _get_tools_for_service(settings.service)]
	agent_doc = frappe.get_doc("Agent", agent)
	have = {row.tool for row in agent_doc.agent_tool or []}
	added = [t for t in tool_names if t not in have]
	for tool in added:
		agent_doc.append("agent_tool", {"tool": tool})
	if added:
		agent_doc.save()

	return {
		"gateway": gateway.name,
		"created": created,
		"enabled": bool(gateway.is_enabled),
		"enable_error": enable_error,
		"previous_agent": previous_agent if previous_agent != agent else None,
		"tools_added": len(added),
	}
