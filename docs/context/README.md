# Context index

Compact router into `docs/architecture/` and `docs/reference/`. This file stays an index — when
to read each document and what it covers — not a summary of their content. If you're reading
this from the root [`AGENTS.md`](../../AGENTS.md), you've already been pointed at the right row
below; if you're browsing directly, match your task's area to the "Read first" column.

## Architecture (behavior, control flow, the "why")

| Area | Read first | Canonical implementation |
|---|---|---|
| Agents, conversations, runs, streaming, prompt caching | [`architecture/agent-runtime.md`](../architecture/agent-runtime.md) | `huf/ai/agent_integration.py`, `huf/ai/run.py`, `huf/ai/conversation_manager.py` |
| Core tools (OCR/image/audio) + tool discovery/sync + file-attachment OCR/STT | [`architecture/tools-and-integrations.md`](../architecture/tools-and-integrations.md) | `huf/ai/sdk_tools.py`, `huf/ai/handlers/`, `huf/ai/tool_registry.py`; full 121-tool catalog in `reference/tools.generated.md` |
| Knowledge / RAG | [`architecture/knowledge.md`](../architecture/knowledge.md) | `huf/ai/knowledge/` (indexer, retriever, pluggable backends) |
| Conversation Data + Memory Record (two distinct systems) | [`architecture/memory.md`](../architecture/memory.md) | `huf/ai/memory_tools.py`, `huf/ai/conversation_data_tools.py` |
| MCP client integration | [`architecture/mcp.md`](../architecture/mcp.md) | `huf/ai/mcp_client.py`, `huf/ai/mcp_oauth.py` |
| Flow Engine (backend) + Flow Builder (frontend) | [`architecture/flows.md`](../architecture/flows.md) | `huf/ai/flow_engine.py`, `huf/ai/flow_api.py`, `frontend/src/components/FlowCanvas.tsx` |
| RBAC (dashboard/API permissions) + Execution Profile (sandboxed tool-call approval) | [`architecture/execution.md`](../architecture/execution.md) | `huf/permissions.py`, `huf/ai/tools/code_execution.py`, `huf/ai/tools/ssh_execution.py` |
| App seeding (resource discovery from installed apps) | [`architecture/apps.md`](../architecture/apps.md) | `huf/ai/app_seeding/` |
| Dynamic custom data tables (`Huf Data Table`) | [`architecture/data-tables.md`](../architecture/data-tables.md) | `huf/huf/doctype/huf_data_table/`, `huf/ai/tools/builder.py` |
| SSRF protection + API key/credential storage | [`architecture/security.md`](../architecture/security.md) | `huf/ai/http_handler.py`, `huf/ai/providers/litellm.py` |
| Frontend structure, commands, visual design pointer | [`architecture/frontend.md`](../architecture/frontend.md) | `frontend/src/`; visual rules in [`../../DESIGN.md`](../../DESIGN.md) |
| Gateways (Telegram/Slack/email/etc. inbound channels) | *(not yet written — see `docs/plans/known-issues.md`; check `huf/ai/gateway_service.py` and `huf/huf/doctype/gateway*` directly until it exists)* | `huf/ai/gateway_service.py` |

## Reference (exact inventories — generated, not hand-maintained)

| What | File | Regenerate with |
|---|---|---|
| All 73 DocTypes: fields, types, links | [`reference/doctypes.generated.md`](../reference/doctypes.generated.md) | `python3 docs/reference/generate_doctypes.py` |
| All 121 integration tools: params, function paths | [`reference/tools.generated.md`](../reference/tools.generated.md) | `python3 docs/reference/generate_tools.py` |

**Never hand-edit a `.generated.md` file or copy its content into `AGENTS.md` / an architecture
doc.** If a field or tool looks wrong, fix the source (schema or registry) and regenerate.

## Other durable material

| What | Where |
|---|---|
| Design decisions and rationale | `docs/adr/` |
| Temporary plans, proposals, status/TODO tracking | `docs/plans/` (e.g. [`known-issues.md`](../plans/known-issues.md)) |
| Point-in-time material kept for provenance only | `docs/archive/` (create as needed; never cite as current behavior) |

## When a doc and the code disagree

Code, DocType JSON schemas, and tests are authoritative. Every doc above went through a
verification pass against source when written (2026-08) and cites `path:line` for load-bearing
claims — but drift is inevitable as the code moves. If you find a mismatch: trust the code, fix
the doc in the same change, and don't propagate the stale claim into a new file.
