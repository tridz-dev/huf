# Plan 006: Render SVG artifacts inside a sandboxed iframe to prevent stored XSS

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat abdd987..HEAD -- frontend/src/components/chat/ArtifactRenderer.tsx`
> If that file changed since this plan was written, compare the "Current state"
> excerpt against the live code before proceeding; on a mismatch, treat it as a
> STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `abdd987`, 2026-06-13

## Why this matters

`ArtifactRenderer.tsx` renders `svg`-type artifacts with `dangerouslySetInnerHTML={{ __html: artifact.content }}` directly into the main app DOM (`frontend/src/components/chat/ArtifactRenderer.tsx:196`). `artifact.content` is parsed from the AI message body (`<artifact>` tags, via `utils/artifactParser.ts`) — it is fully model-controlled and influenceable by prompt injection, a poisoned RAG/knowledge source, or another user's message. SVG can carry `<script>` and event handlers (e.g. `onload`); injected inline it executes in the `/huf` origin with the viewing user's authenticated Frappe session and CSRF token, enabling actions against the backend as that user (stored XSS).

The reach is cross-user: `PreviewViewPage.tsx:76` fetches an arbitrary `Agent Message` by id (`db.getDoc('Agent Message', messageId)`) and renders its artifacts at `/huf/view/:messageId`, so a malicious SVG authored in one context can render in another viewer's session.

The same file already renders untrusted `html` artifacts safely inside a sandboxed `<iframe>` (`:175-180`). This plan applies that proven pattern to the `svg` case with a stricter sandbox (scripts disabled), removing the `dangerouslySetInnerHTML` sink. No new dependency is needed (the repo has no DOMPurify, and adding one is unnecessary for this fix).

## Current state

File: `frontend/src/components/chat/ArtifactRenderer.tsx`.

Verified excerpt — the vulnerable `svg` case, `frontend/src/components/chat/ArtifactRenderer.tsx:190-205`:

```tsx
			case 'svg':
				return (
					<div className="flex flex-col gap-2">
						<div
							className="flex items-center justify-center p-4 bg-white rounded border"
							// biome-ignore lint/security/noDangerouslySetInnerHtml: SVG rendering requires innerHTML
							dangerouslySetInnerHTML={{ __html: artifact.content }}
						/>
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="xml" />
						</details>
					</div>
				);
