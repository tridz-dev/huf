"""Channel-agnostic gateway status for the Channels shell (WhatsApp, Telegram, Slack, Teams)."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from huf.ai.channels import conversation as conv

LIVE_WINDOW_DAYS = 7


def _require_manage() -> None:
	from huf.ai.whatsapp.management import _can_manage_integrations

	if not _can_manage_integrations():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _recent_success(gateway: str) -> bool:
	return bool(
		frappe.db.exists(
			"Gateway Event",
			{"gateway": gateway, "status": "Succeeded", "creation": [">", add_days(now_datetime(), -LIVE_WINDOW_DAYS)]},
		)
	)


@frappe.whitelist()
def list_channel_gateways() -> list[dict[str, Any]]:
	"""``[{name, provider, channel, enabled, health, setup_stage}]`` for every channel gateway."""
	_require_manage()
	rows = frappe.get_all("Gateway", fields=["name", "provider", "is_enabled"], limit_page_length=500)
	wa: dict[str, dict[str, Any]] = {}
	out: list[dict[str, Any]] = []
	for row in rows:
		channel = conv.channel_for_provider(row.provider)
		if not channel:
			continue
		enabled = bool(row.is_enabled)
		if channel == "whatsapp":
			if not wa:
				from huf.ai.whatsapp.management import get_setup_status

				res = get_setup_status() or {}
				wa = {g["name"]: g for g in res.get("gateways") or []}
			info = wa.get(row.name) or {}
			out.append(
				{"name": row.name, "provider": row.provider, "channel": channel, "enabled": bool(info.get("enabled", enabled)),
				 "health": info.get("health") or ("off" if not enabled else "connected_unverified"),
				 "setup_stage": info.get("setup_stage")}
			)
			continue
		if not enabled:
			health, stage = "off", "off"
		elif _recent_success(row.name):
			health, stage = "live", "live"
		else:
			health, stage = "connected_unverified", "connected_unverified"
		out.append({"name": row.name, "provider": row.provider, "channel": channel, "enabled": enabled, "health": health, "setup_stage": stage})
	return out
