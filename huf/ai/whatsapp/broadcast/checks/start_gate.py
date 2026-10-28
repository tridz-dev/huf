# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Start-time gating shared by ``runner.start``: preview blocking, warning acknowledgement, over-budget deferral."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from huf.ai.whatsapp.broadcast import limits as broadcast_limits, policy
from huf.ai.whatsapp.broadcast.checks import audience_check

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


def _hold_until(gateway: str | None):
	"""When the next 24h slot opens: the oldest counted send plus the window, else now plus the window."""
	hours = int(policy.get("over_budget_hold_hours"))
	now = now_datetime()
	oldest = None
	if gateway:
		oldest = broadcast_limits.oldest_counted_send(gateway)
	if oldest:
		return max(add_to_date(get_datetime(oldest), hours=hours), now)
	return add_to_date(now, hours=hours)


def defer_over_budget(broadcast: str, remaining: int, gateway: str | None = None) -> int:
	"""Keep the first ``remaining`` queued rows; the rest stay queued but wait for the next 24h window."""
	rows = frappe.db.sql(
		f"select name from `tab{RECIPIENT}` where broadcast=%s and status='queued' order by creation, name",
		broadcast,
	)
	later = [r[0] for r in rows][max(int(remaining), 0):]
	when = _hold_until(gateway)
	size = int(policy.get("defer_chunk"))
	for i in range(0, len(later), size):
		chunk = later[i : i + size]
		marks = ",".join(["%s"] * len(chunk))
		frappe.db.sql(
			f"update `tab{RECIPIENT}` set next_attempt_at=%s where status='queued' and name in ({marks})",
			(when, *chunk),
		)
	return len(later)


ACK_PREFIX = "acknowledged_warnings: "


def record_acknowledged(broadcast: str, codes) -> None:
	"""Remember on the broadcast (a Comment) which warning codes the operator accepted at start."""
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "WhatsApp Broadcast",
			"reference_name": broadcast,
			"content": ACK_PREFIX + json.dumps(sorted(codes)),
		}
	).insert(ignore_permissions=True)


def stored_acknowledged(broadcast: str) -> set[str]:
	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "WhatsApp Broadcast",
			"reference_name": broadcast,
			"content": ["like", ACK_PREFIX + "%"],
		},
		fields=["content"],
		order_by="creation desc, name desc",
		limit=1,
	)
	if not rows:
		return set()
	try:
		return set(json.loads(rows[0]["content"][len(ACK_PREFIX):]))
	except ValueError:
		return set()


def resume_acknowledged(broadcast: str, preview: dict[str, Any]) -> set[str]:
	"""Codes still acknowledged on resume. A warning the operator never accepted at start refuses the resume."""
	stored = stored_acknowledged(broadcast)
	current = {_code(w) for w in preview.get("warnings") or []}
	if current - stored:
		raise StartRefused(
			"warnings_changed",
			_("New warnings appeared since this broadcast started; review them and start a new one if needed."),
			warnings=list(preview.get("warnings") or []),
		)
	return current & stored


def recheck_locked(broadcast, preview, *, resuming, override_warnings, expected_count):
	"""Re-count and re-check once the start locks are held; returns ``(fresh preview, acknowledged codes)``.

	Everything read before the lock may be stale (rows, picks, template category, 24h budget)."""
	counted = int(frappe.db.count(RECIPIENT, {"broadcast": broadcast, "status": ["in", ["queued", "deferred"]]}) or 0)
	if expected_count is not None and counted != int(expected_count):
		raise StartRefused(
			"recipients_changed",
			_("The recipients changed since you confirmed ({0} now, {1} confirmed); review and confirm again.").format(
				counted, expected_count
			),
			queued=counted,
		)
	preview = broadcast_limits.preview(broadcast) or preview
	deferred = int(frappe.db.count(RECIPIENT, {"broadcast": broadcast, "status": "deferred"}) or 0)
	acknowledged = check_preview(preview, deferred, None if resuming else (override_warnings or []))
	issues = audience_check.purpose_issues(broadcast, preview.get("category"))
	if issues:
		raise StartRefused(issues[0]["code"], issues[0]["message"], blocking=issues)
	if resuming:
		acknowledged = resume_acknowledged(broadcast, preview)
	return preview, acknowledged


def apply_budget_hold(broadcast, gateway, preview, acknowledged, resuming) -> int:
	"""Hold rows beyond the (post-lock) 24h budget when over_budget was accepted; remember accepted codes."""
	held = 0
	if "over_budget" in acknowledged and preview.get("remaining_24h") is not None:
		held = defer_over_budget(broadcast, int(preview["remaining_24h"]), gateway)
	if not resuming:
		record_acknowledged(broadcast, acknowledged)
	return held
