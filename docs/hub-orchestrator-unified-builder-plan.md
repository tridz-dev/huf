# HUF Hub Orchestrator — Unified Conversational Agent and App Builder

Status: architecture/investigation document. Grounded against `origin/pre-dev` as of
2026-08-24 (post-#645 `analytics: fix token accounting...`, includes #640
`feat/lazy-tool-discovery` and #641 `feat/structured-render-tools`, both merged
2026-08-23).

Every claim below is sourced from the actual repository. File:line references point at
this worktree checkout. Where a concept does not exist in code, that is stated
explicitly rather than assumed.

---

## A. Current-State Architecture

### A.1 Hub Orchestrator (system Agent)

- **Seed file**: `huf/huf/agents/hub-orchestrator.json` — `agent_name: "Hub Orchestrator"`,
  `is_system: 1`, `allow_chat: 1`, `persist_conversation: 1`, `persist_user_history: 0`,
  `allow_guest: 0`, `prompt_mode: "Local"`. Provider/model are deliberately absent from
  the seed file itself.
- **Provisioning**: `huf/ai/app_seeding/hub_orchestrator.py`.
  - `create_hub_orchestrator_agent()` (:174) is idempotent — inserts on first run,
    otherwise calls `provision_hub_orchestrator()` + `ensure_hub_orchestrator_tools()`.
  - Provider/model auto-selection: `_find_keyed_provider()` (:131) picks the
    oldest `AI Provider` with a present `api_key` (presence-only check via
    `_provider_has_key`, :120 — never reads/logs the value); `_default_model_for_provider()`
    (:139) picks a chat model using an ordered `PREFERRED_MODELS` list (:30-41),
    skipping `DEPRECATED_MODELS` (:43-48) and non-chat markers (:51).
  - Enablement: if a keyed provider+model is found, `disabled = 0`; else a placeholder
    provider/model is assigned purely to pass validation and `disabled = 1` (:158-216).
    Auto-recovery: `on_ai_provider_update()` (:261), hooked as
    `doc_events["AI Provider"]["on_update"]` (`hooks.py:212`), re-provisions whenever any
    `AI Provider` is saved with a non-empty key.
  - Writes happen under a `_seeding_flag()` context (:100) so the Agent controller's own
    tamper-guards (A.1.2) don't block automated seeding.
  - Called from `huf/install.py:after_install` (:106) and `after_migrate` (:196).
- **Tool attachment at seed time**: `BUILDER_TOOL_NAMES` (`hub_orchestrator.py:55-68`) =
  `create_huf_table, list_table_rows, add_table_row, update_table_row, delete_table_row,
  draft_agent, update_agent_prompt, attach_agent_tools, publish_agent, create_agent_tool,
  list_provider_options, ask_user`. `_attach_builder_tools()` (:71) appends each name to
  the agent's `agent_tool` child table only if a matching `Agent Tool Function` already
  exists — i.e. tool sync must run first.
- **System-agent protections** (`huf/huf/doctype/agent/agent.py`):
  - `_validate_system_field_tamper()` (:226) — only System Managers (or
    seeding/install/migrate flags) may flip `is_system`.
  - `_validate_system_agent_immutability()` (:247) — for `is_system=1` agents, locks
    `instructions, agent_prompt, prompt_mode, provider, model, disabled, allow_chat,
    persist_conversation, persist_user_history, enable_multi_run` plus diffs the
    `agent_tool`/`default_plan` child tables, throwing for non-admins.
  - `on_trash()` (:469) / `before_rename()` (:477) — system agents cannot be
    deleted/renamed outside install/migrate/uninstall.
  - `get_permission_query_conditions()` (:19) — hides `is_system=1` agents from list
    views for non-admins (`AND is_system = 0`).
  - Mirrored at the tool layer: `_check_system_agent_editable()` (`builder.py:74`) throws
    unless `System Manager`, applied before mutating an `is_system` agent via
    `update_agent_prompt`/`attach_agent_tools`/`publish_agent`.
- **Runtime access is separate from edit protection**: `check_agent_access()`
  (`huf/ai/agent_access.py:11`) — because Hub Orchestrator ships with empty
  `allowed_users`/`allowed_roles`, *any authenticated user* can chat with it; `is_system`
  only guards configuration, not conversational use.
- **Frontend exposure**: root route `/` renders `HubSimplePage`
  (`frontend/src/App.tsx:92,159`), which hardcodes `agent: 'Hub Orchestrator'`
  (`frontend/src/pages/HubSimplePage.tsx:128`) and checks `getHubReadiness()` before
  allowing send. `useChatAgentIdentity.ts:7` also hardcodes
  `DEFAULT_COLD_START_AGENT = 'Hub Orchestrator'`. Backend readiness/status:
  `huf/ai/hub_api.py` (`get_hub_readiness`, `get_provider_status`,
  `get_model_catalog_proposals`, `approve_model_proposals`).
- **Conversation persistence**: `Agent Conversation` / `Agent Message` DocTypes (A.3),
  gated by the seed's `persist_conversation: 1` / `persist_user_history: 0`.

### A.2 Existing Hub builder tool layer

All handlers in `huf/ai/tools/builder.py` (+ `huf/ai/tools/ask_user.py`), registered via
a static `BUILDER_TOOLS` list in `huf/ai/tools/_registry.py:1013-1230`
(`category: "Builder"`), synced into `Agent Tool Function` records by
`sync_discovered_tools()` (`huf/ai/tool_registry.py:363`, `types: "App Provided"`).

| Capability | Function | Location |
|---|---|---|
| Create HUF table | `create_huf_table(table_name, fields, ..., confirm=False)` | `builder.py:141` |
| List table rows (read-only) | `list_table_rows(table_name, filters=None, ...)` | `builder.py:584` |
| Add table row | `add_table_row(table_name, data, confirm=False)` | `builder.py:626` |
| Update table row | `update_table_row(table_name, row_name, data, confirm=False)` | `builder.py:658` |
| Delete table row | `delete_table_row(table_name, row_name, confirm=False)` | `builder.py:702` |
| Draft Agent | `draft_agent(agent_name, provider, model, instructions, ..., confirm=False)` | `builder.py:242` |
| Update Agent prompt | `update_agent_prompt(agent_name, instructions=None, ..., confirm=False)` | `builder.py:314` |
| Attach tools (full-replace) | `attach_agent_tools(agent_name, tool_names, confirm=False)` | `builder.py:365` |
| Publish Agent | `publish_agent(agent_name, confirm=False)` (flips `disabled` 1→0) | `builder.py:408` |
| Create Agent Tool (declarative only) | `create_agent_tool(tool_name, description, types, reference_doctype, ..., confirm=False)` | `builder.py:456` |
| Discover providers (presence-only) | `list_provider_options()` | `builder.py:734` |
| Ask user (HITL, formatting convention) | `ask_user(question, kind, options=None, ...)` | `ask_user.py:89` |

**Two-phase preview → confirm → mutate**: every mutating tool takes `confirm: bool = False`
(coerced via `_as_bool()`, `builder.py:96`). `confirm=False` computes and returns a
`diff` with `confirm_required: True` and touches nothing; `confirm=True` re-runs the same
diff computation and applies the mutation. Implemented independently per tool (no shared
base class) in `create_huf_table`, `draft_agent`, `update_agent_prompt`,
`attach_agent_tools`, `publish_agent`, `create_agent_tool`, `add_table_row`,
`update_table_row`, `delete_table_row`. This exact contract is what any new App-builder
tool must replicate — see D.

**Security properties already present** (preserve, do not re-invent):
- `_require_builder_capability()` (`builder.py:48`) — throws unless
  `System Manager`/`Huf Manager` in `frappe.get_roles()` (`BUILDER_ROLES`, :23).
- `_require_doc_permission()` (`builder.py:85`) — layers `frappe.has_permission()` on
  top of the role check, per DocType/name.
