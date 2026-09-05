"""Single source of truth for "can user X run/access Agent Y".

Replaces the previously duplicated, divergent logic in Agent.has_permission()
(huf/huf/doctype/agent/agent.py) and _is_user_allowed() (huf/ai/agent_integration.py).
"""

from dataclasses import dataclass, field

import frappe
from frappe import _

# Trigger-surface identifiers for resolve_run_identity_and_authorize().
# Kept as plain strings (not an enum) so call sites don't need an extra
# import just to pass a constant around.
TRIGGER_DIRECT_API = "direct_api"
TRIGGER_GATEWAY = "gateway"
TRIGGER_FLOW_WEBHOOK = "flow_webhook"
TRIGGER_DOC_EVENT = "doc_event"

_KNOWN_TRIGGER_SURFACES = frozenset(
    {TRIGGER_DIRECT_API, TRIGGER_GATEWAY, TRIGGER_FLOW_WEBHOOK, TRIGGER_DOC_EVENT}
)


def check_agent_access(agent_doc, user, *, for_execution=True) -> bool:
	"""Return True if `user` may access/run `agent_doc`.

	Rules (confirmed product semantics):
	- System Manager and the document owner always have access.
	- Guest access depends solely on allow_guest; allowed_users/allowed_roles
	  are never consulted for Guest.
	- A holder of the agent.view_all or agent.edit capability always has access
	  (mirrors the Agent PQC's capability short-circuit).
	- If both allowed_users and allowed_roles are empty, access is governed by
	  allow_all_users: True grants every authenticated user access (legacy/
	  migrated agents), False closes the agent to everyone but the owner,
	  System Manager, and capability holders above (new agents, closed by
	  default).
	- Otherwise, allowed if the user is listed in allowed_users or holds any
	  role in allowed_roles.
	"""
	# for_execution is currently unused: access rules are identical for viewing/
	# editing and for running the agent. Reserved in case execution ever needs
	# stricter or looser rules than general document access.

	if user == "Guest":
		return bool(agent_doc.allow_guest)

	if agent_doc.owner == user or "System Manager" in frappe.get_roles(user):
		return True

	from huf.permissions import has_capability

	if has_capability(user, "agent.view_all") or has_capability(user, "agent.edit"):
		return True

	allowed_users = agent_doc.allowed_users or []
	allowed_roles = agent_doc.allowed_roles or []

	if not allowed_users and not allowed_roles:
		return bool(agent_doc.allow_all_users)

	allowed_user_names = [u.user for u in allowed_users]
	if user in allowed_user_names:
		return True

	allowed_role_names = [r.role for r in allowed_roles]
	user_roles = frappe.get_roles(user)
	if any(role in user_roles for role in allowed_role_names):
		return True

	return False


def assert_agent_access(agent_doc, user=None, *, for_execution=True) -> None:
	"""Throw frappe.PermissionError if `user` (default: current session user)
	may not access/run `agent_doc`."""
	user = user or frappe.session.user

	if not check_agent_access(agent_doc, user, for_execution=for_execution):
		frappe.throw(_("You do not have access to run this agent."), frappe.PermissionError)


@dataclass
class RunIdentityResult:
	"""Outcome of resolving "who runs this, and are they allowed to".

	This is a pure value object: resolving it never calls frappe.set_user,
	frappe.throw, or writes to any doctype. Callers apply ``run_as_user`` and
	decide how to surface an unauthorized result themselves (raise for a
	synchronous API caller, db_set a rejection onto a Gateway Event / Flow Run
	for a background surface) -- that decision is deliberately left to each
	call site because the four trigger surfaces have different, and
	intentionally different, failure-reporting shapes. Track-Item: GW-11.
	"""

	run_as_user: str
	authorized: bool
	reason: str | None = None
	# True when the identity actually used differs from the one the caller
	# asked to run as (currently only the doc-event surface can do this, when
	# the initiating user has since been deleted).
	fallback_applied: bool = False
	fallback_reason: str | None = None
	metadata: dict = field(default_factory=dict)


