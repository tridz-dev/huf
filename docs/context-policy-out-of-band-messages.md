# Context Policy and Out-of-Band Messages

Status: WIP draft spec  
Target area: Agent runtime, conversation history, Agent Message, Agent Artifact  
Primary goal: prevent large runtime payloads from being persisted or replayed as normal conversation context.

## Problem

HUF currently persists conversation messages in `Agent Message` and later rebuilds agent context from message history. This works for normal chat, but it becomes expensive and risky when applications send large retrieval/runtime payloads as part of a prompt.

Example problem:

- An app builds a prompt containing a large result set, ranking data, visible records, candidate JSON, inventory names, report rows, or UI state.
- HUF saves the assembled prompt or large message content as an `Agent Message`.
- Later turns replay that content as conversation history.
- Even if the active prompt remains stable, billed input tokens grow turn by turn.

This is not limited to one domain. Similar cases exist for hotel search results, product catalogs, invoice lists, ERP report rows, retrieved documents, scraped pages, browser state, large tool results, uploaded files, debug traces, generated UI state, and recommendation candidates.

## Design principle

Persist everything needed for audit and replay, but only inject what is intentionally useful for the next model decision.

Agent Message should be treated as an audit/event record. A separate context policy should decide whether and how a record enters the model context.

## Related patterns from agent systems

### OpenAI Responses / Conversations

OpenAI separates conversation items from direct request messages in newer APIs. However, chained conversation state is not a complete solution to context bloat because previous chained input tokens may still be billed and relevant context still needs deliberate management.

### ChatGPT Apps / MCP-style tool results

A useful pattern is the split between model-visible content and UI-only metadata. Tool results may contain content visible to the model and private metadata delivered only to the UI. HUF should adopt a similar boundary: large UI hydration or app payloads should be storable/auditable without automatically becoming LLM input.

### Anthropic prompt caching

Prompt caching reduces repeated cost for stable prefixes. It does not mean the data is excluded from context. Dynamic per-user retrieval payloads should not be solved primarily through prompt caching.

### Gemini context caching

Gemini explicit caching can store reusable prompt prefixes behind a cache handle. It is useful for stable content, but cached content is still part of the model input context and token limits. It should not be used as the main mechanism for volatile per-user result snapshots.

### LangGraph / agent state stores

LangGraph-style systems distinguish conversation messages, short-term state, long-term memory, artifacts, and stores. HUF should move in the same direction: not every state or artifact belongs inside message history.

## Proposed HUF model

Introduce a context policy layer on top of `Agent Message`, and later add `Agent Context Artifact` for large payloads.

### Core concepts

1. Conversation history: what user and assistant said.
2. Runtime artifact: what was retrieved, shown, generated, or used.
3. Current state: small working variables for the active conversation.
4. Memory: durable learned facts or preferences.
5. Analytics/debug: traces, costs, timings, and raw payloads.

These should not be stored or replayed as the same thing.

## Generic visible/result context pattern

Many apps need the model to understand what the user has just seen, without replaying the full payload forever.

Examples:

- Travel: visible hotels, flights, attractions, rooms, packages.
- Commerce: visible products, search results, cart candidates, recommendations.
- Finance/ERP: invoices, quotations, payment entries, ledger rows, receivables reports.
- CRM/support: lead lists, ticket search results, customer timelines.
- HR: employee lists, leave requests, payroll anomalies, appraisal summaries.
- Knowledge/RAG: retrieved chunks, document candidates, citation candidates.
- Browser/automation: page snapshots, scraped tables, UI state.

The full source records should usually remain in their own app DocTypes or external systems. HUF should store only the reference, compact summary, and context policy needed to reconstruct or fetch the data when required.

Recommended split:

```text
Source records
= full durable records in app DocTypes or external systems

Visible/Result Context
= user-specific snapshot of what was shown, selected, ranked, filtered, or used

Agent Message
= user intent, assistant response, compact reference, and audit metadata

Model Context
= only the intentionally selected full content, summary, or reference line
```

## Suggested fields on Agent Message

