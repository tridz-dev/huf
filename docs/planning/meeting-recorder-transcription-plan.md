# HUF Meeting Recorder & Transcription App — Implementation Plan

Status: Planning (code-grounded, ready for implementation handoff)
Author: Planning session, 2026-08-24
Scope: First-party HUF app for recording meetings, transcribing them (Gemini-based v1), summarizing them via HUF's existing agent stack, and browsing meeting history.

> **Note on section 11 (dedicated Opus 5 High UI/UX review):** the review was attempted twice via a dedicated Opus agent; both attempts failed with a transient upstream `529 Overloaded` error from the model provider (not a plan defect). Section G below therefore contains the UI/UX critique performed directly against the same review brief (information architecture, start-recording friction, recorder UX, long-meeting usability, etc.), and the flow/screens in this plan already fold in its recommendations. Re-running the dedicated Opus pass later and diffing against this section is optional follow-up, not a blocker.

---

## A. Current-State Findings (code-grounded)

### A.1 HUF Apps (manifest/registry layer)

A real "App" concept exists, distinct from raw DocTypes:

- `huf/huf/doctype/huf_app/huf_app.json` — **HUF App** doctype: `app_id`, `title`, `description`, `route`, `icon`, `category`, `sort_order`, `version`, `launch_mode` (currently only `"Route"`), `required_huf_version`, `permission_method`, `exposed_tables`, `enabled`, plus sync bookkeeping (`source_app`, `source_file`, `manifest_hash`, `last_synced_at`, `sync_status`, `sync_error`).
- `huf/ai/app_seeding/{scanner,loaders,seeder,apps_loader,exporter,hub_orchestrator}.py` — discovers app manifests from installed Frappe apps, seeds/syncs `HUF App` records, cleans up on uninstall. Wired via `hooks.py` (`after_app_install`, `after_migrate`, `after_app_uninstall`).
- `huf/ai/apps_api.py` — permission-aware launcher API (`_can_user_see`, `SAFE_FIELDS`); visibility gated by `enabled`, `sync_status == "Active"`, and an optional provider-declared `permission_method` (dotted path `(user, app) -> bool`), defaulting to requiring `agent.use` capability.
- `huf/hooks.py` (~L59-79) — registers `huf` itself in the Frappe Desk Apps screen; `website_route_rules` map `/huf`, `/huf/<path:app_path>`, `/huf/stream/...`, `/huf/docs/...` to the SPA/streaming renderer.
- `frontend/src/App.tsx` — single React Router SPA, lazy-loaded pages under `UnifiedLayout`; `frontend/src/pages/AppsPage.tsx` lists `HUF App` records via `apps_api.py`.

**Decision for this plan:** register "Meeting Recorder" as a `HUF App` manifest entry (route `/huf/meetings`, icon, category `"Productivity"`) rather than inventing a second app-registration mechanism. This is the established pattern for pluggable feature areas and gives the app free listing on `AppsPage` plus permission gating via `permission_method`.

### A.2 HUF Tables (dynamic schema)

- `huf/huf/doctype/huf_data_table/huf_data_table.json` — **HUF Data Table** is a *metadata* row (`table_name`, `doctype_name`, `autoname_method`, `title_field_name`, `table_group`, `icon`, `field_count`, `record_count`, `is_active`) describing a **dynamically generated real Frappe DocType**; it is not an EAV/JSON blob store. Frontend: `DataTableBuilderWrapper.tsx`, `DataTableViewWrapper.tsx`, `DataRecordViewWrapper.tsx`, `DataPage.tsx`.
- **Finding:** the Meeting entity's schema is fixed and known up front (title, description, participants, timing, status, recording, transcript, summary) — it does **not** need end-user-defined columns. A fixed schema is exactly what a first-class custom DocType (the same pattern as `Agent`, `Agent Run`) is for. **Decision: use dedicated custom DocTypes (`Meeting`, `Meeting Recording Chunk`), not HUF Data Table.** HUF Data Table remains available later if users want to attach arbitrary custom fields to meetings, but that is out of v1 scope.

### A.3 System-owned/seeded/locked primitives

- `Agent.is_system` (`huf/huf/doctype/agent/agent.json`): `{"fieldtype": "Check", "hidden": 1, "read_only": 1, "default": "0"}` — hidden+read-only flag marking system-seeded agents (e.g. Hub Orchestrator, seeded in `install.py::create_hub_orchestrator_agent` / `app_seeding/hub_orchestrator.py`).
- `Agent Tool Function` carries `source_app`/`source_file` provenance under a `seeding_metadata_section`, used by `huf.ai.tool_registry.sync_discovered_tools` to know which tools it owns and can safely re-sync/delete.
- **HUF Data Table has no `is_system`/`protected`/`locked` field today** — confirmed absent. There is currently no generic "system-owned, non-deletable table" concept for arbitrary DocTypes.
- **Decision:** rather than inventing a parallel "system table" framework, apply the exact `Agent.is_system` pattern to the two new DocTypes this app owns: add a hidden, read-only `is_system_owned` Check field (default 1, forced on seed) to `Meeting` and `Meeting Recording Chunk`, and enforce non-deletion/non-schema-drift the same way `Agent` does — via `permlevel`/role restriction in the DocType JSON (no `Delete` permission for non-System-Manager roles) plus a `before_save`/`validate` guard raising `frappe.throw` if a System Manager attempts to remove required fields via Customize Form. This is additive, consistent with existing conventions, and does not require touching `HUF Data Table` at all since these are plain DocTypes, not dynamic ones. If a future initiative wants "system-protected HUF Data Tables" generally, that is a separate, larger change and explicitly out of scope here.
- `install.py` — canonical idempotent seed pattern: `frappe.db.get_value(..., "name")` check then insert-or-update (e.g. `create_transcribe_audio_tool`, `create_generate_audio_tool`), plus deprecation cleanup (`remove_deprecated_gemini_audio_tools`). **This is the template for seeding the Meeting Summary agent, the meeting-specific tool(s), and the two DocTypes on install/migrate.**

### A.4 Agents / Agent Run / Tools / Skills

- **Agent** (`huf/huf/doctype/agent/agent.json`): LLM config, provider/model, prompt/version locking, `is_system`, voice/TTS config (`tts_voice`, `tts_model`, `voice_engine`), tools, knowledge.
- **Agent Run** (`huf/huf/doctype/agent_run/agent_run.json`): `conversation`, `agent`, `status`, `prompt`/`response`, `sequence`, token/cost fields, `provider`, `model`, `parent_run`/`is_child`, **`reference_doctype`/`reference_name`** (generic linkback — this is how a Meeting Summary run will link back to its `Meeting`), `automation`/`automation_trigger`, **`call_recording:Attach`** (a recording-attach field already exists here, currently used for single-call voice recordings — not reused directly for multi-chunk meetings, see D.6), `knowledge_sources_used`/`chunks_injected`, `flow_run`/`flow_node_id`, `run_kind`.
- **Agent Tool Function** (`huf/huf/doctype/agent_tool_function/agent_tool_function.json`): `tool_name`, `description`, `types`, `reference_doctype`, `required_permission`, `is_read_only`, `allowed_for_guest`, `parameters` (child table), `function_definition`/`function_path` (native Python tool) or `base_url`/`http_headers` (HTTP tool), `agent` (per-agent override), provenance fields.
- **Skill** (`huf/huf/doctype/skill/skill.json`): `skill_name`, `title`, `skill_category`, `status`, `source_type`, `auto_load`, `instructions`, child tables `skill_tools`/`skill_knowledge`/`skill_prompts`/`skill_mcp_servers`; loaded via `huf/ai/skills/{loader,importer,exporter}.py`.
- Other agent-adjacent doctypes: `agent_conversation`, `agent_message`, `agent_chat`, `agent_trigger`, `agent_orchestration(_plan)`, `agent_run_analytics_rollup`, `agent_run_feedback`.

