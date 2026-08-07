# Tools and Integrations

HUF gives agents two very different kinds of tools: a handful of **core/standard tools** (OCR, image generation, TTS, STT) hard-coded into `huf/ai/handlers/media.py` and dispatched through `huf/ai/sdk_tools.py`, and a large **integration catalog** (Slack, GitHub, Google, ERPNext, ~121 tools total) registered through the same `huf_tools` app hook used by third-party apps. This doc covers the former, plus how both kinds get discovered, synced, and cached, and how file attachments/audio get routed into OCR/STT automatically.

## How a tool becomes callable

Every tool an agent can call — core, integration, or CRUD — is ultimately an **`Agent Tool Function`** document. `create_agent_tools()` (`huf/ai/sdk_tools.py:71`) builds the SDK-facing `FunctionTool` list for an agent by:

1. Loading MCP tools from any linked `MCP Server` (`huf.ai.mcp_client.create_mcp_tools`) — MCP client integration is out of scope for this doc.
2. Loading native tools via `PermissionAwareToolRegistry.get_allowed_tools(agent, user)` (`huf/ai/tool_registry.py:15`), which resolves each `Agent Tool Function` linked on the agent, then filters by read/write/create/delete permission and by whether the requesting user/agent is allowed to run code, SSH, or Docker tools.
3. For each allowed tool doc, mapping `function_doc.types` to a concrete `function_path` via a big `if/elif` chain (`huf/ai/sdk_tools.py:95-165`). `"Custom Function"` and `"App Provided"` types use the `function_path` stored on the document directly; every other `types` value (`"Get Document"`, `"Perplexity Search"`, `"Get Conversation Data"`, etc.) is mapped to a fixed, hard-coded function path.

So "core tools" and "integration tools" are not structurally different at runtime — they're both `Agent Tool Function` rows. The difference is *how the row gets created*: core tools are inserted directly by `huf/install.py` during `after_install`/`after_migrate`; integration tools are discovered from the `huf_tools` hook (see below).

### Permission gating

`PermissionAwareToolRegistry._can_use_tool()` (`huf/ai/tool_registry.py:68`) filters out any tool the acting user isn't allowed to run before it ever reaches `create_agent_tools()`: `MUTATING_TOOL_TYPES` (create/update/delete/submit/cancel/set-value/POST/run-agent/attach-file/builder) are blocked outright for guests unless the tool is explicitly `allowed_for_guest`, and `reference_doctype`-scoped tools additionally require `frappe.has_permission()` for the tool's configured (or type-implied) permission level. Three extra gates apply to specific dangerous tools regardless of type: `_allows_code_execution` (`:107`) requires the `code_execution.run` capability plus `agent.allow_code_execution` plus a non-disabled `Execution Profile`; `_allows_ssh_execution` (`:141`) requires `ssh.run` plus at least one enabled `SSH Connection` on the agent; `_allows_docker_execution` (`:174`) requires `docker.run`. These gates key off `function_path`/`tool_name`, not `types`, so they apply whether the tool is core, hook-discovered, or manually created.

`huf/ai/sdk_tools.py` itself is now mostly re-exports — `from huf.ai.handlers.media import *` etc. (`huf/ai/sdk_tools.py:14-24`) — kept so existing `function_path` strings like `huf.ai.sdk_tools.handle_ocr_document` keep resolving. The actual handler implementations live in `huf/ai/handlers/media.py`, `huf/ai/handlers/crud.py`, `huf/ai/conversation_data_tools.py`, and `huf/ai/handlers/agent_runner.py`.

## Core/standard tools

These are the tools `huf/install.py` creates (or updates) as `Agent Tool Function` records automatically on `after_install`/`after_migrate` (`huf/install.py:102-124` and `:153-183`), so every HUF install has them available without any app registering a hook. Handler code lives in `huf/ai/handlers/media.py`.

| Tool name | Handler | Installer | Tool Type |
|---|---|---|---|
| `ocr_document` | `huf.ai.handlers.media.handle_ocr_document` (`huf/ai/handlers/media.py:317`) | `create_ocr_document_tool` (`huf/install.py:548`) | Generation-adjacent (`Agent Tool Type` created ad hoc) |
| `generate_image` | `huf.ai.handlers.media.handle_generate_image` (`huf/ai/handlers/media.py:39`) | `create_image_generation_tool` (`huf/install.py:479`) | `Generation` |
| `generate_audio` | `huf.ai.handlers.media.handle_generate_audio` (`huf/ai/handlers/media.py:586`) | `create_generate_audio_tool` (`huf/install.py:627`) | — |
| `transcribe_audio` | `huf.ai.handlers.media.handle_transcribe_audio` (`huf/ai/handlers/media.py:837`) | `create_transcribe_audio_tool` (`huf/install.py:717`) | `Transcription` |

