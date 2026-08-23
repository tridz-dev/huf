# HUF Analytics & Observability Architecture — Audit and Target Design

**Status:** Design document (audit + target architecture; no behavioural code changes in this pass)
**Scope:** Token/usage accounting, caching, execution metadata, conversation context composition, and how to extend today's Run-centric analytics into Run → Conversation → Agent → Model → Provider views.
**Audience:** Backend/frontend engineers implementing the next phase of HUF observability.

> **Every claim in this document was verified against the code at `pre-develop`.** Where an earlier assumption proved wrong, the correction is stated explicitly rather than quietly dropped — see §2.0, which lists three findings that changed the design.

---

## 0. Executive Summary

HUF's observability foundation is **substantially better than a first read suggests**. It already has:

- A per-run **context composition breakdown** (`huf/ai/context_segments.py`) producing five categories — `system`, `tools`, `knowledge`, `history`, `message` — counted with a real tokenizer, persisted into `Agent Run.usage_snapshot.segment_tokens`, and rendered today by `ContextBar` on the run detail page.
- A **scheduled, dimensioned rollup pipeline** (`huf/ai/agent_run_analytics.py` + `Agent Run Analytics Rollup`), running every 5 minutes via cron, already bucketed by `agent | provider | model | run_kind` and time.
- A **cost calculator** with a sane priority chain (custom pricing → LiteLLM lookup → local/free → unknown, never a silently-wrong non-zero).
- Derived **cache-effectiveness metrics** (`huf/ai/cache_metrics.py`) exposed per-run.

So the correct posture is **repair and extend, not rebuild**. However, the audit surfaced defects serious enough that building conversation/agent/model dashboards on today's numbers would produce *confidently wrong* charts. The three that must be fixed before any new aggregation ships:

1. **`input_tokens` means two different things depending on execution path** — summed across tool-calling rounds on the sync path, but only the *last* round on the streaming path (§2.1, D1). Any aggregate mixing both is meaningless.
2. **`segment_tokens` is a pre-call, round-1-only estimate**, while `input_tokens` covers the whole run — the two are not comparable, yet the UI presents them side by side (§2.1, D2).
3. **`cache_miss_tokens` is a mislabelled duplicate of `cache_creation_tokens`** (§2.1, D3).

Plus one that blocks conversation analytics specifically: **`Agent Run.conversation` is null for every `run_kind="tool"` run**, so conversation rollups would silently under-count (§2.1, D4).

---

## 1. Current-State Architecture

### 1.1 Where token usage originates

HUF talks to LLM providers almost exclusively through **LiteLLM** (`huf/ai/providers/litellm.py`). `RunProvider.run()` (`huf/ai/run.py:15-78`) always tries `litellm.run()` first; on a generic `Exception` (`run.py:46-52`) it falls back to a same-named legacy module `huf/ai/providers/<provider>.py` (`run.py:54-73`). `RunProvider.run_stream()` (`run.py:80-116`) has **no fallback at all** — LiteLLM or `frappe.throw`.

The legacy modules are effectively dead code for usage accounting. Verified: `openrouter.py:51,74-75`, `anthropic.py:77,101-102`, and `google.py:87,106-108` each initialise `total_usage = {"input_tokens": 0, "output_tokens": 0}` and extract **no cache fields and no cost**. Whenever a fallback triggers, cache and cost data silently vanish with nothing recording that the degraded path was taken.

**One Agent Run is not one model call.** `litellm.py:738` sets `MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10`, and the loop at `litellm.py:745` performs one real LLM completion per round. If the model returns tool calls, the assistant's tool-call request message is appended first (`litellm.py:1062`), the tools execute, and their results are appended (`litellm.py:1166`) — so the loop continues with a **growing** message list carrying both halves of every exchange. Usage is accumulated across rounds and returned once after the loop (`litellm.py:1067`, `1170`) — never persisted per-round.

### 1.2 How input/output/cache tokens are obtained and normalized

Per round (`litellm.py:998-1047`):
- `input_tokens` ← `usage.prompt_tokens`
- `output_tokens` ← `usage.completion_tokens`
- `cached_tokens` (cache **read**) ← `usage.prompt_tokens_details.cached_tokens` / `.cache_hit_tokens`
- `cache_creation_tokens` (cache **write**) ← `prompt_tokens_details.cache_creation_input_tokens` / `.cache_write_tokens` / `.cache_creation_tokens`, with a top-level fallback

LiteLLM normalises OpenAI's `prompt_tokens_details` and Anthropic's separate cache counters into this one shape. But the code reading that shape is **independently re-implemented four times**, with no shared helper anywhere in the repo (verified by grep for `extract_usage`/`_extract_usage`/`parse_usage`):

| # | Location | Purpose |
|---|---|---|
| a | `litellm.py:912-929` | round token counts for `calculate_cost` |
| b | `litellm.py:998-1047` | accumulation into `total_usage` |
| c | `agent_integration.py:1789-1852` | re-extraction from `result.usage`, sync path (the DB write itself is separately at `:1907-1927`) |
| d | `agent_integration.py:2889-2965` | re-extraction, streaming path — near-duplicate of (c), but *not* identical: its dict fallback reads `usage.get("prompt_tokens", 0)` (`:2903`) where the sync block reads `usage.get("input_tokens", 0)` (`:1792`), and it computes `total_tokens` inline (`:2949`, `:2962`) where the sync block does not |

The divergence noted in row (d) is not cosmetic — it is D5 (§2.1) caught in the act: two copies of the same logic have already drifted to different fallback keys, which is exactly how a defect like D1 survives in one path and not the other.

