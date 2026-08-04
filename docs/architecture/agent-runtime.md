# Agent Runtime

The agent runtime is the code path from a stored `Agent` DocType to a model response: resolving provider/model settings, assembling tools and conversation history, calling out to LiteLLM, and persisting the result as an `Agent Run`. Execution is queue-first by default — most calls enqueue a run and a per-conversation drainer executes it — with a direct/streaming path reserved for agents that opt in.

## Domain model

| DocType | Role | Key files |
|---|---|---|
| `AI Provider` | Credentials + connection config for one LLM vendor (API key, base URL, `is_local_llm`, `provider_brand`) | `huf/huf/doctype/ai_provider/` |
| `AI Model` | A specific model tied to a provider | `huf/huf/doctype/ai_model/` |
| `Agent` | Central entity: instructions, provider/model, tools, temperature/top_p, triggers, `enable_prompt_caching` and related fields, `run_immediately` policy | `huf/huf/doctype/agent/agent.py` |
| `Agent Conversation` | One conversation thread for an agent (session/channel scoped) | `huf/huf/doctype/agent_conversation/agent_conversation.py` |
| `Agent Message` | One turn (user/assistant/tool) in a conversation | `huf/huf/doctype/agent_message/agent_message.py` |
| `Agent Run` | One execution record: status (`Queued`/`Started`/`Success`/`Failed`), timing, token usage, response | `huf/huf/doctype/agent_run/agent_run.py`, `huf/huf/doctype/agent_run/agent_run.json:81` |
| `Agent Chat` | Thin UI-facing wrapper linking a `conversation` to an `agent` for the chat frontend | `huf/huf/doctype/agent_chat/agent_chat.py`, `huf/huf/doctype/agent_chat/agent_chat.json:15` |

All five DocType controllers (`AgentConversation`, `AgentMessage`, `AgentChat`) are currently empty `Document` subclasses (`pass`) — the behavior lives in the whitelisted API modules below, not in DocType hooks. `Agent Chat` itself carries almost no logic; the chat backend (`huf/ai/agent_chat.py`) loads it purely to resolve `conversation` and `agent` (`huf/ai/agent_chat.py:36`, `:319`, `:549`).

**Correction to the old AGENTS.md**: the previous "Core Concepts" section described `Agent Tool Function` as part of the numbered core-concept list and folded tools into step 3. Tools are a separate, larger topic (CRUD tools, MCP, skills, knowledge) — see the tools doc rather than this one. This doc only covers what executes an agent turn.

See `docs/reference/doctypes.generated.md` for full field tables of all of the above.

## Core classes and methods

The old AGENTS.md described a file called `agent_integration.py` containing `AgentManager` and `run_agent_sync` — that part was correct and still holds, but several details around it (an `agents_SDK`-only execution model, no queueing, no streaming split) are stale. The runtime today spans `huf/ai/agent_integration.py` (3362 lines), `huf/ai/run.py`, `huf/ai/providers/litellm.py`, `huf/ai/conversation_manager.py`, and `huf/ai/agent_stream_renderer.py`.

| Class / function | File:line | Role |
|---|---|---|
| `AgentManager` | `huf/ai/agent_integration.py:91` | Resolves effective provider/model, loads the `AI Provider` doc, builds the tool list, configures the OpenAI-Agents-SDK client |
| `AgentManager._setup_tools` | `huf/ai/agent_integration.py:113` | Merges CRUD tools (`sdk_tools.create_agent_tools`), skill/agent MCP tools, the skills-listing tool, and knowledge-search tools into `self.tools` |
| `AgentManager._setup_client` | `huf/ai/agent_integration.py:203` | Builds an `OpenAIProvider` (from the `agents` SDK) from the `AI Provider` doc's API key / base URL |
| `AgentManager.create_agent` | `huf/ai/agent_integration.py:332` | Constructs the `agents.Agent` object (instructions, model, tools, model settings) used for the run |
| `run_agent_sync(...)` | `huf/ai/agent_integration.py:915` | Whitelisted entry point. Validates the agent, resolves provider/model, gets/creates the `Agent Conversation`, then either queues a run or executes it directly |
| `_execute_agent_run(...)` | `huf/ai/agent_integration.py:1302` | Shared execution body for both the direct and queued paths: loads history, builds the `AgentManager`/`agents.Agent`, calls `RunProvider.run`, persists the response and run status |
| `run_agent_stream(...)` | `huf/ai/agent_integration.py:2400` | Async generator variant of the same flow; yields `delta`/`tool_call`/`complete`/`error` chunks instead of returning a single result |
| `RunProvider.run` / `RunProvider.run_stream` | `huf/ai/run.py:15`, `huf/ai/run.py:80` | Routes to `huf/ai/providers/litellm.py` for all standard providers; falls back to a `huf.ai.providers.<provider>` module only if LiteLLM raises |
| `providers/litellm.py: run` | `huf/ai/providers/litellm.py` (search `def run`) | Builds the message list (system/history/user, with cache-control blocks), normalizes the model name, calls LiteLLM `completion`, loops on tool calls |
| `ConversationManager` | `huf/ai/conversation_manager.py` | `get_or_create_conversation`, `create_new_conversation`, `add_message`, `get_conversation_history`, `repair_message_sequence` — conversation and message persistence, plus OpenAI-compatible history repair before every LiteLLM call |
| `AgentStreamRenderer` | `huf/ai/agent_stream_renderer.py:19` | Frappe website page renderer that exposes `run_agent_stream` over SSE |

