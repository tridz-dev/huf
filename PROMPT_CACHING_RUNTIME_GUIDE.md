# Huf Runtime Prompt Caching Guide (Static + Dynamic Mix)

This document explains, in plain language, what was added in this PR, what was missing before, what is now possible, and how to use it in real Huf scenarios (API, streaming chat, and trigger-driven runs).

---

## 1) Why this PR exists

Huf already had agent-level prompt caching toggles in the Agent DocType (UI), but that was not enough for teams that need:

- different caching behavior by **channel/trigger** (`api`, `chat`, `doc_event`, `schedule`, `flow`, `sse_stream`, etc.)
- **static vs dynamic** segmentation for better cache hit rates
- provider-specific controls like:
  - OpenAI/Deepseek `prompt_cache_retention`
  - Gemini explicit `cached_content` reuse
- the same behavior in **streaming** and non-streaming paths without adding new UI fields

In short: teams needed backend/runtime control for cost optimization across trigger types.

---

## 2) What was missing before

Before this PR:

1. `run_agent_sync` and `run_agent_stream` did not support passing a runtime cache policy payload.
2. There was no central way to set channel-level cache defaults from site config.
3. Provider execution did not support explicit runtime static/dynamic segmentation controls.
4. SSE endpoint (`/huf/stream/<agent_name>`) did not pass prompt-cache options down to `run_agent_stream`.

---

## 3) What changed in Huf

## 3.1 Runtime cache options in `agent_integration.py`

Added:

- `_parse_prompt_cache_options(...)`
- `_resolve_prompt_cache_options(channel_id, prompt_cache_options=None)`

These functions:

- accept dict or JSON string input
- merge runtime options on top of site defaults from `huf_prompt_cache_defaults`
- support per-channel defaults (`default` + `channels.<channel_id>`)

Both of these APIs now accept `prompt_cache_options`:

- `run_agent_sync(...)`
- `run_agent_stream(...)`

Resolved options are injected into provider context as:

```python
context["prompt_cache_options"] = {...}
```

So every path that uses these functions can leverage it.

---

## 3.2 Provider behavior in `huf/ai/providers/litellm.py`

Added runtime-aware handling for:

- `static_prefix`
- `dynamic_suffix`
- `cache_static_prefix`
- `cache_dynamic_content`
- `openai_prompt_cache_retention`
- `gemini_cached_content`

Also added helper `_build_text_content(...)` to normalize provider message payload format.

### Behavior summary

- If `static_prefix` is set, it is injected as a **system** block before user content.
- If `dynamic_suffix` is set, it becomes the dynamic user part; otherwise it falls back to `enhanced_prompt`.
- `cache_static_prefix` and `cache_dynamic_content` can override what is marked cacheable (subject to provider/model support).
- For OpenAI/Deepseek, `prompt_cache_retention` is forwarded.
- For Gemini/Google, `cached_content` is forwarded for explicit cache object reuse.

---

## 3.3 Streaming endpoint wiring (`huf/ai/agent_stream_renderer.py`)

The SSE renderer now accepts and forwards `prompt_cache_options` from:

- query/form data
- JSON POST body

and passes it into:

```python
run_agent_stream(..., prompt_cache_options=prompt_cache_options)
```

This closes the gap so streaming can use the same runtime controls.

---

## 4) What is now possible

You can now do cost-saving strategies like:

1. Keep a large, stable corpus in `static_prefix` (hotel list, policy text, product catalog slice).
2. Send only changing request data in `dynamic_suffix` (dates, budget, user preference, event payload).
3. Set defaults globally/per-channel in site config, then override per-call only where needed.
4. Use the same approach in:
   - direct API calls
   - chat
   - streaming SSE
   - doc-event/scheduled/flow runs (because they go through `run_agent_sync`)

---

## 5) Runtime option contract

`prompt_cache_options` supports:

```json
{
  "static_prefix": "stable content...",
  "dynamic_suffix": "request-specific content...",
  "cache_static_prefix": true,
  "cache_dynamic_content": false,
  "openai_prompt_cache_retention": "24h",
  "gemini_cached_content": "cachedContents/abc123"
}
```

Notes:

- Unknown keys are ignored.
- Provider/model must still support caching.
- Existing agent-level toggles still apply; these options are runtime overrides/enhancements.

---

## 6) Site-wide/channel defaults (non-UI control)

Add this to site config (`site_config.json`) if desired:

```json
{
  "huf_prompt_cache_defaults": {
    "default": {
      "cache_static_prefix": true,
      "cache_dynamic_content": false
    },
    "channels": {
      "api": {
        "openai_prompt_cache_retention": "6h"
      },
      "doc_event": {
        "openai_prompt_cache_retention": "24h"
      },
      "sse_stream": {
        "openai_prompt_cache_retention": "24h"
      }
    }
  }
}
```

Runtime call options always override these defaults.

---

## 7) Example: Python API call (sync) with static+dynamic mix

