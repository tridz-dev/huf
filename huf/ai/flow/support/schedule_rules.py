"""Plain-language checks for a Schedule trigger's ``cron`` and ``time_zone``.

Pure functions (no database): the activation rules, the sidebar's server twin and the tests all call them. The wording
mirrors ``frontend/src/lib/flow-graph/flowSchedule.ts`` so the editor and the server say the same thing.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

SCHEDULE_TYPE = "trigger.schedule"

_NAME = r"[A-Za-z]{3}"
_ATOM = rf"(?:\*|\d+|{_NAME}|L)(?:-(?:\d+|{_NAME}))?(?:/\d+)?"
_FIELD = re.compile(rf"^{_ATOM}(?:,{_ATOM})*$")

#: (low, high) per cron position: minute, hour, day of month, month, day of week (0 and 7 are both Sunday).
_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_DAYS = {d: i for i, d in enumerate("sun mon tue wed thu fri sat".split())}


def _number(token: str, position: int) -> int | None:
	if token.isdigit():
		return int(token)
	token = token.lower()
	if position == 3:
		return _MONTHS.get(token)
	if position == 4:
		return _DAYS.get(token)
	return None


def _part_in_range(part: str, position: int) -> bool:
	low, high = _LIMITS[position]
	for item in part.split(","):
		base, _, step = item.partition("/")
		if step and int(step) < 1:
			return False
		if base in ("*", "L"):
			continue
		bounds = [_number(b, position) for b in base.split("-")]
		if any(b is None or b < low or b > high for b in bounds):
			return False
		if len(bounds) == 2 and bounds[1] < bounds[0]:
			return False
	return True


def cron_problem(cron) -> str | None:
	"""A sentence saying what is wrong with ``cron`` (5 parts: minute hour day month weekday), or None when it is fine."""
	text = cron.strip() if isinstance(cron, str) else ""
	if not text:
		return "Choose when this flow should run."
	parts = text.split()
	if len(parts) != 5:
		return "A schedule needs 5 parts: minute hour day month weekday (for example 0 9 * * 1)."
	if not all(_FIELD.match(p) for p in parts):
		return "One of the schedule parts is not valid. Use numbers, *, ranges like 1-5, or steps like */15."
	if not all(_part_in_range(p, i) for i, p in enumerate(parts)):
		return "One of the schedule numbers is out of range: minute 0-59, hour 0-23, day 1-31, month 1-12, weekday 0-6."
	from croniter import croniter

	if not croniter.is_valid(text):
		return "This schedule cannot be understood. Check each part, for example 0 9 * * 1."
	return None


def time_zone_problem(zone) -> str | None:
	"""A sentence when ``zone`` is not an IANA time zone name; None when it is empty (site zone) or valid."""
	if zone in (None, ""):
		return None
	if not isinstance(zone, str):
		return "The time zone must be a name such as Asia/Kolkata."
	try:
		ZoneInfo(zone)
	except Exception:
		return f"{zone!r} is not a time zone name. Use one such as Asia/Kolkata or Europe/London."
	return None


def minute_in_zone(minute: datetime, zone: str | None, system_zone: str | None = None) -> datetime:
	"""``minute`` (naive, in the site time zone) as the naive wall-clock minute in ``zone``.

	A schedule fires on the clock of the zone the author picked. With no zone, or a name that is not a time zone,
	the site zone is used, which is the clock ``minute`` is already on.
	"""
	if not zone or not isinstance(zone, str):
		return minute
	from zoneinfo import ZoneInfo

	try:
		target = ZoneInfo(zone)
		if system_zone is None:
			from frappe.utils import get_system_timezone

			system_zone = get_system_timezone()
		source = ZoneInfo(system_zone)
	except Exception:
		return minute
	return minute.replace(tzinfo=source).astimezone(target).replace(tzinfo=None)


def schedule_problems(defn) -> list[str]:
	"""Every schedule problem in a flow definition, ``trigger 'id': sentence``."""
	problems: list[str] = []
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	for node in nodes or []:
		if not isinstance(node, dict) or node.get("type") != SCHEDULE_TYPE:
			continue
		config = node.get("config") if isinstance(node.get("config"), dict) else {}
		for issue in (cron_problem(config.get("cron")), time_zone_problem(config.get("time_zone"))):
			if issue:
				problems.append(f"trigger {node.get('id')!r}: {issue}")
	return problems
