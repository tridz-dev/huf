# HUF Agent — Advanced Settings Audit (Pre-v1)

Scope: `/Users/safwan/Code/Huf/huf/frontend/src/components/agent/AdvancedTab.tsx` — 10 sections, ~30 fields. Each field was traced from UI control → Agent doctype field → backend consumption (or lack thereof).

## 1. Executive Summary

Total findings across all sections: **31** (some fields surfaced more than one finding).

| Status | Count | Meaning |
|---|---|---|
| `ok` | 19 | Field is genuinely read and enforced server-side, matching what the UI tells the user |
| `gap` | 8 | Field works but has a real hole: missing validation, UI/backend condition mismatch, or a defense-in-depth bypass |
| `dead_code` | 2 | Field is saved and rendered but **never read** by any live code path — pure no-op |
| `half_implemented` | 4 | Field is wired for its happy path but skips a validation step the UI's own copy implies exists |
| `unclear` | 1 | Claim in UI copy not fully traced to source; not a confirmed defect |

(Total exceeds 31 because a couple of `gap`/`dead_code` findings describe the same field from two angles — see `summary_ratio` and `enable_memory_*`.)

**Overall v1-readiness verdict: Conditionally ready.** 9 of 10 sections are functionally sound (code execution, SSH execution, memory settings, model/modality, document upload, conversation data, conversation strategy, reasoning, HUF UI). One field — **`summary_ratio`** — is fully dead: it is presented as a live control in the Summarization Engine section, is persisted, but has zero effect on agent behavior. This is the one P0: it is a user-facing broken promise, not a cosmetic gap. Everything else is P1/P2 hardening (missing pre-save validation, silent defaults, minor UI/backend condition mismatches) that should not block v1 but should be tracked.

---

## 2. Per-Section Detail

### 2.1 Conversation Strategy

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `context_strategy` | ok | `huf/ai/agent_integration.py:1467,2545` | Summarize/FIFO/None correctly branches history handling |
| `history_limit` | ok | `huf/ai/agent_integration.py:790,1468,2546` | Drives FIFO truncation + overflow detection |
| `max_turns` | ok | `huf/ai/agent_integration.py:474` | Set directly on SDK `agent.max_turns` |
| `max_knowledge_tokens` | ok | `huf/ai/agent_integration.py:1424,2661` | Caps injected knowledge via `build_knowledge_context()` |
| `autonaming_of_conversation_title` | ok | `huf/ai/agent_integration.py:1944,3018` | Gates `generate_conversation_title` background job |
| `summary_ratio` | **gap → see 2.2** | `huf/huf/doctype/agent/agent.json:413` | Rendered here, but dead — see Summarization Engine section |

### 2.2 Summarization Engine (Agent Advanced tab)

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `summary_ratio` | **dead_code** | `huf/ai/agent_integration.py:800-801` (never read) | Live summarization path `run_background_summarization` (`agent_integration.py:780-838`) computes overflow purely from `history_limit`, never touches `summary_ratio`. Saved via `agent_config_api.py:58` but changing it in the UI has **zero effect**. |
| `summary_ratio` (only real consumer) | **dead_code** | `huf/ai/conversation_manager.py:697-707` | `ConversationManager.summarize_conversation(..., ratio=0.7)` is the only function in the repo that accepts a ratio kwarg, and it has **no callers anywhere** — confirmed via grep for `summarize_conversation(`. Superseded-but-unremoved code. |
| `summary_prompt_version_locked` / `summary_template_version_at_attach` | ok | `huf/ai/prompt_resolver.py:99-108` | Version pinning genuinely gates pinned vs. latest template body |
| `summary_prompt_template` → Agent Summary Prompt | ok | `huf/huf/doctype/agent_summary_prompt/` | Real doctype with fork/attach/detach/promote API surface |

