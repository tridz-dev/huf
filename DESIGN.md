# HUF Design System

## Quiet Control-Room Direction

**Status:** v3.0 ("Apple-quiet", shipped). This file documents what the product ships: the tokens in `frontend/src/index.css` (`:root` = light, `[data-theme="midnight"]` = dark) and `frontend/tailwind.config.*`. **When this file and `index.css` disagree, `index.css` is the truth and this file is the bug.** §2, §3, §4, §10 and §11 were reconciled with the shipped tokens in v3.0; the older v1/v2 "instrument" values (orange `#E8531F` signal, Big Shoulders / IBM Plex / Martian Mono, 2px radius, paper-green neutrals) are retired from the product and kept only in §3.2 as history for the marketing site.

**v3.0 change:** one quiet monochrome palette with a single purple signal, the platform system font stack, 8px radius, a raised shadow only on overlays and floating bars, and a component layer that owns every reusable shape: `components/ui` (primitives), `components/patterns` (§6.10 resource pages), `components/grid` (§6.11 data grids), `components/builder` (§6.12 builder forms).

**Core idea:** HUF's real differentiator isn't "AI" — it's *control*: every agent action is recorded, permissioned, and auditable. The product should feel like a calm, precise instrument — quiet surfaces, hairline rules, plain words — with a single signal color used the way a warning lamp is used: sparingly, and always meaningfully.

**We are a framework-based, design-system-fixed platform.** Pages compose primitives and patterns; they do not invent shapes, colours, sizes or spacing. A page that needs something new extends the system first (a pattern here, a token in `index.css`), then uses it.

---

## 1. Why this direction (and what it replaces)

| Generic "AI slop" pattern | HUF system |
|---|---|
| Purple→violet gradients, glowing hero cards | No gradients anywhere. The purple signal is a lamp (a dot, an edge, an active state), never a wash |
| Dark mode by default | Light by default (`:root`); `midnight` is a true dark counterpart with the same relationships, chosen by the user |
| Rounded cards with colored icon-in-square + soft shadow | Hairline-bordered panels, 8px radius, no shadow at rest; only overlays and floating bars are raised |
| Numbered feature cards (01/02/03) as decoration | Numbering only where it is *true* — row numbers, steps in a real sequence, IDs |
| Status as loud uppercase badges | Status as a dot + plain label (§7) or a sentence-case `pill-*` |
| Jargon labels ("Data", "Int", "temperature") | Plain words ("Text", "Number", "Creativity: Balanced"); jargon lives in Advanced / Developer options |

**Rule of thumb:** the signal color (`--signal`, purple) means *"look here"* — the active cell, the selected item, the live/running dot, the primary focus ring, one emphasized link. It is never decoration and never a second brand color.

---

## 2. Color tokens

Values are the shipped light theme (`:root` in `index.css`). Use the token (Tailwind `bg-paper`, `text-steel`, `border-line`, …), never the hex — the `hex_colour` UI-drift guard fails on literals in `.tsx`. The `midnight` dark theme redefines the same names.

| Token | Light | Role |
|---|---|---|
| `--paper` | `#FBFBFD` | App background |
| `--paper-deep` | `#F4F4F7` | Recessed surfaces — sidebar, hover, table heads, quiet bands |
| `--panel` | `#FFFFFF` | Raised content surface — cards, grids, sheets |
| `--ink` | `#1D1D1F` | Primary text; the primary button fill; the floating bulk bar |
| `--ink-soft` | `#2A2F36` | Secondary dark text |
| `--steel` | `#6E6E73` | Secondary text — descriptions, labels, metadata |
| `--steel-soft` | `#98989D` | Tertiary text — row numbers, type glyphs, faint metadata, off dots |
| `--line` | `#ECECF0` | Hairline borders and dividers |
| `--signal` | `#7A5AF0` | **The** accent: active cell / selection ring, live dot, selected preset edge, focus |
| `--signal-ink` | `#5B3FC4` | Signal as text — links, "Recommended", info pills |
| `--good` / `--good-tint` | `#1C7C54` / `#E8F5EE` | Ready / success |
| `--warning` / `--warning-tint` | `#8A5A00` / `#FDF3E0` | Needs attention, data-impact warnings |
| `--destructive` / `--destructive-tint` | `#B3261E` / `#FDECEA` | Errors, invalid cells, destructive actions |

**Usage discipline:**
- No gradients, anywhere.
- Signal appears as a *fill* at most once or twice per screen; elsewhere it is a ring, dot, edge or a `/5`–`/10` tint for "selected".
- Status colours (`good`, `warning`, `destructive`) carry meaning only; a page never picks them for decoration. Pages choose a **tone** (`ready | live | attention | error | off | neutral`, `patterns/tones.tsx`), and the token mapping lives once in the pattern layer.

---

## 3. Typography

### 3.1 Product type (shipped)

One family: the platform system stack (`--body` / `--display` = `-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Helvetica, Arial, sans-serif`), plus `--mono` (`ui-monospace, 'SF Mono', Menlo, monospace`) for machine values. No web fonts are loaded. Hierarchy comes from the size/weight tokens, not from a second typeface.

| Tailwind class | Token | Size / weight | Use |
|---|---|---|---|
| `text-display` | `--text-display-*` | 28 / 600, −0.02em | Rare hero numbers, one per screen at most |
| `text-title` | `--text-title-*` | 20 / 590, −0.015em | Page `<h1>`, one-card create titles |
| `text-subtitle` | `--text-subtitle-*` | 18 / 590 | Section / panel headings |
| `text-body-text` | `--text-body-*` | 15 / 400 | Reading text, chat messages |
| `text-ui-text` | `--text-ui-*` | 13 / 500 | Workhorse: rows, cells, buttons, menus, fields |
| `text-micro` | `--text-micro-*` | 12 / 500 | Helper text, chips, toolbar counts, field notes |
| `text-meta` | `--text-meta-size` | 11 | Mono counts, row numbers, timestamps |
| eyebrow | `--text-eyebrow-*` | 10, 0.07em, uppercase | Sidebar group labels only |

- Sentence case everywhere; uppercase only for eyebrows.
- `font-mono` is for identifiers and machine values (IDs, counts in chips, row numbers, tokens, latency) — never prose or labels.
- Numbers in grids and counts use `tabular-nums` and thousands separators.
- Never `text-[Npx]` (the `text_px` guard); add a token instead.

### 3.2 History: the v1/v2 instrument layers (retired from the product)

v1–v2 used Big Shoulders (display), Archivo / IBM Plex Sans (UI) and Martian / IBM Plex Mono (data) with an orange `#E8531F` signal and 2px radius. None of these ship in the product any more. The marketing pages (`huf-redesign.html`) may still use that layer; product code must not.

---

## 4. Layout & Structural Primitives

