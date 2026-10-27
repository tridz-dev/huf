"""Tell the originating chat when a gateway-triggered Flow Run fails.

``notify_flow_failure`` is cheap, idempotent (one notice per run, via cache)
and never raises. The user-facing text carries no internal error detail.
"""

from __future__ import annotations

import json

import frappe

_CACHE_PREFIX = "huf:gw_flow_fail_notice:"
_CACHE_TTL = 24 * 3600


def failure_text(event_name: str) -> str:
	return f"Something went wrong. Ref {event_name}."


def _already_notified(flow_run_name: str) -> bool:
	"""Mark-and-check; returns True if a notice was already claimed for this run."""
	cache = frappe.cache()
	key = _CACHE_PREFIX + flow_run_name
	if cache.get_value(key):
		return True
	cache.set_value(key, 1, expires_in_sec=_CACHE_TTL)
	return False


def notify_flow_failure(flow_run_name: str) -> bool:
	"""Send one plain failure notice for a failed gateway-originated run. Returns True if sent."""
	try:
		if not flow_run_name:
			return False
		row = frappe.db.get_value("Flow Run", flow_run_name, ["trigger_payload", "status"], as_dict=True)
		if not row or row.get("status") != "Failed":
			return False
		payload = json.loads(row.get("trigger_payload") or "{}")
		event_name = payload.get("gateway_event") if isinstance(payload, dict) else None
		if not event_name:
			return False
		if _already_notified(flow_run_name):
			return False
		event = frappe.get_doc("Gateway Event", event_name)
		if getattr(event, "flow_run", None) != flow_run_name or not getattr(event, "conversation_id", None):
			return False
		gateway = frappe.get_doc("Gateway", event.gateway)
		from huf.ai.gateway_webhook import send_gateway_reply

		send_gateway_reply(gateway, event, failure_text(event.name))
		return True
	except Exception:
		try:
			frappe.log_error(frappe.get_traceback(), "Gateway flow failure notice failed")
		except Exception:
			pass
		return False


def on_flow_run_update(doc, method=None) -> None:
	"""``Flow Run`` ``on_update`` doc event: notify when status transitions to Failed."""
	try:
		if getattr(doc, "status", None) != "Failed":
			return
		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
		if before is not None and getattr(before, "status", None) == "Failed":
			return
		if "gateway_event" not in (getattr(doc, "trigger_payload", None) or ""):
			return
		notify_flow_failure(doc.name)
	except Exception:
		pass
