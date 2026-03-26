---
name: frontend-chat
category: ui
version: 1.0.0
description: Comprehensive chat interface for HUF AI agents with streaming, artifacts, and real-time updates
---

# Frontend Chat System

## Overview

The Frontend Chat System provides a comprehensive chat interface for interacting with HUF AI agents. It supports real-time streaming responses, rich content rendering (markdown, artifacts, web previews), conversation history, and multi-modal interactions (text, audio, images).

The system is built with React, TypeScript, Tailwind CSS, and integrates with the Frappe backend via REST APIs and Socket.io for real-time updates.

## Key Files

| File | Purpose |
|------|---------|
| `frontend/src/pages/ChatPageV2.tsx` | Main chat page with sidebar toggle and responsive layout |
| `frontend/src/components/chat/ChatWindowV2.tsx` | Core chat container composing header and message list |
| `frontend/src/components/chat/ChatWindowHeader.tsx` | Displays agent info, model badge, and navigation |
| `frontend/src/components/chat/ChatMessageList.tsx` | Message list with infinite scroll, socket integration |
| `frontend/src/components/chat/ChatMessage.tsx` | Individual message rendering with tool support |
| `frontend/src/components/chat/ChatInput.tsx` | Message input with auto-resize, speech input, attachments |
| `frontend/src/components/chat/MessageContentWithArtifacts.tsx` | Rich content parser for artifacts, web previews, JSX |
| `frontend/src/components/chat/MessageActions.tsx` | Copy, thumbs up/down feedback actions |
| `frontend/src/components/chat/ChatListing.tsx` | Sidebar conversation list with "By Agent" and "Recents" tabs |
| `frontend/src/components/chat/AgentModelSelector.tsx` | Agent selection dropdown with search |
| `frontend/src/components/chat/ConversationMenu.tsx` | Right-click context menu for conversations |
| `frontend/src/components/chat/types.ts` | TypeScript types for messages |
| `frontend/src/components/chat/chatMessageList.mappers.ts` | Socket event to message state mappers |
| `frontend/src/components/chat/useChatAgentIdentity.ts` | Hook to resolve agent from conversation or URL |
| `frontend/src/components/chat/useChatScrollToBottom.ts` | Auto-scroll management hook |
| `frontend/src/components/chat/useChatList.ts` | Conversation list data hook |
| `frontend/src/services/chatApi.ts` | Chat REST API methods |
| `frontend/src/services/streamChatApi.ts` | SSE streaming API with REST fallback |
| `frontend/src/hooks/useChatSocket.tsx` | Socket.io hook for real-time updates |
| `frontend/src/utils/socket.ts` | Socket.io client factory |

## AI Elements Components

| File | Purpose |
|------|---------|
| `frontend/src/components/ai-elements/message.tsx` | Base message wrapper with user/assistant styling |
| `frontend/src/components/ai-elements/tool.tsx` | Tool call display with input/output |
| `frontend/src/components/ai-elements/artifact.tsx` | Artifact container component |
| `frontend/src/components/ai-elements/audio-player.tsx` | Audio playback with media-chrome |
| `frontend/src/components/ai-elements/code-block.tsx` | Syntax-highlighted code with copy button |
| `frontend/src/components/ai-elements/reasoning.tsx` | AI reasoning/thinking display |
| `frontend/src/components/ai-elements/image.tsx` | Image display with download |
| `frontend/src/components/ai-elements/web-preview.tsx` | Web preview renderer |
| `frontend/src/components/ai-elements/jsx-preview.tsx` | JSX preview renderer |
| `frontend/src/components/ai-elements/speech-input.tsx` | Voice recording button |

## How It Works

### Message Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   User      │────▶│  ChatInput   │────▶│ streamChatApi   │
│  Types msg  │     │  onSubmit    │     │ (SSE/REST)      │
└─────────────┘     └──────────────┘     └─────────────────┘
                                                  │
                       ┌──────────────────────────┘
                       ▼
              ┌─────────────────┐
              │  Backend Agent  │
              │   Processing    │
              └─────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │  Delta   │ │Tool Call │ │  Complete    │
   │ (SSE)    │ │(Socket)  │ │  Event       │
   └──────────┘ └──────────┘ └──────────────┘
         │             │             │
         ▼             ▼             ▼
   ┌────────────────────────────────────────┐
   │      ChatMessageList Component         │
   │  - useChatSocket for real-time updates │
   │  - useInfiniteScroll for history       │
   │  - Local state for optimistic updates  │
   └────────────────────────────────────────┘
                       │
                       ▼
   ┌────────────────────────────────────────┐
   │         ChatMessage Component          │
   │  - Renders user/assistant messages     │
   │  - Tool calls via Tool component       │
   │  - Artifacts via MessageContentWith... │
   └────────────────────────────────────────┘