```

Verified excerpt — the existing safe pattern for `html`, same file `:172-188` (the model to follow):

```tsx
			case 'html':
				return (
					<div className="flex flex-col gap-2">
						<iframe
							srcDoc={artifact.content}
							sandbox="allow-scripts"
							className="w-full h-96 border rounded bg-white"
							title={artifact.title || 'HTML Preview'}
						/>
						...
```

Note: the `html` case uses `sandbox="allow-scripts"` (no `allow-same-origin`, so it is an opaque origin and cannot reach the parent session — acceptable). For SVG we do NOT need scripts to run at all, so use the most restrictive `sandbox=""`, which renders the vector graphic but disables any embedded `<script>`/event handlers.

Repo conventions: tab-indented TSX, double quotes for JSX attributes, Tailwind classes via `className`, `cn()` for conditional merging. The file uses `lucide-react` icons and shadcn/ui primitives.

## Commands you will need

| Purpose    | Command            | Expected on success           |
|------------|--------------------|-------------------------------|
| Typecheck  | `yarn typecheck`   | exit 0, no errors             |
| Lint       | `yarn lint`        | exit 0 (no NEW errors)        |

Run both from `frontend/`. There is no frontend unit-test harness in this repo (CLAUDE.md: "No unit tests currently"), so verification is typecheck + lint + the manual check in the Test plan.

## Scope

**In scope** (the only file you should modify):
- `frontend/src/components/chat/ArtifactRenderer.tsx` — replace the `svg` case's `dangerouslySetInnerHTML` with a sandboxed iframe.
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- The `html` artifact case — already sandboxed; leave it.
- `mermaid.tsx` (`:82-83`), `chart.tsx` (`:79`), `code-block.tsx` (`:74`) — these also use `dangerouslySetInnerHTML` but for different content: Mermaid sanitizes its own SVG output, Shiki emits structural highlight markup, chart injects CSS variables. They are lower-risk and a separate review; flag them in your report but do NOT change them here.
- The artifact parser (`utils/artifactParser.ts`) and the `ParsedArtifact` type — no change.
- Adding any new npm dependency (no DOMPurify) — the iframe approach needs none.

## Git workflow

- Branch: `advisor/006-svg-artifact-xss`
- One commit. Message style: conventional commits (`fix:`). Suggested: `fix: sandbox SVG artifacts to prevent stored XSS`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Replace the `svg` case with a sandboxed iframe

In `frontend/src/components/chat/ArtifactRenderer.tsx`, replace the `dangerouslySetInnerHTML` `<div>` in the `svg` case (lines 192-197) with an `<iframe>` mirroring the `html` case but with `sandbox=""`. Keep the surrounding `<div className="flex flex-col gap-2">` and the `<details>` "View Source" block unchanged. Target shape:

```tsx
			case 'svg':
				return (
					<div className="flex flex-col gap-2">
						<iframe
							srcDoc={artifact.content}
							sandbox=""
							className="flex w-full h-96 items-center justify-center rounded border bg-white"
							title={artifact.title || 'SVG Preview'}
						/>
						<details className="text-xs">
							<summary className="cursor-pointer text-muted-foreground hover:text-foreground">
								View Source
							</summary>
							<CodeBlock code={artifact.content} language="xml" />
						</details>
					</div>
				);
```

The `// biome-ignore lint/security/noDangerouslySetInnerHtml` comment is removed along with the `dangerouslySetInnerHTML` it suppressed. `sandbox=""` (empty string) is intentional and maximally restrictive — it renders the SVG image but blocks scripts, same-origin access, forms, and popups.

**Verify**: `grep -n "dangerouslySetInnerHTML" frontend/src/components/chat/ArtifactRenderer.tsx` → no matches.
**Verify**: `grep -n 'sandbox=""' frontend/src/components/chat/ArtifactRenderer.tsx` → 1 match (the svg case).

### Step 2: Typecheck and lint

**Verify**: from `frontend/`, `yarn typecheck` → exit 0, no errors.
**Verify**: from `frontend/`, `yarn lint` → exit 0, or no NEW errors introduced by this change (compare against a pre-change run if the baseline already has lint warnings; this change should not add any).

## Test plan

There is no frontend unit-test runner in this repo. Verification is:

1. `yarn typecheck` and `yarn lint` pass (Step 2).
2. Manual confirmation (for the reviewer or executor with a running dev server, `yarn dev`): render an SVG artifact whose content contains an inline `<script>` that would, if executed, call `alert(...)` or write to the DOM. With the fix, the vector graphic renders inside the iframe and the script does NOT execute (no alert, no DOM write to the parent). Before the fix, it would execute. Do NOT commit any such test artifact; this is a manual sanity check only.
3. Confirm a normal (script-free) SVG still renders visually inside the iframe.

If you cannot run a dev server, state that the manual check was not performed and rely on the code-shape verification (no `dangerouslySetInnerHTML`, iframe with `sandbox=""`).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "dangerouslySetInnerHTML" frontend/src/components/chat/ArtifactRenderer.tsx` → no matches
- [ ] `grep -n 'sandbox=""' frontend/src/components/chat/ArtifactRenderer.tsx` → 1 match
- [ ] `grep -n "srcDoc={artifact.content}" frontend/src/components/chat/ArtifactRenderer.tsx` → 2 matches (html + svg)
- [ ] `yarn typecheck` (from `frontend/`) → exit 0
- [ ] `yarn lint` (from `frontend/`) → no new errors
- [ ] `git status --porcelain` shows ONLY `frontend/src/components/chat/ArtifactRenderer.tsx` (+ README) modified
- [ ] `plans/README.md` status row for 006 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `ArtifactRenderer.tsx` changed since `abdd987` and the `svg` case no longer matches the "Current state" excerpt (e.g. it already uses an iframe or a sanitizer).
- `yarn typecheck` fails for a reason related to the iframe change (e.g. an iframe prop type error) that you cannot resolve in one attempt.
- You discover the `svg` artifact content is NOT model/user-controlled after all (e.g. it is server-generated from a fixed template) — then the XSS premise is weaker; report so the priority can be reconsidered. (Per the audit it is parsed from the AI message body, so this is unlikely.)

## Maintenance notes

- The other `dangerouslySetInnerHTML` sinks (`mermaid.tsx`, `chart.tsx`, `code-block.tsx`) were judged lower-risk and left out of scope. A follow-up review should confirm: Mermaid is on a current version whose output sanitization is trusted; Shiki output is structural; chart.tsx only injects CSS, not arbitrary HTML. If any renders raw model content, give it the same iframe/sanitize treatment.
- If product later needs interactive SVG (animations via SMIL are fine under `sandbox=""`; scripted SVG is not), do NOT loosen the sandbox to `allow-scripts` without re-evaluating — scripted SVG in an opaque-origin iframe still cannot reach the parent session, but weigh it explicitly.
- Reviewer should scrutinize: the SVG renders visually inside the iframe (height/width classes give it a visible box), and no `dangerouslySetInnerHTML` remains in this file. Cross-check the `/huf/view/:messageId` preview route renders the same component so the fix covers that surface too.
