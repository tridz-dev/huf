# Security: SSRF Protection and API Key Management

HUF lets agents and flows make outbound HTTP calls and stores third-party LLM/API credentials in the database, so two subsystems carry most of the security weight: a shared URL-validation guard (`validate_url` in `huf/ai/http_handler.py`) that most-but-not-all outbound-call paths run through, and per-provider credential storage built on Frappe's encrypted `Password` field type. Coverage of the SSRF guard is inconsistent across call sites — this doc says explicitly where it is and isn't applied, rather than describing it as uniformly enforced.

## SSRF Protection

### The guard itself

`validate_url(url)` in `huf/ai/http_handler.py:64` is the single implementation used everywhere it's called:

- Rejects any scheme other than `http`/`https` (`huf/ai/http_handler.py:73`).
- Resolves the hostname via `socket.getaddrinfo` and rejects if it doesn't resolve (`huf/ai/http_handler.py:83-86`).
- Rejects the request if **any** resolved IP is private/internal, using `_is_public_ip` (`huf/ai/http_handler.py:34-61`), which classifies via Python's `ipaddress` module (loopback, private, link-local, reserved, multicast, unspecified) and unwraps IPv4-mapped IPv6 addresses (`::ffff:127.0.0.1`) before classifying them.
- Fails closed: an unparseable IP or unresolvable hostname is treated as invalid.

