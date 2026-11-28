# Wave W2 load gate

Module: `huf/ai/flow/tests/perf/test_w2_gate.py` (H-W2-21). Seed helpers: `huf/ai/flow/tests/perf/seed.py`.

**Status: load run at the pre-PR gate (2026-11-28).** Bulk entry misses its target; the other targets in the table passed.

## How to run

Use a disposable site with `allow_tests` on and the scheduler off.

Smoke:

```
bench --site <site> run-tests --app huf --module huf.ai.flow.tests.perf.test_w2_gate
```

Load gate (100k members over 8 flows, a 20k wave due in the same minute, 10% duplicate deliveries, 3k guarded
sends, 10k replayed webhooks):

```
HUF_W2_LOAD_GATE=1 bench --site <site> run-tests --app huf --module huf.ai.flow.tests.perf.test_w2_gate
```

Each metric is printed as `W2_GATE <metric> <value>`; the test fails and lists every missed target. The module
deletes its rows afterwards (flows `perfseed-w2-flow-*`, their runs and members, consent rows
`perfseed-w2-guard-*`, seeded gateway events). The W1 targets are measured by the W1 gate
(`docs/testing/W1_LOAD_GATE.md`); run it in the same pre-PR session, its results count for this gate too.

## Scenario

1. Bulk entry: `enter_members` on 8 flows, 100k members total; chunk jobs run inline. A second submission must
   add nothing.
2. Wave: 20k `send.message` executions through the real guard chain and step-key replay, with a fake transport.
   Every 10th member is outside its send window (the guard defers it); every 10th delivery is repeated with the
   same run and step key. Every persisted context, result and logger call is scanned for the member's phone number.
3. Guard: 3k email sends with Huf's real built-in steps (consent read included) in one `guard.batch()`.
4. Replay: 10k stored gateway event ids ingested again.

## Results

| Metric | Target | Result | Status |
|---|---|---|---|
| `duplicate_runs` (bulk entry, incl. resubmission) | 0 | 0 | PASS |
| `bulk_entry_seconds_per_100k` | < 300 | 1071 | **FAIL** |
| `duplicate_sends` (G2, step keys) | 0 | 0 | PASS |
| `sends_outside_window` | 0 | 0 | PASS |
| `unsent_in_window` | 0 | 0 | PASS |
| `pii_in_trace` (G4) | 0 | 0 | PASS |
| `replay_duplicate_effects` (duplicate webhooks) | 0 | 0 | PASS |
| `guard_sends_per_minute` (G5 chain) | >= 3000 | 46283 (one process) | PASS |
| All W1 targets | see W1 gate | see W1 gate | PASS (manual kill not run) |

Measured 2026-11-28 at 72d989e99. Host: 8 vCPU AMD EPYC 7R13, 31 GiB, MariaDB 11.8.6 (buffer pool 2 GiB, `innodb_flush_log_at_trx_commit=0`, no binlog), no workers: one process.

H-W2-18 republish drain (`test_republish_drain_gate`): 100000 parked runs finished, 0 wrong version, **1448 s** against < 600 s (**FAIL**), one process.

The inline jobs start with fresh per-job state (`seed.new_job`), as a worker's would.

## What the numbers do not cover

- The wave builds runs in memory and stubs context persistence, run transitions and `defer_send`; it measures the
  send step and guard, not the sweeper wake (the W1 drain metric) or the outbox worker.
- The wave's built-in guard steps are replaced by one allow step and the window by a stub, so its timing is not the
  guard throughput; `guard_sends_per_minute` is measured separately on one process, not 4 workers.
- Duplicate webhooks replay only stored ids; the mix with new events is covered by `test_gateway_event_replay`.
- The 100k parked republish drain (H-W2-18) is not part of this module.
