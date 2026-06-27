# Chat-Only UI Plan

## Current Frontend Structure Summary

- `frontend/src/App.tsx` defines all React routes under `BrowserRouter basename="/huf"`.
- Most workbench pages are wrapped in `UnifiedLayout`, which mounts `AppSidebar` and an optional header.
- `AppSidebar` contains normal product navigation and filters items through `PermissionsContext` capabilities. The existing Chat nav item points to `/chat`.
- Existing `/chat` and `/chat/:chatId` routes use `UnifiedLayout hideHeader`, so the app sidebar is still present even though the normal header is hidden.
- Auth is centralized in `UserContext`; `ProtectedRoute` only checks logged-in state.
- Logout is exposed through `NavUser`, but that component is sidebar-specific.
- Existing mobile detection uses `useIsMobile`; current chat page has a mobile overlay conversation list.

## Existing Chat UI/API Summary

- `ChatPageV2` renders a conversation/sidebar experience with `ChatListing` and `ChatWindowV2`.
- `ChatWindowV2` renders `ChatWindowHeader` and `ChatMessageList`, and closes the app sidebar through `useSidebar`.
- `ChatMessageList` is the best reuse point: it loads existing messages, handles socket/tool updates, renders markdown/artifacts through `ChatMessage`, shows loading/error states, and renders `ChatInput`.
- `ChatInput` sends via `streamChatApi.sendMessage`; it supports new and existing conversations, streaming fallback, audio transcription, loading state, and conversation-created callbacks.
- `chatApi.ts` handles conversation and message reads plus feedback/title updates.
- `agentApi.getAgentModels` already filters chat-enabled agents with `allow_chat = 1` and `disabled = 0`.

## Exact Files To Change

- `frontend/src/App.tsx` - add lazy route for standalone chat-only UI.
- `frontend/src/pages/ChatOnlyPage.tsx` - new dedicated route page.
- `frontend/src/components/chat-only/ChatOnlyLayout.tsx` - standalone product-like full-height shell.
- `frontend/src/components/chat-only/ChatHeader.tsx` - Huf identity plus user/logout menu.
- `frontend/src/components/chat-only/ChatAgentSelector.tsx` - mobile-friendly chat-agent picker.
- `frontend/src/components/chat/ChatMessageList.tsx` - pass optional new-conversation path into `ChatInput`.
- `frontend/src/components/chat/ChatInput.tsx` - accept optional new-conversation path builder for route reuse.
- `frontend/src/services/agentApi.ts` - add `getChatAgents`.
- `docs/temp/chat_only_ui_tracker.md` - keep implementation tracker current.
- `docs/temp/chat_only_ui_plan.md` - this plan.

## Proposed Route

Use `/ui/chat` and `/ui/chat/:chatId`, which becomes `/huf/ui/chat` in the deployed app because the router basename is `/huf`.

Reason: `/chat` already exists as the workbench chat experience with conversation listing and app layout behavior. `/ui/chat` cleanly matches the user-preferred URL while avoiding disruption to existing routes.

## Component Plan

- `ChatOnlyPage` owns route params, selected agent, available-agent loading, and navigation.
- `ChatOnlyLayout` provides the standalone full-height shell without `UnifiedLayout` or sidebar.
- `ChatHeader` shows a compact Huf brand mark, current agent label when available, and a user menu with logout from `UserContext`.
- `ChatAgentSelector` shows no-agent, one-agent, and multi-agent selection states. One enabled chat agent is auto-selected by the page.
- Reuse `ChatMessageList` for message loading, markdown rendering, sending, typing/loading, and error display.

## Mobile Behavior Plan

- Use `h-[100svh]`/`min-h-0` flex layout so mobile browser chrome does not push the input away.
- Keep header compact and sticky at the top of the standalone shell.
- Let `ChatMessageList` own natural scroll and bottom input behavior.
- Use full-screen width on phones; constrain only on larger screens with a centered chat container.
- Agent selector uses large touch targets and avoids desktop side panels.

## Permission/Access Assumptions

- The chat-only route remains behind `ProtectedRoute` for authenticated users.
- Agents are exposed only if returned by Frappe through `getChatAgents`, filtered to `allow_chat = 1` and `disabled = 0`.
- If permissions hide all agents, the page shows "No chat access available".
- Existing backend permissions remain authoritative for conversation/message reads and sends.

## Implementation Checklist

- [x] Add route for chat-only UI.
- [x] Add standalone chat-only page/layout.
- [x] Reuse existing chat service/hooks where possible.
- [x] Add responsive CSS/Tailwind classes.
- [x] Add logo/logout in header.
- [x] Handle one-agent, multi-agent, and no-agent states.
- [x] Test desktop and mobile viewport.
- [x] Run build/lint/typecheck if available.

## Risks/Unknowns

- `ChatMessageList` currently reads the new-chat agent from the URL search param; `ChatOnlyPage` must keep `?agent=` in sync for new conversations.
- `ChatInput` has one hardcoded `/chat/new` path for model mismatch; this needs a small optional prop to preserve route isolation.
- Backend access may differ by role; local UI can filter only what the current session can list.
- Existing `UserContext` login redirect points back to `/huf`, not `/huf/ui/chat`; changing that globally is out of scope.

## Testing Checklist

- [x] Build passes.
- [ ] Existing app/sidebar routes still render through existing layout.
- [ ] `/huf/ui/chat` renders without sidebar.
- [ ] One chat-enabled agent opens directly.
- [ ] Multiple chat-enabled agents show a mobile-friendly selector.
- [ ] No chat-enabled agents show a clean empty state.
- [ ] Logout remains available.
- [x] Mobile message list scrolls and input remains reachable.

Note: browser viewport testing was skipped per user request after build verification.
