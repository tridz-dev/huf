"""Let the app that owns a flow refuse one decider of its approvals (for example the person who asked).

Declared in the owning app's ``hooks.py`` and read only from the hooks of the app it names::

	huf_flow_approver_veto = {"<app>": "<dotted path>"}

``handler(request: dict) -> bool`` with ``request = {"flow_id": str, "flow_run": str, "node_id": str,
"user": str, "decision": "approved" | "rejected", "test_run": bool}``. It answers whether to veto.

Only an exact ``False`` lets the decision go on to be made; the veto never grants anything the approver check
would refuse. ``True``, any other answer, an exception, a bad path or an answer later than the time limit refuses.
Huf-native flows are never asked.

frappe is imported inside functions so the module also loads without a bench.
"""

from __future__ import annotations

import time

HOOK = "huf_flow_approver_veto"
TIMEOUT_KEY = "huf_flow_approver_veto_timeout_s"
DEFAULT_TIMEOUT_S = 5
REFUSAL = "You are not allowed to decide this approval."


def refuse_if_vetoed(flow_run, user: str, decision: str) -> None:
	"""Raise PermissionError when the owning app vetoes ``user`` (or cannot be asked). Fails closed."""
	import frappe
	from frappe import _

	if _vetoed(flow_run, user, decision):
		frappe.throw(_(REFUSAL), frappe.PermissionError)


def _timeout_seconds() -> float:
	import frappe

	value = frappe.conf.get(TIMEOUT_KEY)
	if isinstance(value, bool) or not isinstance(value, int | float) or not value > 0:
		return DEFAULT_TIMEOUT_S
	return min(max(value, 1), 30)


def _vetoed(flow_run, user: str, decision: str) -> bool:
	import frappe

	from huf.ai.flow.app_scope.ownership import owner_app_of
	from huf.ai.flow.testrun.gate import is_test_run

	path = None
	messages = getattr(getattr(frappe, "local", None), "message_log", None)
	message_count = len(messages) if isinstance(messages, list) else 0
	try:
		flow_id = flow_run.get("flow_definition") or flow_run.get("flow_id")
		app = flow_run.get("owner_app") or owner_app_of(flow_id)
		if not app:
			return False
		paths = (frappe.get_hooks(HOOK, app_name=app) or {}).get(app) or []
		for path in [paths] if isinstance(paths, str) else list(paths):
			handler = frappe.get_attr(path)
			limit = _timeout_seconds()
			started = time.monotonic()
			answer = handler(
				{
					"flow_id": flow_id,
					"flow_run": flow_run.name,
					"node_id": flow_run.get("current_node_id"),
					"user": user,
					"decision": decision,
					"test_run": is_test_run(flow_run),
				}
			)
			if time.monotonic() - started > limit:
				_warn(path, "timeout")  # a late answer is discarded
				return True
			if answer is not False:
				if answer is not True:
					_warn(path, "invalid result")
				return True
	except Exception as exc:  # noqa: BLE001 - any failure refuses; the message may carry data, so only the class
		if isinstance(messages, list):
			del messages[message_count:]  # a frappe.throw in the hook must not surface to the decider
		_warn(path or HOOK, type(exc).__name__)
		return True
	else:
		return False


def _warn(path: str, what: str) -> None:
	try:
		import frappe

		frappe.logger("huf").warning(f"{HOOK} {path}: {what}; decision refused")
	except Exception:  # noqa: BLE001, S110 - logging must never turn a refusal into something else
		pass
