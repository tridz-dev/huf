# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Helpers split out of ``gateway_webhook`` (delivery-status error parsing, unconfigured-gateway reply)."""

from __future__ import annotations

from typing import Any

import frappe


def _error_parts(status: dict) -> tuple[Any, Any, str]:
	"""``(first error code, first error title, summary of every error)`` of a Meta ``failed`` status."""
	errors = [
		e
		for e in (status.get("errors") if isinstance(status.get("errors"), list) else [])
		if isinstance(e, dict)
	]
	first = errors[0] if errors else {}
	parts = [
		f"error {e.get('code') or 'unknown'}: {e.get('title') or e.get('message') or 'no detail'}"
		for e in errors
	]
	return (
		first.get("code"),
		first.get("title") or first.get("message"),
		"; ".join(parts) or "error unknown: no detail",
	)


def reply_status_values(
	status: dict, state: str, current: str, stored_error: Any, max_len: int
) -> tuple[dict[str, Any] | None, Any, Any]:
	"""Columns to write for a delivery status that already passed the ordering check, plus the first error's
	code and title. ``(None, None, None)``: a replay (same state, or an identical ``failed``): write and fire nothing."""
	if state == current and state != "failed":
		return None, None, None
	values: dict[str, Any] = {"reply_status": state}
	error_code = error_title = None
	if state == "failed":
		from huf.ai.gateway_core.redaction import _redact_error_text

		error_code, error_title, summary = _error_parts(status)
		values["delivery_error"] = _redact_error_text(summary)[:max_len]
		values["delivery_error_code"] = str(error_code if error_code is not None else "unknown")
		if current == "failed" and stored_error == values["delivery_error"]:
			return None, None, None
	elif current == "failed":
		values["delivery_error"] = ""
		values["delivery_error_code"] = ""
	return values, error_code, error_title


def adapter_unavailable_response(fw: Any = frappe) -> dict:
	"""Enabled gateway with missing/incomplete credentials. Raising would 5xx and make the provider retry
	forever, so answer without leaking details and log once. ``fw`` is the caller's ``frappe`` module."""
	fw.log_error(fw.get_traceback(), "WhatsApp gateway adapter unavailable")
	if (getattr(fw.request, "method", "") or "").upper() == "GET":
		fw.local.response.http_status_code = 403
		return {"success": False, "error": "Webhook verification failed"}
	fw.local.response.http_status_code = 200
	return {"success": False, "error": "Gateway is not configured"}


_UNTRACKED_TTL = 7 * 24 * 3600


def untracked_status_hook(gateway: str, status: dict, wins: Any, fire: Any) -> None:
	"""Fire ``huf_gateway_delivery_status`` for a status whose wamid matched neither a Gateway Event reply nor a
	broadcast recipient (agent-tool / template sends). ``event_name`` is None; no row is created.

	Deduped per ``(gateway, wamid)`` in the cache (7 days) with ``wins`` (``_reply_status_wins``): replays, late
	``sent`` and ``failed`` after delivered/read stay silent. Cache loss can refire (at-least-once). Never raises."""
	try:
		state, wamid = str(status.get("status") or "").lower(), str(status.get("id") or "")
		if state not in ("sent", "delivered", "read", "played", "failed") or not wamid:
			return
		key = f"huf_dlv:{gateway}:{wamid}"
		current = frappe.cache().get_value(key) or ""
		if state == current or not wins(current, state):
			return
		frappe.cache().set_value(key, state, expires_in_sec=_UNTRACKED_TTL)
		code, title, _ = _error_parts(status) if state == "failed" else (None, None, "")
		fire("huf_gateway_delivery_status", gateway=gateway, provider_message_id=wamid, status=state,
			error_code=code, error_title=title, event_name=None)
	except Exception:
		pass