### Queue-first execution (the significant behavior change vs. the old doc)

The old "Core Classes and Methods" section already flagged queue-first behavior in prose, but described it as an addendum rather than the default control flow, and the SSE section made no mention of it at all — that's the main gap this doc closes.

`run_agent_sync` (`huf/ai/agent_integration.py:915`) is queue-first by default:

1. Validates the agent (`disabled`, guest access via `allow_guest`, per-user access via `_is_user_allowed`) — `huf/ai/agent_integration.py:940-960`.
2. Resolves provider/model via `_resolve_effective_model` (`huf/ai/agent_integration.py:40`).
3. Gets or creates the `Agent Conversation` through `ConversationManager` (persisted vs. ephemeral depending on `agent_doc.persist_conversation`).
4. Persists an `Agent Run` in status `Queued` with a per-conversation `sequence` number.
5. A single-flight per-conversation drainer (`_drain_run`, `_run_queued_agent`, `huf/ai/agent_integration.py:2244`, `:2194`) executes queued runs in FIFO order and publishes `agent_run_status` lifecycle events (`_emit_run_lifecycle_event`, `huf/ai/agent_integration.py:517`) — `Queued` → `Started` → `Success`/`Failed`.
6. Callers can poll `get_agent_run_status` (`huf/ai/agent_integration.py:1190`).

Direct/inline execution (bypassing the queue) requires either the caller passing `now=true` or the agent's `run_immediately` policy field being set. It still takes the same per-conversation lock (`_conversation_lock_key`, `huf/ai/agent_integration.py:2113`), re-checks state under the lock, and must never be called from code that might already hold that lock (e.g. sub-agent completion hooks) — doing so deadlocks. `recover_stalled_agent_runs` (`huf/ai/agent_integration.py:2336`) exists to un-stick runs left in `Started`/`Queued` by crashed workers.

Both paths converge on `_execute_agent_run` (`huf/ai/agent_integration.py:1302`), which:

- Loads bounded conversation history (`agent_doc.history_limit` + buffer) via `ConversationManager.get_conversation_history`, trimming the just-persisted user turn out of history since `prompt` already carries it.
- Optionally kicks off multi-run orchestration instead of a normal completion, when `agent_doc.enable_multi_run` is set and the channel isn't already an orchestration channel.
- Builds the `AgentManager` and the SDK `Agent` object, injects mandatory knowledge context if configured, then calls `RunProvider.run(agent, enhanced_prompt, resolved_provider, resolved_model_name, context)` at `huf/ai/agent_integration.py:1542`.
- Persists the assistant response as an `Agent Message`, updates the `Agent Run` to `Success`/`Failed`, and emits the final lifecycle event.

## Conversation history and tool-call rounds

`ConversationManager.get_conversation_history` (`huf/ai/conversation_manager.py:517`) fetches the last N `Agent Message` rows for a conversation and rebuilds them into OpenAI-compatible assistant/tool-call pairs. Because history is persisted incrementally and can be truncated at a limit, `repair_message_sequence` (`huf/ai/conversation_manager.py:229`) runs before every LiteLLM call (both in the non-streaming and streaming paths in `providers/litellm.py`) to drop unfulfilled assistant `tool_calls` and reattach orphaned tool results from `Agent Tool Call` records where possible — this guards against sending a malformed message sequence after truncation or a crash mid-tool-call.

Within a single run, `providers/litellm.py` loops over LLM completions to support multi-turn tool calling: `MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10`, then `for round_num in range(MAX_ROUNDS)` (`huf/ai/providers/litellm.py:664-671` for the non-streaming path, `:1512-1521` for streaming). Each round can produce further tool calls, which are executed and fed back in, until the model returns a final answer or the round limit is hit.

## Streaming (SSE)

The old AGENTS.md's "Streaming Architecture" section is largely still accurate on wire format, but wrong on availability: it presented SSE as generally available for any agent. In the current code, streaming is a direct-execution escape hatch gated on the agent's `run_immediately` policy.

`AgentStreamRenderer` (`huf/ai/agent_stream_renderer.py:19`) is a Frappe `BaseRenderer` for two paths:

