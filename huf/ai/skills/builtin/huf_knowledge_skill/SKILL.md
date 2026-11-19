---
name: huf_knowledge_skill
title: HUF Knowledge Ingestion and Retrieval
category: Knowledge
version: 1.0.0
description: >
  Teach HUF Agents how to ingest documents into a HUF Knowledge Source
  (single-file and bulk), monitor processing, validate retrieval with
  provenance, diagnose failures, retry safely, and verify per backend type.
  Covers the frozen bulk API (submit_files / get_ingestion_status /
  retry_ingestion / cancel_ingestion / list_ingestions) and the extension
  contract for new knowledge backends.
---

# HUF Knowledge Ingestion & Retrieval

## 1. Identify before you ingest

Before touching any API, determine four things and state them to the user:

1. **Target** — which Knowledge Source (`knowledge_source` docname) and its
   `knowledge_type` (`sqlite_fts`, `sqlite_vec`, `sqlite_hybrid`, `chroma`,
   `pgvector`, `redis`, `zvec`, `weaviate`, `faiss`, `pinecone`). Read the
   Knowledge Source doc for `status`, `embedding_provider`, `embedding_model`,
   `vector_dimension`.
2. **Format** — what the content is: existing `File` docs (PDF/TXT/DOCX/...),
   pasted text, or URLs. This decides single-file vs bulk flow.
3. **Permissions** — bulk APIs check Knowledge Source *write* and File *read*
   per entry; `knowledge_search` checks Knowledge Source read unless the
   caller runs with agent context. Surface permission errors verbatim.
4. **Capabilities of the target** — see the verification matrix in §7.
   Vector backends prove readiness with a semantic query; FTS with a
   known-term query; table-style targets need record/key lookup (note: the
   `Huf Data Table` doctype is a *different* target type with its own bulk
   import via Frappe's Data Import — do not mix it up with knowledge
   ingestion).

Embeddings must already be configured on the source: `embedding_provider`
(AI Provider) + `embedding_model` (LiteLLM id) + `vector_dimension`, and
`vector_dimension` **must equal the model's real output dimension**
(e.g. `gemini/gemini-embedding-001` = 3072). A mismatch fails at embedding
time, not at submit time.

## 2. There is no "Agent Sync" API

HUF knowledge has exactly three mechanisms — do not look for anything else:

| Concern | Mechanism |
|---|---|
| Initiation | Insert a `Knowledge Input` (single file) or call `submit_files` (bulk) |
| Status | Poll `Knowledge Input.status` / `Knowledge Source.status` / `get_ingestion_status` |
| Readiness | Prove with a real `knowledge_search` query |

## 3. Single-file flow

1. Create a `Knowledge Input` doc:
   - `knowledge_source` = source docname.
   - `input_type` = `File` | `Text` | `URL`.
   - For `File`: `file` = the **File doc's `file_url`** (the pipeline looks
     the File doc up by `file_url`), plus `file_name` and `file_type`
     (extension-like value, e.g. `txt`, `pdf`, `url`).
   - For `Text`: `text` = content. For `URL`: `url` = address.
2. `after_insert` auto-enqueues `huf.ai.knowledge.indexer.process_knowledge_input`
   — nothing else to call.
3. Poll the doc's `status`: `Pending → Processing → Indexed` (with
   `chunks_created > 0`) or `Error` (read `error_message`).
4. `Knowledge Source.status` follows: `Pending → Indexing → Ready` (or
   `Error`). Readiness for retrieval = source `Ready` **plus** a successful
   search probe (§7). A status alone is not retrieval proof.
5. Single-file dedup: `check_duplicate()` throws on a `source_hash`
   collision — a duplicate submit is an error, not a skip.

## 4. Bulk flow (frozen V1 contract)

All of `huf/ai/knowledge/bulk_api.py` is whitelisted.

### Submit
`submit_files(knowledge_source, files)` where `files` is a list (or JSON
string) of entries:

```json
{"file": "<File docname or file_url>", "external_key": "hr/handbook.pdf", "checksum": "<optional sha256 hex>"}
```

- `external_key` is required, ≤ 255 chars, and is the idempotency key
  together with the source.
- Cap: `huf_bulk_max_files` site config, default **1000**.
- Response (200):
  `{"ingestion": "ING-00001", "status": "Queued", "total_items": N, "duplicates_in_request": n, "rejected": [{"index": i, "reason": "..."}]}`
- `rejected[]` entries were never accepted (bad entry shape, file missing or
  unreadable). Fix the cause for those entries and resubmit them; the
  accepted part already has an `ING-*` handle.
- Refuses the whole request while any `Queued|Running` ingestion exists for
  the source — **one lane per source**.

### Poll
`get_ingestion_status(ingestion, include_items=1, item_status=None, limit=50, start=0)`:

```json
{"ingestion": {"name": "...", "status": "Running", "total_items": N, ...},
 "counts": {"pending": n, "processing": n, "indexed": n, "error": n, "skipped": n, "total": N},
 "progress": 0.0..1.0, "chunks_written": n,
 "items": [{"name", "external_key", "file_name", "status", "chunks_created", "attempts", "error_message", "skip_reason"}]}
```

Header statuses: `Queued | Running | Completed | Completed with Errors | Failed | Cancelled`.
Item statuses: `Pending | Processing | Indexed | Error | Skipped` (`skip_reason`:
`Duplicate | Unchanged | No Text | Too Large | Unsupported`).