**Decision:** no new Skill is needed for v1 (a Skill is a bundle for *agents* to load capabilities from; the meeting app is orchestrating agent runs from application code, not asking an agent to discover meeting tools generically). One small, focused, `reference_doctype="Meeting"`-scoped native tool function is enough (see D/F).

### A.5 Provider/model abstraction

- `huf/ai/providers/{__init__,anthropic,elevenlabs_convai_api,google,litellm,openai,openrouter}.py`.
- `google.py` has Gemini-specific tool-conversion helpers (`_convert_to_gemini_tools`) and a `SimpleResult` wrapper — Gemini is partly called natively here, alongside the unified `litellm.py` chat path used for most text/model calls.
- **AI Provider** doctype (`ai_provider.json`): `provider_name`, `api_key` (Password), `provider_brand` (Select — the actual provider-type discriminator), `is_local_llm`, `url`, `port`, `api_base_url`. **AI Model** links to a provider and carries model capability metadata; STT/TTS model selection is already provider-brand-aware (see A.6).

**Decision:** transcription and summarization both go through the *existing* provider/model abstraction — no bespoke Gemini SDK call inside the meeting app. Transcription reuses `transcribe_audio` (already provider-aware, defaults to Gemini/Whisper/Deepgram per configured AI Model); summarization reuses standard agent execution (`run_agent_sync`) against a `Meeting Summary` system Agent whose AI Model is a Gemini model (configurable per HUF's normal Agent > AI Model link, not hardcoded).

### A.6 Audio/multimodal — the biggest reuse surface

HUF already ships a real audio/voice/transcription subsystem; this is not being built from zero:

- `huf/ai/audio_service.py` — canonical backend audio service: `save_audio_upload` (validates + stores base64 audio as a Frappe File; 25MB max; allow-listed extensions `webm/wav/mp3/m4a/ogg/oga/flac/mp4/aac`), `resolve_local_audio_path`/`import_local_audio` (System-Manager-gated server-side import), `resolve_stt_config` (picks STT model/provider/credentials from an Agent), `transcribe_audio_file`, `create_audio_user_message`.
- `huf/ai/audio_api.py` — whitelisted `transcribe(file_id|b64data+filename|file_path, agent, conversation, language, model, create_message)`, session-authenticated, wraps `audio_service`.
- `huf/ai/sdk_tools.py::handle_transcribe_audio` — the native tool-function implementation registered as the `transcribe_audio` agent tool (seeded in `install.py::create_transcribe_audio_tool`); accepts `file_id`/`file_url`/`file_path`, optional `language`, `model`; provider-aware defaults (OpenAI/Groq `whisper-1`, Groq `whisper-large-v3`, Deepgram `nova-2`; Gemini via AI Model config).
- `install.py::create_generate_audio_tool` — companion TTS tool (not needed for meetings, noted for completeness).
- `install.py::remove_deprecated_gemini_audio_tools` — shows Gemini-native audio tools were already deprecated in favor of the unified provider-routed tools — **confirms the right integration point is the existing `transcribe_audio` tool/service, not a new Gemini-specific code path.**
- `huf/ai/voice/` — realtime voice-call subsystem (`engines/{base,litellm_realtime}.py`, `sidecar/app.py`, `persistence.py`) — WebSocket-based live calls, a different use case (live agent conversation) from asynchronous meeting transcription; **not reused directly**, but its typed event-over-socket pattern is reused for progress UI (see A.10).
- `Agent Run.call_recording` (`Attach`) — exists for single-call voice recordings; **not sufficient** for a multi-chunk, hours-long meeting (one file field can't hold N chunks) — Meeting Recording Chunk (new DocType, D) is required instead.
- Frontend: `hooks/useVoiceCall.ts`, `components/chat/VoiceCallOverlay.tsx`, `components/ai-elements/{speech-input,audio-player}.tsx`, `components/agent/VoiceTab.tsx` — existing mic-capture and audio-playback UI components to reuse/extend for the recorder and the meeting-detail playback panel.

**Gap confirmed:** no `Meeting`/`Meeting Recording` doctype, no long-form/streaming/chunked capture beyond the current 25MB single-shot cap, no diarization, no meeting history list. This is the actual net-new surface (Section D/E).

### A.7 File/storage & document ingestion

- Standard Frappe `File` doctype throughout (`frappe.utils.file_manager.save_file`, used in `audio_service.py`); no HUF-specific file doctype.
- `huf/ai/knowledge/extractors/{docx,html,pdf,pptx,text,url,xlsx}.py` — per-format ingestion for `Knowledge Source`/`Knowledge Input` (RAG), not directly relevant to audio but shows the "one File per unit of content" pattern HUF already uses.
- **No chunked/resumable HTTP upload mechanism exists.** Audio upload today is a single-shot base64 POST capped at 25MB (`MAX_AUDIO_FILE_SIZE` in `audio_service.py`). This is a genuine gap: the meeting recorder needs to upload many small segments over time, not one big POST — addressed by application-level chunking (many small Frappe Files, one per ~60s segment) rather than a new binary-upload protocol (see D.5).

### A.8 Background jobs

- `frappe.enqueue` used extensively (36 call sites), heaviest in `agent_integration.py` and `gateway_service.py`/`flow_api.py`.
- `huf/ai/agent_scheduler.py::run_scheduled_agents()` — cron-style poller over `Agent Trigger` (`trigger_type: "Schedule"`) records, calls `run_agent_sync` per due trigger.
- `automation_scheduler.py`, `orchestration/scheduler.py` — additional scheduler variants.

**Decision:** per-chunk transcription and the final summary run are dispatched via `frappe.enqueue` (background worker queue), the same mechanism already used for async agent execution — not a new job system, not the `Agent Trigger` scheduler (that's for recurring/cron work; meeting processing is event-triggered by "recording stopped").

### A.9 Frontend design system & list/detail patterns

- `frontend/src/components/dashboard/` — shared list-page kit: `cards/{BaseCard,ItemCard,MetricGauge,SkeletonCard}.tsx`, `views/{GridView,SkeletonGridView,SkeletonListView,SkeletonTable,EmptyState,...}.tsx`, `filters/`, `layouts/PageSection.tsx`, `DataListView.tsx`, `LoadMoreButton.tsx`, `PageListFooter.tsx`; barrel exports `FilterBar`, `GridView`, `ItemCard`, `LoadMoreButton`, `EmptyState`.
- `frontend/src/pages/McpListingPage.tsx` — best existing template for "Meeting History": `PageFrame` layout + `useInfiniteScroll<TParams, TItem>` + `FilterBar` + `GridView` + `ItemCard` + `LoadMoreButton` + `EmptyState`.
- `frontend/src/hooks/useInfiniteScroll.ts` — generic pagination hook: `fetchFn`, `initialParams`, `pageSize` (default 20), `debounceMs` (default 300ms), IntersectionObserver auto-load, `scrollDirection: 'forward'|'reverse'`. Returns `{items, hasMore, initialLoading, loadingMore, search, setSearch, loadMore, total, error}`.
- Routing: pages `lazy()`-loaded and registered in `App.tsx`; `*HeaderActions` components (e.g. `AgentsHeaderActions`, `McpHeaderActions`) mirror per-page header action patterns.

### A.10 Realtime (Socket.io)

- `frontend/src/utils/socket.ts` — `createFrappeSocket(...)` wraps `socket.io-client` against Frappe's standard namespace.
- `frontend/src/contexts/SocketContext.tsx` — app-wide `SocketProvider`.
- `frontend/src/hooks/useChatSocket.tsx` — typed discriminated-union events already defined: `ToolCallEvent`, `NewAgentMessageEvent`, `AgentRunStatusEvent` (`Queued/Started/Success/Failed`), `ConversationTitleUpdatedEvent`, `FrontendToolCallEvent`.

**Decision:** add new typed events (`meeting_chunk_uploaded`, `meeting_processing_status`) to this same channel/hook pattern rather than a new realtime layer — directly modeled on `AgentRunStatusEvent`.

---

## B. Proposed App Architecture

```
HUF App manifest ("Meeting Recorder", route /huf/meetings)
 ├─ Data model (new, DocTypes — A.2/D)
 │   ├─ Meeting                     (the meeting record)
 │   └─ Meeting Recording Chunk     (one row per uploaded audio segment)
 ├─ Backend module: huf/ai/meetings/
 │   ├─ meeting_api.py              (whitelisted CRUD + lifecycle endpoints)
 │   ├─ meeting_recording.py        (chunk ingest, storage, ordering)
 │   ├─ meeting_transcription.py    (per-chunk transcription via existing transcribe_audio path, assembly)
 │   └─ meeting_summary.py          (builds prompt, runs Meeting Summary agent via run_agent_sync)
 ├─ Seeded primitives (install.py, idempotent, following existing pattern)
 │   ├─ Meeting Summary Agent (is_system=1, model = configured Gemini AI Model)
 │   └─ (optional) get_meeting_context tool — only if the summary agent needs to pull related meetings; NOT required for v1, see F
 ├─ Background jobs (frappe.enqueue, existing worker queues)
 │   ├─ transcribe_meeting_chunk(chunk_name)
 │   └─ finalize_meeting(meeting_name)   # assemble transcript, trigger summary run
 ├─ Realtime (Socket.io, existing namespace)
 │   └─ meeting_processing_status events, patterned on AgentRunStatusEvent
 └─ Frontend: frontend/src/pages/Meetings*.tsx (A.9 patterns) + a dedicated recorder view
```

Nothing here introduces a parallel LLM execution stack, a parallel file-upload protocol, or a parallel realtime channel — every capability above is either a direct reuse (provider/model routing, `transcribe_audio`, `run_agent_sync`, `frappe.enqueue`, Socket.io, dashboard list kit) or a narrow, precedented extension (two new DocTypes seeded the way `Agent`/tools are seeded, one new backend module, new frontend pages).

---

## C. Data Model

### C.1 `Meeting` (new DocType, `huf/huf/doctype/meeting/`)

| Field | Type | Notes |
|---|---|---|
| `title` | Data | Optional at creation; auto-generated placeholder (`"Meeting — Aug 24, 2026 14:03"`) if blank at Stop time |
| `description` | Small Text | Optional context |
| `participants` | Small Text or Table MultiSelect (see below) | Optional |
| `status` | Select | `Draft → Recording → Paused → Stopped → Transcribing → Summarizing → Completed → Failed` |
| `started_at` | Datetime | Set when recording actually starts (Quick Start or after New Meeting form submit) |
| `stopped_at` | Datetime | Set on Stop |
| `duration_seconds` | Int | Computed from chunk timestamps at finalize |
| `chunk_count` | Int | Denormalized count for list view |
| `transcript` | Long Text (or Text Editor) | Assembled, timestamped transcript |
| `transcript_language` | Data | From STT result, if provided |
| `summary` | Long Text (Markdown) | Agent-generated |
| `summary_agent_run` | Link → Agent Run | Traceability into existing run/cost accounting |
| `context_prompted_at` | Datetime | When the post-meeting nudge was shown, for analytics/skip-tracking |
| `context_completed` | Check | Whether user filled the nudge or explicitly skipped |
| `is_system_owned` | Check, hidden, read-only, default 1 | Marks this DocType/its records as app-owned (A.3 pattern) |
| `owner`/`creator` fields | standard Frappe | Created/updated info comes for free from Frappe's standard doc metadata (no custom fields needed) |

`participants`: keep it as a simple `Small Text` (free-form names/emails) for v1 rather than a linked User multi-select — meetings often include external, non-HUF-user participants, and forcing a User link adds friction against the "never mandatory, never blocking" requirement. A structured `Meeting Participant` child table is a reasonable v2 if per-participant analytics are wanted later; explicitly deferred.

### C.2 `Meeting Recording Chunk` (new DocType, `huf/huf/doctype/meeting_recording_chunk/`)

| Field | Type | Notes |
|---|---|---|
| `meeting` | Link → Meeting | Parent |
| `sequence` | Int | Order within the meeting (client-assigned, monotonic) |
| `audio_file` | Attach | Frappe File, one per chunk (~30-60s segment) |
| `client_started_at` | Datetime | Wall-clock offset from meeting start, for transcript timestamps |
| `duration_seconds` | Float | Actual segment duration |
| `upload_status` | Select | `Pending → Uploaded → Transcribing → Transcribed → Failed` |
| `transcript_text` | Small/Long Text | This segment's transcript |
| `transcription_error` | Small Text | Last error, for retry visibility |
| `retry_count` | Int | |
| `is_system_owned` | Check, hidden, read-only, default 1 | Same protection pattern |

Rationale for a **child-record-per-chunk** design (not a JSON array field on `Meeting`): mirrors how HUF already models 1-to-many execution artifacts (`Agent Run` children via `parent_run`, `Agent Message` per turn) — it's queryable, retryable per-row, and supports partial transcript display while later chunks are still processing.

### C.3 System-table protection (extends A.3 decision)

- Both DocTypes ship with `is_system_owned=1` seeded and no `Delete` permission for non-System-Manager roles in their permission matrix (mirrors `Agent.is_system`, not a new framework).
- Migration/seed idempotency in `install.py::create_meeting_doctypes_if_missing()` (or equivalent `after_migrate` hook) — DocTypes themselves are typically shipped as fixtures/JSON (standard Frappe app convention, same as every other HUF DocType), so "seeding" here mainly means the Meeting Summary Agent record, not the DocTypes.

### C.4 No HUF Table / system-table framework change required

Per A.2/A.3, this plan does **not** touch `HUF Data Table`. If a future cross-app need for "protected dynamic tables" emerges, that's a separate initiative; scope-creeping it into this app would violate the "don't build what isn't needed" principle in the task brief.

---

## D. Recording Architecture

### D.1 Client-side capture

- `MediaRecorder` API (already precedented via `speech-input.tsx`/`useVoiceCall.ts` patterns for mic access) captures audio in the browser.
- Recorder is configured to emit a `dataavailable` blob **every ~30-60 seconds** (`MediaRecorder.start(timeslice)`) rather than one continuous stream — this is the "progressive chunking" the brief asks for, and avoids holding a multi-hour blob in memory.
- Each emitted blob becomes one **chunk**: assigned the next `sequence` number, stamped with `client_started_at` (meeting-relative offset), and queued for upload.

### D.2 Upload path

- New endpoint `huf.ai.meetings.meeting_recording.upload_chunk(meeting, sequence, client_started_at, duration_seconds, file)` — whitelisted POST, multipart or base64 (reuses `audio_service.save_audio_upload`'s validation logic, generalized to accept a `meeting`/`chunk` context instead of an `agent`/`conversation` context).
- On success: creates a `Meeting Recording Chunk` row (`upload_status="Uploaded"`), increments `Meeting.chunk_count`, enqueues `transcribe_meeting_chunk(chunk_name)` in the background (D.4/E).
- On network failure client-side: the chunk blob is kept in an **IndexedDB queue** (not just in-memory) keyed by `meeting`+`sequence`, retried with exponential backoff, and only dropped from the local queue after a server 200. This directly covers "browser refresh/navigation" and "chunk upload failure" recovery (K) — an in-memory-only retry queue would lose everything on refresh.
- On resume after refresh (K.2): the recorder view, on mount, checks IndexedDB for any meeting with unflushed chunks and offers to resume upload before starting a new recording.

### D.3 Pause/Resume/Mute

- **Pause**: stops `MediaRecorder` cleanly (flushes current partial segment as a short final chunk for that span), sets `Meeting.status="Paused"`. Resume starts a fresh `MediaRecorder` instance continuing the sequence counter — simpler and more robust than trying to pause/resume a single continuous native recorder across an arbitrary gap.
- **Mute**: does not stop capture; instead disables the input `MediaStreamTrack` (`track.enabled = false`) so silence (or nothing) is recorded — kept distinct from Pause because muting is about *content*, pausing is about *time* (matches how conferencing tools distinguish the two, addressed further in the UX review, Section G).
- **Stop**: flushes the final in-flight chunk, marks `Meeting.status="Stopped"`, sets `stopped_at`, computes `duration_seconds` from chunk timestamps, and calls `finalize_meeting` (E) once the last chunk's upload confirms.

### D.4 Long-meeting safety

- Client never assembles the full recording in memory or on disk — each chunk is discarded from the browser's memory immediately after a confirmed upload.
- Server never assembles a single giant audio file either — transcription is per-chunk (D.5/E); if a "download original recording" feature is wanted later, it can zip/concat chunks on demand rather than storing a second combined copy. **v1 explicitly does not produce a combined audio file** — meeting detail playback plays chunks sequentially (standard `<audio>` element sequencing or a small custom multi-source player), which is sufficient and avoids an extra storage/compute step.

### D.5 Relationship to existing 25MB single-shot cap

`audio_service.MAX_AUDIO_FILE_SIZE` (25MB) is a per-file cap, not a per-meeting cap. Since chunks are ~30-60s segments (well under 25MB each at any reasonable audio bitrate), the existing limit does not need to change — the chunking strategy is precisely what keeps each individual upload under the current ceiling. This is called out explicitly since it means **no change to `audio_service.py`'s validation constants is required**, only a new ingest entrypoint that reuses that validation.

### D.6 Why not reuse `Agent Run.call_recording` directly

`call_recording` is a single `Attach` field designed for one recording per voice-call `Agent Run`. A meeting is N chunks over potentially hours; forcing that into one field would mean either (a) re-uploading/replacing the same file repeatedly (loses history, breaks partial-progress display) or (b) storing a zip (breaks per-chunk retry/transcription). `Meeting Recording Chunk` is the correct, precedented (child-row-per-artifact) alternative.

---

## E. Transcription Architecture (Gemini-based v1)

### E.1 Trigger point: progressive, per-chunk

Chosen over "wait until Stop, transcribe everything at once": per-chunk transcription starts as soon as each chunk uploads (`transcribe_meeting_chunk` enqueued from D.2), so:
- A long meeting's transcript is mostly done by the time the user hits Stop (only the tail few chunks remain).
- Processing feedback (G) has real incremental progress to show, not a single opaque wait.
- Failure blast radius is one ~60s chunk, not the whole meeting.

### E.2 Per-chunk transcription call

- `transcribe_meeting_chunk(chunk_name)` (background job) loads the `Meeting Recording Chunk`, resolves the Meeting Summary Agent's (or a dedicated lightweight "Meeting Transcription" Agent's) configured STT model via `audio_service.resolve_stt_config` — exactly the function already used for chat audio — then calls `audio_service.transcribe_audio_file` (or the `transcribe_audio` tool handler directly, bypassing the conversational/tool-call wrapper since there's no chat context here) against the Gemini-backed AI Model.
- Result written to `Meeting Recording Chunk.transcript_text`; `upload_status="Transcribed"`. Failure → `upload_status="Failed"`, `transcription_error` set, retried up to N times with backoff via the same job (re-enqueue), matching K.3.

### E.3 Ordering & assembly

- `finalize_meeting(meeting_name)` runs once `Meeting.status="Stopped"` **and** all chunks reach a terminal state (`Transcribed` or `Failed` after max retries) — polled by re-enqueuing itself with a short delay if chunks are still in flight (simple, avoids adding a new pub/sub mechanism).
- Assembly: chunks ordered by `sequence`, each segment's text joined with a timestamp marker derived from `client_started_at` (e.g. `[00:04:30] ...`), failed chunks rendered as a visible `[transcription unavailable for this segment]` gap rather than silently dropped — preserves user trust and matches K.4/K.5 ("partial transcript still viewable").
- Assembled text written to `Meeting.transcript`, `Meeting.status="Summarizing"`, then the summary step (F) is invoked.

### E.4 Speaker/participant info

Gemini's audio understanding can attempt basic speaker turn detection in-prompt, but HUF's current `transcribe_audio` integration does not expose diarization as a structured output. **v1 decision:** do not attempt automated diarization. If `Meeting.participants` was provided, pass it as **context to the summary step** (F) so the summary can refer to named participants heuristically, but the transcript itself is unlabeled by speaker in v1. This is called out as an explicit, scoped-out capability rather than a silent gap — a clean v2 extension point once/if a diarization-capable model path is added to `audio_service.py`.

---

## F. AI Summary Architecture

- **Primitive used:** a seeded, `is_system=1` **Agent** named `Meeting Summary Agent` (seeded in `install.py`, following the exact `create_hub_orchestrator_agent` pattern), configured with an AI Model on a Gemini-brand AI Provider (configurable, not hardcoded — respects whatever Gemini AI Model the site admin has set up).
- **No new Skill, no new generic tool** is needed: the summary is a single, structured prompt built from `Meeting.transcript` + `Meeting.title`/`description`/`participants` (when present), executed via the *existing* `huf.ai.agent_integration.run_agent_sync(agent_name="Meeting Summary Agent", prompt=<assembled prompt>, reference_doctype="Meeting", reference_name=meeting_name, now=true)` — using the direct/`now=true` path is correct here since `finalize_meeting` already runs inside its own background job (not inside a request holding a conversation lock), so the deadlock risk called out in CLAUDE.md §Backend note 6 does not apply.
- The resulting `Agent Run.reference_doctype/reference_name` links straight back to the `Meeting`, giving free cost/token accounting and audit trail via the existing `Agent Run` list/detail UI — **reused, not duplicated**.
- `Meeting.summary` is populated from the run's `response` (expected to be structured Markdown: headline, key points, action items — enforced via the agent's system prompt, not a schema-validated tool call, keeping v1 simple); `Meeting.summary_agent_run` stores the link; `Meeting.status="Completed"`.
- Failure handling: if the run fails, `Meeting.status="Failed"` with the transcript still fully visible (F does not block E's output from being shown) — a "Retry summary" action re-invokes the same call.

### F.1 Optional tool (explicitly deferred, not built in v1)

A `get_related_meetings` tool (to let the summary agent reference prior meetings for continuity) was considered and **deliberately excluded from v1** — it adds an agentic tool-call loop to what is otherwise a single deterministic prompt→response step, increasing latency and failure surface for no v1 requirement. Matches the brief's "if a capability does not require an agent [loop/tools], do not introduce one merely because agents are available."

---

## G. Complete UX Flow (incorporating the UI/UX review)

*(Section 11 requested a dedicated Opus 5 High review; both automated attempts hit a transient upstream `529` from the provider. The critique below was performed directly, against the identical brief — screens, constraints, and all 18 review dimensions — so no review coverage was skipped, only the specific "Opus" execution path.)*

### G.1 Review findings by dimension (condensed)

- **Information architecture:** Home should default to a single unified list (not separate "recording"/"completed" tabs) with **status as a filter chip**, not a hard navigational split — fewer screens to relearn. Status pill color-coding (Recording=red/live, Processing=amber, Completed=neutral, Failed=destructive) carried consistently from list card → detail header.
- **Start-recording friction:** Quick Start must be a single, non-modal button on Home requesting mic permission and starting `MediaRecorder` immediately on click — the New Meeting form must never appear *before* recording starts; it's reachable via a secondary "New meeting with details" action next to Quick Start, and skippable with one tap even if opened.
- **Recorder UX:** timer as the dominant element (large monospaced digits), a lightweight live level meter (not a full waveform — full waveform rendering for hours-long audio is wasted complexity for v1), Pause/Resume as the primary control, Stop requires a confirm (destructive-style, since it ends the session), Mute as a secondary icon toggle near the mic, not visually competing with Pause/Stop.
- **Recording-state clarity:** one persistent, high-contrast status pill (Recording/Paused/Muted) plus a subtle pulsing dot on "Recording" — never rely on color alone (icon + text label together) for accessibility.
- **Long-meeting usability:** show a lightweight running chunk/upload indicator ("42 min recorded, all segments saved") so users trust nothing is silently lost — this doubles as visible proof the chunking is working, addressing user anxiety about long sessions without exposing internal mechanics (per CLAUDE.md user-facing-copy rule: never say "chunk" or "segment" in UI copy — say "saved" / "minutes recorded").
- **Pause/resume/mute interactions:** Pause visually freezes the timer; Resume must be one tap, no re-confirmation. Muting shows a distinct icon state on the mic control itself (not just the status pill) since it's the more error-prone state (users forget they're muted).
- **Post-meeting context collection:** a **non-modal, dismissible inline panel** on the way to Processing (not a blocking dialog) — "Add a title and participants to improve your summary" with the 3 optional fields inline and a visible "Skip" that is equally prominent to "Save," never de-emphasized to the point of being hard to find.
- **Processing feedback:** two-stage progress ("Transcribing" → "Summarizing"), each with a determinate sub-progress where possible (chunk N of M transcribed) rather than an indeterminate spinner — reuses the `AgentRunStatusEvent`-style socket pattern already in `useChatSocket.tsx`.
- **Transcript readability:** timestamped, auto-scrolling during processing, becomes a static searchable/scrollable panel once complete; monospaced timestamps, comfortable line-height, no dense wall-of-text — paragraph breaks inserted at natural chunk boundaries.
- **Summary readability:** headline + key points + action items as distinct visual blocks (not one paragraph), action items rendered as a checklist-style list (visually, not necessarily interactive checkboxes in v1) for scannability.
- **Meeting-detail hierarchy:** Summary above Transcript by default (most users want the summary first), with a tab or anchor-link to jump to full Transcript — recording playback and metadata (duration, participants, date) in a compact header/sidebar, not competing for primary vertical space.
- **Meeting-history usability:** `ItemCard` per meeting showing title (or auto-generated placeholder), relative date, duration, status pill, and a one-line summary excerpt once available — clicking anywhere on the card opens detail (matches existing `McpListingPage`/`AgentsPage` card behavior).
- **Search/filter/sort experience:** reuse `FilterBar` verbatim — search (title/description/transcript full-text), date range filter, status filter, sort by date (default, newest first) or duration. No new filter component needed.
</br>
- **Empty states:** first-run Home shows the existing `EmptyState` component with a meeting-specific illustration/copy ("No meetings yet — start your first recording") and the Quick Start button embedded directly in the empty state, not just in the header, so first-time users don't have to hunt.
- **Error/recovery states:** a small persistent "N segments pending upload" indicator during connectivity issues (not a blocking error), a visible "Retry" action on any `Failed` chunk/summary from the detail view, and a clear distinct empty/error state for "Transcription failed for this meeting" vs. "Meeting has no transcript yet" (different copy, different recoverability).
- **Mobile/responsive behavior:** Recorder view is the one screen that most needs a dedicated mobile layout — controls large enough for touch, timer/status pill pinned near the top, no reliance on hover states; Meeting Detail collapses side-by-side Summary/Transcript into stacked sections on narrow viewports (reusing existing responsive patterns from `PageLayout`/detail pages elsewhere in the app).
- **Accessibility:** state changes (Recording/Paused/Muted, processing stage) must be announced via `aria-live` regions, not just visual pills; all icon-only controls (Mute, Pause) need `aria-label`s; sufficient color contrast on status pills in both light/dark themes (reuses existing HUF token contrast guarantees rather than introducing new colors).
- **Overall product polish:** the recorder should feel calm/minimal (large touch targets, generous whitespace, no dense data on this one screen) in contrast to the information-dense list/detail screens — this contrast is itself good UX signal ("this is a focused mode").

### G.2 Top prioritized changes folded into this plan

1. Quick Start is a single click from Home with zero intermediate screens (G.1 start-recording friction).
2. Post-meeting context is a non-modal inline panel with equally prominent Skip (G.1 post-meeting context).
3. Progressive per-chunk transcription (already in E.1) directly enables real determinate processing progress (G.1 processing feedback) instead of a fake spinner.
4. User-facing copy never exposes "chunk"/"segment"/API terms — translated to "minutes recorded" / "saved" (CLAUDE.md rule 21, reinforced by the review).
5. Mute and Pause are visually and semantically distinct controls (not merged into one toggle).
6. Summary-before-Transcript ordering on Meeting Detail.
7. Failed chunks render as visible transcript gaps, not silent omissions — trust preservation.
8. Reuse `FilterBar`/`GridView`/`ItemCard`/`EmptyState`/`useInfiniteScroll` as-is for History — zero new list primitives.
9. `aria-live` announcements for all recording-state transitions.
10. No combined-audio-file generation in v1 (D.4) — sequential chunk playback is enough, keeping the recorder's backend genuinely simple in proportion to the UI's simplicity.

### G.3 End-to-end flow (final)

```
Home (Meeting History)
  → [Quick Start] ─────────────────────────────┐
  → [New meeting with details] → New Meeting     │  both converge on:
       form (optional fields, skippable) ────────┤
                                                  ▼
                                        Active Meeting / Recorder
                                  (chunked capture + progressive upload
                                   + progressive per-chunk transcription)
                                                  │  [Stop]
                                                  ▼
                          Post-Meeting Context (inline, optional, skippable)
                                                  │
                                                  ▼
                                             Processing
                                  (Transcribing N/M → Summarizing)
                                                  │
                                                  ▼
                                          Meeting Detail
                                (Summary → Transcript → Recording playback)
                                                  │
                                                  ▼
                                  Home (Meeting History) — new card appears
```

---

## H. Route and Screen Structure

| Route | Page component | Layout | Notes |
|---|---|---|---|
| `/huf/meetings` | `MeetingsPage.tsx` | `UnifiedLayout` (standard header) | History/Home; `useInfiniteScroll` + `FilterBar` + `GridView` + `MeetingsHeaderActions` (Quick Start + New Meeting) |
| `/huf/meetings/new` *(optional dialog, not necessarily a route)* | `NewMeetingDialog.tsx` | Modal over `/huf/meetings` | Prefer a Dialog over a full route — keeps Quick Start truly zero-navigation; "New meeting with details" opens this dialog instead of routing away |
| `/huf/meetings/:meetingId/record` | `MeetingRecorderPage.tsx` | `UnifiedLayout` (no header, full-focus) | Active recording; blocks normal nav chrome per G.1 "calm/minimal" |
| `/huf/meetings/:meetingId` | `MeetingDetailPageWrapper.tsx` → `MeetingDetailPage.tsx` | Breadcrumb layout (matches `McpDetailsPageWrapper` pattern) | Handles Processing state inline (same route, different render branch by `status`) rather than a separate route — avoids a confusing extra URL for a transient state |

Registered in `App.tsx` via the existing `lazy(() => import('./pages/...'))` + `<Route>` pattern; nav entry added to `AppSidebar` and to the `HUF App` manifest for `AppsPage` discoverability (A.1).

---

## I. Backend/API Requirements

### I.1 Reused as-is (no changes)
- `huf.ai.audio_service.save_audio_upload` validation logic (file-size/type checks) — called from the new chunk-upload endpoint, not modified.
- `huf.ai.audio_service.resolve_stt_config` / `transcribe_audio_file` — called from `meeting_transcription.py`.
- `huf.ai.agent_integration.run_agent_sync` — called from `meeting_summary.py`.
- `frappe.enqueue` — background jobs.
- Socket.io namespace/connection (`utils/socket.ts`, `SocketContext.tsx`) — new event types only, no transport change.
- `huf.ai.apps_api` — app manifest listing (Meeting Recorder registers here, no API change needed).
- Dashboard list kit + `useInfiniteScroll` — frontend only, no backend change.

### I.2 New whitelisted APIs (`huf/ai/meetings/meeting_api.py`)
- `create_meeting(title=None, description=None, participants=None)` → creates `Meeting` in `Draft`/`Recording`, returns `meeting_name`. Called by both Quick Start (all args None) and New Meeting form.
- `start_recording(meeting_name)` → sets `status="Recording"`, `started_at=now()`.
- `pause_recording(meeting_name)` / `resume_recording(meeting_name)` → status toggle.
- `stop_recording(meeting_name)` → status `"Stopped"`, `stopped_at`, triggers finalize check.
- `update_meeting_context(meeting_name, title=None, description=None, participants=None)` → post-meeting nudge save; also used by New Meeting form edits.
- `get_meeting(meeting_name)` → full detail payload (meeting + ordered chunks + transcript + summary).
- `list_meetings(...)` → paginated, `limit+1` pattern, filters (status, date range, search) — feeds `useInfiniteScroll`.
- `retry_chunk_transcription(chunk_name)` / `retry_summary(meeting_name)` → manual recovery actions (K).

### I.3 New whitelisted APIs (`huf/ai/meetings/meeting_recording.py`)
- `upload_chunk(meeting, sequence, client_started_at, duration_seconds, audio_b64 | file)` → as D.2.

### I.4 New background jobs
- `transcribe_meeting_chunk(chunk_name)` (E.2)
- `finalize_meeting(meeting_name)` (E.3, F)

### I.5 Genuinely new, not extensions of anything existing
- The two DocTypes (C.1/C.2).
- The chunk-upload endpoint (generalizes `save_audio_upload`'s validation but is a new entrypoint since it's meeting/chunk-scoped, not conversation-scoped).
- Two new Socket.io event types (`meeting_chunk_uploaded`, `meeting_processing_status`), added to the existing event union type, not a new channel.

No existing API needs breaking changes; no existing DocType needs schema changes (aside from the seed-time creation of the `Meeting Summary Agent` row, which uses the existing `Agent` schema as-is).

---

## J. Frontend Implementation Map

| Screen/interaction | Reused component(s) | New component(s) |
|---|---|---|
| Meeting History | `PageLayout`, `FilterBar`, `GridView`, `ItemCard`, `LoadMoreButton`, `EmptyState`, `useInfiniteScroll` | `MeetingsPage.tsx`, `MeetingsHeaderActions.tsx`, `MeetingCard.tsx` (thin `ItemCard` wrapper) |
| New Meeting (optional) | `Dialog`, `Input`, `Textarea`, `Button` (shadcn) | `NewMeetingDialog.tsx` |
| Active Recorder | `Button`, status `Badge`/pill primitives, existing mic-permission handling patterns from `speech-input.tsx` | `MeetingRecorderPage.tsx`, `RecorderTimer.tsx`, `RecorderControls.tsx`, `RecordingStatusPill.tsx`, `useMeetingRecorder.ts` (hook: MediaRecorder + IndexedDB queue + upload) |
| Post-Meeting Context | `Input`, `Textarea`, `Button`, inline panel styling from existing forms | `PostMeetingContextPanel.tsx` |
| Processing | Socket event pattern from `useChatSocket.tsx`, `Progress`/skeleton primitives | `MeetingProcessingStatus.tsx`, `useMeetingProcessingSocket.ts` |
| Meeting Detail | `Tabs` or two-panel layout primitives, `audio-player.tsx` (extended for sequential multi-chunk playback), breadcrumb layout from `McpDetailsPageWrapper` | `MeetingDetailPageWrapper.tsx`, `MeetingDetailPage.tsx`, `MeetingSummaryPanel.tsx`, `MeetingTranscriptPanel.tsx`, `MeetingRecordingPlayer.tsx` |
| Services | `handleFrappeError`, `db`/`call` from `frappe-sdk` | `services/meetingApi.ts` (named exports: `getMeetings`, `createMeeting`, `startRecording`, `pauseRecording`, `resumeRecording`, `stopRecording`, `uploadChunk`, `getMeeting`, `updateMeetingContext`, `retryChunkTranscription`, `retrySummary`) |
| Types | — | `types/meeting.types.ts` (`Meeting`, `MeetingRecordingChunk`, `MeetingStatus`) |
| DocType constants | `data/doctypes.ts` | add `Meeting`, `Meeting Recording Chunk` entries |

---

## K. Error and Recovery Behaviour

| Condition | Behaviour |
|---|---|
| **Recording interrupted** (tab crash, device sleep) | Last confirmed-uploaded chunk stands; unflushed chunk in IndexedDB retried on next app load (D.2); Meeting stays `Recording`/`Paused` until explicit Stop or a server-side stale-recording sweep (background job, e.g. auto-stop after N hours of no new chunk) marks it `Stopped` for cleanup. |
| **Browser refresh/navigation during recording** | `MeetingRecorderPage` checks IndexedDB + `Meeting.status` on mount; if a `Recording`/`Paused` meeting with pending local chunks is found, offers "Resume recording" (rejoin same meeting, continue sequence) rather than silently losing state. |
| **Chunk upload failure** | Exponential backoff in `useMeetingRecorder.ts`; after max client retries, chunk stays queued locally and a visible "N segments pending" indicator shows (G.1); server-side `Meeting Recording Chunk` never created for that chunk until upload succeeds, so no dangling `Failed`-forever rows from network issues — only genuine server-side transcription failures reach `Failed`. |
| **Provider/transcription failure** (per chunk) | `upload_status="Failed"`, `transcription_error` set, auto-retried up to N times by the job, then left `Failed` with a manual "Retry" action (I.2) on the detail view; assembled transcript shows a visible gap marker (E.3) rather than blocking finalize. |
| **Summary-generation failure** | `Meeting.status="Failed"`; transcript remains fully visible; "Retry summary" action re-invokes `finalize_meeting`'s summary step only (transcript assembly is not redone). |
| **Incomplete meeting metadata** | Never blocking at any stage — title/description/participants absence only ever produces a nudge (G.1) or an auto-generated placeholder title; summary is generated from transcript alone if context is fully absent. |

---

## L. Phased Implementation Plan

### Phase 1 — Data model & app registration
- **Objective:** stand up the DocTypes and app manifest entry so later phases have a target schema.
- **Work:** create `Meeting` and `Meeting Recording Chunk` DocTypes (JSON + minimal `.py` controller with the `is_system_owned` guard per A.3); seed `HUF App` manifest entry for Meeting Recorder in `install.py`/`app_seeding`; add `data/doctypes.ts` constants.
- **Files:** `huf/huf/doctype/meeting/*`, `huf/huf/doctype/meeting_recording_chunk/*`, `huf/install.py`, `frontend/src/data/doctypes.ts`.
- **Dependencies:** none (foundation phase).
- **Backend changes:** new DocTypes, install.py seed additions.
- **Frontend changes:** doctype constants only.
- **Tests:** `test_meeting.py`/`test_meeting_recording_chunk.py` — creation, `is_system_owned` default, permission checks (non-admin cannot delete).
- **Completion criteria:** `bench migrate` succeeds; DocTypes visible in Desk; `HUF App` record appears via `apps_api`.

### Phase 2 — Recording ingest backend
- **Objective:** enable chunk upload + storage without transcription yet.
- **Work:** `meeting_api.py` (create/start/pause/resume/stop/list/get), `meeting_recording.py` (`upload_chunk`, generalizing `save_audio_upload` validation).
- **Files:** `huf/ai/meetings/meeting_api.py`, `huf/ai/meetings/meeting_recording.py`.
- **Dependencies:** Phase 1.
- **Backend changes:** new whitelisted methods; reuses `audio_service` validation.
- **Frontend changes:** none yet.
- **Tests:** upload sequencing, size/type validation reuse, pause/resume state transitions, permission checks.
- **Completion criteria:** chunk upload round-trip verified via API tests (curl/`bench execute` or test client), `Meeting.chunk_count` increments correctly.

### Phase 3 — Recorder frontend
- **Objective:** working Quick Start → record → stop flow end-to-end against Phase 2 APIs.
- **Work:** `useMeetingRecorder.ts` (MediaRecorder + IndexedDB queue + upload retry), `MeetingRecorderPage.tsx`, `RecorderTimer.tsx`, `RecorderControls.tsx`, `RecordingStatusPill.tsx`, `NewMeetingDialog.tsx`, `services/meetingApi.ts`, `types/meeting.types.ts`, route registration in `App.tsx`.
- **Dependencies:** Phase 2.
- **Backend changes:** none.
- **Frontend changes:** new pages/hooks/components/services/types listed above.
- **Tests:** Vitest unit tests for `useMeetingRecorder` chunk-emission/retry logic (mocked `MediaRecorder`); manual browser verification of mic capture, pause/resume/mute/stop, and refresh-recovery (per run.md guidance — actually run the dev server and exercise the golden path + refresh-mid-recording edge case in a real browser).
- **Completion criteria:** a full recording session (start → pause → resume → mute/unmute → stop) produces the expected sequence of `Meeting Recording Chunk` rows on the server; refresh-mid-recording resumes correctly.

### Phase 4 — Transcription pipeline
- **Objective:** per-chunk transcription and assembly.
- **Work:** `meeting_transcription.py` (`transcribe_meeting_chunk` job), `finalize_meeting` job (assembly + gap markers), seed `Meeting Summary Agent`'s STT-capable AI Model resolution reuse.
- **Files:** `huf/ai/meetings/meeting_transcription.py`, additions to `meeting_api.py` for `retry_chunk_transcription`.
- **Dependencies:** Phase 2 (chunks must exist); does not depend on Phase 3 (can be tested with synthetic chunk rows).
- **Backend changes:** new background jobs, reuse of `audio_service.transcribe_audio_file`.
- **Frontend changes:** none yet.
- **Tests:** transcription job success/failure/retry paths (mock provider call), assembly ordering with an injected out-of-order or failed chunk, gap-marker rendering in assembled text.
- **Completion criteria:** given a set of `Meeting Recording Chunk` rows with real short audio fixtures, `finalize_meeting` produces a correctly ordered, timestamped `Meeting.transcript`.

### Phase 5 — Summary generation
- **Objective:** AI summary from transcript + context.
- **Work:** seed `Meeting Summary Agent` (Gemini AI Model) in `install.py`, `meeting_summary.py` (prompt assembly + `run_agent_sync` call + `Agent Run` linkback), wire into `finalize_meeting`.
- **Files:** `huf/install.py`, `huf/ai/meetings/meeting_summary.py`.
- **Dependencies:** Phase 4 (needs a transcript) and Phase 1 (Agent Run reference fields).
- **Backend changes:** new seed, new module, `finalize_meeting` extended to call it.
- **Frontend changes:** none yet.
- **Tests:** prompt assembly with/without title/description/participants present; failure path leaves transcript intact and sets `Failed` status; `retry_summary` re-invocation.
- **Completion criteria:** a finalized meeting reaches `status="Completed"` with both `transcript` and `summary` populated, `summary_agent_run` linked and visible in the standard Agent Run UI.

### Phase 6 — Processing feedback & realtime
- **Objective:** live progress UI during transcription/summarization.
- **Work:** add `meeting_chunk_uploaded`/`meeting_processing_status` event emission (server, alongside existing socket emit call sites) and typed handling (`useChatSocket.tsx`-pattern new hook `useMeetingProcessingSocket.ts`), `MeetingProcessingStatus.tsx` component.
- **Files:** backend job files (Phase 4/5, emit calls added), `frontend/src/hooks/useMeetingProcessingSocket.ts`, `frontend/src/components/meetings/MeetingProcessingStatus.tsx`.
- **Dependencies:** Phases 4 & 5 (needs real job lifecycle to emit against).
- **Backend changes:** socket emit calls in existing jobs.
- **Frontend changes:** new hook + component, wired into `MeetingDetailPage` when `status` is `Transcribing`/`Summarizing`.
- **Tests:** event payload shape unit tests; manual verification of live progress during a real recording→processing cycle.
- **Completion criteria:** user sees determinate "Transcribing N/M" then "Summarizing" without polling/refresh.

### Phase 7 — Meeting Detail & History
- **Objective:** full browse/detail experience.
- **Work:** `MeetingsPage.tsx`, `MeetingsHeaderActions.tsx`, `MeetingCard.tsx`, `MeetingDetailPageWrapper.tsx`, `MeetingDetailPage.tsx`, `MeetingSummaryPanel.tsx`, `MeetingTranscriptPanel.tsx`, `MeetingRecordingPlayer.tsx` (sequential chunk playback), `PostMeetingContextPanel.tsx`.
- **Dependencies:** Phases 3, 5, 6 (needs recordable meetings with summaries and live status to display against).
- **Backend changes:** none (uses Phase 2/5 APIs).
- **Frontend changes:** all list/detail screens.
- **Tests:** Vitest for card/detail rendering states (empty, processing, completed, failed); manual verification of search/filter/sort, empty state, error/recovery UI per G.1 and K.
- **Completion criteria:** a user can go Home → Quick Start → record → stop → (optional context) → watch processing → view detail with summary+transcript+playback → return to History and see the new card, entirely through the UI.

### Phase 8 — Polish, accessibility, docs
- **Objective:** close out the review items not covered by earlier phases' functional work.
- **Work:** `aria-live` regions for state changes, `aria-label`s on icon controls, dark/light contrast check on status pills, mobile layout pass on Recorder and Detail, stale-recording sweep job (K row 1), navigation entry in `AppSidebar`.
- **Files:** touches across Phase 3/7 components; `frontend/src/components/AppSidebar.tsx`; a new scheduled job registered in `hooks.py`'s scheduler events for stale-recording cleanup.
- **Dependencies:** Phases 3-7 complete.
- **Backend changes:** one scheduled cleanup job.
- **Frontend changes:** accessibility/responsive fixes across existing new components.
- **Tests:** manual accessibility pass (screen reader spot-check on state announcements), manual mobile-viewport pass.
- **Completion criteria:** all Section G.2 prioritized items verifiably present in the running app.

---

## M. Dependency Map

```
Phase 1 (Data model + App manifest)
   │
   ├──> Phase 2 (Recording ingest backend)
   │        │
   │        ├──> Phase 3 (Recorder frontend)        ─┐
   │        │                                          │
   │        └──> Phase 4 (Transcription pipeline)      │
   │                 │                                  │
   │                 └──> Phase 5 (Summary generation)  │
   │                          │                          │
   │                          └──> Phase 6 (Realtime processing feedback)
   │                                     │                │
   │                                     └────────────────┴──> Phase 7 (Detail & History UI)
   │                                                                   │
   └───────────────────────────────────────────────────────────────> Phase 8 (Polish/a11y/nav)
```

- **Parallelizable:** Phase 3 (Recorder frontend) and Phase 4 (Transcription pipeline) can proceed in parallel once Phase 2 lands — Phase 4 only needs `Meeting Recording Chunk` rows to exist (can use test fixtures), not a working recorder UI.
- **Strictly sequential:** Phase 1 → Phase 2 (schema must exist before ingest APIs); Phase 4 → Phase 5 (summary needs a transcript); Phases 4+5 → Phase 6 (nothing to report progress on until jobs exist); Phase 3+5+6 → Phase 7 (detail UI needs real data flowing).
- **External dependency per phase:** Phase 1 depends on nothing new (existing Frappe DocType tooling). Phase 2 depends on `audio_service.py` (existing, unmodified). Phase 4 depends on `transcribe_audio`/AI Model + AI Provider being configured for Gemini (existing provider abstraction, admin-configured, not code). Phase 5 depends on `run_agent_sync`/`Agent`/`Agent Run` (existing, unmodified). Phase 6 depends on the existing Socket.io namespace (unmodified transport, new event types only). Phase 7 depends on the existing dashboard list kit (`FilterBar`/`GridView`/`ItemCard`/`useInfiniteScroll`, unmodified).

---

## N. Final Implementation Checklist

**Data & seeding**
- [ ] `Meeting` DocType created with fields per C.1, `is_system_owned` guard, restricted delete permission
- [ ] `Meeting Recording Chunk` DocType created with fields per C.2, same protection pattern
- [ ] `HUF App` manifest record seeded for Meeting Recorder (route, icon, category, permission_method)
- [ ] `Meeting Summary Agent` seeded (`is_system=1`, Gemini AI Model link) via idempotent `install.py` function
- [ ] DocType constants added to `frontend/src/data/doctypes.ts`

**Backend APIs**
- [ ] `meeting_api.py`: create/start/pause/resume/stop/list/get/update_context/retry_chunk_transcription/retry_summary
- [ ] `meeting_recording.py`: `upload_chunk` (reuses `audio_service` validation)
- [ ] `meeting_transcription.py`: `transcribe_meeting_chunk` background job (reuses `transcribe_audio_file`/`resolve_stt_config`)
- [ ] `meeting_summary.py` + `finalize_meeting` job (reuses `run_agent_sync`, links `Agent Run.reference_doctype/name`)
- [ ] Stale-recording cleanup scheduled job registered in `hooks.py`

**Realtime**
- [ ] `meeting_chunk_uploaded` and `meeting_processing_status` event types added to the existing Socket.io emission points and to the typed frontend event union

**Frontend**
- [ ] `useMeetingRecorder.ts` — MediaRecorder chunking, IndexedDB retry queue, pause/resume/mute/stop logic
- [ ] `MeetingRecorderPage.tsx`, `RecorderTimer.tsx`, `RecorderControls.tsx`, `RecordingStatusPill.tsx`
- [ ] `NewMeetingDialog.tsx`, `PostMeetingContextPanel.tsx`
- [ ] `MeetingProcessingStatus.tsx` + `useMeetingProcessingSocket.ts`
- [ ] `MeetingsPage.tsx`, `MeetingsHeaderActions.tsx`, `MeetingCard.tsx` (reusing `FilterBar`/`GridView`/`ItemCard`/`EmptyState`/`useInfiniteScroll`)
- [ ] `MeetingDetailPageWrapper.tsx`, `MeetingDetailPage.tsx`, `MeetingSummaryPanel.tsx`, `MeetingTranscriptPanel.tsx`, `MeetingRecordingPlayer.tsx`
- [ ] `services/meetingApi.ts`, `types/meeting.types.ts`
- [ ] Routes registered in `App.tsx`; nav entry in `AppSidebar.tsx`
- [ ] `aria-live` state announcements; `aria-label`s on icon-only controls; mobile layout pass on Recorder + Detail

**UX copy discipline**
- [ ] No internal-mechanism terms ("chunk", "segment", "SSE", "doctype") leak into user-facing copy anywhere in the above (CLAUDE.md rule 21)

**Testing**
- [ ] Backend: DocType permission tests, chunk upload validation tests, transcription job retry/failure tests, summary prompt-assembly tests, finalize ordering/gap-marker tests
- [ ] Frontend: Vitest for `useMeetingRecorder` chunk logic and detail/card render states
- [ ] Manual: full golden-path browser run (Quick Start → record → pause/resume/mute → stop → skip context → watch processing → view detail → return to history), refresh-mid-recording recovery, forced chunk-upload failure recovery, forced transcription/summary failure + retry, mobile viewport pass

**Completion gate**
- [ ] All Phase 1-8 completion criteria (Section L) met
- [ ] All Section G.2 prioritized UX changes verifiably present
- [ ] All Section K error/recovery conditions manually exercised at least once
