# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Test-only entry point for the desktop app's live end-to-end verification.

The desktop app repo (``desktop-poc``, ``npm run verify``, stage ``live-bench``) starts its real
executor against a LOCAL bench, registers a lease, and then needs the backend to dispatch tool calls
to it exactly as an agent run would. An agent run needs a model; this does not. It calls the same
``huf.ai.desktop_executor.dispatch`` an agent tool calls, with the same pinned run context
(``resolve_desktop_ctx``: executor id, fingerprint, user, the catalog the lease publishes, device id),
so everything the backend does on a real dispatch happens: lease checks, capability checks, the
agent-policy ceiling, the remote-origin gate, catalog and argument validation, the wait for the
desktop's answer, and result shaping.

It is disabled unless the site sets ``huf_desktop_live_test`` in its site config, and then only for
a System Manager. There is no path from a normal site to it: the flag is off by default, is not set
by any install, and is never set by this repository.

    bench --site <site> set-config huf_desktop_live_test 1
"""

import uuid

import frappe
from frappe import _

from huf.ai import desktop_executor as dx

FLAG = "huf_desktop_live_test"


def _guard():
	if not frappe.conf.get(FLAG):
		frappe.throw(_("Desktop live test API is disabled on this site."), frappe.PermissionError)
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only a System Manager may use the desktop live test API."), frappe.PermissionError)


def _as_dict(value):
	if isinstance(value, str) and value:
		import json

		value = json.loads(value)
	return value if isinstance(value, dict) else None


@frappe.whitelist(methods=["POST"])
def dispatch_call(
	executor_id=None,
	op=None,
	params=None,
	origin="desktop",
	agent_policy=None,
	agent_name="LiveTest",
	agent_run_id=None,
	call_id=None,
	timeout_ms=None,
):
	"""Dispatch one desktop op to ``executor_id`` as the session user and return the structured result.

	``origin`` and ``agent_policy`` are what a run pinned to that desktop would carry (``desktop`` or
	``remote``; the agent's ceiling as ``desktop_policy`` builds it). Returns whatever
	``desktop_executor.dispatch`` returns: ``{ok, op, workspace, data | error{code, message}, ...}``.
	"""
	_guard()
	user = frappe.session.user
	ctx = dx.resolve_desktop_ctx(executor_id, user)
	if ctx is None:
		# No live lease: dispatch answers desktop_offline from the same context shape a run would have.
		ctx = {"executor_id": executor_id, "user": user, "fingerprint": None, "label": None}
	ctx = dict(ctx)
	ctx["origin"] = origin
	policy = _as_dict(agent_policy)
	if policy is not None:
		ctx["agent_policy"] = policy
	return dx.dispatch(
		op,
		_as_dict(params) or {},
		ctx,
		call_id=call_id,
		conversation_id=None,
		agent_run_id=agent_run_id or "live-" + uuid.uuid4().hex[:12],
		timeout_ms=timeout_ms,
		tool_name="live_" + str(op),
		agent_name=agent_name,
		web_request=False,
	)


@frappe.whitelist(methods=["POST"])
def lease_state(executor_id=None):
	"""What the backend holds for a lease (no secret): for the test to assert registration facts."""
	_guard()
	lease = dx._get_lease(executor_id) if executor_id else None
	if not lease or lease.get("user") != frappe.session.user:
		return {"live": False}
	return {
		"live": True,
		"device_id": lease.get("device_id"),
		"device_label": lease.get("device_label"),
		"remote_control": bool(lease.get("remote_control")),
		"capabilities": lease.get("capabilities"),
		"permission_mode": (lease.get("workspace") or {}).get("permission_mode"),
		"has_secret": bool(lease.get("secret_hash")),
		"catalog_hash": lease.get("catalog_hash"),
	}
