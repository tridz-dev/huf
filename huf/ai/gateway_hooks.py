# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Hook helpers for external apps that subscribe to gateway events.

Hooks are resolved from ``frappe.get_hooks(hook_name)``: a dotted path or a list of dotted paths.
Handlers are called with the payload as keyword arguments, in registration order.

These hooks are for external apps. Only the pre-send GATE (:func:`gate_hook`) must be side-effect-free:
it runs right before a send, so it may observe the payload and decide, but must not write to the database,
send messages, or call out to the network. Notification hooks (:func:`fire_hook`: delivery_status, opt_out)
are expected to write.

* :func:`fire_hook` notifies. A failing or misconfigured handler is logged and skipped.
* :func:`gate_hook` gates. It fails closed: ONLY a ``None`` return allows. Any other return value (False,
  True, '', 0, {}, a string, a dict), an exception, a bad dotted path or a failing ``frappe.get_hooks`` blocks.
"""

from __future__ import annotations

from typing import Any

import frappe


def _handler_paths(hook_name: str) -> list[str]:
	raw = frappe.get_hooks(hook_name)
	if not raw:
		return []
	if isinstance(raw, str):
		return [raw]
	return list(raw)


def fire_hook(hook_name: str, **payload: Any) -> list[Any]:
	"""Notify every handler registered for ``hook_name`` and return their results in order.

	A handler that raises, or a dotted path that cannot be resolved, is written to the Error Log
	and skipped; the remaining handlers still run and the caller is unaffected.
	"""
	results: list[Any] = []
	for path in _handler_paths(hook_name):
		try:
			handler = frappe.get_attr(path)
			results.append(handler(**payload))
		except Exception:
			frappe.log_error(title=f"gateway hook {hook_name} failed", message=frappe.get_traceback())
	return results


def gate_hook(hook_name: str, **payload: Any) -> None:
	"""Run every handler registered for ``hook_name`` and refuse the send on the first objection.

	Contract (fail closed): a handler allows by returning ``None`` and nothing else. Any other return
	value blocks, including ``False``, ``True``, ``''``, ``0``, ``{}``, a reason string and a dict such as
	``{"allowed": False}``; so does an exception. The chain stops at the first objection and raises
	``OutboundRefused("Blocked by gateway hook", code="blocked_by_hook")``. A bad dotted path, or a
	``frappe.get_hooks`` failure, also blocks. No hooks registered means allow.
	"""
	from huf.ai.whatsapp.outbound_policy import OutboundRefused

	try:
		paths = _handler_paths(hook_name)
	except Exception:
		frappe.log_error(title=f"gateway hook {hook_name} lookup failed", message=frappe.get_traceback())
		raise OutboundRefused("Blocked by gateway hook", "blocked_by_hook")

	for path in paths:
		try:
			handler = frappe.get_attr(path)
			verdict = handler(**payload)
		except Exception:
			frappe.log_error(title=f"gateway hook {hook_name} failed", message=frappe.get_traceback())
			raise OutboundRefused("Blocked by gateway hook", "blocked_by_hook")
		if verdict is not None:
			raise OutboundRefused("Blocked by gateway hook", "blocked_by_hook")
