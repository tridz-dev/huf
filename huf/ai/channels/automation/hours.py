"""Business hours gate for inbound gateway events.

Registered as a pre-route hook (``huf.ai.channels.pipeline.PRE_ROUTE_HOOKS``). Per Gateway:

* ``business_hours_enabled`` off: no restriction, the hook passes through.
* ``after_hours_mode == "agent_24_7"``: the agent answers at all times, the hook passes through.
* Outside the window (or on a holiday) with ``away_message``/``away_template``:
  the away reply is sent at most once per conversation per closed window. Later messages in the same
  closed window are dropped (no agent run). The window is identified by its next opening time, so the
  next closed window gets a new reply. The cache key TTL runs until that opening time.

Window rules: a row covers ``[start_time, end_time)`` on its weekday. ``end_time < start_time`` is an
overnight range: the part after midnight belongs to the window that started the previous day.
A holiday closes every window that starts on that date. Holidays come from the gateway's ``holidays``
child rows (always available) and, when the ERPNext/HRMS ``Holiday List`` DocType is installed, from the
Holiday List named in the ``holiday_list`` Data field. The two sources are unioned.
Times are evaluated in the site timezone (``get_system_timezone``).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import frappe
import pytz
from frappe.utils import getdate

from huf.ai.channels.pipeline import Decision

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SEARCH_DAYS = 8
ONE_DAY_SECONDS = 86400
_CACHE_PREFIX = "huf:bh_away"


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


def _site_timezone() -> str:
	return frappe.utils.get_system_timezone()


def _local_naive(now: datetime, tz_name: str) -> datetime:
	"""Site-local wall-clock time as a naive datetime. Naive input is taken as already site-local."""
	if now.tzinfo is None:
		return now
	try:
		tz = pytz.timezone(tz_name)
	except pytz.UnknownTimeZoneError:
		tz = pytz.UTC
	return now.astimezone(tz).replace(tzinfo=None)


def _to_time(value: Any) -> time | None:
	if value is None or value == "":
		return None
	if isinstance(value, time):
		return value.replace(tzinfo=None)
	if isinstance(value, timedelta):
		total = int(value.total_seconds())
		return time((total // 3600) % 24, (total // 60) % 60, total % 60)
	parts = str(value).split(":")
	try:
		return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
	except (ValueError, IndexError):
		return None


def _windows(gateway_doc) -> list[tuple[int, time, time]]:
	out = []
	for row in gateway_doc.get("business_hours") or []:
		if row.weekday not in WEEKDAYS:
			continue
		start, end = _to_time(row.start_time), _to_time(row.end_time)
		if start is None or end is None or start == end:
			continue
		out.append((WEEKDAYS.index(row.weekday), start, end))
	return out


def _holidays(gateway_doc) -> set[date]:
	"""Union of the gateway's own ``holidays`` rows and the optional ERPNext Holiday List."""
	days: set[date] = set()
	for row in gateway_doc.get("holidays") or []:
		if row.get("holiday_date"):
			days.add(getdate(row.get("holiday_date")))

	name = gateway_doc.get("holiday_list")
	# Holiday List is ERPNext/HRMS; on a frappe-only site the name is simply ignored.
	if name and frappe.db.exists("DocType", "Holiday List") and frappe.db.exists("Holiday List", name):
		holiday_list = frappe.get_cached_doc("Holiday List", name)
		days.update(getdate(row.holiday_date) for row in holiday_list.get("holidays") or [] if row.holiday_date)
	return days


def _open_at(local: datetime, windows: list, holidays: set[date]) -> bool:
	weekday, t, day = local.weekday(), local.time(), local.date()
	for w, start, end in windows:
		if start < end:
			if weekday == w and start <= t < end and day not in holidays:
				return True
			continue
		# Overnight: the evening part starts on weekday w, the tail after midnight on w + 1.
		if weekday == w and t >= start and day not in holidays:
			return True
		if weekday == (w + 1) % 7 and t < end and (day - timedelta(days=1)) not in holidays:
			return True
	return False


def _next_open(local: datetime, windows: list, holidays: set[date]) -> datetime | None:
	"""First site-local opening instant strictly after ``local`` (a window start), or None."""
	for offset in range(SEARCH_DAYS + 1):
		day = local.date() + timedelta(days=offset)
		candidates = [
			datetime.combine(day, start)
			for w, start, _end in windows
			if day.weekday() == w and datetime.combine(day, start) > local
		]
		candidates = [c for c in candidates if _open_at(c, windows, holidays)]
		if candidates:
			return min(candidates)
	return None


def is_open(gateway_doc, now: datetime | None = None) -> bool:
	"""True when the gateway accepts agent traffic at ``now`` (no restriction when hours are disabled)."""
	if not gateway_doc.get("business_hours_enabled"):
		return True
	local = _local_naive(now or _utcnow(), _site_timezone())
	return _open_at(local, _windows(gateway_doc), _holidays(gateway_doc))


def business_hours_hook(context: dict) -> Decision | None:
	ctx = context or {}
	gateway_name = ctx.get("gateway")
	if not gateway_name:
		return None
	gateway = frappe.get_doc("Gateway", gateway_name)
	if not gateway.get("business_hours_enabled"):
		return None
	mode = gateway.get("after_hours_mode") or "agent_24_7"
	if mode == "agent_24_7":
		return None

	tz_name = _site_timezone()
	now = _utcnow()
	local = _local_naive(now, tz_name)
	windows, holidays = _windows(gateway), _holidays(gateway)
	if _open_at(local, windows, holidays):
		return None

	text = (gateway.get("away_message") or "").strip()
	if not text:
		# Nothing to say after hours: keep the agent off without sending an empty reply.
		return Decision("drop")

	next_open = _next_open(local, windows, holidays)
	conversation = (ctx.get("context") or {}).get("conversation_id") or (ctx.get("context") or {}).get("sender_id")
	key = f"{_CACHE_PREFIX}:{gateway.name}:{conversation or 'none'}:{next_open.isoformat() if next_open else 'never'}"
	cache = frappe.cache()
	# expires=True keeps the lookup out of frappe.local.cache, which would otherwise pin the first miss.
	if cache.get_value(key, expires=True):
		return Decision("drop")
	if next_open:
		local_tz = pytz.timezone(tz_name)
		opens_at = local_tz.localize(next_open, is_dst=False).astimezone(timezone.utc)
		ttl = int((opens_at - now).total_seconds())
	else:
		ttl = ONE_DAY_SECONDS
	cache.set_value(key, 1, expires_in_sec=max(ttl, 1))

	if mode == "away_template":
		return Decision("reply", {"template": gateway.get("away_template") or "", "text": text})
	return Decision("reply", {"text": text})
