# RFC: Scoped Memory, Data Management, and Knowledge Bridge for HUF

**Status:** Active — Phase 1 implemented (PR #275), Phases 2–5 planned
**Type:** Architecture RFC (living document)
**Target branch:** `develop`

> **Update log:**
> - 2026-05-27: Initial RFC published (PR #274)
> - 2026-05-29: Updated to reflect PR #275 implementation, three live backends, updated phase plan, learning profile design

**Related:**
- PR #274 — This RFC (docs-only branch: `docs/scoped-memory-knowledge-bridge`)
- PR #275 — Phase 1 implementation (`feature/scoped-memory-core`)
- PR #178 — Agno-style knowledge/vector architecture RFC *(future, not yet merged)*
- PR #225 — Hindsight long-term memory evaluation *(future, not yet merged)*
- [memory/zero-to-hero.md](./memory/zero-to-hero.md) — Full onboarding guide for new contributors
- [memory/phase-plan.md](./memory/phase-plan.md) — Detailed per-phase implementation plan

---

## 1. Purpose

HUF needs a memory layer. Agents have no way to remember what they've learned across conversations. Every session is a blank slate.

The gap is not in static knowledge (we have Knowledge Sources with FTS/vector/RAG). The gap is in **learned, scoped, evolving data** — preferences, decisions, patterns, research — that starts in one conversation and needs to persist, be governed, and optionally become searchable.

This RFC defines the architecture and phased delivery plan for that layer.

---

## 2. The three-layer model

```
Conversation Data (temporary)
      ↓  manual save or policy extraction
Memory Record (canonical, scoped, governed)
      ↓  explicit or policy-driven promotion
Knowledge Source (indexed, searchable)
      └── sqlite_fts | sqlite_vec | chroma | future: pg_vector...
```

**Core principle:** Memory Record is canonical. Knowledge is an optional indexed projection. The memory layer does not know about backends — it targets a Knowledge Source, and the Knowledge Source owns the backend type. Adding new backends requires no changes to memory tools.

---

## 3. What exists today (as of 2026-05-29)

### Knowledge backends (live — not future)

Three backends exist today, all implementing a common `KnowledgeBackend` ABC:

| Backend | Type | When to use | Dependencies |
|---------|------|-------------|--------------|
| `sqlite_fts` | Keyword (BM25) | Always available | None |
| `sqlite_vec` | Vector (semantic) | Semantic similarity | pysqlite3-binary + sqlite-vec |
| `chroma` | Vector (semantic) | Separate vector store, optionally server-mode | chromadb + llama-index |

Selected per `Knowledge Source` via `knowledge_type` field. Adding new backends (pg_vector, Qdrant, Weaviate) means implementing `KnowledgeBackend` and registering it — no memory layer changes needed.

### Memory Record (PR #275)

DocType with full schema: scopes, visibility, lifecycle, projection fields, quality signals (confidence, importance_score), tags, TTL, supersession.

Scopes: Conversation / User / Role / Agent / Site / Global
Record types: Fact / Preference / Decision / Pattern / Research / Instruction

Projection pipeline:
- Memory Record → formatted text → Knowledge Input (Text) → Knowledge Source queue
- Projection status: `Not Indexed → Queued → Projected → Error / Removed`
- "Projected" = handed to Knowledge Input pipeline. Actual indexing is async in Knowledge Input.
- Re-projection on `summary_text` or `data_json` change updates existing Knowledge Input (no duplicates).

Permission model:
- Desk access: System Manager + Huf Manager only
- User/agent access: through tool-level scope enforcement only
- Role/Site/Global write: Managers only
- Knowledge promotion: Managers only

### Memory Policy (PR #275)

Config shell — full schema present, no runtime enforcement yet.

Fields cover: capture mode, approval rules, retrieval injection mode, token budget, auto-promote thresholds, allowed record types, lifecycle TTL.

Runtime enforcement begins in Phase 2.

### Memory tools (PR #275)

Five whitelisted handlers, agent-callable via native tool types in Agent Tool Function:
- `save_memory_record` — scoped write with permission enforcement
- `get_memory_record` — scoped read with permission enforcement
- `search_memory_records` — multi-scope search, query filter, limit cap (max 50)
- `archive_memory_record` — sets status to Archived
- `promote_memory_to_knowledge` — manager-only, queues projection

---

## 4. Terminology

| Term | Meaning |
|------|---------|
| Conversation Data | Temporary working state for one session |
| Memory Record | Canonical scoped learned fact/preference/decision/pattern |
| Memory Policy | Config governing capture, retrieval, injection, promotion |
| Knowledge Projection | Act of converting Memory Record → Knowledge Input → indexed |
| Knowledge Source | Indexed searchable store with a pluggable backend |
| Learning Trigger | When post-run extraction fires (end of conversation, every N turns, manual) |
| Learning Agent | An Agent configured to read transcripts and extract Memory Records |
| Learning Profile | Named Memory Policy preset (conservative, conversational, research, operational) |
| Agno-direction | Pluggable reader/store/retrieval pattern (backends exist today, hybrid search is Phase 5) |
| Hindsight-direction | Post-run extract/retain/reflect pattern (Phase 3) |

---

## 5. Scope matrix

| Scope | Writer | Reader | scope_key |
|-------|--------|--------|-----------|
| Conversation | Any authenticated user | Same conversation | conversation docname |
| User | That user only | That user only | frappe.session.user |
| Role | Managers only | Users with that role (visibility=Shared with Role) | role name |
| Agent | Managers (or policy-allowed agent) | Agent with matching name | agent docname |
| Site | Managers only | Everyone (visibility=Site) | frappe.local.site |
| Global | Managers only | Everyone (visibility=Global) | "global" |

---

## 6. Reference architecture and influences

### 6.1 Agno (phidata) framework

Agno separates agents into memory (short-term), knowledge (indexed content), and storage (long-term runs). Its knowledge system uses pluggable readers and vector stores.

**What HUF adopted:** Pluggable backend ABC (`KnowledgeBackend`), clean separation of ingestion from retrieval, agent-linked knowledge sources. The three live backends (sqlite_fts, sqlite_vec, chroma) are a direct result of this direction.

**What HUF does differently:** Frappe DocType ownership, multi-tenancy via scopes, permission governance layer.

### 6.2 Hindsight memory pattern

Post-run memory consolidation with retain/recall/reflect operations. A reflection agent reads conversation transcripts and extracts durable learnings.

**What HUF adopted:** Learning agent delegation pattern, draft-first extraction, approval workflow, turn-based and session-end triggers. These are planned for Phase 3.

**What HUF defers:** Periodic reflection/consolidation across many memories, contradiction detection, automatic supersession.

### 6.3 Mem0 / MemGPT patterns

Structured memory schemas with episodic/semantic/procedural types, importance scoring, visibility controls.

**What HUF adopted:** Record type taxonomy (Fact/Preference/Decision/Pattern/Research/Instruction), importance_score + confidence fields, visibility model (Private/Shared with Role/Site/Global).

---

## 7. Implementation phases

For full details see [memory/phase-plan.md](./memory/phase-plan.md).

| Phase | Name | Status | Branch/PR |
|-------|------|--------|-----------|
| 0 | Architecture alignment | ✅ Done | PR #274 |
| 1 | Canonical Memory Record + tools | 🔄 In progress | PR #275 |
| 2 | Policy enforcement: inject + auto-promote | 📋 Planned | — |
| 3 | Learning: post-run extraction | 📋 Planned | — |
| 4 | Learning profiles + Learning Agent formalization | 📋 Planned | — |
| 5 | Retrieval upgrades: hybrid search + metadata filters | 📋 Planned | — |

---

## 8. Data quality and safety rules

1. Raw conversation fragments should not automatically become long-term knowledge.
2. Derived records carry provenance (source_type, run, conversation).
3. Low-confidence records should remain Draft unless explicitly activated.
4. User-scoped memory must never appear in Role/Site/Global retrieval.
5. Role/Site/Global memory requires Manager-level write access.
6. Promotion to Knowledge is reversible (`remove_knowledge_projection`).
7. Indexes are rebuildable from canonical Memory Records.
8. Extracted records are Draft by default when `approval_required = True`.

---

## 9. Non-goals (permanent)

- Do not replace existing Knowledge Sources or Agent Knowledge semantics.
- Do not auto-index all conversation data.
- Do not make vector DB dependencies mandatory (`sqlite_fts` always works without extras).
- Do not bypass Frappe permissions.
- Do not expose private user memory across role/site/global boundaries.

---

## 10. Open questions

1. Should memory injection be visible to users in the chat UI? (transparency)
2. Should users be able to view and delete their own User-scoped memory?
3. How should contradictory memory records be handled in Phase 3+?
4. Should Data Tables become eligible memory sources in a future phase?
5. What telemetry captures memory injection quality and extraction cost?
6. Should a formal Memory Record approval workflow (Frappe Workflow) be added in Phase 2?
