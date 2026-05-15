# HUF PRD — Programmable Memory & Learning Layer

## 1. Summary

HUF already has the foundation for a native memory system: agents, conversations, runs, tools, scoped persistence, and a knowledge subsystem with Knowledge Source, Knowledge Input, mandatory prompt injection, and optional knowledge_search over SQLite FTS and vector-capable backends. Agents already persist conversations, can persist per-user history in doc/schedule contexts, and HUF already supports both synchronous and orchestrated execution flows. 

Today's "data management" capability is an optional, prompt-driven structured capture mechanism. It is not automatic, not global, and not yet modeled as a first-class portable knowledge/memory object. The proposed product direction is to evolve this into a first-class, configurable memory/learning layer that remains native to HUF rather than integrating Hindsight first. This is because the HUF design we discussed already covers the core paradigm: optional capture, structured extraction, scoped sharing, pluggable storage, and native retrieval. Hindsight still provides a more mature retain/recall/reflect engine, but that is an advanced enhancement, not a prerequisite for HUF's first-party product maturity. 

## 2. Product Goal

Turn HUF from "agent orchestration + RAG" into a platform where agents can optionally maintain durable, scoped, portable memory and reusable learned knowledge over time, while keeping the system composable, per-agent configurable, and aligned with HUF's existing DocType architecture. HUF should support both open-ended memory capture and opinionated, ready-to-use knowledge/memory profiles for common domains such as programming, science, language, reasoning, and general information. This aligns with the broader pattern seen in Agno's Learning Machine model, where agents use typed stores and configurable learning modes, but HUF should implement this in a more flexible, product-native way. 

## 3. Why This Matters

A mature agent platform cannot stop at conversation persistence and document retrieval. It needs memory that can capture structured user context, reusable facts, preferences, plans, and shared insights, and make them available selectively across conversation, user, agent, or wider scopes. Agno formalizes this through stores such as User Profile, User Memory, Session Context, Entity Memory, and Learned Knowledge, each with configurable modes such as Always, Agentic, and Propose. HUF does not need to clone that exact shape, but it does need the same paradigm: configurable capture, durable storage, scoped sharing, and retrieval-aware reuse. 

## 4. Current State in HUF

HUF already provides the structural substrate needed for this initiative. The current system has first-class Agent, Agent Conversation, Agent Message, and Agent Run records, along with configurable agent instructions, tools, provider/model selection, conversation persistence, and per-user history behavior. It also has a knowledge architecture with Knowledge Source, Knowledge Input, Agent Knowledge, an ingestion/indexing pipeline, SQLite FTS retrieval, optional vector backends, and both mandatory and optional knowledge access patterns. HUF also already supports orchestrated multi-step execution and scheduled/event-triggered execution, which gives it natural insertion points for memory capture and post-run learning. 

The important point is that HUF is not starting from zero. The missing piece is not raw storage or retrieval. The missing piece is to elevate "data management" from a prompt-level helper into a productized memory/learning layer with its own lifecycle, scope model, storage policy, triggers, and optional opinionated templates.

## 5. Current "Data Management" Capability

Today, data management is an optional capability enabled per agent. When enabled, a tool is injected that allows structured JSON-form capture during the conversation. The behavior is prompt-driven: the main agent prompt can decide what to capture, or a specialized agent can be used to decide extraction structure and semantics. This is already powerful because it supports domain-specific capture such as travel destination, dates, party size, purpose, or budget without forcing one universal schema.

This means HUF already has the conceptual beginning of "learning," but in its current form it is still tightly coupled to run-time prompting and not yet portable as a reusable knowledge/memory object. It also lacks first-class controls for scope, lifecycle, indexing policy, sharing policy, and reusable domain presets.

## 6. Product Direction

HUF should evolve this feature into a first-class configurable subsystem. A better product name than "data management" is needed because the capability is no longer just data capture. Recommended names, in order:
 1. Memory Layer
 2. Learning Layer
 3. Agent Memory
 4. Context Memory
 5. Knowledge Capture
 6. Structured Memory

Recommended final product name: Agent Memory for the user-facing feature, with Memory Record or Memory Layer as the core technical concept.

