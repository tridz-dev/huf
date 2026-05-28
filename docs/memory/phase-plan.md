# HUF Memory Architecture: Implementation Phase Plan

> **Status:** Active — Phase 1 in progress (PR #275)
> **Last updated:** 2026-05-29
> **Related:** [zero-to-hero.md](./zero-to-hero.md) | [RFC](../SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md)

---

## Overview

```
Phase 0  → Architecture alignment (done)
Phase 1  → Canonical Memory Record + tools (PR #275, in progress)
Phase 2  → Policy enforcement: inject + auto-promote
Phase 3  → Learning: post-run extraction
Phase 4  → Learning profiles + learning agent formalization
Phase 5  → Retrieval upgrades: hybrid search, metadata filters
```

---

## Phase 0 — Architecture Alignment ✅ Done

**Branch:** `docs/scoped-memory-knowledge-bridge` | **PR:** #274

RFC defining the three-layer model, terminology, phase roadmap.

---

## Phase 1 — Canonical Memory Record + Tools 🔄 In Progress

**Branch:** `feature/scoped-memory-core` | **PR:** #275

### What is included

**DocTypes:**
- `Memory Record` — full schema: scopes, visibility, lifecycle, projection fields, quality signals
- `Memory Policy` — config shell for future enforcement. Schema complete, no runtime enforcement yet.

**Backend tools (whitelisted, agent-callable):**
- `save_memory_record` — scoped write with permission enforcement
- `get_memory_record` — scoped read with permission enforcement
- `search_memory_records` — multi-scope search, query filtering, limit cap
- `archive_memory_record` — sets status to Archived, checks both read + write permission
- `promote_memory_to_knowledge` — manager-only, queues projection to Knowledge Input

**Knowledge projection pipeline:**
- Memory Record → formatted text → Knowledge Input (input_type=Text) → Knowledge Source queue
- Projection status: `Not Indexed → Queued → Projected → Error / Removed`
- `Projected` means Memory Record has been handed to Knowledge Input pipeline
- Actual indexing status owned by Knowledge Input (Pending → Processing → Indexed → Error)
- Re-projection updates existing Knowledge Input rather than creating duplicates

**Permission model:**
- Desk access to Memory Record: System Manager and Huf Manager only
- User/agent access: through tool-level scope/visibility filtering only
- Normal users: can write Conversation and their own User memory
- Managers: can write any scope, promote to knowledge

**Native tool wiring:**
- 5 new types in `agent_tool_function.json`: Save Memory Record, Search Memory Records, Get Memory Record, Archive Memory Record, Promote Memory to Knowledge
- Each type maps to the corresponding handler in `huf/ai/memory_tools.py` via `sdk_tools.py`

### What is explicitly NOT included

- Memory Policy runtime enforcement (config shell only)
- Automatic memory capture from runs
- Frontend memory tab or UI (Desk only, manager-visible)
- New vector DB logic
- Hindsight-style retain/recall/reflect

### Definition of done

- [ ] `python -m py_compile` passes on all three new Python files
- [ ] `bench migrate` applies cleanly
- [ ] Memory Record can be created, activated, promoted to Knowledge
- [ ] Projection status shows `Projected` after queuing
- [ ] Normal user cannot create Role/Site/Global memory via tools
- [ ] Manager can promote memory to an existing Knowledge Source
- [ ] Agent Tool Function can use Save Memory Record and Search Memory Records types

---

## Phase 2 — Policy Enforcement: Inject + Auto-promote

**Depends on:** Phase 1 merged

### Goal

Make Memory Policy do something at runtime. Focus on the two highest-value paths: injecting memory into agent context before a run, and auto-promoting records that meet quality thresholds.

### What is included

**Agent-level policy linking:**
- Add `memory_policy` Link field to Agent DocType
- Add `default_memory_policy` Link field to Agent Settings (singleton) for site-wide fallback
- Policy resolver: `resolve_memory_policy(agent_name)` → Agent Policy → Site Default → None

**New module: `huf/ai/memory_policy_resolver.py`**
- `resolve_memory_policy(agent_name)` — returns effective MemoryPolicy doc or None
- `get_injectable_memory(agent_name, conversation_id, policy)` — returns Memory Records within token budget
- `build_memory_context_block(records, policy)` — formats records for system prompt injection

**Hook into `agent_integration.py`:**
- Before run: if `inject_mode != "None"` → prepend memory context block to system prompt
- After run: if `auto_promote_to_knowledge` → check records meeting thresholds → queue projection

**Injection modes:**
- `None` — no injection (default, backward-compatible)
- `Append to System Prompt` — memory records added as structured block
- `Tool Available` — no injection, but `search_memory_records` tool is available

**Token budget enforcement:**
- Records sorted by `importance_score desc, modified desc`
- Trimmed to fit within `token_budget` (estimated 4 chars/token)

---

## Phase 3 — Learning: Post-run Extraction

**Depends on:** Phase 2 merged

### Goal

Let Memory Policy control when and how the system extracts Memory Records from completed runs. Optionally delegate extraction to a dedicated learning agent.

### Memory Policy — new Learning section fields

- `learning_enabled` (Check)
- `learning_trigger` (Select: Manual | End of Conversation | Every N Turns)
- `turns_per_extraction` (Int)
- `learning_agent` (Link → Agent)
- `extracted_record_default_status` (Select: Draft | Active)
- `extraction_model` (Data — optional model override for built-in extraction)

### New module: `huf/ai/memory_extractor.py`

- `extract_memories_from_run(agent_run_id, memory_policy_name)`
- Assembles transcript from Agent Messages
- If `learning_agent` set: routes to that agent via `run_agent_sync()`, parses output
- If not: calls built-in extraction prompt against base model
- Saves extracted records with source_type = "Agent Run"

**Trigger hooks:**
- End of Conversation: hook on Agent Conversation `on_update` when status → Closed/Complete
- Every N Turns: hook on Agent Message `after_insert`, fire when threshold reached
- Manual: whitelist endpoint `trigger_memory_extraction(agent_run_id)`

**Draft-first safety:**
- If `approval_required = True`, always Draft regardless of `extracted_record_default_status`

---

## Phase 4 — Learning Profiles + Learning Agent Formalization

**Depends on:** Phase 3 merged

### Built-in presets (seeded at install)

| Profile | capture_mode | inject_mode | approval_required | learning_trigger |
|---------|-------------|-------------|-------------------|-----------------|
| Minimal | Manual | None | Yes | Manual |
| Conversational | Auto | Append to System | No | End of Conversation |
| Research | Both | Tool Available | Yes | End of Conversation |
| Operational | Auto | Append to System | No | Every N Turns (5) |

**Agent DocType gains `agent_role`** (Select: General | Learning | Orchestrator | ...)

Memory Policy `learning_agent` field filtered to agents with `agent_role = Learning`.

**Agent Settings gains `default_learning_profile`** for site-wide default.

---

## Phase 5 — Retrieval Upgrades: Hybrid Search + Metadata Filters

**Depends on:** Phase 2 merged (independent of Phases 3–4)

### What is included

**Hybrid search (per Knowledge Source):**
- New `search_mode` field: FTS | Vector | Hybrid
- Hybrid runs both FTS + vector, combines scores (reciprocal rank fusion)
- Requires embedding to be configured

**Metadata filters in retrieval:**
- Knowledge Input gains `metadata_json` field
- During memory projection: tags + scope_type + record_type written to metadata
- `knowledge_search()` accepts `metadata_filters` dict

**Memory-specific search helper:**
- `search_memory_knowledge(query, agent_name, filters)` — searches Knowledge Sources containing projected memory, attributes results back to source Memory Record

**New backend abstractions:**
- `supports_metadata_filters()` method on `KnowledgeBackend`
- `supports_hybrid_search()` method on `KnowledgeBackend`
- Future backends (pg_vector, Qdrant) can implement both

**Chunk cleanup on Knowledge Input deletion:**
- `KnowledgeInput.on_trash()` calls `backend.delete_chunks(input_id)`
- Ensures removing a projected Memory Record removes indexed content

---

## Cross-cutting concerns

### Security (all phases)

- Memory Record Desk access: Managers only
- Tool-level access: scoped per user/role/agent context
- Wider scopes (Role, Site, Global): Managers only
- Knowledge promotion: Managers only
- Extracted draft records: Manager review before activation
- User-scoped memory: never leaks to role/site/global search

### Backward compatibility

- Phase 1: new DocTypes only — no changes to existing DocTypes
- Phase 2: optional fields added to Agent and Agent Settings
- Phase 3: optional fields added to Memory Policy
- Phase 5: optional fields added to Knowledge Source and Knowledge Input
- No existing Knowledge Source or Agent Tool Function behavior changes without opt-in

### Open questions

1. Should memory injection be visible to users in chat UI? (transparency / trust)
2. Should users be able to view and delete their own User-scoped memory?
3. How should contradictory memory records be handled in Phase 3+?
4. Should Data Tables be eligible as memory sources in a future phase?
5. What telemetry should capture memory injection quality and extraction cost?