Minimum fields for Phase 1:

```text
context_policy
context_summary
reference_doctype
reference_name
token_estimate
```

Recommended longer-term fields:

```text
record_kind
visibility
context_policy
context_summary
reference_doctype
reference_name
payload_json
payload_file
expires_on
sensitivity
token_estimate
context_priority
```

## Suggested enum values

### record_kind

```text
message
tool_call
tool_result
retrieval_context
ui_snapshot
result_snapshot
artifact
memory
summary
status
error
debug_trace
```

### role

Existing roles can stay, but HUF may later normalize around:

```text
user
assistant
system
tool
app
developer
```

### visibility

```text
user_visible
model_visible
ui_only
audit_only
developer_only
```

### context_policy

```text
include_full
include_summary
include_reference
include_on_demand
exclude
transient_only
token_budgeted
provider_cached
```

Meaning:

- `include_full`: include full content in model history.
- `include_summary`: include only `context_summary`.
- `include_reference`: include a compact reference line with handle/doctype/name.
- `include_on_demand`: do not inject by default; agent/tool may fetch by handle.
- `exclude`: never include in model context.
- `transient_only`: used for current model call only; do not persist into future history.
- `token_budgeted`: include only if context assembler has enough token budget.
- `provider_cached`: eligible for provider-specific cache handling, not a guarantee of exclusion.

## Generic result snapshot example

Assume an app shows a user a filtered/ranked result list. The full records already live elsewhere and should not be duplicated in HUF.

The app may create a domain-specific context DocType such as:

```text
Hotel Search View Context
Product Search View Context
Invoice Result Context
Quotation Comparison Context
Support Ticket Result Context
Document Retrieval Context
```

A generic result context shape may include:

```text
conversation
session_id
search_id / request_id
source_doctype / source_system
query_or_filters
visible_record_ids
ranking_order
selected_record_ids
summary_rows
snapshot_version
created_at
expires_on
```

HUF then stores an Agent Message or Agent Artifact reference:

```text
record_kind = result_snapshot
visibility = audit_only
context_policy = include_reference
context_summary = "40 records shown to user for Dubai hotel search, context=HVC-00045"
reference_doctype = "Hotel Search View Context"
reference_name = "HVC-00045"
```

Or for another domain:

```text
record_kind = result_snapshot
visibility = audit_only
context_policy = include_reference
context_summary = "25 overdue invoices shown to user for customer ABC, context=IRC-00018"
reference_doctype = "Invoice Result Context"
reference_name = "IRC-00018"
```

Model replay should include only a compact reference line, for example:

```text
[Context available: 40 visible records from previous result set, handle=HVC-00045]
```

If the model needs details later, it should call a tool such as:

```text
get_result_context(handle)
get_visible_records(handle)
get_selected_record(handle)
get_record_details(doctype, name)
```

## Relationship to Conversation Data Management

HUF already has conversation data management on Agent settings. This can be useful for small key-value state, but it should not be used for large result payloads if auto-injection is enabled.

Recommended use:

```text
result_context_id = HVC-00045
visible_count = 40
selected_record_id = HOTEL-0008
last_filter = family-friendly near metro
```

Other examples:

```text
result_context_id = PRC-00022
visible_count = 18
selected_record_id = ITEM-0042
last_filter = under AED 500, in stock
```

```text
result_context_id = IRC-00018
visible_count = 25
selected_record_id = INV-2026-00091
last_filter = overdue, customer ABC
```

Avoid storing full candidate JSON, full visible records, report rows, or large result arrays in conversation data.

For large context payloads, use app DocTypes or Agent Context Artifacts and store only references in conversation data.

## Phased implementation plan

### Phase 1: Safe history filtering

Objective: stop large payload replay without changing all runtime architecture.

Backend changes:

1. Add fields to `Agent Message`:
   - `context_policy`
   - `context_summary`
   - `reference_doctype`
   - `reference_name`
   - optionally `token_estimate`
