# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for Plan v2 Issue 3: real model selection, runs.jsonl un-gating, and
transcript persistence, wired end to end through a STUB model.

IMPORTANT -- what this test does and does not prove
-----------------------------------------------------
``recovery_harness.LiveAPIModel.next_step()`` is a documented stub that raises
``NotImplementedError`` (no real API client is implemented in this task -- that is explicit
follow-up work). This test does NOT call a real model and does NOT prove a real API
integration works. It monkeypatches ``run_experiment.LiveAPIModel`` with a fake class whose
``next_step()`` returns a plausible ``ModelStep`` sequence (with non-zero, hand-set token
counts) shaped exactly like a real implementation's return value would be, and uses it to
prove the WIRING around model selection is correct end to end:

    MODEL + API key env vars present
        -> run_experiment.select_model_backend() reports use_live=True
        -> run_cell() constructs the live model (not MockedModel, not steered by any
           scripted rule)
        -> the row it produces carries the real model_id and tokens_are_real_accounting=True
        -> write_runs_jsonl() routes that row to results/runs.jsonl, not runs.mock.jsonl
        -> persist_transcript() writes the full transcript to
           results/transcripts/<condition>/<workload>/<fault>/<guarantee>/<seed>.json

If a real ``LiveAPIModel.next_step()`` is implemented later, this same wiring is exercised
by real rows without any further changes here.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))

import run_experiment as re_mod  # noqa: E402
from recovery_harness import ModelStep, ToolCallRequest  # noqa: E402


class _StubLiveModel:
    """Stands in for a real API-backed model: on construction it records ``model_id`` (as
    the real ``LiveAPIModel`` does) and its ``next_step`` immediately escalates, reporting
    hand-set, non-zero, honestly-labeled-as-fake token counts -- proving the token-recording
    path would work correctly if a real client populated these numbers instead.
    """

    def __init__(self, *, model_id: str | None = None) -> None:
        self.model_id = model_id
        self.temperature = 0.0  # a real client's config would set this for real

    def next_step(self, *, transcript: list[dict], available_tools: list[str]) -> ModelStep:
        return ModelStep(
            tool_call=ToolCallRequest("escalate", {"reason": "stub: proving live wiring, not a real decision"}),
            estimated_prompt_tokens=123,
            estimated_completion_tokens=45,
        )


class TestModelSelection(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in ("MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_no_model_env_uses_mocked(self):
        use_live, model_id = re_mod.select_model_backend()
        self.assertFalse(use_live)
        self.assertIsNone(model_id)

    def test_model_env_without_key_falls_back_to_mocked(self):
        os.environ["MODEL"] = "test-model"
        use_live, model_id = re_mod.select_model_backend()
        self.assertFalse(use_live, "MODEL alone, with no API key, must not select the live backend")
        self.assertIsNone(model_id)

    def test_model_env_with_key_selects_live(self):
        os.environ["MODEL"] = "test-model"
        os.environ["ANTHROPIC_API_KEY"] = "fake-key-not-real"
        use_live, model_id = re_mod.select_model_backend()
        self.assertTrue(use_live)
        self.assertEqual(model_id, "test-model")

    def test_model_env_with_openai_key_also_selects_live(self):
        os.environ["MODEL"] = "test-model"
        os.environ["OPENAI_API_KEY"] = "fake-key-not-real"
        use_live, model_id = re_mod.select_model_backend()
        self.assertTrue(use_live)


class TestStubbedLiveWiringEndToEnd(unittest.TestCase):
    """Proves the full selection -> run -> runs.jsonl -> transcript path, via a stub model
    (see module docstring: NOT a real API call).
    """

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in ("MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        os.environ["MODEL"] = "stub-model-v1"
        os.environ["ANTHROPIC_API_KEY"] = "fake-key-not-real"
        self._orig_live_model = re_mod.LiveAPIModel
        re_mod.LiveAPIModel = _StubLiveModel

    def tearDown(self):
        re_mod.LiveAPIModel = self._orig_live_model
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # Clean up any transcript this test wrote.
        import shutil

        stub_dir = re_mod.RESULTS_TRANSCRIPTS_DIR / "C4"
        if stub_dir.exists():
            shutil.rmtree(stub_dir, ignore_errors=True)

    def test_live_row_has_real_model_id_and_real_accounting_flag(self):
        row = re_mod.run_cell(condition="C4", workload_name="W1", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
        self.assertEqual(row["model_id"], "stub-model-v1")
        self.assertTrue(row["tokens_are_real_accounting"])
        self.assertEqual(row["input_tokens"], 123)
        self.assertEqual(row["output_tokens"], 45)
        self.assertEqual(row["handoff_tokens"], 123)
        self.assertNotEqual(row["temperature"], "NA", "a live row must not carry the mocked-case placeholder string")
        self.assertEqual(row["temperature"], 0.0)
        self.assertTrue(row["escalated"])

    def test_live_row_routes_to_runs_jsonl_not_mock(self):
        row = re_mod.run_cell(condition="C4", workload_name="W1", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
        mock_path = re_mod.RESULTS_DIR / "runs.mock.jsonl"
        live_path = re_mod.RESULTS_DIR / "runs.jsonl"
        orig_mock = mock_path.read_text() if mock_path.exists() else None
        orig_live = live_path.read_text() if live_path.exists() else None
        try:
            re_mod.write_runs_jsonl([row])
            self.assertTrue(live_path.exists(), "a live row must produce results/runs.jsonl")
            live_rows = [json.loads(line) for line in live_path.read_text().splitlines() if line.strip()]
            self.assertEqual(len(live_rows), 1)
            self.assertEqual(live_rows[0]["model_id"], "stub-model-v1")
            if mock_path.exists():
                mock_rows = [json.loads(line) for line in mock_path.read_text().splitlines() if line.strip()]
                self.assertFalse(any(r.get("model_id") == "stub-model-v1" for r in mock_rows))
        finally:
            if orig_mock is None:
                mock_path.unlink(missing_ok=True)
            else:
                mock_path.write_text(orig_mock)
            if orig_live is None:
                live_path.unlink(missing_ok=True)
            else:
                live_path.write_text(orig_live)

    def test_live_run_persists_transcript(self):
        row = re_mod.run_cell(condition="C4", workload_name="W1", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
        self.assertIsNotNone(row["transcript_path"])
        full_path = re_mod.HERE / row["transcript_path"]
        self.assertTrue(full_path.exists())
        entries = json.loads(full_path.read_text())
        self.assertTrue(any(e["kind"] == "tool_call" and e["content"]["tool_name"] == "escalate" for e in entries))

    def test_scripted_rule_is_never_consulted_when_live_selected(self):
        # If the scripted policy were still being built/consulted for a live run, this
        # would either raise (rule constructors expect concrete kwargs the live path
        # doesn't need to supply) or silently steer the stub -- neither happens: the stub
        # always escalates regardless of condition/fault/guarantee, proving nothing but
        # the system prompt/context/guard can be influencing it.
        for condition in ("C1", "C4", "C4+G", "C5", "C6"):
            row = re_mod.run_cell(condition=condition, workload_name="W1", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
            self.assertTrue(row["escalated"], f"{condition}: stub model's own decision (escalate) must be respected untouched")


if __name__ == "__main__":
    unittest.main()
