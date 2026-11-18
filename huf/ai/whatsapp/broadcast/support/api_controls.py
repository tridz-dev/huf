# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Broadcast start / pause / resume / cancel endpoints (whitelisted; re-exported from ``broadcast.api``).

Shared helpers are looked up on the ``api`` module at call time so patches on ``api`` keep working.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.whatsapp.broadcast import api as _api, policy
from huf.ai.whatsapp.broadcast.checks import start_gate
from huf.ai.whatsapp.broadcast.support.api_helpers import _BROADCAST, _BROADCAST_LOG

def _is_api_key_caller() -> bool:
	"""True when the request is authenticated with an API key/secret (``Authorization: token key:secret``)."""
	header = frappe.get_request_header("Authorization")
	return isinstance(header, str) and header.strip().lower().startswith("token ")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_start_broadcast"), seconds=60)
@_api._bridge_guard
def start_broadcast(
	broadcast: str | None = None, confirm_count: Any = None, override_warnings: Any = None
) -> dict[str, Any]:
	"""Start (or restart a Draft) broadcast.

	The typed count must equal the queued recipients (when ``require_typed_count`` is on; API-key callers skip it).
	``override_warnings``: acknowledged warning codes; the runner refuses with ``warnings_changed`` (plus the
	current warnings) when they differ, and enforces consent and one-running under a lock."""
	row = _api._require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	acknowledged = start_gate.parse_override_warnings(override_warnings)
	if acknowledged is None:
		return _api._error("invalid_override_warnings", "override_warnings must be a JSON list of warning codes.")
	queued = _api._queued_count(broadcast)
	if queued <= 0:
		return _api._error("no_recipients", "There are no queued recipients.")
	if policy.get("require_typed_count") and not _api._is_api_key_caller():
		if str(confirm_count if confirm_count is not None else "").strip() != str(queued):
			return _api._error("confirm_mismatch", f"Type the number of queued recipients ({queued}) to confirm.")
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	try:
		result = broadcast_runner.start(broadcast, user=frappe.session.user, override_warnings=acknowledged, expected_count=queued)
	except broadcast_runner.StartRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc), **exc.extra}
	_api._broadcast_audit(broadcast, "started", queued=queued, override_warnings=acknowledged)
	return {"success": True, "broadcast": broadcast, "queued": queued, **(result if isinstance(result, dict) else {})}


def _runner_action(broadcast: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
	row = _api._require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	result = getattr(broadcast_runner, action)(broadcast, **kwargs)
	_api._broadcast_audit(broadcast, action, **kwargs)
	status = frappe.db.get_value(_BROADCAST, broadcast, "status")
	return {"success": True, "broadcast": broadcast, "status": status, **(result if isinstance(result, dict) else {})}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_pause_broadcast"), seconds=60)
@_api._bridge_guard
def pause_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Pause a running broadcast; queued rows stay queued."""
	return _runner_action(broadcast, "pause", reason="manual")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_resume_broadcast"), seconds=60)
@_api._bridge_guard
def resume_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Resume a paused broadcast."""
	return _runner_action(broadcast, "resume")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_cancel_broadcast"), seconds=60)
@_api._bridge_guard
def cancel_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Cancel a broadcast: queued rows become skipped (cancelled); already sent messages are unaffected."""
	return _runner_action(broadcast, "cancel")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_pause_all"), seconds=60)
@_api._bridge_guard
def pause_all_broadcasts(gateway: str | None = None) -> dict[str, Any]:
	"""Kill switch: pause every running broadcast of a Gateway."""
	refused = _api._require_send_authority(gateway)
	if refused:
		return refused
	running = frappe.get_all(_BROADCAST, filters={"gateway": gateway, "status": "Running"}, pluck="name") or []
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	result = broadcast_runner.pause_all(gateway, "kill_switch")
	broadcast_runner.hold_scheduled(gateway)
	for name in running:
		_api._broadcast_audit(name, "pause_all", gateway=gateway)
	frappe.logger(_BROADCAST_LOG).info(f"gateway={gateway} action=pause_all user={frappe.session.user} paused={len(running)}")
	return {"success": True, "gateway": gateway, "paused": running, **(result if isinstance(result, dict) else {})}