| Primitive | Spec (shipped) |
|---|---|
| **Radius** | `--r` 8px default (`rounded`), `--r-sm` 6, `--r-md` 10, `--r-lg`/`--r-xl` 14, `--r-full` 999 (pills, chips, switches). |
| **Borders** | 1px `--line` hairlines for panels, rows and dividers. |
| **Shadows** | `--shadow-flat` (none) at rest. `shadow-md` = `--shadow-raised` for a lifted card (one-card create, current step). `shadow-lg` = `--shadow-overlay` only for things floating over content (popovers, sheets, the bulk bar). |
| **Spacing** | `--space-1..7` = 4, 8, 12, 16, 24, 32, 48px (Tailwind 1, 2, 3, 4, 6, 8, 12). |
| **Controls** | Heights `--control-h-sm/md/lg` = 30 / 34 / 38px via the component `size` prop or `h-control-*`; never `h-6..h-11` on a control (the `fixed_height` guard). Fields use `--field-label-h`, `--field-gap`, `--field-note-h` through `ui/field`. |
| **Page** | Sidebar + fluid content; management pages via `PageFrame` (§6.9). Builder pages use `BuilderLayout` (§6.12). |


---

## 5. Components — Marketing Site

*Marketing site only; uses the retired v2 layer described in §3.2. Nothing here applies to the product.*

### 5.1 Nav
- Logo: wordmark "HUF" in Big Shoulders 700 + an 10px solid signal-orange square — no icon mark, no gradient logo.
- Sticky, 64px height, 1px bottom border, followed by the **tick rule** divider.
- Links: mono, 11px, uppercase, `--steel` → `--ink` on hover.
- Primary CTA: solid ink button → signal-orange on hover.

### 5.2 Hero — Signature Component: Agent Event Ledger
- Two-column split (7/5): headline + copy + CTAs on the left; the ledger on the right.
- **Ledger panel**: 1px ink border, 2px radius, hard double-offset shadow.
  - Header row: "Agent event ledger" label + a **REC** indicator — small blinking signal-orange dot (`animation: blink 1.6s steps(2) infinite`) + "Recording" in `--signal-ink` mono.
  - Body: mono rows, grid `[timestamp | agent · action | status]`, dashed row separators, `agent_name` in semibold ink, action description in `--steel`.
  - Status: `OK` (steel) or `HELD` (signal-ink) — never a colored pill, just colored mono text.
  - New rows animate in (`drop` keyframe, fade+slide 6px) every ~2.6s, oldest row scrolls off (max 9 visible). Respects `prefers-reduced-motion`.
  - Footer caption in mono: "Every agent action. Written before it runs."

### 5.3 Stack Strip
- Single thin bar, 1px borders top/bottom.
- Left: mono eyebrow label "Built on solid stack."
- Right: tech names in mono, uppercase, separated by vertical hairlines (`border-left`) — *not* logo badges/chips. Each tech may have a small outline icon (stroke 1.5, `--steel` → `--ink` on hover).

### 5.4 Fault Report (Problems Section)
- Replaces generic "3 problem cards." Framed as a **fault report**: `F-01`–`F-06`.
- 3-column grid, 1px top rule (`--ink`), each cell bottom-bordered.
- Each fault: mono code in `--signal-ink`, Archivo semibold title, `--steel` description (max 34ch).
- The numbering is *justified* — these are literally itemized failure modes, like a diagnostic printout.

### 5.5 Capabilities (Features Section)
- Replaces generic "icon + title + description" capability cards.
- **Grouped tabs** (Build / Know / Connect / Run) as bordered instrument-panel segments:
  - Active tab: ink border + 3px signal-orange left rail
  - Inactive tab: line border, hover → ink border
  - No counts, no "All" tab
- **Card grid**: 2-column layout, each card:
  - Outline icon (22px, stroke 1.5, `--steel` → `--ink` on hover)
  - Mono code badge (`AGT-01`, `KNW-01`, etc.) in top-right
  - Archivo semibold title
  - `--steel` description (1–2 lines)
  - Hairline border, hover: bg `--paper-deep` + 3px signal left rail
- Codes follow a real taxonomy: `AGT-*` (agents), `KNW-*` (knowledge), `ORC-*` (orchestration), etc.
- Footer: mono "Index X entries — view full catalog" with a signal-underlined link.

### 5.6 Use Cases
- 3-column grid (progressive disclosure: show 3 by default, "View all" expands to 6).
- Each cell: hairline border, Archivo semibold title, `--steel` description, mono tag pills.
- Hover: bg `--paper-deep` + 3px signal left rail.

### 5.7 Integrations
- **Available Now**: bordered cells in a grid (logo + mono name label), hover: border-ink + bg `--paper-deep`.
- **Coming Soon**: same grid, grayscale logos + 50% opacity.

### 5.8 Control Plane (Dark Section)
- The **only** dark (`--ink` background) section — justified because it represents "inside the system."
- Two-column: copy + checklist on the left (mono list items, `—` marker in signal orange), instrument **gauge stack** on the right.
- Gauge stack: 1px `--line-dark` border, stacked rows, each `[mono label | Big Shoulders value]`. One gauge (e.g. "Actions held for review") is in the **flag** state — value rendered in signal orange with a small mono sub-label ("pending").

### 5.9 CTA / Footer
- Large Big Shoulders headline (`clamp(64px, 9vw, 140px)`), one word in `--signal-ink`.
- Same button pair pattern as hero (solid ink / ghost).
- Footer: thin mono bar, no extra ornamentation.

---

## 6. Components — Product UI

Product UI uses the shipped v3.0 tokens (§2–§4) and the single system type family (§3.1). **Reconciliation note:** §6.1–§6.8 were written for v2 and still name retired values in places (Big Shoulders, IBM Plex, "signal orange", 2px radius, ink-bordered boxes). Read those as their v3.0 equivalents — system font with the §3.1 size tokens, `--signal` (purple), `rounded` (8px), `--line` hairlines — and follow the shipped components in `components/ui` and `components/app-sidebar` where they differ. §6.9–§6.12 are current.

### 6.1 Sidebar (Instrument Panel)
- Background `--paper-deep`, 1px right border.
- **Muted Experimental Sidebar Density:** Tighter vertical rhythm and spacing between items. Inactive items use more subdued text colors (`--steel-soft`) to reduce visual fatigue during extended sessions.
- Brand block: same wordmark + signal-square mark as marketing nav, plus a mono "AI Platform" sub-label (IBM Plex Mono) — **no colored icon-in-rounded-square logo**.
- Nav items: plain 1.6px-stroke line icons in `--steel` (→ `--ink` on hover), **IBM Plex Sans** medium 13.5px labels, sentence case.
- **Active state**: 2px solid signal-orange left edge + `--panel` background + subtle inset border — *not* a gray rounded pill (the most common dashboard-template tell).
- Optional trailing mono count badge (e.g. "12") in IBM Plex Mono, `--steel-soft`, right-aligned.
- Section labels ("Build", "Resources", "Org") in IBM Plex Mono, 9.5–10px, wide letter-spacing, `--steel-soft` — group nav items the way instrument panels group switches by subsystem.
- Footer: user avatar as a bordered initials box (1px ink border, 2px radius) — not a colored circle — plus name/email and an expand/collapse chevron. Name in IBM Plex Sans 600, email in IBM Plex Mono.

