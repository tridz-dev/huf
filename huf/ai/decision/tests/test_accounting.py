"""Frappe integration tests for huf.ai.decision.accounting (PLAN.md §4.7 step 8, D15).

Covers T2A.17 acceptance: the spend-cap pre-check against an origin's Agent Run RunBudget
(allowing when there is room, refusing when the cap would be exceeded, and always allowing an
origin with no ``agent_run``); atomic recording of decision totals on Agent Run / Flow Run /
Automation and Agent Run ``budget_spend_usd``; the Automation ``last_decision_call`` write; and
that concurrent (Shadow-job-style) increments never lose an update.
"""

from __future__ import annotations

import threading
import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import accounting
from huf.ai.decision.types import DecisionOrigin, DecisionUsage
from huf.ai.tests.factories import make_agent_run, make_automation


class TestPrecheckSpend(FrappeTestCase):
	def setUp(self):
		self._prev_spend_cap = frappe.db.get_single_value("Agent Settings", "spend_cap_usd")
		self.run = make_agent_run()

	def tearDown(self):
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", self._prev_spend_cap)
		frappe.delete_doc("Agent Run", self.run.name, ignore_permissions=True, force=True)

	def _origin(self, **overrides) -> DecisionOrigin:
		values = {"origin_type": "Agent Routing"}
		values.update(overrides)
		return DecisionOrigin(**values)

	def test_no_agent_run_always_allowed(self):
		# 0 means unlimited (RunBudget.check_spend), but this asserts the stronger claim:
		# an origin with no agent_run never even looks at a cap, however tight.
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", 0.0000001)
		self.assertTrue(accounting.precheck_spend(self._origin()))
		self.assertTrue(accounting.precheck_spend(self._origin(flow_run="some-flow-run")))
		self.assertTrue(accounting.precheck_spend(self._origin(automation="some-automation")))

	def test_within_cap_allowed(self):
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", 100.0)
		frappe.db.set_value("Agent Run", self.run.name, "budget_spend_usd", 0.0)

		self.assertTrue(accounting.precheck_spend(self._origin(agent_run=self.run.name)))

	def test_cap_would_be_exceeded_refused(self):
		# spend_cap_usd smaller than DEFAULT_CALL_COST_ESTIMATE_USD -- the pre-check estimate
		# alone tips the run over its cap, with nothing spent yet.
		frappe.db.set_single_value(
			"Agent Settings", "spend_cap_usd", accounting.DEFAULT_CALL_COST_ESTIMATE_USD / 2
		)
		frappe.db.set_value("Agent Run", self.run.name, "budget_spend_usd", 0.0)

		self.assertFalse(accounting.precheck_spend(self._origin(agent_run=self.run.name)))

	def test_already_spent_close_to_cap_refused(self):
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", 1.0)
		frappe.db.set_value("Agent Run", self.run.name, "budget_spend_usd", 0.995)

		self.assertFalse(accounting.precheck_spend(self._origin(agent_run=self.run.name)))

	def test_unlimited_cap_zero_always_allowed(self):
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", 0)
		frappe.db.set_value("Agent Run", self.run.name, "budget_spend_usd", 10_000.0)

		self.assertTrue(accounting.precheck_spend(self._origin(agent_run=self.run.name)))

	def test_zero_delta_estimate_does_not_write_anything(self):
		# precheck_spend must be read-only -- it must never itself move budget_spend_usd.
		frappe.db.set_single_value("Agent Settings", "spend_cap_usd", 100.0)
		frappe.db.set_value("Agent Run", self.run.name, "budget_spend_usd", 1.0)

		accounting.precheck_spend(self._origin(agent_run=self.run.name))

		self.assertEqual(frappe.db.get_value("Agent Run", self.run.name, "budget_spend_usd"), 1.0)


