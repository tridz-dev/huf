# HUF Decision Runtime architecture

## Purpose

The Decision Runtime provides provider-neutral, bounded decisions through `select`, `judge`, and `score`. It is distinct from generative Agent execution and deterministic Procedure execution.

## Execution boundary

Hard constraints are evaluated before any decision: permissions, allowlists, capabilities, modality, budgets, provider/model availability, and binding constraints. Automatic candidates must come from authoritative resolvers. PR 1 carries a typed candidate-source declaration and checks candidate membership, but does not itself prove that the declared source performed authorization; future integration callers must obtain candidates from the corresponding resolver before constructing a request. A result may rank, narrow, classify, reject, or escalate only inside that supplied scope; it cannot add candidates, permissions, models, tools, Agents, or budget.

Procedures remain deterministic. No Decision Runtime call belongs inside ProcedureRuntime. Flow `router.decision`, when introduced later, will remain distinct from `router.llm` and will block Flow-to-Procedure conversion.

## Identity model

Decision model class, family, canonical model/version, provider, deployment, and provider-specific model ID are distinct identities. Policies target a canonical model/family by default. Deployment selection is deterministic; deployment failover preserves the canonical model and is recorded separately from policy fallback.

## Backend contract

The runtime owns policy validation, state minimization, capability checks, gating, fallback, telemetry, and redaction. Backends translate one normalized request (one state, many mixed questions) to/from their engine. Adapters are resolved only from installed-app hook declarations, never from a database-controlled import path.

## State and telemetry

Only explicitly bound minimal state is provider-visible. Execution context is internal metadata. Text-only backends reject non-text modalities instead of stringifying them. Telemetry records normalized answers and usage while avoiding credentials and full sensitive state by default.

## Rollout

Bindings default Off/absent. A deterministic fake backend and conformance contract precede Jev, structured LLM, Playground/Shadow, and any enforcement integration.
