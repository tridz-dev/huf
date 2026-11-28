# Wave W1 load gate

Module: `huf/ai/flow/tests/perf/test_w1_gate.py`. Seed: `huf/ai/flow/tests/perf/seed.py` (see its README).

**Status: load run at the pre-PR gate (2026-11-28).** Every automated target passed; the manual worker kill was not run.

## How to run

Use a disposable site with `allow_tests` on and the scheduler off. The gate wakes every due wait, purges expired
state and members, and takes run locks on the whole site.

Smoke (at most 20 rows, behaviour only, no timing assertions):

```
bench --site <site> run-tests --app huf --module huf.ai.flow.tests.perf.test_w1_gate
```

Load gate (1M runs, 100k due waits, 1M members, 10k events, 100k expired state rows, 50 workers):

```
HUF_W1_LOAD_GATE=1 bench --site <site> run-tests --app huf --module huf.ai.flow.tests.perf.test_w1_gate
```

Each metric is printed as `W1_GATE <metric> <value>`; the test fails and lists every missed target. The module
deletes its rows afterwards. `seed.py` builds each DocType's rows in memory before inserting, so check free RAM
before the 1M seed.

## Results

| Metric | Target | Result | Status |
|---|---|---|---|
| `sweep_query_p95_ms` (1M runs) | < 20 | 1.5 | PASS |
| `sweep_query_keys` (EXPLAIN) | `idx_agent_flow_run_status_resume_at` | `idx_agent_flow_run_status_resume_at` | PASS |
| `drain_seconds_per_100k` | < 600 | 124.6 | PASS |
| `drain_rows_per_minute` | recorded only | 48136 | recorded |
| `undrained_runs` | 0 | 0 | PASS |
| `double_wakes` | 0 | 0 | PASS |
| `duplicate_entries` (50-way) | 0 | 0 | PASS |
| `entry_p95_ms` | < 30 | 25.3 | PASS |
| `replay_duplicate_effects` (10k replays) | 0 | 0 | PASS |
| `replay_ms_per_event` | < 5 | 0.27 | PASS |
| `stuck_locks` | 0 | 0 | PASS |
| Real worker kill (manual, below) | 0 stuck locks | - | NOT RUN |
| `member_retention_seconds_per_100k` | < 60 | 2.8 | PASS |
| `state_retention_seconds_per_100k` | < 60 | 2.4 | PASS |
| `parked_row_avg_bytes` | < 4096 | 335 | PASS |

Measured 2026-11-28 at 72d989e99. Host: 8 vCPU AMD EPYC 7R13, 31 GiB, MariaDB 11.8.6 (buffer pool 2 GiB, `innodb_flush_log_at_trx_commit=0`, no binlog), no workers: one process. The real worker kill below was not run.

## What the numbers do not cover

- Drain runs the sweeper and its chunk jobs in one process and only counts continuations. It leaves out queue
  latency, parallel workers and the flow steps after a wake.
- Replay sends only already stored ids through `ingest_gateway_event`. The mix with new events is covered
  functionally by `test_gateway_event_replay`.
- Entry timing covers `claim_entry` plus `upsert_member` with their commits, not the creation of the run. One run per
  member under 50 triggers is covered by `test_flow_member_concurrency`.
- Row width is measured on the synthetic seed rows; a real parked run is checked by `test_flow_retention_batches`.
- `stuck_locks` stops the lock heartbeat and checks that each lock has an expiry. It does not kill a process.

## Manual step: real worker kill

With one `short`/`long` worker running a flow that stays inside a step, `kill -9` that worker. Wait longer than
`engine.RUN_LOCK_TTL_SECONDS` (120 s), then confirm the run's lock key is gone and that `sweep_stale_runs` can fail
the run.