### 6.2 Topbar
- 60px height, `--panel` background, 1px bottom border.
- Left: sidebar-toggle icon + breadcrumb in IBM Plex Mono uppercase (`Dashboard`).
- Right: primary action button — solid ink, signal-orange on hover, **Big Shoulders uppercase label** (character moment) + `+` icon.
- **Display-type rule:** the global topbar carries the mono breadcrumb, never display type. A **work surface** (§6.9) MAY set its screen title in Big Shoulders inside its own compact topbar — vertical space is the scarce resource there, so the title doubles as the breadcrumb. A **management screen** MAY NOT — its title lives in the page head below the breadcrumb.

### 6.3 Page Head
- `<h1>` in Big Shoulders 700, ~34–38px, uppercase — the one big display moment on the screen.
- Subtitle in IBM Plex Sans, `--steel`, plain sentence case.

### 6.4 Gauge Strip
- **Single bordered instrument strip** (1px `--ink` border, 2px radius) divided internally by 1px `--line` verticals — *not* four separate cards.
- Each gauge: IBM Plex Sans uppercase-tracked label + IBM Plex Mono "Last 7 days" period sub-label + an info icon (outline circle with `i`), then a large **Big Shoulders** value (character).
- Values can carry a small IBM Plex Mono unit suffix (`%`, `s`, cents) at reduced size/weight in `--steel`.
- A gauge can enter **flag state**: value rendered in `--signal-ink`.

### 6.5 Tabs
- Underline style, **IBM Plex Sans** 13px medium, sentence case, `--steel` default. (Dropping mono+uppercase here is part of making the product feel calmer than the marketing site.)
- Active tab: `--ink` text + 2px **signal-orange** bottom border, sitting on a shared 1px `--ink` baseline.
- This is the **single tab vocabulary** for the product, backed by one shared implementation (`ui/tabs`, `underline` variant). The divergent `panel` variant and the mono-uppercase treatment were retired; never hand-roll a tab row.

### 6.6 Ledger Rows
- One bordered panel (`--panel`, 1px `--line`) containing a **Big Shoulders** section header ("Active Agents") and stacked rows.
- Row grid: `[name + id | model (mono) | run count (mono, with icon) | status (dot + label) | chevron]`.
- **Name cell**: IBM Plex Sans semibold title + an IBM Plex Mono sub-line (`id · agt_xxxx`) underneath.
- **Status dot vocabulary** (see §7 below); the label sits in IBM Plex Sans, the dot carries the meaning:
  - `--signal` (orange), **blinking** → *Running*
  - `--steel-soft` (gray), static → *Idle*
  - `--good` (green), static → *Healthy*
- Row hover: background → `--paper-deep`, chevron color → `--ink`. No card lift/shadow on hover.

### 6.7 Execution Management UI
- **Purpose:** Interface for managing execution profiles (Local Python, SSH, Docker) and SSH Connections.
- **Layout:** Grid-based cards or list layouts framed as infrastructure configuration.
- **Typography:** Strong use of **IBM Plex Mono** for environment variables, paths, and server addresses to reinforce the technical/infrastructure context.
- **Status:** Health and connection status use the standard dot vocabulary (`--good` for healthy connections, `--signal` for pending/failed).

### 6.8 Chat PWA
- **Control-Room Aesthetic:** The unified Chat PWA avoids typical consumer chat bubbles (no large colored rounded pills).
- **Message Ledger:** Messages are presented as ledger entries. User inputs and Agent responses are distinct but structured in a single stream with hairline dividers where appropriate.
- **Mobile Constraints:** Adapts cleanly to mobile dimensions while preserving the technical ledger feel.

### 6.9 Page Composition

Every screen composes from one of two sanctioned templates. Nothing hand-rolls a topbar or a page head. The split is about what is scarce: on a management screen, orientation is scarce (hence breadcrumb + big title); on a work surface, vertical space is scarce (hence compact chrome).

| | **Management page** (`PageFrame`) | **Work surface** (`WorkSurfaceFrame`) |
|---|---|---|
| Examples | Dashboard, Agents, Executions, Prompts | Playground, Chat |
| Chrome | Global topbar: mono breadcrumb only | Own compact topbar: sidebar trigger + title + actions |
| Title | Big Shoulders h1 in the page head (~34–38px), below the breadcrumb | Big Shoulders ~20px in the compact topbar (the §6.2 exception) |
| Width | Contained content column (§4), generous padding | Full-bleed, no max-width; content fills remaining height |
| Permits | Page head (h1 + steel subtitle + optional badge/actions), gauge strip, filter row, §6.5 tabs, ledger/card content | Sentence-case §6.5 tabs, instrument strips, run/prompt benches |
| Forbids | Display type in the topbar; full-bleed benches | A page head; a breadcrumb (a bench has no parent to go back to); max-width wrapping |

- **Choose a management page** when the user is administering things — lists, grids, settings, inspection. The page head is the one big display moment on the screen (§6.3).
- **Choose a work surface** when the user is *doing* something live — prompting, comparing, conversing. Chrome compresses to make room for the bench.
- Both templates share the same tokens, the §6.5 tab row, and the status vocabulary; they differ only in how much chrome the task can afford.

### 6.10 Resource pages (collection views)

A **resource page** is a management page (§6.9, `PageFrame`) whose job is one collection of things that belong to one parent resource: the documents in a source, the files in a dataset, the members of a team, the runs of a job. The patterns below are domain-free; they live in `frontend/src/components/patterns/` (import from `@/components/patterns`) and are built only from `components/ui` primitives and the §2 tokens. **Never hand-roll one of these shapes on a page;** extend the pattern instead.

Reading order, top to bottom: **head → status sentence → toolbar (ask + filters) → inline rows (progress, attention) → list** — or, when a search is active, **results** in place of the list; or, when the collection is empty, the **empty drop state** in place of toolbar filters and list.

#### 6.10.1 Anatomy and the no-tabs default
- **Head** = `PageFrame` `title` (the resource name; rename via a pencil or the overflow menu), `meta` = the **status sentence**, `actions` = **exactly one primary action** (the verb that grows the collection: "Add content", "Invite") + an `OverflowMenu` for everything else (Settings, History, maintenance actions, then a separator, then Turn off / Delete).
- **No tabs by default.** Settings open in a **settings sheet** (§6.10.9), activity/history opens from the overflow menu, and search lives in the toolbar. One surface means the user never has to guess which tab holds the thing that changed.
- **Use §6.5 tabs only when** the page holds two or more *peer collections* of comparable weight that the user switches between as a routine (Executions: runs vs approvals), or a secondary view is itself a full collection with its own toolbar. A settings form, a test box, or an activity log is **not** a reason for a tab.