### 2.3 Conversation Data

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `enable_conversation_data` | ok | `huf/ai/sdk_tools.py:235`; `agent_integration.py:1480,2629` | Gates tool registration + prompt injection |
| `inject_conversation_data` | ok | `huf/ai/agent_integration.py:1480,2629` | Controls per-turn auto-injection; safe default=1 |
| `conversation_data_api_permission` | **gap** | `huf/ai/conversation_data_tools.py:169,188` | No default value (`agent.json:685`) → empty string → `PermissionError` if unset. Also: API endpoints check the permission value but **do not verify `enable_conversation_data==true`** first — UI hides the field when disabled, but that's presentation-layer only, not a server-side gate. |
| `max_context_chars` | ok | `huf/ai/conversation_manager.py:185`; `agent_integration.py:1649` | Always active, floor of 500 chars enforced |

### 2.4 Reasoning Configuration

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `reasoning_mode` | ok | `huf/ai/reasoning.py:176-193` (via `litellm.py:737-769,1458-1489`) | Real, live wiring for both streaming and non-streaming paths |
| `reasoning_budget_tokens` | **gap** | `huf/ai/reasoning.py:176-182` | UI only shows this field when `reasoning_mode === 'On'`, but backend applies `budget_tokens` for Anthropic models when mode is `'on'` **or** `'auto'`. Users on `Auto` mode cannot set a custom budget — they silently get the hardcoded 4096 default. |
| `reasoning_effort` | **gap** | `huf/ai/reasoning.py:52` | `ReasoningCapabilities.supported_efforts` is computed by `detect_model_capabilities` but never read by `resolve_reasoning`/`build_reasoning_kwargs` — no server-side validation that the chosen effort is actually supported by the target model. |
| `reasoning_summary` | ok | `huf/ai/reasoning.py:176-193` | Passed through for non-Anthropic providers |
| (test coverage) | note | `huf/ai/tests/test_reasoning.py:29` | `test_detect_capabilities_heuristics` is quarantine-skipped (pending CI litellm version fix) — pre-existing, explained, not a new gap, but reduces coverage of Auto-mode capability detection |

### 2.5 Memory Settings

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `enable_memory` | ok | `huf/ai/sdk_tools.py:293-317`; `agent_integration.py:412-433` | Gates both tool registration and system-prompt injection |
| `memory_policy` | ok | `huf/huf/doctype/memory_policy/memory_policy.py`; `huf/ai/memory_tools.py:140-177` | Real doctype, enforced record-type/TTL/promotion rules |
| `enable_memory_search_tool` / `enable_memory_write_tool` | **gap** | `huf/ai/agent_integration.py:412-420` | The always-injected system prompt tells the model it has **both** memory tools regardless of these toggles' state — if write is off, model is instructed to call a tool that was never registered, causing a tool-not-found failure or a false belief it saved something. |
| `enable_memory_search_tool` / `enable_memory_write_tool` | **gap** | `huf/ai/memory_tools.py:112,307` | `search_memory_records`/`save_memory_record` are `frappe.whitelist()` endpoints callable directly via REST/RPC independent of the toggles — defense-in-depth gap, not a broken UI promise (normal chat flow respects the toggles). |

### 2.6 HUF UI (Advanced Settings)

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `agent_color` | ok | `huf/huf/doctype/agent/agent.py:441-462` | Random palette assignment + full frontend rendering |
| `show_tool_execution_details` | **half_implemented** | `huf/huf/doctype/agent/agent.json:864-869` | Frontend filters Tool Call/Result messages correctly; backend field is **write-only** — never read server-side. Pure UI preference, not a functional gap, but worth documenting as such rather than leaving it looking like a backend toggle. |
| `show_tool_execution_details` | **gap** | `agent.json:864` vs `AgentFormPage.tsx:287` | Default value mismatch: doctype default is `1` (shown), frontend form default is `false` (hidden) — agents created via API/seed vs. via UI start in opposite states. |