**"Retrivable" is NOT a status.** Never tell the user content is retrievable
from counts alone — run one `knowledge_search` probe per acceptance run (§7).

### Retry / cancel / list
- `retry_ingestion(ingestion, only_failed=1)`: resets `Error` items to
  `Pending` and re-enqueues the runner (with `only_failed=0`, `Skipped/No
  Text` too). Refuses while `Running`.
- `cancel_ingestion(ingestion)`: header → `Cancelled`; the runner checks at
  each slice boundary.
- `list_ingestions(knowledge_source=None, limit=20)`: find prior batches.

### Idempotency rules (cite these to the user)
Key = `(knowledge_source, external_key)`:
1. Duplicate `external_key` in one request → deduped at submit (last wins),
   reported in `duplicates_in_request`.
2. Existing row, `Indexed` + same `checksum` → `Skipped / Unchanged` (no
   re-index).
3. Existing row, `Indexed` + different checksum → same row reset to
   `Pending` (re-index; old chunks deleted by `input_id` first).
4. Existing row, `Error` → reset to `Pending` (safe retry; rows are reused,
   never duplicated).
5. `Pending`/`Processing` rows are left alone and count as accepted
   (idempotent replay).
6. Identical `checksum` twice within one ingestion → `Skipped / Duplicate`.

## 5. Monitor processing like an operator

- Serial per source, roughly **1 doc per 3–10 s** → 1,000 docs ≈ 1–3 h.
  Say this up front; don't poll every second.
- Poll `get_ingestion_status(..., include_items=0)` on a sane interval
  (10–30 s), then `include_items=1` filtered by `item_status="Error"` at the
  end.
- Scale by **sharding across multiple Knowledge Sources** (each source is
  one lane); never by re-submitting the same source.

## 6. Failure diagnosis & recovery

| Symptom | Meaning | Action |
|---|---|---|
| Item `Error`: "Python's sqlite3 module does not support loadable extensions" | sqlite_hybrid backend missing its native deps | Install `pysqlite3` (source build on arm64) + `sqlite-vec` loadable extension, then `retry_ingestion` |
| hnsw "column cannot have more than 2000 dimensions" in logs, ingestion continues | Postgres refuses the ANN index above 2000 dims (e.g. 3072-d Gemini) | Non-fatal: search still works without the ANN index; or lower `vector_dimension`/model |
| Item `Error` with a per-item message | Transient/model/parse failure | Read `error_message`, fix the cause, `retry_ingestion(ingestion, only_failed=1)` |
| Stuck `Processing`, runner dead | Worker died mid-slice | Self-heals: the stalled-ingestion cron `recover_stalled_ingestions()` resets stale `Processing` → `Pending` and re-enqueues; give it a minute before intervening |
| Item `Skipped / No Text` | 0 chunks extracted (e.g. scanned PDF) | Not an error; needs OCR upstream — single-file re-ingest after OCR, or skip |
| `rejected[]` at submit | Bad entry / missing File doc | Fix the entry, resubmit only those entries |
| Whole submit throws "already queued or running" | One-lane rule | Wait for `get_ingestion_status` to show a terminal header status, then resubmit |

## 7. Validate retrieval with provenance (per target)

Always finish with a **real** search through
`huf.ai.knowledge.retriever.knowledge_search(query, knowledge_source, top_k)`,
returning `{text, title, score, chunk_id, source, metadata{input_id, ...}}`.

- **Vector backends** (`sqlite_vec`, `sqlite_hybrid`, `chroma`, `pgvector`,
  `zvec`, `weaviate`, `faiss`, `pinecone`, `redis`): semantic query with an
  exact token you know is in the doc; require the returned `text` to contain
  the exact token **and** `metadata.input_id` to equal the ingested
  `Knowledge Input` name. That pair is the provenance proof.
- **`sqlite_fts`**: known-term keyword search (same token rule; exact-term
  match is expected).
- **Table-style targets** (e.g. Huf Data Table): prove readiness with a
  record/key lookup, not a semantic query.
- Negative control: a nonsense query must not return the token.

## 8. Extending to a new backend

Before the skill treats a `knowledge_type` as supported, a new backend must
provide ALL of:

1. **Registry key** — the shipping app declares
   `huf_knowledge_backends = {"<key>": "dotted.path.ToBackend"}` in its
   `hooks.py` (hook keys cannot shadow HUF built-ins).
2. **`KnowledgeBackend` subclass** (from `huf.ai.knowledge.backends`)
   implementing `initialize(knowledge_source, config)`, `add_chunks(chunks)`
   → int, `delete_chunks(input_id)` → int, `search(query, top_k, filters)`
   → list[ChunkResult], `clear()`, `get_stats() → dict`.
3. **Knowledge Source option** — `knowledge_type` must offer the new key so
   a source can select it.
4. **`_build_backend_config` support** (in `huf/ai/knowledge/indexer.py`) —
   if the backend needs embedding config, its key must be in the vector
   list there; backend-specific connection settings need a branch.
5. **Verification** — one end-to-end ingest + `knowledge_search` probe with
   `metadata.input_id` provenance before declaring it usable.

Until all five exist, report the target as "not yet supported" instead of
guessing.
