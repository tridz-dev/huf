# HUF Memory System — Project Tracking

> **Project:** HUF Agent Memory & Learning Layer  
> **Started:** 2026-03-28  
> **Status:** In Progress — Phase 1 (Design Complete, Implementation Pending)  
> **Observer:** Coordinator Subagent

---

## 1. Project Overview

Transform HUF from "agent orchestration + RAG" into a platform where agents maintain durable, scoped, portable memory and reusable learned knowledge over time.

### Key Deliverables
- **Memory Record** — First-class DocType for structured memory storage
- **Memory Policy** — Configurable capture and storage policies
- **Memory Profile** — Opinionated presets for common domains
- **Agent Integration** — Memory settings in Agent, Agent Conversation, Agent Run
- **Capture Pipeline** — Multiple capture modes (in-prompt, post-run sync/async, specialized agent)
- **Scope Model** — conversation, user, agent, namespace, global visibility
- **Storage Layer** — Canonical storage + optional FTS/vector indexing
- **Retrieval System** — Prompt injection, tool search, hybrid modes

---

## 2. Project Phases & Milestones

### Phase 1: Core Infrastructure (MVP)
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 1.1 | Memory Record DocType definition | ✅ Complete | Data Model Architect |
| 1.2 | Memory Policy DocType definition | ✅ Complete | Data Model Architect |
| 1.3 | Memory Profile DocType definition | ✅ Complete | Data Model Architect |
| 1.4 | Agent DocType memory fields | 🔲 Pending | TBD |
| 1.5 | Agent Conversation memory fields | 🔲 Pending | TBD |
| 1.6 | Agent Run observability fields | 🔲 Pending | TBD |

### Phase 2: Capture Pipeline
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 2.1 | In-prompt capture mode | 🔲 Pending | TBD |
| 2.2 | Post-response sync capture | 🔲 Pending | TBD |
| 2.3 | Post-response async capture (background jobs) | 🔲 Pending | TBD |
| 2.4 | Specialized memory agent support | 🔲 Pending | TBD |
| 2.5 | Rule-only capture mode | 🔲 Pending | TBD |
| 2.6 | Conversation-end detection | 🔲 Pending | TBD |

### Phase 3: Storage & Indexing
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 3.1 | Canonical storage implementation | 🔲 Pending | TBD |
| 3.2 | SQLite FTS indexing | 🔲 Pending | TBD |
| 3.3 | SQLite vector indexing | 🔲 Pending | TBD |
| 3.4 | Index backend abstraction | 🔲 Pending | TBD |

### Phase 4: Retrieval & Integration
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 4.1 | Prompt injection system | 🔲 Pending | TBD |
| 4.2 | Memory search tool | 🔲 Pending | TBD |
| 4.3 | Hybrid retrieval mode | 🔲 Pending | TBD |
| 4.4 | Scope-aware filtering | 🔲 Pending | TBD |

### Phase 5: Profiles & UX
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 5.1 | Programming Memory profile | 🔲 Pending | TBD |
| 5.2 | Science/Research Memory profile | 🔲 Pending | TBD |
| 5.3 | Language Learning profile | 🔲 Pending | TBD |
| 5.4 | Travel Planning profile | 🔲 Pending | TBD |
| 5.5 | General Knowledge profile | 🔲 Pending | TBD |
| 5.6 | Documentation Memory profile | 🔲 Pending | TBD |
| 5.7 | Agent form Memory tab UI | 🔲 Pending | TBD |
| 5.8 | Memory Explorer desk page | 🔲 Pending | TBD |

### Phase 6: Polish & Future
| Milestone | Description | Status | Assigned |
|-----------|-------------|--------|----------|
| 6.1 | Consolidation engine | 🔲 Pending | TBD |
| 6.2 | Deduplication logic | 🔲 Pending | TBD |
| 6.3 | Expiry/pruning | 🔲 Pending | TBD |
| 6.4 | Memory health dashboards | 🔲 Pending | TBD |
| 6.5 | Hindsight integration (optional future) | 🔲 Pending | TBD |

