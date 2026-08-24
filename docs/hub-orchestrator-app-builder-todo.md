# Hub Orchestrator App Builder — Dependency-Mapped TODO / Tracker

Tracks implementation of `docs/hub-orchestrator-unified-builder-plan.md` (see that file for full
architecture/rationale — this file is the live, per-round status tracker only).

Base branch: `pre-develop` (per final PR target). Implementation branch:
`feat/hub-orchestrator-app-builder`. Huf workspace track: `TRK-20260824-90b1`
(`safwan-erooth.HubOrchestratorAppBuilder` in `huf_workspace_v2`).

**Decision log**:
- 2026-08-24: Building on `pre-develop`, not `pre-dev` — `pre-develop` is a strict superset of
  `pre-dev` (0 commits behind it) and already includes PRs #640/#641. Final PR target per
  instruction is `pre-develop`.
- 2026-08-24 (corrected): PR #596 (`feature/app-capability-discovery`) is **already merged and
  present in `pre-dev`, `pre-develop`, `develop`, and `pre-dev-stg`** — an earlier check searched
  for the wrong module path (`huf/ai/capabilities/`) and missed that a later commit renamed it to
  `huf/ai/capability_discovery/` (13 files, confirmed present in this branch's base). No sync or
  cherry-pick is needed. Its `apps_loader.py` extensions (DocType-ownership-via-Module-Def helper)
  and any `_registry.py` insertions are already live in this worktree's starting state — Phase 2/3a
  agents read the actual current files, so this should already be reconciled, but re-verify with a
  diff review before assuming zero collision.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked/deferred

---

## Phase 1 — Target architecture/ADR
Depends on: none (base audit already done, see the plan doc §A-C)
- [x] Decide: one generic Agent-backed App runtime (plan's D recommendation) — confirm/record
- [x] Finalize `HUF App` field additions (plan §D.5): `agent`, `is_public`, `alias`,
      `icon_source`, `capabilities`
- See `docs/adr/0001-app-runtime-model.md` for the recorded runtime and capability-ownership decisions.

## Phase 2 — App domain service operations
Depends on: Phase 1
- [x] `create_app_from_agent()` in `huf/ai/app_seeding/apps_loader.py`
- [x] `update_app()` in `huf/ai/app_seeding/apps_loader.py`
- [x] `install_app()` (idempotent) in `huf/ai/app_seeding/apps_loader.py`
- [x] Unit tests for the above (`huf/ai/app_seeding/tests/test_app_creation.py`, follows
      `test_apps_sync.py` conventions; not executed against a live bench — see commit note)

## Phase 3a — Hub App builder tools (discovery + two-phase CRUD)
Depends on: Phase 2
- [x] `list_agents`, `get_agent`, `list_apps`, `get_app` (read-only, no confirm)
- [x] `draft_app`, `update_app`, `install_app` (two-phase confirm, mirrors
      `huf/ai/tools/builder.py`'s existing contract)
- [x] `set_app_icon` (two-phase confirm) — Phase 7
- [x] Register in `BUILDER_TOOL_NAMES` / `huf/ai/tools/_registry.py`
- [x] `huf/ai/tests/test_app_builder_tools.py` — capability-gating + preview/confirm tests

## Phase 3b — Design-system Skill self-seed + deterministic render tool
Depends on: Phase 1 (independent of 3a)
- [x] `list_app_components` (read-only) + `render_app_component` (two-phase) in
      `huf/ai/tools/render_tools.py`, escaping via the existing `_escape_jsx_attr` helper
- [x] `huf/ai/app_seeding/design_system_skill.py` — idempotent self-seed, mirrors
      `hub_orchestrator.py`'s shape
- [x] Seed content: no separate versioned JSON file — the Skill's `instructions`
      (short, token-cheap prose) and the component allowlist
      (`APP_COMPONENT_ALLOWLIST` in `render_tools.py`, served on demand via
      `list_app_components`) are defined inline, per D.3's "or reuse the Skill
      shape" alternative — no `huf/huf/skills/` or `huf/huf/knowledge/` file needed
- [x] Wire into `huf/install.py` after_install/after_migrate, right after
      `create_hub_orchestrator_agent()`
- [x] Test: `huf/ai/tests/test_design_system_tools.py` — non-empty component list,
      unknown-component rejection, double-quote prop escaping regression

## Phase 7 — Icon pipeline
Depends on: Phase 1 (independent of 2/3a/3b — can build in parallel)
- [x] `set_app_icon` source handling: existing path / uploaded (reuse `agent_chat.py` upload
      conventions) / generated (reuse `handle_generate_image`)
- [x] MIME/SVG-sanitization check for icon uploads (gap noted in plan §F)

## Phase 4 — Agent → App workflow (Path A/B/C)
Depends on: Phase 2, 3a
- [ ] `draft_app` accepts existing OR freshly-drafted Agent
- [ ] Conversation-context resolution ("make that an App") via `Agent Conversation.conversation_data`

## Phase 5 — Unified chatbot App
Depends on: Phase 4
- [ ] Verify existing chat runtime works unmodified via an App's `route` once `HUF App.agent` exists

## Phase 6 — Installation + launcher integration
Depends on: Phase 4
- [ ] `install_app` idempotency verified (re-run doesn't duplicate)

## Phase 8 — Audio input, transcription, OCR App config
Depends on: Phase 5
- [ ] Surface existing `Agent.allow_file_upload`/STT/`enable_ocr` as App `capabilities` flags

## Phase 9 — Audio generation/TTS App config
Depends on: Phase 8
- [ ] Surface `Agent.tts_model`/`tts_voice` as App `capabilities` flags

## Phase 9b — Public/guest App routing
Depends on: Phase 6
- [ ] `is_public`/`alias` fields, `website_route_rules` entry, guest resolver reusing
      `check_agent_access(agent_doc, user="Guest")`

## Phase 10 — Video playback/output (largest net-new backend work)
Depends on: Phase 9
- [ ] `handle_generate_video` (currently absent) — scope realistically, mark deferred if a
      provider/model contract can't be established in this pass

## Phase 11 — Live voice App config
Depends on: Phase 9
- [ ] Surface `huf/ai/voice/` engine selection at App layer; document known gaps, don't paper over

## Phase 12 — removed (OTR was a typo for OCR; already covered by Phase 8)

## Phase 13 — Hardening
Depends on: whichever of 2-11/9b shipped
- [ ] Permission re-audit, idempotency re-verification, observability check

## Phase 14 — End-to-end testing + documentation + draft PR
Depends on: Phase 13
- [ ] Full Path A/B/C walkthrough
- [ ] Push draft PR against `pre-develop` with screenshots where possible
