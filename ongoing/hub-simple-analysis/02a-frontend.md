# Hub Simple Frontend Recon — `feat/design-simplified-hub-homepage-interface`

## F1. FILE-BY-FILE READ

### `frontend/src/App.tsx` (current HEAD vs develop)

- **Diff summary**: develop's route scaffold was kept; `/` was switched from `HomePage` inside `UnifiedLayout` to the new `HubSimplePage` without the unified layout. `/dashboard` was added and now hosts the old dashboard (`HomePage` + `HomeHeaderActions`). All develop routes (`/console`, `/models`, `/integrations`, `/mcp`, `/chat`, `/executions`, etc.) are preserved.
- **Relevant lines**: `HubSimplePage` lazy import at line 62; `/` route lines 80-89; `/dashboard` route lines 90-100.
- **Streaming wiring**: App boot calls `checkStreamingAvailable()` once at mount (lines 497-509) and stores the result in the module-level `streamingAvailable` flag exported by `streamChatApi.ts`. If the ping fails, a Sonner toast warns the user. Hub reads this flag at send time to decide SSE vs REST.

### `frontend/src/pages/HubSimplePage.tsx`

- **Purpose**: Chat-first home page. Maintains local chat state, renders a collapsed sidebar, composer, starter prompts, and conditionally swaps to `HubConversationView` once messages exist.
- **State management**:
  - Local `messages`, `inputValue`, `showSlashMenu`, `slashQuery`, `isInputFocused`, `conversationId`, `isStreaming`.
  - `conversationId` is held only in React state (line 86); it is not persisted to the URL or local/session storage.
  - Provider presence is a boolean `hasProvider` initialized to `null` (line 85).
- **Data flow / chat streaming**:
  - On mount: `getProviders({ limit: 1 })` populates `hasProvider` (lines 104-109). Failures silently become `false`.
  - On send: if `hasProvider` is false, it artificially injects an assistant message with content `__NO_PROVIDER__` after a 300 ms timeout (lines 112-117).
  - Otherwise it calls `sendMessage({ agent: 'Hub Orchestrator', message: msg, conversationId }, { useStreaming: streamingAvailable, onDelta: ... })` (lines 131-135).
  - SSE deltas update the optimistic assistant message keyed with `assistant-${Date.now()}` (lines 120-128).
  - Non-streaming fallback receives the final response in one shot (line 141).
  - `conversationId` is extracted from the server response and stored in state for subsequent turns (lines 139-142).
  - Errors in `sendMessage` are swallowed and replaced with the hardcoded text: `"Hub Orchestrator agent is not configured yet. Go to Agents to set one up."` (lines 143-144).
- **Slash commands**: A simple `useEffect` detects the last `/` and opens the menu if no space follows (lines 89-101). Selection can either replace the command in the composer or navigate if the slash was at position 0 (lines 166-180).
- **Key refs**: role mapping lines 71-73; route map lines 167-170; `__NO_PROVIDER__` sentinel line 114; hardcoded agent name line 133.

### `frontend/src/components/hub/SlashCommandMenu.tsx`

- **Purpose**: Floating palette of `/` commands.
- **State**: `selectedIndex`, `itemRefs`.
- **Data flow**: Filters the static `COMMANDS` array by `id` or `label` match (lines 32-34). Resets selection to 0 when the query changes.
- **Keyboard**: global `window.addEventListener('keydown', ...)` while visible; supports ArrowDown/ArrowUp/Enter/Tab (lines 38-47). It also sets `onMouseEnter` to change selection.
- **Accessibility**: buttons have no `aria-selected`, no `role="listbox"`, only visual highlighting. The footer shows ↑↓/↵ hints.

### `frontend/src/components/hub/HubConversationView.tsx`

