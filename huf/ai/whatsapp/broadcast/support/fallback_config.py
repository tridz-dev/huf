# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Validation and copying of a broadcast's cross-channel failover configuration (HUFCRM-04).

``fallback_body_kind`` from a broadcast author is ``marketing`` (needs an explicit per-channel marketing opt-in)
or ``transactional``. ``otp`` / ``utility`` are never accepted here: only ``otp.py`` passes ``otp`` to
``failover.run_chain`` directly.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

from huf.ai.whatsapp.broadcast.support import failover

BODY_KINDS = ("marketing", "transactional")
BODY_MAX = 1600
CONFIG_FIELDS = ("fallback_channels", "fallback_body", "fallback_body_kind", "fallback_sms_gateway", "fallback_email_gateway")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(value: Any) -> str | None:
	"""A usable lower-cased address or None."""
	text = str(value or "").strip().lower()
	return text if text and len(text) <= 140 and _EMAIL.match(text) else None


def _channels(raw: Any) -> list[str]:
	if raw is None:
		return []
	if isinstance(raw, str):
		raw = json.loads(raw) if raw.strip() else []
	if not isinstance(raw, (list, tuple)):
		raise ValueError("fallback_channels must be a list such as [\"sms\",\"email\"].")
	out: list[str] = []
	for item in raw:
		channel = str(item or "").strip().lower()
		if channel not in failover.SUPPORTED:
			raise ValueError(f"fallback_channels may only contain: {', '.join(failover.SUPPORTED)}.")
		if channel in out:
			raise ValueError("fallback_channels must not repeat a channel.")
		out.append(channel)
	return out


def _gateway(name: Any, label: str) -> str | None:
	name = str(name or "").strip()
	if not name:
		return None
	if not frappe.db.exists("Gateway", name):
		raise ValueError(f"{label} does not exist.")
	if not frappe.has_permission("Gateway", "read", name):
		raise frappe.PermissionError(f"Not permitted to use {label} {name}.")
	return name


def clean(values: dict[str, Any]) -> dict[str, Any]:
	"""Validated values for the fields present in ``values`` (a ValueError names the first problem).

	An empty ``fallback_channels`` clears the whole configuration. Raises ``frappe.PermissionError`` for a gateway
	the caller cannot read."""
	out: dict[str, Any] = {}
	if "fallback_channels" in values:
		try:
			channels = _channels(values["fallback_channels"])
		except json.JSONDecodeError as exc:
			raise ValueError("fallback_channels must be valid JSON.") from exc
		out["fallback_channels"] = json.dumps(channels) if channels else None
	if "fallback_body" in values:
		body = str(values["fallback_body"] or "").strip()
		if len(body) > BODY_MAX:
			raise ValueError(f"fallback_body is limited to {BODY_MAX} characters.")
		out["fallback_body"] = body or None
	if "fallback_body_kind" in values:
		kind = str(values["fallback_body_kind"] or "").strip().lower()
		if kind and kind not in BODY_KINDS:
			raise ValueError(f"fallback_body_kind must be one of: {', '.join(BODY_KINDS)}.")
		out["fallback_body_kind"] = kind or None
	if "fallback_sms_gateway" in values:
		out["fallback_sms_gateway"] = _gateway(values["fallback_sms_gateway"], "fallback_sms_gateway")
	if "fallback_email_gateway" in values:
		out["fallback_email_gateway"] = _gateway(values["fallback_email_gateway"], "fallback_email_gateway")
	return out


def check_complete(channels: Any, body: Any) -> str | None:
	"""Problem text when channels are set without a body (the template is never turned into text)."""
	if failover.parse_channels(channels) and not str(body or "").strip():
		return "fallback_body is required when fallback_channels is set."
	return None


def snapshot(doc: Any) -> dict[str, Any]:
	"""The failover fields of a broadcast (doc or dict), as stored values."""
	get = doc.get if hasattr(doc, "get") else (lambda k: getattr(doc, k, None))
	return {k: (get(k) or None) for k in CONFIG_FIELDS}


def propagate(broadcast: str) -> None:
	"""Copy the broadcast's current failover config onto its not-yet-sent recipient rows."""
	values = snapshot(frappe.get_doc("WhatsApp Broadcast", broadcast))
	cols = ", ".join(f"`{k}`=%s" for k in CONFIG_FIELDS)
	frappe.db.sql(
		f"update `tabWhatsApp Broadcast Recipient` set {cols} where broadcast=%s and status in ('queued','deferred')",
		(*values.values(), broadcast),
	)
