# RFC: Scoped Memory, Data Management, and Knowledge Bridge for HUF

**Status:** Discussion / refinement proposal  
**Type:** Documentation only  
**Target branch:** `develop`  
**Related PRs:**

- PR #178 — Agno-style knowledge/vector architecture RFC
- PR #225 — Hindsight long-term memory evaluation

---

## 1. Purpose

HUF currently has several adjacent capabilities:

1. **Conversation data management** — local key-value style data derived from a conversation.
2. **Knowledge Sources** — curated document/text/URL/file knowledge used by agents through FTS/vector/RAG.
3. **Data Tables** — structured application/business data managed through HUF UI.
4. **Draft memory architecture** — a proposed `Memory Record`-style canonical memory layer.
5. **Agno-style knowledge architecture** — proposed improvements to readers, chunkers, embedders, vector stores, and hybrid search.
6. **Hindsight-style memory** — proposed long-term retain/recall/reflect memory for learning across time.

The open design question is:

> How should HUF handle data derived from conversations or agent runs when that data may need to live beyond one conversation, become scoped to a user/role/agent/site, and optionally become searchable knowledge?

This RFC proposes a bridge model that keeps these concepts separate but connected.

---

## 2. Current mental model

### 2.1 Conversation Data

Conversation Data is useful for temporary working state.

Examples:

- selected hotel options shown to a user
- current trip dates
- active form values
- extracted fields from the current conversation
- short-lived intermediate state

This should remain local-first and safe by default.

### 2.2 Knowledge Sources

Knowledge Sources are curated retrieval sources.

Examples:

- PDFs
- policy documents
- URLs
- text knowledge bases
- product manuals
- indexed reference material

Knowledge is optimized for retrieval through FTS/vector/RAG and can be linked to agents as mandatory or optional context.

### 2.3 Data Tables

Data Tables are structured app/business records.

Examples:

- hotel inventory
- product catalog
- lead records
- workflow-specific structured records
- custom app-level records

These are not automatically memory or knowledge, but agents may read/write them through tools.

### 2.4 Long-term Memory / Learning

Long-term memory is derived from repeated conversations, agent runs, research, tool outputs, or user interactions.

Examples:

- user preferences
- role-level learnings
- agent-specific observations
- site-level repeated issues
- research conclusions accumulated across chats
- decisions made in previous sessions
- stable facts learned from operational usage

This is not the same as static document knowledge. It is evolving, scoped, and often needs review, consolidation, expiry, or promotion.

---

## 3. Problem statement

The existing conversation-local data model is too narrow for many real use cases.

Some data starts inside one conversation but later needs to be reused at a broader scope:

| Origin | Possible future scope | Example |
|---|---|---|
| Conversation | Same conversation only | selected hotels for current user flow |
| Conversation | User | user prefers family-friendly hotels with breakfast |
| Many conversations | Role | sales users frequently need a specific objection-handling note |
| Agent runs | Agent | this agent has learned a reliable routing pattern |
| Research sessions | Site | accumulated market research summary |
| Admin input | Global/site | default instructions or operational facts |

If everything is kept as conversation data, it cannot scale into reusable learning.

If everything is dumped directly into Knowledge Sources, the knowledge index becomes noisy and hard to govern.

The missing layer is a canonical scoped memory/data layer that can optionally project selected records into Knowledge.

---

## 4. Core principle

> **Data / Memory Record should be canonical. Knowledge should be an optional indexed projection.**

In other words:

```text
Conversation / Agent Activity
        ↓
Scoped Memory / Data Record  ← canonical source of truth
        ↓
Policy / Review / Consolidation
        ↓
Optional Knowledge Projection ← searchable FTS/vector/RAG representation
        ↓
Knowledge Source / Retrieval Layer
```

This avoids forcing one system to do everything.

---

## 5. Proposed terminology

Recommended terminology:

| Term | Meaning |
|---|---|
| Conversation Data | Temporary local working data for one conversation |
| Memory Record / Data Record | Canonical derived data/fact/preference/decision/research note |
| Memory Policy | Rules for capture, scope, visibility, indexing, expiry, and promotion |
| Knowledge Projection | Indexed/searchable representation of selected Memory Records |
| Knowledge Source | Existing HUF RAG container/search source |
| Learning Pipeline | Optional process that consolidates raw records into higher-quality memory or knowledge |