- Declarative-only tool creation: `create_agent_tool()` restricts `types` to
  `_DECLARATIVE_TYPES` (:33-45 — CRUD/Get List/Get Value/Set Value only) and rejects
  `_FORBIDDEN_TOOL_FIELDS = ("function_path", "base_url", "http_headers")` (:28) if
  passed via kwargs — chat-created tools can never wire arbitrary code/HTTP. (The Hub
  Orchestrator's *own* built-in tools do use `function_path`, but that surface is
  reviewed/shipped code registered via `_registry.py`, not something chat can add to.)
- Secret isolation: `list_provider_options()` and `_provider_has_key()` return only a
  `bool`; the `api_key` value never leaves `get_password()`. Broader precedent:
  `huf/ai/hub_api.py:18-19,143` and `huf/ai/tools/builder.py:12-13,57-64` both document
  and implement "presence-check only, never return the secret."
- Tests: `huf/ai/tests/test_builder_tools.py` (1029 lines) is the canonical test-shape
  precedent for any new builder tool — capability-gating tests, two-phase
  preview/confirm tests, system-agent-lock tests, forbidden-field rejection tests.

### A.3 Agent / conversation / run / tool-call model

- **Agent** DocType (`huf/huf/doctype/agent/agent.json`) has **no draft/publish status
  field** — only `disabled` (Check) and `is_system` (protected flag). There is no
  `workflow_state`/`Draft`/`Published` select. "Publishing" in the builder-tool sense
  (`publish_agent`) just flips `disabled` 1→0.
- **Agent Conversation** (`agent_conversation.json`): `status`
  (`Active|Hidden|Archived|Trashed|Deleted`), `agent`, `session_id`, `channel`,
  `external_id`, `conversation_data` (JSON — existing plumbing for ephemeral
  per-conversation state, already used by lazy tool discovery, A.6).
- **Agent Message** (`agent_message.json`): `kind`
  (`Message|Tool Call|Tool Result|Status|Error|Image|Audio|Video`), `role`,
  `content_type` (`Text|JSX|Mermaid|Markdown|Artifact|HTML|Image`), `generated_image`,
  `generated_audio`, `generated_video` (all Attach), `context_policy`, `record_kind`,
  `visibility`.
- **Agent Run** (`agent_run.json`): one row per agent invocation, `parent_run`/`is_child`
  for sub-runs, full token/cost accounting, `run_kind` (`agent|tool|orchestrator`).
- **Agent Tool Call** (`agent_tool_call.json`): `agent_run`, `tool_args`/`tool_result`
  (JSON), `execution_kind`, `exit_status`, `resource_usage`, `limits_hit`.
- **Streaming**: Socket.IO channel `f"conversation:{conversation_id}"`, typed payloads
  (`agent_run_status`, `tool_call_started`/`completed`, `conversation_title_updated`,
  `sub_agent_completed`/`failed`, `open_artifact_pane`) emitted from
  `huf/ai/agent_integration.py`, `huf/ai/providers/litellm.py:1133-1145,1784-1900+`.
  Frontend: `frontend/src/hooks/useChatSocket.tsx:108` routes on `data.type`.
- **Ask User / HITL — two distinct, non-overlapping mechanisms**:
  1. `ask_user` tool (`huf/ai/tools/ask_user.py:89`) is **not a real pause/resume state
     machine** — it validates against `ASK_USER_KINDS` and returns a fenced
     ` ```ask-user``` ` block the model is instructed to emit and then stop generating.
     The frontend renders it as a card; the "pause" is purely conversational — the run
     ends normally and the next user message is a new turn.
  2. `Agent Execution Approval` DocType (`agent_execution_approval.json`) is the actual
     approval-gated mechanism (`status: Pending|Approved|Rejected|Expired`), used for
     elevated-risk tools (code execution, SSH) — not currently used for App-builder
     confirmation, since builder tools use the `confirm` two-phase pattern instead.
- **Tool dispatch**: `huf/ai/sdk_tools.py:create_agent_tools()` (:132) builds the SDK
  tool set for a run, merging MCP tools with native tools from
  `PermissionAwareToolRegistry.get_allowed_tools()`. Execution:
  `huf/ai/providers/litellm.py:_execute_tool_call()` (:272-295).

### A.4 Multimodal capability map (as implemented today)

| Capability | Status | Key files |
|---|---|---|
| Audio TTS (generation) | **Implemented** | `huf/ai/handlers/media.py:handle_generate_audio` (~:591), via LiteLLM `speech()` |
| Audio STT (transcription) | **Implemented** | `huf/ai/handlers/media.py:handle_transcribe_audio` (:842), `huf/ai/audio_service.py` (803 lines), `huf/ai/audio_api.py` |
| Image generation | **Implemented** | `huf/ai/handlers/media.py:handle_generate_image` (:38), per-provider default model map |
| OCR / vision documents | **Implemented** | `huf/ai/handlers/media.py:handle_ocr_document` (:316), `huf/ai/ocr_engine.py`, gated by `Agent.enable_ocr` + model `OCR`/`Vision` modality |
| File/image upload in chat | **Implemented** | `huf/ai/agent_chat.py` (`upload_file_and_process*`, `upload_audio_and_transcribe*`), 25MB hard cap (`_validate_web_file_upload`) |
| Realtime/pipeline voice calls | **Partially implemented, documented gaps** | `huf/ai/voice/` — `engines/elevenlabs.py`, `engines/litellm_realtime.py`; `send_to_session` unimplemented on both engines; litellm_realtime never persists user speech; ElevenLabs persistence depends on a webhook with no fallback; neither engine injects Agent memory (per `huf/ai/voice/README.md`) |
| Video (generation/analysis) | **Not implemented** — schema/frontend-only | `Agent Message.generated_video` field + `kind: "Video"` exist; `frontend/src/components/ai-elements/video.tsx` renders it; **no backend `handle_generate_video`**, no `Video` option in `AI Model.modalities` (`Text|Image|Text-to-Speech|Transcription|Embeddings|Vision|OCR|Speech-to-Speech`) |
| Provider/model capability declaration | **Implemented** | `AI Model.modalities` (Select/CSV), per-model kill-switches `disable_ask_user`/`disable_rich_elements`/`disable_document_artifacts` |

### A.5 HUF App architecture — exactly one system, fully mapped

There is **one** App concept in this codebase: the **HUF App registry**
(`huf.ai.app_seeding.apps_loader` + `huf.ai.apps_api` + `HUF App` DocType +
`frontend/src/pages/AppsPage.tsx`). It is **a launcher/registry for independently
installed Frappe apps that declare a manifest** — not a no-code app builder, and
**not linked to `Agent` by any field in either direction**. No second/legacy App system
exists (confirmed by full-field inspection of both DocTypes).

- **DocType**: `huf/huf/doctype/huf_app/huf_app.json` — `autoname: "field:app_id"`.
  Fields: `app_id` (unique), `title`, `description`, `route` (reqd, **not** unique),
  `icon` (Data — site-local asset path or bare identifier, not an Attach field),
  `category`, `sort_order`, `version`, `launch_mode` (Select, only `"Route"` supported
  today), `required_huf_version` (declared but **never enforced anywhere**),
  `permission_method`, `exposed_tables` (read-only, comma-joined DocType names),
  `enabled`, plus read-only sync metadata (`source_app`, `source_file`,
  `manifest_hash`, `last_synced_at`, `sync_status`). DocType permissions: `System
  Manager` only — all other read access happens in application code (below).
  Controller `huf_app.py` is a bare `Document` subclass, no lifecycle hooks; docstring:
  *"Records are created and maintained by the app-seeding sync... they are discovered,
  not user-authored."*
- **Manifest grammar**: `huf/ai/app_seeding/apps_loader.py` — `ALLOWED_FIELDS` (:45-60),
  `SUPPORTED_MANIFEST_VERSION = 1` (:22), `validate_manifest()` (:195-278). Provenance
  fields (`source_app`, `source_file`, `manifest_hash`) are **forbidden in the manifest
  itself**, always server-derived (sha256 over the normalized JSON,
  `compute_manifest_hash`, :281-284).
