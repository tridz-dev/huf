# Design quick-check: "Apple-quiet" v3.0 proposal vs. current v2.0

**Source:** claude.ai/design project "Apple-like UI system" → `HUF UI System.dc.html`
(https://claude.ai/design/p/d3e50367-c17a-4d03-9048-88373d6979a6), imported via the
`claude_design` MCP. The file's own header labels it `HUF DESIGN.md v3.0 · product ui`.

**Status:** review-only. Nothing in the app is wired to this yet. New tokens live in
[`huf/public/css/huf-tokens-v3.css`](../huf/public/css/huf-tokens-v3.css) as a sibling to the
existing `huf-tokens.css`, which remains canonical. This doc is the diff for a human to react to,
not a decision.

---

## 1. This is a direction change, not a token tweak

The current system (`/DESIGN.md`, v2.0 "Instrument / Control-Room") and this v3 proposal
disagree on almost every foundational primitive:

| Primitive | v2.0 (current, canonical) | v3.0 proposal (this import) |
|---|---|---|
| Typeface philosophy | 3 typefaces, each with one job (Big Shoulders display / IBM Plex Sans UI / IBM Plex Mono data) | 1 system font (-apple-system stack) for everything except machine values, which stay mono |
| Radius | `2px` everywhere, no exceptions | `6–14px` on components, full pill (`999px`) on badges/switches/avatars |
| Shadows | None, except one signature hard-offset shadow on the Agent Event Ledger | Three sanctioned levels: flat / raised (`0 1px 2px`) / overlay (`0 8px 24px -8px`) used throughout |
| Background | Warm paper (`#F2F3EF`) / paper-deep / panel | Cool near-white canvas (`#FBFBFD`) / surface `#FFFFFF` / sunken `#F4F4F7` |
| Accent | Single fixed signal orange `#E8531F`, used sparingly (1–2 fills/screen) | Theme-selectable accent (options: blue / ink / green / purple; default purple `#7A5AF0` in the source file) |
| Status | Dot + mono label, never a colored pill | Colored pill badges (10–12% tint bg + saturated text) are the default status vocabulary |
| Sidebar active state | 2px signal-orange left edge + panel bg | Filled rounded pill (soft shadow), no left rail |
| Case | Uppercase for display + mono labels; sentence case for UI | Sentence case throughout, including nav/section labels; only eyebrows/meta are uppercase mono |
| Icons | Lucide, outline-only, 1.5–2 stroke | Tabler icon webfont (`@tabler/icons-webfont`) |

**Read on it:** this isn't "expand the palette" — it's the generic-SaaS/Apple-system aesthetic
that `/DESIGN.md` §1 explicitly positions v2.0 *against* ("generic AI slop pattern" table). Any
adoption decision should be made deliberately at the direction level, not merged piecemeal via
this one CSS file.

## 2. What's genuinely new (components v2.0's DESIGN.md doesn't spec)

These exist in the v3 file with no v2.0 equivalent documented — worth lifting into v2.0's spec
regardless of which visual direction wins:

- **Agent-switcher command palette** (`#agents` section, second card) — search input + Recent/System
  grouped list with a checkmark on the active agent and a lock icon on system agents. v2.0 has no
  documented pattern for "switch between agents" as a picker/palette.
- **Run ledger table** (compact `[time | model | duration | status]` mono rows) — a *denser* variant
  of v2.0's Ledger Rows (§6.6), scoped to a single agent's execution history rather than a list of
  agents. Worth a dedicated spec entry.
- **Chat tool-activity collapse row** — a single hairline pill (`Read travel_cities · 24 records`,
  chevron to expand) representing a tool call inline in the transcript. v2.0's Chat PWA section
  (§6.8) only specifies the message-ledger framing, not how tool calls render inline.
- **Chat message actions row** — copy / thumbs-up / regenerate icon buttons under an agent turn.
  Not specified anywhere in v2.0.
- **Settings toggle switch** (pill track + shadowed knob, `.huf3-shadow-knob`) and **segmented
  control** (Private/Team/Public, sliding white-bg-with-shadow segment) — v2.0 has no toggle or
  segmented-control spec at all.
- **Notice/inline-alert pattern** — tint background, no border, icon + text (`Changing the model
  resets tool permissions`). v2.0 doesn't spec a non-modal inline notice.
- **Empty state** (`#list` section) — icon tile + title + description + primary CTA, for zero-row
  list views. Not in v2.0.
- **Full form builder layout** (`#builder`) — three-pane field-palette / live-canvas / inspector,
  with drag handles, a "drop a field here" dashed placeholder, and inspector controls specified as
  "one size down" from form controls (12px labels, 7px radius, 6px padding). This is the most
  fully-specified net-new surface in the import; v2.0 has nothing comparable.
- **Field-level validation state** — red border + inline error message with icon, replacing the
  help text in place (so layout doesn't shift). v2.0 doesn't document form validation styling.

## 3. Gaps in the v3 import itself (if this direction were pursued)

Things the `.dc.html` reference doesn't cover, that v2.0 does — would need authoring before v3
could be considered complete:

- No marketing/landing surface at all (v3 is product-UI only; v2.0 §5 covers a full marketing site).
- No dark/"control plane" section equivalent.
- No motion spec (v2.0 §8 defines blink + drop-in; v3 file has no animation other than the
  0.18s toggle-track transition).
- No breakpoint/responsive behavior noted anywhere.
- No dedicated component for the "gauge strip" / big stat display (v2.0 §6.4) — no equivalent large
  numeric readout pattern appears in v3.
- Only one Reference/Foundations page — no worked full-screen composition examples (dashboard,
  agent detail, playground) the way v2.0 references `huf-redesign.html` / `huf-dashboard-redesign.html`
  as living full-page artifacts.

## 4. Recommendation

Treat `huf-tokens-v3.css` as a proposal artifact for design review, not a merge candidate as-is.
If there's appetite to adopt any piece of it, the net-new *component patterns* in §2 (toggle,
segmented control, inline notice, empty state, form builder, tool-activity row) are worth
extracting and re-skinning in v2.0's actual tokens (2px radius, no shadow, IBM Plex, signal
orange) rather than pulling in the whole Apple-system look — that gets the missing components
without the direction change.