- **Purpose**: Renders the message list + bottom composer after the first message has been sent.
- **State**: only a scroll ref; fully controlled by props.
- **Data flow**: scrolls to bottom on every `messages` change (lines 35-37). Maps messages to user/assistant bubbles (lines 50-93).
- **Special rendering**: detects the `__NO_PROVIDER__` sentinel and renders an amber "No AI Provider configured" card with a hardcoded `href="/huf/models"` link (lines 76-83).
- **Typing indicator**: shown if the last message is from the user OR `isStreaming` is true (lines 96-107). This means the indicator remains visible while the assistant bubble is already rendering SSE deltas, which is intentional but visually redundant.
- **Composer**: re-implements slash detection, send button, and new-chat button. No separate mobile layout.

### `frontend/src/services/streamChatApi.ts`

- **Purpose**: Unified SSE + REST chat transport.
- **Streaming availability**: `checkStreamingAvailable()` does a GET to `${frappeUrl}/huf/stream/ping` with a 3 s timeout (lines 44-64). The module-level `streamingAvailable` boolean is mutated by `setStreamingAvailable()` at app boot.
- **SSE path**: `streamAgentResponse()` POSTs to `${frappeUrl}/huf/stream/${encodeURIComponent(agentName)}` with `channel_id: 'Chat'`, optional `conversation_id`, `create_new`, `skip_user_message`, and `files` (lines 84-157). It decodes `data: ...` chunks, yields `delta`/`tool_call`/`complete`/`error` events, and returns `undefined` if the stream ends without a complete event.
- **Fallback path**: `sendMessage()` falls back to `sendMessageToConversation()` or `newConversation()` from `chatApi.ts` when `useStreaming` is false (lines 252-262).
- **Error path**: non-OK fetch yields `{ type: 'error', error: ... }`; `sendMessage()` throws on `error` chunks or when the stream ends without `complete` (lines 206-213). There is **no AbortSignal**; navigation mid-stream cannot cancel the request.

### `frontend/src/services/chatApi.ts`

- **Purpose**: REST chat endpoints and conversation listing.
- **Conversation list filtering**: the recents list (`useChatList`) and "By Agent" list both filter by `["channel", "=", "Chat"]` (chatApi.ts lines 189, 233, 264 and `useChatList.ts` line 47).
- **Implication for Hub**: because `streamChatApi.ts` sends `channel_id: 'Chat'`, a Hub conversation will appear in `/chat` lists, but the Hub page itself never loads existing history.

### `frontend/src/services/commandParser.ts`

- **Purpose**: Natural-language slash-command parser (unused in the current UI).
- **Exports**: `CommandDomain`, `ParsedCommand`, `parseSlashCommand`.
- **Parsing**: splits on whitespace, expects `/domain verb object`, supports aliases (`make`→`create`, `ls`→`list`), and qualifier keys (`for`, `in`, `as`, etc.).
- **Robustness**: throws if input doesn't start with `/`, if fewer than two tokens, or if domain unknown. No fuzzy matching.
- **Dead code**: nothing in the Hub imports this file.

---

## F2. ROLE MODEL

- **Frontend detection** (HubSimplePage.tsx lines 71-73):
  ```ts
  const role = capabilities.includes('system.admin') ? 'admin'
    : capabilities.includes('agent.use') ? 'builder'
    : 'viewer';
  ```
- **Source of role data**: `usePermissions()` → `PermissionsContext` → `getMe()` → `huf.permissions.get_me` (`frontend/src/services/permissionsApi.ts` line 39, backend `huf/permissions.py` lines 243-268).
- **Real Frappe roles vs invented heuristics**: the backend returns `huf_role` and a flat `capabilities` list from the Huf capability catalogue (`huf/permissions.py` lines 30-63). The Hub **ignores** `huf_role` and invents its own client-side mapping.
- **Critical mismatch**: the backend capability catalogue has **no `system.admin` capability**. The admin capability keys are `system.providers.manage`, `system.models.manage`, etc. Therefore `capabilities.includes('system.admin')` is always false for every user, including System Managers.
- **Consequence**:
  - The `admin` greeting and starter prompts are never shown.
  - The `operator` role is never assigned (no mapping path leads to it).
  - Any user with `agent.use` (Huf User, Huf Manager, System Manager) becomes `builder`; users without it become `viewer`.
