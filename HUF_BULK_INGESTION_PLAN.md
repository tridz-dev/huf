# Bulk Ingestion — High-Level Plan

## Why this matters

Today, HUF's knowledge system (`huf/ai/knowledge/`) only ingests one document at a time: a user creates a `Knowledge Input` (File / Text / URL), which enqueues `process_knowledge_input()`. There is no way to point HUF at a folder, a ZIP, an S3 prefix, or a Google Drive folder and have it ingest hundreds or thousands of documents. Without this, no real business with an existing document corpus (SharePoint exports, S3 buckets, Drive folders, HR/legal archives) can onboard onto HUF — they'd have to upload files one by one through a modal.

## Guiding principle: don't build a new ingestion engine

`process_knowledge_input()` (`huf/ai/knowledge/indexer.py:45`) is already a complete, correct, atomic ingestion worker: extract → chunk (LlamaIndex `SentenceSplitter`) → embed → write to the configured vector backend (Chroma / pgvector / Weaviate / Pinecone / FAISS / sqlite). It already runs behind Frappe's Redis-backed job queue (`frappe.enqueue`, `queue="default"`, `deduplicate=True`, `enqueue_after_commit=True`).

**Bulk ingestion is purely an orchestration layer on top of this existing worker.** We are not replacing it, not building a second ingestion path, and not hand-rolling document loading — LlamaIndex already ships the readers/connectors we'd need if we ever want them (`llama-index-readers-s3`, `llama-index-readers-google-drive`, `SimpleDirectoryReader`, etc.); `llama-index-core` is already pinned in `pyproject.toml`, so adding a reader is a dependency bump, not new infrastructure.

```
Bulk source (ZIP / folder / S3 prefix / Drive folder)
        │
        ▼
  Source scanner (lists files, one per row)
        │
        ▼
  Create N × Knowledge Input docs (Pending)
        │
        ▼
  Batch enqueue, 20-100 at a time
        │
        ▼
  Existing process_knowledge_input() worker  ◄── reused unchanged
        │
        ▼
  Vector backend (Chroma / pgvector / Weaviate / Pinecone / FAISS)
```

## What already exists in HUF that this can be built on

| Need | Existing building block | Reuse as-is? |
|---|---|---|
| Per-document ingestion | `process_knowledge_input()` — `huf/ai/knowledge/indexer.py:45` | Yes, unchanged |
| Per-document status | `Knowledge Input` doctype: `Pending → Processing → Indexed / Error` | Yes |
| Source-level status/stats | `Knowledge Source` doctype: `total_chunks`, `total_inputs`, `index_size_bytes` | Extend |
| Background job pattern | `frappe.enqueue(..., queue="default"/"long", deduplicate=True, job_id=..., enqueue_after_commit=True)` | Yes — same pattern |
| Job-with-progress DocType precedent | `Flow Run`, `Agent Run`, `Gateway Event` doctypes (`Queued/Running/Success/Failed` style status) | Copy the pattern for a new `Ingestion Job` doctype |
| File extraction (PDF/DOCX/XLSX/PPTX/HTML/MD/URL) | `huf/ai/knowledge/extractors/` | Yes, unchanged |
| Chunking | `chunkers/sentence.py` (LlamaIndex `SentenceSplitter`) | Yes, unchanged |
| Vector write | `backends/*.py` (`add_chunks`, `delete_chunks`, `get_stats`) | Yes, unchanged |
| Google Drive OAuth + file listing | `huf/ai/tools/google_drive.py` (already used by agent tools) | Reuse the auth/listing code as the Drive scanner |
| S3 | Nothing yet | New — but LlamaIndex has `llama-index-readers-s3` / plain `boto3` is fine too, listing is trivial |
| Multi-file upload UI + progress polling | `frontend/src/components/data-table/BulkImportModal.tsx` (CSV bulk import: drag-drop, upload progress, 2s polling, terminal-status detection, error summary) | **Direct template** — this is almost exactly the UX we need, just repointed at a new bulk-ingestion endpoint |
| Progress bar component | `frontend/src/components/ui/progress.tsx` (Radix) | Yes |
| Realtime job updates | `frontend/src/contexts/SocketContext.tsx`, `useChatSocket.tsx`, `frappe.publish_realtime` (used elsewhere, not yet for knowledge) | Reuse pattern |
| Existing single-input upload UI | `frontend/src/components/knowledge/KnowledgeInputsModal.tsx` | Keep for single-file case; bulk is a new sibling entry point |

**Gaps to fill (genuinely new code):**
1. No content-hash/checksum dedup — reprocessing today just deletes-and-reinserts by `input_id`. Incremental sync needs a real checksum (path + mtime/etag/hash) per external source.
2. No generic "bulk job" DocType — status today lives only on `Knowledge Input`/`Knowledge Source`, which is fine per-document but has no place to track "5,000 discovered, 3,200 succeeded, 40 failed, 1,760 pending."
3. No S3 or ZIP/folder scanning code exists at all.
4. No incremental/cursor-based listing for very large sources (millions of objects).

