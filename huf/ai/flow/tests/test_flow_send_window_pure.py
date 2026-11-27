"""Send window primitive (H-W2-06).

The module under test does not use frappe, so this also runs without a bench:

	python3 huf/ai/flow/tests/test_flow_send_window_pure.py
"""

import importlib.util
import os
import unittest
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

try:
	from huf.ai.flow.policy import send_window as sw
except ImportError:  # pragma: no cover - frappe-less environments
	_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "policy", "send_window.py")
	_SPEC = importlib.util.spec_from_file_location("huf_send_window_standalone", _PATH)
	sw = importlib.util.module_from_spec(_SPEC)
	_SPEC.loader.exec_module(sw)


def utc(*parts):
	return datetime(*parts, tzinfo=timezone.utc)


def window(start, end, weekdays=range(7)):
	return sw.Window(time(*start), time(*end), frozenset(weekdays))


OFFICE = [window((9, 0), (18, 0))]


class TestSendWindow(unittest.TestCase):
	def check(self, now, zone="UTC", windows=OFFICE):
		return sw.check_send_window(now, zone, windows)

	def test_start_is_inside_and_end_is_outside(self):
		self.assertEqual(self.check(utc(2030, 1, 7, 9)), (True, None))
		self.assertEqual(self.check(utc(2030, 1, 7, 17, 59, 59)), (True, None))
		self.assertEqual(self.check(utc(2030, 1, 7, 8, 59, 59)), (False, utc(2030, 1, 7, 9)))
		self.assertEqual(self.check(utc(2030, 1, 7, 18)), (False, utc(2030, 1, 8, 9)))

	def test_zone_of_the_recipient_decides(self):
		# 04:00 UTC is 09:30 in Kolkata (open) and 23:00 the day before in New York (closed).
		self.assertTrue(self.check(utc(2030, 1, 7, 4), "Asia/Kolkata").allowed)
		self.assertEqual(self.check(utc(2030, 1, 7, 4), "America/New_York"), (False, utc(2030, 1, 7, 14)))

	def test_aware_input_in_any_offset(self):
		now = datetime(2030, 1, 7, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
		self.assertEqual(self.check(now), (False, utc(2030, 1, 7, 9)))

	def test_weekdays(self):
		weekdays = [window((9, 0), (18, 0), range(5))]
		# 2030-01-11 is a Friday.
		self.assertEqual(self.check(utc(2030, 1, 11, 19), windows=weekdays), (False, utc(2030, 1, 14, 9)))

	def test_overnight_belongs_to_the_day_it_starts(self):
		friday_night = [window((22, 0), (2, 0), [4])]
		self.assertTrue(self.check(utc(2030, 1, 12, 1), windows=friday_night).allowed)
		self.assertEqual(self.check(utc(2030, 1, 11, 1), windows=friday_night), (False, utc(2030, 1, 11, 22)))

	def test_midnight_end_and_whole_day(self):
		evening = [window((20, 0), (0, 0), [0])]
		self.assertTrue(self.check(utc(2030, 1, 7, 23, 59), windows=evening).allowed)
		self.assertFalse(self.check(utc(2030, 1, 8, 0), windows=evening).allowed)
		self.assertTrue(self.check(utc(2030, 1, 8, 0), windows=[window((0, 0), (0, 0))]).allowed)

	def test_earliest_of_several_windows(self):
		windows = [window((14, 0), (15, 0)), window((12, 0), (13, 0))]
		self.assertEqual(self.check(utc(2030, 1, 7, 10), windows=windows), (False, utc(2030, 1, 7, 12)))

	def test_never_open(self):
		for windows in ([], [window((9, 0), (18, 0), [])]):
			self.assertEqual(self.check(utc(2030, 1, 7, 10), windows=windows), (False, None))

	def test_dst_changes_the_utc_opening(self):
		# New York springs forward on 2030-03-10: 09:00 moves from 14:00 UTC to 13:00 UTC.
		self.assertEqual(self.check(utc(2030, 3, 9, 23), "America/New_York"), (False, utc(2030, 3, 10, 13)))

	def test_dst_skipped_start_opens_at_the_jump(self):
		# 02:30 does not exist on 2030-03-10; the clock goes from 02:00 to 03:00 at 07:00 UTC.
		windows = [window((2, 30), (4, 0))]
		self.assertEqual(
			self.check(utc(2030, 3, 10, 6), "America/New_York", windows), (False, utc(2030, 3, 10, 7))
		)

	def test_dst_window_wholly_skipped_waits_for_the_next_week(self):
		sunday = [window((2, 0), (3, 0), [6])]
		self.assertEqual(
			self.check(utc(2030, 3, 4), "America/New_York", sunday), (False, utc(2030, 3, 17, 6))
		)

	def test_dst_repeated_hour_reopens(self):
		# New York falls back on 2030-11-03 at 06:00 UTC: 01:00-02:00 happens twice.
		windows = [window((0, 0), (1, 30))]
		self.assertEqual(
			self.check(utc(2030, 11, 3, 5, 45), "America/New_York", windows), (False, utc(2030, 11, 3, 6))
		)

	def test_matrix_never_allows_outside_the_window_and_never_skips_an_opening(self):
		"""Compare with a minute-by-minute walk of the local clock around DST changes."""
		cases = {
			"America/New_York": (utc(2030, 3, 10, 5), utc(2030, 11, 3, 4)),
			"Europe/London": (utc(2030, 3, 30, 23), utc(2030, 10, 26, 23)),
			"Australia/Lord_Howe": (utc(2030, 4, 6, 13), utc(2030, 10, 5, 13)),
			"Asia/Kolkata": (utc(2030, 1, 7),),
		}
		shapes = [
			((9, 0), (18, 0)),
			((0, 0), (1, 30)),
			((1, 15), (2, 15)),
			((2, 30), (4, 0)),
			((22, 0), (1, 45)),
		]
		minute = timedelta(minutes=1)
		for zone, starts in cases.items():
			tz = ZoneInfo(zone)
			for start, end in shapes:
				windows = [window(start, end)]

				def inside(moment):
					clock = moment.astimezone(tz).time()
					if time(*start) < time(*end):
						return time(*start) <= clock < time(*end)
					return clock >= time(*start) or clock < time(*end)

				for first in starts:
					for step in range(0, 8 * 60, 15):
						now = first + step * minute
						expected = None
						if not inside(now):
							expected = now + minute
							while not inside(expected):
								expected += minute
						with self.subTest(zone=zone, start=start, end=end, now=now):
							self.assertEqual(
								sw.check_send_window(now, zone, windows), (inside(now), expected)
							)

	def test_bad_input_raises(self):
		now = utc(2030, 1, 7, 10)
		bad = [
			(datetime(2030, 1, 7, 10), "UTC", OFFICE),
			(None, "UTC", OFFICE),
			(now, "Mars/Olympus", OFFICE),
			(now, "", OFFICE),
			(now, None, OFFICE),
			(now, "UTC", [window((9, 0), (9, 0))]),
			(now, "UTC", [window((9, 0), (18, 0), [7])]),
			(now, "UTC", [sw.Window("09:00", time(18, 0))]),
			(now, "UTC", [sw.Window(time(9, tzinfo=timezone.utc), time(18, 0))]),
		]
		for args in bad:
			with self.subTest(args=args), self.assertRaises(ValueError):
				sw.check_send_window(*args)


if __name__ == "__main__":
	unittest.main()