Cache **write** breakpoints (`cache_control` blocks) are emitted only for `provider_name == "anthropic"` (`litellm.py:169-177`); OpenAI and Gemini instead receive native pass-through knobs (`prompt_cache_retention`, `cached_content`) as `completion_kwargs`. Up to three regions can be marked: the static prefix and agent instructions, marked inline in `run()`/`run_stream()` (`litellm.py:659-680`), and the last conversation-history message, marked in `_format_conversation_history` (`litellm.py:180-213`).

### 1.3 The existing context-composition breakdown — `context_segments.py`

**This module is the single most important existing asset for this project, and it already does most of what a "context breakdown" needs.**

`compute_segment_tokens(agent_doc, agent, resolved_model, resolved_provider, history, knowledge_context, prompt)` (`context_segments.py:47-79`) returns, verbatim (`context_segments.py:73-79`):

```python
return {
    "system":    _count(pricing_model, system_text),
    "tools":     _count(pricing_model, tools_text)     if tools_text     is not None else None,
    "knowledge": _count(pricing_model, knowledge_text) if knowledge_text is not None else None,
    "history":   _count(pricing_model, history_text)   if history_text   is not None else None,
    "message":   _count(pricing_model, prompt),
}
```

- `_count` (`context_segments.py:32-38`) uses `litellm.token_counter(model=pricing_model, text=text)` — a **real per-model tokenizer**, not a chars/4 heuristic — returning `0` for empty text and **`None` on any exception**. The docstring (`:50-52`) explicitly warns callers not to treat `None` as zero-cost.
- `system_text` = `agent.instructions` (`:56`) — the fully assembled instructions, which by that point already include skill preambles, tool descriptions, memory blocks, and rich-element/document-artifact instruction text (`agent_integration.py:441-463`).
- `tools_text` = `frappe.as_json(serialize_tools(agent.tools or []))` (`:58-62`).
- `knowledge_text` = `knowledge_context["context_text"]` (`:64`) — the genuine injected RAG text, identical to what `inject_knowledge_context()` concatenates (`knowledge/context_builder.py:105-120`).
- `history_text` = joined `content` of history items (`:66-71`).

`compute_prefix_breakpoints(...)` (`context_segments.py:82-112`) is gated on `enable_prompt_caching` + `model_supports_prompt_caching`, producing at most two `{"marker", "prefix_hash"}` entries (SHA-256, first 16 hex chars): `instructions`, and `history` (hash of only the **last** history item).

Both are invoked at two call sites — sync (`agent_integration.py:1598-1604`) and streaming (`agent_integration.py:2796-2802`) — and persisted into `usage_snapshot.segment_tokens` / `.prefix_breakpoints`.

**The critical limitation** (§2.1, D2): both are computed **before the LLM is called at all** — `compute_segment_tokens` at `agent_integration.py:1599`, the actual call at `:1620-1622`. They therefore describe **round 1's pre-call composition only**, and capture nothing of the tool-call/tool-result content that grows the context across rounds 2..N.

### 1.4 Where usage is persisted

`agent_integration.py:1780-1927` (and its streaming duplicate) writes to two places:

1. **`Agent Conversation`** running totals via raw SQL increments (`:1892-1900`): `total_input_tokens`, `total_output_tokens`, `total_tokens`, `total_cost` — additive per run, not derived by query.
2. **`Agent Run`** via `frappe.db.set_value` (`:1907-1927`):
   - Flat Int/Float columns: `input_tokens`, `output_tokens`, `cached_tokens`, `cost`, `cost_source`, `cost_calculation_status`.
   - `usage_snapshot` (JSON): `schema_version`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cache_miss_tokens`, `cache_skipped_unsupported_model`, `total_tokens`, `completeness`, `segment_tokens`, `prefix_breakpoints`.

Verified `Agent Run` field list confirms flat columns exist for `input_tokens`/`output_tokens`/`cached_tokens` but **not** for `cache_creation_tokens`, `total_tokens`, or `cache_skipped_unsupported_model` — those live only inside the JSON blob.

### 1.5 Caching representation and model metadata

`AI Model` (`huf/huf/doctype/ai_model/ai_model.json`) full field list, verified: `provider, model_name, modalities, capabilities_section, supports_reasoning, reasoning_config_override, pricing_section, use_custom_pricing, input_cost_per_1m_tokens, output_cost_per_1m_tokens, cached_input_cost_per_1m_tokens, chat_capability_overrides_section, disable_ask_user, disable_rich_elements, disable_document_artifacts`.

Consequences:
- **No `context_window` / `max_tokens` / `max_output_tokens` field.** `agent_run_context_api.py:17` therefore hardcodes `DEFAULT_CONTEXT_WINDOW = 200000` and applies it to **every model regardless of actual window** (`:48`), with an in-code comment admitting it is "a placeholder until model metadata exposes one." Today's `ContextBar` headroom is thus wrong for any model whose real window isn't ~200K.
- **No cache-*write* price field** (only the read price, `cached_input_cost_per_1m_tokens`), so `cost_calculator.py` never prices cache-creation tokens.
- **No caching-capability flag** — eligibility is derived at runtime by `prompt_cache_capabilities.py:18`, scanning LiteLLM's pricing table for a non-null `cache_read_input_token_cost`. This derivation is sound and should be kept.

### 1.6 How Runs relate to model calls, messages, tool calls, and conversations

- **Agent Conversation (1) → Agent Run (N)** via `Agent Run.conversation`; **→ Agent Message (N)** via `Agent Message.conversation`, ordered by `conversation_index` (`conversation_manager.py:462-468`).
- **Agent Run (1) → Agent Message (N, optional)** via `Agent Message.agent_run`.
- **Agent Run** is self-referential via `parent_run`/`is_child`, with `run_kind` ∈ `agent | tool | orchestrator`.
- **Agent Tool Call** stores `tool`, `tool_args`, `tool_result`, `status`, and a `resource_usage` JSON (CPU/wall/memory — *not* LLM tokens). No token fields; an LLM-invoking tool's usage lands on a separate child `Agent Run`.
- **`Agent Run.conversation` is populated for `run_kind` `agent` and `orchestrator`, but is null by construction for `run_kind="tool"`**: `_create_flow_agent_run()` (`flow_engine.py:1349-1388`) builds the doc dict at `:1365-1377` with only `agent`, `flow_run`, `flow_node_id`, `flow_id`, `run_kind` — no `conversation` key — and the later `run_doc.db_set({...})` (`:653-660`) never adds one. The sibling `Agent Tool Call` audit doc *does* get `"conversation"` (`flow_engine.py:622`), so the linkage exists but not on the row carrying the tokens.

### 1.7 Existing analytics APIs

**`huf/ai/agent_run_analytics_api.py::get_execution_analytics`** — the real aggregate API. Verified behaviour:
- Reads only `Agent Run Analytics Rollup` (`:36-42`, `:48-54`). It issues no raw `Agent Run` query itself; note however that its lazy backfill (`:45-47`, `if not rows and frappe.db.exists("Agent Run"): refresh_rollups(full_backfill=True)`) *does* scan raw rows inside the same request when the window is cold.
- Window bounded to `MAX_WINDOW_DAYS = 93` (`:10`, enforced `:31`).
- Permission-gated via `_require_analytics_access()` (`:13`).
- Returns exactly (`:74-79`): `{"summary", "series", "breakdowns", "metadata": {granularity, from, to, freshness, source}}`, where `breakdowns` groups **only by provider** (`:65-68`), capped to top 10 (`:77`) — even though the queried fields (`:39`) already include `agent` and `model`.

**Rollup engine** — `agent_run_analytics.py`. `_dimension_key()` (`:29-30`) is verbatim:
```python
return "|".join(str(row.get(field) or "__none__") for field in ("agent", "provider", "model", "run_kind"))
```
The rollup doctype's fields are `bucket_start, granularity, dimension_key, agent, provider, model, run_kind, run_count, success_count, failed_count, input_tokens, output_tokens, cached_tokens, total_cost, duration_ms_sum, duration_count, last_recomputed_at` — **no `conversation`, no `cache_creation_tokens`, no segment/composition fields.**

**Scheduling (verified, previously only assumed):** `huf/hooks.py:251-276` registers `scheduler_events["cron"]["*/5 * * * *"] = ["huf.ai.agent_run_analytics.refresh_rollups"]` — **every 5 minutes**, active (not in the commented-out block above it).

**`huf/ai/agent_run_context_api.py::get_run_context_metrics`** — strictly single-run (`:21-52`), reads `usage_snapshot` plus the immediately-prior run of the same agent (`:29-37`) and delegates to `cache_metrics.compute_run_metrics`. Returns `{segment_tokens, total_tokens, context_window, prefix_breakpoints, cache_skipped_unsupported_model, metrics}` where `metrics` = `{cache_read_share, effective_input_multiplier, wasted_writes_tokens, prefix_stability, counterfactual_savings}` (`cache_metrics.py:85-91`). `wasted_writes_tokens` is hardcoded `None` (`cache_metrics.py:88`, comment: "needs read-after-write tracking; not captured yet").

**No conversation-level analytics API or rollup exists anywhere** — verified by repo-wide search. The only conversation-level numbers are `Agent Conversation`'s additive counters.

### 1.8 Frontend consumption today

Two disconnected paths:
- `services/executionAnalyticsApi.ts` → `get_execution_analytics` → `components/executions/ExecutionAnalyticsDashboard.tsx`, which reads **only `data.summary`** (`:58`) rendering 4 tiles (`:63-87`). `series` and `breakdowns` are computed server-side every call and **never referenced** in the component.
- `services/dashboardApi.ts::getAgentRunsForMetrics` fetches `limit: 10000` raw `Agent Run` rows (`:73-89`, comment "High limit to get all runs") which `HomePage.tsx` reduces in-browser via `calculateSuccessRate` (`:32`), `calculateAvgRuntime` (`:43`), `calculateTotalCost` (`:72`), invoked at `:178-180`. No backend aggregation involved.

The deepest existing analytics surface is `pages/AgentRunDetailPage.tsx`: Overview and Tokens & Cost definition columns, plus a Context card (`:455-465`) passing `contextMetrics.segment_tokens` straight into `ContextBar` with no relabelling, and a child-runs TanStack table.

---

## 2. Gap Analysis

### 2.0 Corrections to earlier assumptions

Three findings overturned the initial draft of this document and are called out so reviewers don't re-derive the wrong plan:

- **C1 — A context breakdown already exists.** An earlier draft proposed building `context_breakdown` capture as new work in `litellm.py`. Wrong: `context_segments.py` already computes system/tools/knowledge/history/**message** with a real tokenizer, is wired at both persistence call sites, and already reaches the UI. The genuinely new work is (i) fixing *when* it is measured, (ii) sub-typing the `tools` segment, and (iii) aggregating it above the run level.
- **C2 — The rollup is genuinely scheduled.** Confirmed at `hooks.py:251-276`, every 5 minutes. No new scheduler is needed.
- **C3 — The context window is a hardcoded 200K placeholder**, not derived per model. Any "% of context window" metric today is unreliable for non-200K models.

### 2.1 Defects — must fix before building new aggregation on top

| ID | Defect | Evidence | Why it invalidates analytics |
|---|---|---|---|
| **D1** | **`input_tokens` has different semantics on sync vs streaming paths.** Sync accumulates across rounds (`litellm.py:999`, `total_usage["input_tokens"] += ...` inside the loop). Streaming **resets** `stream_usage = None` at the top of every round (`litellm.py:1608`) and never accumulates, so after `break` (`:1912`) it holds only the **last** round's `prompt_tokens`, consumed as `input_tokens` at `agent_integration.py:2889-2904`. | verified | The same column means "sum of N growing prompts" for one run and "size of the final prompt" for another. Summing, averaging, or cost-attributing across a mixed population is **incorrect at the source**. This is the single most damaging defect found. |
| **D2** | **`segment_tokens` is pre-call and round-1-only**, while `input_tokens` spans the whole run. `compute_segment_tokens` runs at `agent_integration.py:1599`, the LLM call at `:1620-1622`. Tool results appended in rounds 2..N (`litellm.py:1062,1166`) are counted in neither `segment_tokens` nor any other segment. | verified | The Context card presents segments and total tokens as if commensurable. They are not. Multi-round runs have an entirely unmeasured context category (tool-call/result payloads). |
| **D3** | **`cache_miss_tokens` is a duplicate of `cache_creation_tokens`**, not a miss count. `litellm.py:1046-1047` adds the same `round_creation` to both accumulators; `agent_integration.py:1917-1918` persists `"cache_creation_tokens": cache_creation_tokens` and `"cache_miss_tokens": cache_creation_tokens`. | verified | Any cache dashboard reading `cache_miss_tokens` reports cache *writes* labelled as *misses*. True miss volume is tracked nowhere. |
| **D4** | **`Agent Run.conversation` is null for all `run_kind="tool"` runs** (`flow_engine.py:1365-1377`, never set at `:648-655`). Additionally, non-`flow_shared` conversation modes auto-create throwaway conversations per call. | verified | A conversation rollup would **silently exclude tool-run tokens/cost** — under-reporting exactly the runs most likely to be expensive, with no error surfaced. |
| **D5** | Usage extraction duplicated 4× with no shared helper (§1.2 table). | verified | D3 is a direct symptom; the sync/streaming duplication is how D1 survived. |
| **D6** | Legacy provider fallback drops all cache and cost data, with no flag recording that it happened. | `run.py:46-73`; legacy modules verified | Invisible data-quality cliff blended into aggregates. |
| **D7** | `cache_creation_tokens`, `total_tokens`, `cache_skipped_unsupported_model` exist only inside `usage_snapshot` JSON — no flat columns. | verified | Cannot be summed in SQL or by the rollup engine; the rollup consequently ignores cache writes entirely. |
| **D8** | Rollup has no `conversation` dimension (`_dimension_key`, `:29-30`) and no composition fields. | verified | Conversation analytics cannot reuse the otherwise-correct rollup engine without schema change. |
| **D9** | `context_window` hardcoded to 200000 for every model (`agent_run_context_api.py:17,48`); `AI Model` has no such field. | verified | "How close to the limit" is currently decorative, not measured. |
| **D10** | `tools` segment is one combined count. `agent.tools` is merged in `_setup_tools` (`agent_integration.py:116-204`) from user `Agent Tool Function` tools plus registry/builder tools and `ask_user` (all via `create_agent_tools()`, called at `:121-124`), MCP server tools (`:130-155`), `list_skills` (`:159-168`), and knowledge tools (`:170-204`) — with **no type tag surviving into `tools_text`**. | verified | "Which tools cost the most context" and "user vs system tool overhead" are unanswerable. |
| **D11** | Client-side aggregation on the primary landing page: 10,000-row fetch reduced in-browser. | `dashboardApi.ts:73-89`, `HomePage.tsx:32,43,72` | Non-scalable and divergent from the rollup path; two aggregation strategies coexist. |
| **D12** | Server computes `series` + `breakdowns` that no component renders; `breakdowns` groups only by provider despite `agent`/`model` being available. | `agent_run_analytics_api.py:65-68,74-79`; `ExecutionAnalyticsDashboard.tsx:58` | Trend/attribution questions have no UI even where the data already exists. |
| **D13** | `wasted_writes_tokens` is hardcoded `None`; `prefix_stability` is a hash comparison never reconciled against provider-reported cache tokens (`context_segments.py:17-19` states per-breakpoint attribution is deliberately not attempted). | verified | Two of four displayed cache stats are unbacked by provider truth; one is always blank. |
| **D14** | No cache-write pricing (`AI Model` lacks the field; `cost_calculator.py` receives only `cached_tokens`). | verified | Caching ROI is overstated wherever the provider bills writes at a premium. |
| **D15** | The assembled system prompt is never persisted (`create_agent`, `agent_integration.py:335-496`); `segment_tokens.system` records its size but not its content. | verified | "What did this run actually see" is unanswerable after agent/skill config changes. |
| **D16** | No reconciliation between `sum(segment_tokens)` and `input_tokens` anywhere. | verified by grep | Nothing detects an uninstrumented context source. |

**What is already correct and must not be redesigned:** `context_segments.py`'s category model and tokenizer approach; its `None`-means-unknown discipline; the rollup engine's dimension/bucket/idempotent-recompute design and 5-minute cron; `cost_calculator.py`'s priority chain; `prompt_cache_capabilities.py`'s data-driven capability derivation; `Agent Run.sequence` as a stable per-conversation ordering key.

---

## 3. Target Analytics Model

The canonical atomic unit stays the **Agent Run**. Two properties must hold before anything is aggregated above it:

1. **Every metric has one definition regardless of execution path.** D1 must be fixed first — no dashboard is worth building on a column that means two things.
2. **Every metric declares its measurement point.** A number captured pre-call for round 1 is a different quantity from one summed across rounds, and both are legitimate — but they need distinct names and must never be summed together or rendered as shares of one another.

### 3.1 Canonical metric vocabulary

To end the ambiguity, the target model names three distinct token quantities explicitly:

| Metric | Definition | Answers |
|---|---|---|
| **`billed_input_tokens`** | Sum of `prompt_tokens` across **all** rounds of the run. | "What was I charged for?" — the cost-bearing number. |
| **`peak_context_tokens`** | `prompt_tokens` of the **largest single round** (in practice the last). | "How close did this run get to the context window?" |
| **`composition_tokens`** | The `segment_tokens` breakdown, extended to be measured per-round and summed/peaked consistently. | "What filled the context, and with what?" |

`peak_context_tokens` — not `billed_input_tokens` — is the only correct numerator for a context-window-fullness metric. Conversely `billed_input_tokens` — not `peak_context_tokens` — is the only correct basis for cost and for conversation totals. Today's single `input_tokens` column conflates these and, per D1, computes each on a different path.

Per-run canonical set: `billed_input_tokens`, `peak_context_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cache_miss_tokens` (real, or absent), `cost`, `round_count`, `composition_tokens` (with tool sub-types), `model_context_window` (snapshotted), `latency_ms`, `provider_path`, `execution_mode` (sync/stream).

### 3.2 Derived levels

Conversation, Agent, Model, Provider, and time views are **pure aggregations** of the above with no re-definition:

- **Cumulative cost/tokens** = `SUM(billed_input_tokens)`, `SUM(output_tokens)`, `SUM(cost)`.
- **Current context size** = the latest run's `peak_context_tokens` — explicitly a *snapshot*, never a sum. The UI must label these two differently and never render one as a share of the other. (This is the "misleading aggregation" trap the brief calls out, and it is exactly the trap today's data would spring.)
- **Cache effectiveness** = `SUM(cache_read_tokens) / SUM(cache_read + cache_write + uncached_input)` computed from summed components — **never an average of per-run ratios**, which weights a 100-token run equally with a 100,000-token one.
- **Context growth** = `peak_context_tokens` per run plotted against `Agent Run.sequence`; "major growth" turns are consecutive-row deltas, requiring no new storage.

---

## 4. Storage & Instrumentation Changes

All changes are additive. No parallel analytics hierarchy is introduced for atomic data.

### 4.1 Fix measurement before adding fields (highest priority)

- **Unify usage extraction (D5).** Extract one helper — proposed `huf/ai/usage_extraction.py::extract_round_usage(response) -> dict` — and call it from all four sites (`litellm.py:912-929`, `:998-1047`, `agent_integration.py:1789-1852`, `:2889-2965`). This is the precondition for D1/D3 not recurring.
- **Fix D1.** In `litellm.py`'s streaming loop, accumulate per-round usage exactly as the sync loop does, and additionally track `max(prompt_tokens)` across rounds. Emit both `billed_input_tokens` and `peak_context_tokens` from **both** paths so the two columns are path-independent.
- **Fix D3.** Stop assigning `cache_creation_tokens` to `cache_miss_tokens` (`litellm.py:1047`, `agent_integration.py:1918`). Either compute a real miss figure (`billed_input − cache_read − cache_write`) or omit the field entirely. Do not ship a mislabelled duplicate; a wrong number is worse than a missing one.
- **Fix D4.** Set `conversation` on tool-kind runs in `_create_flow_agent_run()` (`flow_engine.py:1365-1377`), sourcing it the same way the sibling `Agent Tool Call` already does (`flow_engine.py:622`). Until this lands, conversation rollups must explicitly exclude — and the UI must disclose — tool-kind runs rather than silently under-count.

### 4.2 Extend `context_segments.py` (do not replace it)

- **Fix D2 — measure per round.** Move/duplicate segment computation so composition is captured for the actual message list of each round inside `litellm.py`'s loop, not once pre-call in `agent_integration.py`. Report per-run: the round-1 composition (comparable to today's data), the peak-round composition, and a new **`tool_exchange`** category covering assistant tool-call messages and tool results accumulated during the loop — currently an entirely unmeasured context consumer. Keep the existing five keys stable so `ContextBar` and historical snapshots continue to work.
- **Fix D10 — sub-type the tools segment.** `_setup_tools` (`agent_integration.py:116-204`) already knows each tool's origin. Tag tools as `user_configured | builtin_registry | internal_capability (ask_user/list_skills) | knowledge | mcp` and count each subset separately, storing `tools: {total, by_source: {...}}`. Per-tool counts (each tool's serialised schema size) are cheap at the same point and directly answer "which tools contribute the most context overhead."
- **Preserve the `None` discipline.** `None` = "could not count", `0` = "counted, empty" (`context_segments.py:50-52`). Aggregation must propagate unknowns as unknown, never coerce to 0 — a silent 0 would make composition percentages quietly wrong.
- **Add reconciliation (D16).** Compare `sum(composition) ` against the round's provider-reported `prompt_tokens`; log a warning beyond a tolerance. Divergence is the signal that an uninstrumented context source exists. Warn, never fail.

### 4.3 `Agent Run` schema additions

Promote to flat columns (D7): `cache_creation_tokens`, `total_tokens`, `cache_skipped_unsupported_model` (Check). Add: `billed_input_tokens` + `peak_context_tokens` (or repurpose `input_tokens` as billed and add peak — a migration note either way, §8), `round_count`, `model_context_window` (Int, snapshotted at call time so later model-config edits can't rewrite history), `provider_path` (Select: `litellm` / `legacy_fallback`, D6), `execution_mode` (Select: `sync` / `stream`). Keep `usage_snapshot` as the versioned detail record, populated from the same values as the flat columns.

### 4.4 `AI Model` schema additions

Add `context_window` (Int) and `max_output_tokens` (Int), seeded from LiteLLM's model-cost table where available and editable for custom/local models — this retires the hardcoded 200K placeholder (D9). Add `cached_input_write_cost_per_1m_tokens` (Float) so `cost_calculator.py` can price cache writes (D14).

### 4.5 `Agent Run Analytics Rollup` additions

Add `conversation` to both the doctype and `_dimension_key()` (D8), plus `cache_creation_tokens` and `composition_totals` (JSON: summed segment categories per bucket). The existing 5-minute cron and idempotent recompute need no change.

### 4.6 `Agent Conversation`

No schema change. Its additive counters remain a cheap header summary, but the UI must treat them strictly as *cumulative totals* per §3.2 — never as current context size. Note they are also affected by D1 today.

**Latency budget:** all added instrumentation is local tokenizer/counter work on data already in memory at call time — no extra network round-trips. The per-round move (D2) increases tokenizer calls roughly linearly with `round_count`; if that proves measurable, count only round 1 and the final round rather than every round, which still yields both the comparable baseline and the peak.

---

## 5. Aggregation Architecture

Keep the existing two-tier shape; widen it.

1. **Atomic layer** — `Agent Run`, with path-independent metrics (§4.1) and composition (§4.2). Single source of truth; nothing above it stores independently-derived numbers.
2. **Rollup layer** — `Agent Run Analytics Rollup`, extended with `conversation` and composition sums (§4.5), recomputed by the existing `refresh_rollups` cron.
3. **API layer** — extend `get_execution_analytics` to accept `dimension ∈ {agent, provider, model, conversation, run_kind}` (today hardcoded to provider) and to return composition sums. Keep `agent_run_context_api.py` separate: its per-run, prior-run-comparison semantics are deliberately not aggregate.
4. **Frontend layer** — one shared analytics service (extend `executionAnalyticsApi.ts`), parameterised by dimension, backing every view. Retire the `dashboardApi.ts` raw-fetch path (D11).

Correctness holds because every higher-level number is either a `SUM`/`MAX` over atomic rows using one field definition at every level, or an explicitly-labelled latest-snapshot value.

**Rollups vs. direct queries.** The rollup already exists and is scheduled, so use it for time-series and cross-entity views. For a single conversation — typically tens of runs — query `Agent Run` directly, ordered by `sequence`: the rollup's 5-minute lag would make a just-finished turn missing from its own conversation view, which reads as a bug. Rule of thumb: **rollups for aggregate/trend, direct query for one entity's detail.**

---

## 6. Conversation Analytics Design

**Totals (cumulative, labelled as such):** run count split by `run_kind`, `SUM(billed_input_tokens)`, `SUM(output_tokens)`, `SUM(cost)`, `SUM(cache_read/write)`.

**Current state (snapshot, labelled as such):** latest run's `peak_context_tokens` and its composition; `peak_context_tokens / model_context_window` as true window fullness (available only after §4.4).

**Trends:** `peak_context_tokens` per run against `sequence`; composition as a stacked series over the same axis; consecutive-delta flagging for growth spikes.

**Cache:** conversation-level effectiveness from summed components (§3.2), plus `prefix_stability` rolled up — with the caveat (D13) that stability is a hash comparison, not provider-confirmed cache behaviour, and should be labelled as an indicator rather than a measurement.

**"Repeated vs. newly introduced" context:** approximated by cache-read share plus prefix stability. Worth stating plainly in the UI that this is an approximation; exact re-send accounting would require per-breakpoint attribution that `context_segments.py:17-19` deliberately does not attempt.

**Drill-down:** every tile links to the conversation's runs ordered by `sequence`, and from there into the existing run detail page.

---

## 7. UI / Visualization Design

> The frontend conventions below were re-verified against the tree; several component names in circulation (`PageLayout`, `AppSidebar.tsx`, a flat `components/dashboard/` listing) **do not exist** and `CLAUDE.md` is out of date on this point. What follows matches the code.

### 7.1 The conventions a new analytics view must follow

- **Page chrome:** `PageFrame` from `@/layouts/PageFrame` (there is no `PageLayout`), props `{title, badge, meta, actions, filters, children, className, scrollRef}`. It registers with `UnifiedLayout`'s `PageChromeContext` so the outer topbar collapses. List pages: `<PageFrame title actions filters={<FilterBar/>}>` wrapping `GridView` + `LoadMoreButton`. Detail pages: `<PageFrame className="mx-auto w-full max-w-5xl">` wrapping a `space-y-6` stack of `rounded-lg border border-line bg-panel p-5` blocks.
- **Detail routes** use the `*Wrapper` pattern: the wrapper resolves a display name, builds `breadcrumbs: {label, href?}[]`, and renders `<UnifiedLayout breadcrumbs showCurrentCrumb>` around the plain inner page (see `pages/AgentRunDetailPageWrapper.tsx`). Routes are lazy-loaded under `<ProtectedRoute>` with a `<PageLoader/>` suspense fallback.
- **Stat tiles:** `MetricGauge` / `GaugeRow` from `components/dashboard/cards/MetricGauge.tsx` — the genuinely reusable primitives, already used by both HomePage and Executions. `GaugeRow` is a bordered 1/2/4-column divided grid; `MetricGauge({label, period, value, unit, info})` renders label + optional info tooltip + a `text-[22px]` figure. **Figures are never coloured** — the code comments treat a coloured dashboard figure "for no stated reason" as a defect. Use `EmptyStat` (em dash + caption) when a metric has no denominator.
- **Composition bars:** `components/ui/context-bar.tsx::ContextBar` — a segmented proportional meter with `SEGMENT_ORDER` covering System / Tools / Knowledge / History / Message plus computed **Headroom**, and an optional second strip for Cache reads / Cache writes / Fresh input. It already renders exactly the five-way split this project needs, so conversation composition should reuse it rather than invent a new chart.
- **Tables:** hand-rolled `useReactTable` + shadcn `<Table>`, copying the `Executions.tsx` idiom (sortable ghost-button headers, `RIGHT_ALIGNED_COLUMNS` for numeric/temporal, row `onClick` → detail route). A generic `DataListView` exists but is *not* used on the analytics-adjacent pages; follow what ships.
- **Empty states:** `EmptyState` with `variant` ∈ `create | no-results | passive`. Analytics surfaces are `passive` (data accrues over time) — important, because a new analytics page will legitimately be empty for pre-instrumentation conversations (§8).
- **Colour:** Tailwind theme classes only (`ink`, `steel`, `steel-soft`, `panel`, `line`, `signal`, `signal-ink`, `good`, `warning`) — never inline hex. `ContextBar`'s `SEGMENT_ORDER` map (system/tools/message → `bg-signal`, knowledge → `bg-good`, history → `bg-warning`) is the existing categorical precedent and deliberately avoids red, which is reserved for failure. Any new category (e.g. `tool_exchange`) should extend that map in the same spirit. Status uses `StatusDot` (`run | idle | ok | fail`), the current refined pattern, over raw `Badge` variants.
- **Navigation:** nav items live in `components/app-sidebar.tsx` (kebab-case; there is no `AppSidebar.tsx`) as arrays of `{title, url, icon, capability, badge?}`. A new Analytics section belongs in `operateNavItems` (group label **"Monitor"**) alongside Dashboard/Executions/Playground, likely with `badge: "Experimental"` matching its neighbours.

### 7.2 The one genuinely new decision: charts

**No first-party page in HUF renders a chart today.** `components/ui/chart.tsx` is a complete, themed shadcn/recharts wrapper (`ChartContainer`, `ChartConfig`, `ChartTooltip`, `ChartLegend`), but a full-frontend grep found its only real recharts consumer to be `components/ui/jsx-preview.tsx` — the sandboxed renderer for **AI-generated artifacts inside chat**, which imports recharts directly. Every other hit is the Lucide `BarChart3` glyph.

So proposing trend charts is **not** "following existing patterns" — it is a first-of-its-kind adoption, and it should be decided deliberately:

- **Option A (zero precedent risk):** build conversation analytics from `GaugeRow`/`MetricGauge` tiles plus `ContextBar`-style segmented bars, extended with a compact per-turn sparkline-as-bars row. Fits the established "figures are scanned, not read" design intent; no new dependency surface.
- **Option B (first real chart):** adopt `ChartContainer` for the context-growth-over-turns series — the one question tiles genuinely cannot answer, since it is inherently a shape over an axis. The component exists and is theme-aware; the cost is being the first page to depend on it.

**Recommendation: Option B, scoped to exactly one chart** (context growth vs. `sequence`), with everything else built from existing primitives. Context growth is the core question of conversation analytics and is poorly served by tiles; every other metric is well served by them. Confining the precedent to a single chart keeps the risk proportionate. This should be an explicit, reviewed decision rather than an implementation detail — hence its placement here.

### 7.3 Placement

- **Run Analytics:** extend `AgentRunDetailPage.tsx` in place. Add `round_count`, `execution_mode`, and `provider_path` (flagging legacy-fallback runs) to the Overview column; extend the Context card to show peak-round composition and the new `tool_exchange` category; replace the hardcoded 200K headroom with the real `model_context_window` once §4.4 lands. Keep the file-local `DefinitionRow`/`DefinitionColumn`/`ContextStat` idiom — these are page-scoped by design, not shared components.
- **Conversation Analytics:** attach as a second occupant of `ChatShellFrame`'s existing `rightPane` slot — the same slot `ArtifactPreviewPane` uses, with state modelled on the `useArtifactPane()` hook (`open/close/width/current`). The three-column layout (rail + transcript + pane) is documented in `ChatPageV2.tsx` as intentional. The toggle belongs beside the existing artifact toggle in `ChatWindowHeader.tsx`. Note the pane has no tab bar today (the artifact pane uses a switcher, not tabs), so an "Artifact / Analytics" tab strip is new UI — a smaller, more contained novelty than a standalone route, and it keeps analytics adjacent to the conversation it describes.
- **Agent / Model / Provider Analytics:** a new `/analytics` list-shaped page under "Monitor", reusing `PageFrame` + `FilterBar` + `GaugeRow`, with a dimension selector mapping to the extended `get_execution_analytics(dimension=...)`. This is also where `series`/`breakdowns` — computed since day one but never rendered (D12) — finally surface.
- **Drill-down chain:** Provider → Model → Agent → Conversation → Run, each level linking down, consistent with the existing parent/child run navigation.

---

## 8. Migration & Compatibility

- **Backfillable from existing data:** `cache_creation_tokens` and `total_tokens` flat columns can be populated from existing `usage_snapshot` JSON via a Frappe patch — the values are already there.
- **Not backfillable:** per-round composition, `tool_exchange` tokens, tool sub-typing, `round_count`, `peak_context_tokens`, real `model_context_window`, and cache-write cost. The inputs were never captured. Historical runs must render as "not measured", not as zero — conflating the two would silently distort every historical average.
- **Semantics break, and it is intentional:** after D1 is fixed, `input_tokens` for streaming runs changes meaning (last-round → summed). Historical streaming runs will therefore **under-report** relative to post-fix runs. This must be disclosed on any chart spanning the cutover — a visible "measurement changed on <date>" annotation is preferable to a smooth line that quietly compares two different quantities. Consider writing the new values into the new `billed_input_tokens`/`peak_context_tokens` columns and leaving `input_tokens` frozen as legacy, so no historical row is retroactively reinterpreted.
- **D4's effect on history:** existing tool-kind runs have null `conversation` and cannot be retro-linked in general (only `flow_run` relates them). Conversation totals for historical flow-heavy conversations will remain incomplete; disclose rather than approximate.
- **Rollup:** adding the `conversation` dimension requires one `refresh_rollups(full_backfill=True)` — the mechanism already exists and is already triggered lazily on cold windows. New rollup fields backfill as 0/null for pre-instrumentation buckets.
- **Non-breaking:** `usage_snapshot` keys are preserved and only added to; flat-column promotion keeps the JSON copy. Existing readers, including `ContextBar`'s five segment keys, continue to work unchanged.

---

## 9. Implementation Plan

Ordered by dependency. **Phase 1 is a prerequisite for every later phase** — building dashboards before it lands would ship confidently wrong numbers.

**Phase 1 — Correctness (no schema change; ship and verify first)**
1. Add `huf/ai/usage_extraction.py` with one shared extractor; call it from `litellm.py:912-929`, `litellm.py:998-1047`, `agent_integration.py:1789-1852`, `agent_integration.py:2889-2965` (D5).
2. Fix the streaming accumulation bug so `input_tokens` is path-independent, and track the per-round max (`litellm.py:1608`, `:1912`, `agent_integration.py:2889-2904`) (D1).
3. Remove the `cache_miss_tokens` alias (`litellm.py:1047`, `agent_integration.py:1918`) (D3).
4. Populate `conversation` on tool-kind runs (`flow_engine.py:1365-1377`) (D4).

**Phase 2 — Schema**
`agent_run.json`: flat `cache_creation_tokens`, `total_tokens`, `cache_skipped_unsupported_model`, plus `billed_input_tokens`, `peak_context_tokens`, `round_count`, `model_context_window`, `provider_path`, `execution_mode`.
`ai_model.json`: `context_window`, `max_output_tokens`, `cached_input_write_cost_per_1m_tokens`.
`agent_run_analytics_rollup.json`: `conversation`, `cache_creation_tokens`, `composition_totals`.
Frappe patch backfilling the two JSON-derivable columns.

**Phase 3 — Instrumentation (extend `context_segments.py`, do not rewrite)**
Per-round composition capture including the new `tool_exchange` category (D2); tool sub-typing and per-tool schema sizes via `_setup_tools`' origin knowledge (D10); reconciliation warning against provider `prompt_tokens` (D16); `cost_calculator.py` accepting and pricing cache writes (D14); retire `DEFAULT_CONTEXT_WINDOW` in favour of the snapshotted per-model value (D9).

**Phase 4 — Aggregation**
Extend `_dimension_key()`/`_recompute_rollup()` with `conversation` and composition sums; extend `get_execution_analytics` with a `dimension` parameter and composition output; add a conversation-detail endpoint that queries `Agent Run` directly (per §5's lag rule); run one full backfill.

**Phase 5 — Frontend**
Extend `executionAnalyticsApi.ts` into the single shared, dimension-parameterised service; migrate `HomePage` off the 10,000-row client reduction (D11); extend the run detail Context card; build the conversation analytics pane in `ChatShellFrame`'s `rightPane`; build `/analytics` under "Monitor" surfacing `series`/`breakdowns` (D12). Charts strictly per the §7.2 decision.

**Phase 6 — Validation**
Confirm composition reconciles with provider-reported tokens across each provider; confirm sync and streaming runs of the same workload now report equal `billed_input_tokens` (the direct test for D1); confirm conversation totals include tool-kind runs post-D4; verify rollup backfill over a historical window; ensure every pre-instrumentation surface renders "not measured" rather than 0.

---

## Appendix — Verification Notes

Findings were established by direct code reads, not inference. Claims carrying specific risk were independently re-verified, and the following were **corrected** against an earlier draft: the existence and completeness of `context_segments.py` (§2.0 C1); the rollup's actual cron schedule (C2); the hardcoded context window (C3); and the frontend component inventory (§7.1 — `PageFrame` not `PageLayout`, `app-sidebar.tsx` not `AppSidebar.tsx`, and the absence of any first-party chart).

Every file:line citation in this document was then re-checked against the tree in a separate pass, which corrected seven imprecise references (line ranges for `run.py`'s `RunProvider.run`, `flow_engine.py`'s `db_set`, the cache-region and tool-merge citations) and two mischaracterisations (the `agent_integration.py` blocks in §1.2 are usage *extraction*, not persistence; the sync and streaming copies are near-duplicates that have already drifted, not line-for-line identical). The D1–D4 defect claims were re-verified exactly as stated. Line numbers are accurate as of `pre-develop` at the time of writing and will drift as the files change — treat the named symbols, not the numbers, as the durable reference.

Two claims in circulation were found **false** and should not be repeated: that a context breakdown needs to be built from scratch, and that recharts is already in use in the product UI (it is used only inside the AI-artifact sandbox renderer).

Primary sources: `huf/ai/{context_segments,cache_metrics,cost_calculator,prompt_cache_capabilities,run,agent_integration,flow_engine,agent_run_analytics,agent_run_analytics_api,agent_run_context_api,conversation_manager,sdk_tools,tool_registry,tool_serializer}.py`, `huf/ai/providers/{litellm,openrouter,anthropic,google}.py`, `huf/ai/knowledge/{context_builder,retriever}.py`, `huf/hooks.py`; doctypes `agent_run`, `agent_conversation`, `agent_message`, `agent_tool_call`, `ai_model`, `agent_run_analytics_rollup`; frontend `App.tsx`, `layouts/PageFrame.tsx`, `components/app-sidebar.tsx`, `components/dashboard/**`, `components/ui/{context-bar,chart}.tsx`, `components/executions/ExecutionAnalyticsDashboard.tsx`, `pages/{AgentRunDetailPage,AgentRunDetailPageWrapper,HomePage,Executions,ChatPageV2}.tsx`, `services/{dashboardApi,agentRunApi,executionAnalyticsApi}.ts`.
