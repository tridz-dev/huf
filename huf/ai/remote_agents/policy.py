"""Remote Agent Policy resolution for inbound and outbound remote-agent calls.

Both PR #661's HTTP federation path and this track's real ACP path call
``resolve_policy()`` to decide which Huf agent a caller is allowed to reach and
with what capability scope.
"""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError

POLICY_DOCTYPE = "Remote Agent Policy"
POLICY_AGENT_CHILD_DOCTYPE = "Remote Agent Policy Agent"


def _get_user_roles(user: str | None = None) -> set[str]:
	"""Return the roles for the given user; defaults to the current session user."""
	if user is None:
		user = frappe.session.user
	return set(frappe.get_roles(user))


def _is_system_manager(user: str | None = None) -> bool:
	return "System Manager" in _get_user_roles(user)


def resolve_policy(
	caller_type: str,
	caller_reference: str | None,
	requested_agent: str | None = None,
	*,
	user: str | None = None,
) -> dict[str, Any]:
	"""Resolve which agent(s) and capability scope a caller may use.

	Parameters
    ----------
	caller_type:
        The type of caller identity (e.g. ``"api_key"`` or ``"remote_connection"``).
	caller_reference:
        The specific record named by ``caller_type`` (e.g. an API Key name), or
        ``None`` to match catch-all policies.
	requested_agent:
        The agent the caller explicitly asked for. If blank, the policy's
        ``default_agent`` is returned.
	user:
        Optional user override for role checks. Defaults to the current Frappe user.

	Returns
    -------
    A dict with ``default_agent``, ``allowed_agents``, and ``capability_scope``.

	Raises
    ------
    RemoteAgentPolicyError:
        When no enabled policy admits the caller, or the requested agent is not
        in the allowed set.
	"""
	if not caller_type:
		raise RemoteAgentPolicyError("caller_type is required to resolve a policy.")

	# For user callers, caller_reference defaults to the current Frappe user if blank.
	if caller_type == "user" and not caller_reference:
		caller_reference = frappe.session.user

	exact_filters: dict[str, Any] = {
		"enabled": 1,
		"caller_type": caller_type,
		"caller_reference": caller_reference or "",
	}
	catch_all_filters: dict[str, Any] = {
		"enabled": 1,
		"caller_type": caller_type,
		"caller_reference": "",
	}

	# Load exact matches first, then catch-all rows. Within each group, sort by
	# name to keep resolution deterministic.
	policies = frappe.get_all(
		POLICY_DOCTYPE,
		filters=exact_filters,
		fields=["name", "default_agent", "scope_type", "capability_scope", "max_run_duration_seconds"],
		order_by="name",
	)
	policies.extend(
		frappe.get_all(
			POLICY_DOCTYPE,
			filters=catch_all_filters,
			fields=["name", "default_agent", "scope_type", "capability_scope", "max_run_duration_seconds"],
			order_by="name",
		)
	)

	if not policies:
		raise RemoteAgentPolicyError(
			f"No Remote Agent Policy admits this caller ({caller_type}={caller_reference or 'any'})."
		)

	policy = policies[0]

	# Build allowed agent set.
	allowed: set[str] = set()
	default_agent = policy.get("default_agent")
	if default_agent:
		allowed.add(default_agent)

	if policy.get("scope_type") == "agent_list":
		rows = frappe.get_all(
			POLICY_AGENT_CHILD_DOCTYPE,
			filters={"parent": policy["name"]},
			fields=["agent"],
		)
		for row in rows:
			if row.get("agent"):
				allowed.add(row["agent"])

	# If the caller asked for a specific agent, it must be admitted.
	if requested_agent and requested_agent not in allowed:
		raise RemoteAgentPolicyError(
			f"Agent {requested_agent!r} is not allowed by policy {policy['name']!r}."
		)

	# When no agent was requested, default to the policy's default agent.
	if not requested_agent:
		if not default_agent:
			raise RemoteAgentPolicyError(
				f"Policy {policy['name']!r} has no default_agent and no agent was requested."
			)
		requested_agent = default_agent

	capability_scope = _normalize_capability_scope(
		policy.get("capability_scope") or "{}",
		max_run_duration_seconds=policy.get("max_run_duration_seconds") or 300,
		allow_file_tools=False,
		allow_shell_tools=False,
	)

	return {
		"default_agent": default_agent,
		"allowed_agents": sorted(allowed),
		"capability_scope": capability_scope,
		"policy": policy["name"],
		"resolved_agent": requested_agent,
	}


def _normalize_capability_scope(
	value: str | dict[str, Any] | None,
	*,
	max_run_duration_seconds: int,
	allow_file_tools: bool,
	allow_shell_tools: bool,
) -> dict[str, Any]:
	"""Parse and normalize the JSON ``capability_scope`` field."""
	if isinstance(value, str):
		try:
			scope = frappe.parse_json(value) or {}
		except Exception:  # noqa: BLE001
			scope = {}
	elif isinstance(value, dict):
		scope = dict(value)
	else:
		scope = {}

	scope.setdefault("tool_allow_list", [])
	scope.setdefault("tool_deny_list", [])
	scope.setdefault("allow_file_tools", allow_file_tools)
	scope.setdefault("allow_shell_tools", allow_shell_tools)
	scope.setdefault("max_run_duration_seconds", max_run_duration_seconds)
	scope.setdefault("max_concurrent_runs", 1)
	return scope