The exact DocType names can be refined, but the product distinction should remain clear.

---

## 6. Proposed conceptual architecture

```text
                                ┌──────────────────────┐
                                │   Knowledge Source   │
                                │  FTS / Vector / RAG  │
                                └──────────▲───────────┘
                                           │
                              optional projection/indexing
                                           │
┌──────────────────────┐        ┌──────────┴───────────┐
│ Conversation Data    │───────▶│ Memory / Data Record │
│ local working state  │        │ canonical scoped data│
└──────────────────────┘        └──────────▲───────────┘
                                           │
                              capture / retain / reflect
                                           │
                                ┌──────────┴───────────┐
                                │ Conversation / Runs  │
                                │ Tool outputs / Agent │
                                └──────────────────────┘
```

Agno-style knowledge work and Hindsight-style memory work plug into this bridge differently:

```text
Hindsight-inspired layer
= retain / recall / reflect / consolidate learning

Agno-inspired layer
= index / embed / chunk / search / hybrid retrieval
```

---

## 7. Layer responsibilities

### 7.1 Conversation Data

Purpose:

- Keep temporary conversation-local state.
- Avoid overloading the global memory/knowledge system.
- Provide low-friction working memory for agents.

Default behavior:

- Scope is always conversation.
- Not indexed by default.
- Not shared across users or roles.
- Can be promoted manually or by policy.

Examples:

```json
{
  "selected_hotels": ["hotel_a", "hotel_b"],
  "trip_dates": {"from": "2026-06-10", "to": "2026-06-15"},
  "user_budget": "mid-range"
}
```

### 7.2 Memory / Data Record

Purpose:

- Store derived data from conversations, runs, tools, research, or admin input.
- Act as the canonical source of truth for long-lived scoped memory.
- Support backend/Desk management.
- Support lifecycle, review, permissions, and optional indexing.

Possible fields:

| Field | Purpose |
|---|---|
| `title` | short human-readable title |
| `summary_text` | text suitable for display/search/indexing |
| `data_json` | canonical structured payload |
| `record_type` | fact, preference, research_note, decision, extracted_data, state, summary, policy_hint |
| `scope_type` | conversation, user, role, agent, workspace, site, global |
| `scope_key` | concrete ID for the scope |
| `source_type` | conversation, run, manual, event, scheduled, imported, tool_output |
| `source_conversation` | optional link to Agent Conversation |
| `source_run` | optional link to Agent Run |
| `source_message` | optional link/reference to Agent Message |
| `status` | draft, active, archived, expired, superseded, rejected |
| `confidence` | extraction confidence |
| `importance_score` | ranking/usefulness signal |
| `visibility` | private, shared_with_agent, shared_with_role, site, global |
| `ttl_days` | optional expiry policy |
| `effective_from` / `effective_until` | temporal validity |
| `supersedes_record` | version/supersession chain |
| `promote_to_knowledge` | whether it should be indexed/projected |
| `knowledge_source` | optional target Knowledge Source |
| `index_status` | not_indexed, queued, indexed, error |
| `metadata_json` | model, policy, cost, latency, audit metadata |

### 7.3 Memory Policy

Purpose:

- Control capture, reuse, indexing, and governance.

Possible policy fields:

| Field | Purpose |
|---|---|
| `enabled` | enable/disable policy |
| `agent` | optional agent binding |
| `scope_type` / `scope_key` | where policy applies |
| `allowed_capture_sources` | conversation, run, tool output, manual, scheduled |
| `allowed_record_types` | fact, preference, research_note, etc. |
| `capture_mode` | manual, agent_suggested, automatic |
| `approval_required` | require admin/user approval before active use |
| `default_status` | draft or active |
| `read_scopes` | scopes this policy can read |
| `write_scopes` | scopes this policy can write |
| `inject_mode` | never, relevant_only, always, tool_only |
| `max_records` | retrieval limit |
| `token_budget` | prompt injection budget |
| `enable_fts_index` | keyword indexing |
| `enable_vector_index` | vector indexing |
| `auto_promote_to_knowledge` | promote selected records |
| `promotion_threshold` | confidence/importance threshold |
| `consolidation_schedule` | when to summarize/consolidate records |
| `ttl_days` | default expiry |

### 7.4 Knowledge Projection