- **Creation**: never a direct "create app" API — apps are **discovered from files on
  disk** at `<installed_app>/huf/apps/*.json` (flat, non-recursive;
  `huf/ai/app_seeding/scanner.py:5-49`). Core upsert: `upsert_huf_app()`
  (`apps_loader.py:287-364`). Batch driver: `sync_huf_apps()` (:450-513), whitelisted at
  `huf/ai/apps_api.py:184-196` (System Manager only). **No `draft_app`/`publish_app`
  tool exists analogous to `draft_agent`/`publish_agent`.**
- **Installation** = installing an ordinary Frappe app on the bench that ships a
  `huf/apps/*.json` manifest — no separate HUF-level install/uninstall action exists.
  `hooks.py:114-118` (`after_app_install`) → `seeder.on_app_installed()` seeds that
  app's manifests immediately; `hooks.py:148` (`after_app_uninstall`) →
  `apps_loader.on_app_uninstalled()` **hard-deletes** every `HUF App` row with matching
  `source_app`. `after_migrate` (`install.py:200-208`) re-runs `sync_huf_apps()` +
  `cleanup_orphaned_apps()` on every migrate. Frontend copy makes this explicit:
  *"Apps are installed server-side with bench and discovered automatically... Nothing is
  ever installed from this screen"* (`AppsPage.tsx:253-256`).
- **Registry/catalog**: `get_huf_apps()`/`get_huf_app()` (`apps_api.py:108-181`, no
  `allow_guest`, both require a session) return only `SAFE_FIELDS = (app_id, title,
  description, route, icon, category, version)` (+ `exposed_tables`, + `enabled` for
  admins). `_can_user_see()` (:62-83): hidden entirely if `sync_status != "Active"`;
  admins see all Active regardless of `enabled`; else `enabled=0` hides it; else a
  declared `permission_method` decides (fails closed); else requires a non-Guest,
  authenticated user with capability `agent.use`. Frontend: `AppsPage.tsx` — card grid,
  route `/apps` (`App.tsx:177-188`); cards are **plain `<a href>` anchors doing
  full-page navigation — never an iframe, never SPA router navigation**
  (`AppsPage.tsx:57-59,224-228`).
- **Agent-to-App relationship: none.** No Link field either direction. `Agent.source_app`
  is seeding-provenance (same convention as `HUF App.source_app`), not a reference to a
  specific App record. App creation never reads/clones Agent data.
