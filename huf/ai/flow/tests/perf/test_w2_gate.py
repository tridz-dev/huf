"""Wave W2 load gate (H-W2-21). See ``docs/testing/W2_LOAD_GATE.md``.

``TestW2GateSmoke`` runs every measurement on at most 20 rows and checks behaviour only. ``TestW2LoadGate`` holds the
plan targets (100k members over 8 flows, a 20k wave due in one minute, 10% duplicate deliveries); it is DEFERRED to
the pre-PR gate and runs only with ``HUF_W2_LOAD_GATE=1`` on a disposable site. Sends go through a fake transport.
All data is synthetic.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import channel_consent, guard, guard_steps
from huf.ai.flow import engine
from huf.ai.flow.nodes import send
from huf.ai.flow.runs import bulk_entry, park
from huf.ai.flow.support import step_keys
from huf.ai.flow.testrun import gate
from huf.ai.flow.tests.perf import seed
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext

GATE_ENV = "HUF_W2_LOAD_GATE"
DEFERRED = f"DEFERRED to the pre-PR gate: set {GATE_ENV}=1 on a disposable site to run the load"
PREFIX = f"{seed.PREFIX}w2-"
GUARD_PREFIX = f"{PREFIX}guard-"
FLOW_COUNT = 8
CLOSED_EVERY = 10  # every 10th member's send window is closed when the wave is due
DUPLICATE_EVERY = 10  # every 10th delivery comes twice (re-delivered job / duplicate webhook)


@dataclass(frozen=True)
class Scale:
	members: int  # bulk entry, spread over FLOW_COUNT flows
	wave: int  # sends due in the same minute
	guard_sends: int  # guarded sends with the real built-in steps
	events: int  # stored gateway events replayed


SMOKE = Scale(members=16, wave=20, guard_sends=4, events=2)
GATE = Scale(members=100_000, wave=20_000, guard_sends=3_000, events=10_000)

# metric -> (comparison, limit); "max" means value < limit, "min" value >= limit, "zero" value == 0
TARGETS = {
	"duplicate_runs": ("zero", 0),
	"bulk_entry_seconds_per_100k": ("max", 300),
	"duplicate_sends": ("zero", 0),
	"sends_outside_window": ("zero", 0),
	"unsent_in_window": ("zero", 0),
	"pii_in_trace": ("zero", 0),
	"replay_duplicate_effects": ("zero", 0),
	"guard_sends_per_minute": ("min", 3000),
}


def flow_id(i: int) -> str:
	return f"{PREFIX}flow-{i}"


def phone(i: int) -> str:
	return f"+9198{i:08d}"


def cleanup() -> None:
	frappe.db.rollback()
	flows = [flow_id(i) for i in range(FLOW_COUNT)]
	frappe.db.delete("Flow Member State", {"flow": ["in", flows]})
	frappe.db.delete("Agent Flow Run", {"flow_id": ["in", flows]})
	frappe.db.delete("Flow Definition", {"name": ["in", flows]})
	frappe.db.delete(channel_consent.DOCTYPE, {"recipient": ["like", f"{GUARD_PREFIX}%"]})
	seed.cleanup()  # commits


def make_flows() -> list[str]:
	graph = json.dumps(finished_flow())
	for i in range(FLOW_COUNT):
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": flow_id(i),
				"flow_name": f"W2 gate flow {i}",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		frappe.db.set_value("Flow Definition", doc.name, {"definition_json": graph, "status": "Active"})
	frappe.db.commit()
	return [flow_id(i) for i in range(FLOW_COUNT)]


def measure_bulk_entry(scale: Scale, flows: list[str]) -> dict:
	"""Enter every member through ``enter_members``; chunk jobs run inline. A second submission must add nothing."""
	jobs = []

	def enqueue(method, **kwargs):
		if method == "huf.ai.flow.runs.bulk_entry.run_chunk":
			jobs.append(kwargs)

	def submit():
		for n, flow in enumerate(flows):
			keys = [f"{PREFIX}m-{i:08d}" for i in range(n, scale.members, len(flows))]
			bulk_entry.enter_members(flow, keys)
		while jobs:
			job = jobs.pop(0)
			bulk_entry.run_chunk(job["flow_id"], job["member_keys"], job["entry_key"], job["batch_id"])
			frappe.db.commit()

	with (
		patch("frappe.enqueue", side_effect=enqueue),
		patch("huf.ai.graph.validation.flow_validation.check_runnable"),
	):
		started = time.perf_counter()
		submit()
		elapsed = time.perf_counter() - started
		submit()  # resubmission: idempotent
	frappe.db.rollback()
	duplicates = frappe.db.sql(
		"""select count(*) from (select 1 from `tabAgent Flow Run` where flow_id in %s
		group by flow_id, member_key having count(*) > 1) d""",
		(tuple(flows),),
	)[0][0]
	runs = frappe.db.count("Agent Flow Run", {"flow_id": ["in", flows]})
	return {
		"bulk_entry_seconds_per_100k": elapsed * 100_000 / scale.members,
		"duplicate_runs": duplicates + abs(runs - scale.members),
	}


def measure_wave(scale: Scale) -> dict:
	"""``wave`` sends due at once through ``send.message`` and the guard chain, a fake transport behind it.

	Every ``CLOSED_EVERY``-th member is outside its send window (the guard defers it); every ``DUPLICATE_EVERY``-th
	delivery is repeated with the same run and step key. Counts transport calls per step key and scans every
	persisted context, result and log call for the members' phone numbers.
	"""
	sent, deferred, contexts = {}, set(), {}
	pii_hits = [0]
	raw_numbers = {}
	future = datetime.now(timezone.utc) + timedelta(hours=1)

	def transport(request):
		sent[request["step_key"]] = sent.get(request["step_key"], 0) + 1
		return None

	def closed(i: int) -> bool:
		return i % CLOSED_EVERY == 0

	def window(request, resolvers):
		return future if closed(int(request["member_key"].rsplit("-", 1)[1])) else None

	def scan(run_name, text):
		raw = raw_numbers[run_name]
		pii_hits[0] += raw in text or raw.lstrip("+") in text

	def persist(run, ctx, settings):
		scan(run.name, json.dumps(ctx.data, default=str))

	def defer(run, node, until, member_key=None):
		deferred.add(run.name)
		return {"status": "parked"}

	logger = MagicMock()
	with ExitStack() as stack:
		for target, attr, value in (
			(guard, "BUILTIN_STEPS", [("allow", lambda r: {"allow": True})]),
			(guard, "_hook_paths", MagicMock(return_value=[])),
			(guard_steps, "window_resolvers", MagicMock(return_value=["perf.window"])),
			(guard_steps, "window_deferral", window),
			(guard_steps, "resolve_caps", MagicMock(return_value=[])),
			(gate, "live_send_on", MagicMock(return_value=True)),
			(gate, "pin_is_current", MagicMock(return_value=True)),
			(send, "_enqueue", transport),
			(send, "channel_of", MagicMock(return_value="whatsapp")),
			(park, "defer_send", defer),
			(engine, "_context_of", lambda run, s: contexts.setdefault(run.name, GraphContext())),
			(engine, "_persist_context", persist),
			(engine, "_transition_run", MagicMock(return_value=True)),
			(frappe, "logger", MagicMock(return_value=logger)),
		):
			stack.enter_context(patch.object(target, attr, value))
		stack.enter_context(patch("huf.ai.flow.runs.member.set_status"))
		stack.enter_context(guard.batch())
		for i in range(scale.wave):
			run = SimpleNamespace(
				name=f"{PREFIX}run-{i:08d}",
				flow_id=flow_id(i % FLOW_COUNT),
				flow_version="1",
				member_key=f"{PREFIX}m-{i:08d}",
				run_mode="",
				status="Running",
				waiting=None,
			)
			raw_numbers[run.name] = phone(i)
			config = {"gateway": "gw", "recipient": phone(i), "template": "promo", "category": "marketing"}
			node = step_keys.with_key(
				{"id": "s1", "type": "send.message", "config": config}, f"{run.name}:s1:1"
			)
			for _delivery in range(2 if i % DUPLICATE_EVERY == 0 else 1):
				result = send.exec_send_message(run, node, dict(config), {})
				scan(run.name, json.dumps(result, default=str))
	for call in logger.mock_calls:
		text = repr(call)
		pii_hits[0] += any(raw.lstrip("+") in text for raw in raw_numbers.values())
	open_keys = {f"{PREFIX}run-{i:08d}:s1:1" for i in range(scale.wave) if not closed(i)}
	return {
		"duplicate_sends": sum(n - 1 for n in sent.values()),
		"sends_outside_window": len(set(sent) - open_keys),
		"unsent_in_window": len(open_keys - set(sent)),
		"deferred_runs": len(deferred),
		"pii_in_trace": pii_hits[0],
	}


def measure_guard(scale: Scale) -> dict:
	"""Guarded sends per minute with Huf's real built-in steps (consent read included) inside one batch."""
	addresses = [f"{GUARD_PREFIX}{i:08d}@example.com" for i in range(scale.guard_sends)]
	for address in addresses:
		channel_consent.record_opt_in("email", address, source="api")
	frappe.db.commit()
	allowed = 0
	with patch.object(guard, "_hook_paths", return_value=[]), guard.batch():
		started = time.perf_counter()
		for address in addresses:
			request = {
				"member_key": address,
				"channel": "email",
				"category": "marketing",
				"recipient": address,
				"template": None,
				"token_names": [],
			}
			allowed += guard.evaluate(request).allowed
		elapsed = time.perf_counter() - started
	return {
		"guard_sends_per_minute": len(addresses) * 60 / elapsed,
		"guard_blocked": len(addresses) - allowed,
	}


