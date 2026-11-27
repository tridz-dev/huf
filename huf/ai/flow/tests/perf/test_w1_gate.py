"""Wave W1 load gate (H-W1-08). See ``docs/testing/W1_LOAD_GATE.md``.

``TestW1GateSmoke`` runs every measurement on at most 20 rows and checks behaviour only. ``TestW1LoadGate`` holds the
plan targets; it is DEFERRED to the pre-PR gate and runs only with ``HUF_W1_LOAD_GATE=1`` on a disposable site.
"""

from __future__ import annotations

import os
import threading
import time
import unittest
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service
from huf.ai.flow import engine, state
from huf.ai.flow.runs import member, park
from huf.ai.flow.tests.perf import seed

GATE_ENV = "HUF_W1_LOAD_GATE"
DEFERRED = f"DEFERRED to the pre-PR gate: set {GATE_ENV}=1 on a disposable site to run the load"
INDEX = "idx_agent_flow_run_status_resume_at"
ENTRY_FLOW = f"{seed.PREFIX}entry"
STATE_FLOW = f"{seed.PREFIX}state"
WIDTH_SAMPLE = 1000


@dataclass(frozen=True)
class Scale:
	runs: int
	due: int
	members: int  # a tenth of them are past retention (see seed.seed_all)
	events: int
	expired_state: int
	workers: int
	entry_rounds: int
	query_samples: int
	locks: int


SMOKE = Scale(runs=4, due=2, members=10, events=2, expired_state=1, workers=2, entry_rounds=1, query_samples=1, locks=2)
GATE = Scale(
	runs=1_000_000,
	due=100_000,
	members=1_000_000,
	events=10_000,
	expired_state=100_000,
	workers=50,
	entry_rounds=20,
	query_samples=100,
	locks=1000,
)

# metric -> (comparison, limit); "max" means value < limit, "zero" means value == 0
TARGETS = {
	"sweep_query_p95_ms": ("max", 20),
	"drain_seconds_per_100k": ("max", 600),
	"double_wakes": ("zero", 0),
	"undrained_runs": ("zero", 0),
	"duplicate_entries": ("zero", 0),
	"entry_p95_ms": ("max", 30),
	"replay_duplicate_effects": ("zero", 0),
	"replay_ms_per_event": ("max", 5),
	"stuck_locks": ("zero", 0),
	"member_retention_seconds_per_100k": ("max", 60),
	"state_retention_seconds_per_100k": ("max", 60),
	"parked_row_avg_bytes": ("max", 4096),
}


