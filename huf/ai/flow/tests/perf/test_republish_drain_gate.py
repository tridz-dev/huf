"""H-W2-18 load gate: parked runs drain after a republish with no wrong-version execution.

DEFERRED to the pre-PR gate; runs only with ``HUF_W2_18_DRAIN_GATE=1`` on a disposable site with the scheduler off:

    HUF_W2_18_DRAIN_GATE=1 bench --site <site> run-tests --app huf \
        --module huf.ai.flow.tests.perf.test_republish_drain_gate

One run is parked by the engine and its row is copied up to ``PARKED``. The flow is then republished so that a new
run would take another branch, and the wake sweeper drains the copies with its jobs run inline in this one process.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine
from huf.ai.flow.runs import park
from huf.ai.flow.runs.member import member_name
from huf.ai.flow.runs.start import start_flow_for_member
from huf.ai.flow.tests.perf import seed
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

GATE_ENV = "HUF_W2_18_DRAIN_GATE"
PARKED = 100_000
MAX_SECONDS = 600
BATCH = 5_000
FLOW = f"{seed.PREFIX}drain-flow"
INLINE_JOBS = {"huf.ai.flow.runs.park.wake_chunk", "huf.ai.flow.engine.run_flow"}


def graph(threshold: int) -> dict:
	"""Wait, then branch: the ``n=2`` payload ends at ``end`` for threshold 1 and at ``end2`` for threshold 2."""
	return _graph(
		[
			_trigger("pause"),
			{
				"id": "pause",
				"type": "wait",
				"next": "cond",
				"config": {"mode": "duration", "duration": {"value": 1, "unit": "days"}},
			},
			{
				"id": "cond",
				"type": "condition",
				"config": {"expression": f"input['n'] > {threshold}", "on_true": "end", "on_false": "end2"},
			},
			_end(),
			_end("end2"),
		]
	)


def publish(definition: dict) -> None:
	frappe.db.set_value(
		"Flow Definition", FLOW, {"definition_json": json.dumps(definition), "status": "Active"}
	)
	frappe.db.commit()


def make_flow() -> None:
	doc = frappe.get_doc(
		{
			"doctype": "Flow Definition",
			"flow_id": FLOW,
			"flow_name": "Drain gate flow",
			"status": "Draft",
			"definition_json": "{}",
		}
	)
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	publish(graph(1))


def cleanup() -> None:
	frappe.db.rollback()
	frappe.db.delete("Flow Member State", {"flow": FLOW})
	frappe.db.delete("Agent Flow Run", {"flow_id": FLOW})
	frappe.db.delete("Flow Definition", {"name": FLOW})
	frappe.db.commit()


def park_one(key: str) -> str:
	name = start_flow_for_member(FLOW, key, {"n": 2}, enqueue=False)
	frappe.db.commit()
	status = frappe.db.get_value("Agent Flow Run", name, "status")
	if status != park.WAIT_STATUS:
		frappe.throw(f"run did not park: {status}")
	return name


def route_of(context_json: str | None) -> tuple:
	"""The branch ends that produced an output."""
	outputs = json.loads(context_json or "{}").get("__node_outputs__") or {}
	return tuple(sorted(set(outputs) & {"end", "end2"}))


def finish_one(key: str) -> tuple:
	name = park_one(key)
	park.wake_run(name, "elapsed", enqueue=False)
	frappe.db.commit()
	status, context = frappe.db.get_value("Agent Flow Run", name, ["status", "context_json"])
	if status != "Success":
		frappe.throw(f"control run did not finish: {status}")
	frappe.db.delete("Agent Flow Run", {"name": name})
	frappe.db.commit()
	return route_of(context)


def clone_parked(template: str, total: int) -> None:
	"""Copy the parked ``template`` run (and its member state) until ``total`` runs are due."""
	run = frappe.db.get_value("Agent Flow Run", template, "*", as_dict=True)
	member = frappe.db.get_value("Flow Member State", member_name(FLOW, run.member_key), "*", as_dict=True)
	due = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(minutes=1)
	frappe.db.set_value("Agent Flow Run", template, "resume_at", due, update_modified=False)
	for start in range(1, total, BATCH):
		runs, members = [], []
		for i in range(start, min(start + BATCH, total)):
			name, key = f"{seed.PREFIX}drain-{i:08d}", f"{seed.PREFIX}drain-m-{i:08d}"
			runs.append({**run, "name": name, "member_key": key, "resume_at": due})
			if member:
				members.append(
					{**member, "name": member_name(FLOW, key), "member_key": key, "active_flow_run": name}
				)
		seed._bulk_insert("Agent Flow Run", runs)
		seed._bulk_insert("Flow Member State", members)
		frappe.db.commit()


def drain() -> dict:
	"""Tick the sweeper and run its jobs until nothing waits. A tick that takes nothing is a stall."""
	jobs: deque = deque()
	pinned_seen: dict = {}
	real_pinned = engine._pinned_version

	def enqueue(method, **kwargs):
		if method in INLINE_JOBS:
			jobs.append((method, kwargs))

	def pinned(run):
		version = real_pinned(run)
		pinned_seen[run.name] = version.fingerprint
		return version

	def waiting() -> int:
		return frappe.db.count("Agent Flow Run", {"flow_id": FLOW, "status": park.WAIT_STATUS})

	stalled = False
	with patch("frappe.enqueue", side_effect=enqueue), patch.object(engine, "_pinned_version", pinned):
		started = time.perf_counter()
		while waiting():
			taken = park.wake_due_waits()
			while jobs:
				method, kwargs = jobs.popleft()
				if method.endswith("wake_chunk"):
					park.wake_chunk(kwargs["names"], kwargs["due_by"])
				else:
					engine.run_flow(kwargs["flow_run_name"])
				frappe.db.commit()
			# stop at the time budget too, so a slow drain fails instead of running for hours
			if not taken or time.perf_counter() - started > MAX_SECONDS:
				stalled = not taken
				break
		elapsed = time.perf_counter() - started
	return {"seconds": elapsed, "stalled": stalled, "pinned_seen": pinned_seen}


def wrong_versions(fingerprint: str, route: tuple, pinned_seen: dict) -> int:
	"""Runs that loaded another version, lost their pin or left by another branch."""
	wrong = {name for name, seen in pinned_seen.items() if seen != fingerprint}
	after = ""
	while True:
		rows = frappe.get_all(
			"Agent Flow Run",
			filters={"flow_id": FLOW, "name": [">", after]},
			fields=["name", "pinned_fingerprint", "context_json"],
			order_by="name asc",
			limit_page_length=BATCH,
		)
		if not rows:
			return len(wrong)
		wrong.update(
			r.name for r in rows if r.pinned_fingerprint != fingerprint or route_of(r.context_json) != route
		)
		after = rows[-1].name


@unittest.skipUnless(os.environ.get(GATE_ENV) == "1", f"DEFERRED to the pre-PR gate: set {GATE_ENV}=1")
class TestRepublishDrainGate(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.conf.get("allow_tests"):
			frappe.throw("The drain gate only runs on a site with allow_tests enabled.")
		cleanup()
		self.addCleanup(cleanup)
		check = patch("huf.ai.graph.validation.flow_validation.check_runnable")
		check.start()
		self.addCleanup(check.stop)
		make_flow()

	def test_parked_runs_drain_on_their_pinned_version(self):
		old_route = finish_one("drain-control-v1")
		template = park_one("drain-template")
		fingerprint = frappe.db.get_value("Agent Flow Run", template, "pinned_fingerprint")
		clone_parked(template, PARKED)
		publish(graph(2))
		new_route = finish_one("drain-control-v2")
		self.assertEqual((old_route, new_route), (("end",), ("end2",)))

		result = drain()
		finished = frappe.db.count("Agent Flow Run", {"flow_id": FLOW, "status": "Success"})
		wrong = wrong_versions(fingerprint, old_route, result["pinned_seen"])
		print(f"W2_18_GATE parked {PARKED} finished {finished} wrong_version {wrong}")
		print(f"W2_18_GATE drain_seconds {result['seconds']:.1f} stalled {result['stalled']}")
		self.assertFalse(result["stalled"])
		self.assertEqual(finished, PARKED)
		self.assertEqual(wrong, 0)
		self.assertLess(result["seconds"], MAX_SECONDS)
