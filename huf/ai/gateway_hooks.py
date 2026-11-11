# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Hook helpers for external apps that subscribe to gateway events.

Hooks are resolved from ``frappe.get_hooks(hook_name)``: a dotted path or a list of dotted paths.
Handlers are called with the payload as keyword arguments, in registration order.

These hooks are for external apps. Payloads must be side-effect-free: a handler may observe the
payload but must not write to the database, send messages, or call out to the network, because
:func:`fire_hook` runs for notifications and :func:`gate_hook` runs before a send.

* :func:`fire_hook` notifies. A failing or misconfigured handler is logged and skipped.
* :func:`gate_hook` gates. It fails closed: a refusal, an exception or a bad dotted path blocks.
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

	A handler returning a truthy value (a dict or string refusal) or raising stops the chain and
	raises ``OutboundRefused(message, code="blocked_by_hook")``. A bad dotted path also fails closed.
	A falsy return allows. No hooks registered means allow.
	"""
	from huf.ai.whatsapp.outbound_policy import OutboundRefused

	for path in _handler_paths(hook_name):
		try:
			handler = frappe.get_attr(path)
			verdict = handler(**payload)
		except Exception:
			frappe.log_error(title=f"gateway hook {hook_name} failed", message=frappe.get_traceback())
			raise OutboundRefused("Blocked by gateway hook", "blocked_by_hook")
		if verdict:
			raise OutboundRefused("Blocked by gateway hook", "blocked_by_hook")
