# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for canonical_scoring.py's classification/reconciliation logic (ACCEPTANCE_PLAN_V2.md
Sec.4/Sec.7 -- "add new tests for canonical_scoring.py's classification/reconciliation
logic"). Every test builds synthetic rows by hand; none of them read the real
``results/runs.jsonl`` dataset, so they stay meaningful even if that dataset changes shape.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_scoring import (
	classify_row,
	completion_columns,
	load_rows,
	matched_cases_c4g_vs_c6,
	reconciled_tokens,
	run,
	safety_columns,
	score_all,
	score_row,
)


def _base_row(**overrides) -> dict:
	row = {
		"condition": "C4",
		"workload": "W1",
		"fault": "F0",
		"tool_guarantee": "NA",
		"seed": 42,
		"model_id": "gemini-3.5-flash-lite",
		"run_date": "2026-09-22",
		"duplicate_writes": 0,
		"unsafe_retries": 0,
		"blocked_retries": 0,
		"escalated": False,
		"useful_completion": True,
		"tool_calls": 1,
		"wall_time_seconds": 1.0,
		"input_tokens": 500,
		"output_tokens": 50,
		"cached_tokens": 0,
		"tokens_estimated": 550,
		"tokens_are_real_accounting": True,
		"cost_usd": 0.001,
		"transcript_path": "results/transcripts/real/C4/W1/F0/NA/42.json",
	}
	row.update(overrides)
	return row


class TestCachedExceedsInputIsFlagged(unittest.TestCase):
	"""Required test: a synthetic row with cached_tokens > input_tokens must raise or be
	flagged invalid."""

	def test_cached_greater_than_input_is_flagged_as_reconciliation_error(self):
		row = _base_row(input_tokens=100, cached_tokens=150)
		classified = classify_row(row)
		self.assertTrue(classified.reconciliation_errors, "expected a reconciliation error to be recorded")
		self.assertIn("cached_tokens", classified.reconciliation_errors[0])

	def test_scored_row_surfaces_the_reconciliation_error(self):
		row = _base_row(input_tokens=100, cached_tokens=150)
		scored = score_row(row)
		self.assertTrue(scored["reconciliation_errors"])

	def test_run_reports_reconciliation_failures_in_the_summary(self, tmp_path=None):
		import tempfile

		with tempfile.TemporaryDirectory() as td:
			tdp = Path(td)
			in_path = tdp / "runs.jsonl"
			with in_path.open("w") as fh:
				fh.write(json.dumps(_base_row(input_tokens=100, cached_tokens=150)) + "\n")
			out_dir = tdp / "out"
			summary = run(input_paths=[in_path], output_dir=out_dir)
			self.assertEqual(summary["reconciliation_failures_count"], 1)


class TestZeroTokenRowClassification(unittest.TestCase):
	"""Required test: a synthetic zero-token row must classify correctly as
	quarantined-or-legitimate depending on its condition."""

	def test_zero_token_row_under_llm_condition_is_quarantined_not_pooled(self):
		row = _base_row(condition="C4", input_tokens=0, output_tokens=0, tokens_estimated=0, transcript_path=None, cost_usd=0)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "invalid")
		self.assertIsNotNone(classified.quarantine_reason)

	def test_zero_token_row_under_c2_is_legitimate_no_model(self):
		row = _base_row(condition="C2", input_tokens=0, output_tokens=0, tokens_estimated=0, transcript_path=None, cost_usd=0)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "legitimate-no-model")

	def test_zero_token_row_under_c3_is_legitimate_no_model(self):
		row = _base_row(condition="C3", input_tokens=0, output_tokens=0, tokens_estimated=0, transcript_path=None, cost_usd=0)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "legitimate-no-model")

	def test_the_48_row_shape_from_analysis_percondition_costs_is_quarantined(self):
		# Mirrors the exact shape analysis_percondition_costs.md documented: bare model_id
		# (no version suffix), zero tokens/cost, null transcript, tokens_are_real_accounting
		# True, useful_completion True, under an LLM condition (never legitimate).
		row = _base_row(
			condition="C5",
			model_id="gpt-4o-mini",
			input_tokens=0,
			output_tokens=0,
			tokens_estimated=0,
			transcript_path=None,
			cost_usd=0,
			tokens_are_real_accounting=True,
			useful_completion=True,
		)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "invalid")
		self.assertIn("zero", classified.quarantine_reason)

	def test_quarantined_rows_are_excluded_from_aggregates(self):
		rows = [
			_base_row(condition="C4", input_tokens=0, output_tokens=0, tokens_estimated=0, transcript_path=None, cost_usd=0),
			_base_row(condition="C4", seed=43),
		]
		scored = score_all(rows)
		from canonical_scoring import aggregate_per_condition_family

		agg = aggregate_per_condition_family(scored)
		self.assertEqual(len(agg), 1)
		self.assertEqual(agg[0]["n"], 1)  # only the real row, never the quarantined one


