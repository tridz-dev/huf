# HUF Design System

## Instrument / Control-Room Direction

**Status:** v1.1 — derived from marketing redesign (`huf-redesign.html`) and product UI redesign (`huf-dashboard-redesign.html`)

**v1.1 change:** introduces a **product type layer** (§3.1) — the marketing site keeps its loud Big Shoulders / Archivo / Martian Mono voice, but the product UI runs on a calmer, more legible workhorse (IBM Plex Sans + IBM Plex Mono) with display type rationed to a few character moments. This makes the app feel like a tool you live in (Slack / Grafana / Redis dashboard) rather than a poster you read once.

**Core idea:** HUF's real differentiator isn't "AI" — it's *control*: every agent action is recorded, permissioned, and auditable. The visual system should feel like an instrument panel or engineering ledger, not a glowing AI-startup gradient page. Light technical paper, condensed industrial type, hairline rules, and a single signal color used the way a warning lamp is used — sparingly, and always meaningfully.

---

## 1. Why this direction (and what it replaces)

| Generic "AI slop" pattern | HUF system |
|---|---|
| Dark mode by default, purple→violet gradients | Light technical paper background; one dark section reserved for "inside the engine" (Control Plane) |
| Inter/system font everywhere | Three deliberate typefaces, each with one job |
| Rounded cards with colored icon-in-square + soft shadow | Hairline-bordered panels, 2px radius max, no shadows (one hard offset shadow only on the signature ledger) |
| Numbered feature cards (01/02/03) as decoration | Numbering used only where it's *true* — fault codes (F-01), spec/part codes (AGT-01) |
| Fake dashboard screenshot as hero | Live, real signature component: the **Agent Event Ledger** |
| Status shown as colored badge pills | Status shown as a dot + mono label (dot color = meaning, not decoration) |

**Rule of thumb:** the signal color (orange) means *"look here"* — active state, live/running status, flagged values, one emphasized word per headline. It should never be used for general decoration or as a second brand color.

---

## 2. Color tokens

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#F2F3EF` | Primary background (replaces white/light-gray app background) |
| `--paper-deep` | `#E9EBE4` | Secondary surface — sidebars, hover states, recessed panels |
| `--panel` | `#FBFCFA` | Elevated surface — cards, ledgers, content panels (product UI only) |
| `--ink` | `#15181C` | Primary text, headings, borders on key elements |
| `--ink-soft` | `#2A2F36` | Secondary dark surfaces (marketing dark section text on `--ink`) |
| `--steel` | `#5A636F` | Secondary text — descriptions, labels, metadata |
| `--steel-soft` | `#8A929C` | Tertiary text — placeholder icons, disabled, faint metadata |
| `--line` | `#C7CCC0` / `#D7DACF` | Hairline borders and dividers (marketing/product variants) |
| `--line-dark` | `#343A42` | Borders on dark sections |
| `--signal` | `#E8531F` | **The** accent. Active states, live indicators, emphasis, primary CTA hover |
| `--signal-ink` | `#BC3E0F` | Darker signal — emphasized headline words, link underlines, flagged numeric values |
| `--good` | `#3F7A4E` | Healthy/success status dot (product UI only) |

**Usage discipline:**
- No gradients, anywhere.
- Signal orange appears at most once or twice per screen as a *fill*; everywhere else it's a dot, underline, border-edge, or single word.
- The dark (`--ink`) background is reserved for one structural meaning: "this is the control plane / inside the system." Don't use it for arbitrary sections.

---

## 3. Typography

HUF runs **two type layers** that share a philosophy but serve different jobs. The marketing site is a poster — it can be loud. The product is a workspace — it must be quiet and legible. Both keep Big Shoulders for *character moments* (titles, big numbers, buttons), but they differ in what carries the everyday text and data.

### 3.0 Marketing type layer (`huf-redesign.html`)

Three typefaces, three jobs. Never substitute one for another's role.

