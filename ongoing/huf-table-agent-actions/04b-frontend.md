# Phase 4b — Frontend Implementation: HUF Table → Agent Actions

Branch: `feat/huf-table-agent-actions`. Scope: `frontend/` only. No python touched
(`git status` confirms: 5 modified + 1 new file, all under `frontend/`).

## Files added

- `frontend/src/components/data-table/TableAgentAccessModal.tsx` — the "Give agents
  access to {Table}" dialog (F1). Placed in `components/data-table/` next to
  `DeleteTableDialog.tsx` — that is where table-surface dialogs live (the brief's
  `components/data/` path does not exist; the brief allowed matching the real convention).

## Files modified

- `frontend/src/types/dataTable.types.ts` — added `TableAgentAction`
  (`'view' | 'create' | 'edit' | 'delete'`) and `TableAgentAccess`
  (`{ agent, agent_name, actions, tools }`) (F4).
- `frontend/src/data/doctypes.ts` — added `"Agent Tool"` (child table) to the central
  DocType map; needed by the bulk count fetch (F3).
- `frontend/src/services/dataTableApi.ts` — added three functions (below).
- `frontend/src/pages/DataPage.tsx` — "Add to agent…" menuAction between Edit Table and
  Delete Table (F2); "N agents" badge on the ItemCard (F3); renders the modal; refetches
  counts on save.
- `frontend/src/pages/DataTableViewPage.tsx` — same "Add to agent…" item in the header
  kebab between Edit Table and Delete (F2); renders the modal from the loaded schema.

## Component API (F1)

```tsx
interface TableAgentAccessModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	table: { name: string; table_name: string } | null; // registry docname + human label
	onSaved?: () => void;                               // called after a successful save
}
```

Behaviour:

- On open: `Promise.all([getAgents(), getTableAgentAccess(table.name)])`. Loading shows a
  centered spinner; fetch failure shows the Frappe error message with a Retry button;
  zero agents shows "No agents exist yet…" — no blank dialog in any state.
- Agent picker = single-select `Combobox` (same pattern as `AgentKnowledgeModal`).
  Selecting an agent reflects its CURRENT actions from the fetched access list.
- 4 checkboxes: View / Create / Edit / Delete, each with a one-line description.
  Delete's label/description are rendered in `text-destructive` with a "— destructive"
  marker. Checkboxes are disabled until an agent is selected.
- Reassurance copy, verbatim from the design: "The agent still runs under the user's own
  permissions — this doesn't grant new access." (ShieldCheck icon callout.)
- Detach copy: "Unchecking detaches the action from this agent — the tool itself is kept
  and stays available to other agents."
- "Currently:" line lists the OTHER agents (selected one excluded) as
  `Agent Name (View, Edit)`, or "No other agents have access to this table."
