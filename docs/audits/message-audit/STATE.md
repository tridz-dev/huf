# STATE — Agent Message context semantics (as-built)

Audit base: `origin/develop` @ `2c3fd73c81d2af40a392c7dbd1976f6068019d20` (rebasing
covered in CONTEXT.md). All citations are repo-relative paths with lines at that
commit. Terminology follows `Tracks/CodeDiscovery/GLOSSARY.md` (frozen). Built from
first-hand reading (schema, consumer, tests, public API) plus focused re-sweeps for
this rebase: write-path census (A), Agent Tool Call map (B), execution records (C1),
read-side/frontend consumers (C2).

---

## 1. Schema inventory — `huf/huf/doctype/agent_message/agent_message.json`

The DocType has **no controller logic** (`agent_message.py` is an empty `Document`
subclass). Every semantic lives in writers and readers scattered across `huf/ai/`.

Field groups:

| Group | Fields | Notes |
|---|---|---|
| Identity/linkage | `conversation` (Link), `conversation_index` (Int), `session_id`, `user` (Data, not Link), `agent`, `agent_run` (Link), `provider`, `model` | `user` is plain Data — holds a username, external id, or the literal string `"Agent"` |
| Content | `content` (Code/Markdown), `content_type` (Text/JSX/Mermaid/Markdown/Artifact/HTML/Image), `role` (user/tool/agent/system, default user, hidden), `is_agent_message` (Check) | `role="agent"` maps to OpenAI `assistant` at read time |
| Kind — **two parallel fields** | `kind` (Message/Tool Call/Tool Result/Status/Error/Image/Audio/Video, no default) and `record_kind` (message/tool_call/tool_result/retrieval_context/result_snapshot/artifact/summary/status/error/debug_trace, no default) | Same concept, two vocabularies; see §5 |
| Tool-call block | `tool_call` (Link→Agent Tool Call), `tool_name`/`tool_args`/`tool_status` (**`fetch_from`** the link), `tool_call_id` (Long Text — provider call id), `tool_calls` (JSON hidden — OpenAI-style array), `raw_payload` (JSON hidden) | `fetch_from` materializes copies at insert; see §7 |
| Media/voice | `generated_image`, `generated_audio`, `generated_video`, `voice_message`, `tts_voice`, `tts_model`, `stt_model` | `generated_video` was the missing-field 417 bug (ProviderBrand417 track) |
| **Context semantics** | `context_policy` (8 options, no default), `record_kind` (no default), `context_summary` (Small Text), `reference_doctype` + `reference_name` (**both plain Data**, not Link/Dynamic Link), `visibility` (5 options, default `user_visible`), `token_estimate` (Int) | Detailed per-field analysis in §3 |
| Lifecycle | `status` (Started/`Queues`/Completed/Failed, hidden) | `Queues` typo — fixed on `origin/develop`; still present at audit base |

Permissions (`agent_message.json:346-391`): System Manager + Huf Manager full; **Huf
User can create/write**; Huf Viewer read. Row-level scoping exists only as a
list-query condition — `get_message_permission_conditions`
(`agent_integration.py:3328+`, registered `hooks.py:165`) restricts message lists
to conversations the user owns unless they hold `chat.view_all`. There is **no
doc-level `has_permission` hook**, and the `visibility` field does **not** interact
with Frappe permissions at all; it is pure metadata (nothing enforces it — see §3.4).

---

## 2. History assembly — the only policy consumer

`ConversationManager.get_conversation_history` (`huf/ai/conversation_manager.py:517-550`)
fetches the last N messages (`conversation_index desc`, then reversed) projecting:

```
role, kind, content, context_policy, context_summary, reference_doctype,
reference_name, record_kind, tool_call, tool_call_id, tool_calls, creation
```

**Not fetched: `visibility`, `token_estimate`, `status`, `content_type`, media
fields.** Whatever those fields say has zero effect on what the model sees.

The slice limit is a **message count** (default 20, caller passes
`(history_limit or 20) + 10` — `agent_integration.py:1160+`), never tokens. Token-based
bounding exists only for knowledge (RAG) injection, separately
(`knowledge/context_builder.py`, `max_knowledge_tokens or 4000`).

