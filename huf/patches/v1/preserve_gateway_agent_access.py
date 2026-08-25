import frappe


def execute():
	"""Preserve existing behavior for Agents already reachable via a Gateway.

	huf.ai.gateway_service.process_gateway_event now requires an Agent to have
	allow_guest=1 before it can be invoked through a Gateway Binding (there is
	no mechanism mapping an external gateway sender to a specific HUF user, so
	gateway-routed runs are authorized as if the caller were Guest -- see
	Tracks/AgentPermissionsAudit/AGENT_PERMISSIONS_AUDIT.md, finding F1).

	Before this change, gateway-routed runs executed under the Gateway's
	configured service user regardless of allow_guest, so any Agent already
	bound to an enabled Gateway Binding was reachable. Flipping the default
	the day this patch runs would silently break every live gateway
	integration. This patch sets allow_guest=1 on exactly those Agents, once,
	so existing deployments keep working; any *new* Gateway Binding created
	after this patch runs must have its target Agent's "Allow Public /
	Unauthenticated Access" switch turned on explicitly, same as any other
	guest-facing agent.
	"""
	agent_names = frappe.get_all(
		"Gateway Binding",
		filters={"is_enabled": 1, "target_type": "Agent"},
		pluck="agent",
		distinct=True,
	)
	agent_names = [name for name in agent_names if name]
	if not agent_names:
		return

	already_guest = set(
		frappe.get_all(
			"Agent",
			filters={"name": ["in", agent_names], "allow_guest": 1},
			pluck="name",
		)
	)
	to_update = [name for name in agent_names if name not in already_guest]
	if not to_update:
		return

	for agent_name in to_update:
		try:
			frappe.db.set_value("Agent", agent_name, "allow_guest", 1, update_modified=False)
		except Exception as e:
			frappe.log_error(
				title="Preserve Gateway Agent Access",
				message=f"Could not backfill allow_guest for gateway-bound Agent '{agent_name}': {e}",
			)

	frappe.db.commit()