2. Default existing normal messages to `include_full`.
3. Update conversation history assembly so it does not blindly return every `content` value.
4. Add helper to convert message records into model context:
   - full content for `include_full`
   - summary only for `include_summary`
   - compact handle line for `include_reference`
   - nothing for `exclude`, `transient_only`, and `include_on_demand`
5. Add tests for repeated result-context conversations where token growth stays bounded.

Acceptance criteria:

- Persisted `Agent Message.content` no longer needs to contain large retrieval/result sections.
- History replay does not include records marked out-of-band/reference-only.
- Repeated turns do not grow input tokens by more than expected unless new large context is intentionally attached.

### Phase 2: First-class out-of-band/reference message support

Objective: make the pattern explicit and easy for app developers.

Add API support for creating out-of-band/reference messages:

```text
add_message(..., record_kind="result_snapshot", context_policy="include_reference", context_summary=..., reference_doctype=..., reference_name=...)
```

Also support other record kinds:

```text
retrieval_context
ui_snapshot
tool_result
artifact
debug_trace
```

UI behavior:

- Show collapsed context markers in chat/admin view.
- Do not show raw payload in normal chat by default.
- Allow managers/developers to inspect referenced artifacts/documents where permissions allow.

### Phase 3: Agent Context Artifact DocType

Objective: move large non-message payloads out of Agent Message.

Create `Agent Context Artifact` with fields such as:

```text
conversation
agent_run
artifact_type
summary
payload_json
payload_file
reference_doctype
reference_name
visibility
context_policy
token_estimate
expires_on
created_by
```

Agent Message can then point to artifacts instead of storing payloads directly.

### Phase 4: Central Context Assembler

Objective: make model input construction consistent across sync, stream, triggers, tools, and future flows.

Introduce a context assembler that owns:

- system prompt
- recent conversation history
- summaries
- conversation data
- knowledge snippets
- tool outputs
- artifact references
- token budgeting
- provider cache boundaries

All provider calls should go through this assembler.

### Phase 5: Provider-aware optimization

Objective: optimize cost and speed after context correctness is guaranteed.

Provider-specific behavior:

- OpenAI: use Responses/Conversations where useful, but still assemble compact context intentionally.
- Anthropic: cache stable system/instruction/tool prefixes; avoid caching volatile per-user payloads as normal history.
- Gemini: use explicit cached content for stable shared context; not for per-user visible result snapshots.
- MCP/App-style tools: support model-visible content plus UI-only metadata patterns.

### Phase 6: Memory and learning integration

Objective: align with future HUF memory work.

Strictly separate:

```text
conversation history = what was said
artifact = what was shown/used/generated
state = current working variables
memory = durable learned facts
analytics = cost/speed/quality traces
```

Out-of-band context should not automatically become long-term memory. Memory capture should be explicit and policy-driven.

## Migration approach

1. Add new nullable fields first.
2. Keep old behavior as default for existing records.
3. Update history loading to respect policy only when policy is present.
4. Add app/runtime APIs to create reference-only messages.
5. Move large payloads to app DocTypes or `Agent Context Artifact` in later phases.

## Open questions

1. Should `record_kind` replace or extend existing `kind`?
2. Should `context_policy` live only on Agent Message, or also on Agent Tool Call and future Artifact records?
3. Should HUF ship a generic artifact store first, or should app-specific DocTypes remain the recommended first pattern?
4. Should reference summaries be auto-generated, developer-supplied, or both?
5. Should context policy be agent-level default, message-level override, or both?
6. How should permissions work when a message references a DocType from another app?
7. Should expired artifacts remain audit-visible but no longer fetchable by model tools?
8. Should HUF provide a generic `Result Context` DocType, or should each app define domain-specific context DocTypes?

## Initial recommendation

Implement Phase 1 and Phase 2 first.

For application use cases such as search, comparison, recommendations, report review, or document retrieval, store the user-visible result snapshot in the app's own DocType or a future Agent Context Artifact and save only a reference in HUF. Use HUF conversation data only for compact working state. Do not persist large retrieval/result payloads as normal Agent Message content.