Purpose:

- Make selected Memory/Data Records searchable through HUF Knowledge.
- Avoid direct pollution of Knowledge Sources by raw chat fragments.
- Preserve canonical source-of-truth in Memory/Data Record.

Projection should be optional and policy-driven.

Recommended projection modes:

| Mode | Meaning |
|---|---|
| Do not index | record stays as scoped memory only |
| Queue indexing | safe default; async job updates knowledge index |
| Index immediately | useful for small high-confidence records |
| Require approval | admin/user approval before indexing |
| Consolidate then index | many raw records become one clean summary first |
| Remove from index | keep canonical memory but stop retrieval projection |

---

## 8. Relationship with existing Knowledge Sources

Knowledge Sources should remain the primary RAG/retrieval container.

This RFC does not propose replacing Knowledge Sources.

Instead, selected Memory/Data Records may be represented as Knowledge Inputs or direct backend chunks depending on implementation preference.

Possible implementation options:

### Option A — Memory Record creates/updates Knowledge Input

```text
Memory Record
  → generated text representation
  → Knowledge Input
  → existing indexing pipeline
  → Knowledge Source
```

Pros:

- Reuses existing Knowledge Input lifecycle.
- Easy to inspect.
- Fits current ingestion model.

Cons:

- May create many small Knowledge Inputs.
- Requires mapping back to source Memory Record.

### Option B — Memory Record indexes directly into Knowledge backend

```text
Memory Record
  → chunk/index directly
  → Knowledge Source backend
```

Pros:

- Efficient.
- Better control over metadata and updates.

Cons:

- More custom indexing logic.
- Must carefully keep index and canonical record in sync.

### Recommendation

Start with **Option A** for simplicity and auditability.

Move to Option B only if scale/performance requires it.

---

## 9. Relationship with PR #178 — Agno-style Knowledge Architecture

PR #178 should be viewed as the indexing/retrieval half of this bridge.

Its role is not to decide what should become memory. Its role is to improve how promoted knowledge is indexed and retrieved.

Relevant responsibilities from PR #178:

- embedder abstraction
- vector backend abstraction
- optional vector database support
- better readers
- better chunkers
- hybrid search
- metadata filtering
- RRF-style ranking

How it fits this RFC:

```text
Memory/Data Record selected for knowledge
        ↓
Knowledge Projection
        ↓
Agno-style indexing pipeline
        ↓
FTS/vector/hybrid retrieval
```

Design rule:

> Agno-style architecture powers the searchable projection, not the canonical memory source.

This keeps HUF's Frappe-native memory/data governance separate from retrieval engine improvements.

---

## 10. Relationship with PR #225 — Hindsight Memory Evaluation

PR #225 should be viewed as the learning/consolidation half of this bridge.

Its role is not to replace Knowledge Sources. Its role is to help HUF learn from repeated interactions over time.

Relevant responsibilities from PR #225:

- retain
- recall
- reflect
- memory banks
- per-agent/per-user isolation
- optional sidecar integration
- pre-response recall
- post-turn retain
- optional reflection/consolidation

How it fits this RFC:

```text
Conversation / Tool Events / Agent Runs
        ↓
Hindsight-style retain/reflect pipeline
        ↓
Memory/Data Records or external memory bank
        ↓
Optional Knowledge Projection
```

Design rule:

> Hindsight-style memory is for learned memory and reflection. Knowledge Sources remain for curated RAG/static/reference retrieval.

---

## 11. Recommended combined model

```text
1. Conversation Data
   Temporary local state.

2. Memory / Data Records
   Canonical scoped facts, preferences, research notes, summaries, decisions, and extracted data.

3. Learning / Consolidation Layer
   Hindsight-inspired retain/recall/reflect or native HUF consolidation policies.

4. Knowledge Projection
   Optional transformation of selected memory records into searchable chunks.

5. Knowledge Source
   Existing HUF RAG layer backed by FTS/vector/hybrid search.

6. Agent Runtime
   Retrieves relevant conversation data, scoped memory, and knowledge according to policy.
```

---

## 12. Scope model

Recommended scope types:

| Scope | Meaning | Example |
|---|---|---|
| conversation | only the current conversation | selected hotels in current chat |
| user | one user across conversations | user prefers direct answers |
| role | all users in a role | sales team objection handling |
| agent | one agent across users | agent-specific learned routing rule |
| workspace | product/app/team namespace | travel workspace learnings |
| site | current Frappe site/tenant | company-wide support policy |
| global | cross-site/global default | generic platform behavior note |

