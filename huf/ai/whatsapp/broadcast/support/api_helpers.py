# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared helpers for ``broadcast.api`` (constants, audit, views, masking). Moved out of api.py unchanged."""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

from huf.ai.whatsapp.broadcast.support import fallback_config
from huf.ai.whatsapp.management import _iso, _parse_json_arg

_BROADCAST = "WhatsApp Broadcast"
_BROADCAST_RECIPIENT = "WhatsApp Broadcast Recipient"
_BROADCAST_LOG = "huf.whatsapp.broadcast"
_BROADCAST_COUNT_FIELDS = (
	"total", "queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped",
)
_BROADCAST_FIELDS = (
	"name", "title", "status", "pause_reason", "gateway", "whatsapp_account", "template", "template_name",
	"language_code", "category", "body_params", "header_params", "button_params", "carousel_params", "consent_source",
	"consent_attested", "consent_attested_by", "consent_attested_at", "max_recipients", "mps", "send_via",
	"scheduled_at", "started_by", "started_at", "finished_at", "creation", "modified", *_BROADCAST_COUNT_FIELDS,
	*fallback_config.CONFIG_FIELDS,
)


def _broadcast_audit(broadcast: str, action: str, **details: Any) -> None:
	"""Audit every mutation: structured log line plus a Comment on the Broadcast."""
	user = getattr(frappe.session, "user", None)
	extra = ", ".join(f"{k}={v}" for k, v in details.items() if v not in (None, ""))
	frappe.logger(_BROADCAST_LOG).info(f"broadcast={broadcast} action={action} user={user} {extra}".strip())
	try:
		frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", f"{action} by {user}" + (f": {extra}" if extra else ""))
	except Exception:
		frappe.logger(_BROADCAST_LOG).warning(f"broadcast={broadcast} action={action}: audit comment failed")


def _broadcast_view(row: dict[str, Any]) -> dict[str, Any]:
	out = {k: row.get(k) for k in _BROADCAST_FIELDS if k not in _BROADCAST_COUNT_FIELDS}
	out["counts"] = {k: int(row.get(k) or 0) for k in _BROADCAST_COUNT_FIELDS}
	for key in ("body_params", "header_params", "button_params", "carousel_params"):
		value = out.get(key)
		if isinstance(value, str) and value:
			try:
				out[key] = json.loads(value)
			except ValueError:
				pass
	for key in ("creation", "modified", "scheduled_at", "started_at", "finished_at", "consent_attested_at"):
		out[key] = _iso(out.get(key))
	return out


def _queued_count(broadcast: str) -> int:
	"""Recipients still to send (queued + deferred): same set as broadcast_cost.confirm_token and the runner."""
	return int(frappe.db.count(_BROADCAST_RECIPIENT, {"broadcast": broadcast, "status": ["in", ["queued", "deferred"]]}) or 0)


def _mask_phone(value: Any) -> Any:
	text = str(value or "")
	return ("*" * max(len(text) - 4, 0) + text[-4:]) if text else value


_LONG_DIGITS_RE = re.compile(r"\d{7,}")


def _mask_digits(text: Any) -> Any:
	return _LONG_DIGITS_RE.sub(lambda m: _mask_phone(m.group(0)), text) if isinstance(text, str) else text


_UNSET: Any = object()  # distinguishes "not passed" from an explicit null/empty


def _json_param(value: Any, label: str) -> Any:
	parsed = _parse_json_arg(value, label)
	return parsed if parsed not in ("", None) else None


def _carousel_template_problem(tpl: Any, carousel: Any) -> str | None:
	"""A carousel template needs card values; a non-carousel template refuses them."""
	from huf.ai.whatsapp.broadcast.checks import template_check

	try:
		req = template_check.template_requirements(tpl.get("name") if isinstance(tpl, dict) else str(tpl or ""))
	except Exception:  # noqa: BLE001 - the start-time preview re-checks
		return None
	cards = (req or {}).get("view", {}).get("carousel") if req else None
	if cards and carousel in (None, [], {}):
		return None  # may still come per recipient (params.carousel); the start preview checks every row
	if carousel and not cards and req:
		return "This template is not a carousel; carousel_params is not accepted."
	return None


def _reset_attestation(broadcast: str, why: str) -> None:
	"""The attestation covered a different recipient list; the owner must attest again."""
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		frappe.db.set_value(_BROADCAST, broadcast, {
			"consent_attested": 0, "consent_attested_by": None, "consent_attested_at": None,
		})
	finally:
		frappe.flags.in_broadcast_api = prev
	frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", f"attestation reset: {why}")
