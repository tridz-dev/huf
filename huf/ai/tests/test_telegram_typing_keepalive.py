# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import telegram_typing_keepalive as ka


class FakeClock:
	def __init__(self):
		self.t = 0.0

	def __call__(self):
		return self.t


class TestTypingKeepalive(TestCase):
	def setUp(self):
		self._enabled = ka.ENABLED
		ka.ENABLED = True
		with ka._lock:
			ka._active.clear()

	def tearDown(self):
		ka.ENABLED = self._enabled
		with ka._lock:
			ka._active.clear()

	def _run(self, key, send, skip=None, ticks=3, clock=None, **kw):
		"""Start without a real thread and drive the loop with a fake wait."""
		clock = clock or FakeClock()
		count = {"n": 0}
		holder = {}

		def wait(sec):
			count["n"] += 1
			clock.t += sec
			if count["n"] > ticks:
				holder["ka"].stop_flag.set()

		self.assertTrue(ka.start(key, send, skip, clock=clock, wait=wait, spawn=False, **kw))
		holder["ka"] = ka._active[key]
		holder["ka"].run()
		return clock

	def test_repeats_every_interval(self):
		send = MagicMock()
		self._run("g:1:", send, ticks=3)
		self.assertEqual(send.call_count, 3)
		self.assertEqual(ka.active_count(), 0)

	def test_cap_90s(self):
		send = MagicMock()
		clock = self._run("g:1:", send, ticks=1000)
		self.assertLessEqual(clock.t, 92)
		self.assertLessEqual(send.call_count, 22)

	def test_stop_ends_loop(self):
		send = MagicMock()
		ka.start("g:1:", send, spawn=False)
		ka.stop("g:1:")
		self.assertEqual(ka.active_count(), 0)

	def test_real_thread_stops_on_stop(self):
		sent = threading.Event()
		ka.start("g:2:", sent.set, interval=0.01)
		self.assertTrue(sent.wait(2))
		ka.stop("g:2:")
		self.assertEqual(ka.active_count(), 0)

	def test_one_per_chat_extends(self):
		clock = FakeClock()
		ka.start("g:1:", MagicMock(), clock=clock, spawn=False)
		first = ka._active["g:1:"]
		clock.t = 50
		self.assertTrue(ka.start("g:1:", MagicMock(), clock=clock, spawn=False))
		self.assertIs(ka._active["g:1:"], first)
		self.assertEqual(first.deadline, 140)
		self.assertEqual(ka.active_count(), 1)

	def test_thread_cap(self):
		for i in range(ka.MAX_THREADS):
			self.assertTrue(ka.start(f"g:{i}:", MagicMock(), spawn=False))
		self.assertFalse(ka.start("g:over:", MagicMock(), spawn=False))

	def test_exceptions_swallowed(self):
		send = MagicMock(side_effect=RuntimeError("boom"))
		self._run("g:1:", send, ticks=2)
		self.assertEqual(send.call_count, 2)
		self.assertFalse(ka.start("x", None, skip=None, clock=None))  # bad clock: swallowed

	def test_stream_active_skips(self):
		send = MagicMock()
		self._run("g:1:", send, skip=lambda: True, ticks=3)
		send.assert_not_called()

	def test_disabled_by_default_in_tests(self):
		ka.ENABLED = None
		with patch("frappe.flags", SimpleNamespace(in_test=True)):
			self.assertFalse(ka.start("g:1:", MagicMock(), spawn=False))
		self.assertEqual(ka.active_count(), 0)


class TestKeepaliveSiteContext(TestCase):
	def setUp(self):
		ka.ENABLED = True
		self.addCleanup(setattr, ka, "ENABLED", None)
		self.addCleanup(patch.stopall)

	def test_thread_without_local_site_inits_and_destroys_and_records(self):
		import frappe

		from huf.ai.gateway_adapters import telegram_typing_metrics as tm

		calls = []
		patch("frappe.local", SimpleNamespace()).start()
		patch("frappe.init", side_effect=lambda site=None, **k: calls.append(("init", site))).start()
		patch("frappe.destroy", side_effect=lambda: calls.append(("destroy",))).start()
		rec = patch.object(tm, "record_keepalive_tick").start()
		ticks = iter([False, True])
		ran = []

		def tick():
			ran.append(1)
			tm.record_keepalive_tick("GW")

		ok = ka.start("gs:1:", tick, lambda: next(ticks), wait=lambda s: None, site="s.local", spawn=False)
		self.assertTrue(ok)
		ka._active["gs:1:"].run()
		self.assertEqual(calls, [("init", "s.local"), ("destroy",)])
		self.assertEqual(len(ran), 1)  # second tick honoured the stream skip
		rec.assert_called_once_with("GW")
		self.assertEqual(ka.active_count(), 0)

	def test_init_failure_never_raises(self):
		patch("frappe.local", SimpleNamespace()).start()
		patch("frappe.init", side_effect=RuntimeError("x")).start()
		send = MagicMock()
		ka.start("gs:2:", send, lambda: True, wait=lambda s: None, site="s", spawn=False)
		ka._active["gs:2:"].run()
		send.assert_not_called()
