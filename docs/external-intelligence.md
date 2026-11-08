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

1. **Create an External Agent Connection** in Huf. Set the user, the agent, and the policies that apply to this connection.
2. **Create an API key for that user.** In Frappe, open the user's settings and go to **API Access**, then generate the key and secret.
3. **Register the Huf MCP endpoint** with the external agent:

   ```bash
   claude mcp add --transport http huf https://<site>/api/method/huf.ai.external.gateway.mcp --header "Authorization: token <api_key>:<api_secret>"
   ```

   Replace `<site>`, `<api_key>` and `<api_secret>` with your values.

Calls made through this endpoint act as the user who owns the API key. Revoking or disabling that user, or deleting the connection, stops access.

## 3. MCP tools

| Tool | Purpose |
|------|---------|
| `huf_discover` | List the connections and agents this user can attach to. |
| `huf_context` | Return the context for the current session: agent instructions, state and recent history. |
| `huf_invoke` | Call a Huf tool on behalf of the session, subject to policy and approvals. |
| `huf_surface` | Post a message or artifact into the Huf session so the user can see it. |
| `huf_wait` | Wait briefly for new events, such as an approval decision or a user reply. |
| `huf_report` | Record progress the external agent reports about its own work. |
| `huf_complete` | Mark the session as completed, failed or cancelled with a summary. |

## 4. Security model

- **Identity** comes from the authenticated Frappe user. The session token is held by the server. The model never supplies or chooses the identity or the token.
- **Policy classes** group every tool action as one of:
  - `read`
  - `write`
  - `communicate`

  Each class resolves to **Allow**, **Requires Approval** or **Deny** under the connection's policies.
- **Approvals** are bound to the exact arguments of the call. They are single use and expire after 30 minutes. A decision can be made only in the Huf UI, never through the MCP channel.
- **Idempotent replay**: a repeated request with the same idempotency key returns the original result and does not run the action again.
- **Tool membership**: a connection can only invoke tools it has been granted.
- **Guests are refused.** Requests from guest users do not get access.

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

`huf_wait` returns after at most 10 seconds, even if nothing has arrived. The caller should poll again. Waiting is a convenience, not a guarantee of timely delivery.

## 7. Not yet implemented

- **Managed runtimes**: running the agent inside Huf, for example through a Codex app server or a hosted Claude runtime.
- **OAuth for the MCP endpoint**: today the endpoint uses the API key header only.
- **Converting repeated operations into Flows or Procedures**: turning a sequence of tool calls that worked into a reusable Huf Flow.

## 8. Suggested follow-up refactors

These are separate from the External Intelligence feature and should land in their own changes.

- **Telegram modules**: move the 16 top-level `huf/ai/telegram_*.py` modules into a `telegram/` package, alongside the existing `gateway_adapters/telegram_*` modules.
- **MCP package**: group `mcp_client.py`, `mcp_connection_resolver.py`, `mcp_oauth.py` and `mcp_support/` into one `mcp/` package, with the new inbound gateway beside the client.
- **Large modules**: split `huf/ai/agent/integration.py` (about 4900 lines) and `huf/ai/desktop/executor.py` (about 2800 lines) by concern.
- **Tool handlers**: move tool handlers out of `sdk_tools.py` so that `sdk_tools` and `tools/invocation` no longer import each other lazily.
- **Integration tools**: separate integration tools (Gmail, Slack, WhatsApp, Telegram and similar) from core tool types inside `huf/ai/tools/` into an `integrations/` subpackage.
