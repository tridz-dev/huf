# HUF Decision Runtime architecture

## Purpose

The Decision Runtime provides provider-neutral, bounded decisions through `select`, `judge`, and `score`. It is distinct from generative Agent execution and deterministic Procedure execution.

## Architectural principles

The Decision Runtime is designed around nine core principles from the Implementation Plan (§3):

**P1 — Provider-neutral vocabulary:** HUF primitives (`select`, `judge`, `score`) map from any backend without exposing backend-specific concepts. Ranked results come from one `select` question over all candidates, not from N `judge` calls. Derived operations (rank, filter, gate) are composed in HUF code.

**P2 — Capability negotiation:** Backends advertise capabilities (`parallel_questions`, `probabilities`, `confidence`, modalities, rate limits, token budgets). Policies declare their requirements. If a backend cannot satisfy a policy, the runtime uses a configured fallback, deterministic fallback, or fails closed; never fakes capabilities.

**P3 — Decision models cannot grant authority:** Results may narrow, rank, classify, reject, or require escalation within supplied candidates. A decision can never add permissions, models, tools, budgets, or Procedures. Probabilistic judgment may tighten authority; it must never widen authority.

**P4 — Minimal state by default:** Only explicitly bound state is sent to backends. Full agent context, conversation history, and tool schemas are not sent by default. State size is validated before dispatch; oversize state raises an error without a network call.

**P5 — Confidence is evidence, not authorization:** Normalized confidence and probabilities are recorded and available to policy code. High confidence does not override rules. Backends without confidence remain usable for policies that do not require it.

**P6 — Fallback is part of each policy:** No global fail-open / fail-closed. Each surface (Tool Suggestion, Model Routing, Flow Router, Agent Routing, Context Compaction, Guardrails, Output Quality) specifies its own sensible fallback behavior.

**P7 — Decision calls are observable first-class executions:** Every decision is persisted with policy/version, surface, backend/provider/model, resolved model version, candidates, normalized answer, probability/confidence, latency, usage, cost, threshold/gate result, fallback taken, parent run, mode, and error category. Full state is not persisted by default; redacted/safe snapshots are used.

**P8 — Throughput and size are first-class budgets:** Decision backends publish rate limits and token budgets. HUF tracks headroom and degrades deliberately (skips the decision, falls back) before limits are hit. State size is validated in HUF before dispatch. Throughput and size are treated as budgets, not error conditions.

**P9 — Modality scope is explicit:** Text-only backends reject non-text input with an error; they do not stringify audio, image, or binary data. Policies declare their input modality requirements.

## Execution boundary

Hard constraints are evaluated before any decision: permissions, allowlists, capabilities, modality, budgets, provider/model availability, and binding constraints. Automatic candidates must come from authoritative resolvers. A result may rank, narrow, classify, reject, or escalate only inside that supplied scope; it cannot add candidates, permissions, models, tools, Agents, or budget.

### Invariant I-DR1 — candidate provenance

**`DecisionRuntime` must never receive candidates directly from Agent configuration, caller input, or any manual-override helper. Every automatic candidate set must be produced by a dedicated eligibility resolver that applies the hard constraint plane first.**

For models, automatic candidates come only from `huf.ai.model_eligibility.get_routeable_models()`. For tools, from `PermissionAwareToolRegistry.get_allowed_tools()`. For skills, Procedures, and Agents, similar resolvers are used. Automatic routing has strictly narrower semantics than human-authorized overrides; the two code paths are kept deliberately separate and enforced by test.

### Procedure boundary

Procedures remain deterministic. No Decision Runtime call belongs inside ProcedureRuntime. `ProcedureRuntime` explicitly guarantees `NO LLM ANYWHERE IN THIS PATH`. Flow `router.decision`, when introduced, will remain distinct from `router.llm` and will block Flow-to-Procedure conversion.

### Decision models are not chat models

A decision model (modality `Decision`) must never be used for generative chat, completion, or creation. Decision-only models are rejected at enforcement points: `_resolve_effective_model`, Agent validate, model picker filters, LiteLLM defaults, and the Hub Orchestrator Agent default model resolver.

## Identity model