#### 6.10.2 Status sentence (`StatusSentence`)
- One `ToneDot` + one plain sentence, segments joined by " · ": *"Ready · 1,241 documents · used by 2 agents"*, *"Importing · 1,240 of 3,000 found"*, *"No documents yet"*.
- Optional single inline action as a link ("Review"). The sentence states **one** state; if two are true, the more urgent wins (error > attention > live > ready > off).
- Tones (`Tone`, mapped once in `patterns/tones.tsx`): `ready` → `--good`; `live` → `--signal`, **blink** (§8); `attention` → `--warning`; `error` → `--destructive`; `off`/`neutral` → `--steel-soft`. Only `live` moves.
- Set `live` (polite `aria-live`) while the state is changing; leave it off at rest.
- Copy: sentence case, numbers with thousands separators, no internal status words ("Queued", "Scanning") — say what is happening.

#### 6.10.3 Collection toolbar (`CollectionToolbar`, `AskField`, `FilterPills`)
- **AskField**: the one search box. Placeholder says both jobs ("Ask a question or search these documents…"). Shows a `/` key hint; `/` anywhere outside an editable element focuses it; Esc clears; Enter submits. Role `search`, `aria-keyshortcuts="/"`. Only one AskField per page binds the shortcut.
- **FilterPills**: single-choice radio group (arrow keys move, roving tabindex), first pill is "All". Each pill: label + mono count. A pill that means "you must act" takes the `attention` tone on its count. Zero-count optional pills may hide (`hideEmpty`) — never the selected one.
- While search results are showing, hide the filter row (results are not filtered by status).

#### 6.10.4 Resource list (`ResourceList`, `ResourceRow`, `TypeGlyph`)
- One bordered `--panel` with a quiet column header (`Name · Origin · Status · Added`) — a ledger (§6.6), not cards.
- Row: `[TypeGlyph + title (+ reason line) | origin (mono, --steel-soft, truncated) | status pill | relative time | OverflowMenu]`. Below `md` the row collapses to title (+origin under it) and status + menu.
- **Status** uses the sentence-case `Badge` `pill-*` family: Ready → `pill-success`, Adding… → `pill-info`, Needs attention → `pill-warning`, Skipped → `pill-neutral`, Failed → `pill-danger`.
- **Reason line**: a problem row explains itself in one plain sentence under the title, with its own fix link ("This PDF is password protected. Retry").
- **Adding state** (`adding`): row arrives with the §8 **drop-in**, title in `--steel`, `aria-busy`. Arriving rows sort to the top.
- Hover → `--paper-deep`. Title is a button when the row opens a detail sheet.
- **Configurable columns**: the 4-label tuple keeps the default ledger. For other ledgers (a tables list: *Name · Rows · Fields · Updated*) pass column defs `ResourceColumn[]` (`{ key, label, width?: CSS grid track, align?: start|center|end }`). The first def is always the title cell (glyph + title + reason); each row passes `cells={{ [key]: node }}` for the rest; the overflow slot stays last (`2rem`). Below `md` only title + actions show. Never fake extra columns by stuffing several values into `origin`.

#### 6.10.5 Inline progress row (`ProgressRow`)
- A long-running job is a **row at the top of the list it fills** (inside `ResourceListSlot`), not a card above the page, not a toast.
- Copy: *"{Label} from {source} — {done} of {total} · {eta}   Cancel"*. Blinking `live` dot; thin bar (`h-1`).
- **Determinate** when the total is known (`role=progressbar` with value). **Indeterminate** when it is not: no fill, *"412 files found so far"*, no ETA. Never show a fake percentage.
- The text is a polite live region. Cancel is a link-weight action that opens a confirm; finished state replaces the row with a status sentence change (and an attention banner if anything failed) — the row disappears.

#### 6.10.6 Attention banner (`AttentionBanner`)
- One line at the top of the list: icon + count sentence (*"3 documents could not be added."*) + **one** fix action ("Retry all") + optional secondary ("Show them", which selects the attention filter pill). `--warning-tint` band, `role=alert`.
- Count only; per-item reasons stay on the rows. Never stack banners — merge into one sentence. Not rendered at count 0.

#### 6.10.7 Result / citation card (`ResultCard`, `ResultsNote`)
- Search/ask results replace the list. A `ResultsNote` says what the user is looking at (*"These are the passages your agents would read."*) with "Clear search".
- Card: `TypeGlyph` + title + mono location ("page 3") + match word (`High match` / `Good match` / `Weak match`, never a raw score) + passage with query terms in `<mark>` (`--signal` 15% tint) + "Open". `matchStrength(score)` owns the thresholds.
- Highlighting is done on plain text (`highlightTerms`), never by injecting HTML.

#### 6.10.8 Empty drop state (`StepHint`, `DropZone`)
- When the collection is empty: status sentence `off` (*"No documents yet"*), the AskField stays (disabled-looking is not needed — it simply returns nothing), filters and list are replaced by a **3-step hint** (`StepHint`: Add → Try → Connect; current step `aria-current="step"`) and a dashed **drop zone** with the accepted types and limits in plain words, and the primary + one secondary add action.
- The drop zone is a click/keyboard target too; drag-over switches the border to `--signal`.

#### 6.10.9 Settings side sheet (`SettingsSheet`, `SettingsSection`, `SettingsAdvanced`, `DangerZone`)
- Right sheet from the overflow menu's "Settings". Fixed order: everyday fields (name, description, the on/off switch with its consequence) → `SettingsAdvanced` (collapsed) → `DangerZone` last.
- Danger zone states the consequence with real numbers (*"Removes all 1,241 documents. This can't be undone."*); its button opens a confirm dialog, never acts directly.

#### 6.10.10 Next-steps checklist (`Checklist`)
- Shown once a resource first becomes usable; 2–4 items, done items checked and quiet, open items are actions. Dismissible; the caller persists dismissal. It is the continuation of the empty-state `StepHint` — the same steps, now with progress.

#### 6.10.12 Linked-items popover (`LinkedListPopover`)
- For a count of things linked to this resource that people want to see without leaving the page (*Used by 2 agents ▾*). The trigger is a link-weight `Button` with a chevron, usually inside the status sentence or a row.
- Popover (`w-72`): optional heading (*Agents using this*), up to ~8 visible rows (scrolls after), each = optional icon + label + optional mono meta (*3 calls today*); a row with `href` navigates, with `onSelect` acts, with neither is static. Empty state says what linking would do (*No agent uses this yet.*). Optional footer action after a separator (*Manage access*), `--signal-ink`.
- Built from `Popover`, `Button` (ghost / link, `asChild` for anchors) and `Separator` — no raw buttons. Esc and outside click close; focus returns to the trigger.

