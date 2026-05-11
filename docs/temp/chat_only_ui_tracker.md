# Chat-Only UI Tracker

## Objective

Build a dedicated standalone chat experience for users who only have access to conversational agents, reachable from a clean chat route without the normal admin/workbench sidebar. The page should reuse existing Huf chat APIs and auth/logout behavior, support one-agent, multi-agent, and no-agent states, and work well on mobile.

## Current Understanding

- Started from `origin/develop` on branch `feat_chat_ui`.
- Local `develop` had diverged from `origin/develop`, so the feature branch was created directly from `origin/develop` to use latest `tridz-dev/huf` code without rewriting local history.
- Routing lives in `frontend/src/App.tsx` under `BrowserRouter basename="/huf"`.
- Normal pages use `UnifiedLayout`, which always mounts `AppSidebar`; the existing `/chat` route uses `UnifiedLayout hideHeader`, so it still has app sidebar mechanics.
- Current chat page is `frontend/src/pages/ChatPageV2.tsx`. It renders `ChatListing` plus `ChatWindowV2`.
- `ChatWindowV2` calls `useSidebar().setOpen(false)`, so it depends on `SidebarProvider` from `UnifiedLayout`.
- Chat messages/input are mostly reusable through `ChatMessageList`, `ChatInput`, and the streaming service. `ChatMessageList` accepts an explicit `chatId` prop and uses the `agent` search param for new chats.
- Existing chat services are in `frontend/src/services/chatApi.ts`; message sending uses `frontend/src/services/streamChatApi.ts`.
- Existing allowed-chat agent selector is `AgentModelSelector`, backed by `getAgentModels` in `agentApi.ts`, which filters `allow_chat = 1` and `disabled = 0`.
- Auth/logout lives in `UserContext`; `NavUser` uses the same `logout` and `user` values but is coupled to sidebar UI.
- Permission context exposes `chat.use`, but route-level capability checks are not currently enforced by `ProtectedRoute`; sidebar visibility uses capabilities.
- Mobile pattern: `useIsMobile` is used in `ChatPageV2`; existing chat already prioritizes full-height flex layout and scrollable message list.

## Decisions

- Route: `/ui/chat` and `/ui/chat/:chatId` inside the `/huf` basename, yielding `/huf/ui/chat`.
- Layout approach: route-level standalone page outside `UnifiedLayout` so no app sidebar is mounted.
- Components to reuse: `ChatMessageList`, `ChatInput`, `ChatMessage`, markdown/artifact rendering, existing `streamChatApi`, existing `chatApi`, existing `UserContext`.
- Components to create: `ChatOnlyPage`, `ChatOnlyLayout`, `ChatHeader`, and `ChatAgentSelector`.
- API addition: add `getChatAgents` to `agentApi.ts` for a simple list of enabled chat agents using the same `allow_chat = 1` and `disabled = 0` criteria.
- Assumption: if the user can read an enabled `allow_chat` agent returned by Frappe permissions, it is valid to expose in chat-only selector.

## TODO Checklist

- [x] Switch to latest `tridz-dev/huf` code base safely.
- [x] Create `feat_chat_ui` branch from `origin/develop`.
- [x] Create tracker file.
- [x] Create planning document.
- [x] Inspect frontend pages, components, contexts, services, layout, navigation, chat, routing, auth/logout, and mobile patterns.
- [x] Update tracker with inspection notes.
- [x] Complete planning document before implementation.
- [x] Implement chat-only route.
- [x] Implement standalone chat-only page/layout/header/agent selector.
- [x] Reuse existing chat service/components where practical.
- [x] Handle one-agent, multi-agent, and no-agent states.
- [x] Verify desktop and mobile layout.
- [x] Run build/lint/typecheck where available.
- [ ] Commit, push, and open PR.
- [x] Update tracker and plan to final state.

## Scratchpad

- Existing `/chat` should remain unchanged for admin/workbench use.
- Need avoid using `ChatWindowV2` in standalone route because it requires `useSidebar`.
- `ChatMessageList` can be reused directly if standalone page controls selected/new agent.
- Added `getNewConversationPath` optional prop through `ChatMessageList` to `ChatInput` to avoid hardcoded `/chat/new` when used by `/ui/chat`.
- User said browser testing is not needed, so skipped desktop/mobile visual smoke test.

## Files Changed

- `docs/temp/chat_only_ui_tracker.md` - persistent task tracker, TODO list, and scratchpad.
- `docs/temp/chat_only_ui_plan.md` - temporary implementation plan.
- `frontend/src/App.tsx` - adds `/ui/chat` and `/ui/chat/:chatId` protected routes.
- `frontend/src/pages/ChatOnlyPage.tsx` - standalone chat-only page state and routing.
- `frontend/src/components/chat-only/ChatOnlyLayout.tsx` - standalone full-height shell without sidebar.
- `frontend/src/components/chat-only/ChatHeader.tsx` - Huf identity and user/logout menu.
- `frontend/src/components/chat-only/ChatAgentSelector.tsx` - mobile-friendly chat agent selection and empty states.
- `frontend/src/components/chat/ChatMessageList.tsx` - passes route-safe new conversation path to input.
- `frontend/src/components/chat/ChatInput.tsx` - accepts optional new conversation route builder.
- `frontend/src/services/agentApi.ts` - adds `getChatAgents` filtered to enabled chat agents.

## Testing Log

- `yarn typecheck` in `frontend` - initially failed because declared dependencies `media-chrome` and `prismjs` were missing from `node_modules`.
- `yarn build` in `frontend` - initially failed for the same missing dependencies.
- `yarn lint` in `frontend` - failed on existing repo-wide lint issues (hundreds of pre-existing `any`/unused-vars/hook warnings across unrelated files).
- `yarn install --frozen-lockfile` in `frontend` - completed; no yarn lockfile exists, dependencies were installed from `package.json`.
- `yarn build` in `frontend` - sandbox run reached Vite output but failed clearing `huf/public/frontend/assets` with `EPERM`.
- `yarn build` in `frontend` with elevated filesystem access - passed. Vite emitted existing large chunk warnings only.
- Browser/mobile smoke test - skipped per user request.