| Typeface | Role | Where used |
|---|---|---|
| **Big Shoulders** (600/650/700, condensed, uppercase) | Display — the "machine signage" voice | Page titles (`H1`/`H2`), hero headline, large stat numbers/gauge values, dark-section headlines |
| **Archivo** (400/500/600) | Body — the working voice | Paragraphs, ledes, descriptions, card titles |
| **Martian Mono** (400/500) | Data / instrumentation voice | Eyebrows, fault/spec codes, timestamps, model names, IDs, run counts, status labels, telemetry, footnotes |

**Font embed (marketing):**
```html
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders:opsz,wght@10..72,600;10..72,650;10..72,700&family=Archivo:wght@400;500;600&family=Martian+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### 3.1 Product type layer (`huf-dashboard-redesign.html`) — **NEW in v1.1**

The dashboard is something people stare at all day. Condensed display caps and a heavy geometric mono on every label create eye strain and a "designed object" feeling that fights usability. So the product swaps the two *workhorse* roles for the **IBM Plex** family — engineering-credible (it keeps the instrument theme) but far calmer and more legible at UI sizes, the way Slack, Grafana, and the Redis dashboard feel. Display type stays, but is **rationed to character moments only.**

| Typeface | Role | Where used in product |
|---|---|---|
| **Big Shoulders** (700, uppercase) | Character / accent only | Page `<h1>`, the large gauge values, section panel headers ("Active Agents"), and **primary button labels** — the few places a little personality earns its keep |
| **IBM Plex Sans** (400/500/600) | **UI workhorse** | Everything chrome: nav labels, table/row text, descriptions, breadcrumbs, status labels, form fields, menu items, secondary buttons |
| **IBM Plex Mono** (400/500) | Data voice (lightened) | Technical metadata only: IDs (`agt_3f81`), model names, timestamps, counts, codes, telemetry values. Replaces Martian Mono — lighter color, normal letter-spacing, much easier to scan in dense tables |

**Why IBM Plex Sans specifically (and not Inter):** Inter is the literal default of every AI dashboard template — using it would re-introduce the slop signal we removed. Plex Sans is equally legible but carries a subtle slab/engineering DNA that stays on-theme, and it's clearly distinguishable in a screenshot. It's the product's neutral, so it should feel almost invisible — that's the point.

**The character/workhorse split (memorize this):**
- **Character → Big Shoulders:** page title, big numbers, panel headers, primary CTA. *Loud, rare, intentional.*
- **Workhorse → IBM Plex Sans:** every other piece of text. *Quiet, everywhere, invisible.*
- **Data → IBM Plex Mono:** identifiers and machine values only. *Never used for prose or UI labels.*

**Font embed (product):**
```html
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders:opsz,wght@10..72,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Type scale & treatment

**Marketing:**
- **Eyebrows** (mono, 11px, `letter-spacing: .14em`, uppercase, `--steel`) — preceded by an 8px solid signal-orange square. The recurring "tune in here" device.
- **H1 (hero)** — Big Shoulders 700, `clamp(64px, 8.5vw, 118px)`, line-height `.92`, uppercase. One word per headline in `--signal-ink`.
- **H2 (section)** — Big Shoulders 650, `clamp(44px–84px)`, uppercase.
- **Body / lede** — Archivo, 17–18px, `--steel`, max-width `46–52ch`.

**Product:**
- **Page `<h1>`** — Big Shoulders 700, ~34–38px, uppercase. The one big display moment per screen.
- **Panel headers** ("Active Agents") — Big Shoulders 700, ~17–18px, uppercase. Smaller character anchor for sections.
- **Gauge values** — Big Shoulders 700, 38–44px, with a small **IBM Plex Mono** unit/sub-label (`%`, `s`, cents) at ~30–40% size in `--steel`.
- **UI text** (nav, rows, descriptions, breadcrumbs) — IBM Plex Sans, 13–14.5px, `400–600`, sentence case (not uppercase — uppercase is reserved for display + mono labels).
- **Button labels** — primary button: Big Shoulders 600 uppercase ~13px with `.06em` tracking (keeps a little character); secondary/ghost button: IBM Plex Sans 600, 13px, sentence or small-caps. Buttons no longer use mono in the product — mono is now data-only.
- **Mono data** — IBM Plex Mono, 11–12px, **normal letter-spacing** (drop the wide tracking Martian Mono needed), normal case for values, light uppercase only for short status labels.