### 2.1 `_message_to_context` (`conversation_manager.py:573-714`) — policy truth table

| `context_policy` | Actual behavior | Sound? |
|---|---|---|
| `NULL`/missing | treated as `include_full` (`:575`) | backward-compat, fine |
| `include_full` | full `content` | ✅ as named |
| `include_summary` | `context_summary` **or full content fallback** (`:588`) | ⚠️ silent fallback doubles cost when summary missing |
| `include_reference` | emits `[record_kind: summary · handle=Dt/Name]` text (`:589-597`); raw content excluded | ✅ works; the only place `record_kind` is ever read |
| `include_on_demand` | **dropped entirely** (`:578`) | ❌ misnamed: no handle is left behind, so the model cannot know the content exists to demand it |
| `exclude` | dropped entirely | ✅ as named (indistinguishable from `transient_only`) |
| `transient_only` | dropped entirely | ⚠️ duplicates `exclude`; "transient" intent (show once, then drop) is not implementable — no "seen" marker exists |
| `token_budgeted` | `context_summary` or content (`:598-599`) | ❌ **no budgeting**: `token_estimate` is never read by history assembly; behavior identical to `include_summary` |
| `provider_cached` | full content (`:600-601`) | ❌ **no caching semantics**: identical to `include_full`; pure label |

Of 8 declared policies: 4 work as named (`include_full`, `include_summary` with
caveat, `include_reference`, `exclude`), 2 are aliases that mislead
(`token_budgeted`→summary, `provider_cached`→full), 1 is a no-op duplicate
(`transient_only`), 1 is broken-by-design (`include_on_demand` — no discovery path).

### 2.2 Tool-call expansion (`:581-662`)

Three persisted shapes are recognized and expanded into OpenAI-style
assistant(`tool_calls`) + `role:"tool"` pairs:

1. **Assistant tool-call row** — `kind="Tool Call"` or any of `tool_call`/
   `tool_call_id`/`tool_calls` set → `{role:assistant, content:None, tool_calls:[...]}`.
   Stored `tool_calls` JSON preferred; else synthesized from the linked Agent Tool
   Call (`_resolve_tool_call_details`, `:528-547`).
2. **Combined row** — `kind="Tool Result"` with role agent/assistant → returns a
   **pair** `[assistant(tool_calls), tool(result)]` (`:629-650`). This is the shape
   produced by the merge path (`update_tool_call_message`, §6).
3. **Separate tool row** — `role="tool"` → single `role:"tool"` message (`:653-662`).

`repair_message_sequence` (`:229-321`) runs before every completion call in the sync
path (`providers/litellm.py:484`, inside the round loop) but only **once per run** in
the stream path (before the round loop — rounds 2+ reuse the repaired
sequence): drops assistant declarations with no
matching results, synthesizes missing assistant declarations from Agent Tool Call
(`_synthesize_assistant_tool_call`, `:107-138`), drops unrepairable tool results, and
**writes an Error Log entry on every repair** (`:321-328`) — routine trims become
error-log spam.

### 2.3 Ordering & indexing hazards

- `add_message` assigns `conversation_index = MAX(conversation_index)+1` via SQL
  (`conversation_manager.py:439-467`). No unique constraint, no locking → concurrent
  inserts in one conversation can share an index; history order between equal indices
  is undefined.
- `audio_service.py` duplicates the same MAX+1 pattern (`:697-708`) for voice messages.
- The media-tool paths in `sdk_tools.py` no longer assign `conversation_index`
  directly (they route through `ConversationManager.add_message`); the MAX+1 hazard is
  now concentrated in `conversation_manager.py` and `audio_service.py`.
- `total_messages` on the conversation is set to `last_index+1` (`:507-510`) — a
  denormalized counter that drifts if any insert fails between the two writes.

---

## 3. The five context fields — writers, readers, verdict