"Data management" understates the feature. The new system is not only about storing JSON. It is about capturing, structuring, scoping, indexing, retrieving, and optionally consolidating memory for agents.

## 7. Product Principles

HUF's memory system should follow these principles:
 - Memory is optional, not globally forced.
 - Memory is agent-configurable, not hidden infrastructure.
 - Capture can be performed by the main agent, a specialized memory agent, or a post-run processor.
 - Storage is pluggable: raw structured data, SQLite FTS, SQLite vector, and future vector backends.
 - Scope is explicitly controlled: conversation, user, agent, group/custom namespace, or global.
 - Retrieval is native: memory should participate in prompt building and tool-based search just as knowledge sources do today.
 - The system should support both flexible open schema and opinionated presets for faster adoption.
 - HUF should build this natively first; Hindsight is not the first integration target unless HUF later wants a more advanced reflect/consolidation engine. Hindsight's differentiators are memory banks, richer extraction of facts/entities/relationships, multi-path retrieval, and dedicated reflect loops. 

## 8. What We Are Building

We are building a first-class HUF-native memory and learning subsystem that generalizes the current data management feature into a portable, policy-driven layer with:
 - optional structured capture
 - configurable extraction ownership
 - configurable trigger timing
 - first-class storage objects
 - explicit sharing and visibility scopes
 - optional indexing into FTS and/or vector backends
 - native retrieval and prompt injection
 - opinionated presets with recommended models and extraction styles
 - future room for consolidation, pruning, deduplication, and reflection

## 9. Core Model

The design centers on one new first-class record type plus supporting config records.

### 9.1 Primary new DocType: Memory Record

Recommended technical name: Agent Memory Record or Memory Record

This is the canonical portable unit of memory. It replaces conversation-embedded JSON as the long-term model.

Purpose: A structured or semi-structured memory object produced from a conversation, run, event, or post-run process, with configurable scope, storage, and retrieval behavior.

Key fields:
 - title
 - agent
 - conversation
 - run
 - source_type (conversation, run, manual, event, scheduled, imported)
 - producer_mode (main_agent, memory_agent, post_run_llm, rules_only, manual)
 - memory_type (profile, session_state, preference, fact, plan, observation, insight, domain_object, custom)
 - schema_name or profile_name
 - data_json (structured payload)
 - summary_text
 - raw_context_excerpt
 - scope_type (conversation, user, agent, namespace, global)
 - scope_key (e.g. conversation id, user id, agent name, namespace value)
 - visibility (private, shared_with_agent, shared_with_namespace, global)
 - status (active, superseded, archived, expired, error)
 - confidence
 - importance_score
 - ttl_days
 - effective_from
 - effective_until
 - supersedes_memory_record
 - created_from_turn_count
 - tags
 - metadata_json
 - fts_indexed
 - vector_indexed
 - index_backend (none, sqlite_fts, sqlite_vec, pgvector, custom)
 - last_indexed_at
 - last_retrieved_at
 - retrieval_count

This one record becomes the portable memory object that can be referenced by agents, searched, indexed, filtered, or reused across scopes.

### 9.2 Config DocType: Memory Policy

This defines how a given agent or workflow performs memory capture.

Key fields:
 - policy_name
 - enabled
 - agent
 - memory_profile
 - capture_owner (main_agent, memory_agent, post_run_llm, rules_only)
 - memory_agent (Link to Agent, optional)
 - capture_stage (in_prompt, post_response_sync, post_response_async, conversation_end, scheduled)
 - capture_frequency_type (every_run, every_n_runs, every_n_turns, conversation_end, manual, scheduled)
 - capture_frequency_value
 - conversation_end_strategy (manual_close, idle_timeout, heuristic, never)
 - idle_timeout_minutes
 - capture_prompt
 - capture_schema_json
 - allow_open_schema
 - require_json_schema_match
 - allow_update_existing
 - allow_merge
 - allow_append
 - min_confidence
 - store_raw_payload
 - store_summary
 - enable_fts_index
 - enable_vector_index
 - vector_backend
 - fts_backend
 - retrieval_mode_default (inject, tool_only, hybrid)
 - max_items_to_inject
 - max_tokens_to_inject

