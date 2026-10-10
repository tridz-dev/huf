# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Desktop-owned conversations and remote control (Desktop Remote Sessions R1).

A conversation created by a desktop client is *desktop-hosted*: ``execution_host = desktop`` with the
public ``host_device_id`` (derived from the desktop's public key), the workspace fingerprint and a
label. Those fields are written only here (``AgentConversation`` refuses every other write), so a
web session cannot re-point a conversation. A run in a hosted conversation, started from ANY client
(web included, same Frappe user), is pinned to that device:

* the device's lease is not live -> ``desktop_offline`` (with ``last_seen``), never a server run;
* the lease's workspace is not the conversation's -> ``workspace_changed`` (rebind the conversation);
* the request carries the lease secret -> origin ``desktop``; otherwise ``remote``. A remote run needs
  the desktop's ``remote_control`` switch AND the agent's ``allow_remote_desktop`` flag, else
  ``remote_disabled``. When both are on there is no cap and no extra prompting.

``set_desktop_permission_mode`` (whitelisted, callable from web) changes a workspace permission mode
on the desktop through a control request on the lease channel, and records an audit row.
"""

import frappe
from frappe import _

from huf.ai import desktop_executor as dx
from huf.ai import desktop_policy

REMOTE_DISABLED_MESSAGE = {
	"desktop": "Remote control is turned off on this desktop.",
	"agent": "This agent does not allow remote desktop control.",
}


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def audit(
	action,
	outcome,
	user=None,
	device_id=None,
	origin=None,
	conversation=None,
	agent=None,
	detail=None,
	ip=None,
):
	"""Append one ``Desktop Remote Audit`` row. Never raises: an audit failure must not change the
	outcome of the action it describes."""
	try:
		if ip is None:
			try:
				ip = frappe.local.request_ip
			except Exception:
				ip = None
		frappe.get_doc(
			{
				"doctype": "Desktop Remote Audit",
				"user": user or frappe.session.user,
				"device_id": device_id or "",
				"action": action,
				"outcome": outcome,
				"origin": origin or "",
				"conversation": conversation or "",
				"agent": agent or "",
				"detail": (str(detail) if detail is not None else "")[:1000],
				"ip_address": ip or "",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.logger("huf").warning("desktop remote audit write failed")


# --------------------------------------------------------------------------
# Hosted conversations
# --------------------------------------------------------------------------


def is_hosted(conversation):
	"""True for a desktop-hosted Agent Conversation (a document or a ``frappe._dict`` row)."""
	return getattr(conversation, "execution_host", None) == "desktop"


def run_error(code, message, conversation=None, **extra):
	"""The structured, non-raising failure a client receives instead of a run."""
	out = {
		"success": False,
		"queued": False,
		"error": code,
		"code": code,
		"message": message,
		"conversation_id": getattr(conversation, "name", None),
	}
	out.update(extra)
	return out


def remote_gate(lease, policy):
	"""``None`` when a remote-origin run is allowed, else ``"desktop"`` or ``"agent"`` (which switch
	is off). Both must be on; with both on there is no other restriction."""
	if not (lease or {}).get("remote_control"):
		return "desktop"
	if not (isinstance(policy, dict) and policy.get(desktop_policy.REMOTE_FIELD)):
		return "agent"
	return None


def host_from_desktop_request(desktop_executor_id, desktop_lease_secret=None):
	"""``{device_id, workspace_fingerprint, label}`` for a new desktop-hosted conversation.

	Only a desktop that authenticates with its lease secret and registered a device identity can
	create one; anything else raises ``frappe.PermissionError``.
	"""
	user = frappe.session.user
	lease = dx._get_lease(desktop_executor_id) if desktop_executor_id else None
	if (
		not lease
		or lease.get("user") != user
		or not dx.secret_matches(lease, dx.presented_secret(desktop_lease_secret))
	):
		frappe.throw(
			_("Only Huf Desktop, authenticated with its lease, can create a desktop-hosted conversation."),
			frappe.PermissionError,
		)
	if not lease.get("device_id"):
		frappe.throw(
			_("This desktop did not register a device identity, so it cannot host conversations."),
			frappe.PermissionError,
		)
	ws = lease.get("workspace") or {}
	device_label = lease.get("device_label") or ""
	ws_label = ws.get("label") or ""
	label = f"{device_label} - {ws_label}" if device_label and ws_label else (device_label or ws_label)
	return {
		"device_id": lease["device_id"],
		"workspace_fingerprint": ws.get("fingerprint"),
		"label": label[:140],
	}


def resolve_hosted_run(conversation, agent_doc, desktop_lease_secret=None):
	"""Resolve the pin for a run in a desktop-hosted conversation.

	Returns ``(ctx, status, error)``: exactly one of ``ctx`` (the pinned desktop ctx, with ``origin``
	and ``agent_policy``) or ``error`` (a :func:`run_error` dict) is set.
	"""
	user = frappe.session.user
	device_id = conversation.host_device_id
	label = conversation.host_label
	extra = {"host_device_id": device_id, "host_label": label}
	if not user or user == "Guest" or conversation.owner != user:
		return (
			None,
			None,
			run_error(
				"permission_denied",
				"Only the owner of a desktop-hosted conversation can run it.",
				conversation,
				**extra,
			),
		)
	lease = dx.find_device_lease(user, device_id)
	if not lease:
		last_seen = dx.device_last_seen(user, device_id)
		return (
			None,
			None,
			run_error(
				"desktop_offline",
				f"{label or 'The desktop'} is offline. This conversation runs only on that desktop.",
				conversation,
				last_seen=last_seen,
				**extra,
			),
		)
	if (lease.get("workspace") or {}).get("fingerprint") != conversation.host_workspace_fingerprint:
		return (
			None,
			None,
			run_error(
				"workspace_changed",
				"The desktop has a different workspace open. Rebind this conversation to continue.",
				conversation,
				**extra,
			),
		)

	policy = desktop_policy.policy_from_agent(agent_doc)
	origin = "desktop" if dx.secret_matches(lease, dx.presented_secret(desktop_lease_secret)) else "remote"
	origin_ip = dx.request_origin_ip() if origin == "remote" else ""
	if origin == "remote":
		off = remote_gate(lease, policy)
		if off:
			audit(
				"remote_run",
				"blocked:" + off,
				user=user,
				device_id=device_id,
				origin="remote",
				conversation=conversation.name,
				agent=conversation.agent,
			)
			return (
				None,
				None,
				run_error(
					"remote_disabled", REMOTE_DISABLED_MESSAGE[off], conversation, disabled_by=off, **extra
				),
			)
		audit(
			"remote_run",
			"allowed",
			user=user,
			device_id=device_id,
			origin="remote",
			conversation=conversation.name,
			agent=conversation.agent,
			ip=origin_ip or None,
		)
	ctx = dx.resolve_desktop_ctx(lease["executor_id"], user=user)
	if not ctx:
		return (
			None,
			None,
			run_error("desktop_offline", "The desktop went offline.", conversation, **extra),
		)
	ctx["origin"] = origin
	ctx["agent_policy"] = policy
	if origin_ip:
		ctx["origin_ip"] = origin_ip
	return ctx, {"available": True, "reason": None}, None


def assert_hosted_pin(conversation, desktop_ctx):
	"""Fail closed before a run executes: a run in a desktop-hosted conversation without a live pin to
	ITS device (offline by the time a queued run drains, a forged or missing pin) must never run on
	the server. Raises ``frappe.ValidationError``."""
	if not is_hosted(conversation):
		return
	if not desktop_ctx or desktop_ctx.get("device_id") != conversation.host_device_id:
		raise frappe.ValidationError(
			"desktop_offline: this conversation runs only on its desktop, which is not connected."
		)


# --------------------------------------------------------------------------
# Whitelisted API
# --------------------------------------------------------------------------


def _fail(code, message, **extra):
	return {"ok": False, "error": {"code": code, "message": message, **extra}}


@frappe.whitelist(methods=["POST"])
def set_desktop_permission_mode(device_id=None, mode=None):
	"""Change the permission mode of a device's workspace, from any client of the device's owner.

	Requires the device to be live and to have reported ``remote_control`` true. The request travels
	to the desktop as a control request on the lease channel; the answer is the mode the desktop
	confirms it applied. Every call is recorded in ``Desktop Remote Audit``. A device the user does
	not own is indistinguishable from an offline one.
	"""
	user = dx._require_user()
	if mode not in dx.PERMISSION_MODES:
		frappe.throw(_("Invalid permission mode."), frappe.ValidationError)
	lease = dx.find_device_lease(user, device_id)
	if not lease:
		audit("set_permission_mode", "offline", user=user, device_id=device_id, origin="remote", detail=mode)
		return _fail(
			"desktop_offline",
			"That desktop is offline.",
			last_seen=dx.device_last_seen(user, device_id) if isinstance(device_id, str) else None,
		)
	if not lease.get("remote_control"):
		audit(
			"set_permission_mode",
			"remote_disabled",
			user=user,
			device_id=device_id,
			origin="remote",
			detail=mode,
		)
		return _fail("remote_disabled", REMOTE_DISABLED_MESSAGE["desktop"])

	ws = lease.get("workspace") or {}
	previous = ws.get("permission_mode")
	answer = dx.dispatch_control(
		lease,
		dx.CONTROL_SET_PERMISSION_MODE,
		{"mode": mode, "fingerprint": ws.get("fingerprint")},
	)
	if not answer.get("ok"):
		error = answer.get("error") or {}
		audit(
			"set_permission_mode",
			"failed:" + str(error.get("code")),
			user=user,
			device_id=device_id,
			origin="remote",
			detail=f"{previous} -> {mode}",
		)
		return _fail(
			error.get("code") or "internal", error.get("message") or "The desktop did not apply the change."
		)
	applied = (answer.get("data") or {}).get("mode")
	if applied != mode:
		audit(
			"set_permission_mode",
			"not_applied",
			user=user,
			device_id=device_id,
			origin="remote",
			detail=f"{previous} -> {mode}, desktop reports {applied}",
		)
		return _fail(
			"mode_not_applied", "The desktop did not apply the requested mode.", applied_mode=applied
		)

	fresh = dx._get_lease(lease["executor_id"])
	if fresh:
		fresh_ws = dict(fresh.get("workspace") or {})
		fresh_ws["permission_mode"] = applied
		fresh["workspace"] = fresh_ws
		dx._put_lease(lease["executor_id"], fresh)
	audit(
		"set_permission_mode",
		"applied",
		user=user,
		device_id=device_id,
		origin="remote",
		detail=f"{previous} -> {applied}",
	)
	return {"ok": True, "applied_mode": applied, "device_id": device_id}


@frappe.whitelist(methods=["POST"])
def rebind_desktop_conversation(conversation=None, workspace_fingerprint=None, desktop_lease_secret=None):
	"""Move a desktop-hosted conversation to the workspace its device has open now.

	Only the owner can rebind, only within the same device (the device id never changes), only while
	that device is live, and ``workspace_fingerprint`` (when sent) must be the fingerprint the live
	lease reports. Refused while a run of the conversation is queued or running.
	"""
	user = dx._require_user()
	if not conversation or not frappe.db.exists("Agent Conversation", conversation):
		frappe.throw(_("Conversation not found or access denied."), frappe.PermissionError)
	conv = frappe.db.get_value(
		"Agent Conversation",
		conversation,
		["name", "owner", "execution_host", "host_device_id", "host_workspace_fingerprint"],
		as_dict=True,
	)
	if conv.owner != user or conv.execution_host != "desktop":
		frappe.throw(_("Conversation not found or access denied."), frappe.PermissionError)
	lease = dx.find_device_lease(user, conv.host_device_id)
	if not lease:
		return _fail(
			"desktop_offline",
			"The desktop is offline.",
			last_seen=dx.device_last_seen(user, conv.host_device_id),
		)
	origin = dx.origin_for(lease.get("executor_id"), desktop_lease_secret, user=user)
	if origin == "remote" and not lease.get("remote_control"):
		audit(
			"rebind",
			"remote_disabled",
			user=user,
			device_id=conv.host_device_id,
			origin="remote",
			conversation=conversation,
		)
		return _fail("remote_disabled", REMOTE_DISABLED_MESSAGE["desktop"])
	ws = lease.get("workspace") or {}
	current = ws.get("fingerprint")
	if workspace_fingerprint and workspace_fingerprint != current:
		return _fail("workspace_changed", "The desktop does not have that workspace open.")
	if frappe.db.exists("Agent Run", {"conversation": conversation, "status": ["in", ["Queued", "Started"]]}):
		return _fail("run_in_progress", "Wait for the running turn to finish before rebinding.")
	device_label = lease.get("device_label") or ""
	ws_label = ws.get("label") or ""
	label = f"{device_label} - {ws_label}" if device_label and ws_label else (device_label or ws_label)
	frappe.db.set_value(
		"Agent Conversation",
		conversation,
		{"host_workspace_fingerprint": current, "host_label": label[:140]},
		update_modified=False,
	)
	audit(
		"rebind",
		"applied",
		user=user,
		device_id=conv.host_device_id,
		origin=origin,
		conversation=conversation,
		detail=f"{conv.host_workspace_fingerprint} -> {current}",
	)
	return {
		"ok": True,
		"conversation": conversation,
		"host_workspace_fingerprint": current,
		"host_label": label,
	}


@frappe.whitelist()
def list_desktop_hosts():
	"""The session user's desktop devices for host badges: ``[{device_id, label, online, last_seen,
	remote_control, mode}]``. Built from the user's live leases and the devices their conversations are
	bound to. Never includes an executor id, a public key or a secret."""
	user = dx._require_user()
	rows = frappe.get_all(
		"Agent Conversation",
		filters={"owner": user, "execution_host": "desktop"},
		fields=["host_device_id", "host_label"],
		order_by="modified desc",
		limit_page_length=500,
	)
	labels = {}
	for row in rows:
		if row.host_device_id and row.host_device_id not in labels:
			labels[row.host_device_id] = row.host_label
	for device_id in dx.known_device_ids(user):
		labels.setdefault(device_id, None)
	out = []
	for device_id, label in labels.items():
		lease = dx.find_device_lease(user, device_id)
		ws = (lease or {}).get("workspace") or {}
		out.append(
			{
				"device_id": device_id,
				"label": (lease or {}).get("device_label") or label,
				"online": bool(lease),
				"last_seen": dx.device_last_seen(user, device_id),
				"remote_control": bool((lease or {}).get("remote_control")),
				"mode": ws.get("permission_mode") if lease else None,
			}
		)
	return out
