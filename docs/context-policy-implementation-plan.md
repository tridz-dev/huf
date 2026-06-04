# Context Policy & Out-of-Band Messages — Phase 1 Implementation Plan

**Status:** Ready to implement  
**Branch:** `wip/context-policy-out-of-band-messages`  
**Scope:** Concrete, staged, code-grounded plan to prevent large tool/result payloads from being replayed as conversation history.

---

## Executive Summary

HUF currently persists every tool output and large retrieval payload into `Agent Message.content`, then replays it verbatim in future turns. This causes input token growth proportional to conversation length, defeating cost optimization.

**Fix:** Add a `context_policy` field to `Agent Message` that controls whether/how content enters model context. Large tool outputs default to `include_reference` (compact handle only); model can fetch on-demand via tool. Single control point: `ConversationManager.get_conversation_history()`, used by all paths (sync execution, streaming, title generation, summarization, flow nodes).

**Phase 1 deliverable:** Large tool outputs stop being replayed; token growth stays bounded; all existing behavior preserved via backward-compatible defaults.

---

## Current State: The Bloat Vector

### Where history is loaded (4 call sites in agent_integration.py)
1. **run_agent_sync** (L633): `history = conv_manager.get_conversation_history(conversation.name, limit=fetch_limit)`
2. **run_agent_sync** title gen (L534): `get_conversation_history(..., limit=5)`
3. **run_agent_sync** summarization (L474): `get_conversation_history(..., limit=history_limit+20)`
4. **run_agent_stream** (L1197): `get_conversation_history(conversation.name, limit=1000)`

All four feed `context["conversation_history"]` → `RunProvider.run()` / `RunProvider.run_stream()` → `litellm.py` → final LLM message array.

**Key insight:** if `get_conversation_history()` respects context policy, *all four paths automatically get filtered history*. Single point of control.

### Where large payloads enter Agent Message

**Tool result persistence** (agent_integration.py):
- Sync path: L824 create `Agent Tool Call` with `is_output=False`, L864 update with `tool_result=<json>` and `is_output=True`, **L866-878 append result text to Agent Message.content**.
- Stream path: L1343 create `Agent Tool Call`, but **no text appended to Agent Message** — tool result stays only in the tool-call row.

**Tool outputs stored in two DocTypes:**
- `Agent Tool Call.tool_result` (JSON field, L864) — raw output, already read-only, already the audit home.
- `Agent Message.content` (text, L877) — the bloat: gets replayed in every future turn's history.

---

## Phase 1: Safe History Filtering

### 1. Add fields to Agent Message DocType

File: `huf/huf/doctype/agent_message/agent_message.json`

Add these 7 fields (all nullable for backward compatibility):

```json
{
  "fieldname": "context_policy",
  "fieldtype": "Select",
  "label": "Context Policy",
  "options": "include_full\ninclude_summary\ninclude_reference\ninclude_on_demand\nexclude\ntransient_only\ntoken_budgeted\nprovider_cached",
  "default": null
},
{
  "fieldname": "record_kind",
  "fieldtype": "Select",
  "label": "Record Kind",
  "options": "message\ntool_call\ntool_result\nretrieval_context\nresult_snapshot\nartifact\nsummary\nstatus\nerror\ndebug_trace",
  "default": null
},
{
  "fieldname": "context_summary",
  "fieldtype": "Small Text",
  "label": "Context Summary",
  "read_only": 0
},
{
  "fieldname": "reference_doctype",
  "fieldtype": "Data",
  "label": "Reference DocType"
},
{
  "fieldname": "reference_name",
  "fieldtype": "Data",
  "label": "Reference Name"
},
{
  "fieldname": "visibility",
  "fieldtype": "Select",
  "label": "Visibility",
  "options": "user_visible\nmodel_visible\nui_only\naudit_only\ndeveloper_only",
  "default": "user_visible"
},
{
  "fieldname": "token_estimate",
  "fieldtype": "Int",
  "label": "Token Estimate"
}
```

Add to `field_order` at appropriate section (after `kind`, before metadata). **No migration needed:** `NULL` policy → treated as `include_full` (backward compat).

### 2. Update `ConversationManager.get_conversation_history()` to respect policy

File: `huf/ai/conversation_manager.py`