```

### Architecture Overview

1. **Page Layer** (`ChatPageV2.tsx`): Manages sidebar state, responsive layout, and routing
2. **Window Layer** (`ChatWindowV2.tsx`): Composes header and message list
3. **List Layer** (`ChatMessageList.tsx`): Manages message state, infinite scroll, sockets
4. **Message Layer** (`ChatMessage.tsx`): Renders individual messages with variants
5. **Content Layer** (`MessageContentWithArtifacts.tsx`): Parses and renders rich content

### Real-Time Updates

The system uses two mechanisms for real-time updates:

**1. SSE Streaming** (`streamChatApi.ts`)
- Primary method for streaming agent responses
- Endpoint: `POST /huf/stream/{agentName}`
- Events: `delta`, `tool_call`, `complete`, `error`
- Falls back to REST if SSE unavailable

**2. Socket.io** (`useChatSocket.tsx`)
- Real-time tool execution updates
- New message notifications
- Channel: `conversation:{conversationId}`
- Events: `tool_call_started`, `tool_call_completed`, `tool_call_failed`, `new_agent_message`

### Message Types

```typescript
// From types.ts
interface MessageType {
  key: string;                    // Unique message key
  from: 'user' | 'assistant';     // Message source
  versions: {
    id: string;
    content: string;
  }[];
  kind?: string;                  // 'Image', 'Tool Result', etc.
  generatedImage?: string;        // URL for generated images
  generatedAudio?: string;        // URL for generated audio
  voiceMessage?: string;
  tools?: {                       // Tool execution info
    tool_call_id: string;
    name: string;
    status: ToolState;
    parameters: Record<string, unknown>;
    result?: string;
    error?: string;
  }[];
}
```

### Artifact System

Artifacts are special content blocks that render interactively:

```
┌─────────────────────────────────────────────┐
│  Agent Response with <artifact> tags       │
│  <artifact type="code" language="tsx">     │
│    const App = () => <div>Hello</div>      │
│  </artifact>                                │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  MessageContentWithArtifacts                │
│  1. Decodes HTML entities                   │
│  2. Parses artifacts via artifactParser     │
│  3. Parses web previews                     │
│  4. Parses JSX previews                     │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  ArtifactRenderer                           │
│  - Code: Syntax highlighted                 │
│  - React: Live preview                      │
│  - Mermaid: Diagram                         │
│  - HTML/SVG: Iframe preview                 │
└─────────────────────────────────────────────┘
```

### Conversation Management

**Creating a Conversation:**
1. User selects agent from `AgentModelSelector`
2. First message triggers `newConversation` API
3. Backend creates `Agent Conversation` document
4. Frontend navigates to `/chat/{conversationId}`

**Loading History:**
1. `useInfiniteScroll` fetches messages in reverse order
2. `chatMessageList.mappers.ts` merges API data with local state
3. Socket events update local state for real-time tools

**Model Mismatch Detection:**
- Compares conversation model with agent model
- Shows "New Conversation" button if mismatched
- Prevents sending messages to wrong model

## Extension Points

### Adding a New Message Kind

1. **Update Types** (`types.ts`):
```typescript
interface MessageType {
  kind?: string | 'new-kind';  // Add your kind
  newField?: string;            // Add custom data
}
```

2. **Handle in ChatMessage** (`ChatMessage.tsx`):
```typescript
{message.kind === 'new-kind' ? (
  <NewKindRenderer data={message.newField} />
) : (
  // existing conditions
)}
```

3. **Handle Socket Events** (`chatMessageList.mappers.ts`):
```typescript
export function upsertAgentMessageFromSocket(...) {
  // Add handling for your new message kind
  if (event.kind === 'new-kind') {
    // Update message with new data
  }
}
```

### Adding a New Artifact Type

1. **Update Types** (`types/artifact.types.ts`):
```typescript
export type ArtifactType = 
  | 'code' | 'document' | ... 
  | 'new-type';  // Add your type

export interface ParsedNewType {
  // Define your artifact structure
}
```

2. **Create Parser** (`utils/newTypeParser.ts`):
```typescript
export function parseNewType(content: string): NewTypeParseResult {
  // Extract <new-type> tags from content
  // Return { text, items }
}
```

3. **Update MessageContentWithArtifacts**:
```typescript
import { parseNewType, hasNewTypes } from '@/utils/newTypeParser';
import { NewTypeRenderer } from './NewTypeRenderer';

// In component:
if (hasNewTypes(decodedContent)) {
  const parsed = parseNewType(textContent);
  textContent = parsed.text;
  newTypes = parsed.items;
}