### 2.7 Model / Modality Settings

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `tts_voice` | gap | `agent.json:176-179` | Plain Data field, no validation against provider's valid voice IDs — fails only at runtime |
| `image_generation_model` | half_implemented | `agent.py:240-245`; `huf/ai/handlers/media.py:78-82` | Modality validated at save; API key presence only checked at runtime |
| `tts_model` | half_implemented | `agent.py:248-253`; `media.py:517-524` | Same pattern — modality checked, API key not |
| `stt_model` | half_implemented | `agent.py:256-261`; `huf/ai/audio_service.py` | Same pattern |
| `image_generation_model` / `tts_model` / `tts_voice` / `stt_model` (consumption) | ok | `media.py:87-118, 429-575, 502-530`; `audio_service.py` | All four are genuinely resolved and used at generation time with correct priority ordering |

### 2.8 Document Upload

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `allow_file_upload` | ok | `huf/ai/agent_chat.py:634,752` | Gates upload capability fully |
| `enable_ocr` | half_implemented | `agent_chat.py:670,789` | Routes to OCR processing but `Agent.validate()` never checks the selected model actually supports the OCR modality (unlike the sibling pattern at `agent.py:230-261` for image/tts/stt models) — surfaces only at upload time |
| `max_upload_size_mb` | ok | `agent_chat.py:645-646,755-756` | Capped at 25MB server-side, default fallback consistent |

### 2.9 Code Execution

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `allow_code_execution` | ok | `huf/ai/tool_registry.py:106-138`; `huf/ai/tools/code_execution.py:549-557` | Gated at tool-offer time and re-checked fail-closed at dispatch |
| `execution_profile` | ok | `huf/ai/tools/code_execution.py:559-592` | Real doctype, snapshotted into audit row per call |
| `execution_shared_dir_limit_mb` | ok | `huf/ai/tools/code_execution.py:221-242` | Override-down-only enforced server-side, matches UI copy exactly, has dedicated tests |

### 2.10 SSH Execution

| Field | Status | Backend location | Notes |
|---|---|---|---|
| `allow_ssh` / `ssh_connections` | ok | `huf/ai/tool_registry.py:141-171` | Capability check + flag + at-least-one-enabled-connection gate, matches UI description precisely |
| `ssh_connections` (PTY deferral claim) | ok | `huf/ai/tools/ssh_execution.py:1-9` | UI's "PTY sessions deferred" text matches module docstring — accurate, not aspirational |
| Execution Profile fallback note | unclear | `huf/ai/tools/ssh_execution.py:338` | UI claims a fallback to "strict default timeouts + Ask Every Time" when no profile is set. `approval_mode` default-to-`'Ask Every Time'` is confirmed; the exact "strict" default timeout values vs. profile defaults were not fully traced — needs a quick confirm, not a known defect |

---

## 3. Prioritized Action List

### P0 — blocks v1 / user-facing broken promise

1. **`summary_ratio` is fully dead code.** The Summarization Engine UI section (`AdvancedTab.tsx:270-289`) presents "Fraction of history to compress (e.g., 0.7 = 70%)" as a live control. It is saved (`agent_config_api.py:58`, `agent.json:413`) but never read by the only live summarization path, `run_background_summarization` (`huf/ai/agent_integration.py:780-838`), which uses `history_limit`-based overflow instead.
   - **Fix option A (minimal, recommended for v1):** Remove the field from the UI (or mark it "Reserved / not yet implemented") until it's wired.
   - **Fix option B (full fix):** Thread `summary_ratio` into `run_background_summarization`'s overflow computation, or wire `ConversationManager.summarize_conversation` (`conversation_manager.py:697-707`) as the actual call site and delete the redundant overflow-based path in `agent_integration.py`.
   - Either way, do not ship v1 with a control that visibly does nothing — pick one.

### P1 — should fix before v1

