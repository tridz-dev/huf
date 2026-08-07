# Bulk Ingestion — Detailed Execution Plan (V1: Upload/Directory/SFTP + S3-as-Integration)

Companion to [`HUF_BULK_INGESTION_PLAN.md`](HUF_BULK_INGESTION_PLAN.md) (the high-level architecture). This document is the file-by-file build order. It covers three things end to end:

1. **S3 as a first-class HUF Integration** — so any agent can call `s3_list_objects` / `s3_get_object` / `s3_search_objects` as a tool, exactly like `google_drive.py`, `jira.py`, etc. This is built first because bulk-ingestion's S3 source reuses its credentials and client code — one S3 setup powers both.
2. **Bulk Ingestion** itself (new `Ingestion Job` machinery + Upload/Directory/S3/SFTP sources), built on top of the existing single-document pipeline (`process_knowledge_input()`).
3. **SFTP as a bulk source** (Part D) — reusing the existing `SSH Connection` credential doctype, via a dedicated `paramiko` SFTP channel rather than the existing `run_ssh_command` exec tool (which caps output at 64-128KB and is unsuitable for file transfer — see Part D for why).

Every HUF integration already follows one fixed pattern (confirmed against `google_drive.py` and the Jira/Notion/ClickUp/Linear/Zendesk/Cal.com/Zoom tools added in `e253a2f9`): an `Integration Service` DocType record (seeded in `huf/install.py`) declares required credentials → a module in `huf/ai/tools/` reads them via `require_credential()` → functions are registered in `huf/ai/tools/_registry.py` → `ALL_INTEGRATION_TOOLS` is synced into `Agent Tool Function` records that agents can attach. The frontend's credential UI (`CredentialsTab.tsx`) is entirely schema-driven off `Integration Service.required_credentials`, so it needs **no new frontend code** for the integration itself.

---

## Part A — S3 as an Integration (agent tool)

### A1. Add the dependency
**File: `pyproject.toml`** (same section as the existing `llama-index-vector-stores-*` pins, line ~21-32)
- Add `boto3>=1.34.0`.
- No other backend depends on this yet — grep confirmed `boto3` doesn't currently appear anywhere in the repo.

### A2. Seed the Integration Service record
**File: `huf/install.py`** — function `register_integration_services()` (starts at line 1004; `services` list starts at line 1012, right after the existing `serpapi` entry at line 1112-1119)
- Add a new dict:
  ```python
  {
      "service_name": "aws_s3",
      "category": "Cloud",   # matches the existing enum on Integration Service (line ~10-19 of integration_service.json)
      "description": "Amazon S3 object storage — list, read, and search objects in a bucket",
      "required_credentials": [
          {"key": "access_key_id", "label": "AWS Access Key ID", "required": True},
          {"key": "secret_access_key", "label": "AWS Secret Access Key", "required": True},
          {"key": "region", "label": "AWS Region", "required": True},
      ],
  }
  ```
- Dependency: none (pure data, this function already runs idempotently on `after_install`/`after_migrate`).
- No DocType schema change needed — `Integration Service`, `Integration Settings`, `Integration Credential` are all generic already.

