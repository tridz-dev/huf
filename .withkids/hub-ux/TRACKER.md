# withkids tracker — Hub UX wave (sidebar/commands/transitions)

Repo: /Users/safwan/Code/Docker/frappe_docker/development/16/apps/huf
Site: huf.localhost:8000 (container frappe_docker_devcontainer-frappe-1)
Branch: feat/design-simplified-hub-homepage-interface
Predecessor tracker: .withkids/hub-simple/TRACKER.md (done)

## Tasks

| id | task | deps | kid | status | result |
|----|------|------|-----|--------|--------|
| W1-T1 | Sidebar: collapsed avatar centering + Hub/Dashboard nav items | [] | coder | done | nav-user.tsx: group-data-[collapsible=icon] centering; app-sidebar.tsx: "Hub"→/ (Home icon), "Dashboard"→/dashboard (LayoutDashboard); tsc clean |
| W1-T2 | Hub: /cost→/dashboard + back-to-home button | [] | coder | done | routeMap fixed (all 7 commands navigate to real routes); onHome prop + Home button top-left in conversation view; preserves conversationId; tsc clean |
| W1-T3 | Route transitions in AppShell | [] | coder | done | App.tsx: location-keyed AnimatePresence + motion.div fade 150ms mode="wait", h-full wrapper; tsc clean |
| W2-T1 | Shared IconRail + hub hide-sidebar toggle | [W1] | coder | done | NEW IconRail.tsx (48px, bg-sidebar, 32px buttons, nav-main look); HubSimplePage aside replaced; fixed top-left PanelLeft toggle, localStorage 'hub:rail-visible', 200ms width animation; HubRecentChats trigger restyled; tsc + yarn build clean |
| W2-T2 | Integration verify | [all] | parent | done | tsc exit 0; build served (new index hash); Hub chunk has rail logic, 0 violet refs; /api/method/ping OK; dead commandParser.ts deleted (parent) |

## Requirement coverage

1. Command UX consistency — all commands navigate; /cost→/dashboard (real cost view) ✓
2. All advertised commands supported — verified against App.tsx routes ✓; dead commandParser.ts removed ✓
3. Back to hub / new chat — Home button (preserves chat) + existing New chat (clears) + HubRecentChats resume ✓
4. Same collapsed sidebar hub+dashboard — shared IconRail visual language (48px/bg-sidebar/32px buttons), zero layout shift ✓
5. Collapsed account icon off — centered via collapsible=icon scoped classes in nav-user.tsx ✓
6. Hub icon in dashboard sidebar — "Hub"→/ and "Dashboard"→/dashboard items added ✓
7. Hide sidebar canvas mode — fixed top-left toggle, persisted, animated ✓
8. Route transitions — app-wide 150ms fade via AnimatePresence in AppShell ✓

## Notes

- Nothing committed/pushed (needs explicit user confirmation).
- Visual pass recommended at http://huf.localhost:8000/huf (Administrator/admin, hard refresh).
- app-sidebar.tsx not refactored to consume IconRail (one-directional sharing; avoids churn on the shadcn Sidebar machinery).