def measure_replay(scale: Scale) -> dict:
	"""Duplicate inbound webhooks: every stored id replayed adds no event, run or job."""
	from huf.ai import gateway_service

	seed.seed_gateway_events(scale.events)
	frappe.db.commit()

	def counts():
		return tuple(frappe.db.count(dt) for dt in ("Gateway Event", "Agent Run", "Agent Flow Run"))

	before, new = counts(), 0
	with patch("frappe.enqueue") as enqueue:
		for i in range(scale.events):
			result = gateway_service.ingest_gateway_event(
				seed.GATEWAY, seed.provider_event_id(i), {}, verified_sender=True
			)
			new += not result.get("duplicate")
	rows_added = sum(a - b for a, b in zip(counts(), before, strict=True))
	return {"replay_duplicate_effects": new + rows_added + enqueue.call_count}


def run_gate(scale: Scale) -> dict:
	cleanup()
	if not frappe.conf.get("allow_tests"):
		frappe.throw("The W2 gate only runs on a site with allow_tests enabled.")
	flows = make_flows()
	return {
		**measure_bulk_entry(scale, flows),
		**measure_wave(scale),
		**measure_guard(scale),
		**measure_replay(scale),
	}


def failed_targets(results: dict) -> list[str]:
	failed = []
	for metric, (kind, limit) in TARGETS.items():
		value = results[metric]
		ok = value == 0 if kind == "zero" else value < limit if kind == "max" else value >= limit
		if not ok:
			failed.append(f"{metric}={value}")
	return failed


class TestW2GateSmoke(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(cleanup)

	def test_every_measurement_runs_on_a_tiny_seed(self):
		results = run_gate(SMOKE)
		for metric, (kind, _limit) in TARGETS.items():
			self.assertIn(metric, results)
			if kind == "zero":
				self.assertEqual(results[metric], 0, metric)
		self.assertEqual(results["deferred_runs"], -(-SMOKE.wave // CLOSED_EVERY))
		self.assertEqual(results["guard_blocked"], 0)


@unittest.skipUnless(os.environ.get(GATE_ENV) == "1", DEFERRED)
class TestW2LoadGate(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(cleanup)

	def test_plan_targets(self):
		results = run_gate(GATE)
		for metric, value in results.items():
			print(f"W2_GATE {metric} {value}")
		self.assertEqual(failed_targets(results), [])