- **Backend role mapping**: real enforcement is capability-based; the Huf role names are seeded from `DEFAULT_ROLE_CAPABILITIES` (`huf/permissions.py` lines 67-100) and map 1-to-1 to Frappe roles (`HUF_ROLE_FRAPPE_ROLE_MAP`, lines 104-109).

---

## F3. COMMAND PARSER

- **Command surface in the UI**: `SlashCommandMenu.tsx` hardcodes 7 commands (lines 12-20): `/flow`, `/agent`, `/users`, `/runs`, `/cost`, `/knowledge`, `/settings`.
- **Navigation mapping in HubSimplePage.tsx** (lines 167-170):
  ```ts
  const routeMap: Record<string, string> = {
    '/flow': '/flows', '/agent': '/agents', '/users': '/users',
    '/runs': '/executions', '/knowledge': '/knowledge', '/settings': '/models', '/cost': '/',
  };
  ```
- **Route cross-check against `App.tsx`**:
  - `/flows` ✅
  - `/agents` ✅
  - `/users` ✅
  - `/executions` ✅
  - `/knowledge` ✅
  - `/models` ✅
  - `/settings` ❌ exists in router but renders `<NotFoundPage />` (App.tsx lines 344-355). The mapping sends users to `/models` instead.
  - `/cost` ❌ not implemented; mapped to `/` (Hub home).
- **Parser robustness issues**:
  - The `commandParser.ts` parser is **not used** by the UI. The live logic in `HubSimplePage.tsx` simply slices from the last `/` and appends a space (line 172). It does not validate domain, verb, or object.
  - If the user types `hello /flow` and selects the command, the result is `hello /flow ` — the command is left inline, not interpreted.
  - `/cost` and `/settings` are presented to users but lead to non-existent or wrong destinations.
  - The parser supports a `realm` domain (line 1) that is not exposed in the menu or route map.
  - No handling for duplicate slashes, escaped characters, or command cancellation beyond blur/space.

---

## F4. UX / STATE GAPS

- **Loading states**:
  - Provider check is async but the UI shows no spinner/skeleton while `hasProvider === null`; the composer is fully interactive before the check completes.
  - `HubConversationView` has no distinct loading state for the assistant turn beyond the typing dots.
- **Error states**:
  - All `sendMessage` failures are collapsed into the same "Hub Orchestrator agent is not configured yet" message, regardless of actual cause (network, agent not found, provider error, rate limit).
  - No retry UI.
  - SSE errors inside `streamAgentResponse` are only surfaced via the `complete`/`error` event; malformed lines are silently skipped.
- **Empty states**:
  - Home view shows role-based starter prompts; if role mapping is wrong, non-admin users may see admin prompts or vice versa.
  - No empty-state illustration when a conversation has no messages.
- **Conversation persistence / resumability**:
  - The Hub **does create** an `Agent Conversation` on the server (via `run_agent_stream` with `channel_id: 'Chat'`).
  - Because the channel is `Chat`, the conversation appears in the `/chat` recents and "By Agent" lists (`chatApi.ts` filters on `channel = 'Chat'`).
  - However, the Hub page itself **does not resume**: `conversationId` is React state only and is lost on navigation or refresh. Returning to `/` starts a fresh empty conversation.
  - `handleNewChat` (lines 192-196) clears `messages`, `inputValue`, and `showSlashMenu` but does not tell the server to create a new conversation; the next send will pass `undefined` and the backend will create one.
- **Navigation mid-stream**:
  - There is **no AbortController** in `streamChatApi.ts`. If the user navigates away from `/` while streaming, the fetch continues in the background and React may attempt state updates on an unmounted component.
  - No cleanup effect in `HubSimplePage.tsx` cancels the in-flight request.