Decision model class, family, canonical model/version, provider, deployment, and provider-specific model ID are distinct identities. Policies target a canonical model/family by default. Deployment selection is deterministic; deployment failover preserves the canonical model and is recorded separately from policy fallback.

### Schema: D1-D3 resolution

**D1:** Use the existing `AI Provider` DocType; hard-delete `Decision Provider`.

**D2:** A decision model is an `AI Model` row with modality `Decision`. The `Decision Deployment` references it and reads provider and model_name from it.

**D3:** Adapter (model family semantics) lives on `Decision Model Family.adapter_id` (validated against installed-app registry). Transport (provider-specific wire protocol) lives on `Decision Deployment.wire_protocol` (e.g., `systemone`, `openai_chat_json`). The adapter is independent of the wire protocol.

## Backend contract

The runtime owns policy validation, state minimization, capability checks, gating, fallback, telemetry, and redaction. Backends translate one normalized request (one state, many mixed questions) to/from their engine. Adapters are resolved only from installed-app hook declarations, never from a database-controlled import path.

## State and telemetry

Only explicitly bound minimal state is provider-visible. Execution context is internal metadata. Text-only backends reject non-text modalities instead of stringifying them. Telemetry records normalized answers and usage while avoiding credentials and full sensitive state by default.

## Rollout

Bindings default Off/absent. A deterministic fake backend and conformance contract precede Jev, structured LLM, Playground/Shadow, and any enforcement integration.

---

## Design decisions: D1-D20

All major design decisions for the activation are captured in the Activation Plan §2, with full rationale for each:

| ID | Decision | Summary |
|----|----------|---------|
| D1 | Provider = `AI Provider` | `Decision Provider` DocType hard-deleted. Single provider record owns keys, tier, URL validation. |
| D2 | Model = `AI Model` + modality `Decision` | One identity per provider+model. Deployment reads provider/model_name from AI Model. |
| D3 | Adapter on Family, Transport on Deployment | Adapter (semantics) is a family property; transport (wire protocol) is a deployment property. |
| D4 | Permissions: existing capability system | New capabilities `decision.admin`, `decision.author`, `decision.run` on existing Roles. |
| D5 | Call visibility follows origin | Calls from Agent/Flow/Automation inherit visibility. Owner+admin see Playground/API calls. Raw payload admin-only. |
| D6 | Shadow enqueued, never blocks hot path | Shadow runs async; Enforce runs inline under per-surface latency budget. |
| D7 | Hub Routing on Hub Orchestrator Agent | `decision_bindings` row on the Hub Agent; natural, zero-new-DocType home. |
| D8 | Ingestion vs. query-time filtering | Knowledge Source tags policies; Agent-per-Policy filtering at query time. |
| D9 | `decide` tool advisory only | Bound to one policy; tool supplies candidates; tool output does not narrow LLM choice. |
| D10 | Flow policy pinning per node | Flow Run pins version on first execution; republishing does not change running Flows. |
| D11 | Call vocabulary | Rename `decision_provider` to `resolved_provider`; add origin, mode, automation link. |
| D12 | Kill switch on Agent Settings | `decision_runtime_enabled` default Off; site-wide control. |
| D13 | Automation Decide action | New `action_type = Decision` on Automation; branches decision execution. |
| D14 | Modes are user choices | Off / Shadow / Advise / Enforce freely selectable per binding (Advise where applicable). No trust gates, no mandatory sequence. |
| D15 | Spend counted from start | Decision costs hit spend cap immediately; recorded on every completed call with origin. |
| D16 | Provider tier is data | Cost/limits from AI Model pricing and deployment rate limits; change via edit or add deployment. |
| D17 | `run_decision` normal whitelisted method | Inherits HUF auth; no new scheme, no per-policy keys. |
| D18 | Advise mode: hint only | Inline, under latency budget; clearly labelled data (scores); LLM keeps full choice. Applies to Tool/Skill/Procedure/Agent/RAG selection only. |
| D19 | Help text mandatory | Every field, screen, control, empty state, error has description or inline help. |
| D20 | Fit existing IA; one nav entry | "Decisions" sidebar entry in Build. Models on Providers page. Calls in Executions. Bindings in Agent tabs. Switch in Settings. |