**Before:** returns every row's full content.
**After:** returns context-filtered content based on policy.

Replace the method (L115-133) with:

```python
def get_conversation_history(self, conversation_name, limit=20):
    """Get conversation history for model context, applying context policies."""
    messages = frappe.get_all(
        "Agent Message",
        filters={"conversation": conversation_name},
        fields=[
            "role", 
            "content", 
            "context_policy",
            "context_summary",
            "reference_doctype",
            "reference_name",
            "record_kind",
            "creation"
        ],
        order_by="conversation_index desc",
        limit=limit if limit else 1000
    )
    
    messages.reverse()
    
    return [
        self._message_to_context(msg)
        for msg in messages
        if self._message_to_context(msg) is not None
    ]

def _message_to_context(self, msg):
    """Apply context policy to a single message. Returns dict for inclusion, None to omit."""
    policy = msg.get("context_policy") or "include_full"  # backward compat
    record_kind = msg.get("record_kind", "message")
    
    # Policies that exclude the message entirely
    if policy in ("exclude", "transient_only", "include_on_demand"):
        return None
    
    # Policies that include something
    result = {
        "role": "assistant" if msg.get("role") == "agent" else msg.get("role"),
    }
    
    if policy == "include_full":
        result["content"] = msg.get("content")
    
    elif policy == "include_summary":
        result["content"] = msg.get("context_summary") or msg.get("content")
    
    elif policy == "include_reference":
        # Generate compact reference line
        summary = msg.get("context_summary", record_kind)
        ref_doctype = msg.get("reference_doctype", "")
        ref_name = msg.get("reference_name", "")
        if ref_doctype and ref_name:
            result["content"] = f"[{record_kind}: {summary} · handle={ref_doctype}/{ref_name}]"
        else:
            result["content"] = f"[{record_kind}: {summary}]"
    
    elif policy == "token_budgeted":
        # Phase 1: treat as include_summary; Phase 4 makes this real
        result["content"] = msg.get("context_summary") or msg.get("content")
    
    elif policy == "provider_cached":
        # Phase 1: treat as include_full; Phase 5 optimizes caching
        result["content"] = msg.get("content")
    
    return result
```

### 3. Update tool result persistence to use context policy

File: `huf/ai/agent_integration.py`

**Sync path** (around L864-878): when tool result is logged, instead of appending to Agent Message.content, create a separate message with context policy.

Replace L877-882 (the text-append block) with:

```python
# Store tool result as separate message with context policy
tool_result_str = str(tool_result)
tool_result_summary = (tool_result_str[:200] + "...") if len(tool_result_str) > 200 else tool_result_str

# Determine policy: small results → include_full, large → include_reference
max_context_chars = 2000  # configurable later
use_reference = len(tool_result_str) > max_context_chars

conv_manager.add_message(
    conversation,
    role="tool",
    content=tool_result_str,
    provider=resolved_provider,
    model=resolved_model,
    agent=agent_name,
    run_name=run_doc.name,
    kind="Tool Result",
    tool_call_id=tool_call.name,
    record_kind="tool_result",
    context_policy="include_reference" if use_reference else "include_full",
    context_summary=tool_result_summary,
    reference_doctype="Agent Tool Call",
    reference_name=tool_call.name
)
```

**Update `add_message` signature** (L77) to accept the new fields:

```python
def add_message(
    self, 
    conversation, 
    role, 
    content, 
    provider, 
    model, 
    agent, 
    run_name=None, 
    kind="Message", 
    tool_call_id=None,
    record_kind=None,
    context_policy=None,
    context_summary=None,
    reference_doctype=None,
    reference_name=None,
    visibility=None,
    token_estimate=None
):
    """Add message to conversation with optional context policy."""
    # ... existing index logic ...
    message = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation.name,
        "role": role,
        "content": content if isinstance(content, str) else json.dumps(content),
        "user": self.external_id or frappe.session.user if role == "user" else "Agent",
        "session_id": self.session_id,
        "kind": kind,
        "agent_run": run_name,
        "agent": agent,
        "provider": provider,
        "model": model,
        "conversation_index": last_index + 1,
        "is_agent_message": 1 if role == "agent" else 0,
        "tool_call": tool_call_id,
        # New fields
        "record_kind": record_kind,
        "context_policy": context_policy,
        "context_summary": context_summary,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "visibility": visibility,
        "token_estimate": token_estimate
    })
    message.insert(ignore_permissions=True)
    # ... rest of method ...
```

