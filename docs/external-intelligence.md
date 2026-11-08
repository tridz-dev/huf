# External Intelligence

## 1. What it is

Huf can act as a control plane for agents that run outside Huf. Huf owns identity, permissions, approvals, tools and the conversation record. A connected external agent supplies the reasoning and the local work. Huf never has to be the model host to be in charge of what happens.

Huf provides:

- **Identity**: every call is made as an authenticated Frappe user.
- **Permissions**: each tool call is checked against the user's roles and the connection's policies.
- **Approvals**: risky actions pause until a person decides in the Huf UI.
- **Tools**: the same Huf tools that native agents use are offered to the external agent.
- **Conversation records**: Huf-mediated actions and reported progress are stored against the session.

The external agent supplies the intelligence and, where it has them, its own local shell and filesystem.

Modes:

| Mode | Who runs the reasoning | Status |
|------|------------------------|--------|
| Native | Huf's own agent runtime | Available |
| Connected External | An agent the user runs themselves, attached to Huf over MCP | Available |
| Managed External | A runtime hosted or supervised by Huf | Not implemented yet |

## 2. Connecting

1. **Create an External Agent Connection** in Huf. Set the user, the agent, and the policies that apply to this connection. The agent's Execution Mode must not be Native. A user can have only one enabled connection per agent.
2. **Create an API key for that user.** In Frappe, open the user's settings and go to **API Access**, then generate the key and secret.
3. **Register the Huf MCP endpoint** with the external agent, as an HTTP MCP server, using the add-server command of your agent's MCP client:

   ```
   URL:    https://<site>/api/method/huf.ai.external.gateway.mcp
   Header: Authorization: token <api_key>:<api_secret>
   ```

   Replace `<site>`, `<api_key>` and `<api_secret>` with your values.

**Authentication.** The endpoint accepts a Frappe API key and secret, sent in the `Authorization: token <api_key>:<api_secret>` header. Cookie sessions are refused, and so are guest requests, so a browser that is logged in to Huf cannot be used to call the endpoint. An OAuth bearer token is accepted too (see "Sign in with OAuth").

**Connection selection.** Send the `X-Huf-Connection` header, or a `?connection=` query parameter, with the connection name. It is needed only when the user has several enabled connections. With a single enabled connection it can be omitted.

**Session selection.** Send `Mcp-Session-Id` to continue a specific session. Without it, `initialize` opens a new session. Any other method reuses the newest open (non-terminal) session on the connection, or creates one if none exists.

Calls made through this endpoint act as the user who owns the API key. Revoking or disabling that user, or deleting the connection, stops access.

### Sign in with OAuth

MCP clients such as Claude can log in through the browser instead of a pasted key. Huf reuses Frappe's own OAuth server (authorization code with PKCE S256, refresh tokens, optional dynamic client registration) and adds only the discovery document for the gateway.

What the user does: add the server URL `https://<site>/api/method/huf.ai.external.gateway.mcp` in the client, then sign in to Huf in the browser window that opens and approve access. The client stores the token and sends it as `Authorization: Bearer <token>`. Every call runs as the user who approved, with that user's own permissions; the user needs an enabled External Agent Connection (pass `X-Huf-Connection` if there is more than one).

How discovery works: an unauthenticated call gets HTTP 401 with `WWW-Authenticate: Bearer resource_metadata="https://<site>/api/method/huf.ai.external.oauth.protected_resource"`. That document names the gateway as the resource and the site as its authorization server; the client then reads `/.well-known/oauth-authorization-server` and registers or uses a client.

Admin setup (once): open OAuth Settings and keep "Show Auth Server Metadata" on. "Enable Dynamic Client Registration" is off by default (field `enable_dynamic_client_registration`); turn it on so clients can register themselves, otherwise create an OAuth Client with the client's redirect URI, token endpoint auth method None, scopes `all`. Dynamic clients get the consent screen at first login. The consent screen (Allow / Deny) renders only when the site's frontend assets are built (`bench build`); with Allow, the client receives an access token that the gateway accepts and runs as the signed-in user.

Limits: Frappe does not bind a token to a resource and the gateway does not check scopes, so a token is as powerful as the user. Revoke access by deleting the token under OAuth Bearer Token.

## 3. MCP tools

| Tool | Purpose |
|------|---------|
| `huf_discover` | List the Huf tools the session's agent permits under this connection. Each entry gives the tool's action class, the policy decision (allow, requires approval or deny) and its parameters. |
| `huf_context` | Read recent conversation messages (`scope: "conversation"`, up to 50, default 20), or the agent's name, description and instructions (`scope: "agent"`). |
| `huf_invoke` | Call a Huf tool on behalf of the session, subject to policy and approvals. |
| `huf_surface` | Create or update an interactive surface in the Huf session. `action` is `create` or `update`, and `spec` is an object that defines the surface. Returns the `surface_id`. |
| `huf_wait` | Receive queued events: user messages and approval or cancel notices. Waits up to `timeout_seconds` (default 5, maximum 10) and returns early when events arrive. `timed_out` is true when none arrived. Poll again to keep listening. |
| `huf_report` | Record progress, an observation or an artifact (`kind`) that the external agent reports about its own work. |
| `huf_complete` | Finish the task with `status` `success` or `failed` and an optional `result` summary. Success completes the session and stores the result on the Agent Run. Failed marks the session as failed. |