---

## 3. Agent Assignments

| Agent ID | Role | Assigned Tasks | Status | Last Update |
|----------|------|----------------|--------|-------------|
| **data-model-architect** | Data Model Architect | DocType definitions (1.1-1.3) | ✅ Complete | 2026-03-28 |
| **capture-pipeline-engineer** | Capture Pipeline Engineer | Capture modes (2.1-2.6) | 🔲 Not started | — |
| **storage-engineer** | Storage Engineer | Indexing & storage (3.1-3.4) | 🔲 Not started | — |
| **retrieval-engineer** | Retrieval Engineer | Search & injection (4.1-4.4) | 🔲 Not started | — |
| **profile-ux-designer** | Profile/UX Designer | Profiles & UI (5.1-5.8) | 🔲 Not started | — |
| **tech-spec-writer** | Technical Spec Writer | Capture & Retrieval specs | ✅ Complete | 2026-03-28 |
| **coordinator** (this agent) | Observer/Coordinator | Tracking, review, coordination | 🟡 Active | 2026-03-28 |

---

## 4. Current Status

### Overall Progress: ~15% (Phase 1 Design Complete)

### Recently Completed
- ✅ PRD finalized and documented
- ✅ Project directory structure created
- ✅ Tracking document established
- ✅ **Memory Record DocType design complete** (`~/code/huf-memory/doctype_designs/memory_record.json`)
- ✅ **Memory Policy DocType design complete** (`~/code/huf-memory/doctype_designs/memory_policy.json`)
- ✅ **Memory Profile DocType design complete** (`~/code/huf-memory/doctype_designs/memory_profile.json`)
- ✅ **Capture & Retrieval technical specifications complete** (`~/code/huf-memory/tech_specs/CAPTURE_RETRIEVAL.md`)

### In Progress
- 🟡 Awaiting Phase 1 implementation (Frappe DocType creation)
- 🟡 Awaiting agent assignments for implementation tasks

### Pending Tasks (Ready for Assignment)
1. Create Frappe DocType files from JSON designs:
   - `huf/huf/doctype/memory_record/`
   - `huf/huf/doctype/memory_policy/`
   - `huf/huf/doctype/memory_profile/`
2. Add memory fields to existing DocTypes (Agent, Agent Conversation, Agent Run)
3. Implement Python controller classes for memory DocTypes
4. Set up database migrations

---

## 5. Agent Output Files Summary

| File Path | Description | Status | Created By |
|-----------|-------------|--------|------------|
| `~/code/huf-memory/doctype_designs/memory_record.json` | Memory Record DocType schema definition | ✅ Complete | data-model-architect |
| `~/code/huf-memory/doctype_designs/memory_policy.json` | Memory Policy DocType schema definition | ✅ Complete | data-model-architect |
| `~/code/huf-memory/doctype_designs/memory_profile.json` | Memory Profile DocType schema definition | ✅ Complete | data-model-architect |
| `~/code/huf-memory/tech_specs/CAPTURE_RETRIEVAL.md` | Capture modes & retrieval technical specs | ✅ Complete | tech-spec-writer |
| `~/code/huf-memory/PROJECT_TRACKING.md` | This tracking document | 🟡 Active | coordinator |

---

## 6. Blockers & Issues

| Issue ID | Description | Severity | Owner | Resolution |
|----------|-------------|----------|-------|------------|
| — | No active blockers | — | — | — |

---

## 7. Technical Decisions Log

| Date | Decision | Context | Status |
|------|----------|---------|--------|
| 2026-03-28 | Build natively in HUF first | Hindsight integration deferred to later phase | ✅ Finalized |
| 2026-03-28 | Rename "data management" → "Agent Memory" | Better product positioning | ✅ Finalized |
| 2026-03-28 | Support both flexible schema + opinionated presets | Balance power and usability | ✅ Finalized |
| 2026-03-28 | Use JSON-based DocType design first | Allows review before Frappe implementation | ✅ Finalized |

---

## 8. Next Steps