| Field | Writers | Readers | Verdict |
|---|---|---|---|
| `context_policy` | `update_tool_call_message` (`conversation_manager.py:198`) + sync fallback (`agent_integration.py:1654`) — the only automatic writers: `include_reference` iff result > `agent.max_context_chars` (default 2000, min 500), else explicit `include_full`; public API passthrough (`agent_chat.py:1054-1089`); code execution writes it on `Agent Context Artifact` (`code_execution.py:349`) | `_message_to_context` only | **Two policies ever set automatically on Agent Message.** The other 6 are reachable only via the public API, desk, or tests. `Agent Context Artifact` uses `context_policy` for display/filter but not as an enforced model-context contract |
| `record_kind` | same two paths → `tool_result` only (`conversation_manager.py:197`, `agent_integration.py:1653`); API passthrough | `_message_to_context` `include_reference` formatting (`:590`) | 9 of 10 values never written by app code; cosmetic even when read |
| `context_summary` | same two paths → first 200 chars + `"..."` (`:180,199`, `:1638`); API passthrough | `include_summary` / `token_budgeted` / `include_reference` paths | Works, but summary = dumb truncation, never a real summary |
| `visibility` | **Nothing on Agent Message** (schema default `user_visible`); API passthrough (`agent_chat.py:1058-1088`); `Agent Context Artifact` has a writer (`code_execution.py:348`) | **Nothing on Agent Message** — not projected in history query, no query filter, no permission branch, no UI. The `ui_only`/`audit_only`/`model_visible`/`developer_only` options are dead values for messages | **Dead field on Agent Message** (repo-wide confirmed, sweep C2). Live only on `Agent Context Artifact` |
| `token_estimate` | **Nothing on Agent Message**; API passthrough; `Agent Context Artifact` has a writer (`code_execution.py:351`) | **Nothing on Agent Message** — not even history assembly fetches it | **Dead field on Agent Message** (repo-wide confirmed, sweep C2). Live only on `Agent Context Artifact` |

**Read-side census (sweep C2, repo-wide):** besides `_message_to_context`, no code
branches on any of the five fields for Agent Message. None of the five is ever sent
to a client: the React app's message APIs request only legacy fields
(`chatApi.ts:291-323`), the realtime `new_agent_message` payloads carry only
`kind`+media (`sdk_tools.py:1666-1680`), the TS types omit them (`chatApi.ts:39-71`),
and rendering branches on legacy `kind` alone (`ChatMessage.tsx:71-83`,
`chatMessageList.mappers.ts:207-230`; `Status`/`Error` kinds have no UI branch and
render as plain text). The same-named fields on **Agent Context Artifact** *are*
read by the frontend — display/filter only (`agentContextArtifactApi.ts:39-88`,
`AgentContextArtifactsPage.tsx`) — and that doctype still has no creation path
(CodeDiscovery B-01, re-confirmed: zero creation UI, zero backend writer).

### 3.4 The public write API is a trust-boundary hole

`agent_chat.add_message` (`agent_chat.py:1049-1099`) is `@frappe.whitelist()` (no
`allow_guest`, so any authenticated session). It loads the conversation but performs
**no ownership or write-permission check** on it (only the standard `Agent Message`
create/write permission checks inside `ConversationManager`). It has **zero in-repo
callers** (sweeps A+C2) — an unused but live endpoint. Any logged-in user can:

