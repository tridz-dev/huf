"""H-W7-12 perf gate: ``count_app_runs`` over 100k runs answers in under a second.

DEFERRED to the pre-PR gate; runs only with ``HUF_W7_12_COUNT_GATE=1`` on a disposable clone site:

    HUF_W7_12_COUNT_GATE=1 bench --site <site> run-tests --app huf \
        --module huf.ai.flow.tests.perf.test_count_app_runs_gate

Both query paths are timed: grouping in SQL, and the default grouping by ``reason``, which reads every context.
"""

from __future__ import annotations

import json
import os
import time
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.app_scope import runs_api
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.perf import seed
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

GATE_ENV = "HUF_W7_12_COUNT_GATE"
APP = "huf"
RUNS = 100_000
MAX_SECONDS = 1.0
BATCH = 5_000
FLOWS = [f"{seed.PREFIX}count-flow-{i}" for i in range(seed.FLOW_COUNT)]
STATUSES = ("Success", "Success", "Success", "Failed", "Cancelled", "Waiting User")
BLOCKED = json.dumps({"__node_outputs__": {"s1": {"status": "ok"}, "s2": {"reason_code": "freq_cap"}}})


def cleanup() -> None:
	frappe.db.rollback()
	frappe.db.delete("Agent Flow Run", {"flow_definition": ["in", FLOWS]})
	frappe.db.delete("Flow Definition", {"name": ["in", FLOWS]})
	frappe.db.commit()


def seed_app_runs(total: int = RUNS) -> None:
	for flow in FLOWS:
		create_app_flow(APP, flow, flow, _graph([_trigger("end"), _end()]))
	for start in range(0, total, BATCH):
		rows = []
		for i in range(start, min(start + BATCH, total)):
			status = STATUSES[i % len(STATUSES)]
			flow = FLOWS[i % len(FLOWS)]
			rows.append(
				{
					"name": f"{seed.PREFIX}count-{i:08d}",
					"flow_definition": flow,
					"flow_id": flow,
					"owner_app": APP,
					"status": status,
					"member_key": seed.member_key(i),
					"current_node_id": "end",
					"context_json": BLOCKED if status == "Failed" else "{}",
				}
			)
		seed._bulk_insert("Agent Flow Run", rows)
		frappe.db.commit()


@unittest.skipUnless(os.environ.get(GATE_ENV) == "1", f"DEFERRED to the pre-PR gate: set {GATE_ENV}=1")
class TestCountAppRunsGate(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.conf.get("allow_tests"):
			frappe.throw("The count gate only runs on a site with allow_tests enabled.")
		cleanup()
		self.addCleanup(cleanup)
		seed_app_runs()

	def test_counts_at_100k_runs(self):
		slow = []
		for group_by in ("status", "flow,status", "flow,status,reason"):
			started = time.perf_counter()
			counts = runs_api.count_app_runs(APP, group_by=group_by, flow_ids=FLOWS)
			elapsed = time.perf_counter() - started
			print(f"W7_12_GATE group_by={group_by} seconds {elapsed:.3f}")
			self.assertEqual(sum(c["count"] for c in counts), RUNS, group_by)
			if elapsed >= MAX_SECONDS:
				slow.append(f"{group_by}={elapsed:.3f}s")
		self.assertEqual(slow, [])