**Stream path** (around L1343): similar update — create a context-aware tool result message.

### 4. Tests

File: `huf/ai/tests/test_context_policy.py` (new)

```python
import frappe
from huf.ai.conversation_manager import ConversationManager

def test_include_full_policy():
    """Existing behavior: full content included."""
    # Create conversation + normal message
    conv = frappe.get_doc({...}).insert()
    cm = ConversationManager(...)
    cm.add_message(conv, "user", "Hello", "p", "m", "a", context_policy="include_full")
    
    history = cm.get_conversation_history(conv.name)
    assert len(history) == 1
    assert history[0]["content"] == "Hello"

def test_include_reference_policy():
    """Reference policy: compact handle only."""
    # Create large tool result
    large_result = "X" * 5000
    cm.add_message(
        conv, "tool", large_result, "p", "m", "a",
        kind="Tool Result",
        record_kind="tool_result",
        context_policy="include_reference",
        context_summary="5000-byte result",
        reference_doctype="Agent Tool Call",
        reference_name="ATC-001"
    )
    
    history = cm.get_conversation_history(conv.name)
    msg = history[1]
    assert "[tool_result:" in msg["content"]
    assert "ATC-001" in msg["content"]
    assert "XXXXX" not in msg["content"]  # Raw content excluded

def test_exclude_policy():
    """Exclude policy: message omitted entirely."""
    cm.add_message(conv, "system", "debug", "p", "m", "a", context_policy="exclude")
    history = cm.get_conversation_history(conv.name)
    assert len(history) == 0

def test_backward_compat_null_policy():
    """NULL policy (legacy): treated as include_full."""
    # Create message without context_policy (simulates pre-Phase-1 row)
    msg_doc = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conv.name,
        "role": "user",
        "content": "legacy message",
        "context_policy": None  # explicitly None
    }).insert()
    
    history = cm.get_conversation_history(conv.name)
    assert any(h["content"] == "legacy message" for h in history)

def test_token_growth_bounded():
    """Repeated large tool results don't grow input tokens."""
    # Add 3 turns with 5000-byte tool results, all with include_reference
    for i in range(3):
        cm.add_message(conv, "user", f"Question {i}", "p", "m", "a")
        cm.add_message(
            conv, "tool", "X" * 5000, "p", "m", "a",
            record_kind="tool_result",
            context_policy="include_reference",
            context_summary="large result",
            reference_doctype="Agent Tool Call",
            reference_name=f"ATC-{i}"
        )
    
    history = cm.get_conversation_history(conv.name)
    # Rough token estimate: 3 user messages (~20 tokens each) + 3 reference lines (~15 tokens each) = ~105 tokens
    # If we replayed full 5000-byte results, ~4000 tokens per result = 12000+ tokens
    total_content = "".join(h["content"] for h in history)
    assert len(total_content) < 2000  # Compact; full would be ~15000+
```

### 5. Acceptance Criteria Verification

After Phase 1 implementation:
- ✅ Tool result raw output persisted only in `Agent Tool Call.tool_result`; `Agent Message.content` stores summary/reference
- ✅ `get_conversation_history()` filters by `context_policy`; result never includes large payloads
- ✅ Repeated tool-output turns don't grow input tokens (token growth stays O(1) per result, not O(result_size))
- ✅ `context_policy=NULL` rows (legacy) continue to work as `include_full`
- ✅ All downstream readers (title gen, summarization, provider execution) automatically get filtered history

---

## Phase 2: API & UI (comes after Phase 1)

- Expose `add_message(..., record_kind, context_policy, context_summary, reference_doctype, reference_name)` as whitelisted method for app developers.
- Helper tools: `get_result_context(handle)`, `get_visible_records(handle)`.
- Chat UI: render out-of-band rows as collapsed context markers, not full content.

## Phase 3: Agent Context Artifact DocType

- New DocType for large payloads not tied to a single message.
- `Agent Message` references artifacts instead of inlining.

## Phase 4: Central Context Assembler