#### 6.10.11 Motion and states summary
| Pattern | Motion | Live region |
|---|---|---|
| Status sentence | dot blinks only for `live` | polite, only while changing |
| Resource row `adding` | drop-in once | `aria-busy` |
| Progress row | dot blinks | polite |
| Attention banner | none | `role=alert` |
All motion uses `motion-safe:` so `prefers-reduced-motion` disables it (§8).

**Migration targets** (adopt these patterns when next touched): Knowledge source page (all of the above; see the Knowledge handoff), Knowledge library cards (status sentence), Flows / Agents / Automations list filters (`FilterPills` for status filters), Batch jobs (`ProgressRow` for running jobs), Executions (`AttentionBanner` for failed runs).


### 6.11 Data grids (editable tables)

A **data grid** is the place people *work in* a collection of records the way they would in a spreadsheet: read, edit in place, filter, select many, import. It is not a read-only ledger (§6.6) or a resource list (§6.10.4) — use those when rows are things you open, not values you edit. The patterns live in `frontend/src/components/grid/` (import from `@/components/grid`), are domain-free (rows are opaque, columns describe types), and are built only from `components/ui` primitives and §2 tokens. **Never hand-roll a grid, a filter chip row, a bulk bar, an import mapper or a permission matrix on a page.**

Reading order: **head (§6.9) → GridToolbar → DataGrid → GridFooter**; overlays on top of the grid, never routes: filter popover, fields menu, `RecordDrawer`, import dialog with `ImportMapper`, `ConfirmDestructive`. `BulkActionBar` floats while rows are selected.

#### 6.11.1 Anatomy (`DataGrid`)
- One `--panel` with a hairline border, `rounded-lg`, scrolling inside itself (`max-h-[70vh]` default), sticky `--paper-deep` header.
- Columns, left to right: selection checkbox (when `onSelectedChange`), row number (mono, `--steel-soft`; a button that opens the record when `onOpenRow`), then data columns. A trailing "Add row" line (`onAddRow`) with its `⌘ Enter` hint.
- Header cell: type glyph (`TYPE_ICON`, `--steel-soft`) + label + optional quiet `tag` ("title", "key") + `*` when required. Numeric headers right-align. The type is announced to screen readers ("Seats, Number").
- Row height is fixed at 36px (`GRID_ROW_H`); text truncates in the cell; long values are read in the drawer.

#### 6.11.2 Types (`ColumnType`, `types.ts`)
One vocabulary, user words, one glyph each: **Text, Long text, Number, Currency, Date, Dropdown (select), Link, Checkbox**. Storage types (Data, Int, Float, Small Text) never reach the UI; the app maps its storage types to these once (in its own data layer) and the grid formats and parses them in one place (`formatCell`, `parseCell`).

| Type | Display | Editor |
|---|---|---|
| Text | truncated text | `Input size=sm` |
| Long text | first line, truncated | `Textarea` (Enter saves, Shift+Enter new line) |
| Number / Currency | right-aligned, tabular, separators; currency with 2 decimals, code in header | `Input` (`inputMode=decimal`), accepts `1,200.50` |
| Date | `10 Dec 2026` (locale) | `Input type=date` |
| Dropdown | sentence-case `pill-*` coloured by the option's **tone** (`TONE_PILL`) | `Select`, opens immediately; choosing saves |
| Link | `--signal-ink` text + external glyph | `Input` |
| Checkbox | `Checkbox`, toggles in place (no edit mode) | — |

#### 6.11.2a Type picker (`ColumnTypePicker`, `ColumnTypeList`)
- Choosing a field type is choosing a meaning: each option is icon + user word + one-line description (*Currency — Money, shown with two decimals.*), grouped (Text, Numbers, Date, Choice, Reference) and searchable above 8 options. `ColumnTypePicker` is the popover form (closes on pick); `ColumnTypeList` is the inline list for sheets/create forms. Options default to `gridTypeOptions()` from `TYPE_LABEL`/`TYPE_ICON`/`TYPE_DESCRIPTION`; apps with a wider vocabulary (rating, phone, layout breaks) pass `ColumnTypeOption[]` with their own `value`s — still user words, never storage type names. `role=listbox`, options `aria-selected`, ↑/↓ move.

#### 6.11.3 States
| State | Look | Behaviour |
|---|---|---|
| Rest | hairline grid | hover tints the row `--paper-deep/60` |
| Active cell | 2px inset `--signal` ring | one per grid; roving `tabIndex=0` |
| Editing | editor fills the cell, borderless | the cell keeps the ring |
| Invalid | `--destructive-tint` cell, red ring, one-line fix hint under the cell + "Esc to undo" | editor stays open; `aria-invalid`, hint is `role=alert` |
| Selected row | `--signal/5` tint, `aria-selected` | Shift-click selects a range from the last clicked row; the anchor resets when the row set changes (page, sort, filter) |
| Read-only column | no edit on type/Enter | `aria-readonly` |
| Empty | `empty` slot in place of rows (an §6.10.8-style start) | |
| Large | > `windowFrom` (100) rows render a window + spacer rows | keyboard scrolls the active row into view |

#### 6.11.4 Keyboard (spreadsheet muscle memory)
| Mode | Key | Does |
|---|---|---|
| Navigate | Arrows / ⌘+Arrows | move one cell / to the edge |
| Navigate | Tab / Shift+Tab | next / previous cell, wrapping rows; leaves the grid at the ends |
| Navigate | Enter or F2 | edit (checkbox: toggle) |
| Navigate | any printable key | edit, replacing the value with that key |
| Navigate | Backspace / Delete | edit with an empty value |
| Navigate | Space | toggle a checkbox cell |
| Navigate | Shift+Enter | open the row in the drawer (`onOpenRow`) |
| Navigate | ⌘V | paste tab-separated rows at the active cell (`onPaste`, `parseTsv`: quoted cells may hold tabs, newlines and `""` escapes, as Excel/Sheets copy them) |
| Edit | Enter | save, move down |
| Edit | Tab / Shift+Tab | save, move right / left |
| Edit | Esc | cancel, restore the old value, focus back on the cell |
| Header | Enter / Space / click | sort this column: none → ascending → descending → none |

Saving: `onCellChange(rowId, key, value)` may return or resolve a one-line message (or throw) to reject the value; the grid shows it as the invalid state. Required columns reject empty values ("Company can't be empty"); `validate` adds per-column rules.