def resolve_run_identity_and_authorize(
	agent_doc,
	trigger_surface: str,
	context: dict | None = None,
) -> RunIdentityResult:
	"""Resolve the run-as identity and authorization for one "run an agent"
	trigger surface, using a single shared predicate (`check_agent_access`)
	wherever a surface performs its own agent-level entitlement check.

	This unifies *identity resolution*, not failure *reporting*: each of the
	four surfaces below intentionally keeps its own way of surfacing a
	rejection (HTTP exception vs. a persisted Gateway Event / Flow Run
	status), because collapsing that too would itself be a behavior change.
	See Tracks/safwan-erooth.IntegrationsGatewaysAudit/findings/GW-11-refactor.md
	for the full design rationale. Track-Item: GW-11.

	Args:
	    agent_doc: The target Agent document. Required for
	        ``TRIGGER_DIRECT_API`` and ``TRIGGER_GATEWAY`` (both perform a
	        `check_agent_access` gate against it). Not required for
	        ``TRIGGER_FLOW_WEBHOOK`` (a Flow, not a single Agent, is the
	        trigger target) or ``TRIGGER_DOC_EVENT`` (the doc-event surface
	        never gated on `check_agent_access` itself -- it always deferred
	        entitlement to the downstream `run_agent_sync` call made under
	        the resolved identity, and this refactor preserves that).
	    trigger_surface: One of the ``TRIGGER_*`` constants in this module.
	    context: Surface-specific inputs.
	        - ``direct_api``: ``{"user": <acting user, defaults to
	          frappe.session.user>}``.
	        - ``gateway``: ``{"execution_user": <Gateway.execution_user>,
	          "target_agent": <event.target_agent, for the rejection message;
	          defaults to agent_doc.name>}``. ``execution_user`` is required.
	        - ``flow_webhook``: ``{"owner": <Flow Definition.owner>}``. The
	          webhook-key check that gates entry to this surface has already
	          run by the time this is called; this call only resolves who the
	          run executes as.
	        - ``doc_event``: ``{"initiating_user": <str or None>,
	          "current_user": <str, defaults to frappe.session.user>}``.

	Returns:
	    A RunIdentityResult. `authorized` is always True for
	    ``flow_webhook``/``doc_event`` (see above -- neither surface performs
	    an agent-level gate at this point); it reflects the outcome of
	    `check_agent_access` for ``direct_api``/``gateway``.
	"""
	if trigger_surface not in _KNOWN_TRIGGER_SURFACES:
		frappe.throw(f"Unknown trigger surface: {trigger_surface}")

	context = context or {}

	if trigger_surface == TRIGGER_DIRECT_API:
		if agent_doc is None:
			frappe.throw("agent_doc is required for the direct_api trigger surface")

		user = context.get("user") or frappe.session.user

		if not check_agent_access(agent_doc, user):
			# Deliberately not translated here (`_()`) -- these reason strings
			# are pure data on a value object with no i18n dependency of their
			# own; translation, same as before this refactor, happens once,
			# at the call site that actually frappe.throw()s the message.
			reason = (
				"You do not have access to run this agent."
				if user != "Guest"
				else "Agent does not allow guest/public access"
			)
			return RunIdentityResult(run_as_user=user, authorized=False, reason=reason)

		from huf.permissions import has_capability

		if user != "Guest" and not has_capability(user, "agent.use"):
			return RunIdentityResult(
				run_as_user=user,
				authorized=False,
				reason="You are not authorized to use this agent.",
			)

		return RunIdentityResult(run_as_user=user, authorized=True)

	if trigger_surface == TRIGGER_GATEWAY:
		if agent_doc is None:
			frappe.throw("agent_doc is required for the gateway trigger surface")

		execution_user = context.get("execution_user")
		if not execution_user:
			return RunIdentityResult(
				run_as_user=execution_user or "",
				authorized=False,
				reason="Gateway has no Run as user",
			)

		if not check_agent_access(agent_doc, execution_user):
			target_agent_label = context.get("target_agent", agent_doc.name)
			return RunIdentityResult(
				run_as_user=execution_user,
				authorized=False,
				reason=(
					f"Gateway run-as user '{execution_user}' does not have access "
					f"to agent '{target_agent_label}'"
				),
			)

		return RunIdentityResult(run_as_user=execution_user, authorized=True)

	if trigger_surface == TRIGGER_FLOW_WEBHOOK:
		# The webhook-key check upstream (`_webhook_key_is_valid`) is what
		# authorizes triggering this Flow; there is no per-Agent entitlement
		# check at this layer (a Flow, not one Agent, is the trigger target).
		# This call is identity resolution only, matching the pre-refactor
		# `frappe.set_user(defn_doc.owner or "Administrator")` exactly.
		owner = context.get("owner") or "Administrator"
		return RunIdentityResult(run_as_user=owner, authorized=True)

	# TRIGGER_DOC_EVENT
	initiating_user = context.get("initiating_user")
	current_user = context.get("current_user") or frappe.session.user

	if not initiating_user or initiating_user == current_user:
		return RunIdentityResult(run_as_user=current_user, authorized=True)

	if frappe.db.exists("User", initiating_user):
		return RunIdentityResult(run_as_user=initiating_user, authorized=True)

	# GW-11 fix folded in per the audit's "Exception handling" note: this used
	# to silently continue as whatever identity the background worker already
	# had (typically Administrator) with no log entry. Behavior (the fallback
	# itself) is unchanged; the silence is what's fixed.
	fallback_reason = (
		f"Doc-event initiating user '{initiating_user}' no longer exists; "
		f"running as '{current_user}' instead."
	)
	frappe.log_error(fallback_reason, "Doc Event Agent identity fallback")
	return RunIdentityResult(
		run_as_user=current_user,
		authorized=True,
		fallback_applied=True,
		fallback_reason=fallback_reason,
	)
