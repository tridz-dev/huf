# Chess HUF App — Design Spec

**Status:** grounded by Opus 5 Low against the actual pre-develop codebase; corrections
below are incorporated. Pending final user sign-off before claude_swarm implementation.
**Base:** origin/pre-develop @ 4e855147.
**Purpose:** a small, fully self-contained HUF App where a user plays chess against an
LLM-backed HUF Agent. Explicitly a reference/example app for how a HUF App can occupy
"one small intelligence slot inside a deterministic, highly-interactive app" rather than
being a chat surface — the opposite shape from Meeting Recorder, deliberately. Must be
independently readable by someone using it as a template for their own HUF App, with zero
code-sharing or cross-imports with the Meeting Recorder app.

## 1. Scope

**In scope (v0):**
- Single-player: user vs. HUF Chess Agent, one game at a time, no persistence beyond
  `localStorage` (recoverable across refresh, not across devices).
- Full legal chess via chess.js: castling, en passant, promotion (real picker UI, not
  auto-queen), check/checkmate/stalemate, and all of chess.js's draw conditions
  (insufficient material, threefold repetition, fifty-move rule).
- Agent returns exactly one move (validated against the legal-move list) plus an optional
  one-sentence comment.
- Standalone full-page route — no HUF sidebar/topbar chrome (see §4).

**Explicitly out of scope (v0, unchanged from the original proposal):**
- No Chess Game DocType / cross-device persistence / game history / sharing.
- No agent tools, no MCP, no realtime sockets, no multiplayer, no timers, no matchmaking,
  no Stockfish/engine opponent option, no ratings.
- No changes to shared infrastructure (`run_agent_sync`'s rate limit, the Agent doctype,
  the HUF App doctype) — chess consumes what exists as-is.

## 2. Independence contract