#### 6.11.5 Toolbar (`GridToolbar`, `FilterChip`, `SortChip`, `MatchCount`, `FieldsMenu`, `GridFooter`)
- Order: search (`AskField` from §6.10.3; `/` focuses it) → `Filter` / `Sort` / `FieldsMenu` triggers (outline `sm` buttons) → applied chips → right side `MatchCount` + `AutosaveStatus` (§6.12.6).
- **FilterChip** reads as a sentence — *Status is Active*, *Renewal is before 1 Jan 2027* — with plain operators (is, is not, contains, is before, is empty). The body opens its editor popover; × or Backspace/Delete removes it. **SortChip**: *↑ Renewal Oldest first*, click reverses, × removes; direction words fit the type (A→Z, 1→9, Oldest first).
- **Sortable headers**: give `DataGrid` `sort` + `onSortChange` and every header becomes a button (columns opt out with `sortable: false`). Click, Enter or Space cycles none → asc → desc → none (`nextSort`); the `th` carries `aria-sort`; the arrow is `--signal` when active and appears on hover/focus otherwise. The same `{ key, direction }` drives the toolbar `SortChip` (use `sortDirectionLabel(type, direction)` for its words) — one sort state, two controls. Header keys never reach the cell navigation.
- **FilterBuilder / FilterEditor**: the Filter trigger plus applied chips. The editor is field → condition → value: conditions come from `filterOpsFor(type)` (text: is, is not, contains, does not contain; numbers: is more/less than, is at least/most; dates: is before/after; dropdown and link: is / is not; checkbox: is; every type but checkbox: is empty / is not empty), and the value editor fits the type (`FilterValueInput`: date input, decimal keypad, option list, Yes/No checkbox; no value for *is empty*). Each condition is `{ field, op, value: string }`; callers map it to their query language once. Clicking a chip reopens the editor with *Update*.
- **MatchCount**: *212 of 1,284 rows* while filtered, *1,284 rows* otherwise — true totals from the server. Polite live region.
- **FieldsMenu**: checkbox list to show/hide columns; the title field is `locked`. The trigger shows "N hidden".
- **GridFooter**: *Showing 1–25 of 1,284 rows*, a pager slot, and the key legend (Tab next · Enter save · Esc cancel · ⌘V paste rows). When the backend can't count cheaply, say so honestly: `approximate` → *Showing 1–25 of 25+ rows* (at least this many), `total={null}` → *Showing 1–25 rows*. Never invent a total.

#### 6.11.6 Bulk selection (`BulkActionBar`)
- Floats bottom-centre over the grid (`--ink` bar, `shadow-lg`, drop-in): *3 rows selected* · *Select all 1,284* (when only a page is selected) · actions · ×. Non-destructive actions first, destructive last. Esc clears.
- Destructive bulk actions open `ConfirmDestructive`; row delete offers undo in a toast when the backend can restore.

#### 6.11.7 Record drawer (`RecordDrawer`)
- Right sheet for one record: title, *4 of 1,284* with previous/next (Alt+↑/↓), all fields as `Field`s (long text gets room), then History. Use it for long text and wide tables; the grid stays the place to scan.

#### 6.11.8 Permission matrix (`PermissionMatrix`)
- Subjects (rows, `th scope=row`) × capabilities (columns) of checkboxes, each named "{capability} for {subject}". Capabilities declare `implies` (Edit → Read); `applyGrant` keeps the matrix consistent both ways (granting adds what it needs, revoking removes what depended on it). Arrow keys move; Space toggles. A `rowEnd` slot holds per-row actions.

#### 6.11.9 Change impact (`ChangeImpactNotice`)
- Before any edit that touches existing data (type change, field delete, import "replace"), show counts inline above the save button: *1,180 values convert · 104 values will be cleared*. Safe lines are quiet; loss lines are emphasised and switch the notice to `--warning` (or `--destructive` with `severity=error` when nothing can be restored). While counting: *Checking your data…*. Rename-only changes say they are safe.
- Optional footer: `onConfirm` / `onCancel` (`confirmLabel` default *Apply change*) render right-aligned buttons inside the notice; confirm is `destructive` when a loss line has a count, disabled while `checking`, and shows a spinner while `confirming`. Use the footer when the notice *is* the confirm step (inline type change, import replace). When others depend on the thing being removed, open `ConfirmDestructive` from the confirm instead — never both stacked.

#### 6.11.10 Destructive confirm (`ConfirmDestructive`)
- The one dialog for deleting or replacing something others depend on: consequence with real numbers (*Removes 1,284 rows and 7 fields*), a **dependents list** (kind + name: *Agent · Billing agent*, *Flow · Renewal reminder*), recovery truth (*You can restore it for 30 days* / *This can't be undone*), optional type-the-name confirm, an optional gentler `alternative` (*Turn off instead*). The action stays disabled until the typed name matches.

#### 6.11.11 Import (`ImportMapper`)
- The review step of any file import: one row per incoming column — header + 3 sample values (mono) → target `Select` (fields with their type, *New field "X"*, *Don't import*) → a check in plain words (*All valid*, *12 not dates*, *Skipped*). Then a preview of the first rows, then the result line (*1,272 rows ready · 12 can't be imported · Download rejected rows*) and the rejected rows with reasons. Above the mapping: a `--warning` alert when a `required` target has no column (*Required field Name has no column. New rows will be rejected unless you map one.*) and a quiet note listing the columns set to *Don't import* (*2 columns won't be imported: Fax, Notes*) — `importGaps(columns, targets)` computes both. *New field "X"* calls `onCreateTarget(header, detectedType)` so the create form preselects the type. The import button imports the valid rows; mode (add / update by key / replace) sits in the `header` slot, and "replace" shows a `ChangeImpactNotice`.

#### 6.11.12 Copy, motion and a11y
- Copy: user words for types and operators; counts with separators; errors say how to fix (*Enter a number, like 1200*), never codes.
- Motion: only the §8 drop-in (bulk bar, revealed settings); no animated cell transitions. All `motion-safe:`.
- A11y: `role=grid` with `aria-rowcount`/`aria-colcount`/`aria-rowindex`; one tabbable cell; editors labelled by their column; errors `role=alert` and wired by `aria-describedby`; checkboxes named per row; match count and bulk count are polite live regions.

**Migration targets:** Tables grid/list/fields/agents/import/delete (see `tracks/tables-ux/DS_HANDOFF.md`); any admin page that edits rows in place; agent/tool access grids (`PermissionMatrix`); every "Are you sure?" delete that has dependents (`ConfirmDestructive`).

---

### 6.12 Builder forms (configure + try)

A **builder** is a page where people configure one thing and immediately see it work: an assistant, an automation, a widget, a template. The layout is **configure on the left, try on the right**. Patterns live in `frontend/src/components/builder/` (import from `@/components/builder`), domain-free, built from `components/ui`, §6.10 patterns and tokens.

Reading order: **head (title + status pill + `AutosaveStatus` + one primary action) → tabs (§6.5, at most five, plain names) → `ErrorSummary` when a save failed → `FormSection`s** in the main column; **`TryPanel`** in the sticky side column. Creation is a separate **`OneCardCreate`** that ends in the builder.

