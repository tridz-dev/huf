# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for huf.ai.graph.validation_harness (T-50).

Frappe-free by design -- ``validation_harness`` itself never imports frappe, but ``huf/__init__.py``
does an unconditional ``import frappe`` before conftest.py's stub has a chance to run (same issue
documented in ``test_graph_validator.py`` / ``test_graph_permissions.py``), so this module installs
its own narrow stub first.

Where these tests report benchmark numbers, they are produced by running each benchmark's own
``invariants.py`` as a standalone script (subprocess) against that module's own sample result, and by
feeding hand-built :class:`RunMetrics` into the harness -- both are SIMULATED per this track's
existing benchmark tests (T-23/T-30/T-40's tool layer is a fake, not a live bench). See the
``validation_harness`` module docstring.
"""

from __future__ import annotations

import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def _install_standalone_frappe_stub():
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return
	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: lambda f: f
	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils
	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph.validation_harness import (
	ALL_BENCHMARK_NAMES,
	MIN_REPRESENTATIVE_RUNS,
	NRunReport,
	PromotionThresholds,
	RunMetrics,
	RunRecord,
	ShadowBudget,
	ShadowConfig,
	WriteChecklist,
	aggregate_runs,
	compare_results,
	evaluate_promotion,
	find_benchmark_dir,
	load_benchmark,
	run_shadow,
	should_shadow,
)

# ---------------------------------------------------------------------------
# ShadowConfig / ShadowBudget
# ---------------------------------------------------------------------------


class TestShadowConfig(unittest.TestCase):
	def test_defaults_are_conservative(self):
		config = ShadowConfig()
		self.assertLessEqual(config.sample_rate, 0.1)
		self.assertLessEqual(config.max_shadow_runs_per_window, 50)

	def test_rejects_out_of_range_sample_rate(self):
		with self.assertRaises(ValueError):
			ShadowConfig(sample_rate=1.5)
		with self.assertRaises(ValueError):
			ShadowConfig(sample_rate=-0.1)

	def test_rejects_bad_budget(self):
		with self.assertRaises(ValueError):
			ShadowConfig(max_shadow_runs_per_window=-1)
		with self.assertRaises(ValueError):
			ShadowConfig(window_seconds=0)


class _FakeClock:
	def __init__(self):
		self.now = 0.0

	def __call__(self):
		return self.now


class TestShadowBudget(unittest.TestCase):
	def test_grants_up_to_the_cap_then_refuses(self):
		clock = _FakeClock()
		budget = ShadowBudget(ShadowConfig(max_shadow_runs_per_window=3, window_seconds=60), clock=clock)
		self.assertTrue(budget.try_consume())
		self.assertTrue(budget.try_consume())
		self.assertTrue(budget.try_consume())
		self.assertFalse(budget.try_consume())
		self.assertEqual(budget.remaining(), 0)

	def test_window_rolls_off_old_consumption(self):
		clock = _FakeClock()
		budget = ShadowBudget(ShadowConfig(max_shadow_runs_per_window=1, window_seconds=10), clock=clock)
		self.assertTrue(budget.try_consume())
		self.assertFalse(budget.try_consume())
		clock.now = 11.0
		self.assertTrue(budget.try_consume())


# ---------------------------------------------------------------------------
# should_shadow / run_shadow -- the structural write gate
# ---------------------------------------------------------------------------


class TestShouldShadowWriteGate(unittest.TestCase):
	"""Item 3 of the task brief: shadow mode must NEVER run a write procedure, enforced
	structurally, not by convention."""

	def _always_sample_config_and_budget(self):
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1000)
		return config, ShadowBudget(config)

	def test_contains_writes_true_never_shadows_even_at_full_sample_rate(self):
		config, budget = self._always_sample_config_and_budget()
		result = should_shadow(
			is_read_only=False, contains_writes=True, config=config, budget=budget, rng=lambda: 0.0
		)
		self.assertFalse(result)

	def test_is_read_only_false_never_shadows_even_if_contains_writes_unset(self):
		"""Both flags are checked -- a caller that only got is_read_only wrong (but left
		contains_writes at its default False) still gets refused."""
		config, budget = self._always_sample_config_and_budget()
		result = should_shadow(
			is_read_only=False, contains_writes=False, config=config, budget=budget, rng=lambda: 0.0
		)
		self.assertFalse(result)

	def test_disagreeing_flags_never_shadow(self):
		config, budget = self._always_sample_config_and_budget()
		result = should_shadow(
			is_read_only=True, contains_writes=True, config=config, budget=budget, rng=lambda: 0.0
		)
		self.assertFalse(result)

	def test_read_only_and_sampled_and_budgeted_shadows(self):
		config, budget = self._always_sample_config_and_budget()
		result = should_shadow(
			is_read_only=True, contains_writes=False, config=config, budget=budget, rng=lambda: 0.0
		)
		self.assertTrue(result)

	def test_sample_rate_zero_never_shadows_read_only(self):
		config = ShadowConfig(sample_rate=0.0)
		budget = ShadowBudget(config)
		result = should_shadow(
			is_read_only=True, contains_writes=False, config=config, budget=budget, rng=lambda: 0.0
		)
		self.assertFalse(result)

	def test_rng_above_sample_rate_skips(self):
		config = ShadowConfig(sample_rate=0.1)
		budget = ShadowBudget(config)
		result = should_shadow(
			is_read_only=True, contains_writes=False, config=config, budget=budget, rng=lambda: 0.5
		)
		self.assertFalse(result)

	def test_budget_exhaustion_refuses_even_when_sampled(self):
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1)
		budget = ShadowBudget(config)
		self.assertTrue(
			should_shadow(
				is_read_only=True, contains_writes=False, config=config, budget=budget, rng=lambda: 0.0
			)
		)
		self.assertFalse(
			should_shadow(
				is_read_only=True, contains_writes=False, config=config, budget=budget, rng=lambda: 0.0
			)
		)


class TestRunShadow(unittest.TestCase):
	def test_write_procedure_never_invokes_deterministic_runner(self):
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1000)
		budget = ShadowBudget(config)
		runner_called = []

		def runner():
			runner_called.append(True)
			return RunMetrics(output={"x": 1})

		result = run_shadow(
			is_read_only=False,
			contains_writes=True,
			config=config,
			budget=budget,
			agentic=RunMetrics(output={"x": 1}),
			deterministic_runner=runner,
			rng=lambda: 0.0,
		)
		self.assertFalse(result.sampled)
		self.assertEqual(runner_called, [])

	def test_matching_outputs_are_equivalent(self):
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1000)
		budget = ShadowBudget(config)
		result = run_shadow(
			is_read_only=True,
			contains_writes=False,
			config=config,
			budget=budget,
			agentic=RunMetrics(output={"total": 100.0}),
			deterministic_runner=lambda: RunMetrics(output={"total": 100.0000001}),
			rng=lambda: 0.0,
		)
		self.assertTrue(result.sampled)
		self.assertTrue(result.result_equivalent)

	def test_diverging_outputs_are_flagged_not_raised(self):
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1000)
		budget = ShadowBudget(config)
		result = run_shadow(
			is_read_only=True,
			contains_writes=False,
			config=config,
			budget=budget,
			agentic=RunMetrics(output={"total": 100.0}),
			deterministic_runner=lambda: RunMetrics(output={"total": 5.0}),
			rng=lambda: 0.0,
		)
		self.assertTrue(result.sampled)
		self.assertFalse(result.result_equivalent)
		self.assertIsNotNone(result.reason)

	def test_deterministic_runner_exception_is_captured_never_raised(self):
		"""Shadow execution must not change user-visible behaviour -- a broken deterministic
		side must not propagate."""
		config = ShadowConfig(sample_rate=1.0, max_shadow_runs_per_window=1000)
		budget = ShadowBudget(config)

		def boom():
			raise RuntimeError("deterministic side exploded")

		result = run_shadow(
			is_read_only=True,
			contains_writes=False,
			config=config,
			budget=budget,
			agentic=RunMetrics(output={"x": 1}),
			deterministic_runner=boom,
			rng=lambda: 0.0,
		)
		self.assertTrue(result.sampled)
		self.assertIn("exploded", result.shadow_error)
		self.assertIsNone(result.result_equivalent)


# ---------------------------------------------------------------------------
# compare_results / aggregate_runs (N-run comparison, I10)
# ---------------------------------------------------------------------------


class TestCompareResults(unittest.TestCase):
	def test_float_tolerance(self):
		equivalent, reason = compare_results({"total": 100.0}, {"total": 100.0000001})
		self.assertTrue(equivalent)
		self.assertIsNone(reason)

	def test_nested_structures(self):
		a = {"rows": [{"id": 1, "amount": 10.0}, {"id": 2, "amount": 20.0}]}
		b = {"rows": [{"id": 1, "amount": 10.0}, {"id": 2, "amount": 20.0}]}
		self.assertTrue(compare_results(a, b)[0])

	def test_real_divergence_reported(self):
		equivalent, reason = compare_results({"total": 100}, {"total": 90})
		self.assertFalse(equivalent)
		self.assertIn("90", reason)


def _record(
	*,
	agentic_tools=10,
	det_tools=2,
	agentic_tokens=5000,
	det_tokens=200,
	agentic_latency=8.0,
	det_latency=1.0,
	agentic_payload=20000,
	det_payload=800,
	agentic_scopes=("read:Sales Invoice", "read:Customer"),
	det_scopes=("read:Sales Invoice",),
	equivalent=True,
	invariants_passed=True,
	det_success=True,
) -> RunRecord:
	agentic_output = {"total": 100.0}
	det_output = agentic_output if equivalent else {"total": 1.0}
	return RunRecord(
		agentic=RunMetrics(
			output=agentic_output,
			tool_call_count=agentic_tools,
			token_count=agentic_tokens,
			latency_seconds=agentic_latency,
			payload_bytes=agentic_payload,
			permission_scopes=frozenset(agentic_scopes),
		),
		deterministic=RunMetrics(
			output=det_output,
			success=det_success,
			tool_call_count=det_tools,
			token_count=det_tokens,
			latency_seconds=det_latency,
			payload_bytes=det_payload,
			permission_scopes=frozenset(det_scopes),
		),
		invariants_passed=invariants_passed,
	)


class TestAggregateRuns(unittest.TestCase):
	def test_empty_records_is_worst_case_not_a_crash(self):
		report = aggregate_runs([], simulated=True)
		self.assertEqual(report.n, 0)
		self.assertEqual(report.failure_rate, 1.0)
		self.assertEqual(report.result_equivalence_rate, 0.0)
		self.assertFalse(report.permission_envelope_is_subset)

	def test_perfect_runs_reduction_percentages(self):
		records = [_record() for _ in range(5)]
		report = aggregate_runs(records, simulated=True)
		self.assertEqual(report.n, 5)
		self.assertEqual(report.result_equivalence_rate, 1.0)
		self.assertEqual(report.invariant_pass_rate, 1.0)
		self.assertEqual(report.failure_rate, 0.0)
		self.assertAlmostEqual(report.tool_call_reduction_pct, 0.8)  # (10-2)/10
		self.assertAlmostEqual(report.token_reduction_pct, 0.96)  # (5000-200)/5000
		self.assertAlmostEqual(report.latency_reduction_pct, 0.875)  # (8-1)/8
		self.assertAlmostEqual(report.payload_reduction_pct, 0.96)
		self.assertTrue(report.permission_envelope_is_subset)

	def test_permission_envelope_superset_is_flagged(self):
		records = [_record(det_scopes=("read:Sales Invoice", "write:Sales Invoice"))]
		report = aggregate_runs(records, simulated=True)
		self.assertFalse(report.permission_envelope_is_subset)

	def test_divergent_result_lowers_equivalence_rate(self):
		records = [_record(), _record(equivalent=False)]
		report = aggregate_runs(records, simulated=True)
		self.assertEqual(report.result_equivalence_rate, 0.5)

	def test_deterministic_failure_counts_toward_failure_rate(self):
		records = [_record(), _record(det_success=False)]
		report = aggregate_runs(records, simulated=True)
		self.assertEqual(report.failure_rate, 0.5)

	def test_zero_agentic_baseline_yields_none_not_divide_by_zero(self):
		records = [_record(agentic_tools=0, det_tools=0)]
		report = aggregate_runs(records, simulated=True)
		self.assertIsNone(report.tool_call_reduction_pct)

	def test_simulated_flag_is_threaded_through_not_inferred(self):
		records = [_record()]
		self.assertTrue(aggregate_runs(records, simulated=True).simulated)
		self.assertFalse(aggregate_runs(records, simulated=False).simulated)


# ---------------------------------------------------------------------------
# evaluate_promotion -- fails closed (I8/I10)
# ---------------------------------------------------------------------------


class TestPromotionGateFailsClosed(unittest.TestCase):
	def test_no_report_rejects(self):
		decision = evaluate_promotion(None, contains_writes=False)
		self.assertFalse(decision.approved)
		self.assertTrue(decision.reasons)

	def test_too_few_runs_rejects_even_if_perfect(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS - 1)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertFalse(decision.approved)
		self.assertTrue(any("run(s) measured" in r for r in decision.reasons))

	def test_read_only_perfect_report_approves(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertTrue(decision.approved)

	def test_result_divergence_rejects(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS - 1)] + [_record(equivalent=False)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertFalse(decision.approved)

	def test_invariant_failure_rejects(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS - 1)] + [_record(invariants_passed=False)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertFalse(decision.approved)

	def test_permission_escalation_rejects(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS - 1)] + [
			_record(det_scopes=("read:Sales Invoice", "write:Sales Invoice"))
		]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertFalse(decision.approved)

	def test_write_procedure_with_perfect_report_but_no_checklist_rejects(self):
		"""I8: a write Procedure is never promoted automatically, no matter how good the
		N-run numbers look -- omitting the checklist must fail closed, not default to pass."""
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=True)
		self.assertFalse(decision.approved)
		joined = " ".join(decision.reasons)
		self.assertIn("dry-run", joined)
		self.assertIn("rollback", joined)
		self.assertIn("idempotency", joined)
		self.assertIn("human review", joined)

	def test_write_procedure_partial_checklist_still_rejects(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		checklist = WriteChecklist(dry_run_passed=True, rollback_or_sandbox_tested=True)
		decision = evaluate_promotion(report, contains_writes=True, write_checklist=checklist)
		self.assertFalse(decision.approved)

	def test_write_procedure_full_checklist_approves(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		checklist = WriteChecklist(
			dry_run_passed=True,
			rollback_or_sandbox_tested=True,
			idempotency_test_passed=True,
			human_reviewed=True,
		)
		decision = evaluate_promotion(report, contains_writes=True, write_checklist=checklist)
		self.assertTrue(decision.approved)

	def test_simulated_report_still_approves_but_says_so(self):
		records = [_record() for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		decision = evaluate_promotion(report, contains_writes=False)
		self.assertTrue(decision.approved)
		self.assertTrue(any("simulated" in r for r in decision.reasons))

	def test_custom_thresholds_are_respected(self):
		records = [_record(agentic_tools=2, det_tools=2) for _ in range(MIN_REPRESENTATIVE_RUNS)]
		report = aggregate_runs(records, simulated=True)
		# Zero reduction: default threshold (>=0.0) still passes...
		self.assertTrue(evaluate_promotion(report, contains_writes=False).approved)
		# ...but a stricter threshold requiring real savings rejects it.
		strict = PromotionThresholds(min_tool_call_reduction_pct=0.5)
		decision = evaluate_promotion(report, contains_writes=False, thresholds=strict)
		self.assertFalse(decision.approved)


# ---------------------------------------------------------------------------
# Fixture loading (GOAL.md 5.2) -- all four benchmarks
# ---------------------------------------------------------------------------


class TestBenchmarkFixtureLoading(unittest.TestCase):
	def test_find_benchmark_dir_locates_all_four(self):
		missing = [name for name in ALL_BENCHMARK_NAMES if find_benchmark_dir(name) is None]
		if missing:
			self.skipTest(f"benchmarks not found relative to this checkout: {missing}")

	def test_load_benchmark_exposes_fixtures_and_invariants_module(self):
		if find_benchmark_dir(ALL_BENCHMARK_NAMES[0]) is None:
			self.skipTest("benchmarks/ not found relative to this checkout")
		fixture = load_benchmark(ALL_BENCHMARK_NAMES[0])
		self.assertIn("Benchmark 1", fixture.readme)
		self.assertTrue(fixture.seed_data)
		self.assertTrue(hasattr(fixture.invariants, "ALL_INVARIANTS"))

	def test_missing_benchmark_raises_not_silently_returns_none(self):
		with self.assertRaises(FileNotFoundError):
			load_benchmark("benchmark-does-not-exist")

	def test_all_four_benchmarks_invariants_modules_run_clean_standalone(self):
		"""Each invariants.py is executable on its own (its own ``if __name__`` self-check
		against a sample result) -- this is what T-50 loads and runs, never rewrites."""
		results = {}
		for name in ALL_BENCHMARK_NAMES:
			directory = find_benchmark_dir(name)
			if directory is None:
				self.skipTest(f"benchmarks/{name} not found relative to this checkout")
				return
			proc = subprocess.run(
				[sys.executable, str(directory / "invariants.py")],
				capture_output=True,
				text=True,
				timeout=30,
			)
			results[name] = proc
			self.assertEqual(proc.returncode, 0, msg=f"{name} invariants.py failed:\n{proc.stderr}")


if __name__ == "__main__":
	unittest.main()
