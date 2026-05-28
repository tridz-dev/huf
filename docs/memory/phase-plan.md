# HUF Memory Architecture: Implementation Phase Plan

> **Status:** Active — Phase 1 in progress (PR #275)
> **Last updated:** 2026-05-29
> **Related:** [zero-to-hero.md](./zero-to-hero.md) | [RFC](../SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md)

---

## Overview

This document defines the phased delivery plan for HUF's memory and learning architecture. Each phase is independently mergeable and leaves the system in a stable, useful state.

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

**Deliverables:**
- RFC defining the three-layer model: Conversation Data → Memory Record → Knowledge Source
- Terminology alignment: Memory Record vs Knowledge Input vs Knowledge Source vs Learning
- Phase roadmap (superseded by this document)

**Status:** Merged to `docs/` branch. RFC lives at `docs/SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md`.

---

## Phase 1 — Canonical Memory Record + Tools 🔄 In Progress

**Branch:** `feature/scoped-memory-core` | **PR:** #275

### Goal

Ship a safe, internally consistent MVP: a governed Memory Record store with tool access for agents, and a working pipeline to promote records to Knowledge.

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
- Actual indexing status is owned by Knowledge Input (Pending → Processing → Indexed → Error)
- Re-projection on `summary_text` or `data_json` change updates existing Knowledge Input rather than creating duplicates

**Permission model:**
- Desk access to Memory Record: System Manager and Huf Manager only
- User/agent access: through tool-level scope/visibility filtering only
- Normal users: can write Conversation and their own User memory
- Managers: can write any scope, promote to knowledge

**Native tool wiring:**
- 5 new types in `agent_tool_function.json`: Save Memory Record, Search Memory Records, Get Memory Record, Archive Memory Record, Promote Memory to Knowledge
- Each type maps to the corresponding handler in `huf/ai/memory_tools.py`

### What is explicitly NOT included

- Memory Policy runtime enforcement (config shell only)
- Automatic memory capture from runs
- Frontend memory tab or UI (Desk only, manager-visible)
- New vector DB logic
- Full chunk cleanup on Knowledge Input deletion (to be addressed in Phase 5)
- Hindsight-style retain/recall/reflect

### Definition of done

- [ ] `python -m py_compile` passes on all three new Python files
- [ ] `bench migrate` applies cleanly
- [ ] Memory Record can be created, activated, promoted to Knowledge
- [ ] Projection status shows `Projected` (not `Indexed`) after queuing
- [ ] Normal user cannot create Role/Site/Global memory via tools
- [ ] Manager can promote memory to an existing Knowledge Source
- [ ] Agent Tool Function can use Save Memory Record and Search Memory Records types

---

## Phase 2 — Policy Enforcement: Inject + Auto-promote

**Depends on:** Phase 1 merged

### Goal

Make Memory Policy do something at runtime. Focus on the two highest-value enforcement paths: injecting memory into agent context before a run, and auto-promoting records that meet quality thresholds.

### What is included

**Agent-level policy linking:**
- Add `memory_policy` Link field to Agent DocType
- Add `default_memory_policy` Link field to Agent Settings (singleton) for site-wide fallback
- Policy resolver: `resolve_memory_policy(agent_name)` → Agent Policy → Site Default → None

**New module: `huf/ai/memory_policy_resolver.py`**
- `resolve_memory_policy(agent_name)` — returns the effective MemoryPolicy doc or None
- `get_injectable_memory(agent_name, conversation_id, policy)` — returns list of Memory Records within token budget
- `build_memory_context_block(records, policy)` — formats records for system prompt injection

**Hook into agent_integration.py:**
- Before run: if `inject_mode != "None"` → prepend memory context block to system prompt
- After run: if `auto_promote_to_knowledge` → check records meeting min_confidence + min_importance → queue projection

**Injection modes:**
- `None` — no injection (default)
- `Append to System Prompt` — memory records added to system prompt as a structured block
- `Tool Available` — inject nothing, but ensure `search_memory_records` tool is available to the agent

**Token budget enforcement:**
- Records sorted by `importance_score desc, modified desc`
- Trimmed to fit within `token_budget` (estimated at 4 chars/token)
- If budget exceeded, lower-importance records are dropped silently

**Auto-promote rule:**
- Background job checks new/updated Memory Records for the policy
- If `promote_to_knowledge = False` and record meets `promotion_min_confidence` + `promotion_min_importance`, set `promote_to_knowledge = 1` and queue projection

### What is explicitly NOT included

- Capture-side enforcement (auto-extraction from runs is Phase 3)
- `allow_role_scope_write` enforcement (manual manager override only for now)

---

## Phase 3 — Learning: Post-run Extraction

**Depends on:** Phase 2 merged

### Goal

Let Memory Policy control when and how the system extracts Memory Records from completed agent runs. Optionally delegate extraction to a dedicated learning agent.

### What is included

**Memory Policy — new Learning section fields:**
- `learning_enabled` (Check)
- `learning_trigger` (Select: Manual | End of Conversation | Every N Turns)
- `turns_per_extraction` (Int — used when trigger = Every N Turns)
- `learning_agent` (Link → Agent — optional, delegates extraction)
- `extracted_record_default_status` (Select: Draft | Active)
- `extraction_model` (Data — optional model override for built-in extraction)

**New module: `huf/ai/memory_extractor.py`**
- `extract_memories_from_run(agent_run_id, memory_policy_name)` — main entry point
- Assembles conversation transcript from Agent Messages
- If `learning_agent` set: routes to that agent via `run_agent_sync()`, parses structured output
- If not: calls built-in extraction prompt against base model
- Saves extracted records with source_type = "Agent Run", run = agent_run_id

**Trigger hooks:**
- End of Conversation: hook on Agent Conversation `on_update` when status changes to Closed/Complete
- Every N Turns: hook on Agent Message `after_insert`, count turns, fire when threshold reached
- Manual: whitelist endpoint `trigger_memory_extraction(agent_run_id)` for explicit calls

**Extraction output format:**
- Learning agent / extraction prompt returns JSON list of memory record drafts
- Each includes: title, summary_text, record_type, confidence, importance_score, tags
- Scope defaults to Conversation for raw extractions; manager can promote later

**Draft-first safety:**
- Default status controlled by `extracted_record_default_status`
- If `approval_required = True`, always Draft regardless of setting
- Desk review queue for Draft records: filter Memory Records by status=Draft, source_type=Agent Run

### Built-in extraction prompt

The default extraction prompt (when no learning_agent is set) will:
1. Receive the conversation transcript
2. Identify facts, preferences, decisions, patterns
3. Output structured JSON matching Memory Record fields
4. Not invent information not present in the transcript

---

## Phase 4 — Learning Profiles + Learning Agent Formalization

**Depends on:** Phase 3 merged

### Goal

Provide named configuration presets (Learning Profiles) so agents can adopt a sensible memory behavior without hand-crafting a Memory Policy from scratch. Formalize the Learning Agent pattern.

### What is included

**Learning Profiles (Memory Policy presets):**
Built-in presets seeded at install time:

| Profile | capture_mode | inject_mode | approval_required | learning_trigger |
|---------|-------------|-------------|-------------------|-----------------|
| Minimal | Manual | None | Yes | Manual |
| Conversational | Auto | Append to System | No | End of Conversation |
| Research | Both | Tool Available | Yes | End of Conversation |
| Operational | Auto | Append to System | No | Every N Turns (5) |

- Profiles are regular Memory Policy docs with `is_preset = True`
- Agents can link to a preset directly or clone it for customization
- Site admins can define additional custom presets

**Learning Agent pattern:**
- `Agent` DocType gains `agent_role` field (Select: General | Learning | Orchestrator | ...)
- A Learning Agent has `agent_role = Learning` and a specialized system prompt
- Memory Policy's `learning_agent` field filtered to agents with `agent_role = Learning`
- Preset learning agents provided for common extraction styles: conservative, liberal, preferences-focused

**Agent Settings:**
- `default_learning_profile` — fallback profile for agents without an explicit memory_policy link

---

## Phase 5 — Retrieval Upgrades: Hybrid Search + Metadata Filters

**Depends on:** Phase 2 merged (earlier phases are independent of this)

### Goal

Improve retrieval quality for memory-projected knowledge and existing Knowledge Sources. Enable hybrid FTS + vector scoring, metadata filtering by scope/tag/record_type, and prepare the backend for additional vector stores.

### What is included

**Hybrid search (per Knowledge Source):**
- Knowledge Sources with `knowledge_type = sqlite_fts` or `sqlite_vec` can opt-in to hybrid mode
- Hybrid mode runs both FTS and vector search, combines scores (reciprocal rank fusion)
- New `search_mode` field on Knowledge Source: FTS | Vector | Hybrid
- Hybrid requires embedding to be configured

**Metadata filters in retrieval:**
- Knowledge Input gains optional `metadata_json` field for tags, scope_type, record_type
- During projection, Memory Record tags + scope_type + record_type written to Knowledge Input metadata
- `knowledge_search()` accepts `metadata_filters` dict to narrow results
- Example: `{"record_type": "Preference", "tags": "hospitality"}` → only matching chunks returned

**Memory-specific search helper:**
- `search_memory_knowledge(query, agent_name, filters)` — searches Knowledge Sources containing projected memory
- Returns results attributed to source Memory Record (via knowledge_input → memory record backlink)

**New backend scaffolding:**
- Abstract `supports_metadata_filters()` method on `KnowledgeBackend`
- Abstract `supports_hybrid_search()` method
- Concrete backends implement or return False
- Future backends (pg_vector, Qdrant, Weaviate) can implement both

**Chunk cleanup on Knowledge Input deletion:**
- `KnowledgeInput.on_trash()` calls `backend.delete_chunks(input_id)` before deletion
- Ensures removing a projected Memory Record actually removes indexed content

---

## Cross-cutting concerns

### Security model (all phases)

- Memory Record Desk access: Managers only
- Tool-level access: scoped per user/role/agent context
- Wider scopes (Role, Site, Global): Managers only
- Knowledge promotion: Managers only
- Extracted draft records: visible to managers for review before activation
- User-scoped memory: never leaks to role/site/global search

### Testing strategy

**Phase 1:**
- Controller validation tests (scope key, status, projection settings)
- Tool permission tests (who can write which scope)
- Projection lifecycle tests (status = Projected, re-projection updates existing KI)

**Phase 2:**
- Policy resolver tests (agent policy vs site default vs None)
- Injection formatting tests (token budget trimming)
- Auto-promote threshold tests

**Phase 3:**
- Extraction trigger tests (end of conversation, every N turns)
- Learning agent delegation tests (mock agent output → memory records)
- Draft/active status based on approval_required

**Phase 5:**
- Hybrid search scoring tests
- Metadata filter tests per backend
- Chunk cleanup verification

### Backward compatibility

- Phase 1 adds new DocTypes — no changes to existing DocTypes
- Phase 2 adds optional fields to Agent and Agent Settings — no breaking changes
- Phase 3 adds optional fields to Memory Policy — no breaking changes
- Phase 5 adds optional fields to Knowledge Source and Knowledge Input — no breaking changes
- At no phase is existing Knowledge Source or Agent Tool Function behavior changed without opt-in

---

## Open questions

1. Should memory injection be visible to the user in the chat UI? (Attribution / transparency)
2. Should users be able to view and delete their own User-scoped memory via the chat UI?
3. How should contradictory memory records be handled in Phase 3+ (flag only, or attempt resolution)?
4. Should Data Tables be eligible as memory sources in a future phase?
5. What telemetry should be captured for memory injection quality and extraction cost?