def p95(samples: list[float]) -> float:
	return sorted(samples)[max(0, -(-len(samples) * 95 // 100) - 1)]


def utc_now() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_expired_state(total: int) -> None:
	past = frappe.utils.now_datetime() - timedelta(days=1)
	rows = [(f"{STATE_FLOW}-{i:08d}", STATE_FLOW, f"key-{i}", "1", past) for i in range(total)]
	frappe.db.bulk_insert("Flow State", ["name", "flow_id", "state_key", "value_json", "expires_at"], rows)
	frappe.db.commit()


def cleanup() -> None:
	frappe.db.rollback()
	frappe.db.delete("Flow State", {"flow_id": STATE_FLOW})
	seed.cleanup()  # commits


def measure_sweep_query(scale: Scale, now: datetime) -> dict:
	captured = []
	real_get_all = frappe.get_all

	def capture(doctype, *args, **kwargs):
		if doctype != "Agent Flow Run":
			return real_get_all(doctype, *args, **kwargs)
		captured.append(real_get_all(doctype, *args, **kwargs, run=False))
		return []

	with patch.object(park.frappe, "get_all", side_effect=capture):
		park._due_page(now, None, park.WAKE_PAGE_SIZE_DEFAULT)
	plan = frappe.db.sql(f"EXPLAIN {captured[0]}", as_dict=True)

	samples = []
	for _i in range(scale.query_samples):
		started = time.perf_counter()
		park._due_page(now, None, park.WAKE_PAGE_SIZE_DEFAULT)
		samples.append((time.perf_counter() - started) * 1000)
	return {"sweep_query_p95_ms": p95(samples), "sweep_query_keys": [row.get("key") for row in plan]}


def measure_drain(scale: Scale, now: datetime) -> dict:
	"""Sweeper ticks until nothing is due. Chunk jobs run in this process; continuations are only counted."""
	chunks, continued = [], Counter()

	def enqueue(method, **kwargs):
		if method == "huf.ai.flow.runs.park.wake_chunk":
			chunks.append((kwargs["names"], kwargs["due_by"]))
		elif method == "huf.ai.flow.engine.run_flow":
			continued[kwargs["flow_run_name"]] += 1

	started = time.perf_counter()
	with patch("frappe.enqueue", side_effect=enqueue):
		while park.wake_due_waits(now=now):
			frappe.db.commit()
			while chunks:
				park.wake_chunk(*chunks.pop(0))
				frappe.db.commit()
	elapsed = time.perf_counter() - started
	seeded = {name: n for name, n in continued.items() if name.startswith(seed.PREFIX)}
	return {
		"drain_seconds_per_100k": elapsed * 100_000 / scale.due,
		"drain_rows_per_minute": len(seeded) * 60 / elapsed,
		"double_wakes": sum(n - 1 for n in seeded.values()),
		"undrained_runs": scale.due - len(seeded),
	}


def measure_entry(scale: Scale) -> dict:
	"""``workers`` parallel entries: each round one shared member (one winner) and one new member per worker."""
	site, sites_path = frappe.local.site, frappe.local.sites_path
	barrier = threading.Barrier(scale.workers)
	samples, winners, errors = [], Counter(), []

	def worker(index: int):
		try:
			frappe.init(site, sites_path=sites_path)
			frappe.connect()
			frappe.set_user("Administrator")
			for round_no in range(scale.entry_rounds):
				barrier.wait(timeout=120)
				if member.claim_entry(ENTRY_FLOW, f"shared-{round_no}"):
					winners[round_no] += 1  # only a duplicate entry makes a second write to a round
				frappe.db.commit()
				key = f"own-{round_no}-{index}"
				started = time.perf_counter()
				member.claim_entry(ENTRY_FLOW, key)
				member.upsert_member(ENTRY_FLOW, key)
				frappe.db.commit()
				samples.append((time.perf_counter() - started) * 1000)
		except Exception as exc:  # noqa: BLE001 - raised below
			errors.append(repr(exc))
			barrier.abort()
		finally:
			frappe.destroy()

	frappe.db.commit()
	threads = [threading.Thread(target=worker, args=(i,)) for i in range(scale.workers)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()
	frappe.db.rollback()  # a fresh snapshot that sees the threads' commits
	if errors:
		raise AssertionError(f"member entry workers failed: {errors[:3]}")
	rows = frappe.db.count("Flow Member State", {"flow": ENTRY_FLOW})
	expected_rows = scale.entry_rounds * (scale.workers + 1)
	extra_winners = sum(abs(winners[r] - 1) for r in range(scale.entry_rounds))
	return {"duplicate_entries": extra_winners + abs(rows - expected_rows), "entry_p95_ms": p95(samples)}


def measure_replay(scale: Scale) -> dict:
	"""Replay every stored event id: no new event, run or job."""

	def counts():
		return tuple(frappe.db.count(dt) for dt in ("Gateway Event", "Agent Run", "Agent Flow Run"))

	before, new = counts(), 0
	with patch("frappe.enqueue") as enqueue:
		started = time.perf_counter()
		for i in range(scale.events):
			result = gateway_service.ingest_gateway_event(
				seed.GATEWAY, seed.provider_event_id(i), {}, verified_sender=True
			)
			new += not result.get("duplicate")
		elapsed = time.perf_counter() - started
	rows_added = sum(a - b for a, b in zip(counts(), before))
	return {
		"replay_duplicate_effects": new + rows_added + enqueue.call_count,
		"replay_ms_per_event": elapsed * 1000 / scale.events,
	}


def measure_locks(scale: Scale) -> dict:
	"""Locks whose holder stopped beating (as after a kill) must carry a TTL. The real kill is a manual step."""
	cache = frappe.cache()
	names = [f"{seed.PREFIX}lock-{i}" for i in range(scale.locks)]
	stuck = 0
	try:
		for name in names:
			if not engine._acquire_run_lock(name):
				raise AssertionError(f"run lock already held: {name}")
			key = engine._run_lock_key(name)
			engine._stop_run_lock_heartbeat(key)
			stuck += not 0 < cache.ttl(key) <= engine.RUN_LOCK_TTL_SECONDS
	finally:
		for name in names:
			engine._release_run_lock(name)
	return {"stuck_locks": stuck}


def measure_row_width() -> dict:
	rows = frappe.db.sql(
		"select * from `tabAgent Flow Run` where name like %s and status = %s limit %s",
		(f"{seed.PREFIX}%", park.WAIT_STATUS, WIDTH_SAMPLE),
		as_dict=True,
	)
	widths = [sum(len(str(v).encode()) for v in row.values() if v is not None) for row in rows]
	return {"parked_row_avg_bytes": sum(widths) / len(widths)}


def measure_retention(scale: Scale) -> dict:
	results = {}
	for metric, purge, expired in (
		# the seed's expired members are 400 days old
		("member", lambda: member.purge_inactive(399), scale.members // 10),
		("state", state.purge_expired, scale.expired_state),
	):
		started = time.perf_counter()
		removed = purge()
		elapsed = time.perf_counter() - started
		frappe.db.commit()
		results[f"{metric}_retention_removed"] = removed
		results[f"{metric}_retention_seconds_per_100k"] = elapsed * 100_000 / expired
	return results


def run_gate(scale: Scale) -> dict:
	"""Seed, measure in an order where no step eats another's rows, return every metric."""
	cleanup()
	seed.seed_all(runs=scale.runs, due=scale.due, members=scale.members, events=scale.events)
	seed_expired_state(scale.expired_state)
	now = utc_now()
	return {
		**measure_sweep_query(scale, now),
		**measure_row_width(),
		**measure_replay(scale),
		**measure_locks(scale),
		**measure_entry(scale),
		**measure_retention(scale),
		**measure_drain(scale, now),  # last: it moves the due runs out of the waiting state
	}


def failed_targets(results: dict) -> list[str]:
	failed = []
	for metric, (kind, limit) in TARGETS.items():
		value = results[metric]
		if not (value == 0 if kind == "zero" else value < limit):
			failed.append(f"{metric}={value}")
	if results["sweep_query_keys"] != [INDEX]:
		failed.append(f"sweep_query_keys={results['sweep_query_keys']}")
	return failed


class TestW1GateSmoke(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(cleanup)

	def test_every_measurement_runs_on_a_tiny_seed(self):
		results = run_gate(SMOKE)
		for metric, (kind, _limit) in TARGETS.items():
			self.assertIn(metric, results)
			if kind == "zero":
				self.assertEqual(results[metric], 0, metric)
		self.assertGreaterEqual(results["member_retention_removed"], 1)
		self.assertGreaterEqual(results["state_retention_removed"], 1)


@unittest.skipUnless(os.environ.get(GATE_ENV) == "1", DEFERRED)
class TestW1LoadGate(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(cleanup)

	def test_plan_targets(self):
		results = run_gate(GATE)
		for metric, value in results.items():
			print(f"W1_GATE {metric} {value}")
		self.assertEqual(failed_targets(results), [])
