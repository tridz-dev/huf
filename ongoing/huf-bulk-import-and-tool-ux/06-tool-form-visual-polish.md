# Track C Follow-up — Tool Form Visual Polish (Execution Log)

Date: 2026-07-25
Worktree: `/Users/safwan/Code/HUF/huf/.claude/worktrees/magical-mclaren-c76e32`
Branch: `refactor/tool-creation-ux` (extends PR #430). No push performed.
Scope: `frontend/src/components/tools/ToolCreationForm.tsx`, `frontend/src/components/ui/combobox.tsx`. No backend files, no Track A/B files.

## Shared-JSX verification (all 5 tool-type bodies)

Re-read `ToolCreationForm.tsx`: there is a single `renderSettingsView()` JSX path for all five tool-type bodies (Document Operation, External API Request, Platform Utility, Run AI Agent, Custom Script/Function). Category/Description ("Contract"), Core configuration, Operation details, Parameters, and Additional Settings are shared markup; only individual fields are conditional via `shouldShowField(field, selectedType)`. So every zone fix below applies uniformly to all 5 bodies — no per-type duplication exists to drift.

## Problem 1 — Sticky Back bar: mismatched bg + negative-margin padding hack

`ToolCreationForm.tsx`, the sticky bar rendered when `editingParameterIndex === null`.

- Before: `sticky top-0 z-10 bg-panel border-b border-line pb-3 -mx-1 px-1 mb-4`
  - `bg-panel` (#FBFCFA near-white) sat directly on the dialog's own `bg-background` (#F2F3EF cream) → visible mismatched white strip.
  - `-mx-1 px-1` negative-margin hack to fight the form's own `px-1`.
- After: `sticky top-0 z-10 bg-background border-b border-line py-3 mb-4`
  - `bg-background` blends exactly with the dialog surface (same token `dialog.tsx` uses), still opaque so scrolled content doesn't bleed through.
  - Negative-margin hack removed; the bar now spans the form content width, so the Back button's left edge lines up with every field below. `pb-3` → `py-3` for even vertical padding.
- Design choice: blend-the-bar + zone dividers (see Problem 3) rather than wrapping zones in panel Cards — in a modal, Card-in-dialog would compound `p-6` (Card) on `px-6` (DialogScrollBody) and read as heavy nested boxes; a single flat surface with hairline dividers matches the app's flat/bordered aesthetic better.

## Problem 2 — Inconsistent input backgrounds (Combobox rendered white)

Audit of every control type used in the form:

| Control | Primitive | Background |
| :------ | :-------- | :--------- |
| Input | `components/ui/input.tsx` | `bg-transparent` |
| Textarea | `components/ui/textarea.tsx` | `bg-transparent` |
| Select | `components/ui/select.tsx` `SelectTrigger` | `bg-transparent` |
| Combobox | `components/ui/combobox.tsx` → `Button variant="outline"` | **`bg-panel`** (near-white) ← the outlier |
| Switch | `components/ui/switch.tsx` | n/a (track control) |

- Fix (shared primitive, `components/ui/combobox.tsx`): trigger Button className
  - Before: `h-9 w-full justify-between px-3 py-2`
  - After: `h-9 w-full justify-between bg-transparent px-3 py-2 font-normal`
  - `cn()` uses `twMerge`, so `bg-transparent` cleanly overrides the outline variant's `bg-panel`; `font-normal` aligns text weight with Input/Select (Button default is `font-medium`).
- Why primitive-level was safe: `Combobox` has 9 call sites (`ToolCreationForm`, `Executions`, `AgentSummaryPromptsPage`, `AgentPromptsPage`, `knowledge/GeneralTab`, `agent/PromptTemplateSection`, `agent/AgentKnowledgeModal`, `agent/AdvancedTab`, `agent/TriggerFieldsRenderer`). Spot-checked `AdvancedTab.tsx` and `GeneralTab.tsx`: in every case the Combobox is a standard form field sitting beside transparent Inputs/Selects on the same surface, so the panel-white trigger was equally inconsistent there. `bg-transparent` just shows the parent surface — it cannot paint the wrong color on any call site. `Button`'s outline variant itself was deliberately left untouched (widely used as an action button where `bg-panel` is correct).

## Problem 3 — No type scale / no zone grouping

- New module-level `SectionHeader` component in `ToolCreationForm.tsx` — one shared treatment for every zone header:
  - `h3`: `text-sm font-semibold uppercase tracking-wide text-steel`
  - optional icon: `w-4 h-4 text-steel-soft shrink-0`
  - Field labels keep existing `FormLabel` styling (normal case, foreground) → clear 2-level hierarchy.
- Applied to all zones: Core configuration (Settings icon), Contract (inside its trigger row, same classes inline since it lives in a `<button>`), Operation details (Zap icon), HTTP Headers, Parameters (with Auto/Edited badge preserved), Additional Settings, and the aside's Function Definition header (previously `font-semibold text-foreground text-sm`) for uniformity.
  - Before (every zone): `<h3 className="font-semibold text-foreground">` with `w-5 h-5` icons — same visual weight as field labels.
- Zone grouping: each section wrapper after the first now gets `border-t border-line pt-6` (Core configuration stays divider-less as the first zone; container `space-y-8` unchanged). Chosen over wrapping zones in the `Card` primitive: Card's `p-6` would stack on the dialog's `px-6` and create card-in-a-card nesting inside a modal; hairline top dividers keep the single flat surface while making zones read as distinct groups. Applied consistently — no mixed approaches.

## Problem 4 — Contract collapsible had no interactive affordance

- Before: trigger was plain text + chevron — `group flex w-full items-center gap-2 text-left`, no background, no border, no hover state.
- After: `group flex w-full items-center gap-2 rounded-none border border-line bg-panel px-3 py-2.5 text-left transition-colors hover:bg-paper-deep`
  - Bordered row using the same token recipe as the outline Button variant (`border-line` / `bg-panel` / `hover:bg-paper-deep`), sharp corners (`rounded-none`) per the flat aesthetic; here the `bg-panel` row is intentional — it distinguishes the collapsible as a distinct interactive row, and the section's `border-t` divider above it frames the zone.
  - `CollapsibleContent` gained `pt-1` for breathing room under the row; collapsed summary (`— category · description…`) and rotating chevron unchanged.

## Files changed

1. `frontend/src/components/tools/ToolCreationForm.tsx` — SectionHeader component; all six zone headers; zone dividers; sticky Back bar; Contract trigger row; aside header.
2. `frontend/src/components/ui/combobox.tsx` — trigger `bg-transparent font-normal` (shared primitive, safe per audit above).

## Build gate

- `cd frontend && npm run build` → **PASS** (tsc zero errors; vite build + copy-html-entry succeeded, ~25s). Chunk-size warnings only (pre-existing).
