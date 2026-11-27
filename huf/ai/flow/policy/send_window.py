"""Send window primitive: may a message leave at this moment, and if not, when next?

Pure (no frappe). A window covers ``[start, end)`` on the wall clock of a time zone, on the weekdays where it
starts (0 = Monday). ``end < start`` runs overnight into the next day. ``end == 00:00`` means midnight at the
end of the day, so ``00:00`` to ``00:00`` is the whole day. No windows means never open.

DST: a moment is allowed only by what the local clock shows then. A skipped opening time opens when the
clock jumps into the window; a repeated hour is allowed both times it is inside the window.

Every bad input raises ``ValueError``: a caller guarding a send must treat it as a block.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

ALL_WEEKDAYS = frozenset(range(7))
MIDNIGHT = time(0, 0)
# Two weeks and a day: a weekly window that DST skips entirely is found the following week.
SEARCH_DAYS = 15
OFFSET_SAMPLE = timedelta(hours=6)
ONE_SECOND = timedelta(seconds=1)


class Window(NamedTuple):
	start: time
	end: time
	weekdays: frozenset = ALL_WEEKDAYS


class SendWindowDecision(NamedTuple):
	allowed: bool
	# Aware UTC moment the window next opens. None when allowed, or when it never opens.
	next_open: datetime | None = None


def check_send_window(now: datetime, zone: str, windows: Iterable[Window]) -> SendWindowDecision:
	"""``now`` must be timezone-aware; ``zone`` is an IANA name such as ``Asia/Kolkata``."""
	if not isinstance(now, datetime) or now.utcoffset() is None:
		raise ValueError("now must be a timezone-aware datetime")
	tz = _zone(zone)
	windows = [_validated(window) for window in windows]
	now = now.astimezone(timezone.utc)
	if _is_open(now, tz, windows):
		return SendWindowDecision(True)
	return SendWindowDecision(False, _next_open(now, tz, windows))


def _zone(name: str) -> ZoneInfo:
	try:
		return ZoneInfo(name)
	except Exception as error:
		raise ValueError("unknown time zone") from error


def _validated(window: Window) -> Window:
	start, end, weekdays = window
	for value in (start, end):
		if not isinstance(value, time) or value.tzinfo is not None:
			raise ValueError("window start and end must be times without a time zone")
	if start == end and start != MIDNIGHT:
		raise ValueError("window start and end must differ")
	weekdays = frozenset(weekdays)
	if not weekdays <= ALL_WEEKDAYS:
		raise ValueError("weekdays must be numbers from 0 (Monday) to 6 (Sunday)")
	return Window(start, end, weekdays)


def _is_open(moment: datetime, tz: ZoneInfo, windows: list[Window]) -> bool:
	local = moment.astimezone(tz)
	weekday, clock = local.weekday(), local.time()
	for start, end, weekdays in windows:
		if start < end or end == MIDNIGHT:
			if weekday in weekdays and start <= clock and (end == MIDNIGHT or clock < end):
				return True
		elif (weekday in weekdays and clock >= start) or ((weekday - 1) % 7 in weekdays and clock < end):
			return True
	return False


def _next_open(now: datetime, tz: ZoneInfo, windows: list[Window]) -> datetime | None:
	"""The window opens either when the clock reaches a start time or when a DST change jumps into it."""
	offsets, transitions = _offsets(now, tz)
	first_day = now.astimezone(tz).date() - timedelta(days=1)
	candidates = set(transitions)
	for days in range(SEARCH_DAYS + 1):
		day = first_day + timedelta(days=days)
		for window in windows:
			wall = datetime.combine(day, window.start, timezone.utc)
			candidates.update(wall - offset for offset in offsets)
	return min((c for c in candidates if c > now and _is_open(c, tz, windows)), default=None)


def _offsets(now: datetime, tz: ZoneInfo) -> tuple[set[timedelta], list[datetime]]:
	"""UTC offsets in force over the search range, and the moments (to the second) where they change."""
	moment = now.replace(microsecond=0) - timedelta(days=1)
	last = now + timedelta(days=SEARCH_DAYS)
	offset = moment.astimezone(tz).utcoffset()
	offsets, transitions = {offset}, []
	while moment < last:
		later = moment + OFFSET_SAMPLE
		later_offset = later.astimezone(tz).utcoffset()
		if later_offset != offset:
			low, high = moment, later
			while high - low > ONE_SECOND:
				middle = low + timedelta(seconds=int((high - low).total_seconds()) // 2)
				if middle.astimezone(tz).utcoffset() == offset:
					low = middle
				else:
					high = middle
			transitions.append(high)
			offsets.add(later_offset)
		moment, offset = later, later_offset
	return offsets, transitions