### 9.3 Optional DocType: Memory Profile

This is the opinionated preset layer.

Purpose: Provide ready-made capture schema, prompts, storage defaults, and recommended models for common domains.

Example profiles:
 - Programming Memory
 - Science/Research Memory
 - Language Learning Memory
 - Reasoning/Mathematics Memory
 - General Knowledge Memory
 - Travel Planning Memory
 - CRM / Customer Context Memory
 - Support Ticket Context Memory

Key fields:
 - profile_name
 - description
 - category
 - default_schema_json
 - default_capture_prompt
 - recommended_model
 - recommended_provider
 - default_capture_stage
 - default_frequency
 - default_scope_type
 - default_indexing_mode
 - default_retrieval_mode
 - default_memory_type_mapping
 - icon
 - is_system_profile

This is how HUF becomes easier to use than a purely raw, schema-less system.

## 10. Changes to Existing DocTypes

### 10.1 Agent

Add a new Memory / Learning section to Agent.

Recommended new fields:
 - enable_memory
 - memory_policy (Link)
 - default_memory_scope_type
 - default_memory_scope_key_template
 - memory_retrieval_mode (inject, tool_only, hybrid)
 - memory_in_prompt_budget
 - enable_memory_search_tool
 - enable_memory_write_tool
 - memory_profile
 - memory_agent (optional)
 - memory_run_order (before_main_response, after_main_response, background)
 - memory_max_items
 - memory_index_backend_default
 - memory_visibility_default

This complements the existing agent settings around persistence, tools, and knowledge sources rather than replacing them. Existing agent features such as persist_conversation, persist_user_history, agent tools, and knowledge bindings remain relevant and should work alongside memory. 

### 10.2 Agent Conversation

Add fields to support memory lifecycle:
 - memory_scope_override
 - memory_scope_key_override
 - memory_capture_enabled_override
 - memory_turn_count
 - memory_last_capture_at
 - conversation_end_state
 - ended_at
 - idle_expires_at

This lets conversation state drive memory policies like "capture on end" or "capture every 10 turns."

### 10.3 Agent Run

Add observability fields:
 - memory_capture_triggered
 - memory_capture_mode
 - memory_records_created
 - memory_records_updated
 - memory_records_skipped
 - memory_index_jobs_started
 - memory_capture_latency_ms
 - memory_capture_cost
 - memory_error_log

HUF already tracks run status and token usage; these fields extend that for memory observability. 

### 10.4 Knowledge Source / Agent Knowledge

No breaking change required, but add support for memory-backed knowledge ingestion or memory-backed retrieval. Existing Knowledge Source already supports indexed containers and Agent Knowledge already defines mandatory versus optional access. The new memory system should be able to optionally emit into a Knowledge Source or appear as a retrievable memory source under the same retrieval framework. 

## 11. Capture Modes

HUF should support multiple capture modes, inspired by the same problem Agno solves with Always / Agentic / Propose, but implemented in HUF's more configurable style. 

### 11.1 In-prompt capture

The main agent is instructed during its run to maintain/update structured memory. This is closest to today's model.

Best for:
 - low-latency, simple fields
 - short-lived session state
 - agent-specific domains where prompt quality is known

### 11.2 Post-response synchronous capture

After the user-facing response is generated, capture happens immediately in the same request. This guarantees consistency but adds latency.

Best for:
 - critical profile updates
 - highly structured extractions

### 11.3 Post-response asynchronous capture

After the main response, a background job or queued hook performs extraction and storage. This avoids user-facing latency and is the recommended default for heavier extraction.

Best for:
 - travel capture
 - CRM enrichment
 - learned summaries
 - long conversations

### 11.4 Specialized memory agent

Instead of the main agent prompt deciding what to store, a dedicated memory agent runs with its own prompt, model, and possibly cheaper or more extraction-tuned provider.

Best for:
 - strict schemas
 - domain-specific extraction
 - cost optimization
 - different reasoning style from main agent

### 11.5 Rule-only capture

A no-LLM mode for deterministic fields or external system events.