### Builder tools (optional)

Builder tools let the connected agent find, and with your approval create, Huf agents, tools, tables and apps. They are off by default. Set **Builder access** on the External Agent Connection to one of:

- **Off** (default): no builder tools are offered.
- **Build**: the finder tools and the create tools below.
- **Admin**: everything in Build, plus app building.

| Tool | Purpose | Minimum tier | Approval |
|------|---------|--------------|----------|
| `huf_find_agents` | Search the agents the user can see. Read only. | Build | Not needed |
| `huf_find_tools` | Search the tools and site capabilities the user can see. Read only. | Build | Not needed |
| `huf_find_tables` | Search the tables the user can read. Read only. | Build | Not needed |
| `huf_create_agent` | Create an agent from a name and instructions, optionally with existing tools. | Build | Every call |
| `huf_create_tool` | Create an agent tool from a spec. | Build | Every call |
| `huf_create_table` | Create a Huf table from a spec. | Build | Every call |
| `huf_build_app` | Draft, update or install a Huf app from a spec. | Admin | Every call |

Hub tools above the connection's tier look nonexistent. They are left out of the tool list, and calling one returns the same error as any unknown tool name. Every builder call runs as the connection's user, with that user's roles and document permissions.

Writes run only after you approve the exact call in the Huf UI. Approvals are single use and bound to the arguments, as described under Security model.

Never exposed, at any tier: creating server or client scripts, running code, shell access, a generic record passthrough, user and role management, and secrets.

## 4. Security model

- **Identity** comes from the authenticated Frappe user. The session token is held by the server. The model never supplies or chooses the identity or the token.
- **Policy classes** group every tool action as one of:
  - `read`
  - `write`
  - `communicate`

  Each class resolves to **Allow**, **Requires Approval** or **Deny** under the connection's policies.
- **Approvals** are bound to the exact arguments of the call. They are single use and expire after 30 minutes. A decision can be made only in the Huf UI, never through the MCP channel.
- **Idempotent replay**: a repeated request with the same idempotency key returns the original result and does not run the action again.
- **Tool membership**: `huf_discover` offers only tools on the session agent's tool list, and a connection can invoke only tools it has been granted. Builder tools are additionally gated by the connection's Builder access.
- **Guests are refused.** Requests from guest users do not get access.
- **Public metadata.** The public OAuth metadata endpoint exposes only public information.

## 5. Visibility

| What happens | What Huf records |
|--------------|------------------|
| Tool call mediated by Huf (`huf_invoke`) | Full record: arguments, decision, result. |
| Progress the agent reports (`huf_report`) | Reported: stored as the agent stated it, not verified by Huf. |
| Local shell or filesystem access inside the external agent | Not visible to Huf. |
| Private reasoning inside the external agent | Not available to Huf. |

Sessions are labelled by how they run:

- **Connected**: the external agent runs the work. Huf sees only what is mediated or reported.
- **Huf-managed**: the work runs under Huf's runtime. Reserved for Managed External mode, which is not implemented yet.

## 6. Lifecycle and mailbox

### Lifecycle states

| State | Meaning |
|-------|---------|
| Active | The session is running. |
| Waiting for Input | The agent needs a reply from the user. |
| Waiting for Approval | A tool call is paused for a decision in the Huf UI. |
| Runtime Offline | The external agent has stopped responding. It can resume to Active. |
| Completed | Finished successfully. Terminal. |
| Failed | Finished with an error. Terminal. |
| Cancelled | Stopped on request. Terminal. |

Completed, Failed and Cancelled sessions cannot change state again.

### Mailbox

Events for a session, such as user replies, approval decisions and cancellations, are stored durably in a mailbox. They are not lost if the external agent is disconnected.

`huf_wait` returns queued events within at most 10 seconds (default 5), even if nothing has arrived. The caller should poll again. Waiting is a convenience, not a guarantee of timely delivery.

## 7. Not yet implemented

- **Managed runtimes**: running the agent inside Huf, for example through a Codex app server or a hosted Claude runtime.
- **Converting repeated operations into Flows or Procedures**: turning a sequence of tool calls that worked into a reusable Huf Flow.

## 8. Suggested follow-up refactors

These are separate from the External Intelligence feature and should land in their own changes.

- **Telegram modules**: move the 16 top-level `huf/ai/telegram_*.py` modules into a `telegram/` package, alongside the existing `gateway_adapters/telegram_*` modules.
- **MCP package**: group `mcp_client.py`, `mcp_connection_resolver.py`, `mcp_oauth.py` and `mcp_support/` into one `mcp/` package, with the new inbound gateway beside the client.
- **Large modules**: split `huf/ai/agent/integration.py` (about 4900 lines) and `huf/ai/desktop/executor.py` (about 2800 lines) by concern.
- **Tool handlers**: move tool handlers out of `sdk_tools.py` so that `sdk_tools` and `tools/invocation` no longer import each other lazily.
- **Integration tools**: separate integration tools (Gmail, Slack, WhatsApp, Telegram and similar) from core tool types inside `huf/ai/tools/` into an `integrations/` subpackage.
