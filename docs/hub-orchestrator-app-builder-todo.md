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

- 2026-08-24: **Round 1 (Phases 1/2/3a/3b/7) verified against a real disposable bench**, not just
  `py_compile`. Bench `hub-orchestrator-app-builder` provisioned via `frappe-multihand` skill
  (`--app huf --branch feat/hub-orchestrator-app-builder --blank`, port 8088) on
  `frappe_docker_devcontainer-frappe-1`. Found and fixed one real bug `py_compile` couldn't catch:
  the Phase 2 test fixture's minimal `Agent` doc was missing `instructions` (required by
  `Agent._validate_prompt()` when `prompt_mode=Local`, the default) and included a nonexistent
  `title` field — fixed in `huf/ai/app_seeding/tests/test_app_creation.py` (commit `63b0b581`).
  After the fix: `test_app_creation.py` 4/4 pass, `test_app_builder_tools.py` 19/19 pass,
  `test_design_system_tools.py` 8/8 pass, pre-existing `test_builder_tools.py` regression suite
  71/71 still pass (zero regressions). End-to-end seed verification via `bench execute`: Hub
  Orchestrator agent has all 22 expected tools attached (12 original + 10 new), and the "HUF
  Design System Reference" Skill exists and is attached to its `agent_skill` table. Bench left
  running (not torn down) at `http://localhost:8088` (site `hub-orchestrator-app-builder.local`,
  admin/admin) for continued verification in later rounds — see
  `/workspace/benches/hub-orchestrator-app-builder/BENCH_IDENTITY.md` inside the container.