## Proposed data model (new)

1. **`Bulk Ingestion Source`** (or extend `Knowledge Source` with a `source_kind` field: `Manual | Upload | Directory | S3 | Google Drive`)
   - Connection config: bucket/prefix, folder path, Drive folder ID, credentials link (reuse `AI Provider`-style credential doc, or Drive's existing OAuth doc)
   - `sync_cursor` — resume point for incremental scans (S3 continuation token, Drive `pageToken`, or `last_synced_at` for directories)

2. **`Ingestion Job`** — modeled directly on `Flow Run` / `Agent Run`'s status pattern
   - `status`: `Queued → Scanning → Processing → Completed / Completed with Errors / Failed`
   - `total_discovered`, `pending`, `processing`, `succeeded`, `failed`, `skipped`
   - `knowledge_source` (link), `started_at`, `finished_at`
   - Child table `Ingestion Job Item`: one row per discovered file — `external_path`, `checksum`/`etag`, `knowledge_input` (link, created lazily), `status`, `error_message`

3. **`Knowledge Input`** gets two new fields: `external_source_path`, `content_checksum` — this is the whole incremental-sync mechanism: on re-scan, skip any item whose checksum matches what's already indexed.

## Processing flow

1. User configures a `Bulk Ingestion Source` (upload ZIP, pick a server directory, enter an S3 prefix, or authorize + pick a Drive folder) and hits "Import."
2. `frappe.enqueue(scan_bulk_source, queue="long", job_id=f"bulk_scan_{job}")` — scanner lists objects (streaming/paginated for S3 and Drive, not loading everything into memory), writes `Ingestion Job Item` rows in batches, updates `total_discovered` as it goes so the UI shows a live count even before processing starts.
3. Scanner enqueues processing batches of 20-100 items each (`queue="default"`, several jobs in parallel — Frappe's own worker pool handles concurrency, no new scheduler needed).
4. Each batch worker, for each item: skip if checksum unchanged; otherwise create/update a `Knowledge Input` doc and call `process_knowledge_input()` **directly in-process** (not re-enqueued) since we're already inside a background worker — avoids double-queueing overhead for bulk runs.
5. Batch worker updates the `Ingestion Job` counters (succeeded/failed/skipped) and, on the last batch, sets the job to a terminal status.
6. Frontend polls `Ingestion Job` status every ~2s (same pattern as `BulkImportModal.tsx`) or subscribes via `frappe.publish_realtime` (same pattern as chat's `SocketContext`) for live progress; on completion shows a summary with per-item errors pulled from `Ingestion Job Item`.

## Source-type specifics

- **Upload (ZIP / multi-file)**: simplest V1. Browser multi-file or ZIP upload → server extracts to a temp private-files location → each file becomes a `Knowledge Input` → straight into the existing pipeline. No external credentials needed. Ship this first.
- **Server directory**: admin-only, points at a path the bench process can read; walk it with a generator, don't load the full listing into memory for huge trees.
- **S3**: list via `boto3` `list_objects_v2` (paginated) or `llama-index-readers-s3`; store a continuation token as the sync cursor; stream each object to a worker rather than downloading the whole bucket up front. Credentials stored the same way other secrets are (existing credential-storage convention, not a new one).
- **Google Drive**: reuse `huf/ai/tools/google_drive.py`'s OAuth + listing entirely; add folder-level recursive listing and a `pageToken` cursor.

## Phasing

1. **V1 — Upload/ZIP + directory sources.** New `Ingestion Job` + `Ingestion Job Item` doctypes, batch orchestration, reuse `BulkImportModal.tsx` as the frontend template, reuse `process_knowledge_input()` untouched. This alone unblocks most business onboarding (people already have files, not necessarily live S3/Drive feeds).
2. **V2 — Checksum-based incremental sync** for whatever source types exist so far (re-running an import only touches changed/new files).
3. **V3 — S3 connector** (paginated listing + cursor, streamed processing, no full-bucket download).
4. **V4 — Google Drive connector** (extend existing OAuth integration with recursive folder listing + cursor).
5. **V5 (optional)** — scheduled/periodic re-sync per source using Frappe's existing scheduler hooks, for sources that should stay continuously in sync.

## Explicitly out of scope for V1

- Downloading entire buckets/folders before processing (always stream/paginate).
- A generic "connector framework" beyond what's needed for these four source kinds — don't build a pluggable-connector abstraction speculatively; add the next source type's scanner function when it's actually needed.
- Real content-hash dedup for the manual-upload path (checksums matter most for repeat S3/Drive syncs, less for one-off uploads).
