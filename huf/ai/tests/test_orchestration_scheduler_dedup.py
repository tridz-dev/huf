# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) test for ST-R1.3 (WP-R1 / F-26),
duplicate-enqueue half:

`process_orchestrations()` iterates orchestrations with no step yet
`in_progress` (e.g. the previous tick's enqueue hasn't been picked up by a
worker yet) and would otherwise enqueue a second, fully concurrent
`execute_next_step` job for the same orchestration. A short-TTL
`frappe.cache().set(..., nx=True)` claim per orchestration must prevent that:
the second tick's claim attempt fails and the enqueue is skipped.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_orchestration_scheduler_dedup.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	sys.modules["frappe"] = frappe_mock
if "frappe.utils" not in sys.modules:
	utils_mock = MagicMock()
	sys.modules["frappe.utils"] = utils_mock
	sys.modules["frappe"].utils = utils_mock

if "huf.ai.agent_integration" not in sys.modules:
	sys.modules["huf.ai.agent_integration"] = MagicMock()

from huf.ai.orchestration import scheduler  # noqa: E402


class _FakeStep:
	def __init__(self, status="pending"):
		self.status = status
		self.step_index = 1
		self.modified = None


class _FakeOrch:
	def __init__(self, name="ORCH-0001", status="Running"):
		self.name = name
		self.status = status
		self.agent_orchestration_plan = [_FakeStep(status="pending")]
		self.modified = None
		self.error_log = ""
		self.save = MagicMock()


class SchedulerDedupTestCase(unittest.TestCase):
	"""Real in-process fake cache backing frappe.cache().set(..., nx=True) /
	.delete(...), so the second call in the same test genuinely observes the
	first call's claim (unlike a MagicMock stub, which has no state)."""

	def setUp(self):
		self._store = {}

		def _cache_set(key, value, ex=None, nx=False):
			if nx and key in self._store:
				return False
			self._store[key] = value
			return True

		def _cache_delete(key):
			self._store.pop(key, None)

		self.fake_cache = MagicMock()
		self.fake_cache.set.side_effect = _cache_set
		self.fake_cache.delete.side_effect = _cache_delete

		self.patchers = [
			patch.object(scheduler.frappe, "cache", return_value=self.fake_cache),
			patch.object(scheduler.frappe.db, "exists", return_value=True),
			patch.object(scheduler.frappe.db, "commit"),
			patch.object(scheduler, "time_diff_in_seconds", return_value=0),
			patch.object(scheduler, "now_datetime", return_value="2026-01-01 12:00:00"),
			patch.object(scheduler.frappe, "enqueue"),
			patch.object(
				scheduler.frappe, "get_all",
				return_value=[type("Row", (), {"name": "ORCH-0001"})()],
			),
		]
		for p in self.patchers:
			p.start()
			self.addCleanup(p.stop)

	def test_two_ticks_with_no_in_progress_step_enqueue_only_once(self):
		"""Simulates a slow queue: the same orchestration, with no step yet
		in_progress, is seen by two consecutive scheduler ticks. Only the
		first tick's enqueue should go through."""
		orch = _FakeOrch(name="ORCH-0001", status="Running")

		with patch.object(scheduler.frappe, "get_doc", return_value=orch):
			scheduler.process_orchestrations()
			scheduler.process_orchestrations()

		scheduler.frappe.enqueue.assert_called_once()
		_, kwargs = scheduler.frappe.enqueue.call_args
		self.assertEqual(kwargs.get("orch_name"), "ORCH-0001")

	def test_claim_released_allows_a_later_tick_to_enqueue_again(self):
		"""Once the claim is released (execute_next_step's finally, modeled
		here directly via the same key helper), a subsequent tick may
		enqueue again."""
		orch = _FakeOrch(name="ORCH-0001", status="Running")

		with patch.object(scheduler.frappe, "get_doc", return_value=orch):
			scheduler.process_orchestrations()
			# Simulate execute_next_step's finally releasing the claim.
			self.fake_cache.delete(scheduler._orch_enqueue_lock_key("ORCH-0001"))
			scheduler.process_orchestrations()

		self.assertEqual(scheduler.frappe.enqueue.call_count, 2)


if __name__ == "__main__":
	unittest.main(verbosity=2)