- insert a message into **any** conversation by id;
- choose `role` freely — including `system` or `agent` — injecting content that
  re-enters the model window as `include_full` by default (prompt-injection vector
  into other users' agent runs);
- set `visibility`/`token_estimate`/etc., which nothing reads — the API offers knobs
  with no effect, while the effective knob (policy) is unchecked input.

---

## 4. Write-path census (sweep A, verified repo-wide)

Hub: `ConversationManager.add_message` (`conversation_manager.py:415-516`). Census:

| Path | Trigger | Context-field writes |
|---|---|---|
| `agent_integration.py:1160` (sync) / `:1572` (stream tool-call start) | user prompt / tool call starts | none (`kind="Message"`) / `kind="Tool Call"`, `tool_call` link, `tool_call_id`, `tool_calls` JSON |
| `agent_integration.py:1642-1658` (stream fallback) | tool result, merge failed | `kind="Tool Result"`, `record_kind="tool_result"`, policy per threshold, `context_summary`, `reference_*` |
| `agent_integration.py:1846` / `:2927` | final agent reply | none |
| `agent_integration.py:2008+` / `:3079+` / `:3188+` | error events | `kind="Error"` |
| `conversation_manager.py:141-227` (update) | tool result merge | see §6 |
| `agent_chat.py:1049-1099` (whitelisted API) | external HTTP | passthrough of all five fields (see §3.4) |
| `agent_chat.py:37-45,168-176,477-485,584-592,784-792` | voice/file uploads | `kind="Audio"`/`"Message"`; note `:477-485`/`:584-592` insert **with** permissions — inconsistent with every other path |
| `sdk_tools.py` | image/audio/STT tool results | `kind="Image"`/`"Audio"`; no longer writes `Agent Message` directly; routes through `ConversationManager.add_message` |
| `code_execution.py:341-362` | code-execution file write-back | writes `context_policy`, `visibility`, `token_estimate` to `Agent Context Artifact` (not `Agent Message`) |
| `ocr_engine.py` | OCR extraction | none |
| `transcription_handler.py` | provider STT | none (no `kind`, no `session_id`) |
| `elevenlabs_convai_api.py` | voice-call transcript backfill | none; then `db_set("creation", ...)` rewrites timestamps |
| `patches/v1/repair_tool_call_messages.py` | migration | backfills `tool_call_id`/`tool_calls` from Agent Tool Call |

Census conclusions:

- **Only two paths** ever set `context_policy` on `Agent Message` (same threshold
  rule) and **`tool_result` is the only `record_kind` ever written** by app code.
  `include_summary / exclude / transient_only / token_budgeted / provider_cached /
  include_on_demand` and the other 9 record kinds are written **only by tests** or
  the public API. `Agent Context Artifact` now has writers for `context_policy`,
  `visibility`, and `token_estimate` (`code_execution.py:341-362`), but those fields
  remain dead on `Agent Message` itself.
- **No writers anywhere** for `status`, `content_type`, `generated_video` — three
  more dead-on-arrival fields beyond `visibility`/`token_estimate` on `Agent Message`.
- `flow_engine.py` and `huf/ai/orchestration/` write **zero** Agent Messages
  directly; flow/orchestration messages exist only via `run_agent_sync`.
- `sdk_tools.py` realtime socket events (`new_agent_message`) are not writes.
- ATC↔AM asymmetry both directions: (i) streaming — if the message lookup for the
  merge fails, the result is saved on the Agent Tool Call and **no message gets it**
  (only an error log, `litellm.py:1709-1748`); sync — `process_tool_call(is_output=True)`
  returns `None` when no Queued ATC is found (`agent_integration.py:618-719`), no
  message written. (ii) Media/user/error messages have no `tool_call` link at all;
  the sync path needs a special `kind="Image"` lookup to merge image results.
- ~~`add_message` `user` field bug (`conversation_manager.py:441`)~~ — **withdrawn
  (verification pass 2026-07-18)**: Python's conditional expression binds looser than
  `or`, so the line parses as `(external_id or session.user) if role == "user" else
  "Agent"`. Agent messages always get `user="Agent"`; no leak exists (ex-MA-14).

---

## 5. The `kind` / `record_kind` duality

Two fields classify the same rows:

- `kind` — UI vocabulary: `Message/Tool Call/Tool Result/Status/Error/Image/Audio/Video`
  (drives media `depends_on` rendering and the history tool-call expansion).
- `record_kind` — context vocabulary: `message/tool_call/tool_result/
  retrieval_context/result_snapshot/artifact/summary/status/error/debug_trace`.

They overlap for 5 values (message/tool_call/tool_result/status/error) with different
spellings; `record_kind` adds 5 values no writer produces automatically
(`retrieval_context`, `result_snapshot`, `artifact`, `summary`, `debug_trace`). No
code keeps them consistent — `update_tool_call_message` sets both
(`kind="Tool Result"`, `record_kind="tool_result"`, `:195-196`), other writers set
`kind` only, so `record_kind` is NULL on virtually all rows. The read side only
consults `record_kind` when formatting an `include_reference` handle — i.e. the
classification that matters for the model is `kind`, and `record_kind` is near-dead.

---

## 6. Tool result merge path — `update_tool_call_message` (`conversation_manager.py:140-217`)

The streaming-era "one row per tool interaction" mutation:

1. loads the Agent Message created when the tool call started;
2. appends `\n\n**Tool Result:**\n{result}` to `content` (guarded against double-append
   by a substring check, `:192`);
3. flips `kind` → `Tool Result`, `record_kind` → `tool_result`;
4. sets policy: `include_reference` if `len(result) > max_context_chars` else
   `include_full`; always writes `context_summary` (200-char truncation);
5. points `reference_*` at the linked Agent Tool Call; stores provider `tool_call_id`
   and the raw `tool_calls` payload;
6. `save(ignore_permissions=True)`; swallows all exceptions → returns `False`
   (callers log and continue — a failed merge leaves a permanent `kind="Tool Call"`
   row whose result never lands; history then shows a declaration without result and
   `repair_message_sequence` drops or re-synthesizes it).

Soundness notes:

- The `include_reference` threshold is **characters, not tokens** (`max_context_chars`,
  default 2000) — the field the schema offers for this (`token_estimate`) is unused,
  so the one size-control knob is a char heuristic.
- The tool message sent to the model carries the **entire mutated `content`**
  (call text + result text) — the "don't leak UI text" sanitation at `:619-621`
  applies only to the Tool Call branch, not the combined Tool Result branch.
- If the `tool_call` link is missing, `_resolve_tool_call_details` yields an empty
  tool name and `{}` args (`:532-547`) — an invalid function declaration is then sent
  to the provider.

---

## 7. Duplication with Agent Tool Call (sweep B, verified)

### 7.1 Agent Tool Call inventory — `huf/huf/doctype/agent_tool_call/`

10 fields: `agent_run`, `conversation`, `tool` (Data), `tool_args` (JSON),
`tool_result` (JSON), `status` (Started/Queued/Completed/Failed, hidden), `call_id`
(Long Text), `error_message`, `is_mcp_tool`, `mcp_server`. **No token/cost fields.**
Permissions: **System Manager only**. Controller empty. Writers exist in exactly two
files:

| Writer | What |
|---|---|
| `agent_integration.py:451-464` (`process_tool_call`, request) | insert `status="Queued"`, MCP detection (`:438-441`), `call_id` |
| `agent_integration.py:397-428` (`process_tool_call`, output) | find Queued by run+`call_id` → update `tool_result` (140k cap, `:411-419`), `status` Completed/Failed, `error_message` |
| `providers/litellm.py:1089-1102` (stream) | update by conversation+`call_id`; `status="Completed"` **hardcoded** (`:1096`) |

Readers: history reconstruction (`_synthesize_assistant_tool_call`,
`_resolve_tool_call_details`), the agent-callable `get_result_context`
(`sdk_tools.py:1373-1414`, advertised in system instructions
`agent_integration.py:242-246`), desk dashboards. **Zero frontend references** — the
tool-call UI is built entirely from the message's `fetch_from` copies and socket
events (`chatApi.ts:305-306`, `useChatSocket.tsx`).

Status semantics are broken two ways: `"Started"` is never written (dead option,
joins CodeDiscovery C-01), and the `Failed` branch is effectively dead — no caller
passes `error=`; a raised tool exception is stored as result text
`"Error executing tool …"` with status **`Completed`** (`litellm.py:1080-1081,1096`).

### 7.2 Field-by-field duplication (ATC vs paired Agent Message)

| Datum | Agent Tool Call | Agent Message | Verdict |
|---|---|---|---|
| Tool name | `tool` | `tool_name` (fetch copy) + `tool_calls` JSON + `content` text | duplicated **3×** |
| Arguments | `tool_args` (JSON) | `tool_args` (fetch copy) + `tool_calls[].function.arguments` + `content` text | duplicated **3×** |
| Status | `status` (authoritative) | `tool_status` (fetch copy, refreshed only on message save) | **can silently disagree** |
| LLM call id | `call_id` | `tool_call_id` + `tool_calls[].id` | duplicated (patch back-fills) |
| Result | `tool_result` (canonical JSON) | stringified into `content`; 200-char `context_summary` | duplicated |
| Error | `error_message` | **nowhere** (socket payload only) | ATC only |
| MCP flags | `is_mcp_tool`, `mcp_server` | — | ATC only |
| Run/conversation links | ✅ | ✅ | duplicated |
| OpenAI-format payload | — (rebuildable) | `tool_calls` JSON | message only, derivable |
| provider/model/agent | — | ✅ | message only |
| Context metadata | — | `record_kind`, `context_*`, `reference_*` (pointing back at the ATC) | message only |
| Tokens/cost | — | — | **neither** (see §7.4) |

Disagreement windows: (a) `tool_status` is `fetch_from` — refreshed only when the
message is saved; if the ATC update succeeds but the message merge fails, the failure
is merely logged (`litellm.py:1141-1151`); in the sync fallback path the original
Tool Call message is never re-saved after the ATC flips to Completed
(`agent_integration.py:984-1009`) → `tool_status="Queued"` forever. (b) Errors never
reach the message. (c) `kind` is mutated in place Tool Call → Tool Result, so one
message row represents both request and result while the ATC holds the lifecycle.

**Source of truth is the ATC** — proven by direction of repair:
`patches/v1/repair_tool_call_messages.py` back-fills message columns *from* the ATC;
`_synthesize_assistant_tool_call` rebuilds model context from the ATC; the provider
docstring says "We keep the full result in the Agent Tool Call record for audit /
reference" (`litellm.py:201-208`); `get_result_context` serves the canonical full
result from the ATC. Agent Message tool rows are denormalized presentation/context
copies that can silently disagree with the truth.

### 7.3 Flow `tool.call` gap — confirmed

`_exec_tool_call` (`flow_engine.py:539-607`) creates **no Agent Tool Call** — only an
audit Agent Run with `run_kind="tool"` (`_create_flow_agent_run`, `:1265-1281`).
Captured: tool name+args as an unstructured `prompt` string, result JSON in
`response`, error, flow linkage. Lost vs ATC: conversation link, `call_id`,
structured `tool`/`tool_args`/`tool_result`, MCP flags. (CodeDiscovery B-04: model
violation — every tool invocation should produce a Tool Call.)

### 7.4 Token/cost accounting — no double count, but a real undercount

- ATC has no token/cost fields; Agent Message only the dead `token_estimate`.
- Agent Run `input/output/cached_tokens` + `cost` written **once per run** (sync
  `agent_integration.py:1127-1132`; stream `:1706-1717`); Agent Conversation totals
  incremented by raw SQL `+=` once per run (`:1115-1123` / `:1689-1697`); providers
  accumulate usage across LLM rounds in memory. **No double counting via ATC.**
- **Stream undercount bug:** in `run_stream`, `stream_usage` is reset per tool round
  (`litellm.py:975`) and overwritten by each usage chunk (`:984-989`), so the
  `complete` event carries **only the final round's usage** — tool-call rounds'
  tokens vanish from Agent Run and Conversation totals for streaming runs, and the
  stream cost computation inherits the same undercount (`litellm.py:1238-1255` →
  `agent_integration.py:1657`). Sync accumulates correctly.
- Conversation totals are fire-and-forget SQL; failures only logged
  (`:1124-1125,1698-1699`) → run-level and conversation-level totals drift silently.

---

## 8. Test-pinned behavior — `huf/ai/tests/test_context_policy.py`

The only tests covering this machinery pin: `include_full`, `include_reference`
(raw content excluded, handle present), `exclude`, `transient_only`, NULL backward
compat, bounded token growth under `include_reference` (char-length proxy), and
`include_summary`. Notably **no tests** for `token_budgeted`, `provider_cached`,
`include_on_demand`, `visibility`, `token_estimate`, or the tool-pair expansion
shapes — the misleading/unsupported policies are exactly the untested ones.

---

## 9. Branch deltas

- Audit base is now `origin/develop` @ `2c3fd73c`. The `Queues`→`Queued` typo fix
  and Agent Run `reference_doctype`/`reference_name` trigger links are already
  present on this base. No message-semantics change relative to the prior audit.
- `origin/feature/queue-first-agent-runs` has been merged into `develop`; the
  per-conversation lock and queued-run drainer are now the default execution mode.

---

## 10. The three execution records (sweep C1, verified)

| | **Agent Run** | **Agent Orchestration** | **Flow Run** |
|---|---|---|---|
| Status vocab | Started/Queued/Success/Failed | Planned/Running/Paused/Completed/Failed/Cancelled (+ lowercase per-step `pending/in_progress/done/failed`) | Queued/Running/Waiting Approval/Waiting User/Success/Failed |
| Tokens/cost/duration | ✅ `input/output/cached_tokens`, `cost`, `start_time`/`end_time` — **the only carrier** | ❌ (only `last_run_at`) | ❌ (only `started_at`/`completed_at`) |
| Prompt/response | ✅ `prompt`, `response` | per-step `instruction`/`output_ref`, `scratchpad` | `trigger_payload` + `context_json` (initially **identical**, `flow_engine.py:103,105`) |
| Error | `error_code` + `error_message` | `error_log` | `last_error` |
| Linkage | `parent_run`, `is_child`, `agent_orchestration`, `flow_run`, `flow_node_id`, `flow_id`, `run_kind` | `parent_run` (shell run) | `last_agent_run` (overwritten per node), `conversation` |
| Controller | empty | empty | empty |

Key structural facts:

- **Orchestration = shell parent run + plan rows.** The parent Agent Run never makes
  a provider call (marked Started with a placeholder response,
  `agent_integration.py:762-766`); only final status/summary is mirrored back
  (`orchestrator.py:158-162`, `:208`). Each plan step is a child Agent Run
  (`parent_run` = shell, `is_child=1`), hidden in the UI by the `is_child=0` filter
  (`Executions.tsx:60`).
- **Flow Run retains no node history** — only `last_agent_run`, overwritten per node
  (`flow_engine.py:518,588,664,1221`). Per-node outputs are duplicated into
  `context_json` only when the node opts in (`save_response_to_context`,
  `save_result_to_context`) — the same text stored on the linked Agent Run's
  `response`. The real audit trail is Agent Runs with matching
  `flow_run`+`flow_node_id` — queryable, but nothing aggregates it.
- **Tokens/cost system of record is Agent Run alone**; aggregation duplicated in
  Agent Conversation totals via raw SQL + `Agent.total_run/last_run` counters.
  Orchestration/flow cost must be derived by summing child runs; shell parent runs
  and `run_kind="tool"` audit runs carry none.
- **Agent Message / Agent Tool Call attach to executions only via `agent_run`
  (+`conversation`)** — neither links Flow Run or Agent Orchestration directly, so
  flow/orchestration message timelines must be reconstructed through the run table.
- Dead statuses: Flow Run `Waiting User`, Orchestration `Paused` (declared, read,
  never set). Drift: ElevenLabs webhook writes `total_cost` — **not a field** on
  Agent Run (field is `cost`), silently dropped (`elevenlabs_convai_api.py:194`).
- Frontend: **three separate surfaces, no unified timeline** — Executions page lists
  Agent Runs only (`Executions.tsx:53-60`); Flow Runs appear only inside the flow
  canvas sheets (`FlowRunHistory.tsx`, `FlowRunViewer.tsx`); "orchestration" UI is a
  child-runs card on the run detail page that **never fetches the Agent Orchestration
  doctype** (`AgentRunDetailPage.tsx:135-146,419-425`). Nothing lists Agent
  Orchestration docs anywhere in the React app.

---

## 11. Verdict on the observation

> "HUF has three partially separate execution records—Agent Run, Agent Orchestration,
> and Flow Run—while Agent Message also duplicates tool-call data already stored in
> Agent Tool Call. A rewrite should unify those semantics first; otherwise a new
> language would preserve the same complexity at a higher cost."

**Confirmed, and stronger than stated.** The three execution records are not just
"partially separate": they run three divergent status vocabularies, duplicate error/
timestamp fields under different names, keep tokens/cost in exactly one of them, and
have no unified read surface. The message/tool-call duplication is not symmetric
copying: Agent Tool Call is the de-facto source of truth (repairs flow ATC→message),
yet the UI reads only the denormalized message copies — which can silently disagree
(status staleness, missing errors) — while the truth is System-Manager-only and
frontend-invisible. On top, the context-policy layer that a rewrite would "preserve"
is 8 declared policies of which only 2 are ever written by app code, 4 are aliases
or no-ops, 1 is broken by design, and 2 of the 5 context fields (`visibility`,
`token_estimate`) have no readers at all. A new language over this surface would
inherit all three vocabularies, the 3× tool-data duplication, and the phantom policy
enum — the unification must happen at the semantics layer first. See PLAN.md.