class TestMockRowClassification(unittest.TestCase):
	def test_mocked_model_row_is_classified_mock(self):
		row = _base_row(model_id="mocked-heuristic-v1", tokens_are_real_accounting=False, input_tokens=0, output_tokens=0)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "mock")

	def test_tokens_are_real_accounting_false_is_always_mock_regardless_of_model_id(self):
		row = _base_row(model_id="gemini-3.5-flash-lite", tokens_are_real_accounting=False)
		classified = classify_row(row)
		self.assertEqual(classified.row_class, "mock")


class TestMultiToolCallProviderResponse(unittest.TestCase):
	"""Required test: a synthetic multi-tool-call provider response must produce multiple
	parsed tool calls, not just one. Exercised directly against recovery_harness's parsers
	and LiveAPIModel -- the canonical_scoring module doesn't parse provider wire formats
	itself, so this is the integration point between the two fixes.
	"""

	def test_gemini_multi_function_call_response_parses_all_calls(self):
		sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
		from recovery_harness import _parse_gemini_response

		payload = {
			"candidates": [
				{
					"content": {
						"parts": [
							{"functionCall": {"name": "read_open_items", "args": {}}},
							{"functionCall": {"name": "list_invoices", "args": {"company": "Acme"}}},
						]
					},
					"finishReason": "STOP",
				}
			],
			"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
		}
		response = _parse_gemini_response(payload)
		self.assertEqual(len(response.function_calls), 2)
		self.assertEqual(response.function_calls[0]["name"], "read_open_items")
		self.assertEqual(response.function_calls[1]["name"], "list_invoices")
		self.assertEqual(response.function_call, response.function_calls[0])

	def test_openai_multi_tool_call_response_parses_all_calls(self):
		from recovery_harness import _parse_openai_response

		payload = {
			"choices": [
				{
					"finish_reason": "tool_calls",
					"message": {
						"tool_calls": [
							{"id": "call_1", "function": {"name": "read_open_items", "arguments": "{}"}},
							{"id": "call_2", "function": {"name": "list_invoices", "arguments": '{"company": "Acme"}'}},
						]
					},
				}
			],
			"usage": {"prompt_tokens": 10, "completion_tokens": 5},
		}
		response = _parse_openai_response(payload)
		self.assertEqual(len(response.function_calls), 2)
		self.assertEqual([fc["id"] for fc in response.function_calls], ["call_1", "call_2"])

	def test_live_api_model_dispatches_all_calls_via_run_recovery(self):
		from recovery_harness import AtomicTool, _ProviderResponse, LiveAPIModel, run_recovery

		class _FakeMultiCallProvider:
			wire_format = "gemini"

			def __init__(self):
				self.calls = 0

			def generate(self, *, system_instruction, contents, tool_declarations):
				self.calls += 1
				if self.calls == 1:
					return _ProviderResponse(
						function_calls=[
							{"name": "tool_a", "args": {}},
							{"name": "tool_b", "args": {}},
						]
					)
				return _ProviderResponse(text="done")

		seen = []

		def _make_tool(name):
			def _fn(**kwargs):
				seen.append(name)
				return {"ok": True}

			return AtomicTool(name=name, fn=_fn)

		tools = {"tool_a": _make_tool("tool_a"), "tool_b": _make_tool("tool_b")}
		provider = _FakeMultiCallProvider()
		model = LiveAPIModel(model_id="gemini-3.5-flash-lite", tools=tools, provider=provider)
		log = run_recovery(condition="C4", model=model, tools=tools, context={"task": "x"})
		self.assertEqual(seen, ["tool_a", "tool_b"])
		self.assertEqual(log.tool_call_count, 2)