- One function owns all model-input construction (sync, stream, triggers, flows, orchestration).
- Makes `token_budgeted` real; enables token budget-aware filtering.

## Phase 5: Provider-aware Optimization

- Anthropic: cache stable prefixes; don't cache per-user payloads.
- Gemini: similar.
- OpenAI: use Responses/Conversations where useful.

---

## Risk & Rollout

- **Low risk:** Phase 1 is purely additive; `NULL` policy = legacy behavior.
- **Safest rollout:** deploy Phase 1, run it with default `include_reference` on tool results in shadow mode (i.e., still append to content for safety, but also set the policy fields). Once confident, switch off text-append.
- **Revert plan:** if issues, set `context_policy = "include_full"` on all new rows; `get_conversation_history` reverts to unfiltered.

---

## Files to modify

| File | Changes | Est. LOC |
|------|---------|---------|
| `huf/huf/doctype/agent_message/agent_message.json` | Add 7 fields | +60 |
| `huf/ai/conversation_manager.py` | Replace `get_conversation_history` + add `_message_to_context` | +60, -20 |
| `huf/ai/conversation_manager.py` | Update `add_message` signature + field mappings | +20 |
| `huf/ai/agent_integration.py` | Tool result persist (L864-878, L1343) | +15, -5 |
| `huf/ai/tests/test_context_policy.py` | New test file | +150 |

**Total:** ~280 LOC added, ~25 LOC modified, ~100 LOC tests.

---

## Implementation order

1. **Agent Message fields** — add to JSON, regenerate DocType (5 min)
2. **ConversationManager refactor** — implement `_message_to_context` + update `get_conversation_history` (30 min)
3. **add_message signature** — extend params + field mapping (10 min)
4. **Tool result persistence** — sync path + stream path (20 min)
5. **Tests** — verify all 6 acceptance criteria (60 min)
6. **Manual QA** — run a conversation with tool results, inspect history in Desk, verify tokens don't bloat

Total: ~2 hours implementation + 30 min QA = **2.5 hours Phase 1**.

---

## 1. What modern agent tools actually do (and what we borrow)

The spec already surveys OpenAI Responses, Anthropic caching, Gemini caching, and LangGraph. Distilled into the patterns that matter for implementation:

| Pattern | Seen in | What HUF should take |
|---|---|---|
| **Message ≠ context** — stored transcript is an audit log; what the model sees is assembled on demand | LangGraph, ChatGPT, Claude Code | A *context assembler* separate from `Agent Message` persistence. |
| **Tool results are ephemeral by default** — full output is needed *this turn*, a summary/handle is kept after | Claude Code, Cursor, Aider | `context_policy` defaulting to `include_reference`/`include_summary` for tool results. |
| **Reference + fetch-on-demand** — keep a handle, let the model re-fetch if needed | ChatGPT Apps, MCP, Cursor file reads | `include_reference` + `get_*_context(handle)` tools. |
| **Model-visible vs UI-only split** — payload hydrates the UI without entering the prompt | MCP tool results, ChatGPT Apps | `visibility` field (`model_visible` / `ui_only` / `audit_only`). |
| **Token budgeting / recency window** — newest N turns full, older compressed/summarized | Claude Code compaction, Cursor | `token_budgeted` policy + budget-aware assembler (Phase 4). |
| **Stable prefix caching** — cache system/instructions/tools, never volatile per-user data | Anthropic, Gemini | `provider_cached` boundary handled in assembler (Phase 5), not as a correctness mechanism. |

Guiding principle (unchanged from spec): **persist everything for audit; inject only what helps the next decision.**

---

## 2. Current HUF reality (the starting point)

Key facts from the code on this branch:

- **`huf/ai/conversation_manager.py`**
  - `add_message(conversation_id, role, content, tool_calls, tool_call_id, name, agent_run, metadata)` — writes one `Agent Message` row.
  - `get_history(conversation_id, limit)` — **the bloat source.** Returns every row's *full* `content` as `{role, content, tool_calls?, tool_call_id?, name?}`. No filtering, no policy, no summarization.
  - `get_recent_messages()` — thin wrapper over the same query.
  - (Note: the module currently has a large block of duplicated `def` convenience functions — a pre-existing cleanup item worth fixing while we're here.)
- **`Agent Message` doctype** fields today: `conversation, role, content, tool_calls, tool_call_id, name_field, agent_run, timestamp, metadata`. No context fields yet.
- **`agent_integration.py`** (`run_agent_sync` / `run_agent_stream`) assembles the model message list from `get_history` + the new prompt, then persists the user turn and assistant turn back via `add_message`. This is the single choke point Phase 1 must route through.
- Tool execution happens inside the provider-native loop (`run.py` / `providers/litellm.py`); raw tool output flows back to the model **within** the run. We must not break that loop — only what gets *persisted and replayed*.

**Implication:** the smallest correct fix is (a) add policy fields to `Agent Message`, (b) make `get_history` policy-aware via a single assembler function, (c) write tool results with a conservative default policy. Everything else is layering.

---

## 3. Design: the data model

### 3.1 Fields to add to `Agent Message` (Phase 1)

Nullable, additive, backward-compatible:

```
record_kind        Select  (message|tool_call|tool_result|retrieval_context|
                            result_snapshot|artifact|summary|status|error|debug_trace)
                            default "message"
context_policy     Select  (include_full|include_summary|include_reference|
                            include_on_demand|exclude|transient_only|
                            token_budgeted|provider_cached)
                            default "include_full"
context_summary    Small Text
reference_doctype  Data
reference_name     Data
visibility         Select  (user_visible|model_visible|ui_only|audit_only|developer_only)
                            default "user_visible"
token_estimate     Int
```

Phase 1 only *requires* `context_policy`, `context_summary`, `reference_doctype`, `reference_name`. The others are cheap to add now to avoid a second migration and unlock Phase 2 UI.

**Migration safety:** existing rows have `context_policy = NULL` → assembler treats `NULL` as `include_full`. No backfill needed; legacy behavior preserved exactly.

### 3.2 Policy semantics (assembler contract)

| Policy | What enters model context |
|---|---|
| `include_full` | full `content` (today's behavior) |
| `include_summary` | `context_summary` only |
| `include_reference` | one compact line: `[<record_kind>: <summary> · handle=<reference_doctype>/<reference_name>]` |
| `include_on_demand` | nothing injected; fetchable via tool by handle |
| `exclude` | never |
| `transient_only` | current run only; never persisted into future history |
| `token_budgeted` | included if assembler has budget (Phase 4); pre-Phase-4 treat as `include_summary` |
| `provider_cached` | included, flagged for cache boundary (Phase 5); pre-Phase-5 treat as `include_full` |

---

## 4. Staged plan

### Phase 1 — Safe history filtering (the core; ship first)

**Goal:** large tool/result payloads stop being replayed as history, without touching the in-run provider tool loop.

1. **Doctype** — add the fields in §3.1 to `agent_message.json` (+ regenerate). Defaults as specified.
2. **Assembler helper** in `conversation_manager.py`:
   - `message_to_context(msg) -> dict | None` — applies the §3.2 table; returns `None` for omitted rows.
   - `get_history()` maps each row through `message_to_context`, dropping `None`. Select the new fields in the query. `NULL` policy ⇒ `include_full`.
3. **`add_message` signature** — accept `record_kind`, `context_policy`, `context_summary`, `reference_doctype`, `reference_name`, `visibility`, `token_estimate` (all optional, defaulting to today's behavior).
4. **Tool result persistence** — where `agent_integration.py` saves tool turns:
   - Raw output → `Agent Tool Call` (already the audit home) / or `metadata`.
   - `Agent Message` gets `record_kind="tool_result"`, `context_policy="include_reference"` (or `include_summary` if small), a generated `context_summary`, and `reference_doctype/name` pointing at the tool-call record.
   - Add a size threshold (`max_context_chars`, default e.g. 2000): under it ⇒ `include_full`; over ⇒ `include_reference`.
5. **Cleanup** the duplicated convenience-function block in `conversation_manager.py`.
6. **Tests** (`huf/ai/tests/test_context_policy.py`):
   - large tool output → not present in next `get_history`; only handle line appears.
   - `exclude` / `transient_only` never appear.
   - `NULL`/legacy rows → full content (no regression).
   - repeated result-snapshot turns → input token estimate stays bounded.
   - `include_summary` yields summary, not content.

**Acceptance (from spec):** persisted `content` need not hold large payloads; reference-only rows excluded from replay; repeated turns don't grow tokens beyond expectation; large tool JSON absent from future history unless configured.

### Phase 2 — First-class out-of-band / reference messages

- Public API: `add_message(..., record_kind="result_snapshot", context_policy="include_reference", context_summary=..., reference_doctype=..., reference_name=...)` exposed as a whitelisted method for app developers.
- Helper tools the model can call: `get_result_context(handle)`, `get_visible_records(handle)`, `get_record_details(doctype, name)` (registered via `huf_tools`).
- **Frontend** (`components/chat/`): render out-of-band rows as collapsed "context markers" / expandable tool cards (summary first, raw payload behind permission-aware inspection). Never dump raw payload into the normal chat bubble.

### Phase 3 — `Agent Context Artifact` doctype

- New doctype: `conversation, agent_run, artifact_type, summary, payload_json, payload_file, reference_doctype, reference_name, visibility, context_policy, token_estimate, expires_on, created_by`.
- `Agent Message` references artifacts instead of inlining large payloads. Expiry → audit-visible but not model-fetchable.

### Phase 4 — Central Context Assembler

- One module owns model-input construction for **all** paths: sync, stream, triggers, sub-agents, orchestration, flow nodes. Owns system prompt + recent history + summaries + conversation data + knowledge snippets + tool outputs + artifact refs + **token budgeting**.
- This is where `token_budgeted` becomes real and where the 10 coverage points in the spec (§"Coverage required") are guaranteed in one place instead of scattered.

### Phase 5 — Provider-aware optimization

- Cache stable prefixes (Anthropic/Gemini); use OpenAI Responses/Conversations where useful; MCP model-visible + UI-only metadata. Correctness first (Phases 1–4), cost second.

### Phase 6 — Memory/learning alignment

- Keep the five lanes strictly separate: conversation history / artifact / state / memory / analytics. Out-of-band context must **not** auto-promote to long-term memory; memory capture stays explicit and policy-driven (ties into the Memory System tracked on the sibling branch).

---

## 5. Tool- and agent-level config (lands with Phase 1–2)

- **`Agent Tool Function`** defaults: `default_context_policy`, `max_context_chars`, `max_context_tokens`, `summarize_result`, `store_raw_result`, `raw_result_visibility`, `safe_to_include_full`.
- **`Agent`** fallbacks: `default_tool_result_context_policy` (safe default `include_reference`), `allow_full_tool_result_replay` (default `false`), `auto_summarize_large_tool_results` (default `true`), `max_tool_result_context_tokens`.

Resolution order: message-level override → tool-level default → agent-level fallback → global safe default.

---

## 6. Sequencing & risk

```
Phase 1 (fields + assembler + tool-result policy + tests)   <- ship, low risk, reversible
   └─> Phase 2 (API + helper tools + chat UI)
          └─> Phase 3 (Artifact doctype)
                 └─> Phase 4 (central assembler) ── unifies all paths
                        ├─> Phase 5 (provider caching/optimization)
                        └─> Phase 6 (memory separation)
```

- **Lowest-risk, highest-value:** Phase 1. It is additive (nullable fields), preserves legacy behavior on `NULL`, and routes through one function (`get_history`) plus one writer (tool-result persistence).
- **Biggest latent risk:** partial coverage. Until Phase 4's central assembler, every *new* path that reads `Agent Message` (summarization, title-gen, silent triggers, streaming, orchestration, flow nodes) must remember to go through the assembler helper. Track these explicitly.

## 7. Open questions to resolve before coding Phase 1

(from spec §"Open questions" — the ones that gate Phase 1)

1. `record_kind` as new field vs reuse of existing `metadata` — **recommend new field** for queryability.
2. Safe default for *existing* tools: keep `include_full` legacy until migrated, or flip to `include_reference`? — **recommend:** legacy rows stay full; *new* tool-result writes default to `include_reference` above the size threshold.
3. `context_policy` on `Agent Message` only, or also `Agent Tool Call`/artifact? — **recommend** message-level for Phase 1; widen in Phase 3.
4. Auto-generated vs developer-supplied summaries — **recommend** developer-supplied if present, else cheap truncation/heuristic in Phase 1, LLM summary in Phase 4.
