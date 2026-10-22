# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Per-run "a tool delivered a message to the user's chat" flag.

A gateway run that ends with empty final text is a success only when a send tool actually delivered
to the user's chat during that run (Telegram current-chat send, WhatsApp send). Read-only tools
(search, list) never set it, so an empty answer after them stays a failure. Cache-backed (like the
send caps), keyed by the Agent Run name.
"""

from __future__ import annotations

import frappe

_TTL = 6 * 3600


def _key(run_id: str) -> str:
	return f"huf:run_delivered:{run_id}"


def mark(run_id) -> None:
	if not run_id:
		return
	try:
		frappe.cache().set_value(_key(str(run_id)), 1, expires_in_sec=_TTL)
	except Exception:
		pass


def delivered(run_id) -> bool:
	if not run_id:
		return False
	try:
		return bool(frappe.cache().get_value(_key(str(run_id))))
	except Exception:
		return False


def current_run_delivered() -> bool:
	return delivered(getattr(frappe.flags, "huf_current_agent_run_id", None))