- `GET/POST /huf/stream/<agent_name>` — the actual SSE endpoint.
- `GET /huf/stream` — an HTML demo page with a JS `EventSource` client, for manual testing.
- `/huf/stream/ping` — lightweight liveness check (`_render_ping`, `huf/ai/agent_stream_renderer.py:279`).

`_render_agent_stream` (`huf/ai/agent_stream_renderer.py:77`) enforces, before touching `run_agent_stream`:

1. **Run Immediately required**: if `agent_doc.run_immediately` is falsy, it returns an SSE `error` event telling the caller the agent runs queue-first and to use the standard chat API instead (`huf/ai/agent_stream_renderer.py:164-169`).
2. **Queue ordering parity**: if the target conversation already has queued runs pending (`_has_queued_runs`), the stream refuses to run ahead of them and returns an error event, unless the stream is starting a brand-new conversation (`huf/ai/agent_stream_renderer.py:184-193`).

Once past those checks, it wraps the async generator `run_agent_stream` (`huf/ai/agent_integration.py:2400`) into a synchronous generator (`asyncio.new_event_loop()` + `run_until_complete` per chunk) for Werkzeug's `Response`, and serializes each chunk as an SSE `data:` line — no custom event names, just JSON payloads with a `type` field, matching the old doc's format description.

### Event shape

Each SSE chunk is `data: <json>\n\n` where the JSON has:

- `type`: one of `"delta"`, `"tool_call"`, `"complete"`, `"error"` (`huf/ai/agent_integration.py:2400` docstring; verified against actual `yield` sites throughout `run_agent_stream`, e.g. `huf/ai/agent_integration.py:2442`, `:2998`, `:3136`).
- `content` / `full_response`: partial and accumulated text, for `delta`.
- `tool_call`: tool invocation details, for `tool_call`.
- `error`: error string, for `error`.

The stream loop stops as soon as it sees `type` in (`"complete"`, `"error"`) (`huf/ai/agent_stream_renderer.py:238-239`).

`run_agent_stream` shares conversation management and run tracking with `run_agent_sync` — same `ConversationManager`, same `Agent Run`/`Agent Conversation` records — it just yields incrementally instead of returning once.

## Prompt caching

The old AGENTS.md's one-paragraph "Prompt Caching" section undersold how granular this is; caching is controlled per content segment, not as a single on/off switch.

**Support check** — `model_supports_prompt_caching(model_name, provider_name)` (`huf/ai/prompt_cache_capabilities.py:18`) is purely data-driven: it scans `litellm.model_cost` for an entry matching the model name and checks whether `cache_read_input_token_cost` is present. No hardcoded model allowlist — a new model automatically qualifies once LiteLLM ships pricing for it.

**Enablement** — controlled by fields on `Agent` (`huf/huf/doctype/agent/agent.json:28,589-617`):

- `enable_prompt_caching` — master toggle.
- `cache_control_type` — cache-control block type (defaults to `"ephemeral"`).
- `cache_system_message`, `cache_static_prefix`, `cache_conversation_history` — per-segment toggles for whether the system prompt, an optional static prefix, and conversation history each get cache-control markers.

**Where it's applied** — `huf/ai/providers/litellm.py` (`def run`, around line 537, and the streaming variant around line 1283) reads these fields per call and:

- Disables caching outright for local/custom endpoints (`is_local_llm`) since they don't support cache-control blocks (`huf/ai/providers/litellm.py:557`-ish region).
- Calls `model_supports_prompt_caching` once per run and short-circuits all caching if the model isn't supported (`cache_skipped_unsupported_model`).
- Builds the message list with `_build_text_content(...)`, passing a per-segment `*_cache_enabled` flag — static prefix, system instructions, conversation history, and the final dynamic user content each get their own enable/disable decision (`huf/ai/providers/litellm.py:585-631`).
- Runtime overrides can come through `prompt_cache_options` (parsed by `_parse_prompt_cache_options` / `_resolve_prompt_cache_options`, `huf/ai/agent_integration.py:562`, `:580`), which layers site-config defaults (`huf_prompt_cache_defaults` in `frappe.conf`, with per-channel overrides) under any per-call overrides — e.g. `openai_prompt_cache_retention`, `gemini_cached_content`, `static_prefix`/`dynamic_suffix`, `cache_dynamic_content`.

**Correction to the old AGENTS.md**: the previous text said prompt caching applies "on supported providers (Anthropic, Deepseek, OpenAI, Bedrock)" as if that were a hardcoded provider list. That's not how the current implementation decides support — it's purely the LiteLLM pricing-metadata check above, so any provider/model LiteLLM prices for cache reads qualifies, not a fixed set of four vendors.

## See also

- `docs/reference/doctypes.generated.md` — full field tables for `Agent`, `Agent Conversation`, `Agent Message`, `Agent Run`, `Agent Chat`, `AI Provider`, `AI Model`.