Best for:
 - exact user IDs
 - timestamps
 - state transitions
 - system-generated plans

## 12. Capture Triggers

HUF should support first-class trigger controls for memory capture.

Supported trigger types:
 - every run
 - every N runs
 - every N turns in a conversation
 - after a tool call
 - after final response only
 - when conversation is marked complete
 - when idle timeout is reached
 - manual capture
 - scheduled consolidation

This aligns well with HUF's existing trigger-oriented architecture, since HUF already supports Agent Trigger for schedule/doc event/webhook/app/manual execution. The same philosophy should be applied to memory capture policy. 

### Conversation-end detection

Support all of:
 - manual close by user/admin
 - automatic close after inactivity threshold
 - heuristic close based on agent classification
 - close-on-workflow-completion

## 13. Scope and Sharing Model

This is one of the biggest reasons to move from embedded conversation JSON to a standalone DocType.

Supported scopes:
 - Conversation: memory visible only inside the current conversation
 - User: memory visible across the same user's interactions
 - Agent: shared across all users of one agent
 - Namespace: custom scope shared by a chosen group such as sales_west, project_alpha, or family_trip
 - Global: visible to all eligible agents or the full site, subject to permissioning

This is conceptually similar to Agno's configurable namespaces and Hindsight's memory bank separation, but HUF should implement it in its own DocType-native model. Agno explicitly supports user/global/custom namespace models in some stores, and Hindsight recommends one bank per user or per agent depending on the use case. 

Sharing examples:
 - Travel agent shares trip memory only within one conversation
 - Visa agent shares customer profile across all that user's sessions
 - Programming tutor shares reusable best-practice snippets globally
 - Three research agents share one custom namespace for a project

## 14. Storage Architecture

The new memory layer should separate canonical storage from indexing.

### Canonical storage

All memory lives first in Memory Record as the source of truth.

### Optional indexing

Memory may then be indexed into:
 - SQLite FTS
 - SQLite vector
 - future pgvector
 - future external vector backend
 - hybrid FTS + vector

The user asked specifically for the ability to store raw structured data in the primary table while optionally pushing to vector and/or FTS. That should be a first-class policy field, not an implementation detail.

Why this matters:

This keeps HUF portable and avoids coupling learning to any one backend. The record remains queryable and auditable even if vector indexing is disabled or rebuilt later.

## 15. Retrieval Model

HUF already has a strong knowledge retrieval pathway: mandatory context injection and optional knowledge_search tool. The new memory layer should integrate into the same conceptual pipeline. 

### Retrieval options:
 - Inject into prompt as relevant memory context
 - Tool-only search where the agent explicitly queries memory
 - Hybrid, where top-ranked memory is injected and the rest remains searchable

### Retrieval filters:
 - scope
 - agent
 - user
 - namespace
 - memory type
 - confidence
 - recency
 - tags
 - profile
 - source type

### Retrieval ranking

Phase 1:
 - recency + confidence + scope weighting + backend relevance

Phase 2:
 - per-profile ranking strategy
 - explicit importance weighting
 - later optional consolidation/reflect

## 16. Opinionated Profiles

This is the productization layer.

Each profile should define:
 - schema
 - extraction prompt
 - recommended model
 - capture stage
 - storage defaults
 - retrieval defaults
 - UI labels and help text

### Example: Programming Memory

Captures:
 - language
 - stack
 - coding conventions
 - architectural decisions
 - reusable fix patterns
 - debugging context

Storage:
 - structured record + vector
 - optional FTS

Recommended models:
 - low-cost extraction model for routine capture
 - stronger reasoning model for consolidation

### Example: Science / Research Memory

Captures:
 - concepts
 - claims
 - evidence level
 - references
 - contradictions
 - open questions

Storage:
 - structured + vector
 - high emphasis on citation metadata

### Example: Travel Planning Memory

Captures:
 - destination
 - dates
 - travelers
 - budget
 - preferences
 - purpose
 - accommodation constraints

Storage:
 - structured + optional vector
 - usually user- or conversation-scoped

This profile-based approach gives HUF the benefits of Agno's typed stores and custom schemas, but without forcing HUF into a fixed schema catalog. 

