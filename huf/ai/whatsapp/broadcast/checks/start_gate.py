# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Start-time gating shared by ``runner.start``: preview blocking, warning acknowledgement, over-budget deferral."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

RECIPIENT = "WhatsApp Broadcast Recipient"
# Enforced by the runner itself under a row lock; the preview only reports them.
LOCKED_CHECKS = ("consent_not_attested", "another_broadcast_running")


class StartRefused(frappe.ValidationError):
	"""A start the runner refused, with a machine code (and extra payload) for the API to relay."""

	def __init__(self, code: str, message: str, **extra):
		super().__init__(message)
		self.code = code
		self.extra = extra


def _code(issue: Any) -> str:
	return str(issue.get("code")) if isinstance(issue, dict) else str(issue)


def parse_override_warnings(value: Any) -> list[str] | None:
	"""Acknowledged warning codes from a JSON string or a list; None when malformed."""
	if value is None or value == "":
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	if not isinstance(value, (list, tuple)) or not all(isinstance(c, str) for c in value):
		return None
	return list(dict.fromkeys(c.strip() for c in value if c.strip()))


def check_preview(preview: dict[str, Any], deferred: int, acknowledged: list[str] | None) -> set[str]:
	"""Raise ``StartRefused`` unless the preview allows a start; returns the acknowledged warning codes.

	``acknowledged`` None = resume (no new acknowledgement needed)."""
	blocking = [b for b in (preview.get("blocking") or []) if _code(b) not in LOCKED_CHECKS]
	if blocking:
		text = "; ".join(str(b.get("message") or b.get("code")) if isinstance(b, dict) else str(b) for b in blocking)
		raise StartRefused(_code(blocking[0]), _("Broadcast blocked: {0}").format(text), blocking=blocking)
	if int(preview.get("queued") or 0) + deferred <= 0:
		raise StartRefused("no_recipients", _("No queued recipients"))
	if acknowledged is None:
		return set()
	current = {_code(w) for w in preview.get("warnings") or []}
	if current != set(acknowledged):
		raise StartRefused(
			"warnings_changed",
			_("The warnings for this broadcast changed; review them again."),
			warnings=list(preview.get("warnings") or []),
		)
	return current


def defer_over_budget(broadcast: str, remaining: int) -> int:
	"""Keep the first ``remaining`` queued rows; the rest stay queued but wait for the next 24h window."""
	rows = frappe.db.sql(
		f"select name from `tab{RECIPIENT}` where broadcast=%s and status='queued' order by creation, name",
		broadcast,
	)
	later = [r[0] for r in rows][max(int(remaining), 0):]
	when = add_to_date(now_datetime(), hours=24)
	for i in range(0, len(later), 1000):
		chunk = later[i : i + 1000]
		marks = ",".join(["%s"] * len(chunk))
		frappe.db.sql(
			f"update `tab{RECIPIENT}` set next_attempt_at=%s where status='queued' and name in ({marks})",
			(when, *chunk),
		)
	return len(later)