```python
import frappe
import json

HOTEL_STATIC = """
You are a hotel recommendation assistant.
Rank hotels for business travelers.
Prefer metro access, strong wifi, clean modern rooms.

Hotels in Dubai:
1. Jumeirah Emirates Towers | DIFC | AED 980
2. Conrad Dubai | Sheikh Zayed Road | AED 860
3. Rove Trade Centre | Trade Centre | AED 520
"""

dynamic = """
User trip dates: 2026-05-10 to 2026-05-14
Budget: AED 700-1000
Preference: near DIFC/Sheikh Zayed + strong wifi + metro
Return top 3 with one-line reason each.
"""

result = frappe.call(
    "huf.ai.agent_integration.run_agent_sync",
    agent_name="Dubai Hotel Agent",
    channel_id="api",
    prompt="Use the provided criteria and answer.",
    prompt_cache_options={
        "static_prefix": HOTEL_STATIC,
        "dynamic_suffix": dynamic,
        "cache_static_prefix": True,
        "cache_dynamic_content": False,
        "openai_prompt_cache_retention": "24h"
    }
)

print(json.dumps(result, indent=2))
```

---

## 8) Example: SSE streaming with prompt cache options

### GET style (query param)

```javascript
const options = {
  static_prefix: "Stable domain rules and hotel corpus...",
  dynamic_suffix: "Trip dates, budget, and user prefs...",
  cache_static_prefix: true,
  cache_dynamic_content: false,
  openai_prompt_cache_retention: "24h"
};

const url = `/huf/stream/${encodeURIComponent("Dubai Hotel Agent")}`
  + `?prompt=${encodeURIComponent("Recommend best hotels")}`
  + `&prompt_cache_options=${encodeURIComponent(JSON.stringify(options))}`;

const es = new EventSource(url);
es.onmessage = (evt) => console.log(JSON.parse(evt.data));
```

### POST style

```javascript
await fetch(`/huf/stream/${encodeURIComponent("Dubai Hotel Agent")}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    prompt: "Recommend best hotels",
    prompt_cache_options: {
      static_prefix: "Stable domain rules and hotel corpus...",
      dynamic_suffix: "Trip dates, budget, and user prefs...",
      cache_static_prefix: true,
      cache_dynamic_content: false,
      openai_prompt_cache_retention: "24h"
    }
  })
});
```

---

## 9) Example: Huf Agent + trigger combination (doc event + chat)

Imagine one agent:

- Agent name: `Travel Procurement Assistant`
- Used by:
  - **Doc Event trigger** on `Travel Request` submission
  - **Chat** for employee follow-up questions

Use one stable static block (policy + preferred hotels), and dynamic content per channel:

### A) Doc Event hook path (dynamic from document)

```python
# in your custom hook / server logic
from huf.ai.agent_integration import run_agent_sync

static_policy = """
Company travel policy for Dubai:
- Prefer approved hotels list first
- Require metro access and stable wifi for business trips
- Budget bracket rules...
"""

def on_travel_request_submit(doc, method=None):
    dynamic = f"""
Travel Request: {doc.name}
Employee: {doc.employee}
Dates: {doc.from_date} to {doc.to_date}
Budget: {doc.budget}
Special requirements: {doc.special_requirements or "None"}
"""

    run_agent_sync(
        agent_name="Travel Procurement Assistant",
        prompt="Recommend approved hotel options and rationale.",
        channel_id="doc_event",
        prompt_cache_options={
            "static_prefix": static_policy,
            "dynamic_suffix": dynamic,
            "cache_static_prefix": True,
            "cache_dynamic_content": False,
            "openai_prompt_cache_retention": "24h"
        }
    )
```

### B) Chat path (dynamic from live user query)

```python
run_agent_sync(
    agent_name="Travel Procurement Assistant",
    prompt="I need options closer to DIFC this time.",
    channel_id="chat",
    prompt_cache_options={
        "static_prefix": static_policy,
        "dynamic_suffix": "User follow-up: closer to DIFC, same budget and dates.",
        "cache_static_prefix": True,
        "cache_dynamic_content": False
    }
)
```

Result: same stable policy block reused, dynamic asks remain small and change per interaction.

---

## 10) Reasoning behind design

Why this approach:

1. **No schema/UI migration required** for immediate adoption.
2. Keeps compatibility with existing Agent toggles.
3. Provides a pragmatic backend escape hatch for advanced cost optimization.
4. Works with existing execution architecture (`run_agent_sync` / `run_agent_stream`), so it naturally spans trigger types.

---

## 11) Known limits / what can be improved next

Good next steps:

1. **UI support (optional)**  
   Add advanced panel to define per-channel runtime caching templates directly in Desk.

2. **Validation + typing**  
   Add strict schema validation for `prompt_cache_options` and descriptive errors.

3. **Observability**  
   Persist effective cache options + retention/cached-content refs into `Agent Run` for auditing.

4. **Provider-specific adapters**  
   Add richer Gemini cache lifecycle helpers (create/list/expire) and explicit cache object management APIs.

5. **Policy presets**  
   Allow reusable named cache policies (e.g., `travel_policy_v3`) with role-based access.

---

## 12) Quick checklist for production usage

- Keep `static_prefix` byte-stable whenever possible.
- Keep dynamic details out of static block.
- Start with `cache_dynamic_content=false` for best static hit ratio.
- Use channel defaults in site config for consistency.
- Add per-call overrides only for special cases.
- Monitor cached token usage in run telemetry.

