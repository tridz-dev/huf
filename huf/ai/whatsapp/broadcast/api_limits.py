# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast limits API: read every limit with its effective value, and change the editable ones.

``get_broadcast_limits(broadcast?)`` (GET) returns ``{"limits": [row, ...]}`` where each row is
``{key, label, group, kind, value, default, effective, source, unit, min, max, note, editable}``:

* ``kind``: ``meta`` (set by Meta, read-only) | ``setting`` | ``safety`` | ``internal`` (read-only).
* ``value``: what is stored in the settings (``null`` when blank); ``effective`` is what applies, with
  ``source`` ``default`` | ``settings`` | ``broadcast`` (a per-broadcast override beats settings).
* For ``max_recipients_default`` and ``max_recipients_ceiling`` the stored value ``0`` means "no limit":
  ``value`` is ``0`` and ``effective`` is ``null``. Any other blank resets to the default.
* Tier and quality rows carry ``as_of`` (ISO time of the Meta read; Meta reads are cached 10 minutes)
  and are filled only when ``broadcast`` is given.

``update_broadcast_limits(values)`` (POST, System Manager or Huf Admin) takes a JSON object
(string or dict) of ``key -> value``; ``null`` or an empty string resets that key to its default.
A value outside ``min``/``max`` is rejected and nothing is stored. It returns the same shape.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.management import _error, _gateway_read_allowed, _require_admin

_LOG = "huf.whatsapp.broadcast"


def _can_read(broadcast: str | None) -> str | None:
	"""Gateway of ``broadcast`` (or ``""``) after proving read authority; raises PermissionError."""
	gateway = ""
	if broadcast:
		gateway = frappe.db.get_value("WhatsApp Broadcast", broadcast, "gateway") or ""
		if not gateway:
			return ""
		if not _gateway_read_allowed(gateway):
			raise frappe.PermissionError("Not permitted to read limits for this Gateway")
	elif not frappe.has_permission("Gateway", "read") and "Huf Admin" not in frappe.get_roles():
		raise frappe.PermissionError("Not permitted to read limits")
	return gateway


def _live(gateway: str) -> dict[str, Any]:
	if not gateway:
		return {}
	try:
		from huf.ai.whatsapp.broadcast import limits

		return limits.get_messaging_limit(gateway) or {}
	except Exception:  # noqa: BLE001 - never raises
		return {}


def build_rows(broadcast: str | None = None, gateway: str = "") -> list[dict[str, Any]]:
	doc = frappe.get_doc("WhatsApp Broadcast", broadcast) if broadcast and gateway else None
	stored = policy.stored_values()
	live = _live(gateway)
	as_of = frappe.utils.now_datetime().isoformat() if live.get("tier") or live.get("quality") else None
	rows = []
	for lim in policy.LIMITS:
		effective, source = policy.resolve(lim.key, doc)
		value = stored.get(lim.key) if lim.editable else None
		row = {
			"key": lim.key,
			"label": lim.label,
			"group": lim.group,
			"kind": lim.kind,
			"value": value,
			"default": lim.default,
			"effective": effective,
			"source": source,
			"unit": lim.unit,
			"min": lim.min,
			"max": lim.max,
			"note": lim.note + ("" if lim.verified or lim.kind not in ("meta", "internal") else " (Not verified against Meta's documentation.)"),
			"editable": lim.editable,
		}
		if lim.key == "messaging_tier_24h":
			row.update(value=live.get("max_unique_24h"), effective=live.get("max_unique_24h"), as_of=as_of)
			row["tier"] = live.get("tier")
		elif lim.key == "quality_rating":
			row.update(value=live.get("quality"), effective=live.get("quality"), as_of=as_of)
		rows.append(row)
	return rows


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=policy.rate("rate_limits_read"), seconds=60)
def get_broadcast_limits(broadcast: str | None = None) -> dict[str, Any]:
	"""Every broadcast limit with default, stored value, effective value and where it comes from."""
	gateway = _can_read(broadcast)
	_ = gateway  # authority proven above
	try:
		return {"success": True, "limits": build_rows(broadcast, gateway or "")}
	except Exception as exc:  # noqa: BLE001 - this read never raises
		frappe.logger(_LOG).warning("get_broadcast_limits failed (%s)", type(exc).__name__)
		return {"success": True, "limits": build_rows(None, "")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_limits_write"), seconds=60)
def update_broadcast_limits(values: Any = None) -> dict[str, Any]:
	"""Change editable limits. ``values``: JSON object of key -> number/boolean; null resets to default."""
	_require_admin()
	try:
		parsed = json.loads(values) if isinstance(values, str) and values.strip() else values
		if not isinstance(parsed, dict) or not parsed:
			return _error("invalid_params", "values must be a non-empty JSON object.")
		policy.set_values(parsed)
	except ValueError as exc:
		return _error("invalid_limit", str(exc))
	user = frappe.session.user
	summary = ", ".join(f"{k}={'default' if v in (None, '') else v}" for k, v in parsed.items())
	frappe.logger(_LOG).info(f"limits updated by={user} {summary}")
	try:
		frappe.get_doc(policy.SETTINGS).add_comment("Info", f"limits changed by {user}: {summary}")
	except Exception:  # noqa: BLE001
		frappe.logger(_LOG).warning("limits audit comment failed")
	return {"success": True, "limits": build_rows(None, "")}
