# Bulk Knowledge Ingestion — Frozen API & Status Contract (V1)

Status: FROZEN before parallel implementation. Derived from the verified
single-file pipeline (Phase B evidence: pgvector + sqlite_hybrid both proven
end-to-end) and the architect decision "reuse the worker, not the fan-out".

## Model

- **`Knowledge Ingestion`** (new header DocType) — the batch handle. No child table.
- **`Knowledge Input`** — stays the work queue and the per-file status surface.
  Gains 5 fields + 1 enum value. Bulk rows are created up-front in `Pending`
  ("accepted" and idempotency for free).
- **`huf/ai/knowledge/bulk_runner.py`** — one self-chaining, slice-bounded
  runner job on the `long` queue that calls the existing
  `process_knowledge_input()` per item, with the per-source lock in play.
- **`huf/ai/knowledge/bulk_api.py`** — thin whitelisted API surface.

## New DocType: Knowledge Ingestion

| fieldname | type | notes |
|---|---|---|
| (naming) | `format:ING-{#####}` | |
| `knowledge_source` | Link, reqd | scope + permission anchor |
| `status` | Select | `Queued\nRunning\nCompleted\nCompleted with Errors\nFailed\nCancelled` |
| `total_items` | Int | written at submit = len(accepted) |
| `submitted_by` | Link User, default `__user` | audit |
| `error_message` | Small Text | job-level only; never per-file |
| `started_at`, `finished_at` | Datetime | |
| `slice_seq` | Int, hidden | self-chaining cursor |

Permissions: same roles as Knowledge Source (System Manager / Huf Manager
full; Huf User read only).

## Knowledge Input additions

| fieldname | type | notes |
|---|---|---|
| `ingestion` | Link → Knowledge Ingestion, search_index | batch back-reference; the queue key |
| `external_key` | Data(255), search_index | caller's stable id; idempotency key = (knowledge_source, external_key) |
| `external_checksum` | Data(64) | optional sha256 hex; change detection + in-batch dedup |
| `skip_reason` | Select | `Duplicate\nUnchanged\nNo Text\nToo Large\nUnsupported\nUnsafe` |
| `attempts` | Int, default 0 | retry evidence; cap 5 |
| `status` | Select | adds `Skipped` to `Pending\nProcessing\nIndexed\nError` |

## Status contract (only substantiated claims)

| Word | Actual state | Proven by |
|---|---|---|
| accepted | header exists, `Queued`, `total_items=N` | synchronous response |
| queued | `Knowledge Input.status = Pending` | derived count |
| processing | `Processing` | derived count |
| indexed | `Indexed` with `chunks_created > 0` | derived count + chunks_created |
| retrievable | NOT a per-item status — never claimed | once per acceptance run via real `knowledge_search` probe |

Honesty rule: a document yielding 0 chunks is flipped by the runner from
`Indexed` → `Skipped / No Text`.

## Duplicate / idempotency rules (precedence order)

1. Duplicate `external_key` within one request → deduped at submit (last
   wins), response reports `duplicates_in_request`.
2. Existing row for same `(source, external_key)`:
   - `Indexed` + same checksum → `Skipped / Unchanged` (no new row, no re-index)
   - `Indexed` + different checksum → same row reset to `Pending` (re-index; `delete_chunks` swap)
   - `Error` → reset to `Pending` (safe retry; rows are reused, never re-created)
   - `Pending`/`Processing` → leave alone, count as accepted (idempotent replay)
3. Never create a second `Knowledge Input` for the same `external_key`
   (chunk cleanup is scoped by input_id; a second row duplicates vectors).
4. Within one ingestion, a second entry with identical `external_checksum`
   → `Skipped / Duplicate`.
5. `check_duplicate()` hard-throw is bypassed under
   `frappe.flags.huf_bulk_ingestion`; bulk dedup is the runner's job.
6. Single-writer invariant: only the runner creates bulk rows, sequentially.

## Frozen API (`huf/ai/knowledge/bulk_api.py`, all `@frappe.whitelist()`)

### `submit_files(knowledge_source, files)`
- `files`: list or JSON string; 1..`huf_bulk_max_files` (default 1000).
- Each entry: `{"file": <File docname or file_url>, "external_key": str(<=255, required), "checksum": optional sha256 hex}`.
- Gates: `Knowledge Source` write permission; `File` read per entry.
- Rejects whole request if a `Queued|Running` ingestion exists for the source.
- Enqueues exactly one `run_ingestion` on `queue="long"`, `job_id=f"huf_ingest_{name}"`, `deduplicate=True`, `enqueue_after_commit=True`, `timeout=1500`.
```jsonc
// 200 response
{"ingestion": "ING-00007", "status": "Queued", "total_items": 998,
 "duplicates_in_request": 2,
 "rejected": [{"index": 12, "reason": "File not found or not readable: /private/files/x.pdf"}]}
```