### A3. Write the tool module
**New file: `huf/ai/tools/s3.py`** — mirror `huf/ai/tools/google_drive.py`'s shape exactly (imports `json`, `frappe`, `require_credential`/`update_last_error` from `huf/ai/tools/credentials.py`), but use `boto3` instead of raw `requests`:
- `_get_client()` — builds a `boto3.client("s3", aws_access_key_id=..., aws_secret_access_key=..., region_name=...)` using `require_credential("aws_s3", "access_key_id")` etc. (same three-line pattern as `google_drive.py:11-16`).
- `handle_list_buckets(**kwargs)` — `client.list_buckets()`, return `{"success": True, "results": [...]}`.
- `handle_list_objects(**kwargs)` — params: `bucket` (required), `prefix`, `limit` (default 50); calls `client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=limit)`; returns key/size/last_modified/etag per object. **This same call, with pagination, becomes the bulk-ingestion scanner in Part B — do not duplicate the listing logic, factor it into a shared `list_objects_page(client, bucket, prefix, continuation_token, page_size)` helper in this file that both the agent tool and the bulk scanner import.**
- `handle_get_object_metadata(**kwargs)` — params: `bucket`, `key`; `client.head_object(...)`.
- `handle_search_objects(**kwargs)` — params: `bucket`, `query`; client-side substring filter over `list_objects_v2` pages (S3 has no server-side full-text search) — same shape as `google_drive.py`'s `handle_search_files`.
- Every handler wrapped in try/except calling `update_last_error("aws_s3", str(e))` on failure, matching the existing pattern.
- Dependency: A1 (boto3), A2 (credential lookups will raise `ValueError` until the service exists, same as any other tool before it's configured — acceptable, matches existing behavior).

### A4. Register the tools
**File: `huf/ai/tools/_registry.py`**
- Add near the other tool-list constants (pattern at line 705-730 for `GOOGLE_DRIVE_TOOLS`):
  ```python
  S3_TOOLS = [
      {"tool_name": "s3_list_buckets", "description": "List S3 buckets accessible with the configured AWS credentials.", "function_path": "huf.ai.tools.s3.handle_list_buckets", "category": "Cloud", "parameters": []},
      {"tool_name": "s3_list_objects", "description": "List objects in an S3 bucket, optionally filtered by prefix.", "function_path": "huf.ai.tools.s3.handle_list_objects", "category": "Cloud", "parameters": [_p("bucket", required=True), _p("prefix"), _p("limit", type="integer", description="Max objects (default 50)")]},
      {"tool_name": "s3_get_object_metadata", "description": "Get metadata (size, type, last modified) of an S3 object.", "function_path": "huf.ai.tools.s3.handle_get_object_metadata", "category": "Cloud", "parameters": [_p("bucket", required=True), _p("key", required=True)]},
      {"tool_name": "s3_search_objects", "description": "Search for objects in an S3 bucket by key/name substring.", "function_path": "huf.ai.tools.s3.handle_search_objects", "category": "Cloud", "parameters": [_p("bucket", required=True), _p("query", required=True)]},
  ]
  ```
- Append `+ _with_service(S3_TOOLS, "aws_s3")` to the `ALL_INTEGRATION_TOOLS` tuple (currently ends at line 1854-1860, alongside `GOOGLE_DRIVE_TOOLS`/`GOOGLE_MEET_TOOLS`).
- Dependency: A3 (function paths must resolve via `importlib` when `sync_discovered_tools()` validates them — see `huf/ai/tool_registry.py:413-430`).

### A5. Sync + verify
- On next `bench migrate` (or manually via `bench execute huf.ai.tool_registry.sync_discovered_tools`), the four `s3_*` tools become `Agent Tool Function` records under category "Cloud", attachable to any agent from the existing tool picker UI — **no frontend work required** for this part.
- Manual verification: attach `s3_list_objects` to a test agent, configure an `Integration Settings` record for `aws_s3` via the existing Integration Settings UI, ask the agent to list a bucket.

---

## Part B — Bulk Ingestion (Upload / Directory / S3 sources)

Builds on Part A only for the S3 source specifically; Upload and Directory sources have no integration dependency and can ship independently/first if you want to sequence V1 without S3.

### B1. New DocTypes (backend data model)
**New: `huf/huf/doctype/ingestion_job/ingestion_job.json` + `ingestion_job.py`**
- Fields: `knowledge_source` (Link), `source_kind` (Select: `Upload`/`Directory`/`S3`/`SFTP`/`Google Drive`), `status` (Select: `Queued`/`Scanning`/`Processing`/`Completed`/`Completed with Errors`/`Failed` — same enum style as `Flow Run`/`Agent Run`), `total_discovered`, `pending`, `processing`, `succeeded`, `failed`, `skipped` (all Int), `started_at`, `finished_at` (Datetime), `error_message` (Small Text), `sync_cursor` (Data — S3 continuation token / Drive pageToken / SFTP directory-queue snapshot, for resumable scans), plus source-kind-specific config fields (`s3_bucket`, `s3_prefix`, `directory_path`, `sftp_connection` (Link to `SSH Connection`), `sftp_root_path`) shown/hidden via `depends_on` like `Knowledge Source`'s existing `chroma_*`/`pgvector_*` sections do.
- `ingestion_job.py`: whitelisted methods `start()` (enqueues `scan_bulk_source`, see B3) and a `@frappe.whitelist()` `get_progress(name)` reader.

**New: `huf/huf/doctype/ingestion_job_item/ingestion_job_item.json` + `.py`** (child table, `istable: 1`)
- Fields: `external_path` (Data), `external_checksum` (Data), `size_bytes` (Int), `status` (Select: `Pending`/`Processing`/`Succeeded`/`Failed`/`Skipped`), `knowledge_input` (Link, set once created), `error_message` (Small Text).
- Dependency: none (new, independent DocTypes). Follows the exact status-enum convention already used by `Flow Run`/`Agent Run`/`Gateway Event`.

### B2. Extend existing DocTypes
**File: `huf/huf/doctype/knowledge_input/knowledge_input.json`** (+ `.py`)
- Add fields: `external_source_path` (Data), `external_checksum` (Data), `ingestion_job` (Link, optional — back-reference for traceability).
- **Do not reuse `source_hash`/`check_duplicate()` for bulk dedup** — that mechanism (`knowledge_input.py:30-56`) hashes the Frappe file URL/text/url string and hard-`frappe.throw()`s on collision, which is correct for the single-input create UI but wrong for bulk sync (re-scanning an unchanged S3 prefix must silently *skip*, not raise). The bulk scanner (B3) checks `external_checksum` against existing `Knowledge Input` rows for the same `knowledge_source` **before** calling `frappe.get_doc().insert()`, so `check_duplicate()` never even fires for legitimately-skipped items.
- Dependency: none.

**File: `huf/huf/doctype/knowledge_source/knowledge_source.json`**
- Add `source_kind` Select field (`Manual`/`Upload`/`Directory`/`S3`/`Google Drive`, default `Manual`) next to the existing `configuration_section` fields (line ~1-10 of the field list) — purely descriptive/filtering, the actual per-job config lives on `Ingestion Job` from B1.
- Dependency: none.

### B3. Bulk ingestion backend package
**New directory: `huf/ai/knowledge/bulk/`**
- `huf/ai/knowledge/bulk/__init__.py`
- `huf/ai/knowledge/bulk/scanners.py`
  - `scan_upload(job_name)` — reads an already-extracted temp directory (populated by B4's upload handler), walks it with `os.walk`, writes `Ingestion Job Item` rows in batches of ~200 (avoid one giant `.save()`).
  - `scan_directory(job_name)` — same walk, but rooted at `Ingestion Job.directory_path` on the bench filesystem (admin-only; validate path is under an allow-listed root to avoid path traversal).
  - `scan_s3(job_name)` — **imports `list_objects_page` from `huf/ai/tools/s3.py`** (the shared helper from A3) and `require_credential` from `credentials.py`, paginating via `continuation_token`, writing `sync_cursor` back onto the `Ingestion Job` after each page so a crashed scan resumes instead of restarting. This is the concrete reuse point requested: **the S3 credentials and boto3 client set up in Part A are the same ones used here** — no separate S3 credential UI for bulk ingestion.
  - `scan_sftp(job_name)` — see **Part D** below for the full spec; listed here only for placement (same file, same `Ingestion Job.status` lifecycle).
  - Each scanner sets `Ingestion Job.status = "Scanning"` → updates `total_discovered` incrementally → on completion enqueues `process_ingestion_batches(job_name)`.
- `huf/ai/knowledge/bulk/orchestrator.py`
  - `process_ingestion_batches(job_name)` — reads all `Pending` `Ingestion Job Item` rows for the job, splits into chunks of 20-100 (configurable), and for each chunk calls `frappe.enqueue(process_batch, queue="default", items=[...], job_id=f"bulk_batch_{job_name}_{i}")`.
  - `process_batch(job_name, item_names)` — for each item: skip if `external_checksum` matches an existing `Knowledge Input.external_checksum` under the same source; otherwise create/update a `Knowledge Input` doc (bypassing its `after_insert` auto-enqueue — call **`process_knowledge_input()` directly, in-process**, since we're already inside a worker) and update the `Ingestion Job Item` + `Ingestion Job` counters. On the last batch, set `Ingestion Job.status` to `Completed` or `Completed with Errors`.
  - Dependency: B1 (doctypes must exist), B2 (new fields), A3 (S3 scanner only).

### B4. Whitelisted API endpoints
**New file: `huf/ai/knowledge/bulk/api.py`** (all `@frappe.whitelist()`)
- `start_upload_import(knowledge_source, files)` — receives already-uploaded Frappe `File` docnames (frontend uploads via Frappe's standard multi-file upload first, same as any other Attach field), extracts any `.zip` among them to a private temp dir under `frappe.get_site_path("private", "files", "bulk_import", job_name)`, creates the `Ingestion Job` (`source_kind="Upload"`), enqueues `scan_upload`.
- `start_directory_import(knowledge_source, directory_path)` — creates `Ingestion Job` (`source_kind="Directory"`), enqueues `scan_directory`.
- `start_s3_import(knowledge_source, bucket, prefix)` — creates `Ingestion Job` (`source_kind="S3"`), enqueues `scan_s3`.
- `start_sftp_import(knowledge_source, sftp_connection, root_path)` — creates `Ingestion Job` (`source_kind="SFTP"`), enqueues `scan_sftp`. `sftp_connection` is an existing `SSH Connection` docname — no new credential form.
- `get_job_progress(job_name)` — thin wrapper returning the `Ingestion Job` counters + a page of `Ingestion Job Item` rows (for the error list in the UI).
- Dependency: B1, B3.

### B5. Backend tests
**New: `huf/ai/knowledge/tests/test_bulk_ingestion.py`** — mirrors existing test style in `huf/ai/knowledge/tests/`. Cover: scanner pagination/cursor resume, checksum skip logic, batch counter updates, S3 scanner using a mocked `boto3` client (same mocking style as `huf/ai/tests/test_*_tools.py` from the Jira/Notion commit).

---

## Part C — Frontend

### C1. API layer
**New file: `frontend/src/services/bulkIngestionApi.ts`** (sibling to `knowledgeApi.ts`, same fetch/error-handling conventions)
- `startUploadImport(knowledgeSource, fileUrls)`, `startDirectoryImport(knowledgeSource, path)`, `startS3Import(knowledgeSource, bucket, prefix)`, `getJobProgress(jobName)` — thin wrappers over B4's whitelisted methods.
- Dependency: B4 must exist (or stub during parallel FE/BE work).

**Edit: `frontend/src/types/integration.types.ts`** — no changes needed (S3 credentials are generic `Integration Credential` rows, already typed).
**New types file (or extend `frontend/src/types/knowledge.types.ts` if it exists, else add to `knowledgeApi.ts`)**: `IngestionJobDoc`, `IngestionJobItemDoc` matching B1's fields.

### C2. Bulk import UI
**New file: `frontend/src/components/knowledge/KnowledgeBulkImportModal.tsx`** — built directly on the existing template `frontend/src/components/data-table/BulkImportModal.tsx` (drag-drop, upload progress, 2s-interval polling with a `TERMINAL_STATUSES` set, error summary list). Differences from the CSV template:
- A source-kind picker (Upload / Directory / S3 / SFTP) as a first step — Directory, S3, and SFTP show a small config form instead of a dropzone (path input; bucket+prefix inputs; SFTP connection dropdown + root path input — the SFTP dropdown lists existing `SSH Connection` records via a simple Link-field-style fetch, no new credential form). Google Drive is out of scope for V1 per the phasing in the high-level plan, so the picker only offers Upload/Directory/S3/SFTP for now, with the component structured so a fifth option is a one-line addition later.
- On submit, calls the matching `bulkIngestionApi.ts` function instead of the CSV import endpoint, then polls `getJobProgress` and renders counts (`succeeded/failed/skipped/pending`) using the existing `frontend/src/components/ui/progress.tsx` bar plus a scrollable error list sourced from `Ingestion Job Item` rows with `status="Failed"`.
- Dependency: C1.

### C3. Wire the entry point
**Edit: `frontend/src/pages/KnowledgeSourcesPage.tsx`** — add a "Bulk Import" button next to the existing per-source actions, opening `KnowledgeBulkImportModal` scoped to that `Knowledge Source`.
**Edit: `frontend/src/pages/KnowledgeSourceFormPage.tsx`** — optionally surface the same entry point from within a source's detail/status tab (`StatusTab.tsx`) so users can bulk-import into a source they're already configuring, without leaving the page.
- Dependency: C2.

### C4. S3 credential UI
No new frontend code — once A2 seeds the `aws_s3` Integration Service, it appears automatically in `ServiceCatalogModal.tsx` and gets a generic credential form via `CredentialsTab.tsx` (schema-driven off `required_credentials`), exactly like every other integration. Verify this renders correctly (3 fields: access key id / secret access key / region) as a manual QA step, not a code change.

---

## Part D — SFTP as a bulk source

**Why not reuse the existing SSH tool as-is:** `huf/ai/tools/ssh_execution.py`'s `run_ssh_command` is a one-shot remote **exec** tool — no PTY, per-call human-approval workflow, and output hard-capped at `DEFAULT_STDOUT_MAX_BYTES = 65536` / `DEFAULT_COMBINED_OUTPUT_MAX_BYTES = 131072` (`ssh_execution.py:33-38`). Piping `scp`/`cat` through it would silently truncate almost any real document and would fire an approval prompt per file, which doesn't work for a job touching thousands of files. It is out of scope to change.

**What *is* reusable:** the `SSH Connection` DocType (`huf/huf/doctype/ssh_connection/ssh_connection.json`) already stores `host`, `port`, `username`, `auth_method` (`Password`/`Private Key`), `password`/`private_key`/`private_key_passphrase`, and strict pinned host-key verification (`host_key_fingerprint`, `host_key_type`) — solid, already-encrypted credential storage. And `paramiko` is already a dependency (used by `ssh_execution.py`). `paramiko.SSHClient.open_sftp()` opens a **separate channel** from the exec/output-capture path — no output cap, streams file bytes directly.

### D1. SFTP client helper
**New file: `huf/ai/knowledge/bulk/sftp_client.py`**
- `_connect(ssh_connection_name)` — loads the `SSH Connection` doc, builds a `paramiko.SSHClient()`, and reuses the **exact same host-key verification and private-key-loading logic already written** in `ssh_execution.py` (`_load_private_key()` at line ~93-106, `_fingerprint_for_key()` at line ~89-91) — import and call those functions directly rather than re-implementing key parsing or host-key pinning. Connects with `password` or the loaded private key per `auth_method`. Returns an open `SFTPClient` (`ssh_client.open_sftp()`).
- `list_dir_recursive(sftp, root_path, dir_queue)` — one page of work: pops one directory off `dir_queue` (a plain list), calls `sftp.listdir_attr(path)`, splits entries into subdirectories (pushed back onto `dir_queue`) and files (returned, each as `{path, size, mtime}` — `mtime` + `size` stand in for a checksum since SFTP/SSH has no native content hash equivalent to S3's ETag). Caller persists the returned `dir_queue` as JSON into `Ingestion Job.sync_cursor` after each page, so a crashed/paused scan resumes from the same directory frontier instead of restarting.
- `read_file(sftp, path, local_tmp_path)` — `sftp.get(path, local_tmp_path)`, used by the batch worker to stream a remote file to a local temp path before handing it to the existing extractors (which expect a local file, same as the Upload/Directory sources).
- Dependency: none new (paramiko already installed); imports from `ssh_execution.py` only the two helper functions named above, not the whole exec/approval flow.

### D2. Scanner
**Add to `huf/ai/knowledge/bulk/scanners.py`: `scan_sftp(job_name)`**
- Reads `Ingestion Job.sftp_connection` and `sftp_root_path`; if `sync_cursor` is already set (resume case), parses it back into the starting `dir_queue`, otherwise starts with `[sftp_root_path]`.
- Calls `sftp_client._connect()`, then loops `list_dir_recursive()` popping one directory per iteration, writing `Ingestion Job Item` rows in batches of ~200 (`external_path` = remote path, `external_checksum` = `f"{size}:{mtime}"`), updating `total_discovered` and persisting `sync_cursor` after each batch — same shape as `scan_s3`'s pagination loop.
- On an empty `dir_queue`, closes the SFTP session, clears `sync_cursor`, and enqueues `process_ingestion_batches(job_name)` exactly like the other scanners.

### D3. Batch processing
**`process_batch()` in `huf/ai/knowledge/bulk/orchestrator.py`** needs one branch for `source_kind == "SFTP"`: instead of reading a local path directly (Upload/Directory) or calling boto3 (S3), it opens one SFTP session per batch (not per file — reuse the connection across the batch for throughput), calls `sftp_client.read_file()` into a private temp path per item, then hands off to the same `process_knowledge_input()` call used by every other source. This is the one place SFTP needs orchestrator-level branching; everything downstream (extraction, chunking, embedding, backend write) is identical across all four source kinds.

### D4. DocType/API/UI touch points
Already covered inline above — `source_kind` enum (B1) includes `SFTP`, `Ingestion Job` carries `sftp_connection`/`sftp_root_path` (B1), `bulk/api.py` gets `start_sftp_import` (B4), and the frontend picker (C2) gets a fourth option that reuses the existing `SSH Connection` list rather than a new credential form (no `Integration Service` needed for SFTP — it rides entirely on `SSH Connection`, which predates this feature).

### D5. Tests
**Add to `huf/ai/knowledge/tests/test_bulk_ingestion.py`**: mock `paramiko.SSHClient`/`SFTPClient` (same mocking approach as D1's dependency-free design makes this straightforward) to cover `list_dir_recursive` pagination/cursor resume and the size+mtime checksum-skip path.

---

## Build order (dependency-ordered)

1. **A1 → A2 → A3 → A4 → A5** (S3 integration, fully independent of bulk ingestion; ships and is useful on its own — agents can already use S3 as a tool once this lands).
2. **B1** (new DocTypes, now including `SFTP` in `source_kind` + `sftp_connection`/`sftp_root_path` fields) — no dependency on Part A.
3. **B2** (field additions to `Knowledge Input`/`Knowledge Source`) — depends on B1 existing so migrations apply cleanly together.
4. **D1** (`sftp_client.py`) — no dependency on A/B; only imports two helper functions from the existing `ssh_execution.py`.
5. **B3** `scanners.py` (Upload/Directory/S3/`scan_sftp` per D2) and `orchestrator.py` (per D3) — depends on B1, B2. `scan_s3` also depends on A3 (imports `list_objects_page`). `scan_sftp` also depends on D1.
6. **B4** (API endpoints, including `start_sftp_import`) — depends on B3.
7. **B5**/**D5** (backend tests) — depends on B3, B4, D1.
8. **C1** (frontend API layer) — can start in parallel with B3/B4 against a stubbed contract, wired for real once B4 lands.
9. **C2** (bulk import modal, 4-way source picker) — depends on C1.
10. **C3** (entry points in existing pages) — depends on C2.
11. **C4** (manual QA of auto-generated S3 credential UI) — depends on A2 only, can happen right after step 1.

**Suggested shipping slice for V1**: steps 1, 2, 3, 5 (Upload + Directory scanners only, skip `scan_s3`/`scan_sftp` internals), 6, 8, 9, 10 — i.e. ship Upload/Directory bulk import first, then land S3-as-integration and SFTP as fast-follows that slot into the same `Ingestion Job` machinery with zero changes to B1/B2/C2/C3.