2. **`conversation_data_api_permission` has no default and no server-side dependency on `enable_conversation_data`.** `agent.json:682-686` — add a default (`""` should map to "no access" cleanly, verify it does) and add an explicit `enable_conversation_data` check inside `huf/ai/conversation_data_tools.py:169,188` rather than relying on frontend field-hiding.
3. **Memory tool instructions don't branch on `enable_memory_search_tool`/`enable_memory_write_tool`.** `huf/ai/agent_integration.py:412-420` unconditionally tells the model it has both tools whenever `enable_memory` is on. Fix: build the instruction text conditionally on the two sub-toggles, matching what `sdk_tools.py:296-299` actually registers.
4. **`reasoning_budget_tokens` UI visibility gate is stricter than backend consumption.** UI hides the field unless `reasoning_mode === 'On'` (`AdvancedTab.tsx:646`), but backend applies it for `'on'` OR `'auto'` (`huf/ai/reasoning.py:176-182`). Either show the field for Auto mode too, or restrict backend consumption to `'On'` only — pick the one that matches intended UX.
5. **`show_tool_execution_details` default mismatch.** Doctype default is `1` (`agent.json:864`), frontend form default is `false` (`AgentFormPage.tsx:287`). Align the two so API-created and UI-created agents behave the same out of the box.
6. **`enable_ocr` has no pre-save modality validation**, unlike its siblings (`image_generation_model`, `tts_model`, `stt_model`). Add an OCR-modality check to `Agent.validate()` mirroring `_validate_advanced_models()` (`agent.py:230-261`).
7. **API-key presence is never validated at save time** for `image_generation_model`, `tts_model`, `stt_model` — only modality is checked (`agent.py:240-261`). Misconfigured providers only surface at first runtime call (`media.py:78-82,517-524`; `audio_service.py`). Consider a save-time warning (not necessarily a hard block, since keys can be added later) so admins get earlier feedback.
8. **`search_memory_records` / `save_memory_record` are whitelisted endpoints with no server-side enforcement of the per-agent tool toggles.** `huf/ai/memory_tools.py:112,307` — toggles only gate what the SDK offers inside a chat session, not the raw API surface. Add an agent-scoped check inside the endpoints themselves if these are reachable by an authenticated non-owner caller.

### P2 — cleanup / nice-to-have

9. Delete or wire up the dead `summarize_conversation` method in `conversation_manager.py:697-707` — it has zero callers and duplicates logic already live in `agent_integration.py`. Leaving it invites a future maintainer to "fix" the wrong function.
10. `ReasoningCapabilities.supported_efforts` (`huf/ai/reasoning.py:52`) is computed but never consulted — either wire it into `resolve_reasoning`/`build_reasoning_kwargs` for real validation, or remove the field to avoid implying a check that doesn't happen.
11. Un-quarantine `test_detect_capabilities_heuristics` (`huf/ai/tests/test_reasoning.py:29`) once the CI litellm version issue is resolved — currently reduces coverage of Auto-mode capability detection.
12. Confirm the exact "strict default timeout" values referenced in the SSH Execution Profile fallback UI copy (`AdvancedTab.tsx:1236`) against `ssh_execution.py`'s actual defaults, to close out the one `unclear` finding.
13. `tts_voice` has no validation against the selected provider's valid voice list (`agent.json:176-179`) — low-severity, since failure is a clear runtime error, but a client-side or save-time allow-list per provider would improve UX.

---

## 4. Cross-Cutting Issues

- **Silent-default / write-only fields.** Three separate sections (`conversation_data_api_permission`, `show_tool_execution_details`, `summary_ratio`) show the same shape of bug: a field that is fully wired for storage and UI rendering but either has no meaningful default, is never read backend-side, or has a default that disagrees between doctype and frontend. This suggests the Agent doctype and the AdvancedTab form were evolved somewhat independently — worth a lightweight process fix (e.g., a lint/test that every writable "advanced" field must appear in at least one non-test backend read, and that doctype defaults match frontend form defaults).
- **"Validate modality, not credentials" pattern.** `image_generation_model`, `tts_model`, `stt_model`, and (missing entirely) `enable_ocr` all share the same half-implementation shape: `Agent.validate()` checks that the linked AI Model supports the right modality, but never checks the provider actually has an API key configured. This is a deliberate-looking but incomplete pattern — either extend `_validate_advanced_models()` (`agent.py:230-261`) to do a light key-presence check for all four modality fields at once, or explicitly document that key validation is intentionally deferred to runtime.
- **UI conditional gating (`depends_on`) used as the only enforcement layer.** `conversation_data_api_permission` and (to a lesser extent) the memory tool endpoints rely on the frontend hiding a field/control as if that were a security boundary, when the backend endpoint itself doesn't re-check the parent toggle. This is a recurring category worth a general audit pass across all `depends_on`-gated Advanced Tab fields, not just the two flagged here.
- **Dead-but-not-deleted code paths.** Both `summary_ratio`'s only real consumer (`ConversationManager.summarize_conversation`) and the field itself are examples of a redesign that left the old implementation in place instead of removing it. This is the single highest-impact issue found and should be resolved rather than just documented (see P0 above).
- **Defense-in-depth vs. enforcement gaps are consistently distinguished correctly in the source findings** (e.g., code_execution and SSH sections explicitly note re-checks at dispatch time as good design) — the memory and conversation-data sections are the two places that pattern is *missing*, and that asymmetry is itself informative: newer/more heavily tested subsystems (code execution, SSH) got the fail-closed treatment; older subsystems (memory, conversation data) did not.

