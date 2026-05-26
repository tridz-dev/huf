# HUF Memory Layer - Implementation Plan

## Overview
Implementation of the HUF-native memory and learning subsystem, elevating "data management" into a first-class Agent Memory layer with portable records, flexible scopes, and opinionated profiles.

---

## 1. Phase 1 (MVP) Tasks with Dependencies

### Task Group A: Foundation (Week 1)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| A1 | Create Memory Record DocType | None | Medium |
| A2 | Create Memory Policy DocType | None | Medium |
| A3 | Create Memory Profile DocType | None | Low |
| A4 | Add memory section to Agent DocType | A2, A3 | Medium |

### Task Group B: Conversation & Run Integration (Week 1-2)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| B1 | Add memory fields to Agent Conversation | A1 | Low |
| B2 | Add memory observability to Agent Run | A1 | Low |
| B3 | Rename "data management" to "Memory" in UI | None | Trivial |

### Task Group C: Capture Infrastructure (Week 2-3)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| C1 | Implement in-prompt capture mode | A1, A4 | Medium |
| C2 | Implement post-run async capture | A1, A4, B2 | High |
| C3 | Implement specialized memory agent support | A2, A4 | Medium |
| C4 | Implement rule-only capture mode | A1 | Low |

### Task Group D: Storage & Indexing (Week 3)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| D1 | Implement canonical storage in Memory Record | A1 | Low |
| D2 | Optional FTS indexing pipeline | A1 | Medium |
| D3 | Optional vector indexing pipeline | A1 | Medium |
| D4 | Index backend abstraction layer | D2, D3 | Medium |

### Task Group E: Retrieval & Injection (Week 3-4)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| E1 | Memory retrieval service (scope-filtered) | A1 | Medium |
| E2 | Prompt injection integration | E1 | Medium |
| E3 | Memory search tool | E1 | Low |
| E4 | Memory write tool | A1 | Low |

### Task Group F: Profiles & UI (Week 4)
| Task | Description | Dependencies | Complexity |
|------|-------------|--------------|------------|
| F1 | Create 5 opinionated profiles | A3 | Medium |
| F2 | Memory Explorer desk page | A1 | Low |
| F3 | Agent Memory tab UI | A4 | Low |
| F4 | Conversation memory inspector | B1 | Low |

### Dependency Graph
```
A1, A2, A3 (foundation)
    ↓
A4 (Agent integration) ← A2, A3
    ↓
B1, B2 (conversation/run) ← A1
    ↓
C1-C4 (capture) ← A1, A4, B2
    ↓
D1-D4 (storage/indexing) ← A1
    ↓
E1-E4 (retrieval) ← A1, D1-D4
    ↓
F1-F4 (profiles/UI) ← A3, E1-E4
```

---

## 2. New DocTypes to Create

### 2.1 Memory Record
**Purpose:** Canonical portable unit of memory - replaces conversation-embedded JSON

**Core Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | Data | Yes | Human-readable memory title |
| agent | Link (Agent) | Yes | Source agent |
| conversation | Link (Agent Conversation) | No | Source conversation |
| run | Link (Agent Run) | No | Source run |
| source_type | Select | Yes | conversation, run, manual, event, scheduled, imported |
| producer_mode | Select | Yes | main_agent, memory_agent, post_run_llm, rules_only, manual |
| memory_type | Select | Yes | profile, session_state, preference, fact, plan, observation, insight, domain_object, custom |
| schema_name | Data | No | Name of schema used |
| profile_name | Link (Memory Profile) | No | Profile used for capture |
| data_json | JSON | Yes | Structured payload |
| summary_text | Text | No | Human summary |
| raw_context_excerpt | Text | No | Original context snippet |
| scope_type | Select | Yes | conversation, user, agent, namespace, global |
| scope_key | Data | Yes | Scoped identifier |
| visibility | Select | Yes | private, shared_with_agent, shared_with_namespace, global |
| status | Select | Yes | active, superseded, archived, expired, error |
| confidence | Float | No | 0.0-1.0 confidence score |
| importance_score | Float | No | 0.0-1.0 importance |
| ttl_days | Int | No | Time-to-live in days |
| effective_from | DateTime | No | Validity start |
| effective_until | DateTime | No | Validity end |
| supersedes_memory_record | Link (Memory Record) | No | Previous version |
| created_from_turn_count | Int | No | Conversation turn when captured |
| tags | Table | No | Tags for categorization |
| metadata_json | JSON | No | Additional metadata |
| fts_indexed | Check | No | FTS index status |
| vector_indexed | Check | No | Vector index status |
| index_backend | Select | No | none, sqlite_fts, sqlite_vec, pgvector, custom |
| last_indexed_at | DateTime | No | Last index timestamp |
| last_retrieved_at | DateTime | No | Last access timestamp |
| retrieval_count | Int | No | Number of retrievals |