**Restraint note (still applies, sharpened):** in the product, Big Shoulders appears in exactly four kinds of place — the page `<h1>`, gauge values, panel headers, and the primary button. Everywhere else is IBM Plex Sans (UI) or IBM Plex Mono (data). If you find yourself setting a table cell, a description, or a nav item in Big Shoulders or in mono, stop — that's the slip back toward "designed object."

---

## 4. Layout & Structural Primitives

| Primitive | Spec |
|---|---|
| **Border radius** | `2px` everywhere (`--r`). No pill shapes, no large rounded corners. |
| **Borders** | 1px hairline (`--line`) for dividers; 1px `--ink` for the outer edge of "instrument" containers (ledger, gauge strip, spec table top rule). |
| **Shadows** | None, except the signature ledger's hard double-offset shadow (`6px 6px 0 var(--paper-deep), 6px 6px 0 1px var(--line)`) — this is the one allowed "object on a desk" effect. |
| **Tick rule** | A repeating 1px-dash horizontal strip (`repeating-linear-gradient`) used as a section divider on the marketing page — evokes a chart recorder. Use sparingly, max once or twice per page. |
| **Grid** | Marketing: asymmetric splits (7/5, 5/7, 6/6). Product: fixed 248px sidebar + fluid content, max-width 1280px. |
| **Spacing** | Generous vertical rhythm on marketing (88–120px section padding); tighter, table-like rhythm in product (16–22px row/card padding). |
| **Wrap** | `max-width: 1240px; margin: 0 auto; padding: 0 32px` (marketing). Product content: `max-width: 1280px; padding: 36px`. |

---

## 5. Components — Marketing Site

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

Same tokens and structural primitives as marketing, but running on the **product type layer** (§3.1): IBM Plex Sans for all UI chrome, IBM Plex Mono for data, and Big Shoulders rationed to four character moments (page `<h1>`, gauge values, panel headers, primary button). The result reads like a tool, not a poster.

### 6.1 Sidebar (Instrument Panel)
- Background `--paper-deep`, 1px right border.
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

### 6.6 Ledger Rows
- One bordered panel (`--panel`, 1px `--line`) containing a **Big Shoulders** section header ("Active Agents") and stacked rows.
- Row grid: `[name + id | model (mono) | run count (mono, with icon) | status (dot + label) | chevron]`.
- **Name cell**: IBM Plex Sans semibold title + an IBM Plex Mono sub-line (`id · agt_xxxx`) underneath.
- **Status dot vocabulary** (see §7 below); the label sits in IBM Plex Sans, the dot carries the meaning:
  - `--signal` (orange), **blinking** → *Running*
  - `--steel-soft` (gray), static → *Idle*
  - `--good` (green), static → *Healthy*
- Row hover: background → `--paper-deep`, chevron color → `--ink`. No card lift/shadow on hover.

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

**Never** introduce a second accent color for status. Green (`--good`) is the *only* addition beyond the core palette, reserved exclusively for "healthy/success" states in the product UI — it does not appear in marketing.

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

```css
:root{
  /* Surfaces */
  --paper:      #F2F3EF;
  --paper-deep: #E9EBE4;
  --panel:      #FBFCFA;

  /* Text & lines */
  --ink:        #15181C;
  --ink-soft:   #2A2F36;
  --steel:      #5A636F;
  --steel-soft: #8A929C;
  --line:       #D7DACF;   /* product */
  --line-marketing: #C7CCC0;
  --line-dark:  #343A42;

  /* Signal */
  --signal:     #E8531F;
  --signal-ink: #BC3E0F;
  --good:       #3F7A4E;

  /* Shape */
  --r: 2px;

  /* Type — MARKETING layer */
  --display: 'Big Shoulders', sans-serif;  /* 600/650/700, uppercase, condensed */
  --body:    'Archivo', sans-serif;        /* 400/500/600 */
  --mono:    'Martian Mono', monospace;    /* 400/500 */

  /* Type — PRODUCT layer (v1.1) */
  --p-display: 'Big Shoulders', sans-serif; /* character moments only: h1, gauge values, panel headers, primary button */
  --p-ui:      'IBM Plex Sans', sans-serif;  /* 400/500/600 — UI workhorse, everything chrome */
  --p-mono:    'IBM Plex Mono', monospace;   /* 400/500 — data/identifiers only */
}

@keyframes blink{ 50%{ opacity:.2 } }
@keyframes drop{ from{opacity:0; transform:translateY(-6px)} to{opacity:1; transform:none} }
```