---

## 5. Resolution (branch `fix/agent-advanced-settings-audit`)

| # | Item | Status | Change |
|---|---|---|---|
| P0-1 | `summary_ratio` dead code | **Fixed** | Wired into `run_background_summarization` (`agent_integration.py`) — the compression size is now `max(overflow_count, len(history) * summary_ratio)`, clamped to [0.1, 0.95]. Deleted the dead, uncalled `ConversationManager.summarize_conversation` (`conversation_manager.py`). |
| P1-2 | `conversation_data_api_permission` no server-side `enable_conversation_data` check | **Fixed** | `api_get_conversation_data` / `api_set_conversation_data` (`conversation_data_tools.py`) now require `enable_conversation_data` truthy in addition to the permission level. |
| P1-3 | Memory tool instructions ignore sub-toggles | **Fixed** | System prompt in `agent_integration.py` now only mentions `search_memory_records`/`save_memory_record` when the corresponding `enable_memory_search_tool`/`enable_memory_write_tool` is actually on. |
| P1-4 | `reasoning_budget_tokens` UI/backend visibility mismatch | **Fixed** | UI now shows the field for both `On` and `Auto` modes (`AdvancedTab.tsx`), matching backend consumption in `reasoning.py`. |
| P1-5 | `show_tool_execution_details` default mismatch | **Fixed** | Frontend new-agent default changed from `false` to `true` (`AgentFormPage.tsx`) to match the doctype default of `1`. |
| P1-6 | `enable_ocr` missing modality validation | **Fixed** | `Agent._validate_advanced_models()` now checks the agent's primary model supports the `OCR` modality when `enable_ocr` is set, mirroring the image/tts/stt pattern. |
| P1-7 | No save-time API-key validation for image/tts/stt models | **Deferred** | Left as runtime-only by design per the doc's own note (keys can be added after agent creation); flagged for a future pass rather than blocking this round. |
| P1-8 | Memory endpoints bypass per-agent toggles via raw API | **Fixed** | `save_memory_record` / `search_memory_records` (`memory_tools.py`) now check `enable_memory` + the specific sub-toggle for non-manager callers when `agent_name` is supplied. |
| P2-9 | Dead `summarize_conversation` method | **Fixed** | Deleted (see P0-1). |
| P2-10 | Unused `supported_efforts` | **Fixed** | `reasoning.py` now validates the requested `reasoning_effort` against `capabilities.supported_efforts`, falling back to a supported tier instead of silently sending an unsupported value. |
| P2-11 | Quarantined reasoning test | **Deferred** | Blocked on an external CI litellm version fix, out of scope for this pass. |
| P2-12 | Unclear SSH timeout defaults | **Deferred** | Documentation-only clarification, no code change needed. |
| P2-13 | `tts_voice` no validation | **Deferred** | Low severity, runtime error is already clear; left for a future UX pass. |

Verified: `python3 -m py_compile`/AST-parse clean on all touched Python files; `yarn build` (real production build, not just `tsc --noEmit`) passes with no errors after the fixes.
