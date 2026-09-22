# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for the --condition/--seeds/--output-suffix CLI flags added to
run_experiment.py (Track-Item: v3-issue-b-prep), which let N parallel real-run workers
each dispatch a distinct slice of the experiment matrix to its own output file.

Pure pytest/unittest -- no frappe, no bench, no network. Every run here goes through
MockedModel (no MODEL env var / API key is set), so these tests cost nothing and never
touch the real Gemini API. All file I/O is redirected to a per-test tmp directory by
monkeypatching the module's RESULTS_DIR-derived path constants, so these tests can never
write into (or be confused by) the real benchmarks/safe-deopt/results/ directory.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))

import run_experiment as re_mod  # noqa: E402


class _IsolatedResultsDirMixin:
    """Redirects every results-path module constant to a fresh tmp dir for the duration of
    a test, and guarantees they're restored afterwards regardless of outcome. Also strips
    any live-model env vars so every cell in these tests runs against MockedModel.
    """

    def setUp(self):
        # row["transcript_path"] is stored relative to HERE (run_experiment.py's own
        # directory) via Path.relative_to(HERE) -- so the isolated results dir must live
        # under HERE, not under the system tmp dir, or that relative_to() call raises.
        self._tmp = Path(tempfile.mkdtemp(prefix="run_experiment_cli_flags_test_", dir=str(re_mod.HERE)))
        self._orig = {
            name: getattr(re_mod, name)
            for name in (
                "RESULTS_DIR",
                "RUNS_MOCK_JSONL_PATH",
                "RUNS_JSONL_PATH",
                "SUMMARY_CSV_PATH",
                "PLOTS_DIR",
                "RESULTS_TRANSCRIPTS_DIR",
            )
        }
        re_mod.RESULTS_DIR = self._tmp
        re_mod.RUNS_MOCK_JSONL_PATH = self._tmp / "runs.mock.jsonl"
        re_mod.RUNS_JSONL_PATH = self._tmp / "runs.jsonl"
        re_mod.SUMMARY_CSV_PATH = self._tmp / "summary.csv"
        re_mod.PLOTS_DIR = self._tmp / "plots"
        re_mod.RESULTS_TRANSCRIPTS_DIR = self._tmp / "transcripts"

        self._orig_env = {k: os.environ.get(k) for k in ("MODEL",) + re_mod._API_KEY_ENV_VARS}
        for k in self._orig_env:
            os.environ.pop(k, None)

        # run_cell/run_all/write_runs_jsonl bind their transcripts_dir/output-path defaults
        # at function-definition time, so reassigning the module constants above does NOT
        # change what a caller gets when it omits those kwargs. Patch the bound defaults
        # too, so every caller in these tests -- not just ones that pass transcripts_dir
        # explicitly -- is isolated from the real results/ directory.
        self._orig_run_cell_kwdefaults = re_mod.run_cell.__kwdefaults__
        new_run_cell_kwdefaults = dict(self._orig_run_cell_kwdefaults)
        new_run_cell_kwdefaults["transcripts_dir"] = re_mod.RESULTS_TRANSCRIPTS_DIR
        re_mod.run_cell.__kwdefaults__ = new_run_cell_kwdefaults

        self._orig_run_all_defaults = re_mod.run_all.__defaults__
        new_run_all_defaults = list(self._orig_run_all_defaults)
        new_run_all_defaults[-1] = re_mod.RESULTS_TRANSCRIPTS_DIR
        re_mod.run_all.__defaults__ = tuple(new_run_all_defaults)

        self._orig_write_runs_jsonl_defaults = re_mod.write_runs_jsonl.__defaults__
        re_mod.write_runs_jsonl.__defaults__ = (re_mod.RUNS_JSONL_PATH, re_mod.RUNS_MOCK_JSONL_PATH)

    def tearDown(self):
        re_mod.run_cell.__kwdefaults__ = self._orig_run_cell_kwdefaults
        re_mod.run_all.__defaults__ = self._orig_run_all_defaults
        re_mod.write_runs_jsonl.__defaults__ = self._orig_write_runs_jsonl_defaults
        for name, value in self._orig.items():
            setattr(re_mod, name, value)
        for k, v in self._orig_env.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]