Important:

- `scope_type` defines the boundary.
- `scope_key` identifies the specific boundary object.
- permissions must be checked at retrieval and management time.

---

## 13. Runtime retrieval strategy

At agent runtime, context should be assembled in controlled layers.

Recommended order:

```text
1. Conversation-local data
2. Relevant user-scoped memory
3. Relevant role-scoped memory
4. Relevant agent-scoped memory
5. Relevant workspace/site/global memory
6. Agent-linked Knowledge Sources
7. Optional Hindsight recall context
```

But the runtime should not inject everything blindly.

Each layer should be controlled by:

- permissions
- status
- scope
- relevance
- token budget
- recency
- importance
- conflict handling
- source attribution

Recommended injection modes:

| Mode | Meaning |
|---|---|
| never | not injected; only available through tools |
| relevant_only | retrieve and inject only relevant records |
| always | inject selected high-priority records every turn |
| tool_only | agent must explicitly call memory/knowledge tools |

Default should be `relevant_only` or `tool_only`, not `always`.

---

## 14. Capture and promotion flows

### 14.1 Manual promotion

```text
User/Admin reviews conversation data
        ↓
Clicks "Save as Memory"
        ↓
Selects scope and type
        ↓
Record becomes active/draft
        ↓
Optional: "Use as Knowledge"
```

### 14.2 Agent-suggested memory

```text
Agent identifies a stable fact/preference/decision
        ↓
Creates draft Memory Record
        ↓
User/Admin approves
        ↓
Record becomes active
        ↓
Optional indexing/projection
```

### 14.3 Automatic policy capture

```text
Conversation/run ends
        ↓
Memory Policy evaluates output
        ↓
Records created if rules match
        ↓
Low-confidence records remain draft
        ↓
High-confidence records may become active
```

### 14.4 Research accumulation

```text
Many chat/research records
        ↓
Scheduled consolidation job
        ↓
Creates summary/insight Memory Record
        ↓
Summary may be promoted to Knowledge
```

---

## 15. Backend / Desk management UX

A backend Desk/HUF UI should allow admins to manage scoped memory/data.

Recommended views:

### Memory Records list

Columns:

- title
- record type
- scope type
- scope key
- status
- confidence
- importance
- source agent
- source conversation
- knowledge projection status
- last indexed at

### Memory Record form

Actions:

- Approve
- Reject
- Archive
- Supersede
- Promote to Knowledge
- Queue Re-index
- Remove from Knowledge
- View Source Conversation
- View Indexed Chunks

### Policy UI

Actions:

- create/edit memory policy
- set scopes
- configure capture mode
- configure approval rules
- configure indexing backend
- configure token budget
- configure consolidation schedule

---

## 16. Tools for agents

Recommended tools:

| Tool | Purpose |
|---|---|
| `search_memory` | search scoped memory records |
| `get_memory_record` | fetch exact memory record |
| `save_memory_record` | create memory record, respecting policy |
| `update_memory_record` | update/supersede memory record |
| `archive_memory_record` | archive stale memory |
| `promote_memory_to_knowledge` | queue/index as knowledge if allowed |
| `search_knowledge` | existing knowledge/RAG search |

Tool permissions should be stricter than prompt injection.

Agents should not be able to write role/site/global memory unless explicitly allowed.

---

## 17. Data quality and safety rules

Memory/knowledge pollution is a major risk.

Recommended rules:

1. Raw conversation fragments should not directly become long-term knowledge by default.
2. Derived records should carry provenance.
3. Low-confidence records should remain draft.
4. User/private records must never leak into role/site/global retrieval.
5. Role/site/global memory should generally require approval or high-trust policy.
6. Old records should expire or be superseded.
7. Contradictory records should be surfaced, not silently merged.
8. Search results should include source attribution.
9. Promotion to Knowledge should be reversible.
10. Indexes should be rebuildable from canonical records.

---

## 18. Conflict handling

Conflicts can occur between:

- user memory vs role memory
- role memory vs site policy
- HUF Knowledge Source vs Hindsight recall
- old memory vs new memory
- admin-authored memory vs agent-extracted memory