#### 6.12.1 Layout (`BuilderLayout`)
- Main column `minmax(0,1fr)` + side panel 400px (`asideSize=lg` → 480px) from `lg` up; the panel is sticky (`top-4`, viewport height) so it stays in view while sections scroll. Below `lg` it stacks after the main column. The side panel is a labelled `aside`.

#### 6.12.2 Sections and inline validation (`FormSection`, `RequiredMark`, `FieldError`, `focusFirstError`, `ErrorSummary`)
- `FormSection`: `--panel` card, `text-subtitle` title, one-line description that says what the section does, optional head action ("Change").
- Fields are `ui/field` with `required` (renders the `*`) and `error` (renders the note, `aria-invalid`, `role=alert`). Use `RequiredMark` / `FieldError` only for custom controls not wrapped in `Field`.
- Validate on blur and on save, never on every keystroke. On a failed save: call `focusFirstError(form)` and show **one** `ErrorSummary` (*2 things need fixing* + a jump link per error). Never only a toast.
- Error copy says what to do: *Add instructions so it knows what to do*, not *Field required*.

#### 6.12.3 Switches that reveal (`ToggleReveal`, `ToggleRow`)
- `ToggleReveal`: label + one-sentence consequence + `Switch`; when on, its dependent settings appear below in a labelled region (drop-in), with `aria-controls`/`aria-expanded`. When off they are not rendered (their values are kept by the caller).
- `ToggleRow`: a row in a list of optional items — title, description, a tone-dot status line (*Ready*, *Needs a connection*), trailing actions, switch.

#### 6.12.4 Presets (`PresetSelector`)
- Named presets replace raw numbers (*Precise · Balanced · Creative*), each with a one-line description; one may be `recommended`. A radio group (arrows move and select). An optional **Custom** option reveals the raw controls. Raw parameters otherwise live under Advanced / Developer options.

#### 6.12.5 Templates and suggestions (`TemplateChips`)
- Outline pill buttons that **fill** the form (or the composer) — never submit. Used on the create card and as Try-panel empty-state suggestions.

#### 6.12.6 Autosave (`AutosaveStatus`)
| State | Copy | Look |
|---|---|---|
| `dirty` | Unsaved changes | `--steel` |
| `saving` | Saving… (spinner) | `--steel` |
| `saved` | Saved just now / Saved 4 min ago / Saved at 14:02 | `--steel`, check |
| `error` | Couldn't save · Retry | `--destructive`; Retry re-runs the save |
- A polite live region in the head, next to the primary action. Conflicts use `errorText` (*Someone else changed this · Reload*).

#### 6.12.7 Try panel (`TryPanel`, `Inspector`)
- Head: title (*Try it*), a neutral pill for what is being tried (*Draft · not published*), Reset. Optional **coaching banner** slot under the head (an `AttentionBanner` that names the fix and links to it).
- Log (`role=log`, polite): user messages right on `--ink`, replies left on `--paper-deep`; a pending reply shows its current step with a spinner (*Looking up order 1042…*). Each reply may carry **inspector** chips: `call` (an action it ran), `source` (*Read: Returns policy.pdf*, signal tint), `metric` (*1.8s*, *412 tokens*, mono); failed items are red.
- Screen readers: the log is not live and is `aria-busy` while a reply runs; each finished reply is announced once through a visually hidden polite region; messages carry sr-only *You:* / *Agent:* labels.
- Empty: suggestions (`TemplateChips`), rendered outside the log. Composer: Enter sends, Shift+Enter new line. Footer slot: model line, *View run details*.
- It renders state; the caller runs the conversation against the **current draft**.

#### 6.12.8 Create (`OneCardCreate`, `StepCard`)
- `OneCardCreate`: one centred card (`max-w-xl`, `shadow-md`) with only what's needed to get a working thing (name + the one essential field + template chips), defaults for everything else, and a verb that creates and opens it (*Create and try it*). ⌘Enter submits.
- `StepCard`: numbered card for a short guided sequence on one page (current step raised, done steps quiet with a check, `aria-current=step`).

#### 6.12.9 Motion and a11y
- Motion: drop-in for revealed settings only; spinner while saving/running. All `motion-safe:`.
- A11y: switches are labelled by their visible label and described by their consequence; presets are a radio group; errors are announced and linked; the try log and autosave status are polite live regions; spinners inside live regions are `aria-hidden`.

**Migration targets:** Agent form (see `tracks/agent-form-ux/DS_HANDOFF.md`); any settings page with on/off features (`ToggleReveal`); any slider of model parameters (`PresetSelector`); any form that only toasts on validation failure (`ErrorSummary` + `focusFirstError`).

---

## 7. Status & Indicator Vocabulary

This is the unifying signal language across marketing and product — the same dot/color means the same thing everywhere:

| Indicator | Color | Motion | Meaning |
|---|---|---|---|
| Solid square (8px) before eyebrows | `--signal` | static | "Read this label — section marker" |
| Dot in ledger header ("Recording") | `--signal` | blink (1.6s steps(2)) | Live capture in progress |
| `HELD` / review status | `--signal-ink` (text only) | static | Action paused for human review |
| Dot — *Running* | `--signal` | blink | Agent actively executing |
| Dot — *Idle* | `--steel-soft` | static | Agent configured, not currently running |
| Dot — *Healthy* | `--good` | static | Agent running normally / no issues |
| Gauge value in flag state | `--signal-ink` | static | Metric crossed a threshold worth noticing |
| Left-edge rail on hover (spec rows) | `--signal` (3px) | appears on hover | "This is the focused/selected line" |
| Active nav item edge | `--signal` (2px) | static | Current location |

**Never** introduce a second accent color. Beyond `--signal`, only the three status colours exist (`--good`, `--warning`, `--destructive`, each with a `-tint`), and they are reached through tones (`patterns/tones.tsx`), never picked by a page.

---

## 8. Motion Principles

- Motion is used **only** where it demonstrates the product's actual behavior (live recording, running agents) — never as ambient decoration.
- Two motion patterns total:
  1. **Blink** (`opacity` pulse, `1.6s steps(2) infinite`) — for live/recording/running indicators.
  2. **Drop-in** (fade + 6px slide, `0.35s ease-out`) — for new ledger rows arriving.
- All motion respects `prefers-reduced-motion: reduce` (disable both).
- No hover-lift, no scroll-triggered fade-ins, no parallax, no gradient animation.

---

## 9. Iconography

- Outline/stroke icons only, `stroke-width: 1.5–2`, no fills (except small status dots and the marker square).
- Color: `--steel` default, `--ink` on hover/active — icons never carry the signal color except as part of a status dot.
- No icon-in-colored-rounded-square containers (the single biggest "AI template" tell in the original design).
- Lucide React icons used throughout the marketing site.