All four are registered under `function_path`s that point at `huf.ai.sdk_tools.<name>` (the re-export shim), even though the real code is in `huf/ai/handlers/media.py`.

The **scoped-memory tools** (`save_memory_record`, `search_memory_records`, `get_memory_record`, `archive_memory_record`, `promote_memory_to_knowledge`, created by `create_memory_tools()`, `huf/install.py:1219`) and the **conversation-data tools** (`get_conversation_data`, `set_conversation_data`, `load_conversation_data`) are also core/system tools by this definition, but they're documented in [`memory.md`](./memory.md) rather than here — see that doc for their resolution, injection, and API-permission behavior.

There is no dedicated `web_search` tool. The closest built-in capability is `handle_perplexity_search` (`huf/ai/tools/perplexity.py:9`), dispatched when an `Agent Tool Function.types == "Perplexity Search"`, reading the API key from `perplexity_api_key` in `site_config.json` (falling back to the `PERPLEXITY_API_KEY` env var). Unlike the four tools above, no installer auto-creates a `Perplexity Search` tool record — one has to be created manually (or by an app's `huf_tools` hook) before it's usable. Any doc or generated reference that lists `web_search` as a standard, always-available tool (including the note at the top of `docs/reference/tools.generated.md`) is describing an aspiration, not current behavior.

### `ocr_document`

`handle_ocr_document` (`huf/ai/handlers/media.py:317`) requires `agent_name` (auto-injected from run context) to resolve the agent's `AI Provider` and API key, then delegates to `extract_document()` in `huf/ai/ocr_engine.py:496`. Accepted params: `file_id`, `file_url` (fallback, resolves both `/files/` and `/private/files/` paths and picks the newest File record on a name collision), `pages` (PDF only), `include_images` (PDF + OCR-endpoint only), `model` (override).

`extract_document` resolves the `File` doc (`_resolve_file_doc`, `huf/ai/ocr_engine.py:91`), enforces a read-permission check and a path-traversal guard against the site's files directory, hashes the file (SHA-256, for the `file_hash` field callers can use to verify the processed content), and then picks an extraction **strategy** via `_determine_strategy()` (`huf/ai/ocr_engine.py:199`):

- **Images** → always `vision`.
- **PDFs** → `vision` for `google`, `gemini`, `vertex_ai`, `anthropic`, `openai`; `ocr` (LiteLLM OCR endpoint) for `mistral`, `azure`; `local_pdf` (pypdf/PyPDF2) for everything else.
- **Office/text documents** (DOCX, XLSX, PPTX, TXT, MD, HTML, CSV, JSON, XML, LOG) → `local` extractors (no API cost).
- **Unknown types** → `local` if they look text-ish, otherwise `vision` if small enough.

If the primary strategy fails, PDFs fall back to `local_pdf`; other failures fall back to `vision` if a vision default model exists for the provider and the file is under the 25 MB base64 limit (`_MAX_BASE64_FILE_SIZE`, `huf/ai/ocr_engine.py:32`).

**This is a real discrepancy from the old monolith.** The previous `AGENTS.md` claimed PDFs go to the LiteLLM OCR endpoint for "Mistral, Azure, Google/Gemini/Vertex" and to local pypdf extraction only for "OpenAI, Anthropic". The current code instead routes `google`/`gemini`/`vertex_ai`/`anthropic`/`openai` PDFs through **vision models**, and reserves the OCR endpoint strictly for `mistral`/`azure`. This changed at some point after the old doc was written and was never updated there.

Result strategies returned to callers: `local`, `local_pdf`, `ocr`, `vision` — this part of the old doc was correct.

### `generate_image`

`handle_generate_image` (`huf/ai/handlers/media.py:39`) generates images via LiteLLM's image endpoint, with `_get_default_image_model()` (`huf/ai/handlers/media.py:13`) supplying provider defaults (`dall-e-3` for OpenAI/Azure/OpenRouter, `google/gemini-2.5-flash-image` for Google, etc.) when no `model` param is passed.

### `generate_audio` (TTS) and `transcribe_audio` (STT)

See [Audio, STT, and TTS model routing](#audio-stt-and-tts-model-routing) below.

## Tool discovery and hook-based registration

Apps (including HUF's own integration catalog) register tools by exposing a `huf_tools` hook in their `hooks.py`:

```python
huf_tools = [
    "my_app.tools.custom_tool",       # dotted path to a dict, or a list of dicts
    ["my_app.tools.tool1", "my_app.tools.tool2"],
]
```

Each resolved entry is expected to be a dict with at least `tool_name` and `function_path`; `description`, `category`/`tool_type`, `parameters` (list of `{name/fieldname, type, required, description, label}`), and `service` are optional. `_normalize_hook_tools()` (`huf/ai/tool_registry.py:282`) flattens strings (imported via `frappe.get_attr`), dicts, and nested lists into a flat list of tool-definition dicts.

HUF's own 121-tool integration catalog is registered this exact way — `huf_tools = "huf.ai.tools._registry.ALL_INTEGRATION_TOOLS"` (`huf/hooks.py:364`). That catalog (Slack, GitHub, Google, ERPNext, etc.) is generated into [`../reference/tools.generated.md`](../reference/tools.generated.md) from `huf/ai/tools/_registry.py` — see that file for the full list; it is not reproduced here.

### Sync process (`huf/ai/tool_registry.py`)

`sync_discovered_tools()` (`huf/ai/tool_registry.py:338`, whitelisted) does the actual work:

1. `get_tools_by_app()` (`:301`) reads `frappe.get_hooks("huf_tools", app_name=app)` for each app to scan and normalizes the entries.
2. Every discovered tool is **validated** before any DB write: `tool_name` and `function_path` must be present, and the function path must actually import and be callable (`importlib.import_module` + `getattr`, with a per-`function_path` validation cache to avoid re-importing the same module twice in one sync). Invalid tools are skipped and collected into an `errors` list rather than raising.
3. Valid tools are upserted as `Agent Tool Function` documents with `types = "App Provided"`, `tool_type` set from `category`/`tool_type`, and `provider_app` set to the owning app name (batched: one query to fetch existing docs by name, then per-doc create/update).
4. When doing a **full scan** (`apps_to_scan=None`, i.e. no app filter — manual sync, `after_install`, `after_migrate`), any existing `"App Provided"` tool whose name is no longer produced by any app's hook is deleted as orphaned. Incremental (single-app) syncs never delete.

`sync_app_tools(app_name)` (`huf/ai/tool_registry.py:556`) is a thin wrapper that calls `sync_discovered_tools(apps_to_scan=[app_name])` for a single app; it's wired to `after_uninstall` (`huf/hooks.py:129`) so an app's `App Provided` tools get cleaned up when it's removed. `to_sync_tools = "huf.ai.tool_registry.sync_discovered_tools"` (`huf/hooks.py:361`) exists as a hook name apps can invoke the same sync through.

Full syncs happen at `after_install` (`huf/install.py:120`, `use_cache=False`) and `after_migrate` (`huf/install.py:179`, `use_cache=False`) — both force a complete rescan regardless of cache.

### Caching

Caching here is about **skipping unchanged apps during a scan**, not about caching tool definitions in Redis. It lives entirely in `huf/ai/tool_registry.py`:

- `_get_app_modified_time(app_name)` (`:185`) uses the mtime of that app's `hooks.py` file as a cheap proxy for "did this app's tool registrations change".
- `_get_cached_scans()` / `_update_cached_scans()` (`:206`, `:223`) persist a `{app_name: last_scan_iso_timestamp}` map as a JSON string in the `last_app_scans` field on the `Agent Settings` singleton doctype.
- `_get_apps_to_scan()` (`:252`) diffs `frappe.get_installed_apps()` against that cache: an app is rescanned if it has no cache entry, or if its `hooks.py` mtime is newer than its last recorded scan time.

**This differs from the old monolith's description.** The previous `AGENTS.md` invented cache key names — `huf:discovered_tools` and `huf:app_modification_times` — that do not exist anywhere in the current code; there is no Redis-backed "Tool Discovery Cache" separate from tool definitions. The only persisted state is the single JSON blob on `Agent Settings.last_app_scans`, keyed by app name to a timestamp, used purely to decide *whether to rescan*, not to cache the discovered tool definitions themselves (those live as `Agent Tool Function` documents, which is itself the durable store).

`use_cache=True` is only honored when `apps_to_scan is None` (full, unfiltered scans); any caller that passes an explicit app list always scans exactly those apps regardless of cache state.

## File attachments trigger and OCR ingestion

`Agent Trigger` documents (Doc Event triggers) can declare `file_attachments` — a child table of `{source_type, field_name, child_table}` rows (`huf/huf/doctype/agent_trigger/agent_trigger.json:216`) describing which fields (or child-table fields) on the triggering document hold file URLs. `source_type` is either `"DocField"` (a direct field on the doc) or `"Child Table Field"` (a field inside a child-table row).

At execution time, `run_agent_for_doc()` (`huf/ai/agent_hooks.py:141`) does the following for each triggered run:

1. Resolves every attached file URL from the configured fields (`huf/ai/agent_hooks.py:222-265`), guesses its MIME type, and classifies it as `is_image` (image MIME) or `is_audio` (via `huf.ai.audio_service.is_audio_file`) — images are checked first, so an ambiguous file is never both. Each file's Frappe `File` record `name` is resolved by URL up front (`file_id`) to avoid ambiguous lookups later.
2. Any file that is **neither image nor audio** is routed through `handle_ocr_document(file_id=..., file_url=..., agent_name=...)` (`huf/ai/agent_hooks.py:267-293`) inside a dedicated `asyncio` event loop. Successful extractions are concatenated into an `Attached File Content (OCR Extracted):` block (with a `hash:` marker per file) that's appended to the agent's prompt.
3. Any file classified as **audio** is routed through `huf.ai.audio_service.transcribe_audio_file(file_id=..., file_url=..., agent_name=...)` (`huf/ai/agent_hooks.py:296-323`) — audio is transcribed via STT, not OCR. Transcripts are appended under a separate `Attached Audio Transcript(s):` block.
4. **Images are not processed by this hook at all** — they're left in the `files` list and passed straight through to `run_agent_sync(..., files=files, now=True)` (`huf/ai/agent_hooks.py:342`) for the underlying multimodal call to consume directly, matching the old doc's claim that images go to vision models rather than OCR.

Both the OCR and transcription steps fail soft: exceptions are caught and logged via `frappe.log_error` under `"Agent Hooks OCR"` / `"Agent Hooks Audio"` rather than aborting the triggered run.

## Audio, STT, and TTS model routing

Both TTS and STT resolution follow the same three-tier priority — tool-call param, then agent-level config, then provider default — but they're implemented separately and the priority order between the *first two* tiers is not quite symmetric.

### TTS: `_resolve_tts_config` (`huf/ai/handlers/media.py:427`)

Called by `handle_generate_audio` (`huf/ai/handlers/media.py:586`).

| Priority | Condition | Model source | API key source |
|---|---|---|---|
| 1 | `model` passed to the `generate_audio` tool call | Tool-call `model`, normalized against the agent's **main** provider | Agent's **main** `AI Provider` |
| 2 | `agent.tts_model` set (`Agent.tts_model`, Link to `AI Model`, `huf/huf/doctype/agent/agent.json:169`) | `AI Model.model_name` via the link | `AI Model → AI Provider` — may be a **different** provider than the agent's main one |
| 3 | Neither set | `_get_default_tts_model(main_provider)` (`huf/ai/handlers/media.py:401`) | Agent's **main** provider |

Voice resolves similarly: explicit tool-call `voice`, else `agent.tts_voice` (`Agent.tts_voice`, Data field, `huf/huf/doctype/agent/agent.json:176`) or a provider default, else `_get_default_voice(provider_name)` (`huf/ai/handlers/media.py:387`). This is what makes cross-provider TTS possible — an OpenAI-model agent can set `tts_model` to an ElevenLabs `AI Model` and generate audio with ElevenLabs credentials without changing its main provider.

### STT: `resolve_stt_config` (`huf/ai/audio_service.py:345`)

Called (indirectly, via a backward-compatible alias `_resolve_stt_config` in `huf/ai/handlers/media.py:559-577`) by `handle_transcribe_audio` (`huf/ai/handlers/media.py:837`) and by the file-attachment ingestion path (`transcribe_audio_file`, `huf/ai/audio_service.py:472`).

| Priority | Condition | Model/provider source |
|---|---|---|
| 1 | Explicit `model` param (tool call or ingestion override) | Model looked up by name in `AI Model`, or by `provider/model` slug against `AI Provider.slug` if not found directly |
| 2 | `agent.stt_model` set (`Agent.stt_model`, Link to `AI Model`, `huf/huf/doctype/agent/agent.json:766`) | Model's own linked provider |
| 3 | Neither set | `_find_transcription_model(provider)` (`huf/ai/audio_service.py:326`) — prefers an `AI Model` record whose `modalities` field contains `"Transcription"` for the agent's main provider, then falls back to `_get_default_stt_model(provider_name)` (`huf/ai/audio_service.py:309`: `whisper-1` for OpenAI/Azure, `groq/whisper-large-v3` for Groq, `deepgram/nova-2` for Deepgram, `gemini/gemini-2.5-flash` for Google/Gemini/Vertex) |

## See also

- [`../reference/tools.generated.md`](../reference/tools.generated.md) — the full generated catalog of the ~121 integration tools (Slack, GitHub, Google, ERPNext, etc.), regenerated from `huf/ai/tools/_registry.py` via `docs/reference/generate_tools.py`.
