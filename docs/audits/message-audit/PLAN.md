# PLAN — MessageAudit: incremental unification

Derived from [`FINDINGS.md`](FINDINGS.md) (MA-01…MA-25) and the structural
observation this track verified (STATE.md §11). Guiding rule from the observation:
**unify semantics before any new language/rewrite** — otherwise the three execution
vocabularies, the 3× tool-data duplication, and the phantom policy enum are
preserved at higher cost.

Each phase is independently shippable, ordered by risk (no schema change → additive
→ structural). Every task lists: findings addressed, files touched, and the check
that proves it done. Base branch for implementation: `develop` (per workspace
branch topology), in a worktree inside this track.

---

## Phase 0 — Baseline (docs, this track) ✅

- [x] STATE.md / FINDINGS.md / PLAN.md written, cited at `eebb9dc`.
- [ ] File GitHub issues for MA items (needs owner go-ahead — outward action).
- [ ] Owner review: pick which "decide" tasks (P2.1–P2.3) land as designed.

## Phase 1 — Stop the bleeding (bug fixes, no schema change)

Small, reviewable PRs; each behind the existing test suite + one new test.

| # | Task | Findings | Files | Done when |
|---|---|---|---|---|
| 1.1 | Harden or remove `agent_chat.add_message`: add conversation-ownership check (mirror `get_message_permission_conditions`) + restrict `role` to `user`/`system`-with-capability; or delete the endpoint (zero in-repo callers) | MA-12 | `ai/agent_chat.py:873-923` | API returns 403 for non-owner; legit callers unaffected; test added |
| 1.2 | Fix stream token undercount: accumulate `stream_usage` across tool rounds instead of resetting | MA-09 | `ai/providers/litellm.py:975,984-989,1238-1255` | streaming run with tool calls records total tokens == sum of rounds; sync/stream parity test |
| 1.3 | Make ATC `Failed` real: pass `error=` from exception paths, stop storing exceptions as `Completed`; surface error to the message row | MA-08, MA-10(b) | `ai/agent_integration.py:397-485`, `ai/providers/litellm.py:1080-1102` | a raising tool produces ATC `Failed` + `error_message`; message/socket show failure |
| 1.4 | Put index assignment behind the per-conversation lock (align with queue-first) or add `UNIQUE(conversation, conversation_index)`; dedupe the 3 MAX+1 copies (~~user-field precedence fix~~ — MA-14 withdrawn, no bug) | MA-11 | `ai/conversation_manager.py:420-448`, `ai/sdk_tools.py:1539-1550,2154-2166,2468-2475` | no duplicate indices under concurrent inserts (test) |
| 1.5 | Kill `tool_status` staleness: drop the three `fetch_from` fields, read `tool_name/args/status` via the `tool_call` link at read time (report/API projection) | MA-10 | `agent_message.json`, `chatApi.ts:305-306`, desk list views | UI shows live ATC status; no fetch copies in schema |
| 1.6 | Quiet routine repairs: log repairs at debug level (or count-only), not Error Log | MA-15 | `ai/conversation_manager.py:312-319` | routine trims produce no Error Log rows |
| 1.7 | ElevenLabs drift: `total_cost`→`cost`; stop rewriting `creation` | MA-16 | `ai/providers/elevenlabs_convai_api.py:186-237` | voice runs record cost; message timestamps immutable |

## Phase 2 — Truthful context semantics (additive schema evolution)

Principle: the enum must only contain behaviors that exist. Introduce new behavior
**or** remove the option — never keep a label without semantics.