class TestRecordCall(FrappeTestCase):
	def setUp(self):
		self.run = make_agent_run()
		self.automation = make_automation()

		# A real Flow Definition must satisfy the graph-IR schema (flow_definition.py
		# validate()); this test only needs a Flow Run row with a flow_definition Link
		# field, not a runnable flow, so skip Link-target validation instead of
		# constructing a full graph-IR document.
		self.flow_run = frappe.get_doc({
			"doctype": "Flow Run",
			"flow_definition": f"test-flow-{uuid.uuid4().hex[:8]}",
		}).insert(ignore_permissions=True, ignore_links=True)

	def tearDown(self):
		frappe.delete_doc("Flow Run", self.flow_run.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Automation", self.automation.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Agent Run", self.run.name, ignore_permissions=True, force=True)

	def _origin(self, **overrides) -> DecisionOrigin:
		values = {"origin_type": "Agent Routing"}
		values.update(overrides)
		return DecisionOrigin(**values)

	def test_agent_run_totals_and_budget_spend_incremented(self):
		origin = self._origin(agent_run=self.run.name)
		usage = DecisionUsage(input_tokens=120, output_tokens=40, measured_cost=0.02)

		accounting.record_call(origin=origin, usage=usage, cost=0.02)

		row = frappe.db.get_value(
			"Agent Run",
			self.run.name,
			["decision_call_count", "decision_input_tokens", "decision_output_tokens", "decision_cost", "budget_spend_usd"],
			as_dict=True,
		)
		self.assertEqual(row.decision_call_count, 1)
		self.assertEqual(row.decision_input_tokens, 120)
		self.assertEqual(row.decision_output_tokens, 40)
		self.assertAlmostEqual(row.decision_cost, 0.02)
		self.assertAlmostEqual(row.budget_spend_usd, 0.02)

	def test_agent_run_totals_accumulate_across_calls(self):
		origin = self._origin(agent_run=self.run.name)

		accounting.record_call(
			origin=origin, usage=DecisionUsage(input_tokens=100, output_tokens=10, measured_cost=0.01), cost=0.01
		)
		accounting.record_call(
			origin=origin, usage=DecisionUsage(input_tokens=50, output_tokens=5, measured_cost=0.005), cost=0.005
		)

		row = frappe.db.get_value(
			"Agent Run",
			self.run.name,
			["decision_call_count", "decision_input_tokens", "decision_output_tokens", "decision_cost", "budget_spend_usd"],
			as_dict=True,
		)
		self.assertEqual(row.decision_call_count, 2)
		self.assertEqual(row.decision_input_tokens, 150)
		self.assertEqual(row.decision_output_tokens, 15)
		self.assertAlmostEqual(row.decision_cost, 0.015)
		self.assertAlmostEqual(row.budget_spend_usd, 0.015)

	def test_call_with_no_usage_still_increments_call_count_only(self):
		# A call that never reached a provider (e.g. TIMEOUT / THROUGHPUT_BUDGET_EXHAUSTED
		# before this point) has a default, all-None DecisionUsage -- cost 0. The call still
		# happened and must still be counted.
		origin = self._origin(agent_run=self.run.name)

		accounting.record_call(origin=origin, usage=DecisionUsage(), cost=0.0)

		row = frappe.db.get_value(
			"Agent Run",
			self.run.name,
			["decision_call_count", "decision_input_tokens", "decision_output_tokens", "decision_cost", "budget_spend_usd"],
			as_dict=True,
		)
		self.assertEqual(row.decision_call_count, 1)
		self.assertEqual(row.decision_input_tokens, 0)
		self.assertEqual(row.decision_output_tokens, 0)
		self.assertEqual(row.decision_cost, 0)
		self.assertEqual(row.budget_spend_usd, 0)

	def test_flow_run_totals_incremented_no_budget_field(self):
		origin = self._origin(flow_run=self.flow_run.name)
		usage = DecisionUsage(input_tokens=80, output_tokens=20, measured_cost=0.015)

		accounting.record_call(origin=origin, usage=usage, cost=0.015)

		row = frappe.db.get_value(
			"Flow Run",
			self.flow_run.name,
			["decision_call_count", "decision_input_tokens", "decision_output_tokens", "decision_cost"],
			as_dict=True,
		)
		self.assertEqual(row.decision_call_count, 1)
		self.assertEqual(row.decision_input_tokens, 80)
		self.assertEqual(row.decision_output_tokens, 20)
		self.assertAlmostEqual(row.decision_cost, 0.015)

	def test_automation_totals_incremented_and_last_decision_call_set(self):
		origin = self._origin(automation=self.automation.name)
		usage = DecisionUsage(input_tokens=60, output_tokens=15, measured_cost=0.008)

		accounting.record_call(origin=origin, usage=usage, cost=0.008, decision_call="DC-TEST-0001")

		row = frappe.db.get_value(
			"Automation",
			self.automation.name,
			["total_decision_calls", "total_decision_cost", "last_decision_call"],
			as_dict=True,
		)
		self.assertEqual(row.total_decision_calls, 1)
		self.assertAlmostEqual(row.total_decision_cost, 0.008)
		self.assertEqual(row.last_decision_call, "DC-TEST-0001")

	def test_automation_last_decision_call_set_twice_is_idempotent(self):
		"""Setting the same last_decision_call value twice (this module and T6.02's own
		automation_runner bookkeeping both write it) must not raise or corrupt state."""
		origin = self._origin(automation=self.automation.name)

		accounting.record_call(origin=origin, usage=DecisionUsage(), cost=0.0, decision_call="DC-TEST-0002")
		accounting.record_call(origin=origin, usage=DecisionUsage(), cost=0.0, decision_call="DC-TEST-0002")

		self.assertEqual(
			frappe.db.get_value("Automation", self.automation.name, "last_decision_call"), "DC-TEST-0002"
		)
		self.assertEqual(
			frappe.db.get_value("Automation", self.automation.name, "total_decision_calls"), 2
		)

	def test_automation_without_decision_call_leaves_last_decision_call_untouched(self):
		origin = self._origin(automation=self.automation.name)

		accounting.record_call(origin=origin, usage=DecisionUsage(), cost=0.0, decision_call=None)

		self.assertFalse(frappe.db.get_value("Automation", self.automation.name, "last_decision_call"))
		self.assertEqual(
			frappe.db.get_value("Automation", self.automation.name, "total_decision_calls"), 1
		)

	def test_multiple_origins_on_one_call_each_increment_independently(self):
		# An Agent Run inside a Flow (or an Automation-driven Agent Run) can carry more than
		# one origin field at once; each destination gets its own independent increment.
		origin = self._origin(agent_run=self.run.name, flow_run=self.flow_run.name, automation=self.automation.name)
		usage = DecisionUsage(input_tokens=10, output_tokens=5, measured_cost=0.001)

		accounting.record_call(origin=origin, usage=usage, cost=0.001)

		self.assertEqual(frappe.db.get_value("Agent Run", self.run.name, "decision_call_count"), 1)
		self.assertEqual(frappe.db.get_value("Flow Run", self.flow_run.name, "decision_call_count"), 1)
		self.assertEqual(frappe.db.get_value("Automation", self.automation.name, "total_decision_calls"), 1)

	def test_playground_origin_touches_nothing(self):
		# No agent_run / flow_run / automation on the origin -- record_call must be a no-op
		# beyond the Decision Call row the runtime already persisted (not this module's job).
		origin = self._origin(origin_type="Playground")

		# Must not raise for an origin with nothing to increment.
		accounting.record_call(origin=origin, usage=DecisionUsage(input_tokens=5, output_tokens=5), cost=0.001)


