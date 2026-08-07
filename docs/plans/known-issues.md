# Known incomplete features

**Status doc, not an instruction.** This is a snapshot of what's mid-flight, not durable
guidance — it can go stale the moment someone finishes or restarts the work. Moved here from
`AGENTS.md` (2026-08) so root instructions don't carry temporary status; keep this file current
or delete entries once resolved rather than letting them accumulate.

## Gateways UI not yet user-ready

The Gateways feature (channel inbound adapters) is merged into `develop` but is not yet
user-ready. The UI navigation and Flow Run trigger are temporarily disabled while the
provider adapters and connection forms are finished.

- `#473-followup` comments in `frontend/src/services/gatewayApi.ts`,
  `frontend/src/pages/GatewaysPage.tsx`, `frontend/src/components/app-sidebar.tsx`,
  `frontend/src/App.tsx`, `huf/huf/doctype/flow_run/flow_run.json`, and
  `huf/ai/gateway_service.py`.
- The previous version of this note also pointed at `docs/gateway-todo.md` as a "detailed shame
  list and restoration checklist" — **that file does not exist in the current tree.** Either it
  was never committed, got deleted, or the reference was wrong from the start. If a restoration
  checklist is still needed, recreate it here or in a GitHub issue; don't re-add a dead pointer.
