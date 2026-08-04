# AGENTS.md — `huf`

HUF is a Frappe application for building and running conversational AI agents with tool use,
knowledge (RAG), memory, MCP client integration, and a visual flow builder for workflow
automation. Backend is Python on the Frappe framework (`huf/`); frontend is a Vite + React +
TypeScript SPA (`frontend/`) that the backend serves as static assets.

This file is a router and a set of durable rules — not a description of what HUF does. For that,
start at [`docs/context/README.md`](docs/context/README.md).

## Repo map

| Path | What's there |
|---|---|
| `huf/huf/` | Main Python module; `huf/huf/doctype/<name>/` holds each DocType's `.json` schema, `.py` controller, `.js` client script |
| `huf/ai/` | Core AI runtime — agent execution, tools, knowledge, memory, MCP, flows |
| `frontend/src/` | React app — `pages/`, `components/`, `services/`, `contexts/`, `types/` |
| `docs/context/README.md` | Task → architecture-doc routing table |
| `docs/architecture/` | Focused subsystem docs (one topic each, verified against source) |
| `docs/reference/*.generated.md` | Generated DocType and tool inventories — regenerate, never hand-edit |
| `.github/workflows/` | CI: `server-tests.yml` (bench run-tests), `frontend-tests.yml` |

## Before changing code

1. Check `git status` first and preserve unrelated work.
2. Read [`docs/context/README.md`](docs/context/README.md), then the architecture doc for the
   subsystem you're touching.
3. **Code, DocType JSON schemas, and tests are authoritative over prose.** If a doc conflicts
   with what you find in source, trust the source, then fix the doc in the same change. Do not
   copy DocType field lists or the tool catalog into this file or into a new doc — they live in
   `docs/reference/*.generated.md` and drift the moment they're duplicated elsewhere.

## Context routing

| Change area | Read first |
|---|---|
| Agents, conversations, runs, streaming, prompt caching | [`docs/architecture/agent-runtime.md`](docs/architecture/agent-runtime.md) |
| Tools (core + integrations), file-attachment OCR/STT | [`docs/architecture/tools-and-integrations.md`](docs/architecture/tools-and-integrations.md) |
| Knowledge / RAG | [`docs/architecture/knowledge.md`](docs/architecture/knowledge.md) |
| Conversation memory | [`docs/architecture/memory.md`](docs/architecture/memory.md) |
| MCP client | [`docs/architecture/mcp.md`](docs/architecture/mcp.md) |
| Flows (backend engine + frontend builder) | [`docs/architecture/flows.md`](docs/architecture/flows.md) |
| Permissions (RBAC) and execution/approval sandboxing | [`docs/architecture/execution.md`](docs/architecture/execution.md) |
| App seeding | [`docs/architecture/apps.md`](docs/architecture/apps.md) |
| Custom data tables | [`docs/architecture/data-tables.md`](docs/architecture/data-tables.md) |
| SSRF / credential handling | [`docs/architecture/security.md`](docs/architecture/security.md) |
| Frontend structure and commands | [`docs/architecture/frontend.md`](docs/architecture/frontend.md), [`frontend/AGENTS.md`](frontend/AGENTS.md) |
| Visual design | [`DESIGN.md`](DESIGN.md) |

## Safety and compatibility

- Never commit secrets or expose provider API keys in logs, API responses, or frontend state.
  `AI Provider` credentials use Frappe's encrypted `Password` field type — don't route them
  through a plain `Data` field or log them.
- `Agent Tool Function` custom functions execute with the calling user's Frappe permissions —
  validate inputs and check permissions inside the tool function itself; a frontend check is not
  authorization.
- Outbound HTTP from tools/flows should go through the shared SSRF guard
  (`huf/ai/http_handler.py:validate_url`) — see
  [`docs/architecture/security.md`](docs/architecture/security.md) for which call paths currently
  do and don't. Don't add a new outbound-HTTP path that skips it without a documented reason.
- DocType JSON changes are schema changes: include a migration plan and update
  `docs/reference/doctypes.generated.md` (`python3 docs/reference/generate_doctypes.py`).
- Registering a new integration tool: add it to `huf/ai/tools/_registry.py`, then regenerate
  `docs/reference/tools.generated.md` (`python3 docs/reference/generate_tools.py`) — don't
  hand-edit the generated file.
- User-facing frontend text must read as plain product copy — never leak Frappe/DocType/SSE/API
  mechanics into labels, placeholders, or error messages.

## Validation commands

```bash
# Backend (from a bench with the huf app installed on a test site)
bench --site <site> run-tests --app huf

# Frontend (from frontend/)
npm run typecheck && npm run lint && npm run test
```

CI runs the same: `.github/workflows/server-tests.yml`, `.github/workflows/frontend-tests.yml`.

## Shared workspace

If you're working from the shared agent workspace at the parent `workspace/` directory (check
for a `workspace/AGENTS.md` above this repo), this checkout may be a **read-only reference
symlink** — do not edit it directly. Create a track and a git worktree of this repo inside it,
and make code changes there instead; follow `workspace/AGENTS.md` for the exact steps. If you're
already in a dedicated worktree (not the shared reference checkout), this doesn't apply.

## Documentation

When a change alters observable behavior (a DocType field, a whitelisted method, a hook, a
default), update the relevant `docs/architecture/*.md` page in the same change — don't let docs
drift further behind code. Temporary status (incomplete features, TODOs) belongs in
[`docs/plans/`](docs/plans/known-issues.md), not here.