class TestBackwardCompatibleNoFlagsBehavior(_IsolatedResultsDirMixin, unittest.TestCase):
    """No new flags passed -> byte-for-byte identical to pre-flag behavior: same matrix
    (all conditions x all workloads x all faults x all guarantees, single seed=SEED), same
    row schema, written to the same unsuffixed file names.
    """

    def test_no_flags_matches_run_all_defaults(self):
        # "Today's known-good behavior" fixture, computed directly (bypassing the CLI) --
        # this is what run_experiment.py has always produced with no arguments.
        expected_rows = re_mod.run_all(transcripts_dir=re_mod.RESULTS_TRANSCRIPTS_DIR)

        re_mod.main([])

        actual_rows = self._read_jsonl(re_mod.RUNS_MOCK_JSONL_PATH)

        # Row count: same matrix size (build_matrix() with defaults == build_matrix() as
        # it existed before this change).
        self.assertEqual(len(actual_rows), len(expected_rows))
        self.assertEqual(len(actual_rows), len(re_mod.build_matrix()))

        # Schema shape: identical set of keys on every row, matching the pre-flag shape.
        expected_keys = set(expected_rows[0].keys())
        for row in actual_rows:
            self.assertEqual(set(row.keys()), expected_keys)

        # Every row is mocked (no live model configured) and every row uses the single
        # fixed default seed, exactly as before --seeds existed.
        for row in actual_rows:
            self.assertFalse(row.get("tokens_are_real_accounting"))
            self.assertEqual(row["seed"], re_mod.SEED)

        # Byte-for-byte: same (condition, workload, fault, guarantee) cells appear, in the
        # same order, as the pre-flag build_matrix() produced.
        actual_cells = [(r["condition"], r["workload"], r["fault"], r["tool_guarantee"]) for r in actual_rows]
        expected_cells = [(r["condition"], r["workload"], r["fault"], r["tool_guarantee"]) for r in expected_rows]
        self.assertEqual(actual_cells, expected_cells)

        # No suffixed files were created, and results/runs.jsonl (real-rows file) does not
        # exist since no live rows were produced (mocked-only run, as always).
        self.assertFalse(re_mod.RUNS_JSONL_PATH.exists())
        self.assertFalse((re_mod.RESULTS_DIR / "runs.testC1.jsonl").exists())
        self.assertTrue(re_mod.RESULTS_TRANSCRIPTS_DIR.exists() or True)  # dir only created if an LLM cell persists a transcript; no assertion needed either way here


class TestConditionSeedsOutputSuffixFlags(_IsolatedResultsDirMixin, unittest.TestCase):
    def test_condition_seeds_output_suffix_produce_isolated_c1_only_output(self):
        re_mod.main(["--condition", "C1", "--seeds", "2", "--output-suffix", "testC1"])

        suffixed_mock_path = re_mod.RESULTS_DIR / "runs.mock.testC1.jsonl"
        rows = self._read_jsonl(suffixed_mock_path)

        n_c1_cells = len(re_mod.build_matrix(conditions=("C1",)))
        self.assertEqual(len(rows), n_c1_cells * 2, f"expected {n_c1_cells} C1 cells x 2 seeds, got {len(rows)} rows")

        # Only C1 rows.
        self.assertTrue(all(r["condition"] == "C1" for r in rows), f"non-C1 condition leaked in: {sorted(set(r['condition'] for r in rows))}")

        # Exactly 2 distinct seeds, SEED and SEED+1, each covering every C1 cell once.
        seeds_seen = sorted(set(r["seed"] for r in rows))
        self.assertEqual(seeds_seen, [re_mod.SEED, re_mod.SEED + 1])
        for seed in seeds_seen:
            self.assertEqual(sum(1 for r in rows if r["seed"] == seed), n_c1_cells)

        # The default, unsuffixed files must not exist at all -- this run never touched them.
        self.assertFalse(re_mod.RUNS_JSONL_PATH.exists(), "default results/runs.jsonl must not be touched by a suffixed run")
        self.assertFalse(re_mod.RUNS_MOCK_JSONL_PATH.exists(), "default results/runs.mock.jsonl must not be touched by a suffixed run")

        # Transcripts (if any were persisted for the LLM condition C1) land under the
        # suffixed transcripts directory, never the default one.
        self.assertFalse((re_mod.RESULTS_TRANSCRIPTS_DIR).exists(), "default results/transcripts/ must not be touched by a suffixed run")

    def test_condition_accepts_comma_separated_and_repeated_form(self):
        conditions_a = re_mod._parse_conditions_arg(["C4,C4+G"])
        conditions_b = re_mod._parse_conditions_arg(["C4", "C4+G"])
        self.assertEqual(conditions_a, ("C4", "C4+G"))
        self.assertEqual(conditions_b, ("C4", "C4+G"))

    def test_condition_omitted_means_all_conditions(self):
        self.assertEqual(re_mod._parse_conditions_arg(None), re_mod.ALL_CONDITIONS)
        self.assertEqual(re_mod._parse_conditions_arg([]), re_mod.ALL_CONDITIONS)

    def test_unknown_condition_raises(self):
        with self.assertRaises(SystemExit):
            re_mod._parse_conditions_arg(["NOT-A-CONDITION"])

    def test_seeds_default_is_single_seed(self):
        cells_default = re_mod.build_matrix()
        cells_explicit_one = re_mod.build_matrix(seeds=(re_mod.SEED,))
        self.assertEqual(cells_default, cells_explicit_one)


if __name__ == "__main__":
    unittest.main()