- **Icon**: plain Data string, not Attach — either a site-local asset path (served from
  the provider app's own `public/` assets) or a bare identifier that **no code currently
  resolves** to an actual icon; frontend falls back to a generic `AppWindow` icon on any
  non-path value or load failure.
- **Versioning/enable-disable/uninstall**: `version`/`required_huf_version` stored but
  unenforced; `enabled` toggled via `set_huf_app_enabled()` (System Manager only),
  "manual-disable-wins" on re-sync (`values.pop("enabled", None)` before update,
  :353-356); no soft-delete — orphaned/uninstalled apps are hard-deleted
  (`frappe.delete_doc(..., force=True)`), `sync_status: "Missing"` is declared but never
  actually set (MVP behavior is documented as "delete, do not mark Missing").
- **Seeded/default Apps**: **none today** — zero `huf/apps/*.json` files exist anywhere
  in the current worktree; the registry is empty on a fresh install.
- **Runtime loading**: none beyond the catalog list fetch — once a user clicks through,
  the destination app's own independent frontend takes over entirely. No App-specific
  dynamically-defined tools exist; "App Provided" tool type (`_registry.py`) is a
  separate, unrelated concept (tools *contributed by* an installed app, not scoped to a
  `HUF App` record).

### A.6 Recent token-efficiency precedent (PRs #640, #641 — merged 2026-08-23)

These two merged-yesterday PRs are the direct precedent for the design-system/token-cost
requirement (see D.3):

- **#640 `feat/lazy-tool-discovery`** — `huf/ai/tools/lazy_discovery.py` +
  `Agent.enable_lazy_tools` (Check, default off, strictly additive/opt-in). Instead of
  building a full JSON schema for every allowed tool on every run
  (121 tools across `ALL_INTEGRATION_TOOLS`, one integration group alone has 45), the
  model sees 4 discovery tools: `list_tool_groups → describe_tool_group → load_tools`,
  or `search_tools → load_tools` directly. `load_tools` **re-validates every requested
  tool name against `PermissionAwareToolRegistry.get_allowed_tools()` before granting
  it** — never trusts the model's request, so it cannot be used to discover/leak schemas
  for tools the agent lacks permission for. Discovered tools cache in
  `Agent Conversation.conversation_data["_lazy_tools"]` and promote to eager on the next
  `create_agent_tools()` call. MCP tools are explicitly **out of scope** for this PR
  (still always eager — flagged as the single biggest remaining token cost).
- **#641 `feat/structured-render-tools`** — `huf/ai/tools/render_tools.py`. New
  `render_mermaid`/`render_chart` tools: the model passes small structured JSON
  (nodes/edges, or chart data/series); the backend **deterministically templates** the
  exact same `<artifact type="mermaid">`/`<artifact type="chart" language="jsx">` markup
  a model would otherwise hand-author — zero frontend/DocType changes, since from
  `ArtifactRenderer.tsx`'s point of view nothing changed. When these tools are attached,
  the ~30-line syntax-teaching prompt instructions (`chart_artifact_instructions.py`)
  are swapped for a one-line "call the tool instead" note. Security fix during review:
  templated attribute values (`title`/`x_key`/`series_keys`/`colors`) are escaped
  (`_escape_artifact_attr`/`_escape_jsx_attr`) because the frontend's artifact parser
  uses plain regexes that stop at the first unescaped `>`/quote.
- Both PRs insert into `huf/ai/tools/_registry.py` at the same point (documented,
  trivially-resolvable textual conflict) — a third insertion here (App-builder tools) is
  a natural, precedented extension point.

### A.7 Design system, generative-UI constraint mechanism, Knowledge/Skill, and seeding

- **Design system**: shadcn/ui, configured via `frontend/components.json` (style
  `new-york`). `frontend/src/components/ui/` — 60+ primitives (Button, Card, Dialog,
  Table, Tabs, Accordion, Badge, Alert, Progress, Select, Combobox, Sidebar, Chart,
  etc.). Separate `frontend/src/components/ai-elements/` for chat/agent-specific
  primitives (Artifact, AudioPlayer, Image, Video, Message, Tool, Reasoning, etc.).
  Canonical design tokens: `frontend/src/index.css:1-566` ("Apple-quiet v3.0", the *sole
  shipped* direction as of 2026-08-21 — comment explicitly marks the older
  `[data-theme=...]` blocks as dead code). Root `DESIGN.md` (446 lines) documents the
  **stale** v2.0 direction and should not be treated as current. No Storybook/MDX
  component-prop doc exists anywhere in the repo.
- **Generative-UI constraint mechanism — the direct precedent for D.1**: the "artifact"
  system, enforced **twice**:
  1. Server-side prose instructions injected into the system prompt:
     `huf/ai/artifact_instructions.py` (`AI_ELEMENT_INSTRUCTIONS`),
     `huf/ai/chart_artifact_instructions.py` (`CHART_ARTIFACT_INSTRUCTIONS` — hard-lists
     allowed layout tags and allowed Recharts components), assembled conditionally in
     `huf/ai/agent_integration.py:518-562` based on `capability_enabled(...,
     "rich_elements"/"document_artifacts")` and whether the agent has `render_chart`/
     `render_mermaid` tools attached.
  2. Client-side hard whitelist: `frontend/src/components/ui/jsx-preview.tsx` uses
     `react-jsx-parser` with an explicit `availableComponents` map (:170-260+) — a plain
     JS object, not a JSON Schema/Zod schema. Only names present in this map render when
     the model emits raw JSX; anything else is inert.
  `Artifact.artifact_type` (DocType Select) and `VALID_ARTIFACT_TYPES`
  (`huf/ai/artifact_extraction.py:39-52`) must mirror each other by explicit code
  comment.
- **Knowledge Source / RAG**: fully implemented, general-purpose pipeline.
  `Knowledge Source` DocType (10 backend types: sqlite_fts/vec/hybrid, chroma, pgvector,
  redis, zvec, weaviate, faiss, pinecone; `scope: Site|Workspace|Agent|Global`),
  `Knowledge Input` (per-document ingestion unit), `Agent Knowledge` (child table linking
  Agent → Knowledge Source, `mode: Mandatory|Optional`, `max_chunks`, `token_budget`).
  Pipeline: `huf/ai/knowledge/{extractors,chunkers,backends}/`, `indexer.py`,
  `context_builder.py:build_knowledge_context()` (injects mandatory-source context before
  agent execution).
- **Skill mechanism**: a real, distinct DocType — `Skill`
  (`huf/huf/doctype/skill/skill.json`) — a reusable bundle of tools + knowledge + prompts
  + MCP servers (`skill_tools`, `skill_knowledge`, `skill_prompts`, `skill_mcp_servers`
  child tables), `source_type: Local|Git|Common Destination|App Provided`, `auto_load`.
  Agents attach via `agent_skill` child table (`mode: Mandatory|Optional`).
  `huf/ai/skills/loader.py:get_mandatory_skill_knowledge()` feeds into
  `context_builder.py`.
- **Critical gap for the design-system/token-cost requirement**: `huf` **never seeds its
  own Knowledge Source**. The `huf/ai/app_seeding/` pipeline
  (`scanner.py:find_seed_dirs()` explicitly skips `if app == "huf": continue`, :15) only
  ingests `<other_app>/huf/{prompts,tools,knowledge,agents,triggers,apps}/*.json` — it
  seeds content *from* other installed apps *into* Huf, not Huf's own reference content.
  The only content actually self-seeded identically into every install today is: Skill
  Categories (hard-coded Python list), Memory Policies (hard-coded Python list), builtin
  Agent Tool Function records, and the Hub Orchestrator Agent itself (from
  `huf/huf/agents/hub-orchestrator.json`). `huf/huf/prompts/demo-assistant.json` is a
  **template/example** referenced only in a docstring, not live seed data.
  **Conclusion**: shipping a design-system reference "that will exist in whatever
  installation" (per the requirement) needs a **new, small self-seed step**, following
  the *exact same pattern already proven for the Hub Orchestrator Agent itself*
  (versioned JSON in `huf/huf/`, idempotent upsert function, called from
  `after_install`/`after_migrate`) — not a new mechanism.

### A.8 Guest/public access precedent (Agent embed) — grounds the "public App" requirement

- `Agent.embed_enabled` (Check) / `Agent.publishable_key` (`pk_<32-char hash>`, generated
  once by `_ensure_publishable_key()`, `agent.py:134-141`, self-healing on every
  `validate()`, never regenerated) / `Agent.allowed_origins` (newline-separated origin
  list) exist on the Agent DocType, **but are consumed by exactly one code path**: the
  **voice** embed flow, `huf/ai/voice/api.py:start_public_session()` (:282-342).
  - Looks up the Agent by name, constant-time-compares
    (`hmac.compare_digest`) the supplied key against `agent_doc.publishable_key`
    (identical error message on both "agent not found" and "key mismatch" — deliberate
    anti-enumeration), requires `embed_enabled` truthy, then still funnels through
    `assert_agent_access(agent_doc, user="Guest")` (:321) — i.e. `allow_guest` on the
    Agent is *still* required on top of the key.
  - Origin check: `_origin_allowed()` (:244-266) compares
    `(scheme.lower(), netloc.lower())` tuples exactly (not substring) against
    `allowed_origins` lines. Documented caveat: the actual
    `Access-Control-Allow-Origin` response header is emitted centrally by Frappe's own
    `allow_cors` site-config, independently of this field — `allowed_origins` is "a
    second, per-Agent gate on top of that, not a replacement for it." **No
    X-Frame-Options/CSP handling exists anywhere in the repo.**
- **`publishable_key` has no equivalent lookup for text/chat** — it appears nowhere in
  `chat_api.py`, `agent_integration.py`, or `agent_chat.py`. Text-chat guest access
  (`run_agent_sync`, `run_agent_sync_chat`, `get_agent_run_status`) gates **solely** on
  `agent_doc.allow_guest` via the shared `check_agent_access()`
  (`huf/ai/agent_access.py:10-49` — *"Guest access depends solely on allow_guest;
  allowed_users/allowed_roles are never consulted for Guest"*) — no key/origin check at
  all on that path today.
- **No React/SPA embed route exists** (`embed`/`publishable_key`/`widget` all return zero
  hits under `frontend/src`). Two separate non-React surfaces instead:
  `huf/public/js/huf-voice.js` (dependency-free JS bundle for third-party sites, mints a
  voice session only) and `huf/www/agent_chat.html` (standalone static page, auth via
  session CSRF cookie only, **does not use `publishable_key`/`allowed_origins` at all**).
- **Website-layer routing** (`huf/hooks.py:62-79`, `website_route_rules`):
  ```
  /huf/sw.js, /huf/manifest.json, /huf/stream/ping,
  /huf/stream/<path:agent_name>, /huf/stream, /huf/docs, /huf/docs/<path:app_path>,
  /mcp-oauth-callback, /huf, /huf/<path:app_path>
  ```
  `page_renderer = ["huf.ai.agent_stream_renderer.AgentStreamRenderer"]` handles the SSE
  stream routes; agent-level auth happens *inside* `run_agent_stream`, not in the
  renderer's `can_render()`. `huf/www/huf.py:get_context()` (:18-43) already branches on
  Guest vs. authenticated to serve the right boot data for the SPA shell at `/huf/*` —
  i.e. **the SPA shell is already Guest-servable**; per-screen/action authorization is
  enforced client-side/per-API-call, not by this website controller.
- **`HUF App.route`** (A.5) is validated as a site-local absolute path
  (`_validate_route`) but is **not marked unique** in the DocType JSON, has **no
  server-side route registration** mapping it to any controller (only ever rendered as
  a plain `<a href>` on the frontend), and `apps_api.py`'s `get_huf_apps`/`get_huf_app`
  have **no `allow_guest=True`** — so today's App registry itself requires a logged-in
  session end-to-end.

**Conclusion for A.8**: the closest existing precedent for "App at
`site.com/huf/app-alias`, guest-accessible" is the *combination* of (a) the
`website_route_rules` + `page_renderer` pattern already used for `/huf/stream/<agent>`,
(b) the Guest-branching already present in `huf/www/huf.py`, and (c) the
`allow_guest`/`check_agent_access` gate already used for text-chat guest access on
Agent. The `publishable_key`/`allowed_origins`/origin-check machinery exists but is
voice-only today and would need to be generalized (or a parallel, simpler `is_public` +
route-uniqueness check added directly to `HUF App`, gated the same way Agent's
`allow_guest` already is) — see D.9.

---

## B. Capability Matrix

| Capability | Existing implementation | File(s) | API/tool | Reusable as-is? | Gap |
|---|---|---|---|---|---|
| Create Agent | `draft_agent` | `builder.py:242` | tool | Yes | none |
| Edit Agent | `update_agent_prompt`, `attach_agent_tools` | `builder.py:314,365` | tool | Yes | none |
| Publish Agent | `publish_agent` (flips `disabled`) | `builder.py:408` | tool | Yes | Agent has no draft/publish *state*, only `disabled` — acceptable, document as-is |
| Create Tool | `create_agent_tool` (declarative only) | `builder.py:456` | tool | Yes | none |
| Attach Tool | `attach_agent_tools` (full-replace) | `builder.py:365` | tool | Yes | full-replace semantics must be preserved/documented for App-builder callers |
| Create Table | `create_huf_table` | `builder.py:141` | tool | Yes | none |
| App creation | file-based manifest discovery only | `apps_loader.py:upsert_huf_app` | none (no tool) | No | **missing**: a `draft_app`/two-phase App-creation primitive |
| App installation | implicit (installing a Frappe app on the bench) | `apps_loader.py:on_app_installed`/`sync_huf_apps` | System-Manager-only API | No | **missing**: a HUF-level "install this Agent-backed App" action; today's "installation" is bench-level, not per-record |
| Agent → App | none | — | — | No | **missing entirely** — no Link field either direction |
| App icon | Data string (path or unresolved identifier) | `huf_app.json` | — | Partially | **missing**: Attach-based upload, generation, validated resolution of bare identifiers |
| File upload | `upload_file_and_process*` | `agent_chat.py` | API | Yes | none |
| Image generation | `handle_generate_image` | `handlers/media.py:38` | tool/handler | Yes | none |
| Audio input | `upload_audio_and_transcribe*` | `agent_chat.py` | API | Yes | none |
| Transcription | `handle_transcribe_audio`, `audio_service.py` | `handlers/media.py:842` | tool/handler | Yes | none |
| TTS/audio generation | `handle_generate_audio` | `handlers/media.py:591` | tool/handler | Yes | none |
| Audio playback | `AudioPlayer` component | `ai-elements/audio-player.tsx` | frontend | Yes | none |
| Video playback | `Video` component (renderer only) | `ai-elements/video.tsx` | frontend | Partial | **missing**: no backend generation/analysis; renderer alone can't be exposed as an App capability yet |
| Live voice | pipeline + provider-native engines | `huf/ai/voice/` | API | Partial | documented gaps: `send_to_session` unimplemented, user speech not persisted (litellm_realtime), no memory injection |
| Provider/API configuration | `AI Provider`/`AI Model` | doctype | API | Yes | none |
| Secrets | `Password` fieldtype + `get_password()` | multiple | — | Yes | none — strong existing pattern, must be followed exactly for any new credential-consuming App capability |
| Chat | full run/stream/persist pipeline | `agent_integration.py`, `litellm.py` | API | Yes | none |
| Ask User/HITL | formatting convention (not real pause) | `ask_user.py:89` | tool | Yes, with caveat | must be documented as non-blocking; do not assume it can gate App-builder confirmation |
| Design-system component rendering | artifact JSX whitelist (`jsx-preview.tsx`) + chart/mermaid deterministic tools (#640/#641) | multiple | tool + frontend | Yes, extend | **gap**: no tool yet for arbitrary shadcn component composition beyond charts/mermaid; see D.1 |
| Lazy tool discovery | `lazy_discovery.py`, opt-in per-Agent | `huf/ai/tools/lazy_discovery.py` | tool | Yes, extend | MCP tools explicitly out of scope in #640 — App-builder's own large tool surface should opt in, not invent a second lazy mechanism |
| Self-seeded reference Knowledge | none | — | — | No | **missing** — see A.7 conclusion, D.3 |
| Public/guest App routing | Agent embed (voice-only) + Guest-branching SPA shell | `voice/api.py`, `www/huf.py` | partial | Partial | **missing**: no guest path for `HUF App`, no alias/route uniqueness, `publishable_key` pattern not generalized to Apps |
| OCR (document/image extraction) | **Implemented** — `Agent.enable_ocr`, `handle_ocr_document`, PDF/image/office extraction | `huf/ai/ocr_engine.py`, `huf/ai/handlers/media.py:316` | tool/handler | Yes | not yet surfaced as an App-level `capabilities` flag (D.5) — same shallow gap as TTS/STT (Phase 8/9), not a missing capability |

### OCR — already implemented (correcting an earlier drafting error in this document)

An earlier pass of this document searched for the literal term "OTR" (a typo carried over
from the source requirement) and correctly found zero hits — that string genuinely does
not exist anywhere in the repository. The intended term was **OCR**, which is a
first-class, fully implemented capability (see A.4): `Agent.enable_ocr` (Check),
`AI Model.modalities` includes `OCR`/`Vision`, `huf/ai/ocr_engine.py` handles PDFs
(LiteLLM OCR endpoint / local extraction / vision), images (vision models), and
office/text documents (local extractors), dispatched via
`huf/ai/handlers/media.py:handle_ocr_document` (:316) and gated the same way file uploads
are (`huf/ai/agent_chat.py:_validate_web_file_upload`, A.4). There is nothing unresolved
here — the only remaining work is exposing this existing Agent-level capability as an
App-level `capabilities` flag (D.5), which is the same small task already planned for
audio TTS/STT in Phase 8/9, not a new pipeline. See Phase 8 in the phased plan below,
which now explicitly includes OCR/document-understanding alongside audio/transcription.

(If a genuinely distinct "OTR" concept — separate from OCR — was intended, the original
finding stands: zero hits anywhere in the repository, and that would need to come from
the requester directly rather than being invented here.)

---

## C. Duplication/Conflict Analysis

- **No duplicate App systems** — confirmed by full-field inspection (A.5). One System,
  one DocType, one API surface, one frontend page. Nothing to consolidate here.
- **Active, adjacent in-flight work — coordinate, do not collide**: there is a currently
  active track in the `huf_workspace_v2` coordination repo, `AppCapabilityDiscovery`
  (PR #596, branch `feature/app-capability-discovery`, base `develop`, draft as of
  2026-08-24), titled "App Capability Discovery & App-First Agent Builder V1
  (Phase 0-3)." It adds `huf/ai/capabilities/{apps,actions,resources,ranking,
  events,api,models}.py` and extracts a `resolve_function_descriptor`/
  `inspect_function_parameters` helper set out of `agent_tool_function.py`, plus a
  DocType-ownership-via-Module-Def helper it explicitly extracts *into* `apps_loader.py`
  — the same file this plan's Phase 2 (D.4/D.6) extends. It is solving a different
  problem (letting a human/LLM pick an *existing installed Frappe app's* resources/
  actions/events when building a Tool or Trigger, using `HUF App.exposed_tables` as the
  ranking signal) rather than this plan's problem (turning an Agent into a new,
  installable `HUF App` record). The two are complementary, not duplicative, but Phase 1
  of this plan must read PR #596's actual landed diff (not just this summary) before
  touching `apps_loader.py`, since both plans add functions to the same module and a
  naming/ordering conflict is the likeliest integration risk. Confirmed via
  `gh pr view 596 --repo tridz-dev/huf` and the `huf_workspace_v2` `TRACKS.md` index — no
  local clone of `huf_workspace_v2` was available in this environment, so its `CONTEXT.md`
  (git-ignored, per the workspace's own convention for active tracks) could not be read;
  only the committed `TRACKS.md` summary row and the PR body were inspected.
- **`publishable_key`/embed machinery is voice-only but named generically** — a future
  App-guest-access feature must decide explicitly whether to generalize this existing
  field set (adding a text/App-aware lookup path) or add App-scoped equivalents. Reusing
  the *pattern* (constant-time key compare, anti-enumeration error parity, origin
  allowlist) is strongly preferred over inventing a new one; reusing the *exact fields*
  onto `HUF App` risks conflating Agent-level embed concerns with App-level ones. See
  D.9 for the recommendation.
- **`AI Element` / rich-content prompt instructions exist in three near-duplicate
  shapes** (`artifact_instructions.py`, `chart_artifact_instructions.py`,
  `document_artifact_instructions.py`) already following a consistent "prose
  instructions vs. tool-call instruction" swap convention gated by
  `capability_enabled()`. A fourth ("design-system component instructions") should
  follow the exact same shape rather than a new pattern — see D.1.
- **Two duplicate `publishable_key` generation code paths exist**: the live one in
  `Agent.validate()` (`agent.py:134-141`) and a dead, unwired `doc_events` fallback in
  `huf/ai/voice/api.py:269-278` (explicitly documented as not wired into `hooks.py`).
  Not part of this project's scope to fix, but noted so it isn't mistaken for a second
  live mechanism.
- **`huf/permission.py` (singular) vs. `huf/permissions.py` (plural)** — two separate
  files; `permissions.py` is the real capability-role system
  (`CAPABILITIES`/`has_capability`), `permission.py` is an older, simpler
  `frappe.session.user == "System Manager"` check used in isolated spots. Any new
  App-builder permission check must use `permissions.py`'s `has_capability()`, not the
  legacy file.

---

## D. Target Architecture

**Principle** (unchanged from the requirement): Hub Orchestrator becomes the
conversational layer composing HUF's existing first-class primitives (Agent, Tool,
Table, Knowledge Source, AI Provider/Model) into a `HUF App` record — it does not
recreate the platform inside the Agent, and it does not duplicate business logic that
already exists in `apps_loader.py`/`apps_api.py`.

```
Hub Orchestrator (system Agent, unchanged identity)
        │  chat turn
        ▼
Lazy-discovered Builder Tools  (existing pattern, A.6/#640)
        │  two-phase confirm=False/True  (existing pattern, A.2)
        ▼
New App-domain service functions in huf/ai/app_seeding/apps_loader.py
  (extends the existing upsert_huf_app / validate_manifest / sync_huf_apps functions —
   does NOT bypass them; a chat-authored App is just another manifest source)
        │
        ▼
HUF App DocType (existing, additive fields only — D.5)
        │
        ▼
HUF App Runtime:
  - authenticated: existing AppsPage.tsx card → route (unchanged)
  - NEW: guest/public path, only if HUF App.is_public — D.9
        │
        ▼
Underlying Agent (existing chat/run/stream pipeline, unchanged) via the NEW
Agent link field on HUF App (D.5)
```

### D.1 Design-system-aware App rendering (user-added requirement)

Do not let the Hub Orchestrator (or an App's backing Agent) hand-author raw JSX against
the full 60-component shadcn library from memory. Extend the **existing** artifact
mechanism (A.7) exactly the way #641 extended it for charts/mermaid:

- New deterministic tool, e.g. `render_app_component(component, props, confirm=False)`
  in `huf/ai/tools/render_tools.py` (same file #641 already introduced), constrained to
  a **small, explicit allowlist** mirrored from `jsx-preview.tsx`'s existing
  `availableComponents` map — not the full 60. The tool deterministically templates
  the `<artifact type="chart" language="jsx">`-style markup (escaped via the same
  `_escape_jsx_attr` helper #641 added), so the LLM never free-forms component
  props/markup.
- A companion **read-only, no-confirm** discovery tool, e.g.
  `list_app_components()`, returning the same allowlist as structured JSON (name +
  accepted props + one short example each) — this is the "list of available fields,
  components allowed, APIs, examples" the requirement asks for, but served as a small
  deterministic tool response, not a giant prompt block.
- Both new tools are added to `BUILDER_TOOL_NAMES`/`_registry.py` following the existing
  `#640`/`#641` insertion point.

### D.2 Deterministic vs. LLM-decided actions (user-added requirement)

Per the requirement's own §26 ("agentic planning, deterministic execution") and the
concrete precedent in A.6: any action that has one correct shape given structured input —
appending a component, creating/attaching a Tool, installing an App, resolving a
provider — is implemented as a deterministic tool call (Python function producing exact
output from validated input), the same way `render_mermaid`/`render_chart` replaced
hand-authored diagram syntax. The LLM's job stays scoped to: deciding *which* deterministic
tool to call and with *what* structured arguments — never to hand-authoring the
component/App markup itself.

### D.3 Design-system reference as seeded Knowledge (user-added requirement)

Per A.7's conclusion, `huf` has no self-seeding mechanism for its own Knowledge Source
today. Add one, following the **exact** pattern already proven for Hub Orchestrator
itself (A.1):

- New versioned file `huf/huf/knowledge/design-system-reference.json` (or reuse the
  `Skill` shape — a `Skill` with `source_type: "App Provided"`, `provider_app: "huf"`,
  bundling `skill_knowledge` + `skill_tools` pointing at `list_app_components`/
  `render_app_component`) describing: allowed components, their props, 2-3 usage
  examples each, and pointers to the relevant existing builder tools/APIs.
- New idempotent seed function `huf/ai/app_seeding/design_system_skill.py` (mirrors
  `hub_orchestrator.py`'s shape: `create_design_system_skill()`, idempotent
  insert-or-update), called from `huf/install.py:after_install`/`after_migrate` right
  after `create_hub_orchestrator_agent()`.
- Attach this Skill/Knowledge Source to Hub Orchestrator's `agent_skill`/`agent_knowledge`
  child table at seed time, `mode: "Mandatory"` (it's small and always relevant to
  App-building) — following the same `_attach_builder_tools()`-style idempotent append
  already used for tools.
- This directly satisfies "seeded to whatever will exist always in all installations":
  it ships as part of `huf` itself (not the other-apps-only `app_seeding` pipeline),
  runs on every `after_install`/`after_migrate`, and needs no external app to be
  installed first.

### D.4 App creation as a first-class, two-phase builder capability

New handlers in `huf/ai/tools/builder.py` (or a new `huf/ai/tools/app_builder.py`
following the same module shape), each following the exact two-phase `confirm`
contract already proven in A.2:

- `draft_app(app_id, title, description, agent_name, route, category="Other",
  icon=None, confirm=False)` — validates `agent_name` resolves to an existing,
  accessible Agent (does **not** clone it); computes a diff against
  `validate_manifest()`'s existing normalization; on confirm, calls
  `upsert_huf_app()` directly (A.5) rather than duplicating its validation logic.
- `update_app(app_id, ..., confirm=False)` — same shape, updates an existing `HUF App`
  record's title/description/icon/category/capabilities (D.5 new fields).
- `install_app(app_id, confirm=False)` — see D.6/D.7; idempotent, retry-safe.
- `set_app_icon(app_id, source, confirm=False)` — see D.8.
- Discovery/read tools (no confirm): `list_apps()`, `get_app(app_id)`,
  `list_agents()`, `get_agent(agent_name)` — needed for Path B/C in the requirement
  ("turn my existing Agent into an App", "make that an App") since today's builder tools
  have no Agent/App discovery primitives at all, only creation ones.

All new tools: gated by the existing `_require_builder_capability()` +
`_require_doc_permission()` pair, added to `BUILDER_TOOL_NAMES`, and — because this adds
meaningfully to the tool-schema surface — attached to Hub Orchestrator with
`enable_lazy_tools=1` (A.6) rather than growing the always-eager set further.

### D.5 Data model changes — `HUF App` (additive only)

| Field | Type | Why | Migration |
|---|---|---|---|
| `agent` | Link → Agent | The missing Agent↔App relationship (A.5/B). Nullable — not every App needs to be Agent-backed on day one, but a chat-created App always sets it. | Additive, nullable, no backfill needed (no existing App records reference an Agent today) |
| `is_public` | Check, default 0 | Backs the guest-routing requirement (D.9) without overloading `enabled` (which already means "visible to authenticated users") | Additive, default 0 — zero behavior change for existing records |
| `alias` | Data, unique (nullable) | A validated, collision-checked public path segment, distinct from the existing free-text non-unique `route` — see D.9 for why `route` itself is insufficient | Additive; existing `route` values are untouched |
| `icon_source` | Select: `Path\|Uploaded\|Generated\|Default` | Makes icon provenance explicit (today `icon` is an ambiguous Data string) — needed for D.8's validation/retry logic | Additive; existing `icon` values default to `"Path"` on migration (a `patches.txt` data-migration, not a schema-breaking change) |
| `capabilities` | Small Text (JSON) | Composable capability flags (file input, audio input, TTS output, video output, live voice) per §24 of the requirement — see D.10 for why this is a flat JSON blob and not five new booleans | Additive, defaults to `{}` |

No changes to `Agent`, `Agent Message`, `Agent Conversation` schemas are required — the
existing `generated_video`/`kind: Video` fields already cover the App-output-rendering
side (A.4); the gap is entirely in the *generation* pipeline (Phase 10), not the schema.

### D.6–D.14

(Installation lifecycle, icon pipeline, capability validation, public routing, and the
remaining architecture questions from the original requirement §37–40 are answered in
the Phased Execution Plan below, each tied to the concrete phase that implements it, to
keep this document from restating implementation detail twice.)

---

## E. Hub Orchestrator Tool Contract Changes

| Tool | Status | Confirm? | Notes |
|---|---|---|---|
| `create_huf_table`, `list_table_rows`, `add_table_row`, `update_table_row`, `delete_table_row` | Retained unchanged | per A.2 | no change |
| `draft_agent`, `update_agent_prompt`, `attach_agent_tools`, `publish_agent`, `create_agent_tool` | Retained unchanged | per A.2 | no change |
| `list_provider_options`, `ask_user` | Retained unchanged | n/a | no change |
| `list_agents`, `get_agent`, `list_apps`, `get_app` | **New** — discovery/read | No | required for Path B/C (existing-Agent → App) |
| `draft_app`, `update_app` | **New** | Yes | mirrors `draft_agent`/`update_agent_prompt` shape exactly |
| `install_app` | **New** | Yes | idempotent — re-running with the same `app_id` must not duplicate records (D — Phase 6) |
| `set_app_icon` | **New** | Yes | source discriminated union: existing path / uploaded file id / generation prompt (D.8) |
| `list_app_components` | **New** — discovery/read | No | design-system reference, D.1 |
| `render_app_component` | **New** | Yes (persistent artifact) | deterministic templating, D.1/D.2 |

All new mutating tools: `_require_builder_capability()` + `_require_doc_permission()`,
same failure mode (`frappe.PermissionError`) as existing tools. All new tools added to
`enable_lazy_tools` discovery groups rather than the always-eager set.

---

## F. Security Review (delta only — see A.2/A.7/A.8 for what's already solid)

- **New attack surface**: `render_app_component`'s `props` argument is user/LLM-supplied
  structured data templated into JSX-like markup — **must** reuse #641's
  `_escape_artifact_attr`/`_escape_jsx_attr` helpers verbatim; this is precisely the
  vulnerability class #641's own review caught and fixed for chart tools.
- **`draft_app`/`update_app` must never accept an `agent` value the calling user cannot
  access** — reuse `_require_doc_permission("Agent", "read", agent_name)`, not a bare
  existence check, or a low-privilege user could bind their App to an Agent they can't
  see/use.
- **Icon upload path** (D.8) must reuse the existing 25MB cap and `is_private` conventions
  from `agent_chat.py`/`audio_service.py` (A.4) — there is currently no MIME allowlist
  anywhere in the codebase (only `mimetypes.guess_type` for *routing*, not validation);
  this gap should be closed for icon uploads specifically (SVG in particular needs
  sanitization given it can carry `<script>`), even though fixing it platform-wide is out
  of scope.
- **Public App routing (D.9) must not bypass `check_agent_access`** — a guest hitting
  `/huf/<alias>` must still resolve through the same `allow_guest`-gated path
  `run_agent_sync` already enforces; `is_public` on `HUF App` controls *route
  visibility*, not a new, separate authorization bypass.
- **No arbitrary code execution introduced** — every new tool in D.1/D.4 is declarative
  (structured JSON in, validated deterministic output out), consistent with the existing
  `_FORBIDDEN_TOOL_FIELDS` restriction (A.2) on chat-created tools.
- **Secrets** — any App capability requiring a provider credential (TTS/STT
  provider selection, D.10) must reuse the existing presence-only check pattern
  (`_provider_has_key`) — never return the key value through a builder tool's output.

---

## G. Test Plan (mapped to existing conventions, A.2)

New tests follow `huf/ai/tests/test_builder_tools.py`'s shape (capability-gating,
two-phase preview/confirm, forbidden-field rejection) in a new
`huf/ai/tests/test_app_builder_tools.py`:

1. `test_draft_app_denied_without_builder_role`
2. `test_draft_app_preview_no_mutation` / `test_draft_app_confirm_creates_record`
3. `test_draft_app_rejects_inaccessible_agent`
4. `test_install_app_idempotent` (run twice, assert single record / no duplicate
   `HUF App` row — mirrors `apps_loader.py`'s existing `upsert_huf_app` collision
   handling)
5. `test_set_app_icon_uploaded_rejects_oversized`/`_rejects_bad_mime`
6. `test_render_app_component_escapes_attrs` (mirrors `test_render_tools.py`'s
   Mermaid/chart escaping tests, A.6)
7. `test_list_app_components_matches_jsx_preview_allowlist` (regression guard so the
   seeded Knowledge reference (D.3) and the client-side `availableComponents` map never
   drift apart)
8. `test_hub_orchestrator_resolves_recent_agent` (Path C — conversation-context
   resolution, uses `Agent Conversation.conversation_data`, same plumbing #640 already
   uses for lazy-tool caching)
9. Existing-capability regression: table CRUD, agent draft/publish, tool attach — run
   unchanged from `test_builder_tools.py` to confirm zero regression (backward-compat
   requirement).

---

## H. Migration and Rollout

- All `HUF App` schema changes are additive Select/Check/Data/Link fields with safe
  defaults (`is_public=0`, `capabilities="{}"`) — existing App records (today: zero,
  A.5) are unaffected either way.
- New seed step (D.3) runs via the existing `after_install`/`after_migrate` hook chain —
  idempotent by construction (same guarantee `create_hub_orchestrator_agent()` already
  provides), so re-running `bench migrate` on an already-upgraded site is a no-op.
- No changes to `Agent`, `Agent Conversation`, `Agent Message` schemas — zero risk to
  existing chat history/replay.

---

## I. Phased Execution Plan (dependency-mapped)

Dependencies are explicit: each phase lists exactly which earlier phase(s) it requires.
Phases with no dependency edge between them can run in parallel.

```
Phase 0 (Audit)                      — this document. No dependency.
   │
   ▼
Phase 1 (Target architecture/ADR)    — depends on: 0
   │
   ├──────────────┬───────────────────┬─────────────────────┐
   ▼              ▼                   ▼                     ▼
Phase 2           Phase 3a            Phase 3b              Phase 7 (Icon pipeline)
(App domain       (App-builder        (Design-system        depends on: 1
service ops:      discovery/CRUD      Skill self-seed,       [independent of 3a/3b —
draft/update/     tools: draft_app,   D.3 — new seed         can build in parallel]
install, D.4/D.6) update_app,         function + tool         │
depends on: 1     list_apps, etc.)    pair, D.1)              │
   │              depends on: 2       depends on: 1           │
   │                   │                   │                  │
   │                   └─────────┬─────────┘                  │
   │                             ▼                             │
   │                        Phase 4 (Agent → App workflow,      │
   │                        Path A/B/C, D.4)                    │
   │                        depends on: 2, 3a                   │
   │                             │                               │
   │                             ▼                               │
   │                        Phase 5 (Unified chatbot App —       │
   │                        reuse existing chat runtime, A.3)    │
   │                        depends on: 4                        │
   │                             │                               │
   │                             ▼                               │
   │                        Phase 6 (Installation + launcher     │
   │                        integration, idempotent install_app) │
   │                        depends on: 4                        │
   │                             │                               │
   └─────────────────────────────┼───────────────┬───────────────┘
                                  ▼               ▼
                             Phase 8         Phase 7 output feeds in
                             (Audio input/   (icon selection during
                              transcription/ draft_app/update_app, D.4)
                              OCR App
                              config)
                             depends on: 5, A.4 (audio + OCR already
                             implemented, just needs App-level config
                             surfacing)
                                  │
                                  ▼
                             Phase 9 (Audio generation/TTS App config)
                             depends on: 8 (shares provider/model
                             selection tooling)
                                  │
                                  ▼
                             Phase 10 (Video — NEW backend pipeline,
                             not just config; largest scope in this
                             plan since A.4 shows zero existing
                             implementation)
                             depends on: 9 (reuses the same App
                             capability-declaration mechanism, D.5)
                                  │
                                  ▼
                             Phase 11 (Live voice App config —
                             reuses huf/ai/voice/, documents the
                             known gaps from A.4 rather than
                             silently working around them)
                             depends on: 9

Phase 9b (Public/guest App routing, D.9) — depends on: 6 (an App must be
installable before it can be made public), and reuses the Agent
allow_guest/check_agent_access pattern from A.8 — independent of
Phases 8/10/11, can run in parallel with them once Phase 6 lands.

Phase 12 — removed. The original requirement's "OTR" item was a typo for
OCR (confirmed with the requester); OCR is an existing, fully implemented
capability (A.4) and is already covered by Phase 8's App-level capability
exposure — no separate phase is needed.

Phase 13 (Hardening: permission audit, secret audit, idempotency/retry
review, observability)            — depends on: all of 2–11 and 9b
(whichever subset actually shipped)

Phase 14 (End-to-end testing + documentation) — depends on: 13
```

### Phase details

**Phase 0 — Audit.** Objective: ground truth. Output: this document. No files changed.
Acceptance: every claim above is traceable to a file:line. **Done.**

**Phase 1 — Target architecture/ADR.** Objective: settle D.5's field list, D.9's guest
approach, and the "one App runtime vs. many" question (requirement §37) with a short
written decision: **recommend one generic Agent-backed App runtime** (chat-capable,
capability-flagged) rather than specialized runtimes per modality — justified because
A.5 already shows the App registry is deliberately capability-agnostic (`launch_mode`
has exactly one value today, "Route") and A.3 shows the chat/run pipeline is already
modality-agnostic (`Agent Message.kind` already spans Text/Image/Audio/Video). Files:
none (design doc only, e.g. `docs/adr/0001-app-runtime-model.md`). Dependencies: Phase 0.

**Phase 2 — App domain service operations.** Files: extend
`huf/ai/app_seeding/apps_loader.py` with `create_app_from_agent(...)`,
`update_app(...)`, `install_app(...)` as plain Python functions (no `frappe.whitelist`
yet) that wrap/extend the existing `upsert_huf_app`/`validate_manifest`. Tests: unit
tests for the new functions alone. Dependencies: Phase 1. Acceptance: existing
`upsert_huf_app` callers (file-manifest sync) are unaffected — verified by re-running
`test_apps_sync.py`.

**Phase 3a — Hub App builder tools.** Files: new `huf/ai/tools/app_builder.py` (or
extend `builder.py`), entries added to `BUILDER_TOOL_NAMES` and `_registry.py`,
`enable_lazy_tools` grouping. Depends on Phase 2. Tests: `test_app_builder_tools.py`
(G.1–G.4).

**Phase 3b — Design-system Skill self-seed.** Files: new
`huf/ai/app_seeding/design_system_skill.py`, new `huf/huf/knowledge/*.json` or
`huf/huf/skills/*.json` seed content, `render_app_component`/`list_app_components` in
`huf/ai/tools/render_tools.py`, hook into `install.py:after_install/after_migrate`.
Depends on Phase 1 only (independent of 3a). Tests: G.5, G.6, G.7.

**Phase 4 — Agent → App workflow (Path A/B/C).** Files: wire `draft_app` to accept
either a freshly-`draft_agent`'d Agent or an existing one (`list_agents`/`get_agent`
discovery tools), plus conversation-context resolution ("make that an App") using
`Agent Conversation.conversation_data` the same way #640 already caches lazy-tool
state. Depends on Phase 2 + 3a. Tests: G.8.

**Phase 5 — Unified chatbot App.** Files: no new backend chat logic — verify the
existing `run_agent_sync`/streaming pipeline (A.3) works unmodified when reached via an
App's `route`, since `HUF App.agent` now exists (D.5). Mostly a verification/wiring
phase, not new implementation. Depends on Phase 4.

**Phase 6 — Installation + launcher integration.** Files: `install_app` becomes
idempotent/retry-safe (existence check before insert, matching `upsert_huf_app`'s
existing collision handling in A.5), `AppsPage.tsx` needs no changes (it already renders
any `HUF App` record). Depends on Phase 4. Tests: G.4.

**Phase 7 — File and icon pipeline.** Files: `set_app_icon` tool (D.4), reusing
`agent_chat.py`'s upload/validation conventions (A.4) for the "Uploaded" source,
`handle_generate_image` (A.4) for the "Generated" source. New: MIME/SVG-sanitization
check (F). Depends on Phase 1 only — can build in parallel with 2–6. Tests: G.5.

**Phase 8 — Audio input, transcription, and OCR App config.** Files: expose existing
`Agent.allow_file_upload`/STT config and `Agent.enable_ocr` (A.3/A.4, all already fully
implemented) as App-level `capabilities` flags (D.5) settable via `update_app`. No new
backend transcription or OCR code — this phase is entirely about surfacing existing
capability at the App layer, for both spoken-audio and document/image (OCR) input. Depends
on Phase 5.

**Phase 9 — Audio generation/TTS App config.** Same shape as Phase 8, for
`Agent.tts_model`/`tts_voice` (already implemented, A.3/A.4). Depends on Phase 8 (shares
the provider/model-selection tooling pattern).

**Phase 9b — Public/guest App routing (D.9).** Files: new `is_public`/`alias`
fields (D.5), a new `website_route_rules` entry (`huf/hooks.py`, following the exact
`/huf/stream/<path:agent_name>` shape from A.8), a new lightweight `page_renderer` or a
`huf/www/<something>.py` controller that (a) resolves `alias` → `HUF App`, checking
`is_public` and `enabled`, (b) resolves the linked `Agent`, and (c) reuses
`check_agent_access(agent_doc, user="Guest")` exactly as `run_agent_sync` already does
(A.8) — explicitly does **not** invent a parallel auth bypass. Depends on Phase 6 (an
App must exist/be installed before it can be made public). Tests: guest-access-denied
when `is_public=0`, guest-access-granted + correct Agent resolved when `is_public=1` and
the underlying Agent also has `allow_guest=1` (both must be true — App-level
`is_public` narrows visibility, it does not widen the Agent's own guest gate).

**Phase 10 — Video playback/output (largest net-new backend work).** Files: new
`handle_generate_video` in `huf/ai/handlers/media.py` (currently absent per A.4), new
`Video` option added to `AI Model.modalities`, wiring into the existing
`Agent Message.generated_video`/`kind: "Video"` fields and `ai-elements/video.tsx`
renderer (already present, A.4) — this phase is backend-generation work behind an
already-built frontend, not new UI. Depends on Phase 9 (reuses the same
capability-declaration mechanism established there).

**Phase 11 — Live voice App config.** Files: expose `huf/ai/voice/` engine selection at
the App layer; **explicitly document, not silently paper over**, the known gaps from
A.4 (`send_to_session` unimplemented, litellm_realtime doesn't persist user speech, no
memory injection) as App-level capability caveats rather than claiming full support.
Depends on Phase 9.

**Phase 12 — removed.** "OTR" in the original requirement was a typo for OCR (confirmed
with the requester, 2026-08-24); OCR is already fully implemented (A.4) and its
App-level exposure is covered by Phase 8. No implementation work remains under this
phase number.

**Phase 13 — Hardening.** Permission re-audit of every new tool/endpoint against F,
idempotency verification for `install_app`/`draft_app` re-runs, observability check
(every new mutation traceable via existing `Agent Run`/`Agent Tool Call` records, A.3 —
no new logging system needed since these are just more tool calls through the existing
pipeline). Depends on whichever of Phases 2–11 and 9b actually shipped.

**Phase 14 — End-to-end testing + documentation.** Full Path A/B/C walkthrough in one
Hub conversation, using the test matrix in G plus the existing Playwright e2e
conventions (`frontend/e2e/*.spec.ts`, A — permissions test-fixture note). Depends on
Phase 13.