Every file this app touches is either brand-new under a chess-only path, or a single
additive line in a genuinely shared file (App.tsx's route table, install.py's hook calls,
package.json's dependency list). Nothing is imported from `huf/ai/meetings/` or
`frontend/src/{components,hooks,services}/meetings*`, and nothing chess-specific is added
to a shared meetings file. This is deliberate: a future HUF App author should be able to
read `huf/ai/chess/` and `frontend/src/{pages/ChessPage.tsx,components/chess/,hooks/useChessGame.ts,services/chessApi.ts}`
top to bottom as one coherent, standalone unit.

```
huf/ai/chess/
  __init__.py
  seed.py            # create_chess_agent(), create_chess_app() — fresh, no meeting imports

frontend/src/
  pages/ChessPage.tsx
  components/chess/
    ChessBoardPanel.tsx       # react-chessboard wrapper + drag/drop + promotion trigger
    PromotionDialog.tsx       # real piece-picker (Radix Dialog, existing primitive)
    MoveList.tsx              # mono SAN move list
    AgentStatusPanel.tsx      # dot+mono status, agent's comment
  hooks/useChessGame.ts       # chess.js instance + game state + agent-move orchestration
  services/chessApi.ts        # thin call.post wrapper around run_agent_sync

huf/install.py                 # thin wrapper calls only — real precedent is
                                #   create_hub_orchestrator_agent()/create_design_system_skill()
                                #   (install.py:540,553): a function-local deferred import
                                #   (`from huf.ai.chess.seed import ...` INSIDE the function
                                #   body, not module-level) wrapped in try/except with a
                                #   logger.warning, avoiding any import-order risk. Two call
                                #   sites: after_install (space-indented, ~2 lines) and
                                #   after_migrate (tab-indented, each call individually
                                #   try/except-guarded like the existing seeds at lines
                                #   210-228, ~4 lines) — NOT a uniform "+2 lines" in both.
frontend/src/App.tsx           # +1 route: standalone (no UnifiedLayout), lazy-loaded
frontend/package.json          # +2 deps: chess.js@^1.4.0, react-chessboard@^4.7.3
```

## 3. Architecture

```
User drags a piece
      │
ChessBoardPanel (react-chessboard v4.7.3 — v5 requires React 19, this repo is on 18.3.1)
      │ onPieceDrop(source, target, piece)
      ▼
useChessGame: chess.js .move() — throws on illegal (try/catch, not a null-check)
      │ updates fen, moves[] (SAN), checks isGameOver()/isCheckmate()/etc.
      │ writes moves[] to localStorage
      ▼
if game not over and it's the agent's turn:
      │
chessApi.requestAgentMove({ fen, moves, legalMoves })
      │ call.post('huf.ai.agent_integration.run_agent_sync', {
      │   agent_name: 'HUF Chess Player',
      │   prompt: <fen + move history + legal move list, see §5>,
      │   response_format: { type: 'json_object' },
      │   now: true,
      │ })
      │ (persist_conversation is NOT a run_agent_sync parameter — Frappe silently
      │  drops unknown kwargs. It's an Agent doctype field, set at seed time in §6.
      │  Even with it off, a fresh Agent Conversation + Agent Message row is still
      │  created on every move (agent_integration.py's create_new_conversation call
      │  runs regardless) — acknowledged DB churn, not a bug, no history is loaded
      │  back in so §7's "self-contained per-move prompt" assumption still holds.)
      ▼
gate on response.success === true (NOT response.status — direct-execution path has no
  status key; this is the exact bug already live in meeting_chat.py's ask_meeting, which
  gates on `result.get("status") == "Success"` on a now=True call and can never be true —
  chess must not repeat it)
      │
read response.structured (already JSON.parsed server-side via litellm response_format)
  fallback: if structured is falsy, scan response.response (freeform text) for a substring
  match against legalMoves before declaring failure
      ▼
chess.js .move(agentMove) — try/catch
  on failure: one repair request, same legal-move list, explicit "that was illegal" framing
  if repair also fails: leave the board unchanged, surface a readable error, let the user
    retry or resign — do not silently skip the agent's turn
      ▼
board updates, move appended to moves[] and localStorage
```

No new backend Python API module beyond the seed file. `run_agent_sync` is already
`@frappe.whitelist()` and already called directly from the frontend elsewhere in this
codebase (`agentApi.ts`) — confirmed, not assumed.

## 4. Standalone page, not app-shell chrome

Precedent already exists in this codebase: `/view/:messageId` → `PreviewViewPage` is
routed as **Standalone** — no `UnifiedLayout`, no `AppSidebar`, no topbar — unlike every
management/work-surface route. Confirmed mechanism (`App.tsx`'s route table): all routes
are flat siblings inside one `<Routes>` block; there is no wrapping `<UnifiedLayout>` tree
around them — each route *individually opts in* to `<UnifiedLayout>...</UnifiedLayout>` in
its own JSX, and `/view/:messageId` simply doesn't. Chess follows the same shape:
`<ProtectedRoute><Suspense fallback={<PageLoader/>}><ChessPage /></Suspense></ProtectedRoute>`,
no `UnifiedLayout` wrapper at all, full-viewport, with its own minimal chrome (a thin top
bar: "Chess" title + a "New game" action + a way back to `/`). (Note for future reference,
not used here: `UnifiedLayout` also supports `hideHeader`/`hideRail` props for a middle
ground, used by `/chat` — full omission is the right call for chess specifically.)
This is a full page in the sense of "this route owns the whole viewport," not in the sense
of Frappe's `www_template`/portal static-page mechanism (checked: that mechanism is built
for third-party provider apps to ship a server-rendered page under their own app's `www/`
directory outside the React SPA entirely — real, but heavyweight infrastructure for a v0
POC page that's explicitly meant to stay small; using it here would be scope creep against
the brief's own framing). `delivery: "spa-deep-link"` on the HUF App record stays correct
either way — it's still a route inside the SPA, just one that opts out of the shared shell.

## 5. Agent prompt shape

System instructions (short, per the original proposal, unchanged):
> You are the chess opponent in the HUF Chess app. Play to win. You will receive the
> current board position, game history, and the complete set of legal moves. Choose
> exactly one move from the supplied legal move list. Never invent a move. Return only
> the requested JSON. Keep commentary to one short sentence and do not reveal internal
> reasoning.

Per-turn prompt (built client-side, sent as the `prompt` argument):
```
You are playing {color}.
FEN: {fen}
Moves so far: {SAN move list, e.g. "1. e4 e5 2. Nf3 Nc6"}
Legal moves: {JSON array of legal SAN moves}

Return only:
{"move": "<one exact move from legal_moves>", "comment": "<optional short comment>"}
```

`response_format: {type: "json_object"}` is genuinely plumbed through to the underlying
provider call (confirmed in `litellm.py`) — this is real JSON-mode, not a hopeful prompt
instruction alone.

## 6. Agent + HUF App seeding (`huf/ai/chess/seed.py`)

`create_chess_agent()`:
- Mirrors the *shape* of the existing "model may not be configured yet" guard pattern
  (`_agent_is_configured`/`MODEL_NOT_CONFIGURED_MESSAGE` in meeting_transcription.py —
  confirmed trivially small: a 3-line function and a 2-line string constant, so
  reimplementing fresh costs nothing), reimplemented independently (no import) — write a
  small `_chess_model()` helper (~12 lines) in the exact shape of the existing
  `_meeting_summary_model()` precedent (install.py:589): check
  `frappe.db.exists("AI Provider", "Google")`, `frappe.get_all("AI Model", filters=
  {"provider": "Google"})`, prefer from a small preferred-models list, else fall back to
  the first available model. (`create_demo_ai_models()` only *seeds* models — it is not
  itself a lookup, and is not called by this helper.) If no model resolves, insert the
  Agent `disabled=1` with `ignore_mandatory=True` rather than fail the install.
- `agent_modality: "Text"` (reqd=1, default `"Both"` — being explicit avoids relying on
  the default), `prompt_mode: "Local"`, `instructions`: the system prompt from §5,
  `run_immediately: 1`, `persist_conversation: 0` (Agent doctype field, default `1` —
  must be set explicitly here since it's not something `run_agent_sync`'s caller controls,
  see §3).
- No tools attached (JSON-mode and tool-calling are known to conflict/degrade together on
  some providers — keep this agent tool-free, confirmed via `litellm.py`).

`create_chess_app()`:
- `app_id: "chess"`, `title: "Chess"`, `route: "/huf/chess"` (the HUF App doctype's route
  field — distinct from the React Router path, see below). No `icon` set: the field is
  free-text and only renders if the value starts with `/` (a real asset path) — anything
  else falls back to a generic `AppWindow` icon in the Apps launcher (`AppsPage.tsx`).
  Meeting Recorder's own `icon: "mic"` already falls into this same fallback today, so
  leaving chess's icon unset is consistent with existing behavior, not a gap — a real
  asset can be added later without a design decision blocking this spec. `category: "Play"`,
  `delivery: "spa-deep-link"` (`"spa"` alone is not a valid option — confirmed against the
  doctype), `sync_status: "Active"` (no default — must be set explicitly), `source_app:
  "huf"`, `is_public: 0` (**required**, not optional: Guest role has no `Agent Run` create
  permission, so a public/guest-facing chess page would authenticate through the app
  shell and then hard-fail creating the run the moment a guest tries to move — confirmed
  against `agent_run.json`'s permission table), `agent: "HUF Chess Player"`, `enabled: 1`.
- Same idempotent get-or-create/update pattern as Meeting Recorder's seed function, called
  from both `after_install` and `after_migrate`, in that order relative to model seeding
  (model seed → agent seed → app seed, matching the existing insertion points).

React Router path is `/chess` (no `/huf` prefix — that prefix is the SPA's own
`basename`, already applied globally; the HUF App doctype's `route` field is a separate,
absolute-from-site-root value used for the Apps launcher tile, not the in-SPA path).

## 7. Game outcome states

Not a single `status: 'playing' | 'checkmate' | 'draw' | ...` string — chess.js exposes
five distinct terminal predicates and collapsing them loses information a player would
expect to see (e.g. "draw by repetition" vs. "draw, insufficient material" read very
differently). State shape:

```ts
type GameOutcome =
  | { kind: 'playing' }
  | { kind: 'checkmate'; winner: 'white' | 'black' }
  | { kind: 'stalemate' }
  | { kind: 'draw'; reason: 'insufficient-material' | 'threefold-repetition' | 'fifty-move' | 'other' }
  | { kind: 'resigned'; by: 'player' };
```
Derived after every move from `chess.isCheckmate()`, `.isStalemate()`,
`.isInsufficientMaterial()`, `.isThreefoldRepetition()`, `.isDraw()` (fifty-move/other
catch-all), in that priority order.

## 8. Error handling

- **No model configured, or an insufficiently-permissioned role**: detect before the
  first move (mirror the existing "Model Not Configured" UX pattern conceptually —
  reimplemented independently, not imported), show a clear message with a link to
  configure a model, don't let the user start a game that will fail on move one. Confirmed
  role calibration: **Huf User** (the typical logged-in role) has `Agent Run`/`Agent
  Conversation`/`Agent Message` create permission and works out of the box; **Huf
  Viewer** does not (`create=0` on all three) and will hard-fail creating the run on the
  first move — the same guard screen should also cover this role, not just the
  no-model-configured case, since both produce the same "can't actually play" outcome.
- **Agent returns an illegal move**: one repair request (§3), then a readable inline error
  ("The opponent's move couldn't be validated — try again or resign") if that also fails.
  Board state is never silently corrupted.
- **Rate limit (`run_agent_sync`'s shared 20/min-per-IP decorator)**: not designed around
  specially — falls through the existing generic `handleFrappeError` toast path like any
  other request failure. This is a shared, global constraint on `run_agent_sync` itself
  (raising it would affect every agent using that function, not just chess) — out of scope
  to touch here; a genuine production need can revisit it later as its own change.
- **Network/transient failure**: standard `handleFrappeError` + toast, matching every
  other service file in this codebase.

## 9. UI — canonical v2.0 "Instrument / Control-Room" design system

This repo's canonical spec is `DESIGN.md` (v2.0). A separate `docs/design-system-v3-apple-quiet-review.md`
proposal (colored pill badges, rounded corners, Apple-system aesthetic) exists but is
explicitly marked review-only, not merged — and is *not* what this app should follow, even
though some recently-added Meeting components drifted toward v3-style pill badges. Chess
is a clean opportunity to build strictly to the canonical v2.0 spec.

- **Layout**: standalone full-viewport page (§4). Own minimal top bar (Big Shoulders
  ~20px title "Chess" — the one sanctioned work-surface exception to "no display type in
  the topbar" per DESIGN.md §6.2/§6.9 — plus a "New game" button and a back link), board
  centered/left, a right-rail panel for status/moves/comment.
- **Board**: no custom skin beyond square coloring in `--paper`/`--paper-deep` tones if
  react-chessboard's theming allows it cheaply; otherwise its sane default is acceptable
  for v0 — this is not a place to over-invest.
- **Agent status**: dot + IBM Plex Sans mono label, per DESIGN.md §7's status vocabulary —
  **not** a colored pill badge:
  - `--steel-soft` static dot — "Waiting for your move"
  - `--signal` **blinking** dot — "Thinking…" (the same blink keyframe already defined:
    `1.6s steps(2) infinite`, respects `prefers-reduced-motion`)
  - `--good` static dot — "Your move" (agent replied successfully)
  - `--signal-ink` text (no dot) — a transient error/illegal-move-repair state (distinct
    from the dot states above — see §7's note on this not being a `GameOutcome` variant),
    matching the `HELD` convention's "colored mono text, never a pill" treatment.
  Label typeface: IBM Plex Mono (data/status label register), not Sans.
- **Move list**: IBM Plex Mono, exactly the register DESIGN.md reserves mono for
  (notation/data), in a bordered panel (`--panel`, 1px `--line`) matching the Ledger Rows
  component shape (§6.6) — SAN pairs, not raw chess.js output.
- **Agent comment**: IBM Plex Sans, `--steel`, quoted, below the move list — this is prose,
  so it does not get mono treatment even though it's agent-authored.
- **Checkmate/resignation state**: the winning/terminal message may use `--signal-ink` for
  the emphasized word (matching the "flag state" convention), 2px radius throughout, no
  shadows, no gradients, no colored icon-in-square containers.
- **Promotion picker**: a Radix `Dialog` (existing primitive, not a new one) showing the
  four promotable pieces as plain outline-icon buttons in a row — hairline-bordered, 2px
  radius, no colored backgrounds, consistent with §9 of DESIGN.md's icon rules (outline
  only, `--steel` → `--ink` on hover, never filled/colored except the status dot).

## 10. Dependencies

- `chess.js@^1.4.0` (current; `move()` throws on illegal input — confirmed, not a
  null/false return, design accounts for this in §3).
- `react-chessboard@^4.7.3` — **not** v5 (v5's peer dependency is `react: ^19.0.0`; this
  repo is `react: ^18.3.1`; v5 also swapped `react-dnd` for `@dnd-kit/core` and changed
  the component API to an options-object shape incompatible with v4's positional-props
  API this design relies on).

## 11. Testing

- Unit: `useChessGame`'s move-application, outcome-derivation (§7), and localStorage
  round-trip logic — pure functions/hook, testable via the existing vitest setup without a
  live agent.
- Unit: `chessApi`'s response-parsing (success/`structured`-present, success/fallback-text
  match, failure/repair-triggered, failure/repair-also-fails) — mock `call.post`.
- Manual/live: full game playthrough against a real configured agent on an isolated bench
  site (same discipline as the meeting-app work in this session — never live-test against
  the shared `huf.localhost` site from a divergent branch).

## 12. Open items for implementation-time judgment (not blocking spec approval)

- Whether react-chessboard v4's theming API makes matching `--paper`/`--paper-deep` square
  colors cheap enough to bother with, or whether the default board skin ships as-is for v0.
- chess.js 1.4 exposes `isDrawByFiftyMoves()` directly — §7's derivation can use it
  precisely instead of folding fifty-move into the generic `isDraw()` catch-all; a minor
  precision improvement to make at implementation time, not a spec-level decision.

(Icon choice resolved in §6 — no custom icon for v0, matching Meeting Recorder's actual
current behavior.)