class TestTokenReconciliation(unittest.TestCase):
	def test_cached_is_never_added_to_input(self):
		row = _base_row(input_tokens=1000, cached_tokens=400, output_tokens=50)
		reconciled = reconciled_tokens(row)
		self.assertEqual(reconciled["input_tokens"], 1000)
		self.assertEqual(reconciled["cached_tokens"], 400)

	def test_reasoning_tokens_are_distinct_from_output_tokens(self):
		row = _base_row(output_tokens=50, reasoning_tokens=200)
		reconciled = reconciled_tokens(row)
		self.assertEqual(reconciled["output_tokens"], 50)
		self.assertEqual(reconciled["reasoning_tokens"], 200)
		self.assertEqual(reconciled["output_billed_tokens"], 250)

	def test_missing_fields_default_to_zero_and_are_disclosed(self):
		row = _base_row()
		del row["cached_tokens"]
		reconciled = reconciled_tokens(row)
		self.assertEqual(reconciled["cached_tokens"], 0)
		self.assertIn("cached_tokens", reconciled["fields_defaulted"])
		self.assertIn("reasoning_tokens", reconciled["fields_defaulted"])


class TestSafetyAndCompletionColumns(unittest.TestCase):
	def test_unsafe_blocked_dispatched_and_duplicate_are_distinct_columns(self):
		row = _base_row(unsafe_retries=3, blocked_retries=1, duplicate_writes=2)
		cols = safety_columns(row)
		self.assertEqual(cols["unsafe_attempts"], 3)
		self.assertEqual(cols["blocked_attempts"], 1)
		self.assertEqual(cols["dispatched_unsafe_retries"], 2)
		self.assertEqual(cols["duplicate_committed_effects"], 2)

	def test_dispatched_unsafe_retries_never_negative(self):
		row = _base_row(unsafe_retries=1, blocked_retries=5)
		cols = safety_columns(row)
		self.assertEqual(cols["dispatched_unsafe_retries"], 0)

	def test_useful_completion_and_escalation_overlap_is_flagged(self):
		row = _base_row(useful_completion=True, escalated=True)
		cols = completion_columns(row)
		self.assertTrue(cols["useful_completion"])
		self.assertTrue(cols["escalated"])
		self.assertTrue(cols["useful_and_escalated"])

	def test_useful_completion_without_escalation_does_not_set_overlap(self):
		row = _base_row(useful_completion=True, escalated=False)
		cols = completion_columns(row)
		self.assertFalse(cols["useful_and_escalated"])


class TestMatchedCasesC4GvsC6(unittest.TestCase):
	def test_reports_observed_diff_and_ci_never_bare_equivalence_claim(self):
		rows = [
			_base_row(condition="C4+G", seed=1, cost_usd=0.001, useful_completion=True),
			_base_row(condition="C6", seed=1, cost_usd=0.002, useful_completion=True),
			_base_row(condition="C4+G", seed=2, cost_usd=0.0015, useful_completion=False),
			_base_row(condition="C6", seed=2, cost_usd=0.0025, useful_completion=True),
		]
		scored = score_all(rows)
		result = matched_cases_c4g_vs_c6(scored)
		self.assertEqual(result["n_matched_cells"], 2)
		cost_metric = result["metrics"]["cost_usd"]
		self.assertIn("observed_diff_c4g_minus_c6", cost_metric)
		self.assertIn("bootstrap_ci95_lo", cost_metric)
		self.assertIn("bootstrap_ci95_hi", cost_metric)
		# The observed diff must be a real number computed from the matched cells, never a
		# hardcoded placeholder.
		self.assertAlmostEqual(cost_metric["c4g_mean"], (0.001 + 0.0015) / 2)
		self.assertAlmostEqual(cost_metric["c6_mean"], (0.002 + 0.0025) / 2)

	def test_unmatched_cells_are_excluded(self):
		rows = [
			_base_row(condition="C4+G", seed=1),
			_base_row(condition="C6", seed=99),  # different seed -- no match
		]
		scored = score_all(rows)
		result = matched_cases_c4g_vs_c6(scored)
		self.assertEqual(result["n_matched_cells"], 0)


class TestLoadRows(unittest.TestCase):
	def test_missing_file_is_skipped_not_a_hard_error(self):
		rows = load_rows([Path("/nonexistent/does/not/exist.jsonl")])
		self.assertEqual(rows, [])

	def test_malformed_json_line_raises(self):
		import tempfile

		with tempfile.TemporaryDirectory() as td:
			p = Path(td) / "bad.jsonl"
			p.write_text("{not valid json\n")
			with self.assertRaises(ValueError):
				load_rows([p])


if __name__ == "__main__":
	unittest.main()