class TestRecordCallConcurrency(FrappeTestCase):
	"""Concurrent Shadow-job-style increments (T2A.17 acceptance): two or more decision calls
	completing for the same Agent Run at once must not lose an update to each other. Each
	worker thread opens its own Frappe site connection (the same pattern
	huf.ai.agent_integration._run_coro_sync uses for background work), matching how real
	Shadow jobs run -- each in its own ``frappe.enqueue`` worker process, not sharing the
	calling request's DB connection or Python contextvars.
	"""

	def setUp(self):
		self.site = frappe.local.site
		self.run = make_agent_run()
		frappe.db.commit()  # make the run visible to the other connections this test opens

	def tearDown(self):
		frappe.delete_doc("Agent Run", self.run.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_concurrent_record_call_increments_all_land(self):
		n_workers = 12
		cost_per_call = 0.001
		origin_kwargs = {"origin_type": "Agent Routing", "agent_run": self.run.name}
		errors: list[BaseException] = []

		def _worker():
			frappe.init(self.site)
			frappe.connect()
			try:
				accounting.record_call(
					origin=DecisionOrigin(**origin_kwargs),
					usage=DecisionUsage(input_tokens=10, output_tokens=2, measured_cost=cost_per_call),
					cost=cost_per_call,
				)
				frappe.db.commit()
			except BaseException as exc:  # noqa: BLE001 -- surfaced via assertion below
				errors.append(exc)
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=_worker) for _ in range(n_workers)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=30)

		self.assertEqual(errors, [])

		# Refresh this connection's view -- the other threads committed on their own
		# connections after this test's own setUp commit.
		frappe.db.commit()
		row = frappe.db.get_value(
			"Agent Run",
			self.run.name,
			["decision_call_count", "decision_input_tokens", "decision_output_tokens", "decision_cost", "budget_spend_usd"],
			as_dict=True,
		)
		self.assertEqual(row.decision_call_count, n_workers)
		self.assertEqual(row.decision_input_tokens, 10 * n_workers)
		self.assertEqual(row.decision_output_tokens, 2 * n_workers)
		self.assertAlmostEqual(row.decision_cost, cost_per_call * n_workers, places=6)
		self.assertAlmostEqual(row.budget_spend_usd, cost_per_call * n_workers, places=6)

	def test_repeated_calls_simulating_interleaving_accumulate_exactly(self):
		"""Sequential repeated calls (the same shape a rapid burst of Shadow jobs would
		produce if they happened to interleave one at a time) must accumulate exactly --
		this pins down the SQL increment arithmetic itself, independent of real thread
		scheduling."""
		n_calls = 50
		origin = DecisionOrigin(origin_type="Agent Routing", agent_run=self.run.name)

		for _ in range(n_calls):
			accounting.record_call(
				origin=origin, usage=DecisionUsage(input_tokens=1, output_tokens=1, measured_cost=0.0001), cost=0.0001
			)

		row = frappe.db.get_value(
			"Agent Run", self.run.name, ["decision_call_count", "decision_cost"], as_dict=True
		)
		self.assertEqual(row.decision_call_count, n_calls)
		self.assertAlmostEqual(row.decision_cost, 0.0001 * n_calls, places=6)
