# HUF Analytics & Observability Architecture — Audit and Target Design

**Status:** Design document (no code changes in this pass — audit + target architecture only)
**Scope:** Token/usage accounting, caching, execution metadata, conversation context, and how to extend the current Run-centric analytics into Run → Conversation → Agent → Model → Provider views.
**Audience:** Backend/frontend engineers implementing the next phase of HUF observability.

---

## 1. Current-State Architecture

### 1.1 Where token usage originates

HUF talks to LLM providers almost exclusively through **LiteLLM** (`huf/ai/providers/litellm.py`, ~2000 lines). `RunProvider.run()` (`huf/ai/run.py:15-78`) always tries `litellm.run()` first and only falls back to a legacy per-provider module (`huf/ai/providers/{openrouter,anthropic,google}.py`) if LiteLLM raises. Those legacy modules are effectively dead code for usage/cache accounting: `openrouter.py` extracts only `prompt_tokens`/`completion_tokens` from raw REST JSON, `anthropic.py` and `google.py` similarly extract only plain input/output counts, and **none of the three extract cache tokens or compute cost**. Whenever a request falls back to one of them, cache and cost data silently disappear.

Inside `litellm.py`, a single agent "Run" is **not** one model call. `RunProvider.run` triggers an internal tool-calling loop (`litellm.py:738-745`, `MAX_ROUNDS = agent.max_turns or 10`): each round is one real LLM completion call; if the model returns tool calls, they execute and the loop continues. Usage from every round is accumulated into one `total_usage` dict (`litellm.py:727-736`) and returned as a single `SimpleResult` for the whole run. This means **`Agent Run.input_tokens`/`output_tokens`/`cached_tokens` are sums across however many round-trips the tool-calling loop took (up to `max_turns`)** — not the token footprint of any single model call.

### 1.2 How input/output/cache tokens are obtained from providers, and normalized

Per round (`litellm.py:998-1047`), usage is read from the LiteLLM response:
- `input_tokens` ← `usage.prompt_tokens`
- `output_tokens` ← `usage.completion_tokens`
- `cached_tokens` (cache **read**) ← `usage.prompt_tokens_details.cached_tokens` or `.cache_hit_tokens`
- `cache_creation_tokens` (cache **write**) ← `prompt_tokens_details.cache_creation_input_tokens` / `.cache_write_tokens` / `.cache_creation_tokens`, with a top-level fallback

LiteLLM normalizes OpenAI's `prompt_tokens_details` and Anthropic's separate cache read/write counters into this one shape — that part works. But the extraction logic that reads this shape is **re-implemented independently three times**: once for cost calculation (`litellm.py:912-929`), once for the returned `total_usage` (`litellm.py:998-1047`), and again for persistence in `huf/ai/agent_integration.py:1789-1852` (duplicated again in the streaming path at ~2880-2962). Each copy independently tries "dict shape, then attribute shape, then several alias key names." A new provider field name requires updating three places, and they can already be observed drifting (see 2.1).

Cache **write** (`cache_control` blocks) is only emitted for `provider_name == "anthropic"` (`litellm.py:169-177`) — other providers get no explicit cache breakpoints from HUF even when `enable_prompt_caching` is on for the agent, though OpenAI/Gemini get their own native knobs passed through as `completion_kwargs` (`prompt_cache_retention`, `cached_content`). Up to three cache regions can be marked: a static prefix, the agent's own instructions, and the last conversation-history message (`_format_conversation_history`, `litellm.py:180-213`).

### 1.3 Where this information is persisted

`AgentManager._execute_agent_run` in `agent_integration.py:1780-1927` (and its duplicate for the streaming path) persists to two places:

1. **`Agent Conversation`** running totals, via raw SQL increments (`agent_integration.py:1892-1900`): `total_input_tokens`, `total_output_tokens`, `total_tokens`, `total_cost`. These are additive counters updated per run, not derived by aggregate query.
2. **`Agent Run`**, via `frappe.db.set_value` (`agent_integration.py:1907-1927`):
   - Flat, queryable columns: `input_tokens`, `output_tokens`, `cached_tokens`, `cost`, `cost_source`, `cost_calculation_status`.
   - `usage_snapshot` (JSON): `schema_version`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cache_miss_tokens`, `cache_skipped_unsupported_model`, `total_tokens`, `completeness`, `segment_tokens`, `prefix_breakpoints`.

### 1.4 What is persisted versus calculated dynamically

Persisted as real columns (directly summable in SQL): `input_tokens`, `output_tokens`, `cached_tokens`, `cost`. Persisted only inside a JSON blob (not summable without parsing): `cache_creation_tokens`, `cache_miss_tokens`, `total_tokens`, `segment_tokens`, `prefix_breakpoints`, `completeness`. Calculated dynamically at read-time, never persisted: derived cache-effectiveness metrics (`cache_read_share`, `effective_input_multiplier`, `prefix_stability`, `counterfactual_savings`) computed on demand by `huf/ai/cache_metrics.py` from the stored `usage_snapshot`.

Not persisted **at all**: the fully-assembled system prompt actually sent to the model (base HUF prompt + skill preambles + tool descriptions + memory/rich-element instructions — assembled fresh every call in `AgentManager.create_agent`, `agent_integration.py:335-496`, and only ever handed to the SDK object, never written to a doctype field); the per-tool token cost of tool schemas in context; the estimated token size of injected knowledge/RAG context (computed with a rough chars/4 heuristic in `huf/ai/knowledge/context_builder.py:81`, used only as a loop-guard and discarded); and per-round-trip usage inside a multi-round tool-calling loop (only the sum across the loop survives).

### 1.5 How caching information is represented

See 1.2. In addition, `AI Model` (`huf/huf/doctype/ai_model/ai_model.json`) has no "supports prompt caching" flag — caching eligibility is derived at runtime by `model_supports_prompt_caching()` (`huf/ai/prompt_cache_capabilities.py:18`), which scans LiteLLM's own pricing table for a model entry with a non-null `cache_read_input_token_cost`. `AI Model` does carry `cached_input_cost_per_1m_tokens` (cache **read** price) but has **no cache-write price field**, so `cost_calculator.py` never separately prices cache-creation tokens — they're currently unpriced/free in HUF's cost model even when the provider bills for them (e.g. Anthropic's 1.25x write premium).

### 1.6 How Run records relate to model calls, messages, tool calls, and conversations

- **Agent Conversation (1) → Agent Run (N)**: `Agent Run.conversation` FK; no reverse child-table.
- **Agent Conversation (1) → Agent Message (N)**: `Agent Message.conversation` FK, ordered by `conversation_index` (strictly increasing per conversation, `conversation_manager.py:462-468`).
- **Agent Run (1) → Agent Message (N, optional)**: each message may carry an `agent_run` FK tying it to the run that produced it.
- **Agent Run** is self-referential via `parent_run`/`is_child`, and carries `run_kind` (`agent|tool|orchestrator`) — sub-agent/orchestration invocations get their own child Agent Run row with independent token/cost accounting. This is a *different* mechanism from the in-loop tool-calling rounds described in 1.1, which do **not** get separate rows.
- **Agent Tool Call**: linked from `Agent Run` and `Agent Message`, stores `tool`, `tool_args`, `tool_result`, `status`, and a `resource_usage` JSON (CPU/wall time/memory — compute resource usage, not LLM tokens). It carries no token/cost fields of its own; if a tool call is itself an LLM invocation (a sub-agent tool), its usage lives on a separate child `Agent Run` (`run_kind="tool"`).

### 1.7 How existing analytics APIs obtain their data

Two backend surfaces exist, and they are architecturally very different:

- **`huf/ai/agent_run_analytics_api.py`** (`get_execution_analytics`) — a genuine bucketed, dimensioned, permission-gated aggregate API bounded to 93 days. It reads exclusively from a pre-aggregated doctype, **`Agent Run Analytics Rollup`**, never scanning raw `Agent Run` rows at request time. The rollup rows are computed by `huf/ai/agent_run_analytics.py::refresh_rollups()`, which finds terminal-status runs in a correction window and re-derives `run_count`, `success_count`, `failed_count`, `input_tokens`, `output_tokens`, `cached_tokens`, `total_cost`, `duration_ms_sum`/`duration_count`, bucketed by `(granularity, bucket_start, dimension_key)` where `dimension_key = agent|provider|model|run_kind`. **This is already dimensioned for agent/provider/model rollups** — the API currently only breaks down by `provider` in Python, but the stored rows already carry `agent` and `model` too. It does **not** track cache-creation tokens or a `conversation` dimension.
- **`huf/ai/agent_run_context_api.py`** (`get_run_context_metrics`) — explicitly single-run only ("never aggregates raw runs" per its own docstring); reads one run's `usage_snapshot` plus the agent's immediately-prior run for prefix-stability comparison, via `cache_metrics.py`.

On the frontend, these two backend surfaces are consumed by **two disconnected paths**:
- `frontend/src/services/executionAnalyticsApi.ts` calls the real rollup-backed `get_execution_analytics` and feeds the Executions page's `ExecutionAnalyticsDashboard.tsx` — but that component only renders `data.summary` as stat tiles (Runs, cache ratio, LLM cost, avg duration); the API's bucketed `series` and provider `breakdowns` are computed server-side but **never rendered** — no chart consumes them despite `recharts` already being wired into `components/ui/chart.tsx`.
- `frontend/src/services/dashboardApi.ts` (used by `HomePage.tsx`) does **not** use the rollup API at all. It fetches up to 10,000 raw `Agent Run` rows client-side and reduces them in the browser on every page load (`calculateSuccessRate`, `calculateAvgRuntime`, `calculateTotalCost`), for the last 7 days only. This is the primary dashboard landing page and it is the least scalable analytics path in the codebase.

### 1.8 How the current run-level analytics UI and visualizations work

`frontend/src/pages/AgentRunDetailPage.tsx` is the deepest existing analytics surface: an Overview panel (agent/provider/model/duration), a Tokens & Cost panel (input/output/cached tokens, cost, cost_source), and a Context card driven by `agent_run_context_api.py` — a `ContextBar` component visualizing `segment_tokens` against a context-window value, plus four derived stats (`prefix_stability`, `effective_input_multiplier`, `counterfactual_savings`, `wasted_writes_tokens` — the last of which is hard-coded `None`, not implemented). A child-runs table shows `run_kind="tool"/"orchestrator"` sub-runs. No charting library is used on this page — it's definition lists and tables only.

### 1.9 Whether analytics data is sufficiently granular to aggregate correctly later

Partially. The rollup pipeline's dimensioning (`agent|provider|model|run_kind` + time bucket) is a solid foundation that already generalizes toward agent/model/provider views. But three gaps block reliable cross-dimensional aggregation as requested in this audit:
1. **No `conversation` dimension** in the rollup — conversation-level analytics cannot be derived from the rollup table today; only from raw `Agent Conversation` running counters (additive, not query-composable with time/agent/model filters) or by scanning raw `Agent Run` rows per conversation.
2. **No per-model-call granularity** — a Run's tokens are a sum across an internal tool-calling loop of unknown depth (up to `max_turns`), so "cost per LLM round-trip" and "context growth within a single run" are not reconstructable from persisted data.
3. **No context-composition breakdown at capture time** — system prompt, tool schemas, and knowledge context token costs are folded into a single `input_tokens` number with no persisted attribution; `segment_tokens` in `usage_snapshot` is the closest existing attempt but its categories need to be examined and extended (Phase 3 below) to match the system/history/tools/other breakdown requested.

---

## 2. Gap Analysis

| # | Gap | Where | Impact |
|---|---|---|---|
| G1 | Usage-extraction logic duplicated 3× independently (cost calc, `total_usage`, persistence — sync and streaming paths) | `litellm.py:912-929`, `litellm.py:998-1047`, `agent_integration.py:1789-1852` and its ~2880-2962 duplicate | New provider fields require 4 coordinated edits; already drifted (see G2) |
| G2 | `cache_creation_tokens` and `cache_miss_tokens` are the *same value* stored under two different semantic labels | `litellm.py:1047`, `agent_integration.py:1917-1918` | "Cache miss" (tokens that were cache-eligible but not hit) is not actually tracked anywhere; any dashboard built on `cache_miss_tokens` today reports the wrong thing |
| G3 | Legacy provider modules (`openrouter.py`, `anthropic.py`, `google.py`) silently drop all cache accounting and cost calculation on LiteLLM fallback | `run.py:15-78` | Analytics data has an invisible quality cliff whenever fallback triggers — no flag records that a run took the degraded path |
| G4 | `cache_creation_tokens`, `cache_miss_tokens`, `total_tokens` exist only in `usage_snapshot` JSON, not as real columns | `agent_run.json` | Cannot be summed/filtered in SQL or in the rollup pipeline without JSON parsing; rollup already excludes cache-creation entirely |
| G5 | Rollup has no `conversation` dimension | `agent_run_analytics.py`, `agent_run_analytics_rollup.json` | Conversation-level analytics (the core ask of this project) cannot reuse the existing, otherwise-solid rollup infrastructure without extension |
| G6 | HomePage dashboard bypasses the rollup system entirely, fetching up to 10k raw rows client-side | `dashboardApi.ts`, `HomePage.tsx` | Non-scalable, inconsistent with the Executions page; two aggregation strategies live side by side and will diverge further as dimensions grow |
| G7 | Server computes bucketed `series` and provider `breakdowns` that no frontend component renders | `agent_run_analytics_api.py` + `ExecutionAnalyticsDashboard.tsx` | Wasted backend work; also means trend/attribution questions ("which runs caused context growth") have no UI even where data exists |
| G8 | No context-composition breakdown captured at the point of the LLM call (system / history / tools / knowledge) | `agent_integration.py` (system prompt assembly is ephemeral), `sdk_tools.py`/`tool_serializer.py` (tool schema is built and serialized fresh every call, never persisted) | Cannot answer "what % of context is tools vs history vs system" — the central ask of Section 2/6 of this project — without new instrumentation |
| G9 | System prompt actually sent to the model is never persisted, only reconstructible by replaying `create_agent()` against *current* config | `agent_integration.py:335-496` | Historical/audit accuracy is lost if agent instructions, skills, or memory policy change after the run — "what did this run actually see" becomes unanswerable after the fact |
| G10 | Knowledge/RAG injected-context size is only a rough chars/4 estimate used as a loop-guard, discarded after the call | `knowledge/context_builder.py:81` | The real, provider-reported contribution of knowledge context to `input_tokens` is invisible to `usage_snapshot`/`segment_tokens` |
| G11 | Internal/system tools (Ask User, rich elements) are gated by capability flags but are not distinguished from user tools in any way that survives into persisted usage data | `tool_registry.py`, `capabilities.py` | "Which tools contribute the most context overhead" cannot separate user-added vs. system-provided tool cost |
| G12 | No per-round usage inside the tool-calling loop is persisted — only the sum across up to `max_turns` rounds | `litellm.py:738-745` | Cannot see how many actual API round-trips a run took or their individual cost; conflates "one LLM call" with "one Run" throughout downstream analytics |
| G13 | `AI Model` doctype has no `context_window`/`max_tokens` fields — context-window fullness (`% of context window used`) relies on LiteLLM's internal table only, not a queryable HUF value | `ai_model.json` | Cannot reliably report "how close did this call get to the model's context limit" per-model in aggregate; current Run-detail `ContextBar` likely resolves this ad hoc, not as stored data |
| G14 | No cache-write price field on `AI Model` — cache-creation tokens are effectively unpriced in HUF's cost model | `ai_model.json`, `cost_calculator.py` | "How effective was caching, in dollars" undercounts caching's true cost when writes are billed by the provider (e.g., Anthropic 1.25x) |
| G15 | `cache_skipped_unsupported_model` is tracked in `usage_snapshot` JSON but has no matching flat column | `agent_run.json` | Cannot filter/aggregate "runs where caching silently didn't apply," a real degradation worth surfacing per the original request's "silent context consumption" theme |

**What's already correct and should not be redesigned:** the rollup pipeline's dimension model (`agent|provider|model|run_kind` + time bucket), the `Agent Run`/`Agent Conversation`/`Agent Message` relational structure, the `cost_calculator.py` priority chain (custom pricing → LiteLLM lookup → local/free → unknown), and the queue-first execution model's `sequence` field (a stable per-conversation ordering key independent of async timing — useful as-is for reconstructing turn order).

---

## 3. Target Analytics Model

The canonical unit of observability should remain **the Agent Run**, but two changes are required so higher-level views can be *derived* rather than separately maintained:

1. **Every Agent Run must carry a `conversation` FK usable as a rollup dimension** (it already exists as a field — it just needs to be added to the rollup's `dimension_key`/schema).
2. **Every Agent Run must carry a persisted, structured context-composition breakdown** (system / history / tools / knowledge-other) captured at the moment the call is made, not reconstructed later.

Canonical metrics, defined precisely to avoid the "summed input tokens vs. context size of latest call" ambiguity flagged in the request:

- **Run-level (atomic, one row per Agent Run):** `input_tokens`, `output_tokens`, `cached_tokens` (read), `cache_creation_tokens` (write), `total_tokens`, `cost`, `context_breakdown` (system/history/tools/other, each in tokens), `context_window_used_pct` (this run's total input ÷ the model's context window), `round_count` (number of internal LLM round-trips this run took), `latency_ms`.
- **Conversation-level (derived by aggregation over its Agent Runs, never separately stored as a source of truth):**
  - `sum(input_tokens)` across runs = **cumulative tokens billed for this conversation** — answers "what did this conversation cost so far."
  - `latest_run.context_breakdown` / `latest_run.input_tokens` = **current context size and composition** — answers "how big is this conversation's context right now." These are explicitly two different questions and both must be exposed, separately labeled, in any conversation UI.
  - `context growth curve` = `input_tokens` (or context_breakdown total) per run plotted against `run.sequence`, letting a UI point at exactly which turn caused a jump.
  - `cache_effectiveness` = `sum(cached_tokens) / sum(cached_tokens + cache_creation_tokens + uncached_input_tokens)` computed across the conversation's runs, not re-derived from `usage_snapshot` per run at read time.
- **Agent/Model/Provider-level:** identical aggregation logic reused via the rollup's existing dimension keys, extended with the new columns above. "Which agent has the highest cache hit rate" = `sum(cached_tokens)/sum(cache-eligible tokens)` grouped by `agent` over the rollup table — no new query pattern needed once the schema carries the fields.

---

## 4. Storage / Instrumentation Changes

All changes are additive to existing DocTypes — no new parallel analytics doctype hierarchy is proposed for atomic data. A new rollup dimension is required; that is the one structural addition.

### 4.1 `Agent Run` (`huf/huf/doctype/agent_run/agent_run.json`)

- **Promote to real Int columns** (currently JSON-only): `cache_creation_tokens`, `total_tokens`. Keep `usage_snapshot` as the detailed/versioned record, but stop treating flat columns and JSON as two different sources of truth — flat columns should be populated from the same values written into `usage_snapshot`, at write time, in `agent_integration.py`.
- **Fix G2**: stop writing `cache_creation_tokens` into `cache_miss_tokens`. Either compute a real cache-miss value (`input_tokens - cached_tokens - cache_creation_tokens`, i.e., context that was cache-eligible but not hit) or remove the field until it's real; do not ship a mislabeled duplicate.
- **Add `cache_skipped_unsupported_model` as a flat Check column** (currently JSON-only) so degraded-caching runs are filterable (G15).
- **Add `context_breakdown` (JSON)**: `{"system": int, "history": int, "tools": int, "knowledge": int, "other": int}`, in tokens, captured per-call (see 4.3 for how this is measured). This directly answers Section 2 of the request.
- **Add `context_window_used_pct` (Float)** or store `model_context_window` (Int, snapshotted from AI Model at call time — see 4.2) alongside `input_tokens`, so the percentage can be computed without a join and without depending on the model's current config (config may change after the run).
- **Add `round_count` (Int)**: number of internal LLM round-trips inside `litellm.py`'s tool-calling loop for this run (G12). Cheap — the loop already knows its own iteration count; just surface it into `total_usage`.
- **Add `provider_path` (Select: `litellm`/`legacy_fallback`)**: records whether this run went through the LiteLLM path or a legacy provider fallback (G3), so degraded-accounting runs are identifiable rather than silently blended into aggregates.

### 4.2 `AI Model` (`huf/huf/doctype/ai_model/ai_model.json`)

- **Add `context_window` (Int)** and **`max_output_tokens` (Int)**, sourced at model-creation time from LiteLLM's own model-cost table where available, editable for custom/local models. Needed for G13 — without this, "how close to the limit" can't be a first-class stored/aggregable metric.
- **Add `cached_input_write_cost_per_1m_tokens` (Float)** alongside the existing read-price field, so `cost_calculator.py` can price cache-creation tokens (G14) instead of treating them as free.

### 4.3 Context-breakdown capture (new instrumentation, not a new doctype)

This is the one genuinely new piece of capture logic. It should live where the final message list is assembled for the LLM call — `litellm.py`'s message-building section (`_build_text_content`, `_format_conversation_history`, and the tool-schema serialization call into `tool_serializer.serialize_tools()`), immediately before the call is dispatched:

- **System/Instructions tokens**: the assembled instructions string is already fully known at that point (`agent.instructions`, produced by `create_agent()`); token-count it with the same tokenizer LiteLLM uses for the target model (`litellm.token_counter`, already a dependency) rather than chars/4 heuristics.
- **Conversation history tokens**: token-count the exact message list passed as history for *this* call (already assembled by `conversation_manager.get_conversation_history`).
- **Tools tokens**: token-count the serialized JSON schema returned by `tool_serializer.serialize_tools()` for this call. Because internal/user tool distinction already exists structurally (`Agent Tool Function.category`, `capabilities.py`'s `ask_user`/`rich_elements`/`document_artifacts` gates — G11), tag each tool's schema with `source: user_configured | system_builtin | internal_capability` while summing, so `context_breakdown.tools` can optionally carry a `by_source` sub-object without a schema change (store as nested JSON).
- **Knowledge/other tokens**: replace the chars/4 estimate in `context_builder.py:81` with a real tokenizer count of `context_text`, and thread that number through into the run's `context_breakdown.knowledge` instead of discarding it (G10).
- All four numbers, summed, should reconcile closely with the provider-reported `input_tokens` for that round; log a warning (not a hard failure) if they diverge beyond a tolerance, since that's a strong signal of an uninstrumented context source (G8's "other meaningful categories" concern) that needs a new category.

This capture is a token-counting pass over data HUF already has at call time — it does not require an extra LLM round-trip and should add negligible latency (local tokenizer call, not a network call), addressing the "avoid materially increasing execution latency" requirement.

### 4.4 `Agent Run Analytics Rollup` (`huf/huf/doctype/agent_run_analytics_rollup/agent_run_analytics_rollup.json`)

- **Add `conversation` to the dimension set** (G5) so `_dimension_key()` in `agent_run_analytics.py` can bucket by conversation as well as agent/provider/model/run_kind. This is the single change that unlocks conversation-level rollups from the existing, already-correct rollup engine, rather than building a parallel aggregation path.
- **Add `cache_creation_tokens` and `context_breakdown_totals` (JSON, summed system/history/tools/knowledge across the bucket)** to the rollup row, so conversation/agent/model-level "what consumes context" questions don't require scanning raw runs.

### 4.5 `Agent Conversation`

No schema change required. Its existing `total_input_tokens`/`total_output_tokens`/`total_tokens`/`total_cost` running counters remain useful as a cheap, always-current summary (avoids a rollup-table read for the conversation header), but the UI must not treat them as authoritative for anything beyond "cumulative totals" — trend/composition/per-turn views must come from the rollup or from querying the conversation's Agent Run rows directly, per the semantics distinction in Section 3.

---

## 5. Aggregation Architecture

Keep the existing two-tier design — it's the right shape, it just needs its dimension set widened:

1. **Atomic layer**: `Agent Run` rows, now carrying `context_breakdown`, `round_count`, `cache_creation_tokens` as real fields (Section 4.1). This remains the single source of truth; nothing above it stores independently-computed numbers that could drift from it.
2. **Rollup layer**: `Agent Run Analytics Rollup`, extended with a `conversation` dimension and the new summed fields (Section 4.4), recomputed by the existing `refresh_rollups()`/`_recompute_rollup()` machinery in `agent_run_analytics.py` — no new scheduler/job needed, just a wider `_dimension_key()`.
3. **API layer**: `agent_run_analytics_api.py::get_execution_analytics` extended to accept `dimension=agent|provider|model|conversation|run_kind` (currently hardcoded to provider-only breakdown) and to return `context_breakdown` sums alongside token/cost sums. `agent_run_context_api.py` remains the correct place for genuinely single-run detail (prefix-stability comparison against the immediately-prior run) — it should not be merged into the aggregate API, since its semantics are deliberately per-run.
4. **Frontend consumption**: a single shared analytics service (extending `executionAnalyticsApi.ts`, not `dashboardApi.ts`'s raw-fetch pattern) should back Run/Conversation/Agent/Model/Provider views alike, parameterized by dimension and drill-down filter. `dashboardApi.ts`'s client-side reduction over up to 10k rows should be retired in favor of this same rollup-backed path (closes G6), even for the HomePage's simple "last 7 days" tiles.

This avoids duplicating or corrupting semantics because every higher-level number is either (a) a `SUM`/`AVG` over the atomic `Agent Run` rows via the rollup, using the exact same field definitions at every level, or (b) explicitly labeled as a "latest snapshot" value (e.g., current context size) rather than a sum, per the Section 3 semantics rule.

---

## 6. Conversation Analytics Design

**Conversation totals and trends:**
- Run/model-call count: `count(Agent Run)` for the conversation, split by `run_kind` (agent turns vs. internal tool/orchestrator sub-runs).
- Total input / total output / total cached: `SUM` over the conversation's runs — explicitly labeled "cumulative, billed" totals.
- **Current context size and composition**: the *latest* run's `input_tokens` and `context_breakdown` — explicitly labeled "current," not summed. This is the number that answers "what does this conversation's context look like right now."
- Context growth curve: `context_breakdown` totals (or plain `input_tokens`) per run, plotted against `Agent Run.sequence` (already a stable per-conversation ordering key, robust to the queue-first async gap). Points where the delta from the previous run is disproportionately large are flagged as "major context growth" turns — computable purely from consecutive-row deltas, no new storage needed.
- Percentage breakdown (system / history / tools / knowledge-other) as a stacked view, both for the latest call and as a trend over the conversation's runs — sourced directly from `context_breakdown` (Section 4.3).
- Cache effectiveness for the conversation: `sum(cached_tokens) / sum(cached_tokens + cache_creation_tokens + estimated_cache_miss)`, distinct from a single run's `cache_metrics.py` ratio, computed by summing the same underlying fields across the conversation's runs rather than averaging per-run ratios (averaging ratios would be a second aggregation-semantics trap worth avoiding explicitly).
- Context-window proximity: `MAX(context_window_used_pct)` and the run(s) that hit it, using the new `context_window_used_pct`/`model_context_window` snapshot fields (Section 4.1) so this is model-config-change-proof.
- "Repeated vs. newly introduced" context: approximated via `prefix_stability` (already computed per-run by `cache_metrics.py` from consecutive-run prefix-hash breakpoints) rolled up across the conversation, plus the cache-read share as a proxy for "how much of this call's input was identical to the previous call's."

**Drill-down:** every conversation-level chart/tile must link to the underlying list of Agent Runs (already supported by `agent` FK-style querying patterns used elsewhere, e.g. `AgentRunDetailPage`'s child-runs table) filtered to that conversation and ordered by `sequence`, and from there into the existing per-run `AgentRunDetailPage` view — reusing the page/detail navigation pattern already established for parent/child runs.

---

## 7. UI / Visualization Design

- **Run Analytics** (extend `AgentRunDetailPage.tsx`): keep the existing Overview/Tokens & Cost/Context panels; extend the Context card to render the new `context_breakdown` as a stacked bar (system/history/tools/knowledge) instead of only the current `segment_tokens` bar, and surface `round_count` and `provider_path` (flagging legacy-fallback runs, G3) as additional metadata chips.
- **Conversation Analytics** (new page/tab, e.g. `/chat/:chatId` analytics panel or a dedicated `/conversations/:id/analytics` route consistent with existing routing conventions): summary tiles (total runs, total cost, total tokens, cache effectiveness) + a context-growth line/area chart (finally using `recharts`, already available via `components/ui/chart.tsx` but currently unused for analytics, G7) + a stacked context-composition chart + a per-run table identical in spirit to the existing child-runs table on `AgentRunDetailPage`, sortable by contribution to context growth.
- **Agent Analytics**: aggregate tiles + breakdown by model, reusing the extended `get_execution_analytics(dimension="agent")`, plus an "average conversation cost for this agent" derived metric (`SUM(cost)/COUNT(DISTINCT conversation)` at the rollup layer once the conversation dimension exists).
- **Model Analytics**: usage/cost/cache-effectiveness by model, plus `context_window_used_pct` distribution to show how close real workloads run to each model's limit — the first place the new `AI Model.context_window` field becomes directly useful.
- **Provider Analytics**: extends the existing `provider_by_name` breakdown already computed (but not fully surfaced) by `get_execution_analytics`, adding `provider_path` split (litellm vs. legacy fallback) to expose reliability of accounting itself as a provider-level signal.
- **Cross-linking**: every level should support click-through to the next level down (Provider → Model → Agent → Conversation → Run), consistent with the existing pattern where `AgentRunDetailPage` already links parent/child runs — this is a navigation convention to extend, not invent.

---

## 8. Migration / Compatibility Considerations

- **Historical data**: existing `Agent Run` rows will have `context_breakdown = null` and `cache_creation_tokens`/`total_tokens` only in `usage_snapshot` JSON (not yet promoted to columns) or absent entirely for very old rows. Conversation/composition analytics should treat `context_breakdown IS NULL` as "pre-instrumentation" and either exclude such runs from composition charts (with an explicit "no data before <date>" note) or backfill `total_tokens`/`cache_creation_tokens` columns from existing `usage_snapshot` JSON via a one-time migration patch (feasible — the JSON already has the values; only the new `context_breakdown` genuinely cannot be backfilled since it requires re-tokenizing inputs that weren't captured).
- **Rollup backfill**: extending `_dimension_key()` with `conversation` requires a one-time `refresh_rollups(full_backfill=True)` re-run (the mechanism already exists — `agent_run_analytics_api.py` already triggers this lazily when a rollup window is empty) to populate the new dimension for historical runs; new fields (`cache_creation_tokens`, `context_breakdown_totals` sums) on the rollup will similarly backfill as `null`/`0` for pre-instrumentation runs and real from the migration date forward.
- **New metrics only available going forward**: context composition (system/history/tools/knowledge split), `round_count`, `context_window_used_pct`, and true cache-write cost pricing are all only available for runs captured after this instrumentation ships — they cannot be reconstructed retroactively (the underlying token-count inputs weren't preserved). This should be called out explicitly in any conversation/context UI ("composition data available from <ship date>").
- **No breaking change to existing consumers**: `usage_snapshot`'s existing keys are preserved as-is; new keys are additive. Flat-column promotion (`cache_creation_tokens`, `total_tokens`) adds columns without removing the JSON copy, so any code reading the JSON today continues to work unchanged.

---

## 9. Implementation Plan

Phased, ordered by dependency. Each phase references the exact files to change.

**Phase 1 — Fix correctness bugs in existing accounting (no schema change, safe to ship first)**
- `huf/ai/providers/litellm.py:1047` — stop aliasing `cache_creation_tokens` into `cache_miss_tokens`; either compute a real miss value or drop the field.
- `huf/ai/agent_integration.py:1917-1918` (+ streaming duplicate ~2900-2962) — same fix, persistence side.
- Consolidate the three independent usage-extraction implementations (`litellm.py:912-929`, `litellm.py:998-1047`, `agent_integration.py:1789-1852`) into one shared helper function to prevent further drift (G1).

**Phase 2 — Schema additions**
- `huf/huf/doctype/agent_run/agent_run.json`: promote `cache_creation_tokens`, `total_tokens` to Int columns; add `cache_skipped_unsupported_model` (Check), `context_breakdown` (JSON), `context_window_used_pct` (Float) or `model_context_window` (Int), `round_count` (Int), `provider_path` (Select).
- `huf/huf/doctype/ai_model/ai_model.json`: add `context_window` (Int), `max_output_tokens` (Int), `cached_input_write_cost_per_1m_tokens` (Float).
- `huf/huf/doctype/agent_run_analytics_rollup/agent_run_analytics_rollup.json`: add `conversation` (Link), `cache_creation_tokens` (Int), `context_breakdown_totals` (JSON).
- Write a Frappe patch (`huf/patches/...`) to backfill `cache_creation_tokens`/`total_tokens` columns from existing `usage_snapshot` JSON for historical rows.

**Phase 3 — Capture instrumentation**
- `huf/ai/providers/litellm.py`: add real tokenizer counts (via `litellm.token_counter`) for the assembled system instructions, conversation history slice, and serialized tool schemas immediately before dispatch; surface `round_count` from the existing loop counter.
- `huf/ai/knowledge/context_builder.py`: replace the chars/4 heuristic with a real tokenizer count and return it to the caller instead of discarding it.
- `huf/ai/agent_integration.py`: thread the four `context_breakdown` numbers, `round_count`, and `provider_path` into the same persistence block that already writes `usage_snapshot` (`agent_integration.py:1907-1927`, and its streaming duplicate) — no new persistence codepath, extend the existing one.
- `huf/ai/cost_calculator.py`: accept and price `cache_creation_tokens` against the new `cached_input_write_cost_per_1m_tokens` field.

**Phase 4 — Rollup and API extension**
- `huf/ai/agent_run_analytics.py`: extend `_dimension_key()`/`_recompute_rollup()` to include `conversation` and the new summed fields.
- `huf/ai/agent_run_analytics_api.py`: extend `get_execution_analytics` to accept a `dimension` parameter (agent/provider/model/conversation/run_kind) and return `context_breakdown` sums.
- Run `refresh_rollups(full_backfill=True)` against the new dimension.

**Phase 5 — Frontend**
- Extend `frontend/src/services/executionAnalyticsApi.ts` with a conversation-analytics call and a generic `dimension` parameter; deprecate the raw-fetch pattern in `dashboardApi.ts` in favor of this shared service (closes G6).
- Build the Conversation Analytics view (Section 7) using `recharts` via the existing `components/ui/chart.tsx` wrapper (closes G7 — first real use of already-available charting infra for analytics).
- Extend `AgentRunDetailPage.tsx`'s Context card to render `context_breakdown` as a stacked composition bar; add `round_count`/`provider_path` chips.
- Add Agent/Model/Provider analytics views reusing the same shared components, parameterized by dimension.

**Phase 6 — Validation and rollout**
- Confirm `context_breakdown` sums reconcile with provider-reported `input_tokens` within tolerance on a sample of live runs across each supported provider; log (not fail) on divergence to catch an uninstrumented context source.
- Confirm rollup backfill completes correctly for a historical window before enabling the conversation-dimension UI.
- Document the "pre-instrumentation" data boundary in the UI per Section 8.

---

## References

All findings above are grounded in direct reads of, at minimum:
`huf/ai/providers/litellm.py`, `huf/ai/providers/{openrouter,anthropic,google}.py`, `huf/ai/run.py`, `huf/ai/agent_integration.py`, `huf/ai/conversation_manager.py`, `huf/ai/prompt_resolver.py`, `huf/ai/sdk_tools.py`, `huf/ai/tool_registry.py`, `huf/ai/tool_serializer.py`, `huf/ai/tools/_registry.py`, `huf/ai/tools/ask_user.py`, `huf/ai/capabilities.py`, `huf/ai/cache_metrics.py`, `huf/ai/cost_calculator.py`, `huf/ai/prompt_cache_capabilities.py`, `huf/ai/knowledge/context_builder.py`, `huf/ai/knowledge/retriever.py`, `huf/ai/agent_run_analytics.py`, `huf/ai/agent_run_analytics_api.py`, `huf/ai/agent_run_context_api.py`; DocType JSONs for `agent_run`, `agent_conversation`, `agent_message`, `agent_tool_call`, `ai_model`, `agent_run_analytics_rollup`; and frontend files `frontend/src/services/{dashboardApi,agentRunApi,executionAnalyticsApi}.ts`, `frontend/src/pages/{AgentRunDetailPage,HomePage}.tsx`, `frontend/src/components/executions/ExecutionAnalyticsDashboard.tsx`, `frontend/src/components/ui/{context-bar,chart}.tsx`.
