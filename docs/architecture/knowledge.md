# Knowledge System

HUF's Knowledge system is a pluggable RAG (retrieval-augmented generation) layer: `Knowledge Source` documents own a chunked, indexed copy of ingested content, and agents pull from it either automatically (`Mandatory` sources injected pre-execution) or on demand (`Optional` sources via a `knowledge_search` tool). Contrary to the old AGENTS.md description, storage is **not** SQLite FTS5-only — it is a backend abstraction with nine pluggable implementations, of which SQLite FTS5 is just the default keyword-search option.

## What changed since the last write-up

The previous `AGENTS.md` (`### Knowledge System Architecture`, formerly around line 1342) described the system as hard-wired to a single SQLite FTS5 backend. That is now stale:

- **Multiple backends exist**, not one. `huf/ai/knowledge/backends/__init__.py:18-28` registers nine built-in backend types: `sqlite_fts`, `sqlite_vec`, `sqlite_hybrid`, `chroma`, `pgvector`, `zvec`, `weaviate`, `faiss`, `pinecone` — keyword (FTS5), vector, and hybrid (RRF) search are all first-class options, not just BM25/FTS5.
- **Third-party apps can register additional backends** via a `huf_knowledge_backends` hook (`huf/ai/knowledge/backends/__init__.py:96-168`) — the backend registry was not previously mentioned as extensible.
- **An embedding module exists** (`huf/ai/knowledge/embedding.py`) providing model-agnostic embeddings via LiteLLM for every vector/hybrid backend — not documented at all previously.
- `context_builder.py` and `tool.py` also pull in **skill-attached knowledge** (`huf.ai.skills.loader.get_mandatory_skill_knowledge` / `get_agent_skills`), via a `Skill Knowledge` child doctype that mirrors `Agent Knowledge`. The old doc only mentioned `agent.agent_knowledge`.
- A **mandatory-knowledge failure now aborts the agent run** rather than degrading silently — `huf/ai/agent_integration.py:1406-1434` catches failures building knowledge context and marks the `Agent Run` `Failed` instead of proceeding.
- The directory listing in the old doc omitted `embedding.py`, `hooks.py`, and `maintenance.py`, and it did not mention that `chunkers/` falls back to a simple non-LlamaIndex chunker when `llama-index-core` is unavailable.

## Directory structure (`huf/ai/knowledge/`)

| Path | Role |
|---|---|
| `backends/` | `KnowledgeBackend` ABC + registry (`__init__.py`) plus one module per backend: `sqlite_fts.py`, `sqlite_vec_backend.py`, `sqlite_hybrid.py`, `chroma_backend.py`, `pgvector_backend.py`, `zvec_backend.py`, `weaviate_backend.py`, `faiss_backend.py`, `pinecone_backend.py`, `redis_backend.py`, plus shared `llamaindex_base.py` |
| `extractors/` | Text extraction per input type: `text.py`, `docx.py`, `html.py`, `pdf.py`, `pptx.py`, `xlsx.py`, `url.py` |
| `chunkers/sentence.py` | `chunk_text()` — LlamaIndex `SentenceSplitter` with a manual fallback chunker |
| `embedding.py` | `get_embedding` / `get_embeddings` — LiteLLM-backed, model-agnostic, batched |
| `indexer.py` | Ingestion pipeline: extraction → chunking → backend write |
| `retriever.py` | `knowledge_search()` — the retrieval contract used by both context injection and the agent tool |
| `context_builder.py` | Assembles mandatory-knowledge context text for the system/user prompt |
| `tool.py` | `knowledge_search` / `get_knowledge_sources` tool definitions and handlers for `Optional` sources |
| `hooks.py` | Doctype lifecycle hooks: create/update/delete for `Knowledge Source` and `Knowledge Input` |
| `maintenance.py` | Scheduled cleanup: orphaned SQLite file removal, `PRAGMA optimize` / `VACUUM` |

## DocTypes

`Knowledge Source`, `Knowledge Input`, `Agent Knowledge`, and `Skill Knowledge` carry the persisted state. Full field tables are generated in `docs/reference/doctypes.generated.md` — this doc covers only behavior. Notable fields:

- `Knowledge Source.knowledge_type` (`huf/huf/doctype/knowledge_source/knowledge_source.json:85-89`) — Select field, one of the nine backend type strings above; this is the value passed to `get_backend()`.
- `Knowledge Source.scope` (`Site\nWorkspace\nAgent\nGlobal`, default `Site`) — present on the doctype but **not read anywhere in `huf/ai/knowledge/*.py` or `agent_integration.py`**; appears to be reserved/unused at present.
- `Knowledge Source.chunk_size` / `chunk_overlap` — defaults 512 / 50, consumed by `indexer.py:109-113`.
- `Knowledge Source.advanced_config` — free-form JSON merged into the backend config (`indexer.py:63-74`), letting each backend expose extra tunables (e.g. FTS tokenizer, BM25 weights — see below).
- `Agent Knowledge` / `Skill Knowledge` (child tables) — `knowledge_source`, `mode` (`Mandatory`/`Optional`), `priority`, `max_chunks`, `token_budget`. `Agent Knowledge` additionally has a free `priority` used to sort mandatory sources (`retriever.py:154`); `Skill Knowledge` does not.

## 1. Ingestion pipeline (`indexer.py`)

`process_knowledge_input(knowledge_input, skip_lock=False)` runs as a background job per `Knowledge Input`:

1. **Locking** — acquires a Redis lock `knowledge_index_{source_name}` (`frappe.cache().set(..., nx=True)`, 300s TTL) so only one ingestion runs per source at a time (`indexer.py:94-96`).
2. **Extraction** — `_extract_text()` dispatches on `input_type`: `Text` returns the pasted string directly; `File` resolves the Frappe `File` doc and picks an extractor via `TextExtractor.get_extractor(doc.file_type)`; `URL` does a synchronous `requests.get` (30s timeout) then runs it through the HTML extractor (`indexer.py:275-303`).
3. **Chunking** — `chunk_text(text, chunk_size, chunk_overlap)` (default 512/50) via LlamaIndex `SentenceSplitter`, with a manual sentence/paragraph-boundary fallback if `llama_index.core` import fails (`chunkers/sentence.py:16-90`).
4. **Backend write** — resolves the configured backend class via `get_backend(source.knowledge_type)`, calls `initialize()` then `delete_chunks(doc.name)` (clears any prior chunks for this input, so re-processing is idempotent) followed by `add_chunks()` (`indexer.py:131-140`).
5. **Status bookkeeping** — updates `Knowledge Input.status` (`Pending → Processing → Indexed`/`Error`) and `Knowledge Source.status` (`Pending → Indexing/Rebuilding → Ready`/`Error`), plus `update_source_stats()` pulling `chunk_count` / `input_count` / `size_bytes` from `backend.get_stats()` (`indexer.py:141-158, 306-315`).

`rebuild_knowledge_index(knowledge_source)` takes a longer (600s) exclusive lock, sets status to `Rebuilding`, calls `backend.clear()`, resets every `Knowledge Input` row to `Pending`, then reprocesses each input in turn via `process_knowledge_input(..., skip_lock=True)` (`indexer.py:194-256`).

`_build_backend_config(source)` (`indexer.py:16-75`) is the shared config builder both ingestion and retrieval use: it always includes `chunk_size`/`chunk_overlap`; adds `embedding_model` / `vector_dimension` / `embedding_provider` for any vector-capable type (`sqlite_vec`, `chroma`, `pgvector`, `redis`, `zvec`, `weaviate`, `faiss`, `pinecone`); adds Chroma-specific (`host`/`port`/`ssl` or `persist_directory`) or pgvector-specific (`table_name`, `distance_metric`, `index_type`, connection fields) config depending on `knowledge_type`; and finally merges `source.advanced_config` JSON on top (core fields win on key collision).

## 2. Storage backends (`backends/`)

All backends implement the `KnowledgeBackend` ABC (`backends/__init__.py:52-93`): `initialize`, `add_chunks`, `delete_chunks`, `search`, `clear`, `get_stats`, plus an optional `get_advanced_config_schema()` classmethod that drives the "Advanced Config" UI for backend-specific tunables.

The registry (`_BUILTIN_BACKENDS`, `backends/__init__.py:18-28`) merges built-ins with any `huf_knowledge_backends` hook contributions from installed apps (`_discover_backends`, `backends/__init__.py:96-130`); a hook cannot override a built-in type name, and duplicate hook registrations keep the first one, both logged as warnings. `get_backend(backend_type)` resolves and validates the class (`backends/__init__.py:178-195`).

### `sqlite_fts` — the default keyword backend (`backends/sqlite_fts.py`)

This is the backend the old doc described in isolation, and its description there is largely still accurate:

- One SQLite file per source at `{private files}/knowledge/{scrubbed_source_name}.sqlite3` (`sqlite_fts.py:145-152`).
- Schema: a `chunks` table plus an FTS5 virtual table `chunks_fts` (`content=chunks`) kept in sync via `AFTER INSERT/UPDATE/DELETE` triggers (`sqlite_fts.py:19-58`).
- Tokenizer is configurable per source via `advanced_config.fts_tokenizer`, one of `porter unicode61` (default), `unicode61`, `ascii`, `porter ascii`, `trigram` — but FTS5 fixes the tokenizer at table-creation time, so changing it only affects newly created sources, not existing ones (`sqlite_fts.py:61-126`).
- Pragmas: WAL journal mode, `synchronous=NORMAL`, 64MB cache, in-memory temp store (`sqlite_fts.py:128-133`).
- `search()` ranks with SQLite's built-in `bm25()` function, with configurable per-column weights `fts_bm25_text_weight` (default 1.0) and `fts_bm25_title_weight` (default 0.75) from `advanced_config` (`sqlite_fts.py:226-276`). Metadata filters are validated against `^[A-Za-z0-9_]+$` (`validate_filter_key`, `backends/__init__.py:30-37`) before being interpolated into a `json_extract()` path, so arbitrary keys can't inject SQL.
- Query sanitization (`_escape_fts_query`, `sqlite_fts.py:300-312`) strips FTS5 special characters and re-joins multi-word queries with `OR`, so a multi-term query is an OR-of-terms search rather than a phrase match — a meaningful behavior detail for anyone tuning search relevance.

### Vector and hybrid backends

`sqlite_vec`, `chroma`, `pgvector`, `redis`, `zvec`, `weaviate`, `faiss`, `pinecone` store dense embeddings computed via `embedding.py`'s LiteLLM wrapper (`get_embedding`/`get_embeddings`, model-agnostic — OpenAI, Gemini, Cohere, HuggingFace, Ollama, or any LiteLLM-supported provider). `sqlite_hybrid` combines keyword and vector search with Reciprocal Rank Fusion (RRF), per the module docstring in `backends/__init__.py:5`. `llamaindex_base.py` provides shared scaffolding several of these build on. This doc does not enumerate each backend's storage details — see the individual modules under `backends/` and `backends/BACKEND_CONTRACT.md` for the interface contract new backends must satisfy.

### File cleanup

`hooks.py:on_knowledge_source_deleted` removes the source's `.sqlite3` (plus `-wal`/`-shm`) files on delete — this cleanup is SQLite-specific and does not reach into non-file backends. `maintenance.py:cleanup_orphaned_files` (daily scheduled job, `huf/hooks.py:248`) removes `.sqlite3` files under `{private files}/knowledge/` that no longer have a matching `Knowledge Source`. `maintenance.py:optimize_indexes` (also daily) runs `PRAGMA optimize` + `VACUUM` against `Knowledge Source.sqlite_file_path` for sources with `status=Ready, disabled=0` — note this field is only populated for SQLite-backed sources, so vector-backend sources are silently skipped by this job rather than erroring.

## 3. Retrieval (`retriever.py`)

`knowledge_search(query, knowledge_source=None, knowledge_sources=None, top_k=5, filters=None, ignore_permissions=False)` (`retriever.py:43-132`) is the single retrieval contract used everywhere — both mandatory-context injection and the `knowledge_search` tool call into it:

- Requires either `knowledge_source` or `knowledge_sources`.
- Per source: skips if `status != "Ready"`, skips if `disabled`, and (unless `ignore_permissions`) skips if the caller lacks `read` on the `Knowledge Source` doctype record.
- Initializes the source's backend fresh on every call (via `get_backend` + `_build_backend_config`) and calls `backend.search()`.
- Results from all requested sources are pooled and globally re-sorted by `score` descending, then truncated to `top_k` total — `top_k` is a global cap across sources, not per-source.
- Exceptions per source are caught, logged (`frappe.log_error`), and that source is skipped rather than failing the whole call.

`get_search_diagnostics(source_names)` (`retriever.py:11-40`) explains *why* a source returned nothing (not-ready status, disabled, missing permission, or "index may be empty") — surfaced by the `knowledge_search` tool when results come back empty, to give the agent (and a human debugging it) something actionable instead of a bare "no results."

`get_mandatory_knowledge(agent_name)` / `get_optional_knowledge(agent_name)` (`retriever.py:135-177`) read `agent.agent_knowledge` child rows filtered by `mode`, with mandatory sources sorted by `priority` descending.

## 4. Agent integration

### Mandatory knowledge (always injected)

`build_knowledge_context(agent_name, user_query, max_tokens=4000)` in `context_builder.py:9-102`:

1. Collects mandatory sources from `get_mandatory_knowledge(agent_name)` **plus** mandatory sources contributed by any skills attached to the agent, via `huf.ai.skills.loader.get_mandatory_skill_knowledge(agent_name)` (best-effort — import/lookup failures are swallowed).
2. For each source, calls `knowledge_search(..., ignore_permissions=True)` — the agent-to-source linkage itself is treated as the authorization, bypassing the caller's own Frappe permissions.
3. Greedily packs results into `context_text` under a `## Relevant Knowledge` heading, one `### {title}` block per chunk, stopping once the running token estimate (chars // 4) would exceed `max_tokens`.
4. Returns `context_text`, `sources_used`, `chunks_used` (each with `chunk_id`, `source`, `title`).

`inject_knowledge_context(prompt, knowledge_context)` prepends the context block to the outgoing prompt, separated by `---`.

Call site: `huf/ai/agent_integration.py:1406-1434`, inside `run_agent_sync`. `max_tokens` comes from `agent_doc.max_knowledge_tokens` (default 4000). **Important behavior change from the old doc**: if `build_knowledge_context` raises any of `ImportError, ValueError, TypeError, KeyError, AttributeError, RuntimeError`, or a Frappe `DoesNotExistError`/`ValidationError`/`PermissionError`, the whole agent run is aborted — `run_doc.status` is set to `Failed` and the method returns early — rather than the agent proceeding without knowledge. When injection does succeed, `Agent Run.knowledge_sources_used` and `Agent Run.chunks_injected` are recorded (`agent_integration.py:1510-1519`).

### Optional knowledge (agent-queried on demand)

`tool.py` builds two tool definitions when an agent has any linked knowledge (agent-level `Agent Knowledge` rows or skill-level `Skill Knowledge` rows — `_get_allowed_knowledge_sources`, `tool.py:9-36`):

- **`knowledge_search`** (`create_knowledge_search_tool` / `handle_knowledge_search`, `tool.py:63-201`) — parameters `query` (required), `knowledge_source` (optional, must be one of the allowed sources), `top_k`, `filters` (JSON, parsed if passed as a string). Unlike mandatory injection, this path does **not** pass `ignore_permissions` — the current user's own read permission on the `Knowledge Source` is still enforced. Results are formatted as numbered `## Result N` blocks with title, source, score, and text. On an empty result set it appends the first `get_search_diagnostics()` reason.
- **`get_knowledge_sources`** (`create_get_knowledge_sources_tool` / `handle_get_knowledge_sources`, `tool.py:203-245`) — lists each allowed source with its mode, priority, and (for skill-attached sources) which skill contributed it.

Both tools are attached to the agent's tool list in `agent_integration.py:167-198` (`AgentManager` construction), conditionally — if `create_knowledge_search_tool`/`create_get_knowledge_sources_tool` return `None` (no linked sources), the tool is simply not added, so agents without knowledge sources see no knowledge-related tools at all.

## Extractors (`extractors/`)

`TextExtractor.get_extractor(file_type)` (`huf/ai/knowledge/extractors/__init__.py`) dispatches by file type/extension to one of: `text.py` (plain text), `docx.py`, `html.py`, `pdf.py`, `pptx.py`, `xlsx.py`. `url.py`'s extractor is used for the `URL` input type — `indexer.py` fetches the URL itself with `requests.get` and hands the raw HTML to the HTML extractor's `extract_from_content()` rather than calling a dedicated URL extractor class directly. Each extractor returns an `ExtractedText` (`text`, `title`, `character_count`, `metadata`) that feeds directly into chunking.

## End-to-end walkthrough

1. A user creates a `Knowledge Source` (`knowledge_type=sqlite_fts`) and adds a `Knowledge Input` (a PDF upload). `on_knowledge_source_created` (`hooks.py:8-18`) eagerly initializes the backend so the SQLite file/schema exists even before any input is processed.
2. Uploading the input enqueues `process_knowledge_input`. It extracts text via `PDFExtractor`, chunks it (512/50 defaults), and writes chunks through `SQLiteFTSBackend.add_chunks`. Source status flips `Pending → Indexing → Ready`.
3. An `Agent` links this source via an `Agent Knowledge` row with `mode=Mandatory`. On the next `run_agent_sync`, `build_knowledge_context` runs `knowledge_search(..., ignore_permissions=True)` against it, and the top chunks (bounded by `max_knowledge_tokens`) are prepended to the prompt.
4. A second agent links the same source as `Optional` instead. It gets a `knowledge_search` tool and calls it mid-conversation when it decides it needs the information; that call goes through the caller's normal Frappe permissions on the `Knowledge Source`, unlike the mandatory path.
5. If the source's `knowledge_type` is changed to `chroma` or `pgvector` and `Rebuild Index` is run, `rebuild_knowledge_index` clears the old backend, resets every input to `Pending`, and reprocesses them — this time computing embeddings via `embedding.py`'s LiteLLM wrapper instead of writing directly into FTS5.

## See also

`docs/reference/doctypes.generated.md` for the full `Knowledge Source`, `Knowledge Input`, `Agent Knowledge`, and `Skill Knowledge` field tables.
