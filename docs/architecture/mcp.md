# MCP Client Integration

HUF acts as an MCP (Model Context Protocol) **client only**: it connects to external MCP servers to consume their tools, using the official `mcp` Python SDK (not LiteLLM's experimental MCP client, contrary to what an earlier version of this doc claimed — see "Corrections" below). MCP tools and native `Agent Tool Function` tools are merged into one flat tool list before being handed to the LLM.

```
HUF Agent
  └── Tool Registry (huf/ai/sdk_tools.py: create_agent_tools)
        ├── MCP Tools (from linked/skill MCP servers)
        └── Native Tools (Frappe CRUD, Custom Functions, App Provided, Client Side)
```

## DocTypes

MCP configuration lives in four DocTypes. Full field tables are generated in `docs/reference/doctypes.generated.md`; only the fields load-bearing for the flows below are called out here.

| DocType | File | Role |
|---|---|---|
| **MCP Server** | `huf/huf/doctype/mcp_server/mcp_server.json` | One row per external MCP server: transport, auth, cached tool list, OAuth state |
| **MCP Server Header** (child) | `huf/huf/doctype/mcp_server_header/mcp_server_header.json` | Extra static HTTP headers sent on every request (`header_name`, `header_value`) |
| **MCP Server Tool** (child) | `huf/huf/doctype/mcp_server_tool/mcp_server_tool.json` | Cached tool definitions synced from the server (`tool_name`, `description`, `parameters` JSON, `enabled`) |
| **Agent MCP Server** (child) | `huf/huf/doctype/agent_mcp_server/agent_mcp_server.json` | Links an `Agent` to an `MCP Server` (`mcp_server`, `enabled`, `tool_count`) |
| **Skill MCP Server** (child) | `huf/huf/doctype/skill_mcp_server/skill_mcp_server.json` | Links a `Skill` to an `MCP Server`, same shape as Agent MCP Server |

`MCP Server` fields fall into three groups: connection (`transport_type` — `http`/`sse`, `server_url`, `timeout_seconds`, `tool_namespace`), non-OAuth auth (`auth_type`, `auth_header_name`, `auth_header_value`), and a large **OAuth 2.1** block (`oauth_status`, `oauth_client_id`, `oauth_client_secret`, `oauth_access_token`, `oauth_refresh_token`, `oauth_token_expires_at`, plus discovery fields `oauth_discovery_status`, `oauth_resource_metadata_url`, `oauth_authorization_server`, `oauth_metadata_json`, etc.) — see `huf/huf/doctype/mcp_server/mcp_server.json:1-70` for the full block. `available_tools` (Code/JSON) caches the raw OpenAI-format tool list from the last sync; `tools` (Table, `MCP Server Tool`) is the per-tool enable/disable UI built from that cache.

`MCPServer.validate()` only requires `auth_header_name` when `auth_type` is set and is not `none`/`oauth` (`huf/huf/doctype/mcp_server/mcp_server.py:9-13`). The `sync_tools()` document method (`huf/huf/doctype/mcp_server/mcp_server.py:21-41`) is a thin wrapper around `huf.ai.mcp_client.sync_mcp_server_tools`.

## MCP Client Module

Core MCP client logic is split across three files in `huf/ai/`:

| File | Responsibility |
|---|---|
| `huf/ai/mcp_client.py` | Tool construction, tool execution, sync, connection test |
| `huf/ai/mcp_oauth.py` | OAuth 2.1 + PKCE authorization-code flow, token storage/refresh |
| `huf/ai/mcp_connection_resolver.py` | URL-first OAuth discovery (Protected Resource Metadata, Authorization Server Metadata, Dynamic Client Registration) |

### `mcp_client.py` key functions

-   **`create_mcp_tools(agent_doc, mcp_server_names=None)`** (`huf/ai/mcp_client.py:37`)
    Builds `FunctionTool` objects from the **cached** `mcp_server.tools` child table rows — it does not hit the network. Accepts an optional explicit `mcp_server_names` list (used to merge skill-linked servers with agent-linked ones without a second round trip through `agent_doc.agent_mcp_server`).
-   **`_create_mcp_function_tool(mcp_server, tool_def)`** (`huf/ai/mcp_client.py:124`)
    Wraps one tool definition into an SDK `FunctionTool`, applying namespacing and name sanitization (see below).
-   **`execute_mcp_tool(server_name, tool_name, arguments)`** (`huf/ai/mcp_client.py:211`)
    Checks `frappe.has_permission("MCP Server", "read", server_name)`, loads the doc, and delegates to `_execute_mcp_tool_via_sdk`.
-   **`execute_with_mcp_session(mcp_server, operation)`** (`huf/ai/mcp_client.py:272`)
    Opens an MCP `ClientSession` (via `_do_execute_mcp_session`) and runs `operation(session)`. On a `401` for an `oauth`-authenticated server, calls `refresh_oauth_token()` once and retries.
-   **`_do_execute_mcp_session(mcp_server, headers, operation)`** (`huf/ai/mcp_client.py:302`)
    Picks transport by `mcp_server.transport_type`: `mcp.client.sse.sse_client` for `sse`, `mcp.client.streamable_http.streamable_http_client` for `http` (the default). Both wrap an `mcp.client.session.ClientSession`.
-   **`sync_mcp_server_tools(server_name)`** (`huf/ai/mcp_client.py:396`, whitelisted)
    Calls `session.list_tools()` over an MCP session, converts results to OpenAI tool format, writes them to `available_tools` (JSON cache) and upserts rows into the `tools` child table, then saves with `ignore_permissions=True` (documented as needed because non-admin users can trigger a sync) and commits via `commit_if_background()`.
-   **`test_mcp_connection(server_name)`** (`huf/ai/mcp_client.py:505`, whitelisted)
    Does a raw JSON-RPC `tools/list` POST with `requests` (not the MCP SDK) as a lightweight reachability check.
-   **`get_agent_mcp_servers(agent_name)`** / **`get_available_mcp_servers()`** (whitelisted) — list servers for the frontend.
-   **`auto_sync_mcp_server_tools()`** (`huf/ai/mcp_client.py:661`, whitelisted) — hourly scheduled job, syncs servers where `enable_auto_sync=1` and `auto_sync_interval` hours have elapsed since `last_sync`. Registered in `huf/hooks.py:263`.

## Tool Loading Flow

Tool loading is two-layered:

1. **`sdk_tools.create_agent_tools(agent)`** (`huf/ai/sdk_tools.py:71-104`) builds the base list: MCP tools from `agent.agent_mcp_server` first, then native tools from allowed `Agent Tool Function` documents.
2. **`AgentManager` init** (`huf/ai/agent_integration.py:117-154`) calls `create_agent_tools()` for the base list, then separately merges in tools from **skill-linked** MCP servers: it unions `agent.agent_mcp_server` names with `get_agent_skill_mcp_servers(agent_name)` (`huf/ai/skills/loader.py:80`), calls `create_mcp_tools(agent_doc, mcp_server_names=merged_names)`, and overlays the result onto `self.tools` keyed by tool name (skill/merged tools win on name collision).

Both layers read from the **cached** `MCP Server Tool` child table — no live MCP call happens during tool loading. A server must have been synced (manually or via the hourly auto-sync job) for its tools to appear.

## MCP Tool Execution Flow

1. The LLM returns a tool call; the provider layer (`huf/ai/providers/litellm.py`) looks it up by name in the agent's tool list — this dispatch is generic to all `FunctionTool`s, not MCP-specific.
2. The matched tool's `on_invoke_tool()` closure (built in `_create_mcp_function_tool`, `huf/ai/mcp_client.py:162-185`) runs, parsing the JSON arguments and calling `execute_mcp_tool(server_name, tool_name, arguments)`.
3. `execute_mcp_tool` re-checks read permission on the `MCP Server` doc, then opens a live MCP session (`execute_with_mcp_session`) and calls `session.call_tool(tool_name, arguments)`.
4. On `auth_type == "oauth"` and an HTTP 401 anywhere in the exception chain (`_has_status_code` walks nested exception groups), the token is refreshed once and the call retried; a second failure raises "OAuth token invalid or expired. Reconnect via the MCP Server form."
5. The MCP result (`model_dump()` if available, else a synthesized `{"content": [...], "isError": ...}`) is JSON-serialized and returned to the LLM as the tool result.

## Authentication

`auth_type` supports five values (`none`, `api_key`, `bearer_token`, `custom_header`, `oauth`), built into request headers by `_build_mcp_headers()` (`huf/ai/mcp_client.py:349-392`):

| `auth_type` | Header behavior |
|---|---|
| `none` | No auth header added |
| `api_key` / `custom_header` | `auth_header_value` (decrypted via `get_password`) sent verbatim under `auth_header_name` |
| `bearer_token` | `auth_header_name` set to `Bearer <auth_header_value>` |
| `oauth` | `Authorization: Bearer <token>` where the token comes from `mcp_oauth.get_valid_access_token()`, which proactively refreshes if the stored token expires within 5 minutes |

`custom_headers` (child table `MCP Server Header`) are layered on top of the auth header for every request regardless of `auth_type`.

### OAuth 2.1 flow (`mcp_oauth.py`)

This is a full authorization-code + PKCE (S256) implementation, org-level (one token pair per `MCP Server` doc, not per Frappe user):

-   **`resolve_and_start_oauth_flow(server_name)`** (`huf/ai/mcp_oauth.py:111`, whitelisted) — the single entry point for the "Connect" button. If the doc already has manual `oauth_client_id` + `oauth_authorization_endpoint` + `oauth_token_endpoint`, it skips discovery and calls `start_oauth_flow` directly; otherwise it runs `discover_mcp_server()` (`mcp_connection_resolver.py`) first.
-   **`start_oauth_flow(server_name)`** (`huf/ai/mcp_oauth.py:34`) — generates a PKCE verifier/challenge and `state`, stores `{server_name, code_verifier, user, site}` in Frappe's cache (Redis) under `mcp_oauth_state:<state>` for 10 minutes, and returns the provider's authorization URL.
-   **`handle_oauth_callback(server_name, code, state)`** (`huf/ai/mcp_oauth.py:151`, whitelisted, `allow_guest=False`) — invoked by `huf/www/mcp_oauth_callback.py` at the `/mcp-oauth-callback` route (registered in `huf/hooks.py:75`). Validates the cached state/user/site, exchanges the code for tokens, and calls `frappe.db.commit()` explicitly (required because Frappe rolls back GET requests to web pages by default).
-   **`refresh_oauth_token(server_name)`** (`huf/ai/mcp_oauth.py:261`) and the hourly scheduled job **`auto_refresh_oauth_tokens()`** (`huf/ai/mcp_oauth.py:318`, registered in `huf/hooks.py:264`) — refresh tokens expiring within 65 minutes for all `enabled` + `oauth` + `Connected` servers.
-   **`disconnect_oauth(server_name)`** — clears `oauth_access_token`/`oauth_refresh_token`/`oauth_token_expires_at` and resets `oauth_status` to `Not Connected`.

`mcp_connection_resolver.py` implements URL-first discovery per the MCP auth spec: probe the endpoint unauthenticated, parse the `WWW-Authenticate` challenge, fetch Protected Resource Metadata, fetch Authorization Server Metadata, and attempt Dynamic Client Registration — all without the admin needing to hand-enter endpoint URLs. Discovered values are cached in `oauth_metadata_json` and used as fallback in `_get_effective_oauth_config()` (`huf/ai/mcp_oauth.py:442`) when the corresponding manual `oauth_*` field is blank.

Auth credentials (`auth_header_value`, `oauth_client_secret`, `oauth_access_token`, `oauth_refresh_token`) are all stored via Frappe's encrypted `Password` field type.

## Tool Namespacing

If `tool_namespace` is set on `MCP Server` (e.g. `gmail`), tool names are prefixed with a dot: `send_email` → `gmail.send_email` (`huf/ai/mcp_client.py:154-156`). The resulting display name is then sanitized for OpenAI compatibility — non `[a-zA-Z0-9_-]` characters replaced with `_` and truncated to 64 characters (`huf/ai/mcp_client.py:187-191`) — so a namespaced dotted name actually reaches the LLM as `gmail_send_email`, not `gmail.send_email`. Tool descriptions are always prefixed with `[MCP:<server_name>]` (using `server_name`, not `tool_namespace`) regardless of whether namespacing is configured.

## Skills and MCP Servers

Skills can also carry their own MCP server links via the `Skill MCP Server` child table (`skill_mcp_servers` field on `Skill`, `huf/huf/doctype/skill/skill.json`). `huf/ai/skills/loader.py:80` (`get_agent_skill_mcp_servers`) resolves, for a given agent, which MCP servers come from its attached skills; `AgentManager` merges these with the agent's direct MCP server links (see Tool Loading Flow above) so a skill can grant an agent tool access without editing the agent's own `agent_mcp_server` table. Skill import/export (`huf/ai/skills/importer.py:330-387`, `huf/ai/skills/exporter.py:107`) round-trip `skill_mcp_servers` as part of a skill bundle.

## Frontend Integration

-   **`frontend/src/services/mcpApi.ts`** — full CRUD plus action wrappers: `getMCPServers`, `getMCPServer`, `createMCPServer`, `updateMCPServer`, `deleteMCPServer`, `getAgentMCPServers`, `getAvailableMCPServers`, `testMCPConnection`, `syncMCPTools`, `updateMCPTool`, and the OAuth trio `startMCPOAuthFlow`, `resolveAndStartMCPOAuthFlow`, `disconnectMCPOAuth`, `getMCPOAuthStatus`. `MCPServerDoc` mirrors the full backend field set including all `oauth_*` fields.
-   **`frontend/src/components/mcp/`** — dedicated MCP server detail page components: `MCPHeader.tsx`, `DetailsTab.tsx`, `ConnectionTab.tsx` (drives `resolveAndStartMCPOAuthFlow`/`disconnectMCPOAuth` for the Connect/Disconnect buttons), `ToolsTab.tsx`, `MCPToolDetailModal.tsx`. Routed at `/mcp` (listing) and `/mcp/:mcpId` (detail) per `CLAUDE.md`'s route table.
-   **`frontend/src/components/agent/ToolsTab.tsx`** — the agent-form "Tools and MCP" tab; takes `mcpServers`, `onAddMCP`, `onRemoveMCP`, `onToggleMCP`, `onSyncMCP` props to manage an agent's `agent_mcp_server` links inline.

## Corrections vs. the old AGENTS.md

The MCP section of the pre-split `AGENTS.md` (lines 1794-1988) was written for an earlier, simpler implementation and is out of date in several ways:

-   **No `oauth_token_response_path` field.** This field does not exist on `MCP Server` (confirmed absent from `huf/huf/doctype/mcp_server/mcp_server.json`). OAuth is a full RFC 8414/9728-aware authorization-code+PKCE flow (see above), not a bespoke "path into the token response" mechanism.
-   **Not LiteLLM's experimental MCP client.** The old doc describes `litellm.experimental_mcp_client.load_mcp_tools()`/`call_openai_tool()` as the primary mechanism with a raw HTTP/JSON-RPC fallback. The current code instead uses the official `mcp` Python SDK directly (`mcp.client.session.ClientSession`, `mcp.client.sse.sse_client`, `mcp.client.streamable_http.streamable_http_client`) for both sync and execution; `requests`-based raw JSON-RPC is used only for the lightweight `test_mcp_connection` reachability check, not as an execution fallback.
-   **`auth_type` has grown.** The old doc lists `none`, `api_key`, `bearer_token`, `custom_header`. The live schema adds `oauth` as a fifth option, backed by ~25 additional `oauth_*` fields not documented at all in the old file.
-   **Tool sync is now child-table-backed, not JSON-only.** The old doc implies `available_tools` (JSON) is the only cache; in practice `sync_tools()` also upserts individual rows into the `tools` child table (`MCP Server Tool`), which is what `create_mcp_tools()` actually reads at agent-run time — `available_tools` is a secondary raw cache plus the source used by `get_agent_mcp_servers`/`get_available_mcp_servers` for tool counts.
-   **Skill-linked MCP servers are new.** The old doc's tool loading flow only mentions `agent_mcp_server`; it predates the `Skill MCP Server` child table and the merge logic in `agent_integration.py`.
-   The "What HUF Is NOT" framing (not an MCP server/gateway/OAuth broker) is still materially accurate — HUF only ever acts as an OAuth *client* against external MCP servers' own authorization servers, it does not issue its own OAuth tokens or expose an MCP endpoint.

## See also

`docs/reference/doctypes.generated.md` for the full generated field tables of `MCP Server`, `MCP Server Header`, `MCP Server Tool`, `Agent MCP Server`, and `Skill MCP Server`.
