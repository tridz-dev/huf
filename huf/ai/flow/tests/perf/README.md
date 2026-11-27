# Flow load seed

`seed.py` writes synthetic rows for the load gates (H-W1-08, H-W2-21). It asserts and measures nothing.

Use a disposable test site only (`allow_tests` must be on).

```
bench --site <site> execute huf.ai.flow.tests.perf.seed.seed_all
bench --site <site> execute huf.ai.flow.tests.perf.seed.seed_all --kwargs "{'runs': 100000, 'due': 10000}"
bench --site <site> execute huf.ai.flow.tests.perf.seed.cleanup
```

## What is seeded (defaults)

| DocType | Rows | Shape |
|---|---|---|
| Agent Flow Run | 10,000 | 1,000 due `Waiting Timer` waits; the rest mixed Success, Failed, Cancelled, Waiting User and future waits |
| Flow Member State | 10,000 | 1,000 `Waiting` on a due run; 1,000 inactive for 400 days (for retention) |
| Gateway Event | 10,000 | distinct `provider_event_id`, `idempotency_key` derived as ingest does |

The defaults are the **10k scale**. They are not the 1M runs / 100k due waits of the H-W1-08 targets, so
results from them do not show those targets are met.

`replay_event_ids()` yields an inbound id stream in which 10% are already stored. The database cannot hold
duplicate events (`idempotency_key` is unique), so duplicates are replayed, not seeded.

## Limits

- Rows are bulk inserted: no controllers, hooks or link validation. The flows and gateway they name do not exist.
- With the scheduler on, the wake sweeper will pick up the due waits and their runs will fail. Keep the
  scheduler off while seeded rows exist, and run `cleanup` afterwards.
- Only fields that exist today are written. Tasks that add fields (such as `entry_window`) extend the seed.
- Concurrent member entry is a test scenario, not seed data; it is not covered here.
