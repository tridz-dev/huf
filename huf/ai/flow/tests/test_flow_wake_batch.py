"""Batched wake sweeper (``park.wake_due_waits`` / ``park.wake_chunk``): paging, chunk jobs, budget, one wake per run."""

import json
from collections import Counter
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import park

NOW = datetime(2000, 1, 1, 12, 0, 0)  # in the past, so no other parked run on the site is due
CHUNK_JOB = "huf.ai.flow.runs.park.wake_chunk"
CONTINUATION = "huf.ai.flow.engine.run_flow"


class TestWakeBatch(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.prefix = f"_test-wake-{frappe.generate_hash(length=8)}"
		self.jobs = []  # chunk jobs the sweeper enqueued
		self.continued = Counter()  # continuations enqueued per run
		for target, value in (("WAKE_CHUNK_SIZE", 3), ("WAKE_BUDGET_SECONDS", 600)):
			patcher = patch.object(park, target, value)
			patcher.start()
			self.addCleanup(patcher.stop)
		patcher = patch("frappe.enqueue", side_effect=self._enqueue)
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.db.delete("Agent Flow Run", {"name": ["like", f"{self.prefix}%"]})
		frappe.db.commit()

	def _enqueue(self, method, **kwargs):
		self.assertEqual(kwargs["queue"], "short")
		if method == CHUNK_JOB:
			self.jobs.append((kwargs["names"], kwargs["due_by"]))
		elif method == CONTINUATION:
			self.continued[kwargs["flow_run_name"]] += 1

	def _seed(self, count):
		"""Due runs; pairs share a ``resume_at`` so page boundaries fall inside a tie."""
		names = [f"{self.prefix}-{i:03d}" for i in range(count)]
		waiting = json.dumps({"type": "timer", "node_id": "w1"})
		rows = [
			(name, park.WAIT_STATUS, NOW - timedelta(minutes=count - i // 2), waiting)
			for i, name in enumerate(names)
		]
		frappe.db.bulk_insert("Agent Flow Run", ["name", "status", "resume_at", "waiting"], rows)
		frappe.db.commit()
		return names

	def _run_jobs(self):
		for chunk, due_by in self.jobs:
			park.wake_chunk(chunk, due_by)

	def test_drains_every_page_in_chunks_and_wakes_each_run_once(self):
		names = self._seed(25)
		taken = park.wake_due_waits(now=NOW, limit=5)
		self.assertEqual(taken, names)
		self.assertEqual(set(self.continued), set(names[:3]))  # only the oldest chunk is woken by the tick
		self.assertTrue(all(len(chunk) <= 3 for chunk, _ in self.jobs))
		self._run_jobs()
		self.assertEqual(self.continued, Counter(names))

	def test_double_sweep_and_replayed_jobs_never_double_wake(self):
		names = self._seed(10)
		park.wake_due_waits(now=NOW, limit=4)
		park.wake_due_waits(now=NOW, limit=4)  # overlaps: the first tick's jobs have not run yet
		self._run_jobs()
		self._run_jobs()
		self.assertEqual(self.continued, Counter(names))
		self.assertEqual(park.wake_due_waits(now=NOW), [])

	def test_late_chunk_job_leaves_a_reparked_run_asleep(self):
		name = self._seed(1)[0]
		frappe.db.set_value("Agent Flow Run", name, "resume_at", NOW + timedelta(hours=1))
		self.assertEqual(park.wake_chunk([name], NOW), [])
		self.assertEqual(frappe.db.get_value("Agent Flow Run", name, "status"), park.WAIT_STATUS)
		self.assertFalse(self.continued)

	def test_timer_wait_without_resume_at_is_not_due_and_does_not_block_the_sweep(self):
		"""A handoff parks a run as a timer wait with no ``resume_at``; the sweep must skip it, not loop on it."""
		waiting = json.dumps({"type": "timer", "node_id": "h1", "reason": "handoff", "resume_at": None})
		parked = [f"{self.prefix}-h{i}" for i in range(5)]
		frappe.db.bulk_insert(
			"Agent Flow Run", ["name", "status", "resume_at", "waiting"], [(n, park.WAIT_STATUS, None, waiting) for n in parked]
		)
		frappe.db.commit()
		names = self._seed(3)
		with patch.object(park, "WAKE_BUDGET_SECONDS", 3):  # a regression spins until the budget instead of hanging the suite
			taken = park.wake_due_waits(now=NOW, limit=2)
		self.assertEqual(taken, names)
		self.assertEqual({frappe.db.get_value("Agent Flow Run", n, "status") for n in parked}, {park.WAIT_STATUS})

	def test_page_size_comes_from_site_config(self):
		self._seed(5)
		with (
			patch.dict(frappe.conf, {"huf_flow_wake_page_size": 2}),
			patch.object(park, "_due_page", wraps=park._due_page) as page,
		):
			park.wake_due_waits(now=NOW)
		self.assertEqual([call.args[2] for call in page.call_args_list], [2, 2, 2])

	def test_spent_budget_stops_after_one_page(self):
		names = self._seed(8)
		with patch.object(park, "WAKE_BUDGET_SECONDS", 0):
			self.assertEqual(park.wake_due_waits(now=NOW, limit=4), names[:4])
		self._run_jobs()  # the next tick takes only what is still parked
		self.assertEqual(park.wake_due_waits(now=NOW, limit=4), names[4:])
