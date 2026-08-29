# HUF Current-State Coverage Map

Source: Phase 0 subsystem audits of `tridz-dev/huf` `develop` (base `29376ebc`) + historical PR salvage (#359, #339, #298, #302, #303, #304). All file:symbol references below are as reported in those raw audits, not independently re-verified beyond what the audits state.

---

## 1. Repo / CI infrastructure

- **CI workflows** (`.github/workflows/`): `server-tests.yml` (backend, `bench --site test_site run-tests --app huf`, MariaDB 11.8 + Redis 7), `frontend-tests.yml` (path-filtered on `frontend/**`, `npm run typecheck && npm run test && npm run build`), `failure-analysis.yml` (Claude-Haiku-driven post-failure triage, gated on `FAILURE_ANALYSIS_ENABLED`), `deploy-huf.yml` (SSH deploy on push to `pre-develop`/`develop`), `fasterdocker-publish.yml` (multi-arch ghcr.io image build).
- **No full-stack/E2E CI job exists** — Playwright specs run locally only (`npm run test:e2e`); there is no `e2e-tests.yml` wiring MariaDB+Redis+bench-serve+Playwright together in CI. This is the single largest CI gap: 18 Playwright specs exist but are not gated in CI today.
- **Backend**: 92 `test_*.py` files (32 doctype tests, 44 `huf/ai/tests/`, 9 knowledge, 4 capability-discovery, 2 app-seeding, 1 skills). Runner: Frappe native (`bench run-tests`), no pytest.ini/pyproject test config.
- **Frontend**: 17 Vitest unit tests (`frontend/src/**/*.test.ts`, Node environment, `.ts` only — no `.tsx` component tests, no jsdom, no `@testing-library/*`), 18 Playwright specs across 3 suites (offline/mocked `frontend/e2e/*.spec.ts`, deployed `frontend/e2e/deployed/*.spec.ts` with real storage-state auth, audit `frontend/e2e/audit/A1-A3`).
- **Static analysis**: 1 Semgrep rule (`huf-no-explicit-frappe-commit`), Ruff (`pyproject.toml`), design-parity checker (`frontend/scripts/check-design-parity.mjs`, 5 checks: token/palette/dark fatal, override/casing warn-then-strict).
- **Gap**: no dedicated characterization tests found for SSRF (`http_handler.py::validate_url`) or webhook HMAC auth (`flow_api.py`, `automation_webhook.py`) despite both having shipped fixes (PR #302/#304) — only `huf/ai/tests/test_context_policy.py` exists nearby and is unrelated.

---

## 2. Agent core (DocType / config API / React editor)

- **Source of truth**: `huf/huf/huf/doctype/agent/agent.json` (10 tab-breaks), controller `agent.py` (`class Agent(Document)`, 10+ private `_validate_*` methods).
- **Two independently-maintained field-list surfaces must stay in sync with the doctype**: `AGENT_SECTIONS` dict in `huf/ai/agent_config_api.py:43` (8 API sections) and `tabConfig` in `frontend/src/pages/AgentFormPage.tsx:206` (8 UI tabs, mapped 1:1 to `AGENT_SECTIONS` but not 1:1 to the doctype's 10 tab-breaks). A new doctype field needs a 3-way update or it silently fails to load/save via the tab UI — **no automated check enforces this sync today**.
- **Persistence has two coexisting write paths**: (a) per-section optimistic-concurrency PATCH via `update_agent_section` (`agent_config_api.py:202`, `_assert_revision` at :173 raising `TimestampMismatchError` on stale writes) used by the tab-save flow; (b) full-document `updateAgent` (`agentApi.ts:643`) used ad-hoc by `linkKnowledgeToAgent`/`linkMcpServerToAgent` — bypasses the section API and its revision check entirely. Regression-relevant: concurrent-save race between these two paths is untested.
- **Read/write permission asymmetry (by design, not a bug)**: `get_agent_section` only requires `check_permission("read")`; `update_agent_section` requires `check_permission("write")` → `has_capability(user, "agent.edit")`. Documented as reviewed (`Tracks/AgentPermissionsAudit/AGENT_PERMISSIONS_AUDIT.md` F13/OQ7) — "do not fix", but should have a regression test pinning the asymmetry so it isn't "fixed" accidentally.
- **System-agent immutability**: `_validate_system_agent_immutability` (`agent.py:247-312`) deep-diffs `agent_tool`/`default_plan` and blocks edits to `instructions`, `agent_prompt`, `prompt_mode`, `provider`, `model`, `disabled`, `allow_chat`, `persist_conversation`, `persist_user_history`, `enable_multi_run` on system agents; `_validate_system_field_tamper` (agent.py:226) guards `is_system` itself; system agents can't be renamed/deleted.
- **Hidden-tab-still-saveable edge case**: `agent_modality` hides Voice vs Tools/Knowledge/Skills tabs (`AgentFormPage.tsx:469`, `hiddenTabs`), but those sections remain PATCH-able via `update_agent_section` even while hidden (explicit code comment, lines 465-467) — a good target for a regression test (can a hidden section's stale state still get PATCHed).
- **Cross-field validation is 100% server-side** (`agent.py::validate()` chain); none is duplicated client-side beyond `depends_on` visibility expressions.

## 3. Agent runtime / execution lifecycle

- **DocType**: `Agent Run` (`huf/huf/doctype/agent_run/`) — status `""/Started/Queued/Success/Failed`; **no `Cancelled`/`Retrying` state in the schema**.
- **Entry points**: `chat_api.py::run_agent_sync_chat` (guest-allowed) → `agent_integration.py::run_agent_sync` (line 980, canonical sync entry, also called by scheduler/automation/flow code) and `run_agent_stream` (line 2483, async SSE).
- **Queue-first design**: default execution path enqueues `_run_queued_agent` (`agent_integration.py:2277`) rather than running inline; direct execution (`run_immediately=1` or `now=True`) is guarded against queue-jumping (`_has_queued_runs` check) and uses a Redis lock (`agent_run_conv_{conversation_id}`, `nx=True`, `ex=600`) with a `_RunHeartbeat` thread renewing every 180s.
- **Stall recovery, not retry**: `recover_stalled_agent_runs` (line 2419, scheduler job) resets `Started` runs older than the lock TTL with no live lock back to `Queued`, and re-drains orphaned `Queued` runs older than 60s. This is the *only* recovery mechanism.
- **No cancellation API exists anywhere** — confirmed by grep across `agent_integration.py`, `execution_api.py`, `chat_api.py`; the only "cancel" hit is an unrelated `cancel_document_tool` (cancels a submittable Frappe *document*, not a run). **This is a P0 gap**: nothing lets a client cancel a Queued or Started Agent Run.
- **Two parallel execution code paths with duplicated context-assembly logic**: `_execute_agent_run` (direct/queued, `agent_integration.py:1377-2196`) vs `run_agent_stream` (streaming, line 2483) — history-fetch/context-strategy logic is **not shared**, so behavior can drift between the two without either failing a shared test.
- **Core execution steps** (`_execute_agent_run`): history fetch → multi-run orchestration escape hatch (delegates to `orchestration.orchestrator.create_orchestration` if `enable_multi_run`) → mandatory RAG context build (abort-on-failure, not degrade) → context-strategy injection (Summarize/FIFO/None) → provider invocation via `RunProvider.run` wrapped in `mcp_session_pool()` → tool-call loop over `result.new_items` → usage/cost persistence → final message persist → sub-agent chaining re-enqueue → auto-naming/background-summarization enqueue.
- **Realtime status**: `_emit_run_lifecycle_event` (line 535) publishes `agent_run_status` on `conversation:{name}`; polling fallback `get_agent_run_status` (line 1274) for guests/external clients that miss the socket event.

## 4. Tool-calling framework

- **Definition**: `Agent Tool Function` doctype — no JSON-schema validation of `params`/`parameters` at rest (`json.loads` try/except silently drops bad JSON, `sdk_tools.py:189-195`); `strict_json_schema=False` tolerates loose schemas.
- **Assembly** (`AgentManager._setup_tools`, `agent_integration.py:115-186`): native+App-Provided (`sdk_tools.create_agent_tools`) → MCP tools (merged/deduped by name, last wins) → skills-list tool → knowledge tools (a *second*, separate code path from `create_function_tool`).
- **Permission gating at assembly time**: `PermissionAwareToolRegistry.get_allowed_tools` (`tool_registry.py:44-68`) — `_can_use_tool` (read-only agent block, guest hard-block, `frappe.has_permission` per `required_permission`/`TOOL_PERMISSIONS` map), plus separate capability gates for code execution/SSH/Docker/ask-user/document-artifacts.
- **Execution is NOT via the OpenAI Agents SDK Runner** — HUF's own loop in `huf/ai/providers/litellm.py::run()` (~lines 700-1170): `MAX_ROUNDS = agent.max_turns or 10`; unknown-tool-name and handler-exception paths both resolve to a normal `role: tool` message fed back to the model (**model cannot structurally distinguish "tool doesn't exist" from "tool ran and errored"**); loop-detection guard (`_tool_calls_signature`, `MAX_TOOL_LOOP_REPEATS=1`) raises `ProviderUnavailableError` on repeats.
- **Runtime permission re-check** in `create_function_tool`'s `on_invoke_tool` closure (`sdk_tools.py:429-505`) — defense-in-depth against the assembly-time filter; malformed JSON args from the model are caught and returned as `{"error": ...}` rather than crashing the run.
- **Audit trail**: `process_tool_call`/`log_tool_call` (`agent_integration.py:636/784`) persist `Agent Tool Call` + a parallel `Agent Message` (kind="Tool Call") **after the fact**, reconstructed from litellm.py's `SimpleNamespace` items — persistence bugs degrade to a missing/incomplete audit row, not a crashed run.
- **MCP tools bypass the entire `PermissionAwareToolRegistry`/`Agent Tool Function` pipeline** — the only gate is `frappe.has_permission("MCP Server", "read", ...)` plus whatever the remote MCP server itself enforces. MCP tool names truncate at 64 chars vs 128 for native tools — a naming-collision risk not present for native tools.
- **Silent tool disappearance**: `get_function_from_name` (`sdk_tools.py:536-585`) returns `None` on any import/attribute error for a broken `function_path` — the tool just vanishes from the agent's tool list with only a debug-level log line, no startup error.
- **Outer exception handler gap**: `litellm.run()` swallows `frappe.DoesNotExistError/PermissionError/ValidationError` with only a warning log and no explicit return — downstream handling of a possible `None` result from `RunProvider.run` was flagged as unverified by the audit.

## 5. Provider / model / LLM gateway

- **LiteLLM-unification design**: `run.py::RunProvider.run/run_stream` always tries `huf.ai.providers.litellm` first; legacy per-provider modules (`anthropic.py`, `google.py`, `openrouter.py`, `openai.py` — the last a 4-line SDK-Runner stub) are migration remnants, keyed off the AI Provider *document name* not `provider_brand`, so effectively dead code paths.
- **DocTypes**: `AI Provider` (1) → `AI Model` (many); `api_key` is a Frappe `Password` field; resolution is DB-then-boot-time-env-snapshot (`_BOOT_ENV`, captured at module import — deliberately not live `os.environ`, to avoid cross-request key leakage).
- **Model-name routing**: `_normalize_model_name` derives `<prefix>/<model>` from `provider_brand` or a `provider_prefix_map`; Ollama routes via `ollama_chat/` specifically (not `ollama/`) for reasoning+tools support; brand-alias reconciliation (`alibaba→dashscope`, `grok→xai`) has its own lookup table that must stay in sync with the prefix map.
- **Streaming has narrower feature parity than non-streaming**: no `response_format` (structured output) support in `run_stream`; no custom-provider streaming fallback (LiteLLM-only); near-identical-but-duplicated message-building code between `run()` and `run_stream()` (candidate for drift).
- **Tool/response_format conflict auto-recovery**: heuristic learned via runtime 400s (`_L1_CAPABILITY_CACHE` + Redis, keyed `litellm_tool_json_conflict:{provider_name}`), not a static capability table — behavior can silently change per-provider after the first observed 400.
- **Prompt caching**: `cache_control` blocks are Anthropic-specific in `_build_text_content`; OpenAI/Gemini get separate native mechanisms; local LLMs unconditionally disable caching; capability gate (`model_supports_prompt_caching`) is data-driven off `litellm.model_cost` pricing entries, not a hardcoded list.
- **Cost calculation priority**: custom `AI Model` pricing → `litellm.completion_cost()` → `0.0`/`local_no_pricing` → `0.0`/`unknown`.
- **Error normalization**: `ProviderUnavailableError` with separate `public_message`/`log_message`; `_sanitize_provider_error_message` buckets raw errors into 5 canonical user-facing categories; retry wrapper handles transient network errors (2 retries, exponential backoff).

## 6. Chat / conversation E2E

- **DocTypes**: `Agent Conversation` (status Active/Hidden/Archived/Trashed/Deleted), `Agent Message` (kind: Message/Tool Call/Tool Result/Status/Error/Image/Audio/Video). Both controllers are 9-line stubs — all logic lives in `conversation_manager.py`/`agent_integration.py`/`agent_chat.py`.
- **Ordering risk**: `ConversationManager.add_message()` computes `conversation_index` via `SELECT MAX(...)+1` — **not atomic in that function itself**; correctness depends entirely on every caller holding the per-conversation Redis lock. The audit found one caller that appears not to: the whitelisted `add_message` API (`agent_chat.py:1070`) does not visibly take the conversation lock before calling `cm.add_message()` — flagged as a potential race if used concurrently with an active run.
- **No server-side cancel/stop API** (same finding as §3) — frontend "Stop" (`ChatInput.tsx::handleStop`) only aborts the client fetch for the SSE streaming path; the queue-first REST path (the default) has nothing to abort server-side.
- **Tool-call approve/deny is UI-only** — explicitly `TODO(tool-call-approval-api)` marked in `ChatMessage.tsx` (lines 88-101); clicking shows a toast, no backend/socket wiring exists. Only flow-run-level approvals exist elsewhere (`ApprovalsBell.tsx`).
- **Client-side hang guards are UI-only, not server-authoritative**: `RUN_RESPONSE_TIMEOUT_MS=180_000` in `ChatInput.tsx`, `RUN_STATUS_POLL_TIMEOUT_MS` (10 min) in `useRunStatusPolling.ts` — both can show "Failed" to the user while the backend run is still actually executing, and a late completion event can arrive after the UI has already given up.
- **`run_agent_sync_chat` (guest-facing) duplicates guest/capability/access checks** from `run_agent_sync` rather than delegating (only inside its `create_new` branch) — a documented drift risk if `run_agent_sync`'s checks change.
- **Owner-or-System-Manager read gate** explicitly enforced on `get_history`/`add_message` (`agent_chat.py:286,1070`) — "being allowed to run the agent is NOT enough to read someone else's conversation."
- **Regeneration never mutates history in place** — always appends a new user+assistant turn (documented: "there's no endpoint to edit/replace history in place").

## 7. Automations

- Backend: `automation_api.py` (CRUD + run/pause/resume, all doc-level `has_permission` gated), `automation_runner.py` (`run_automation` → `_execute` → `run_agent_sync`; `_check_run_as_user_permission` restricts `run_as_user` escalation to System Manager only), `automation_scheduler.py` (cache-based 60s-TTL lock per due trigger, advances `next_execution` *before* executing), `automation_hooks.py` (doc-event trigger routing across 13 supported Frappe doc events, `safe_eval` condition evaluation against `{"doc": doc}`).
- `_validate_system_agent_lock()` blocks non-System-Manager edits to automations targeting system agents (mirrors Agent's own system-agent immutability pattern).
- Frontend: `automationApi.ts`, `AutomationFormPage.tsx`, trigger-editing components (`TriggerEditor.tsx` etc.).

## 8. Prompt templates

- `prompt_api.py`: version lifecycle (`create_new_version`, `fork_prompt`, `detach_from_template`, `attach_template`, `save_as_template`, `get_version_history`) — all `has_capability`-gated (`agent.create`/`agent.edit`/`agent.use`); parallel summary-prompt API mirrors every endpoint.
- `prompt_resolver.py::resolve_prompt`/`resolve_summary_prompt` — central resolution: Local mode returns `agent_doc.instructions`; Template+locked walks `prompt_group` to the exact locked version; Template+unlocked follows latest.
- `_update_agent_links()` auto-repoints *unlocked* agents to a newly created version on `create_new_version` — a global side effect worth a dedicated regression test (does creating v2 of a shared template silently change behavior for every unlocked agent using it).
- Frontend: Playground (`PlaygroundView.tsx`, `PromptPanel.tsx`, `SaveTemplateDialog.tsx`, `TemplatePickerDialog.tsx`).

## 9. Permissions

- Capability-based model, not raw Frappe roles: `huf/permissions.py::has_capability`/`get_user_capabilities` (cached 300s)/`get_user_huf_role`. 30 capabilities across agent/chat/knowledge/tools/flows/system/data/users/execution domains.
- `check_agent_access`/`assert_agent_access` (`agent_access.py`): guest requires `allow_guest`; owner/System-Manager always allowed; empty `allowed_users`+`allowed_roles` means "all authenticated"; otherwise explicit membership required.
- Enforcement sequence is consistent across subsystems: `@frappe.whitelist()` → `frappe.has_permission`/`doc.has_permission` → `assert_agent_access` → `has_capability` → doctype `validate()` system-agent locks.
- No-op guard conditions recur everywhere and are a natural fault-injection surface for regression tests: `frappe.flags.in_seeding/in_install/in_migrate/in_patch/in_import`, `"System Manager" in frappe.get_roles(user)`.
- Gateway webhooks (`gateway_webhook.py::handle_gateway_webhook`) are credential-verified, not user-permission-gated — a structurally different auth model from everything else in the app, worth its own contract tests.

---

## 10. Salvageable historical fixes / gaps (from PR audits, see `PR359_SALVAGE.md` for full detail)

- Confirmed present on develop: SSRF guard in `http_handler.py` (ipaddress private/loopback check), `hmac.compare_digest` in `automation_webhook.py`/`flow_api.py`, `get_result_context` allow-list (`sdk_tools.py`), `delete_documents` per-doc permission check (`tool_functions.py`), code-block XSS escape (`code-block.tsx`), `innerHTML` entity-decoder XSS fix (`decodeHtmlEntities`), `returnTo` navigation validation (`AgentPromptFormPage.tsx`).
- Confirmed **still open** (per PR #304's own text, not independently re-verified): conversation-mutation-API authz (#008), Huf Data Table capability bypass (#010), `transcribe_audio` arbitrary File read (#011), TTS/STT keys in `os.environ` (#012), HTML/SVG same-origin artifact execution (#014), JSX preview arbitrary JS execution (#015) — these are unclaimed P0/P1 security surfaces with no confirmed fix and no found test coverage.
- Confirmed gap, no test file anywhere: sandboxed AST expression evaluator (`flow_eval.py`) and orchestration plan-priority/scheduler logic (`agent_orchestration`/`process_orchestrations`) — security-relevant code with zero test coverage.