| # | Task | Findings | Decision needed |
|---|---|---|---|
| 2.1 | Collapse the policy enum to implemented behaviors: `include_full`, `include_summary`, `include_reference`, `exclude`. Data patch mapping `token_budgeted`→`include_summary`, `provider_cached`→`include_full`, `transient_only`→`exclude`; remove the aliases from options | MA-03 | none (mechanical) |
| 2.2 | `include_on_demand`: either implement discovery (emit a handle like `include_reference` but withhold content until `get_result_context` fetches it) or drop the option | MA-03 | owner pick — recommend **implement via handle** (unifies with 2.5) |
| 2.3 | `token_estimate` + `token_budgeted`: either implement real budgeting (estimate at write time via chars/4 heuristic or tokenizer; enforce a per-conversation token budget in `get_conversation_history` using estimates) or drop field + policy | MA-02 | owner pick — recommend **implement** (it's the only token-aware knob; aligns with queue-first cost work) |
| 2.4 | `visibility`: either enforce (extend `get_message_permission_conditions` + history filter so `ui_only` never enters model context and `audit_only` never leaves the backend) or drop the field | MA-01 | owner pick — recommend **enforce minimally**: `model_visible` vs `ui_only` split is genuinely useful for status/debug rows |
| 2.5 | Generalize `get_result_context` to any `include_reference` handle (today: ATC + Context Artifact only) and add a backend creation path for Agent Context Artifacts | MA-07, B-01/#365 | none — completes the designed loop |
| 2.6 | Merge `kind`/`record_kind` into one canonical `record_kind` (superset vocabulary), data patch `kind`→`record_kind`, switch readers, deprecate then remove `kind` | MA-04, MA-05 | naming ratification (GLOSSARY update) |
| 2.7 | Real summaries: replace 200-char truncation with the existing summarization machinery (`run_background_summarization`) for `include_summary` rows; hard-fail (not silent full-include) when summary missing | MA-05 | perf note: summarization is a background job today |

Validation per task: extend `ai/tests/test_context_policy.py` (it already pins the
real behaviors) + add policy-matrix tests for every enum value (the currently
untested ones are exactly the phantom ones — STATE §8).

## Phase 3 — Unify the execution records (structural; the observation's core)

| # | Task | Findings | Notes |
|---|---|---|---|
| 3.1 | Write **Execution Semantics ADR** (follow CodeDiscovery ADR format): one canonical execution = **Agent Run**; Orchestration and Flow Run become *coordination metadata* over runs, not parallel state machines. Define the status-vocabulary mapping (Queued/Started/Success/Failed as canonical; flow Waiting Approval/Waiting User as substates) | MA-21, MA-23 | owner sign-off — this is the hard-to-reverse call; candidate ADR 0003 |
| 3.2 | Flow `tool.call` produces a real **Agent Tool Call** (structured tool/args/result/call_id/conversation), keeping the audit run only if still needed | MA-21, B-04/#368 | removes the last non-ATC tool path |
| 3.3 | Single token/cost aggregation: run-level write stays; conversation totals become derived (sum over runs) or transactional — no fire-and-forget SQL | MA-17 | after 1.2 (streaming totals fixed first) |
| 3.4 | Unified read API + timeline UI: one endpoint returning runs (all kinds) with linkage; Executions page + flow sheets + orchestration card consume it | MA-21, MA-23 | frontend after backend API lands |
| 3.5 | Retire dead statuses (`Waiting User`, `Paused`, ATC `Started`, message `Queues`→`Queued` backport) and lowercase plan-step vocabulary | MA-24, C-01/#373 | mechanical after 3.1 mapping |

## Phase 4 — Message ↔ Tool Call unification (after 1–3)

| # | Task | Findings | Notes |
|---|---|---|---|
| 4.1 | Agent Message tool rows become **pure projections** of ATC: no `fetch_from` copies (done in 1.5), no `tool_call_id`/`tool_calls` duplication — history expansion always resolves via the link (the code paths already exist and are used as fallbacks today) | MA-18, MA-19, MA-20 | the repair patch proves this direction is safe |
| 4.2 | Collapse to **one persisted tool shape** (assistant declaration row + linked ATC holding result); migration for the three legacy shapes using the existing patch + `_synthesize_assistant_tool_call` logic | MA-18, MA-13 | biggest data migration; dry-run on a bench copy first |
| 4.3 | Separate presentation from context: UI renders from ATC+message projection; `content` stops being mutated in place (Tool Call row stays a call; result lives on ATC; the model view is assembled, not stored) | MA-19, MA-13 | completes the two-masters decoupling |

## Cross-track dependencies

- **QueueFirstRuns**: queue-first's per-conversation lock is the natural home for
  1.4; land that branch or cherry-pick the lock first.
- **CommitAudit**: Phases 1–2 touch commit-adjacent paths — follow its
  `safe_commit` guidance, don't reintroduce raw commits.
- **CodeDiscovery**: ADR 0003 (3.1) and GLOSSARY updates (2.6) belong to its
  domain-model governance; file issues in its numbering style.

## Incremental context-building (how to execute)

1. Land Phase 1 PRs individually (each is a few files, each verifiable on bench 16).
2. Re-run this track's sweeps after Phase 1 to re-baseline STATE.md (fields that
   became live/dead).
3. Take Phase 2 decisions to the owner in one grill session (precedent:
   CodeDiscovery GRILL-LOG), then implement.
4. Phases 3–4 each get their own track registered via `tools/ws track-add` when
   started (3 → e.g. `ExecutionUnify`, 4 → e.g. `MessageUnify`).
