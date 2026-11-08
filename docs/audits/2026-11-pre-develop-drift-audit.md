# Huf `pre-develop`: structural drift audit and lint-guard review

Audited commit: `a42c021d` (pre-develop, 2026-11-03). Sibling repo checked for cross-repo contracts: `huf_desktop` (`main` = `75aecf6`, 2026-10-30).
Method: static analysis only (AST import graph, dotted-path resolution, string-reference search, orphan scans, running the repo's own `scripts/run_standards.py`). Nothing in either repo was modified. No bench, no runtime, no test run, ESLint not run (no `node_modules`).
A second reviewer spot-checked seven claims; corrections are folded in (see "Review log").

## 1. Baseline

- History: 1,426 commits, 2026-08-04 to 2026-11-03. No long-lived baseline.
- Established convention (strongest signal): the 2026-10-22 consolidation moved flat `huf/ai/*` modules into feature packages (`agent_chat` -> `agent/chat`, `tool_*` -> `tools/`, `desktop_*` -> `desktop/`, `flow_*` -> `flow/`), co-located tests, and shipped `patches/v1/rewrite_moved_module_paths.py` for stored dotted paths.
- Frappe version: not verifiable (`pyproject.toml`: `frappe>=15.0.0`, comments mention v16 / Python 3.14).
- Frontend: React 18.3, Vite 5, React Router 7, base `/huf`. Build output `huf/public/frontend` is gitignored on purpose (`.gitignore:10`).
- Existing guardrails (missed in the first pass): a decrease-only "Standards" framework in `scripts/` (file-size, api-calls, ui-drift, whitelist, ui-parity), `check_repo_layout.py`, `check_explicit_commits.py`; ruff, ESLint, `tsc` strict + `noUnused*`; pre-commit and CI (`standards.yml` on PRs and pushes to develop/pre-develop).

## 2. Architecture map

```
huf/                         Frappe app, one module "Huf" (modules.txt)
  hooks.py (498)             125 dotted paths checked: all resolve
  install.py                 after_install / after_migrate
  patches.txt, patches/v1    33 patches, all resolve
  huf/doctype/               146 DocTypes, all with controllers, all module "Huf"
  api/v1/                    public developer API (separate from whitelisted methods)
  www/                       SPA shell (huf.py), tg_*, MCP OAuth callback
  public/                    css, js widgets, assets; frontend/ = build output
  testing/                   shared test helpers
  ai/                        ~1,000 non-test .py, ~540 whitelisted functions
    agent/ flow/ graph/ automation/ procedure/ decision/ orchestration/   engines
    tools/ providers/ knowledge/ artifacts/ skills/ meetings/ voice/      capabilities
    gateway_service.py gateway_core/ gateways/ gateway_adapters/          gateway stack
    whatsapp/ channels/ telegram_*.py (16 flat)                           channel stack
    desktop/                                                              host side of Electron client
frontend/src                 Vite SPA
  App.tsx (1,048)  pages (104)  components (945 files)  services (120)  lib (214)  hooks  contexts  types  utils
```

Frontend -> backend: components -> `services/*Api.ts` -> `/api/method/huf.ai.<module>.<fn>` (via `lib/api.ts` or `lib/frappe-sdk`); SSE at `/huf/stream`. `huf_desktop` is a second client of the same `huf.ai.*` methods.

## 3. Overall assessment

Coherent: Frappe wiring (all hooks/patches resolve, every DocType has a controller), one module-level import cycle in the whole backend, shared `graph` layer under `flow` and procedures, a careful 10-22 consolidation with a migration patch, only 14 of 540 whitelisted functions with no name reference anywhere.

Drift is concentrated in: the cross-repo API contract, overlapping workflow runtimes, channel code (Telegram/WhatsApp), the frontend Flow feature spread over five roots, two competing frontend API clients, and stale docs/tooling.

## 4. Findings (final)

| # | Sev | Conf | Category | Evidence | Impact | Action |
|---|---|---|---|---|---|---|
| 1 | High | Confirmed | Public interface / persisted refs | `huf_desktop` (main) calls removed paths: `huf.ai.agent_chat.*` (`hufChatApi.ts:477,505,575,591,612,644,651,671`, `useHufChat.ts:167`, also `streamChatApi.ts`, `protocol.ts`), `agent_integration.get_agent_run_status` (`hufChatApi.ts:533`), `automation_api` (`capabilities.ts:67`), `desktop_executor` (`huf-client.ts:40`), `desktop_outputs` (`huf-client.ts:43`, `catalogApi.ts:57`), `desktop_import` (`publisher.ts:97`). Targets now live at `huf/ai/agent/chat.py`, `huf/ai/automation/api.py`, `huf/ai/desktop/*`. No alias or shim in huf (`huf/ai/__init__.py` empty; `override_whitelisted_methods` unrelated). `desktop_import` has no successor anywhere under `huf/ai/desktop/` (missing endpoint, not a move). | Desktop chat, run status, automations, tool execution and sync fail with method-not-found against this server. | Choose a stable public surface: alias old paths for a defined window, or update the client in the same release. Restore or retire `desktop_import`. Document which `huf.ai.*` methods other repos may call. |
| 2 | Medium | Confirmed | Old/new coexisting | Legacy `Agent Trigger` and new `Automation` both registered (`hooks.py:254-268` doc events, `:315` cache-clear for Agent Trigger, `:347` legacy scheduler). Gated by site-config `automation_trigger_runtime`, default `"new"` (`automation/runtime_flag.py`, 17 call sites), so legacy is inert by default. `docs/DEPRECATIONS.md` lists only `run_scheduled_agents`. | Double registration and maintenance; no removal gate. | Write removal criteria (flag default, date, delete Agent Trigger + 5 frontend files). Under the project's pre-release no-compat rule this is cleanup. |
| 3 | Medium | Confirmed (wired) / Hypothesis (intent) | Overlapping engines | `ai/orchestration/` (420 loc, "AgentFlo" header) still wired: `hooks.py:370` cron every minute, `agent/integration.py:2094`, `doctype/agent/agent.py:16-17`. Beside `flow/` (12k), `graph/` (7.7k), `procedure/`, `automation/`, `decision/`. One ADR in `docs/adr`. | Five orchestration concepts, no document relating them. | Runtime-check whether Agent Orchestration rows are still produced; then document or deprecate. |
| 4 | Medium | Confirmed | Directory drift | Telegram is ~21k non-test lines (all non-test `.py` with "telegram" in path): 16 flat `huf/ai/telegram_*.py` (~7.1k), 47 files in `gateway_adapters/` (~11.0k), plus `tools/`, `flow/gateways`, 4 DocType controllers. WhatsApp ~25k across `whatsapp/`, `gateway_adapters/whatsapp*`, `channels/`, `tools/whatsapp*`, `gateway_core`. `whatsapp` and `gateway_adapters` import each other (9 / 20 module-level imports); the only module-level cycle is in `gateway_adapters` WhatsApp. | Finding one channel's code needs grep; the flat Telegram files are what the 10-22 consolidation did not reach. | Move Telegram into one package (precedent: 10-22). First break the WhatsApp cycle; don't restructure WhatsApp yet. |
| 5 | Medium | Confirmed | Frontend ownership | Flow feature spread across `components/flow` (170 files), `lib/flow*` (11 dirs, ~170), `services/flow` (16), `hooks/flow` (12), `components/nodes`, root `components/Flow*.tsx`. CLAUDE.md describes `lib/` as SDK wrapper, error handling, `cn()`; it has 214 files. | Feature code in a shared layer; names don't line up (`flow-canvas` vs `flow/canvas`). | Put new Flow code in one place; migrate gradually. |
| 6 | Medium | Confirmed | Two API-client conventions | `scripts/check_api_calls.py` states "all backend calls go through `frontend/src/lib/api.ts`" (9 importers). CLAUDE.md and 85 service files use `lib/frappe-sdk`. 21 non-service files import `frappe-sdk` directly (10 components, 7 pages, hook, context). The guard does not count SDK imports. | Agents get contradictory instructions; one convention is enforced, the other documented. | Decide the target client, update CLAUDE.md and the guard together. |
| 7 | Medium | Confirmed | Build/tooling | Root `package.json` postinstall: `cd frontend && yarn install && yarn build` (bench path). CI runs `npm ci` with `frontend/package-lock.json` (four workflows; `server-tests.yml:82-83` mentions a stale yarn.lock). `.gitignore:8` has `**/yarn.lock`; only a root `yarn.lock` is tracked. | Bench builds unlocked; CI tests another resolution. | Pick one package manager and lockfile. |
| 8 | Medium | Confirmed | Guard state | `python3 scripts/run_standards.py` on pre-develop HEAD fails: `huf/ai/app_seeding/apps_loader.py` 1,060 lines, baseline 987 (grew in `e492bedc`, 2026-11-03). Other four guards pass. | The ratchet is red on the integration branch. Cause not determined (was the Standards workflow required/run on that PR?). | Split the file or re-baseline with owner approval; make the check required. |
| 9 | Low-Med | Confirmed | Stale baseline | CLAUDE.md: 47 DocTypes (actual 146), 18 pages (104 files), ~150 components (945), 54 ui (70), 11 services (120 files); still documents `mockApi`. Names: `package.json` name `vite-react-typescript-starter`, description "Messaging Application", README "HufAI Platform", "AgentFlo" in headers. | Agents calibrate on a wrong picture. | Remove counts or generate them. |
| 10 | Low | Confirmed (static) | Frontend orphans | 53 files with no importer (aliases, relative, `import()` resolved). Real: `services/mockApi.ts`, `components/agent/TriggerFieldsRenderer.tsx` + `TriggerDocEventExtras.tsx` (stale copies; `TriggerEditor.tsx` imports the `automation/` versions), `chat/ChatAgentPicker`, `chat/ChatListBase`, `pages/SettingsPage.tsx`, `integrations/TelegramTab.tsx`, `FlowNode.tsx`, `JsonSchemaForm.tsx`. 25 of 35 `ai-elements` and several `ui/` files unused (vendored library code; leave). | Edits land on dead or duplicate copies. | Delete the duplicates and `mockApi` first. |
| 11 | Low / verify | Confirmed (static) | Python providers | `providers/{anthropic,google,openai,openrouter}.py` are imported only from tests, but `run.py:94-95` builds `huf.ai.providers.<name>` and loads it via `frappe.get_module` as a fallback after the LiteLLM path. | Reachable at runtime, rarely. | Establish when the branch can be hit, then remove or mark legacy. |
| 12 | Low | Confirmed | Hygiene | `public/design-v3-preview.html`, `css/huf-tokens-v3.css` unreferenced; 284 test files remain in flat `ai/tests/` despite co-location convention; `tools/registry.py` (620) beside `tools/_registry.py` (2,842). | Mild confusion. | Inspect the registry pair before judging. |
| 13 | Info | Confirmed | Endpoint usage | 540 whitelisted functions; only 14 have no name reference in huf, tests, docs or `huf_desktop`: `agent.chat.list_orphaned_messages`, five `app_seeding.exporter.export_*`, six `prompt_api` template functions, one `www`, one `huf_data_table`. | Probably small removable surface; exporters may be CLI-run. | Verify per function before removal. Note `document_api` / `document_comment_api` have no in-repo caller but are used by `huf_desktop`. |

Not defects: single Frappe module "Huf" for 146 DocTypes; large files alone (`integration.py` 4.9k, `AgentFormPage.tsx` 2.6k).

## 5. Proposed target structure

| Current | Proposed | Affected |
|---|---|---|
| `huf/ai/telegram_*.py` (16 flat) | `huf/ai/telegram/` | Python imports; `hooks.py` (`telegram_admin.send_daily_digests`); frontend `telegram*Api.ts` call strings; desktop calls; extend `rewrite_moved_module_paths` |
| `lib/flow-*/`, root `components/Flow*.tsx` | under `components/flow/` (or one `features/flow/`) for new work | `@/lib/flow-*` imports only |
| `components/agent/Trigger*.tsx` duplicates | delete | none |
| `providers/{anthropic,google,openai,openrouter}.py` | delete or `providers/legacy/` after finding 11 | tests |
| `ai/tests/*` | beside owning package | test paths, fixture imports |

Do not split the "Huf" module (DocType metadata and controller paths would change). Persisted references to protect: `Agent Tool Function.function_path`, `HUF App.permission_method`, `Scheduled Job Type.method`. Public interfaces: `huf.ai.*` methods used by `huf_desktop`, `/huf/api/v1`.

## 6. Cleanup plan

Straightforward: delete duplicates and `mockApi` (10); refresh CLAUDE.md (9); remove unused public assets (12); fix or re-baseline `apps_loader.py` (8); pick one package manager (7).
Needs compatibility or design decisions, in order: desktop contract (1); Agent Trigger removal gate (2) and orchestration decision (3); one API client (6); Telegram package and WhatsApp cycle (4); Flow reorganisation (5); provider fallback (11).

## 7. Lint and guard review

### What exists
- Ruff: rules F, E, W, I, UP, B, RUF, BLE, S, TRY; ignores include F401 (unused imports), E402, E501.
- ESLint: `js` + `typescript-eslint` recommended + react-hooks + react-refresh. No import-boundary rules.
- `tsc`: strict, `noUnusedLocals`, `noUnusedParameters`.
- Standards framework (`scripts/run_standards.py`, decrease-only baselines in `scripts/baselines/`): file-size (500-line new-file cap, folder cap of 15, no growth), api-calls (raw `/api/method` URLs, `fetch(`, ad-hoc helpers outside `lib/api.ts`/`services/`), ui-drift, whitelist (guest/permission/mutating-GET heuristics), ui-parity. Runs on every PR and push to develop/pre-develop; whole run is about 10 s.
- Today: 4 of 5 guards pass; file-size fails (finding 8).

### Gaps measured
| Gap | Current size | Why existing rules miss it |
|---|---|---|
| `frappe-sdk` imported outside `services/` | 21 files | api-calls counts URLs/fetch, not SDK imports; ESLint has no restriction |
| New flat modules directly in `huf/ai/` | 82 files | file-size caps folder growth only above 15 files and is baselined; nothing says "use a package" |
| Moved/removed dotted path still referenced | 0 in huf (hooks/patches clean), 21 call sites in `huf_desktop` | no resolver runs; cross-repo not covered |
| Module-level import cycles / cross-package coupling | 1 cycle; whatsapp <-> gateway_adapters | no import-graph check |
| Unreferenced frontend files | 53 | `noUnused*` is per file; no cross-file reachability |
| Unused Python imports | 255 (248 auto-fixable), F401 ignored | rule disabled; some may be intentional re-exports or patch targets |
| Lockfile / package-manager split | 1 | none |
| Stale numbers in docs | 5+ claims | not lintable; remove the numbers |

### Recommendations (in the existing framework, each with a decrease-only baseline, per `scripts/README.md` "Adding a guard")
1. **`sdk-imports`** (extend `check_api_calls.py` or add `check_sdk_imports.py`): count `frappe-sdk` imports outside `services/`, `lib/`, `contexts/UserContext`; baseline 21. Alternative: ESLint `no-restricted-imports` with `overrides` for allowed folders (needs ESLint run to baseline; I could not run it).
2. **`ai-layout`**: fail if the count of `.py` files directly in `huf/ai/` rises above 82, and if any new `telegram_*.py` appears there. Cheap, directly encodes the 10-22 convention.
3. **`dotted-paths`**: resolve every dotted path in `hooks.py` and `patches.txt` (zero failures today, so zero baseline) and every `huf.*` method string in `frontend/src`. Add an optional CI job that checks out `huf_desktop` and resolves its `/api/method/huf.*` strings; this is the only check that would have caught finding 1. Needs a cross-repo checkout and an agreed set of public methods, and prefix-plus-method concatenations (common in the frontend) will need a pattern allowance, so expect some false negatives.
4. **`import-cycles`**: AST scan for module-level cycles and for package pairs importing each other at module level; baseline 1 cycle and the whatsapp/gateway_adapters pair. `import-linter` is an alternative but is not installed and not in the repo; the AST script is small and matches the existing guard style.
5. **`orphan-files` (frontend)**: reachability from `main.tsx`, aliases and `import()`; baseline 53, ratchet down. Exempt `components/ui/**` and `ai-elements/**` (vendored). A Python equivalent is not recommended as a gate: DocType controllers, `www`, string-loaded modules and `import x as y` produce false positives (my first scan flagged 147, most spurious), so keep it as an advisory report.
6. **Ruff F401**: enable with a per-file baseline rather than globally; review re-exports and patch targets before auto-fixing.
7. **`lockfiles`**: fail when `frontend/package.json` dependencies change without `package-lock.json`, and when both yarn and npm lockfiles are tracked for the same package.
8. **Process, not lint**: make "Standards" a required check on `pre-develop`; finding 8 shows a baselined breach landed on the integration branch.

### Limits of linting here
- Guards cannot decide semantic overlap (findings 2, 3, 5), which need a documented decision (ADR + DEPRECATIONS entry).
- Ratchets freeze existing debt; they reduce growth, not the debt. Baselines need owner approval to raise, as the README already requires.
- Static checks miss Frappe dynamic discovery and string-built paths; every resolver above needs allowlists for those, and they should fail closed only where the baseline is zero (hooks/patches).
- Cross-repo checks depend on a second checkout and a defined public API list.
- Not verified: ESLint behaviour on the real tree, the exact ruff F401 split between real and intentional imports, and whether Standards was required on the PR that broke the file-size baseline.

## 8. Repository guardrails for future agents

1. New backend features go in `huf/ai/<feature>/` with tests inside; no new flat `huf/ai/*.py`.
2. After moving or renaming a module, update `hooks.py`, `patches.txt` and the rewrite patch mapping, and check `huf_desktop` call strings.
3. Every deprecation gets a `docs/DEPRECATIONS.md` entry with a removal condition.
4. Frontend backend calls live in `services/` through the single chosen client; no SDK imports or raw doctype strings elsewhere.
5. New frontend feature code goes under one feature root, not `lib/`.
6. Copying a component or module requires deleting or redirecting the old one in the same change.
7. Keep counts out of CLAUDE.md or generate them; use one package manager.
8. Run `python3 scripts/run_standards.py` before pushing; never raise a baseline without owner approval.

## 9. Review log (second-pass corrections)

- Finding 1 widened: `main` of `huf_desktop` equals the audited commit; extra callers in `useHufChat.ts`, `streamChatApi.ts`, `protocol.ts`; `desktop_import` is missing, not moved.
- Finding 2 downgraded High -> Medium (legacy path inert by default; `Agent Trigger` entry at `hooks.py:315` only clears caches).
- Finding 11 downgraded: dynamic dispatch at `run.py:94-95` makes the providers reachable.
- Telegram breakdown corrected (adapters hold 47 Telegram files, not 46 of all; `gateway_adapters` also holds Slack, Discord, Teams, email, SMS and other adapters).
- Added after the review: existing Standards framework, failing file-size guard, and the two-API-client convention (findings 6, 8), found while checking the lint question.

## 10. Coverage and what could not be verified

Covered: repo instructions, hooks, patches, DocTypes, scheduler, import graph, frontend routes/services/lib/components, orphan scans, cross-repo call strings, build and CI configuration, the Standards guards (run once).
Not verified: installed Frappe version, any runtime behaviour (including orchestration use and provider fallback reachability), ESLint output, whether the first-party frontend call strings built by concatenation all resolve, per-function status of the 14 unreferenced endpoints, why the file-size baseline was breached.