### Font embeds

**Marketing:**
```html
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders:opsz,wght@10..72,600;10..72,650;10..72,700&family=Archivo:wght@400;500;600&family=Martian+Mono:wght@400;500&display=swap" rel="stylesheet">
```

**Product:**
```html
<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders:opsz,wght@10..72,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```

---

## 11. Tailwind Config (Reference)

```js
// tailwind.config.js
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F2F3EF',
        'paper-deep': '#E9EBE4',
        ink: '#15181C',
        'ink-soft': '#2A2F36',
        steel: '#5A636F',
        'steel-soft': '#8A929C',
        line: '#C7CCC0',
        'line-dark': '#343A42',
        signal: '#E8531F',
        'signal-ink': '#BC3E0F',
      },
      fontFamily: {
        display: ['"Big Shoulders"', 'sans-serif'],
        body: ['Archivo', 'system-ui', 'sans-serif'],
        mono: ['"Martian Mono"', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '2px',
        sm: '2px',
        md: '2px',
        lg: '2px',
        xl: '2px',
        '2xl': '2px',
        '3xl': '2px',
        full: '2px',
      },
      animation: {
        blink: 'blink 1.6s steps(2) infinite',
        drop: 'drop 0.35s ease-out',
      },
      keyframes: {
        blink: { '50%': { opacity: '0.2' } },
        drop: {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
    },
  },
  plugins: [],
};
```

---

## 12. Quick Checklist Before Shipping a New Screen

**Both surfaces**
- [ ] Background is `--paper` / `--paper-deep` / `--panel` — not white, not dark, unless it's a "control plane" context.
- [ ] No gradients, no drop shadows except the signature ledger.
- [ ] Radius is 2px everywhere.
- [ ] Signal orange used at most 1–2 times as a fill; otherwise as dot/edge/underline/single emphasized word.
- [ ] Status communicated via dot + label, not a colored pill.
- [ ] Numbering/codes used only where they reflect a real taxonomy (fault codes, spec codes, IDs) — not decorative 01/02/03.
- [ ] Icons are outline-only, no colored container squares.
- [ ] Motion limited to blink (live/running) and drop-in (new row) — reduced-motion respected.

**Marketing surface**
- [ ] Body/lede in Archivo; eyebrows, codes, and data in Martian Mono.
- [ ] Big Shoulders for hero/section headlines and large stat numbers.

**Product surface (v1.1)**
- [ ] UI chrome (nav, rows, descriptions, tabs, breadcrumbs, secondary buttons) is **IBM Plex Sans**, sentence case.
- [ ] Technical metadata (IDs, model names, timestamps, counts, codes) is **IBM Plex Mono**, normal tracking.
- [ ] Big Shoulders appears in **only** four kinds of place: page `<h1>`, gauge values, panel headers, and the primary button label.
- [ ] No table cell, description, nav item, or tab is set in Big Shoulders or mono — if it is, that's the slip back toward "designed object."
- [ ] Uppercase reserved for display + short mono status labels; UI text stays sentence case.

---

## 13. Reference Artifacts

- `huf-redesign.html` — marketing landing page: nav, hero w/ Agent Event Ledger, stack strip, fault report, spec index, dark control plane, CTA.
- `huf-dashboard-redesign.html` — product dashboard: instrument-panel sidebar, topbar, gauge strip, underline tabs, Active Agents ledger rows.
- `DESIGN.md` (this file) — the canonical spec for the design system.

Both HTML files are self-contained and can be used directly as living references when building new screens or handing off to implementation.
