# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Reusable fake-clock helpers for Layer A (mocked-frappe, no bench)
automation/scheduler tests.

Project rule this exists to satisfy: "Automation/scheduler tests must not
sleep for real time. Introduce a testable clock/time abstraction where
required. Test: current time -> advance -> due automation -> scheduler
decision. Make time-based behaviour reproducible."

Why a patch helper instead of a product-code clock dependency
---------------------------------------------------------------
Both `huf/ai/automation_scheduler.py` and `huf/ai/agent_scheduler.py` read
"now" via a single call at the top of their whitelisted entrypoint:

    from frappe.utils import now_datetime, add_to_date
    ...
    now = now_datetime().replace(microsecond=0)

Because that's a `from-import`, `now_datetime` and `add_to_date` are names
bound directly in each scheduler module's own namespace at import time.
Patching `frappe.utils.now_datetime` after import has *no effect* on code
that already holds the old reference - the scheduler modules would keep
calling the original function. The two real options are:

  1. Add a clock-dependency-injection seam to the product code (e.g. an
     optional `now=None` parameter, or a `huf.ai.clock` module every
     scheduler imports and calls through). This changes call signatures /
     adds a new import surface to code that's part of a live dual-runtime
     migration (see docs/testing/CURRENT_STATE.md section 7) - higher risk
     for a test-infra change.
  2. Patch the `now_datetime`/`add_to_date` names *inside* each scheduler
     module directly, via `unittest.mock.patch.object(module, "now_datetime",
     ...)`. This is exactly what `patch.object` is for, requires zero product
     code changes, and is already the pattern this repo's Layer A tests use
     for other external-dependency mocking (see `test_factories.py`,
     `test_p0_commit_hazards.py`).

Option 2 is lower-risk and non-invasive, so that's what `patch_clock` below
does. `FakeClock` is the controllable "now" both `now_datetime` and
`add_to_date` route through, with a `.advance(...)` method so tests move
time forward deterministically instead of sleeping for real time.

Usage
-----
    from huf.ai import automation_scheduler
    from huf.ai.tests.clock_helpers import FakeClock, patch_clock

    with patch_clock(automation_scheduler, initial="2026-01-01 00:00:00") as clock:
        automation_scheduler.run_due_automations()
        clock.advance(days=1)
        automation_scheduler.run_due_automations()
"""

from __future__ import annotations

import calendar
import datetime as _dt
from contextlib import contextmanager
from unittest.mock import patch


def _to_datetime(value):
	"""Parse a Frappe-style datetime string or pass a `datetime` through."""
	if isinstance(value, _dt.datetime):
		return value
	if isinstance(value, _dt.date):
		return _dt.datetime(value.year, value.month, value.day)
	if isinstance(value, str):
		for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
			try:
				return _dt.datetime.strptime(value, fmt)
			except ValueError:
				continue
		raise ValueError(f"Unparseable datetime string: {value!r}")
	raise TypeError(f"Cannot convert {value!r} to datetime")


class FakeClock:
	"""A settable, advanceable stand-in for "now" - never sleeps for real time.

	Exposes `now_datetime`/`add_to_date` methods with the same call shape as
	their `frappe.utils` counterparts, so `patch_clock` can bind them
	directly in place of the real functions inside a scheduler module.
	"""

	def __init__(self, initial="2026-01-01 00:00:00"):
		self._now = _to_datetime(initial)

	def now(self):
		return self._now

	def set(self, value):
		self._now = _to_datetime(value)
		return self._now

	def advance(self, **kwargs):
		"""Advance the fake clock by a timedelta-like amount (deterministic,
		no real sleeping), e.g. `clock.advance(days=1)`,
		`clock.advance(seconds=90)`."""
		self._now = self._now + _dt.timedelta(**kwargs)
		return self._now

	def now_datetime(self):
		"""Drop-in replacement for `frappe.utils.now_datetime`."""
		return self._now

	def add_to_date(self, date=None, **kwargs):
		"""Drop-in replacement for `frappe.utils.add_to_date`. Resolves
		`date=None` (Frappe's "from now" convention) against this fake
		clock's current time instead of the real wall clock, then applies
		the same year/month/day/hour/... deltas."""
		base = self._now if date is None else _to_datetime(date)

		years = kwargs.pop("years", 0)
		months = kwargs.pop("months", 0)
		if years or months:
			total_months = base.month - 1 + months + years * 12
			year = base.year + total_months // 12
			month = total_months % 12 + 1
			day = min(base.day, calendar.monthrange(year, month)[1])
			base = base.replace(year=year, month=month, day=day)

		return base + _dt.timedelta(**kwargs)


@contextmanager
def patch_clock(module, initial="2026-01-01 00:00:00", clock: "FakeClock | None" = None):
	"""Patch the `now_datetime`/`add_to_date` names bound inside `module`
	(e.g. `huf.ai.automation_scheduler` or `huf.ai.agent_scheduler`) so they
	route through a `FakeClock` instead of the real wall clock.

	Yields the `FakeClock` in use so the caller can `.advance()`/`.set()` it
	mid-test to move "now" forward deterministically. Only patches names
	that actually exist on the module, so this stays safe to use against any
	future scheduler-shaped module that imports just one of the two names.
	"""
	if clock is None:
		clock = FakeClock(initial)

	patchers = []
	if hasattr(module, "now_datetime"):
		patchers.append(patch.object(module, "now_datetime", clock.now_datetime))
	if hasattr(module, "add_to_date"):
		patchers.append(patch.object(module, "add_to_date", clock.add_to_date))

	for p in patchers:
		p.start()
	try:
		yield clock
	finally:
		for p in patchers:
			p.stop()