This replaces the old AGENTS.md description of a "private IP regex" — the current implementation resolves DNS and classifies real `ipaddress` objects rather than regex-matching the literal URL string, which is both more correct (catches IPv6, doesn't false-positive on public IPs that merely look like private ones) and has a known gap: **it does not protect against DNS rebinding**. The comment at `huf/ai/http_handler.py:80-81` calls this out directly — validation resolves the hostname once, but the actual request (`requests.request`) re-resolves independently, so a hostname that resolves to a public IP at validation time and a private IP at request time is not caught. This is documented as a known follow-up, not fixed.

### `handle_http_request` (the tool-facing entry point)

`huf/ai/http_handler.py:96` is the whitelisted RPC (`@frappe.whitelist(allow_guest=True)`) that `Agent Tool Function` HTTP tools call through. On top of `validate_url`, it adds:

- **Base URL binding**: if the `Agent Tool Function` doc specifies `base_url`, a relative tool-supplied URL is joined against it (`huf/ai/http_handler.py:142-145`) before validation.
- **Guest gating**: guest requests are rejected unless the specific tool has `allowed_for_guest` set (`huf/ai/http_handler.py:133-138`).
- **Manual, re-validated redirect handling**: requests are made with `allow_redirects=False`, and each `Location` header is resolved and re-passed through `validate_url` before being followed, up to 5 hops (`huf/ai/http_handler.py:175-203`). This is a real improvement over just trusting `requests`' built-in redirect following, and it closes the specific "tool redirects to `169.254.169.254`" attack — but it inherits the same DNS-rebinding caveat as above at each hop.
- **Response size cap**: 10MB, checked against `Content-Length` first and then against actual content length (`huf/ai/http_handler.py:11, 205-221`).
- **30-second timeout** (`huf/ai/http_handler.py:12`, `DEFAULT_TIMEOUT`).

There is no dedicated "error sanitization" layer beyond `str(e)` on `RequestException` (`huf/ai/http_handler.py:246-253`) — the old AGENTS.md's claim of "clean error messages that don't expose system information" is not backed by anything specific in the code; treat it as aspirational.

### Call sites: where the guard is (and isn't) applied

| Call site | Uses `validate_url` / `handle_http_request`? | Notes |
|---|---|---|
| `Agent Tool Function` HTTP tools → `handle_http_request` (`huf/ai/http_handler.py:96`) | Yes | Primary tool-facing path; full redirect re-validation. |
| Sandboxed code execution `http.request` op (`huf/ai/tools/code_execution.py:1229`) | Yes, plus a separate gate | `_authorize_egress` (`huf/ai/tools/code_execution.py:1029`) checks the calling Execution Profile's `Network Access Policy` (host/CIDR + port + protocol allowlist) **before** `handle_http_request` runs the SSRF guard. Fails closed: no policy attached to the profile means egress is denied outright (`huf/ai/tools/code_execution.py:1036-1037`). This is the most defended path in the codebase. |
| Knowledge base URL ingestion (`huf/ai/knowledge/extractors/url.py:21`) | Yes | Validates the initial URL and each redirect hop, mirroring the pattern in `http_handler.py`. |
| `Knowledge Input` doctype validation (`huf/huf/doctype/knowledge_input/knowledge_input.py:25`) | Yes | Validates a submitted URL at save time. |
| Generic file download helper (`huf/ai/tool_functions.py:429`, `_download_content`) | Yes | Used when a tool result needs to fetch bytes from a URL (e.g. attaching a file). |
| Media handler image fetch (`huf/ai/handlers/media.py:169-171`) | Yes, via `_http_request` (`huf/ai/http_handler.py:15`) | The lower-level internal helper — same `validate_url` call, no redirect re-validation loop (single request only). |
| **Flow Engine `http_request` node** (`huf/ai/flow_engine.py:944`, `_exec_http_request`) | **No** | Makes a raw `requests.request(method, url, **kwargs)` call with no call to `validate_url` and no network-policy check. A flow author (or an LLM-driven flow orchestrator picking node config) can point this node at an internal address and it will be fetched. This is a real gap, not a documented limitation in the old AGENTS.md — flag it if working on flow security. |
| MCP client requests (`huf/ai/mcp_client.py`, `_do_execute_mcp_session`) | No | MCP server URLs come from the `MCP Server` doctype (admin-configured, not agent-supplied per-call), so the risk profile is different, but there is no SSRF guard on `mcp_server.server_url` itself. |

### What's actually protected vs. the old AGENTS.md's claims

The old "Security Enhancements" section (formerly AGENTS.md lines ~1690-1703) described SSRF protection as a settled feature of `http_handler.py` with "header management" and "error sanitization" as named security features. In the current code:

- The core IP-blocking logic is real and is arguably stronger than described (proper `ipaddress`-based classification instead of regex, plus redirect re-validation).
- "Header Management" in the old doc isn't a security feature — it's just tool-defined headers being merged with request headers (`huf/ai/http_handler.py:156-160`); there's no filtering of dangerous headers (e.g. nothing strips a caller-supplied `Host` or hop-by-hop header).
- SSRF protection is **not** applied uniformly — the Flow Engine's `http_request` node bypasses it entirely, and MCP server URLs are never checked.
- DNS rebinding is an acknowledged, unfixed gap in every code path that uses `validate_url`.

## API Key Management

### Storage: `AI Provider` doctype

`huf/huf/doctype/ai_provider/ai_provider.json` stores the `api_key` field as Frappe's `Password` fieldtype, which Frappe encrypts at rest and never returns via normal `get_doc`/API reads — it must be explicitly unlocked with `.get_password("api_key")` server-side. `AIProvider.validate()` (`huf/huf/doctype/ai_provider/ai_provider.py:9-11`) enforces that cloud providers must have a key (`validate_api_key`, `huf/huf/doctype/ai_provider/ai_provider.py:29-36`), while local LLM providers (Ollama, LM Studio) are allowed to skip it and get a dummy `"not-needed"` placeholder for legacy callers that expect a truthy value.

`get_configured_providers()` (`huf/huf/doctype/ai_provider/ai_provider.py:59`) is the whitelisted method the frontend uses to check which providers are usable — it calls `.get_password("api_key")` server-side to check for presence but only returns provider `name`/`provider_brand`, never the key itself.

The `MCP Server` doctype follows the same pattern for its own secrets: `auth_header_value`, `oauth_client_secret`, `oauth_access_token`, and `oauth_refresh_token` are all `Password` fields (`huf/huf/doctype/mcp_server/mcp_server.json`), unlocked via `.get_password(...)` only when building request headers (`huf/ai/mcp_client.py:379`).

### How keys reach the provider SDK/API call

Each provider integration pulls the key at call time with `frappe.get_doc("AI Provider", provider).get_password("api_key")` — see `huf/ai/providers/anthropic.py:59`, `huf/ai/providers/google.py:59`, `huf/ai/providers/openrouter.py:40`, and `huf/ai/providers/litellm.py:527,1127,1179,1272`. There is no separate secrets vault or in-memory cache layer; the DB is the source of truth on every call.

**Where the old AGENTS.md undersold the mechanism**: the "Environment Variables" bullet described this as something specific to OpenRouter. In the current LiteLLM integration, `_setup_api_key()` (`huf/ai/providers/litellm.py:417-449`) is the general mechanism for *all* LiteLLM-routed providers, not just OpenRouter:

- A fixed map of known providers (OpenRouter, xAI/Grok, DeepSeek, Mistral, DashScope, Google/Gemini, Cohere, Perplexity, Moonshot) writes the key into a provider-specific `os.environ[...]` variable (`huf/ai/providers/litellm.py:424-438`), because LiteLLM's SDK for those providers reads credentials from the environment rather than accepting them as a call parameter.
- Other providers get the key passed directly as `completion_kwargs["api_key"]` (`huf/ai/providers/litellm.py:442`), which is the safer of the two mechanisms since it doesn't touch process-global state.
- For genuinely unknown providers, HUF *also* sets a heuristic `<PROVIDER>_API_KEY` env var as a fallback (`huf/ai/providers/litellm.py:444-449`), on top of the `api_key` kwarg.

This means: **for the providers in the env-var map, the API key is written into the process's environment variables on every request**, not scoped to that request or that thread. In a multi-worker/multi-threaded Frappe process handling concurrent requests for different `AI Provider` records of the same brand (e.g. two different OpenRouter accounts), this is a potential cross-request key confusion / leak surface — the code does not scope or lock around this write. This is a real property of the current implementation worth knowing about; it is not called out anywhere in the old AGENTS.md.

### Isolation and access control

- Each `AI Provider` record's key is independent — there's no shared secret store, so compromising one provider record doesn't expose others.
- Reading a provider's key requires Frappe-level read permission on the `AI Provider` doctype plus calling `.get_password()`, which itself is gated by Frappe core (raises `frappe.PermissionError` for users without the right to view the encrypted value). HUF does not add extra access-control logic on top of this — it relies entirely on standard Frappe DocType permissions.
- There is no key rotation, expiry, or audit-logging mechanism specific to `AI Provider` in this codebase as of this writing.

## See also

- `docs/reference/doctypes.generated.md` for the full `AI Provider` (and `MCP Server`) field schema.
