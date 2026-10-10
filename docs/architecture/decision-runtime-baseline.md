# Decision Runtime baseline findings

**Date:** 2026-09-22
**Repository:** `/Users/safwan/Code/Huf/huf-worktrees/decision-runtime-pr1`
**Base branch/head:** `origin/pre-develop` at `43b69a0c6373d78e24b814be8ad546cfb250a4c3`
**Feature branch:** `codex/decision-runtime-pr1`

## Branch and worktree

- `origin/pre-develop` exists and matches the workplan's verified head.
- The local `pre-develop` branch is stale at `fd64de37ac9a8cc537a7f042ca5d58b1a4644733`; implementation therefore uses a new clean worktree from `origin/pre-develop`.
- The main checkout is on `night-mode-token-fixes` with unrelated untracked work and was left untouched.
- Existing graphify checkout is detached at the older plan baseline `c21cd526814a862675a83674eec63a626272680b` and has unrelated untracked output; it was left untouched.

## Integration invariants confirmed

- Generative execution lives in `huf/ai/run.py`; this PR must not add Jev to it or LiteLLM completion semantics.
- Agent override/allowlist handling exists in `huf/ai/agent_integration.py`; automatic eligibility resolver is not present yet and remains a later phase.
- `huf/ai/run_budget.py` exists and remains authoritative; PR 1 adds no routing integration.
- `huf/ai/flow_engine.py` contains `router.llm`; conversion blockers in `procedure_conversion.py` currently include `agent.run`, `router.llm`, and `human.approval`.
- `huf/ai/graph/procedure_runtime.py` documents “NO LLM ANYWHERE IN THIS PATH” and has a closed procedure node tuple; leave it untouched.
- `huf/ai/tools/lazy_discovery.py` calls `PermissionAwareToolRegistry.get_allowed_tools()` and re-resolves bound Procedures before exposing details.
- `AI Provider` currently owns URL validation in `huf/huf/doctype/ai_provider/ai_provider.py`; existing coverage is in `huf/ai/tests/test_ai_provider_validation.py`. The helper extraction must preserve current localhost/private IP/HTTPS behavior.
- `huf/hooks.py` has no decision backend registry hook. Add only an installed-app registration hook; never import DB-supplied paths.
- `pyproject.toml` targets Python 3.10 and uses Ruff; core types can use frozen dataclasses and stdlib types.

## Scope decisions

- PR 1 contains architecture/contract, fake backend, runtime foundation, conformance suite, telemetry/cost interfaces, and shared provider URL security only.
- DocTypes, Jev/OpenCode integration, structured LLM backend, live probes, Playground, Shadow bindings, Flow, Agent/model routing, and selectors remain later PRs.
- Amendment 01 is authoritative: canonical model identity and provider/deployment identity remain separate in core types and telemetry.