**Estimated Complexity: 3-4 days**

---

### 2.2 Memory Policy
**Purpose:** Defines how an agent performs memory capture

**Core Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| policy_name | Data | Yes | Unique name |
| enabled | Check | Yes | Active flag |
| agent | Link (Agent) | No | Linked agent |
| memory_profile | Link (Memory Profile) | No | Default profile |
| capture_owner | Select | Yes | main_agent, memory_agent, post_run_llm, rules_only |
| memory_agent | Link (Agent) | No | Specialized agent for capture |
| capture_stage | Select | Yes | in_prompt, post_response_sync, post_response_async, conversation_end, scheduled |
| capture_frequency_type | Select | Yes | every_run, every_n_runs, every_n_turns, conversation_end, manual, scheduled |
| capture_frequency_value | Int | No | N value for frequency |
| conversation_end_strategy | Select | No | manual_close, idle_timeout, heuristic, never |
| idle_timeout_minutes | Int | No | Auto-close after idle |
| capture_prompt | Text | No | Prompt for extraction |
| capture_schema_json | JSON | No | Expected schema |
| allow_open_schema | Check | No | Allow flexible schema |
| require_json_schema_match | Check | No | Enforce schema strictness |
| allow_update_existing | Check | No | Enable updates |
| allow_merge | Check | No | Enable merging |
| allow_append | Check | No | Enable appending |
| min_confidence | Float | No | Minimum confidence threshold |
| store_raw_payload | Check | No | Store raw input |
| store_summary | Check | No | Generate summary |
| enable_fts_index | Check | No | Enable FTS |
| enable_vector_index | Check | No | Enable vector index |
| vector_backend | Select | No | sqlite_vec, pgvector, custom |
| fts_backend | Select | No | sqlite_fts, custom |
| retrieval_mode_default | Select | Yes | inject, tool_only, hybrid |
| max_items_to_inject | Int | No | Injection limit |
| max_tokens_to_inject | Int | No | Token budget |

**Estimated Complexity: 2-3 days**

---

### 2.3 Memory Profile
**Purpose:** Opinionated presets for common domains

**Core Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| profile_name | Data | Yes | Unique name |
| description | Text | No | Profile description |
| category | Select | Yes | programming, science, language, reasoning, general, travel, crm, support, documentation, custom |
| default_schema_json | JSON | Yes | Default capture schema |
| default_capture_prompt | Text | Yes | Extraction prompt template |
| recommended_model | Data | No | Suggested model |
| recommended_provider | Data | No | Suggested provider |
| default_capture_stage | Select | No | Default timing |
| default_frequency | Select | No | Default frequency |
| default_scope_type | Select | No | Default scope |
| default_indexing_mode | Select | No | fts, vector, both, none |
| default_retrieval_mode | Select | No | inject, tool_only, hybrid |
| default_memory_type_mapping | JSON | No | Type mapping rules |
| icon | Attach Image | No | Profile icon |
| is_system_profile | Check | Yes | Built-in flag |

**Shipped Profiles (MVP):**
1. **Programming Memory** - code patterns, conventions, debugging context
2. **General Knowledge Memory** - facts, preferences, reusable info
3. **Travel Planning Memory** - destinations, dates, preferences, constraints
4. **CRM Memory** - customer context, history, preferences
5. **Documentation Memory** - requirements, decisions, API contracts

**Estimated Complexity: 2 days**

---

## 3. Modifications to Existing DocTypes

### 3.1 Agent (New Memory Section)
**Estimated Complexity: 2 days**

| Field | Type | Description |
|-------|------|-------------|
| enable_memory | Check | Master toggle |
| memory_policy | Link (Memory Policy) | Policy reference |
| default_memory_scope_type | Select | conversation, user, agent, namespace, global |
| default_memory_scope_key_template | Data | Jinja template for scope key |
| memory_retrieval_mode | Select | inject, tool_only, hybrid |
| memory_in_prompt_budget | Int | Token budget for injection |
| enable_memory_search_tool | Check | Add search tool |
| enable_memory_write_tool | Check | Add write tool |
| memory_profile | Link (Memory Profile) | Default profile |
| memory_agent | Link (Agent) | Specialized agent |
| memory_run_order | Select | before_main_response, after_main_response, background |
| memory_max_items | Int | Max memories per query |
| memory_index_backend_default | Select | none, sqlite_fts, sqlite_vec, pgvector |
| memory_visibility_default | Select | private, shared_with_agent, shared_with_namespace, global |

### 3.2 Agent Conversation
**Estimated Complexity: 1 day**

