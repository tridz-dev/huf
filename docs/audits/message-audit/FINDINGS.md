# FINDINGS — MessageAudit register

Gaps / locks / traps / issues in Agent Message context semantics and the execution
records, consolidated from STATE.md (evidence cited there). Base: `origin/develop` @ `2c3fd73c`.
Categories: **G** = gap (missing/broken behavior), **L** = lock (coupling that
constrains change), **T** = trap (misleads a rewrite/new-language effort),
**I** = issue (outright bug). Severity: Critical / High / Medium / Low.
Cross-refs: CodeDiscovery FINDINGS IDs (A-*, B-*, C-*, D-*) and their GitHub issues.

## G. Gaps — missing or broken behavior

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| MA-01 | High | `visibility` is a **dead field**: no reader anywhere (not history assembly, not permission hooks, not UI); options `ui_only/audit_only/model_visible/developer_only` are dead values. Messages carry a security-looking label that enforces nothing | STATE §3, §3.4 |
| MA-02 | Medium | `token_estimate` is a **dead field**: no reader anywhere; the `token_budgeted` policy that should consume it ignores it | STATE §3 |
| MA-03 | High | **Policy enum is mostly phantom**: `token_budgeted`→alias of `include_summary`; `provider_cached`→alias of `include_full`; `transient_only`→alias of `exclude`; `include_on_demand`→drops content leaving no discovery handle. Only `include_full`/`include_reference` are ever written by app code | STATE §2.1, §4 |
| MA-04 | Medium | `record_kind` near-dead: 9 of 10 values never written; read only as a label in `include_reference` handles | STATE §3, §5 |
| MA-05 | Medium | `include_summary` silently falls back to full content when no summary exists (cost-inflating no-op); `context_summary` is a 200-char truncation, never a real summary | STATE §2.1, §3 |
| MA-06 | Low | No writers at all for `status`, `content_type`, `generated_video` (schema declares, nothing produces) | STATE §4 |
| MA-07 | High | Agent Context Artifact has **no creation path** (CodeDiscovery B-01 / issue #365 re-confirmed): artifact-typed `record_kind` values and artifact `context_policy` are unreachable; `include_reference` handles only ever point at Agent Tool Call | STATE §3, C2 |
| MA-08 | Medium | ATC status semantics broken: `"Started"` never written (joins CodeDiscovery C-01 / #373); `Failed` effectively dead — tool exceptions persist as `Completed` with `"Error executing tool …"` in the result body | STATE §7.1 |

## I. Issues — outright bugs

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| MA-09 | High | **Stream token undercount**: `stream_usage` reset per tool round (`litellm.py:975`) → streaming runs record only the final LLM round's tokens/cost on Agent Run + Conversation totals. Sync path correct | STATE §7.4 |
| MA-10 | High | **`tool_status` staleness**: `fetch_from` copies refresh only on message save; sync-fallback rows keep `tool_status="Queued"` forever; stream merge failures only logged → UI status silently disagrees with ATC truth | STATE §7.2 |
| MA-11 | High | **`conversation_index` race**: MAX+1 via SQL with no lock/unique constraint in `conversation_manager.py:439-467` and `audio_service.py:697-708`; equal indices → undefined history order. `sdk_tools.py` no longer assigns the index directly on current `develop` | STATE §2.3 |
| MA-12 | High | **Unguarded public write API**: `agent_chat.add_message` — no in-repo callers, no ownership/permission check, free `role` choice (`system`/`agent` injection into any conversation, re-enters model context as `include_full`) | STATE §3.4 |
| MA-13 | Medium | Merge path fragility: `"**Tool Result:**"` substring guard couples persistence to a display string; mutated full `content` (call text + result) sent as the tool message, contradicting the Tool Call branch's UI-text sanitation; missing link → empty tool name + `{}` args sent to provider | STATE §6 |
| MA-14 | — | **WITHDRAWN** (verification pass 2026-07-18, 4× kimi + orchestrator re-check): the claimed precedence bug does not exist — `(external_id or session.user) if role == "user" else "Agent"` is the actual parse; agent messages always get `user="Agent"` | STATE §4 |
| MA-15 | Medium | `repair_message_sequence` writes an Error Log entry on **every routine repair** (trimming is by-design) → error-log spam + extra DB writes (`conversation_manager.py:321-328`) | STATE §2.2 |
| MA-16 | Low | ElevenLabs webhook writes nonexistent `Agent Run.total_cost` (silently dropped) and rewrites message `creation` timestamps | STATE §10, §4 |
| MA-17 | Low | Conversation totals updated by fire-and-forget SQL; failures only logged → run-level vs conversation-level token/cost drift | STATE §7.4 |

## L. Locks — couplings that constrain any change

| ID | Finding | Evidence |
|---|---|---|
| MA-18 | **Three persisted tool shapes** coexist — separate Tool Call row, combined Tool Result row (in-place mutation), legacy separate `role=tool` rows — each with its own expansion branch; plus a repair synthesis path and a data patch. Any schema change must migrate all three shapes and keep OpenAI pairing valid | STATE §2.2, §7.2 |
| MA-19 | **One row serves two masters**: Agent Message is simultaneously UI presentation (fetch copies, socket events, mappers keyed on legacy `kind`) and model context (policy machinery reading the same `content`/`kind`). The in-place Tool Call→Tool Result mutation is the sharpest example. Changing either side breaks the other — this is the coupling that produced the duplication | STATE §6, §7.2 |
| MA-20 | **ATC is the truth but invisible**: repairs flow ATC→message, `get_result_context` serves from ATC, yet ATC is System-Manager-only and the frontend reads only the denormalized copies. Unification must re-home presentation data, not just pick a winner | STATE §7.2 |
| MA-21 | **Execution linkage runs through Agent Run only**: messages/tool calls attach to flows/orchestrations indirectly via `agent_run`; Flow Run keeps only `last_agent_run`; orchestration state split between a shell run and plan rows. Any unified timeline must first unify the run linkage | STATE §10 |

## T. Traps — what would mislead a rewrite / new-language effort

| ID | Finding | Evidence |
|---|---|---|
| MA-22 | **The 8-policy enum looks designed; it is 2 behaviors + aliases + tests that pin only the real ones.** A rewrite that "preserves all 8 policies + 10 record kinds + 5 visibilities" carries forward 4 aliases, 2 dead fields, and a broken on-demand contract — the observation's "same complexity at a higher cost" in miniature | STATE §2.1, §8 |
| MA-23 | **Three status vocabularies + split token/cost ownership**: 4/6/6 option sets (+ lowercase plan steps), tokens/cost only on Agent Run, errors triplicated under different names, Flow Run holding one overwritten `last_agent_run`. A new execution language over these inherits all three vocabularies and every aggregation rule | STATE §10 |
| MA-24 | **Dead statuses and fields are load-bearing in readers**: `Waiting User`/`Paused` are checked but never set; `Status`/`Error` message kinds render as plain text but enter model context as content. Removing them naively changes behavior; keeping them preserves noise | STATE §10, C2 §3 |
| MA-25 | **Branch drift**: Audit rebased onto `origin/develop` @ `2c3fd73c`; `generated_video` still has no writer on this base (see MA-06). Any rewrite must name its base and merge policy first (see `DOCKER_BENCH.md` §3 drift warnings) | STATE §9 |

## Relation to prior registers

- Confirms and sharpens CodeDiscovery **B-01** (#365, artifact creation path), **B-04**
  (#368, flow tool.call → no Tool Call), **C-01** (#373, dead status options — ATC
  `"Started"` joins the list).
- CommitAudit overlap: message write paths are classified there
  (guarded/`safe_commit`); this register adds only the data-consistency
  consequences (MA-09/MA-10/MA-17), not commit-policy items.
- ProviderBrand417 overlap: `generated_video` no-writer fact (MA-06) is the same
  half-shipped feature that caused the 417s.

## Suggested issue filing

Batch-file on `tridz-dev/huf` following the CodeDiscovery precedent (#363–#385,
base `origin/develop` @ `2c3fd73c`): one issue per MA row, or grouped
as "context-policy truthfulness" (MA-01..05), "tool-call consistency" (MA-08..13),
"execution-record unification" (MA-21..23). Filing is an outward action — do it only
on owner request.