### `get_ingestion_status(ingestion, include_items=0, item_status=None, limit=50, start=0)`
```jsonc
{"ingestion": {"name": "ING-00007", "knowledge_source": "HR Handbook", "status": "Running",
               "total_items": 998, "submitted_by": "ops@x.com", "started_at": "…", "finished_at": null,
               "error_message": null},
 "counts": {"pending": 210, "processing": 1, "indexed": 760, "error": 12, "skipped": 15, "total": 998},
 "progress": 0.788,   // (indexed+error+skipped)/total, 0 when total=0
 "chunks_written": 8123,
 "items": [{"name": "…", "external_key": "hr/handbook.pdf", "file_name": "handbook.pdf",
            "status": "Error", "chunks_created": 0, "attempts": 2, "error_message": "…", "skip_reason": null}]}
```
Counts are a single `SELECT status, count(*), sum(chunks_created) … GROUP BY
status` filtered on `ingestion`. No denormalized counters anywhere.

### `retry_ingestion(ingestion, only_failed=1)`
`Error` rows → `Pending` (with `only_failed=0`, `Skipped/No Text` too);
re-enqueues runner; refuses while `Running`.

### `cancel_ingestion(ingestion)`
Header → `Cancelled` + `finished_at`; runner checks header at slice boundary.

### `list_ingestions(knowledge_source=None, limit=20)`

## Runner contract

```
run_ingestion(ingestion_name)
├─ header terminal (Cancelled/Completed/…) → return
├─ Redis lock huf:ingest_lock:{ingestion} (nx, ex=120, refreshed) → else return
├─ materialize() if declared rows missing (only the runner creates rows)
├─ header.status = Running, started_at ||= now
├─ for row in Pending(limit=25) by creation:
│    deadline (600s between items) or Cancelled → break
│    claim: status=Processing, attempts+=1, commit      # crash marker
│    result = process_knowledge_input(row.name)
│    success && chunks_created==0 → Skipped / No Text
│    result["status"]=="busy"          → Pending (defer, not error)
├─ Pending remains → enqueue run_ingestion(ingestion, slice=seq+1)
└─ else finalize terminal status + finished_at
```
- Job id `huf_ingest_{name}_{slice}` (slice counter required for dedupe).
- Worker-died recovery: existing 1-min cron gains `recover_stalled_ingestions()` —
  `Running` header with stale `modified` and no live lock → re-enqueue;
  `Processing` rows older than 10 min → `Pending`.
- Failure isolation: per-item exceptions already become `Error` inside
  `process_knowledge_input`; the loop never breaks.

## P0 prerequisite fixes (correctness backbone)

1. `pgvector_backend.delete_chunks()` re-raises instead of swallowing
   (otherwise replay silently duplicates chunks — ids are random, add_chunks
   is append-only).
2. `indexer.process_knowledge_input()` distinguishes lock contention:
   returns `{"status": "busy"}` without touching doc status (today it lands
   in Error — false failures during concurrent runs).
3. `KnowledgeInput.check_duplicate()`/`after_insert()` respect
   `frappe.flags.huf_bulk_ingestion` (no throw, no auto-enqueue).

## Deliberately NOT built (V1)

S3/SFTP/Drive/directory scanners, ZIP extraction, `Ingestion Job Item` child
table, per-doc enqueue fan-out, denormalized counters, worker pool or rate
limiter, separate parser/embedder/persistence path, `source_kind`.
Scanners later plug in as "produce manifest entries" and reuse everything above.

## Known limitation (published)

One source = one indexing lane (~1 doc / 3–10 s → 1,000 docs ≈ 1–3 h).
Scale throughput by sharding across multiple Knowledge Sources.

## Sources (Upload / Zip / Directory / S3 / SFTP)

`Knowledge Ingestion` gains `source_kind`, `source_config` (non-secret echo) and status `Scanning`
(active, like Queued/Running; a stale Scanning header is failed by the sweeper after 20 min without
a heartbeat). `huf.ai.knowledge.bulk_sources_api.start_import(knowledge_source, source_kind, config)`
(POST) creates the Scanning header and enqueues `sources.scanners.run_scan` (queue long); the scan
creates private File docs, writes the manifest, flips Scanning -> Queued and enqueues the same
`run_ingestion`. Manifest entries with `skip_reason` (`Too Large` / `Unsupported` / `Unsafe`) have no File and
materialize as Skipped rows. Limits: `huf_bulk_max_file_mb` (50), `huf_bulk_max_files` (1000),
`huf_bulk_max_uncompressed_mb` (1024), `huf_bulk_allowed_extensions`, `huf_bulk_directory_roots`.