---

## 10. Core CSS Tokens (Reference)

The source is `frontend/src/index.css` (`:root` light, `[data-theme="midnight"]` dark). Abridged:

```css
:root{
  --paper:#FBFBFD; --paper-deep:#F4F4F7; --panel:#FFFFFF;
  --ink:#1D1D1F; --ink-soft:#2A2F36; --steel:#6E6E73; --steel-soft:#98989D; --line:#ECECF0;
  --signal:#7A5AF0; --signal-ink:#5B3FC4;
  --good:#1C7C54; --good-tint:#E8F5EE; --warning:#8A5A00; --warning-tint:#FDF3E0;
  --destructive:#B3261E; --destructive-tint:#FDECEA;
  --r:8px; --r-sm:6px; --r-md:10px; --r-lg:14px; --r-xl:14px; --r-full:999px;
  --shadow-flat:none; --shadow-raised:0 1px 2px rgba(0,0,0,.05); --shadow-overlay:0 8px 24px -8px rgba(0,0,0,.16);
  --space-1:4px … --space-7:48px;
  --control-h-sm:30px; --control-h-md:34px; --control-h-lg:38px;
  --display/--body: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --mono: ui-monospace, 'SF Mono', Menlo, monospace;
  --text-display/title/subtitle/body/ui/micro/meta/eyebrow-*: see §3.1
}
@keyframes blink{ 50%{ opacity:.2 } }
@keyframes drop{ from{opacity:0; transform:translateY(-6px)} to{opacity:1; transform:none} }
```

`[data-theme="winter|summer|morning"]` blocks are dead code from the retired theme picker — do not use them.

---

## 11. Tailwind Config (Reference)

`frontend/tailwind.config.*` maps every token to a utility, so pages never need a raw value: colours (`bg-paper`, `text-steel`, `border-line`, `bg-signal/5`, `bg-good-tint` …), `rounded` → `--r` (and `-sm/-md/-lg/-xl/-full`), `shadow-md` → `--shadow-raised`, `shadow-lg`/`xl`/`2xl` → `--shadow-overlay`, `h-control-sm/md/lg`, `px-control*`, type sizes `text-display / text-title / text-subtitle / text-body-text / text-ui-text / text-micro / text-meta`, `font-sans/display/mono` → the CSS stacks, and `animate-blink` / `animate-drop`. Add a token to `index.css` and a key here before using a new value anywhere.

---

## 12. Quick Checklist Before Shipping a New Screen

**Every product screen**
- [ ] Built from `components/ui`, `@/components/patterns`, `@/components/grid` and `@/components/builder`; a missing shape was added to the system first, not hand-rolled on the page.
- [ ] Colours, radius, shadows, spacing, control heights and type come from tokens (§2–§4); no hex, no `text-[Npx]`, no `h-6..h-11` on controls, no inline styles (`python3 scripts/run_standards.py` passes).
- [ ] No gradients; shadows only on raised cards (`shadow-md`) and floating layers (`shadow-lg`).
- [ ] Signal purple used at most 1–2 times as a fill; otherwise ring / dot / edge / tint / one link.
- [ ] Status via a tone (dot + label, or `pill-*` from the tone) — never a page-picked colour.
- [ ] Sentence case; mono only for machine values; numbers with thousands separators.
- [ ] Motion limited to blink (live) and drop-in (arrivals, reveals), all `motion-safe:`.
- [ ] Works in `midnight` (dark) without page changes.

**Resource pages (§6.10)**
- [ ] Built from `@/components/patterns`; no hand-rolled status line, filter row, progress card, banner, drop zone or settings tab.
- [ ] One primary action in the head; everything else in the overflow menu; destructive items last.
- [ ] No tabs unless there are two peer collections (§6.10.1); settings live in a side sheet.
- [ ] Status sentence tone matches §7 (`live` blinks, nothing else does); counts use thousands separators.
- [ ] Long jobs show as an inline progress row; unknown totals are indeterminate ("N found so far"), never a fake percent.
- [ ] Problems: one attention banner with one fix + a reason line on each affected row.
- [ ] Search results show match words, not scores; highlighting is on plain text.
- [ ] "/" focuses the ask field; filter pills work with arrow keys; progress text is a polite live region.
- [ ] "Used by N …" counts open a `LinkedListPopover`, not a custom popover or a tab.

**Data grids (§6.11)**
- [ ] The grid is a `DataGrid`; toolbar, chips, bulk bar, drawer, import, matrix and confirms come from `@/components/grid`.
- [ ] Column types are user words with their glyph (Text, Long text, Number, Currency, Date, Dropdown, Link, Checkbox); storage types never reach the UI.
- [ ] Tab / Enter / Esc / arrows / type-to-edit work; Esc restores the old value; invalid values show a one-line fix hint on the cell.
- [ ] Counts are true totals (*212 of 1,284 rows*), from the server.
- [ ] Filters read as sentences and are removable by × and Backspace; sorts say their direction in type-aware words.
- [ ] Any change that touches existing data shows a `ChangeImpactNotice` with counts before save.
- [ ] Every delete/replace with dependents uses `ConfirmDestructive` with the dependents list and the recovery truth; typed confirm for whole collections.
- [ ] Imports go through `ImportMapper`: mapping, per-column checks, preview, import valid rows, download rejected rows.
- [ ] Permission grids use `PermissionMatrix` with declared implications.

**Builder forms (§6.12)**
- [ ] `BuilderLayout` with the try / preview panel sticky beside the form; the panel tries the current draft.
- [ ] Creation is one `OneCardCreate` card with defaults and a verb that opens the builder.
- [ ] At most five tabs with plain names; jargon is behind Advanced / Developer options.
- [ ] Required fields marked (`Field required`); validation on blur and save; failed save → `focusFirstError` + one `ErrorSummary`; error copy says how to fix.
- [ ] Features that need settings use `ToggleReveal`; optional items use `ToggleRow` with a status line.
- [ ] Raw numeric parameters are `PresetSelector` presets (with Custom when needed).
- [ ] The head shows `AutosaveStatus`; failure offers Retry; never a silent save failure.
- [ ] Try panel shows what happened: calls, sources, latency/tokens, and a coaching banner that links to the fix.

**Marketing surface** — separate site; see §3.2 history. Product rules above do not apply to `huf-redesign.html`.

---

## 13. Reference Artifacts

- `huf-redesign.html` — marketing landing page: nav, hero w/ Agent Event Ledger, stack strip, fault report, spec index, dark control plane, CTA.
- `huf-dashboard-redesign.html` — product dashboard: instrument-panel sidebar, topbar, gauge strip, underline tabs, Active Agents ledger rows.
- `DESIGN.md` (this file) — the canonical spec for the design system.

Both HTML files are self-contained and can be used directly as living references when building new screens or handing off to implementation.