## 17. Documentation-Aware Upgrades

You asked for documentation-oriented behavior and targeted update capability. This should be built into the design.

Add a documentation-oriented profile:

Recommended profile name: Documentation Memory or Documentation Capture

Purpose:
Capture and maintain structured documentation state from conversations and runs.

Use cases:
 - project requirements
 - architecture notes
 - implementation decisions
 - API contracts
 - status summaries
 - codebase mapping
 - domain glossary

Special behavior:
 - targeted update of an existing memory/document record rather than append-only creation
 - section-aware updates
 - optional merge into Markdown docs
 - optional index emission for search

This allows HUF to evolve data management into not just memory capture, but also structured living documentation.

## 18. Proposed Lifecycle

### Phase 1 lifecycle

Capture → store canonical record → optional index → retrieve

### Phase 2 lifecycle

Capture → compare with prior → merge/supersede → store → optional index → retrieve

### Phase 3 lifecycle

Capture → consolidate → deduplicate → decay/archive → retrieve with profile-aware ranking

This is the area where Hindsight remains ahead today. Hindsight's retain/recall/reflect model gives structured extraction, bank isolation, and an explicit reflect loop. HUF should not integrate Hindsight first, but should leave room for future optional Hindsight-style consolidation if later needed. 

## 19. Recommended MVP Scope

### Build now:
 - rename and elevate data management
 - add Memory Record
 - add Memory Policy
 - add Memory Profile
 - add agent-level memory settings
 - add conversation/run observability
 - support conversation/user/agent/global/custom scope
 - support canonical structured storage
 - support optional FTS and vector indexing
 - support in-prompt and post-run async capture
 - support specialized memory agent
 - ship 3–5 opinionated profiles

### Do later:
 - consolidation engine
 - deduplication
 - expiry/pruning
 - confidence re-ranking
 - "reflect" style synthesis
 - memory health dashboards
 - cross-memory graphing

## 20. UI / UX Changes

### Agent form

Add a new tab or section: Memory

Controls:
 - enable memory
 - choose memory policy
 - choose memory profile
 - choose capture owner
 - choose capture stage
 - choose frequency
 - choose scope defaults
 - choose storage backends
 - choose retrieval mode
 - set budgets and limits

### Conversation UI

Add:
 - mark conversation ended
 - inspect memory produced
 - force capture now
 - see scoped memory attached to conversation

### Memory Explorer

A new desk page or DocType list view to browse and filter memory records by:
 - scope
 - agent
 - user
 - type
 - profile
 - indexed status
 - tags
 - confidence

## 21. Permission and Safety Considerations

Memory introduces privacy and leakage risks. HUF must treat scope and visibility as permission-bearing fields. This is especially important if a record is shared across users, agents, or globally. Existing HUF security patterns such as Password fields for secrets, careful tool permissioning, and explicit agent/document access patterns should be extended to memory records. 

Controls needed:
 - explicit sharing flags
 - permission checks for cross-user or global retrieval
 - audit trail of producer and updater
 - disable indexing for sensitive records
 - ability to delete or expire user-scoped memory

## 22. Why Not Hindsight First

If HUF implements the above, it already owns the essential learning paradigm natively: capture, scope, storage, search, and retrieval. Hindsight still gives richer extraction of facts/entities/relationships, memory-bank semantics, and a dedicated reflect loop, but those are advanced accelerators, not blockers. Hindsight is best considered later if HUF wants to buy speed on higher-order consolidation or more advanced memory reasoning. 

## 23. Final Recommendation

Build this natively in HUF first.

The current HUF architecture already supports the underlying primitives: first-class agents, runs, conversations, optional knowledge, retrieval, triggers, and scoped persistence. The right next move is to turn today's optional "data management" into a first-class Agent Memory subsystem with portable records, flexible scopes, pluggable indexing, configurable capture stages, and opinionated profiles. This will give HUF a product-grade memory/learning layer without introducing an external dependency too early. Hindsight should remain a future optional integration if and when HUF specifically wants a stronger out-of-the-box consolidation/reflect engine. 