Recommended precedence:

```text
1. Explicit current user instruction
2. Hard system/developer/agent instruction
3. Site/company policy knowledge
4. Admin-approved scoped memory
5. User-scoped memory
6. Role/agent learned memory
7. Draft/low-confidence memory should not be used unless explicitly requested
```

Conflicts should be represented in metadata and possibly shown in diagnostics.

---

## 19. Implementation phases

### Phase 0 — Documentation and alignment

- Use this RFC to discuss the product/architecture boundary.
- Cross-link PR #178 and PR #225.
- Agree terminology before implementation.

### Phase 1 — Canonical Memory/Data Record

- Add Memory/Data Record DocType.
- Add Memory Policy DocType.
- Add basic Desk/HUF UI list/form.
- Support manual create/edit/archive.
- Keep indexing disabled by default.

### Phase 2 — Migration from conversation data

- Keep conversation-local data as default.
- Add manual "Save as Memory" from conversation data.
- Add conservative migration path for existing data management records.
- Do not auto-promote old records.

### Phase 3 — Scoped retrieval

- Add `search_memory` and `get_memory_record` tools.
- Add runtime resolver for user/role/agent/site/workspace scopes.
- Add policy-controlled prompt injection.
- Add token budgets and relevance filtering.

### Phase 4 — Knowledge projection

- Add `promote_to_knowledge` flow.
- Start with queued indexing.
- Represent Memory Record as Knowledge Input or direct chunks.
- Add status tracking: queued/indexed/error/removed.

### Phase 5 — Learning/consolidation

- Add Hindsight-style retain/recall/reflect integration or native equivalent.
- Add scheduled consolidation of raw memory records.
- Add approval workflow for role/site/global learnings.

### Phase 6 — Agno-style retrieval upgrades

- Use PR #178 direction to improve embedding, vector DBs, readers, chunkers, metadata filters, and hybrid retrieval.
- Apply these improvements to both normal Knowledge Sources and memory-derived projections.

---

## 20. Open questions

1. Should the canonical DocType be called `Memory Record`, `HUF Memory Record`, `Data Record`, or `Scoped Memory Record`?
2. Should role-scoped memory use Frappe Role directly, HUF Role, or both?
3. Should memory-derived knowledge create Knowledge Inputs or index directly into backend chunks?
4. Should Hindsight be an external sidecar only, or should HUF implement native retain/recall/reflect semantics first?
5. Should Memory Policy live on Agent, Knowledge Source, separate DocType, or all three?
6. What approval workflow is needed before user/role/site/global memory becomes active?
7. Should Data Tables be eligible as memory sources, knowledge sources, or both?
8. How should stale/contradictory memory be detected and superseded?
9. Should users be able to view and delete their own user-scoped memory?
10. What telemetry should be captured for memory retrieval quality and cost?

---

## 21. Proposed decision

Recommended direction:

> Keep Conversation Data local and default. Add a first-class scoped Memory/Data Record layer as canonical storage. Allow selected records to become Knowledge through an explicit projection/indexing policy. Use Hindsight-inspired design for learning/consolidation and Agno-inspired design for retrieval/indexing.

This gives HUF a clean separation:

```text
Conversation Data = temporary working state
Memory/Data Record = canonical scoped learned data
Hindsight-style layer = learning and reflection
Agno-style layer = indexing and retrieval architecture
Knowledge Source = searchable RAG projection
Data Tables = structured business/app records
```

---

## 22. Non-goals for the first implementation

- Do not replace existing Knowledge Sources.
- Do not replace existing Agent Knowledge mandatory/optional semantics.
- Do not auto-index all conversation data.
- Do not make Hindsight a hard dependency.
- Do not make vector DB dependencies mandatory.
- Do not bypass Frappe permissions.
- Do not expose private user memory across role/site/global scopes.

---

## 23. Summary

The clean bridge is:

```text
Data Management / Memory = canonical, scoped, governable data
Knowledge = optional searchable projection of selected data and documents
Agno PR = better projection/index/search architecture
Hindsight PR = better learning/consolidation architecture
```

This gives HUF a future-proof path for:

- conversation-local state
- user memory
- role-level learning
- agent-level improvements
- site-level accumulated research
- controlled promotion into knowledge
- auditable and reversible indexing
- better retrieval over time
