# Chat-Only PWA UI Tracker

## Context
- Branch: `feat_pwa`
- Base: local `develop`
- Goal: standalone mobile-first PWA chat experience for Huf React/Vite, served through Frappe.
- Important note: local `develop` diverges from `origin/develop` by 1 local commit and 89 remote commits.

## Decisions
- Keep first version simple: installable PWA, static frontend asset caching only, no cached private API data.
- Use Vite build output under `/assets/huf/frontend/`.
- Serve the app shell through a Frappe `www` route.

## TODO
- [x] Inspect current Huf frontend build, routing, auth/logout, and logo/assets.
- [x] Inspect Frappe route/build integration.
- [x] Add PWA plugin and service worker registration.
- [x] Add or adapt Frappe-served chat shell.
- [x] Add icons/manifest support.
- [x] Verify build and type checks where possible.

## Scratchpad
- Current repo already has `frontend/`, `frontend/vite.config.ts`, root `package.json`, and `huf/www/agent_chat.html`.
- Root `package.json` already delegates build/dev/install to `frontend`.
- `frontend/package.json` already builds with `vite build --base=/assets/huf/frontend/` and copies generated HTML to `huf/www/huf.html`.
- `frontend/vite.config.ts` already outputs to `../huf/public/frontend`.
- `huf/hooks.py` catch-all maps `/huf/<path:app_path>` to `huf`, so `/huf/ui/chat` can use the existing Frappe shell.
- Existing `ChatWindow` uses `useSidebar`, so a standalone chat route needs a `SidebarProvider` or a small adaptation.
- Added `StandaloneChatPage` at React routes `/ui/chat` and `/ui/chat/:chatId`, which resolve under the app basename as `/huf/ui/chat`.
- PWA configured via `vite-plugin-pwa` with API requests forced `NetworkOnly` and static frontend assets `StaleWhileRevalidate`.
- Generated PWA icons in `frontend/public/icons/` from `huf/public/Images/huf.png`.
- `yarn install` completed after network escalation and created `frontend/yarn.lock`.
- `frontend/yarn.lock` is ignored by repo rules (`**/yarn.lock`), so dependency persistence is in `frontend/package.json`.
- `yarn build` in `frontend/` passed as a smoke check and generated `manifest.webmanifest`, `sw.js`, `workbox-*.js`, and copied the shell to `huf/www/huf.html` plus `huf/www/chat.html`.
- Added `huf/www/chat.html` to `.gitignore` because it is generated alongside the already-ignored `huf/www/huf.html` and references hashed assets from ignored `huf/public/frontend`.
- `yarn typecheck` in `frontend/` passed after the final standalone chat adjustment.
- Bench validation was not run because this worktree is not a bench environment.