- **Mobile behavior**:
  - The Hub does **not** use `useIsMobile` or any responsive breakpoint. The 60 px sidebar is always visible (HubSimplePage.tsx line 205).
  - On small viewports the sidebar will consume fixed space and the composer will be squeezed; there is no hamburger/collapse.
- **Keyboard navigation / accessibility**:
  - The slash menu supports arrow keys and Enter/Tab.
  - Sidebar nav buttons have `title` attributes but no `aria-label`, so screen-reader users get only the icon (or the tooltip, which is not a substitute).
  - The send button is disabled when input is empty, but focus styles rely on default browser outlines.
  - No `aria-live` region announces streamed assistant content.
- **Provider-check UX**:
  - If no provider exists, the user can still type and press Enter; only after sending does the `__NO_PROVIDER__` sentinel appear (delayed 300 ms). There is no preemptive disabled state or inline warning.
  - The "Add Provider →" link in `HubConversationView.tsx` line 80 uses a plain `<a href="/huf/models">`, causing a full page reload instead of client-side navigation.

---

## F5. HARDCODING / TODOs / DEAD CODE

- **Hardcoded agent name**:
  - `HubSimplePage.tsx` line 133: `{ agent: 'Hub Orchestrator', message: msg, conversationId }`
  - `HubSimplePage.tsx` line 144: fallback message references "Hub Orchestrator agent".
  - `HubConversationView.tsx` line 72: assistant label hardcoded as `"Hub Orchestrator"`.
  - PR notes acknowledge this agent needs to be seeded on install; no such seed exists in the current branch.
- **Hardcoded greetings** (HubSimplePage.tsx lines 23-28):
  ```ts
  const GREETINGS: Record<string, string> = {
    admin: 'What would you like to orchestrate?',
    builder: 'What are you building today?',
    operator: 'What do you need to monitor?',
    viewer: 'What insights are you looking for?',
  };
  ```
- **Hardcoded starter prompts** (HubSimplePage.tsx lines 30-55): route targets are hardcoded strings.
- **Hardcoded default response** (HubSimplePage.tsx line 138): `"I've processed your request."`.
- **Hardcoded navigation items** (HubSimplePage.tsx lines 57-64) and route map (lines 167-170).
- **TODO / dead code**:
  - `frontend/src/services/commandParser.ts` is exported but never imported; its `realm` domain is dead.
  - `HubSimplePage.tsx` role mapping path for `admin` and `operator` is effectively dead due to the non-existent `system.admin` capability.
  - `frontend/src/components/HomeHeaderActions.tsx` still contains a "New" dropdown whose items say "Open Flows" / "Open Agents" (lines 36-43) — labels are misleading because they open listing pages, not create flows/agents.
- **No TODO markers found** in the Hub files (`TODO`, `FIXME`, `XXX` searches returned none), but the dead code above functions as unused scaffolding.

---

## Summary Counts

| Task | Issue count |
|------|-------------|
| F1 | 6 major (no abort, state-only conversationId, conflated error messages, no SSRF/mobile concerns in scope, provider race, hardcoded agent) |
| F2 | 1 critical (role mapping uses non-existent `system.admin`; admin/operator greetings unreachable) |
| F3 | 4 (unused parser, `/settings`→NotFound, `/cost` unimplemented, inline command append broken) |
| F4 | 7 (no loading for provider check, no resumability, no abort on nav, no mobile adaption, a11y gaps, provider UX delayed, error conflation) |
| F5 | 5+ (hardcoded agent/greetings/prompts, dead command parser, dead admin/operator role branches) |

## Verdict

**MIXED** — the page renders, typechecks/lints pass, and it correctly wires into the existing SSE/REST chat layer, but the role model is broken, the command parser is unused and has dead routes, conversations are not resumable in the Hub, and error handling conflates every failure with a missing "Hub Orchestrator" agent.