### Immediate (Next 24h)
1. [ ] Assign implementation agents to Phase 1 milestones
2. [ ] Convert JSON DocType designs to Frappe DocType files
3. [ ] Create Python controller classes for Memory Record, Policy, Profile
4. [ ] Set up development branch for memory system

### Short Term (This Week)
1. [ ] Complete all Phase 1 DocType implementations
2. [ ] Begin Phase 2 capture pipeline implementation
3. [ ] Design storage backend abstraction layer

### Medium Term (Next 2 Weeks)
1. [ ] Complete Phase 2 & 3 (capture + storage)
2. [ ] Begin Phase 4 retrieval system
3. [ ] Implement first 3 opinionated profiles

---

## 9. Resource Links

- **PRD:** `~/code/huf-memory/PRD.md`
- **This Tracking Doc:** `~/code/huf-memory/PROJECT_TRACKING.md`
- **AGENTS.md (Project Context):** `~/code/huf-memory/AGENTS.md`
- **DocType Designs:** `~/code/huf-memory/doctype_designs/`
- **Tech Specs:** `~/code/huf-memory/tech_specs/`
- **Code Repository:** `~/code/huf-memory/` (HUF Frappe app)

---

## 10. Agent Communication Log

| Timestamp | Agent | Message | Action Required |
|-----------|-------|---------|-----------------|
| 2026-03-28 04:46 | Coordinator | Project tracking initialized | Awaiting agent reports |
| 2026-03-28 04:47 | data-model-architect | Completed DocType designs for Memory Record, Memory Policy, Memory Profile | Review and approve for implementation |
| 2026-03-28 04:47 | tech-spec-writer | Completed Capture & Retrieval technical specifications | Review and use for implementation guidance |

---

## 11. Design Artifacts Summary

### Memory Record DocType
**Purpose:** Canonical portable unit of memory  
**Key Fields:**
- Core: title, agent, conversation, run, source_type, producer_mode, memory_type
- Data: schema_name, profile_name, data_json, summary_text, raw_context_excerpt
- Scope: scope_type, scope_key, visibility
- Lifecycle: status, confidence, importance_score, ttl_days, effective_from/until
- Indexing: fts_indexed, vector_indexed, index_backend, last_indexed_at
- Retrieval Stats: last_retrieved_at, retrieval_count

### Memory Policy DocType
**Purpose:** Configurable capture and storage policies  
**Key Fields:**
- Basic: policy_name, enabled, agent, memory_profile
- Capture: capture_owner, memory_agent, capture_stage
- Frequency: capture_frequency_type, capture_frequency_value, conversation_end_strategy, idle_timeout_minutes
- Schema: capture_prompt, capture_schema_json, allow_open_schema, require_json_schema_match
- Merge: allow_update_existing, allow_merge, allow_append, min_confidence
- Storage: store_raw_payload, store_summary, enable_fts_index, enable_vector_index, vector_backend, fts_backend
- Retrieval: retrieval_mode_default, max_items_to_inject, max_tokens_to_inject

### Memory Profile DocType
**Purpose:** Opinionated presets for common domains  
**Key Fields:**
- Identity: profile_name, description, category, icon, is_system_profile
- Schema: default_schema_json, default_capture_prompt, default_memory_type_mapping
- Model: recommended_model, recommended_provider
- Defaults: default_capture_stage, default_frequency, default_scope_type, default_indexing_mode, default_retrieval_mode
- UI: ui_labels_json, example_memories_json, documentation_url

### Capture & Retrieval Specs
**Document:** `CAPTURE_RETRIEVAL.md`  
**Covers:**
- 5 capture modes: in_prompt, post_response_sync, post_response_async, specialized_agent, rules_only
- 10 trigger types: every_run, every_n_runs, every_n_turns, after_tool_call, final_response_only, conversation_end, idle_timeout, manual, scheduled
- 3 retrieval modes: inject, tool_only, hybrid
- Retrieval ranking algorithm
- Error handling strategies

---

*Last updated: 2026-03-28 04:47 GMT+8 by coordinator*