| Field | Type | Description |
|-------|------|-------------|
| memory_scope_override | Select | Override default scope |
| memory_scope_key_override | Data | Override scope key |
| memory_capture_enabled_override | Check | Force enable/disable |
| memory_turn_count | Int | Turns since last capture |
| memory_last_capture_at | DateTime | Last capture timestamp |
| conversation_end_state | Select | open, closing, closed |
| ended_at | DateTime | Close timestamp |
| idle_expires_at | DateTime | Idle timeout |

### 3.3 Agent Run
**Estimated Complexity: 1 day**

| Field | Type | Description |
|-------|------|-------------|
| memory_capture_triggered | Check | Capture attempted |
| memory_capture_mode | Select | Mode used |
| memory_records_created | Int | Records created |
| memory_records_updated | Int | Records updated |
| memory_records_skipped | Int | Records skipped |
| memory_index_jobs_started | Int | Index jobs queued |
| memory_capture_latency_ms | Int | Capture time |
| memory_capture_cost | Float | Estimated cost |
| memory_error_log | Text | Error details |

---

## 4. File Changes Required

### New Files
```
huf_agent_memory/
├── memory_record/
│   ├── memory_record.json          # DocType definition
│   ├── memory_record.py            # Server controller
│   └── test_memory_record.py       # Unit tests
├── memory_policy/
│   ├── memory_policy.json          # DocType definition
│   ├── memory_policy.py            # Server controller
│   └── test_memory_policy.py
├── memory_profile/
│   ├── memory_profile.json         # DocType definition
│   ├── memory_profile.py           # Server controller
│   ├── default_profiles.py         # Shipped profiles
│   └── test_memory_profile.py
├── capture/
│   ├── capture_service.py          # Core capture orchestrator
│   ├── in_prompt_capture.py        # In-prompt mode
│   ├── post_run_capture.py         # Async capture worker
│   ├── memory_agent_capture.py     # Specialized agent mode
│   └── rule_capture.py             # Rule-only mode
├── storage/
│   ├── storage_service.py          # Canonical storage
│   ├── fts_indexer.py              # FTS indexing
│   ├── vector_indexer.py           # Vector indexing
│   └── index_backend.py            # Backend abstraction
├── retrieval/
│   ├── retrieval_service.py        # Memory retrieval
│   ├── prompt_injector.py          # Prompt injection
│   ├── memory_search_tool.py       # Search tool implementation
│   └── memory_write_tool.py        # Write tool implementation
├── scope/
│   └── scope_resolver.py           # Scope/visibility logic
└── utils/
    └── schema_validator.py         # JSON schema validation

huf_agent/doctype/agent/
├── agent.json                      # MODIFY - add memory fields
└── agent.py                        # MODIFY - memory integration

huf_agent/doctype/agent_conversation/
├── agent_conversation.json         # MODIFY - add memory fields
└── agent_conversation.py           # MODIFY - lifecycle hooks

huf_agent/doctype/agent_run/
├── agent_run.json                  # MODIFY - add observability
└── agent_run.py                    # MODIFY - capture triggers

huf_agent_memory/www/
└── memory_explorer.html            # Desk page

huf_agent_memory/public/js/
├── memory_profile_selector.js      # UI component
└── memory_inspector.js             # Conversation inspector
```

### Modified Files
```
huf_agent/hooks.py                  # Register memory signals
huf_agent/patches.txt               # Migration patches
huf_agent/doctype/agent/agent.js    # Memory tab UI
```

---

## 5. Estimated Complexity Summary

### By Component
| Component | Days | Risk Level |
|-----------|------|------------|
| Memory Record DocType | 3 | Low |
| Memory Policy DocType | 2 | Low |
| Memory Profile DocType + 5 profiles | 2 | Low |
| Agent modifications | 2 | Medium |
| Conversation/Run modifications | 1 | Low |
| Capture infrastructure | 4 | Medium |
| Storage & indexing | 3 | Medium |
| Retrieval & injection | 3 | Medium |
| UI components | 2 | Low |
| Testing & integration | 2 | Medium |
| **TOTAL** | **24 days** | **Medium** |

### Risk Factors
- **Medium:** Post-run async capture requires background worker integration
- **Medium:** Vector indexing dependency on existing HUF vector infrastructure
- **Medium:** Prompt injection may affect token budgeting logic

### Suggested Team
- 1 Backend Engineer (DocTypes, capture, storage)
- 1 Integration Engineer (retrieval, injection, UI)
- 0.5 QA Engineer (testing, profile validation)

---

## 6. Success Criteria (MVP)

- [ ] Memory Record created and queryable
- [ ] Memory Policy configures agent behavior
- [ ] 5 profiles shipped and functional
- [ ] In-prompt capture works end-to-end
- [ ] Post-run async capture queues successfully
- [ ] Scope filtering (conversation/user/agent/global) works
- [ ] FTS indexing optional and functional
- [ ] Memory appears in agent prompts when configured
- [ ] "Data management" renamed to "Memory" throughout UI
