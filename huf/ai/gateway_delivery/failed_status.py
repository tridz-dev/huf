"""Outbound delivery failure recording for gateway webhooks."""

from __future__ import annotations

import frappe

from huf.ai.gateway_adapters import provider_hooks


_FAILED_STATUS_TTL = 7 * 24 * 3600


def _record_failed_status(gateway_name: str, status: dict, provider: str | None = None) -> None:
	"""Record a failed outbound delivery status through the provider's ``failed_status`` hook."""
	hook = provider_hooks.get(provider, "failed_status")
	if hook is None:
		return
	# A redelivered callback (same message and provider timestamp) must not alert twice.
	key = ""
	if status.get("id") and status.get("timestamp"):
		key = f"huf_dlv_failed:{gateway_name}:{status['id']}:{status['timestamp']}"
		if frappe.cache.get_value(key) == 1:
			return
	hook(gateway_name, status)
	if key:
		# Only after commit: a rolled-back delivery is redelivered and must alert then.
		frappe.db.after_commit.add(lambda: frappe.cache.set_value(key, 1, expires_in_sec=_FAILED_STATUS_TTL))
