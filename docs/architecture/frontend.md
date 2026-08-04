# Frontend architecture

HUF's frontend is a Vite + React + TypeScript SPA under `frontend/`, served by the Frappe
backend at build time (`vite build` emits into the app's public assets). This doc is a router,
not a component inventory — the frontend changes too fast for a hand-maintained page list to
stay accurate; use the structure below plus normal code search.

## Where things live

`frontend/src/` (verify against the live tree — this is a snapshot, not a contract):

| Directory | What's there |
|---|---|
| `pages/` | Route-level views (~70 files as of 2026-08) — one per top-level dashboard section (Agents, Flows, Knowledge, MCP, Data, Execution Profiles, AI Providers, ...). |
| `components/` | Shared and page-scoped components, including the Flow builder pieces (`FlowCanvas.tsx`, `FlowNode.tsx`, `FlowRunHistory.tsx`, `FlowRunViewer.tsx`) — see [`flows.md`](flows.md) for the flow builder's data model and backend contract. |
| `services/` | API clients per subsystem (e.g. `gatewayApi.ts`). |
| `contexts/`, `hooks/`, `layouts/`, `lib/`, `utils/`, `config/`, `types/` | Standard app-shell plumbing. |
| `pwa/` | PWA-specific code (service worker, install prompts, etc.). |

## Visual and interaction rules

**[`DESIGN.md`](../../DESIGN.md)** (repo root) is the source of truth for HUF's visual system —
color tokens, typography, component patterns, the "instrument panel" design direction. Read it
before touching shared UI. Don't restate its content here; if this doc and `DESIGN.md` ever
disagree, `DESIGN.md` wins for visual rules.

## Commands

Run from `frontend/`:

```bash
npm run dev         # vite dev server
npm run build        # tsc -b && vite build && copy-html-entry
npm run typecheck    # tsc --noEmit -p tsconfig.app.json
npm run lint          # eslint .
npm run test          # vitest run
npm run test:e2e      # playwright test
```

Confirm these still match `frontend/package.json`'s `scripts` block before trusting this table —
it's copied from there, so it can drift the same way any manual copy can.

## Related docs

- [`flows.md`](flows.md) — the Flow builder's frontend components and their backend contract.
- [`../../DESIGN.md`](../../DESIGN.md) — visual design system (colors, type, component patterns).
- Local frontend-only working rules (TS strictness, lint/typecheck-before-commit, accessibility):
  [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md).

## See also

[`../reference/doctypes.generated.md`](../reference/doctypes.generated.md) for any DocType a
frontend page reads/writes against.
