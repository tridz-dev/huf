# 08 — Tool form input contrast (add-data-form-styling convention)

Date: 2026-07-25
Branch: refactor/tool-creation-ux (PR #430)
Scope: `frontend/src/components/tools/ToolCreationForm.tsx`, `frontend/src/components/ui/combobox.tsx`

## Problem

After the 6f679dce polish commit, every field control in the Add/Edit Tool dialog
(Input, Textarea, Combobox trigger, Select trigger) rendered `bg-transparent`
directly against the dialog's `bg-background` (cream `#F2F3EF`) surface — zero
contrast, fields read as flush with the dialog.

## Reference pattern (PR #428, fix/add-data-form-styling)

The sibling fix for the HUF Table record form used **local className overrides**,
not shared-primitive changes:

- Panel wrap on the form container (`bg-panel border border-line …`), then
- `bg-background` added per-control in `DataRecordFormLayout.tsx` via className.

Verified with `git diff origin/develop origin/fix/add-data-form-styling` — the
branch touches zero files under `components/ui/`.

## Decision: local overrides, not primitive changes

Grepped call sites before touching any primitive:

- `input.tsx` — 40 importing files
- `select.tsx` — 27 importing files
- `textarea.tsx` — 24 importing files
- `combobox.tsx` — 9 importing files

Changing the `bg-transparent` default on any of these would restyle every screen
in the app (agent forms, MCP tabs, knowledge, integrations, dashboard filters…),
most of which sit on lighter surfaces where transparent is correct. So the fix is
applied locally in `ToolCreationForm.tsx`, matching exactly how PR #428 did it.

**One additive primitive change was required:** `Combobox` accepted no `className`
prop and hardcoded `bg-transparent` on its trigger Button. Added an optional
`className?: string` prop, merged via `cn()` after the default classes so
`bg-background` wins. Fully backward-compatible — all 8 other call sites are
untouched and render identically.

## What changed

### T1 — Left-column zone panels (`rounded-none`, flat, no shadow)

Each zone wrapped in `bg-panel border border-line rounded-none p-4` (same tokens
as the existing Contract/Guardrails trigger rows; sharp corners per this file's
aesthetic — deliberately NOT the reference page's `rounded-lg shadow-sm`):

- Core configuration (was unwrapped `space-y-4`)
- Operation details (was `border-t border-line pt-6` separator — redundant once
  the zone has its own border, so replaced)
- HTTP Headers (conditional GET/POST zone — same separator replaced, for
  consistency with the other zones)
- Parameters (same separator replaced)

### T2 — Right rail

- Contract `CollapsibleContent` and Guardrails `CollapsibleContent` wrapped in the
  same panel treatment, so the fields inside the expanded sections get the same
  panel + recessed-well contrast as the left column.
- Function Definition live preview left unchanged: it renders on `bg-ink` (dark)
  and already has strong contrast; wrapping it would add nothing.
- Guardrails switch rows (`rounded-none border p-4`) left as-is inside the new
  panel — visible bordered rows, and switches are out of scope per T4.

### T3 — `bg-background` on every field control

- Input: Tool Name, Function Path, Function Name, Provider App, Base URL
- Textarea: Description
- Combobox trigger: Reference DocType, Select Agent, Tool Category (via new
  `className` prop)
- Select trigger: Operation Type, Required Permission

### T4 — untouched

Switches (Read Only, Allowed for Guest, Pass parameters as JSON) and the footer
Checkbox — own distinct visual state, no well needed.

## Consistency check (gate)

All five tool-type bodies share a single conditional JSX path (`shouldShowField`)
— there are no per-type duplicates of the core fields, so the overrides apply to
every tool type uniformly. Re-grepped the final file: every `<Input>`,
`<Textarea>`, `<Combobox>`, and `<SelectTrigger>` in the form now carries
`bg-background`; only `<Switch>`/`<Checkbox>` remain transparent (by design).

Note: `ParameterCard` / `HttpHeaderCard` are separate components with their own
Card surfaces and were out of scope (not listed in T3, not part of this file);
the parameter editor view replaces the settings view rather than rendering
inside a zone panel.

## Build gate

`cd frontend && npm run build` — passed, zero TypeScript errors
(vite build ✓ in ~11s, huf.html copy done).