- Save → `setTableAgentAccess(table, agent, actions)`; success toast ("Access updated
  for X" / "Access removed for X" when all unchecked), error toast with
  `getFrappeErrorMessage`, closes only on success, then fires `onSaved`.

Dialog chrome copied from the house pattern (`SelectToolsModal` / `AgentKnowledgeModal`):
`Dialog` + `DialogScrollContent/Header/Body/Footer`, Cancel/Save footer, sonner toasts.

## Service layer (in `dataTableApi.ts`)

- `getTableAgentAccess(table)` → `call.get('huf.huf.doctype.huf_data_table.api.get_table_agent_access')`,
  unwraps `result.message`.
- `setTableAgentAccess(table, agent, actions)` → `call.post(...)`; returns the resulting
  single-agent `TableAgentAccess`.
- `getTableAgentAccessCounts()` → bulk per-table agent counts (F3, below).

## F3 — how the "N agents" badge avoids N+1

There is no bulk backend endpoint, and phase 4b may not add python. So the counts are
computed client-side from **two REST calls total per page load** (not per card), in
`getTableAgentAccessCounts()`:

1. `db.getDocList('Agent Tool Function', fields=[name, reference_doctype],
   filters=[reference_doctype like 'HF %'], limit=1000)` — all tools pointing at HUF
   table doctypes. If none, return `{}` (second call skipped).
2. `db.getDocList('Agent Tool', fields=[parent, tool],
   filters=[tool in <names from 1>], limit=10000)` — the child rows linking those tools
   to agents.

Grouped client-side into `Record<doctype_name, distinctAgentCount>`; `DataPage` keeps it
in state, badges read `agentCounts[table.doctype_name]`, and one refetch happens after
each successful save (`onSaved`). **Cost: 2 requests on `/data` mount + 1 per save.**
The whole fetch is wrapped in try/catch returning `{}` — a failure (e.g. a role that
can't list the `Agent Tool` child table via REST) just means no badges, never a broken
list page.

Caveats (accepted, noted for phase 5/6):

- Counts any tool referencing `HF *` doctypes, not only the 5 scaffolded `types` — a
  hand-made `Submit Document` tool also counts as "access". Arguably correct semantics.
- `limit: 1000` tools / `limit: 10000` link rows — fine at realistic HUF scale.

## Decisions / deviations

1. **Action strings on the wire are lowercase** (`view`/`create`/`edit`/`delete`), the
   backend's canonical vocabulary (`api.py:265-270` `TABLE_ACTION_MAP`; responses return
   lowercase at `api.py:371`). The backend also `.lower()`s input (`api.py:406`), so the
   brief's "literal View/Create/Edit/Delete" would work too, but symmetric lowercase
   keeps the frontend's checkbox-state diffing against `get_table_agent_access` responses
   exact. Display labels are capitalized; no `types` mapping exists in the frontend.
2. **Modal directory** — see "Files added".
3. **Badge source** — kept out of `getDataTables()` (unlike `record_count`) so the extra
   fetch only happens where the badge is shown and can be refreshed after saves without
   re-running the paginated query.

## Gates — real output

### `yarn typecheck` (host) — PASS

```
$ tsc --noEmit -p tsconfig.app.json
Done in 8.40s.
```

### `yarn lint` (host) — FAIL (pre-existing, branch-wide; 0 errors introduced by this change)

```
✖ 408 problems (346 errors, 62 warnings)
error Command failed with exit code 1.
```

The 346 errors are repo-wide `no-explicit-any` / hook-dependency issues in ~40 untouched
files (`toolApi.ts`, `streamChatApi.ts`, `flow.types.ts`, `formValidation.ts`, …) — the
gate was already red before this branch's frontend work. Proof for the files I touched:
every flagged line is pre-existing code merely shifted by my insertions —

- `DataPage.tsx:92` = the original `catch (err: any)` in `handleDeleteConfirm` (was :79).
- `DataTableViewPage.tsx:43,69,151` = the original `catch (err: any)` blocks (were :41,:67,:146).
- `dataTableApi.ts:68,305` = the original `(filters as any)` casts in `getDataTables` /
  `getTableRecords` (were :66,:219).

`TableAgentAccessModal.tsx`, `dataTable.types.ts`, `doctypes.ts` do not appear in the
lint output at all — new code is lint-clean. Fixing 346 pre-existing errors across 40
unrelated files is out of scope.

### `yarn build` — PASS (run inside the container, see note)

```
✓ built in 48.97s
$ cp ../huf/public/frontend/index.html ../huf/www/huf.html
Done in 84.46s.
```

**Note (environment, not code):** `yarn build` on the macOS host fails with
`Host version "0.21.5" does not match binary version "0.25.4"` — the frontend
`node_modules` was installed inside Docker and contains only the `linux-x64` esbuild
binary. The build was therefore run in the devcontainer
(`cd /workspace/development/16/apps/huf/frontend && yarn build`), which is also the
canonical path that produces the served assets (`huf/public/frontend/`, `huf/www/huf.html`).
`tsc -b` (the type-checking half of the build) had already passed on the host too.
Build artifacts are gitignored — `git status` stayed clean of them.

### `git diff` touches no python

`git status --short`: only the 6 frontend files above (plus untracked `ongoing/` docs).
No `huf/**/*.py` in the diff.

## UNKNOWNs

- Whether non-System-Manager roles can list the `Agent Tool` child table via REST
  (`/api/resource/Agent Tool`) — untested (no non-admin login attempted). Impact is
  bounded: the badge fetch fails soft to `{}` (no badge), and the `/data` page itself
  plus the modal's endpoints already require `flows.use`/`flows.manage`.
- Visual/manual UI verification against huf.localhost is phase 6's job; not done here.