- 2026-08-24: **Round 2 (Phases 4/5/6/9b) verified against the same real bench.** Found and fixed
  two real bugs `py_compile` couldn't catch:
  1. `bench migrate` hard-failed every time — `huf.ai.skills.hooks.sync_app_skills` (pre-existing
     mechanism, runs on every `after_migrate`) treats any `source_type="App Provided"` Skill not
     declared via the `huf_skills` hook as orphaned and deletes it; our self-seeded Design System
     Skill was created directly, bypassing that declaration, so it was swept up every migrate
     (deletion correctly failed since it's attached to Hub Orchestrator, but the failure-logging
     path hit an unrelated `frappe.log_error` title-length bug that turned it into a hard migrate
     failure). Fixed by declaring the skill via a `huf_skills` hook entry + `get_skill_manifest()`
     (commit `04c6c91b`) — the same mechanism every other app already uses.
  2. `test_install_app_idempotent_across_preview_and_confirm_branches` (Phase 6) failed —
     `create_app_from_agent`/`validate_manifest` already default a new App to `enabled=1` (existing
     `apps_loader.py` convention), so the test's assumption that a freshly-drafted app starts
     uninstalled was wrong. Fixed the test to explicitly disable before testing the not-yet-installed
     preview branch, mirroring `test_app_creation.py`'s existing convention (commit `1ea5ac9e`).

  After both fixes: `bench migrate` clean, and full sweep — `test_app_creation.py` 4/4,
  `test_app_builder_tools.py` 24/24, `test_design_system_tools.py` 8/8,
  `test_app_public_renderer.py` 6/6, pre-existing `test_builder_tools.py` 71/71 — all pass, zero
  regressions (113 tests total). Also confirmed via `bench execute`: the Design System Skill
  survives `bench migrate` and stays attached to Hub Orchestrator; `HUF App` DocType now has
  `agent`/`is_public`/`alias`/`icon_source`/`capabilities` fields (verified via `meta.has_field`).

  **Two pre-existing test suites (NOT ours, NOT regressions we caused) also fail on this bench**:
  `test_lazy_tool_discovery.py` (1 failure, PR #640) and `test_render_tools.py`'s
  `TestPromptInstructionSelection` (2 errors, PR #641 — its own PR description explicitly flags
  this exact test as needing "a real bench run" with a configured AI Provider/Model, which this
  `--blank` bench doesn't have). Confirmed not caused by this branch: `git diff --stat
  origin/pre-develop HEAD -- huf/ai/tools/_registry.py huf/ai/sdk_tools.py huf/ai/tool_registry.py
  huf/ai/tools/lazy_discovery.py` shows only `_registry.py` touched, purely additive (0 deletions)
  — this branch never modifies the tool-eligibility/eager-set code path those tests exercise.
  Out of scope for this track; noted here so it isn't mistaken for something we broke.

- 2026-08-24: **Round 3 (Phases 8/9) verified against the same real bench.** No DocType schema
  changes this round, so no `bench migrate` needed. `validate_app_capabilities()` added to
  `apps_loader.py` (file_upload→`allow_file_upload`, ocr→`enable_ocr`, audio_input→`stt_model`,
  audio_output→`tts_model`), wired into `update_app()`, enforcing the ADR's "App capabilities must
  be a subset of Agent capabilities" invariant server-side. `test_app_creation.py` 8/8 pass
  (4 original + 4 new), `test_app_builder_tools.py` 24/24, `test_builder_tools.py` 71/71 — zero
  regressions. One open note from the implementing agent: `draft_app` does not yet call
  `validate_app_capabilities` (only `update_app` does) — the ADR's language covers both, but the
  task scope named only `update_app`; since `draft_app` doesn't currently accept a `capabilities`
  kwarg at all (checked: it doesn't), this isn't a live gap yet, but flag it if `draft_app` grows
  that parameter later.

- 2026-08-24: **Round 4 (Phases 10/11) verified against the same real bench — found round 2's
  migrate-fix was itself incomplete.** `bench migrate` hard-failed again with the *exact same*
  orphan-skill-deletion error as round 2, despite the `huf_skills` hook fix from commit `04c6c91b`.
  Root cause (a real, pre-existing bug in `sync_app_skills`'s caching, not something introduced by
  us): its per-app scan cache (keyed on `hooks.py` mtime) can legitimately skip re-scanning an app
  whose declarations haven't changed since the last scan — but the orphan-cleanup pass (full scan
  mode) only builds its "still valid" set from apps *actually rescanned this pass*, so a cache-skip
  gets misread as "no longer declared" and the skill gets swept for deletion anyway, on a schedule
  that depends on cache timing rather than anything we control. **Real fix (commit `0ac1c702`)**:
  stop using `source_type: "App Provided"` for the self-seeded skill entirely — switched to
  `source_type: "Local"` (the DocType's own default value, and semantically accurate: this skill is
  directly authored, not hook-discovered), which sidesteps the orphan-cleanup subsystem completely
  regardless of caching behavior. Removed the now-unnecessary `huf_skills` hook entry and
  `get_skill_manifest()`. Verified stable across **two consecutive** `bench migrate` runs (the
  round-2 fix looked fine on the first migrate too — it only broke on a later one — so a single
  clean migrate is not sufficient evidence here). Full sweep after the fix: `test_app_creation.py`
  10/10, `test_app_builder_tools.py` 24/24, `test_design_system_tools.py` 8/8,
  `test_app_public_renderer.py` 6/6, `test_media_handlers.py` 4/4 (new), `test_builder_tools.py`
  71/71 — 123 tests total, zero regressions. Hub Orchestrator now has 23 tools (added
  `resolve_recent_resource` from Phase 4) and the Skill remains attached with `source_type: Local`.

  **Phase 10 status is honestly partial, not "done" in the working-feature sense**: `AI Model`
  gained a `Video` modality option and `handle_generate_video()` exists with full fail-closed
  validation (no Video-modality model configured → clear error), but the actual generation call is
  a documented `NotImplementedError` — confirmed via direct introspection that the installed
  `litellm==1.95.0` has no video-generation entry point at all (unlike `image_generation`). Also:
  `Agent` DocType has no video-generation-model field (no analogue to `image_generation_model`/
  `tts_model`), so `validate_app_capabilities`'s `video_output` check unconditionally rejects the
  capability with an explanatory error — a real, deliberately-not-silently-worked-around gap.
  Phase 11 (live voice) stayed correctly scoped to config-surfacing: `live_voice` capability
  validation (`voice_enabled` + `voice_engine` required) plus a new non-blocking `warnings` list on
  `update_app`'s return value (e.g. flagging the real, documented lack of Agent-memory injection in
  `huf/ai/voice/README.md`) — upstream voice-engine gaps were not silently papered over.

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
- [x] `draft_app` accepts existing OR freshly-drafted Agent
- [x] Conversation-context resolution ("make that an App") via `Agent Conversation.conversation_data`
      — implemented as `resolve_recent_resource(resource_type, conversation_id=None)` in
      `huf/ai/tools/builder.py`, backed by a new `conversation_data["_recent_resources"]`
      list (newest-first, capped at 10) that `draft_agent`/`draft_app` append to on a
      confirmed (`confirm=True`) creation.

      Conversation-context mechanism used: no existing builder tool in `builder.py`
      received `conversation_id` as a parameter, but `huf.ai.tools.lazy_discovery.handle_load_tools`
      and `huf.ai.sdk_tools._merge_run_context` already establish the pattern —
      `_merge_run_context` auto-injects `conversation_id` (and `agent_run_id`,
      `agent_name`) from the huf run context dict into a tool's call args via
      setdefault-like semantics (LLM-supplied values win; blank/missing ones are
      filled from context), *provided the tool function declares that parameter*.
      `draft_agent` and `draft_app` did not previously declare `conversation_id`, so
      this round added `conversation_id: str | None = None` to both signatures — this
      is the same mechanism `lazy_discovery.handle_load_tools` relies on via `**kwargs`,
      just declared explicitly instead of caught by `**kwargs`. No new plumbing was
      invented. `resolve_recent_resource` also takes `conversation_id` for the same
      reason and is NOT listed as a model-facing parameter in `_registry.py` (matching
      how `draft_agent`/`draft_app` already omit it), so it is only ever populated by
      the auto-injection path, never guessed by the model.

## Phase 5 — Unified chatbot App
Depends on: Phase 4
- [x] Verify existing chat runtime works unmodified via an App's `route` once `HUF App.agent` exists
      (`docs/verification/phase5-chatbot-app.md` confirms: agent field added to DocType, run_agent_sync takes agent_name parameter, zero chat-code changes required)

## Phase 6 — Installation + launcher integration
Depends on: Phase 4
- [x] `install_app` idempotency verified (re-run doesn't duplicate) — tool-layer regression test added to `huf/ai/tests/test_app_builder_tools.py:test_install_app_idempotent_across_preview_and_confirm_branches`

## Phase 8 — Audio input, transcription, OCR App config
Depends on: Phase 5
- [x] Surface existing `Agent.allow_file_upload`/STT/`enable_ocr` as App `capabilities` flags
      (`validate_app_capabilities()` in `huf/ai/app_seeding/apps_loader.py`, wired into
      `update_app()`; checks `file_upload` against `Agent.allow_file_upload`, `ocr` against
      `Agent.enable_ocr`, `audio_input` against `Agent.stt_model`; enforces the subset
      invariant server-side before saving; tests in
      `huf/ai/app_seeding/tests/test_app_creation.py`)

## Phase 9 — Audio generation/TTS App config
Depends on: Phase 8
- [x] Surface `Agent.tts_model`/`tts_voice` as App `capabilities` flags
      (`validate_app_capabilities()` in `huf/ai/app_seeding/apps_loader.py` now also checks
      `audio_output` against `Agent.tts_model`; enforced server-side in `update_app()`; tests
      in `huf/ai/app_seeding/tests/test_app_creation.py`)

## Phase 9b — Public/guest App routing
Depends on: Phase 6
- [x] `is_public`/`alias` fields, `website_route_rules` entry, guest resolver reusing
      `check_agent_access(agent_doc, user="Guest")`
      (`huf/ai/app_public_renderer.py:HufAppPublicRenderer`, `/huf/apps/<path:app_alias>`
      route + `page_renderer` entry in `huf/hooks.py`; anti-enumeration — not-public,
      disabled, and public-but-guest-denied all raise the same
      `frappe.PageDoesNotExistError`; tests in `huf/ai/tests/test_app_public_renderer.py`)

## Phase 10 — Video playback/output (largest net-new backend work)
Depends on: Phase 9
- [x] `handle_generate_video` — PARTIALLY DONE, HONESTLY SCOPED, NOT FULLY WORKING:
      confirmed litellm==1.95.0 (installed/pinned version) has no generic
      `video_generation()`-style call (unlike `image_generation`); no provider/model
      contract could be established in this pass, so per the plan's own instruction
      this was deferred rather than faked. What actually shipped:
      `huf/ai/handlers/media.py::handle_generate_video` implements the full
      model-resolution/validation scaffolding (mirrors `handle_generate_image`'s
      shape, fails closed with a clear error if no Video-modality AI Model is
      configured) but the actual provider call raises `NotImplementedError` with an
      explanatory message — it does NOT generate video. `Video` added to
      `AI Model.modalities` options
      (`huf/huf/doctype/ai_model/ai_model.json`). `validate_app_capabilities`
      (`huf/ai/app_seeding/apps_loader.py`) now rejects `video_output` capability
      unconditionally with an explanatory error, because Agent DocType has **no**
      video-generation-model field yet (no analogue to `image_generation_model`/
      `tts_model` — checked `huf/huf/doctype/agent/agent.json`, field does not
      exist). Adding that field is a real prerequisite for Phase 10 to be
      considered complete; not done here to avoid inventing a field ahead of other
      in-flight work. Tests: `huf/ai/tests/test_media_handlers.py` (fail-closed
      paths only; no test asserts successful generation, since none happens).

## Phase 11 — Live voice App config
Depends on: Phase 9
- [x] Surface `huf/ai/voice/` engine selection at App layer; document known gaps, don't paper over.
      Scope note: this phase is App-level config surfacing only, not new voice-engine
      implementation -- the underlying gaps in `huf/ai/voice/` are pre-existing and out of
      scope for this track. `validate_app_capabilities` (`huf/ai/app_seeding/apps_loader.py`)
      now rejects `live_voice` capability with a clear error unless the linked Agent has both
      `voice_enabled` (Check) truthy and `voice_engine` (Select) set (confirmed exact
      fieldnames from `huf/huf/doctype/agent/agent.json`). This does **not** claim full
      live-voice support: it only validates that the Agent is minimally configured to attempt
      a voice session, not that the session will behave fully. `update_app` had no existing
      mechanism for non-blocking, informational issues distinct from hard validation errors, so
      one was added: a new `collect_app_capability_warnings()` helper (same
      dict-of-strings-in/list-of-strings-out shape as `validate_app_capabilities`) resolves the
      Agent's configured voice engine via `huf.ai.voice.get_engine_class` and checks its
      `capabilities()` (`huf/ai/voice/engines/base.py`); if `memory` is `False`, `update_app`'s
      returned dict now carries a `warnings` list (separate from the errors that `frappe.throw`
      already blocks the save on) noting the gap, but the save still succeeds.
      **Known upstream gaps restated here as App-level caveats** (not fixed by this phase,
      per `huf/ai/voice/README.md`'s "Known gaps" and plan section A.4/I): an App exposing
      `live_voice` inherits all of these limitations from the underlying engine, unchanged —
      (1) `send_to_session` is unimplemented on both shipped engines (ElevenLabs,
      litellm_realtime) — always raises; a live-voice App cannot inject text/tool-result content
      into an in-progress call. (2) `litellm_realtime` never persists the user's spoken turns —
      only agent-spoken text is captured (best-effort, via `response.audio_transcript.done`
      frames); a live-voice App's conversation history is agent-only, not a full transcript.
      (3) ElevenLabs persistence depends entirely on its post-call webhook firing; if it doesn't
      (unreachable site, misconfiguration), that call persists nothing, with no fallback path.
      (4) Neither engine injects Agent memory into a live session (`memory: False` on both,
      confirmed via each engine's `capabilities()`) — this is the one gap this phase actively
      surfaces as a non-blocking `update_app` warning rather than only documenting in prose.
      Tests: `huf/ai/app_seeding/tests/test_app_creation.py` —
      `test_update_app_rejects_live_voice_capability_without_agent_voice_enabled`,
      `test_update_app_accepts_live_voice_capability_and_warns_about_memory_gap` (uses the real
      built-in `litellm_realtime` engine key, no bench-external dependency needed).

## Phase 12 — removed (OTR was a typo for OCR; already covered by Phase 8)

## Phase 13 — Hardening
Depends on: whichever of 2-11/9b shipped
- [ ] Permission re-audit, idempotency re-verification, observability check

## Phase 14 — End-to-end testing + documentation + draft PR
Depends on: Phase 13
- [ ] Full Path A/B/C walkthrough
- [ ] Push draft PR against `pre-develop` with screenshots where possible