// In render:
{newTypes.map((item, idx) => (
  <NewTypeRenderer key={idx} item={item} />
))}
```

4. **Create Renderer** (`NewTypeRenderer.tsx`):
```typescript
export function NewTypeRenderer({ item }: { item: ParsedNewType }) {
  return <div className="new-type">{/* Render logic */}</div>;
}
```

### Customizing Tool Display

1. **Tool Component** (`ai-elements/tool.tsx`):
```typescript
// Tool states map to UI badges
const getStatusBadge = (status: ExtendedToolState) => {
  // Add your custom state handling
  'custom-state': <CustomBadge />
};
```

2. **Status Mapping** (`chat/utils.ts`):
```typescript
export function mapToolStatusToState(status?: string): ExtendedToolState {
  // Map backend status to frontend state
  'Custom': 'custom-state',
}
```

### Adding Message Actions

1. **Update MessageActions** (`MessageActions.tsx`):
```typescript
interface MessageActionsProps {
  content: string;
  agentMessageId?: string;
  onFeedback: ...;
  onRegenerate?: () => void;  // Add new action
}

// In component:
<Button onClick={onRegenerate}>
  <RefreshIcon />
</Button>
```

2. **Wire up in ChatMessage**:
```typescript
<MessageActions
  content={...}
  onFeedback={...}
  onRegenerate={() => handleRegenerate(message.key)}
/>
```

## Dependencies

### Core Dependencies
- `react` / `react-router-dom` - UI framework and routing
- `socket.io-client` - Real-time communication
- `streamdown` - Markdown rendering (custom package)
- `prismjs` - Syntax highlighting
- `media-chrome/react` - Audio player components

### UI Components
- `@radix-ui/*` - Headless UI primitives
- `lucide-react` - Icons
- `tailwindcss` / `tailwind-merge` / `clsx` - Styling
- `class-variance-authority` - Component variants

### State Management
- React hooks for local state
- Custom hooks for data fetching (`useInfiniteScroll`)
- Socket.io for real-time state updates

### Backend Integration
- Frappe SDK (`frappe-sdk` pattern via `frappeApi.ts`)
- REST APIs for CRUD operations
- Socket.io for real-time events
- SSE for streaming responses

## Gotchas

### Message State Merging

When merging socket updates with API data, the system prioritizes:
1. Socket state for tools (real-time updates)
2. API state for message content (source of truth)
3. Local optimistic updates during transitions

See `chatMessageList.mappers.ts` for the merge logic.

### Scroll Behavior

- Initial load: Instant scroll to bottom
- New messages: Smooth scroll to bottom
- Image load: Scroll after image loads (`scrollToBottomAfterPaint`)
- User scroll up: Disable auto-scroll (not implemented, always scrolls)

### Socket Connection

- One socket per conversation
- Auto-reconnects once, then gives up
- Falls back to polling if websocket fails
- Events are namespaced: `conversation:{id}`

### Streaming Fallback

If SSE streaming fails:
1. `setStreamingAvailable(false)` disables SSE
2. Falls back to REST API
3. No auto-retry for SSE
4. User must refresh to re-enable SSE

### Model Mismatch

When agent model changes after conversation creation:
- UI detects mismatch via `useEffect` comparison
- Shows "New Conversation" button
- Prevents sending messages
- Does not auto-migrate existing conversations

### Audio Transcription Flow

1. User records audio via `SpeechInput`
2. `handleAudioRecorded` uploads and transcribes
3. Transcript inserted as user message
4. Agent run triggered automatically
5. Both transcription and response shown

### Artifact Parsing Order

Tags are parsed in specific order to prevent nesting issues:
1. JSX previews (innermost)
2. Web previews
3. Artifacts (outermost)

This prevents `<web-preview>` inside `<artifact>` from being double-parsed.

### HTML Entity Decoding

Backend may send HTML-escaped content (`&lt;web-preview&gt;`). The system decodes these before parsing:

```typescript
function decodeHtmlEntities(text: string): string {
  // Handles &lt;, &gt;, &quot;, &#39;, &amp;
}
```

### Tool Result Handling

Tool results are merged carefully:
- Temporary tools from socket events have `temp-*` IDs
- API-loaded tools use actual IDs
- Result/error shown based on `toolStatus`
- Args parsed from JSON string if needed

### Conversation Transition

When creating a new conversation:
1. Optimistic UI shows messages immediately
2. `isCreatingConversationRef` prevents double-creation
3. `newlyCreatedConversationIdRef` handles transition state
4. 800ms delay before enabling API fetching
5. Prevents race conditions between local state and API

### Sidebar State

- Desktop: Collapsible with transition animation
- Mobile: Overlay that covers full screen
- Auto-closes on mobile when conversation selected
- State persisted in component (not URL)

### Date Grouping

Recents tab groups by:
- TODAY
- YESTERDAY  
- THIS WEEK (last 7 days)
- OLDER

Uses `last_activity` or `modified` timestamp from conversation.

### Type Safety

The `MessageType` uses `key` (not `id`) for React keys because:
- API messages use document `name` as key
- Optimistic messages use timestamp-based keys
- Socket updates reference both types

### Image Loading

Generated images show skeleton until loaded:
```typescript
{message.generatedImage ? (
  <Image src={...} onLoad={() => scrollToBottomAfterPaint(false)} />
) : (
  <Skeleton className="w-full h-[512px]" />
)}
```
