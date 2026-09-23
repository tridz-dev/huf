"""One-off script: regenerate exactly the 180 F4 rows in results/runs.jsonl that were
generated with the OLD buggy FaultInjector._inject_f4 (which committed a write for real but
then always fabricated a validation-rejection response to the caller regardless of outcome).

Fixed in commit 8c5466504 (see faults.py). This script re-runs ONLY the 180 F4 cells using
run_experiment.run_cell -- the SAME logic every other cell in runs.jsonl was produced with --
and appends each new row to results/runs_f4_rerun.jsonl. It does NOT touch results/runs.jsonl.

Usage:
    MODEL=gemini-3.5-flash-lite <api-key-env-set-inline> python3 rerun_f4_cells.py --model-group gemini
    MODEL=gpt-4o-mini <api-key-env-set-inline> python3 rerun_f4_cells.py --model-group gpt

Cost guardrail: aborts if cumulative cost_usd across this process's own rows exceeds
HARD_ABORT_USD.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_experiment as re_mod  # noqa: E402

HARD_ABORT_USD = 3.0

CONDITIONS = ("C1", "C4", "C4+G", "C5", "C6")
WORKLOADS = ("W1", "W2", "W2-nonidempotent")
FAULT_ID = "F4"

# (condition, workload, seed) tuples per model group, matching the exact set of old F4 rows
# in results/runs.jsonl (verified: 150 gemini rows at seeds 42-51, 30 gpt-4o-mini rows at
# seeds 42-43, across all 5 LLM conditions x 3 workloads).
GEMINI_SEEDS = tuple(range(42, 52))  # 42..51 inclusive, 10 seeds
GPT_SEEDS = (42, 43)


def build_cells(model_group: str) -> list[tuple[str, str, int]]:
    seeds = GEMINI_SEEDS if model_group == "gemini" else GPT_SEEDS
    cells = []
    for condition in CONDITIONS:
        for workload in WORKLOADS:
            for seed in seeds:
                cells.append((condition, workload, seed))
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-group", choices=("gemini", "gpt"), required=True)
    parser.add_argument(
        "--output",
        default=str(HERE / "results" / "runs_f4_rerun.jsonl"),
        help="Output JSONL path (appended to, not overwritten).",
    )
    args = parser.parse_args()

    use_live, live_model_id = re_mod.select_model_backend()
    if not use_live:
        print(
            "[rerun_f4_cells] MODEL env var + a recognized API key are required -- refusing "
            "to run this against MockedModel (that would defeat the whole point of this "
            "script).",
            file=sys.stderr,
        )
        sys.exit(1)

    expected_prefix = "gemini-" if args.model_group == "gemini" else "gpt-"
    if not live_model_id.startswith(expected_prefix):
        print(
            f"[rerun_f4_cells] --model-group {args.model_group!r} expects MODEL to start "
            f"with {expected_prefix!r}, got MODEL={live_model_id!r}.",
            file=sys.stderr,
        )
        sys.exit(1)

    commit_hash = re_mod.huf_commit_hash()
    cells = build_cells(args.model_group)
    print(
        f"[rerun_f4_cells] model_group={args.model_group} live_model_id={live_model_id!r} "
        f"huf_commit_hash={commit_hash} -- regenerating {len(cells)} F4 cells",
        file=sys.stderr,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cumulative_cost = 0.0
    rows_written = 0
    with open(out_path, "a") as out_f:
        for i, (condition, workload, seed) in enumerate(cells, start=1):
            row = re_mod.run_cell(
                condition=condition,
                workload_name=workload,
                fault_id=FAULT_ID,
                guarantee_for_matrix="none",
                commit_hash=commit_hash,
                seed=seed,
                transcripts_dir=re_mod.RESULTS_TRANSCRIPTS_DIR,
            )
            cumulative_cost += row.get("cost_usd") or 0.0
            out_f.write(json.dumps(row) + "\n")
            out_f.flush()
            rows_written += 1
            print(
                f"[rerun_f4_cells] {i}/{len(cells)} {condition}/{workload}/seed={seed} "
                f"real={row['tokens_are_real_accounting']} cost=${row['cost_usd']:.6f} "
                f"cumulative=${cumulative_cost:.6f}",
                file=sys.stderr,
            )
            if not row["tokens_are_real_accounting"]:
                print(
                    "[rerun_f4_cells] ABORT: a row came back with tokens_are_real_accounting="
                    "False -- this must never happen for a live-backed run. Stopping.",
                    file=sys.stderr,
                )
                sys.exit(2)
            if cumulative_cost >= HARD_ABORT_USD:
                print(
                    f"[rerun_f4_cells] HARD ABORT: cumulative cost ${cumulative_cost:.4f} >= "
                    f"${HARD_ABORT_USD} guardrail. Stopping after {rows_written} rows.",
                    file=sys.stderr,
                )
                sys.exit(3)

    print(
        f"[rerun_f4_cells] done. wrote {rows_written} rows to {out_path}, "
        f"cumulative cost=${cumulative_cost:.6f}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
