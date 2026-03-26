---
name: frontend-core
description: HUF Frontend Core & Architecture - React 18 + TypeScript + Vite application with Frappe integration, shadcn/ui components, Tailwind CSS, and real-time socket connections. Use when working with frontend components, contexts, services, hooks, or pages.
category: ui
---

# HUF Frontend Core & Architecture

HUF is a Frappe-based AI agent platform with a modern React frontend. This skill covers the core architecture, patterns, and extension points for the frontend application.

## Overview

The HUF frontend is a single-page application (SPA) built with:
- **React 18** with StrictMode
- **TypeScript** with strict mode enforcement
- **Vite** for build tooling and HMR
- **Tailwind CSS** for styling
- **shadcn/ui** component library (50+ components)
- **Frappe JS SDK** for backend communication
- **Socket.io** for real-time updates
- **React Router v7** for navigation
- **React Flow** for visual flow builder

## Key Files

| File | Purpose |
|------|---------|
| `frontend/src/main.tsx` | React 18 app bootstrap with StrictMode |
| `frontend/src/App.tsx` | Root component with routing, providers, and socket setup |
| `frontend/src/layouts/UnifiedLayout.tsx` | Main layout wrapper with sidebar and header |
| `frontend/src/layouts/UnifiedHeader.tsx` | Dynamic header with breadcrumbs and actions |
| `frontend/src/contexts/UserContext.tsx` | Authentication and user state management |
| `frontend/src/contexts/PermissionsContext.tsx` | Role-based permission checking |
| `frontend/src/contexts/FlowContext.tsx` | Flow builder state management |
| `frontend/src/contexts/ModalContext.tsx` | Modal state for flow builder |
| `frontend/src/lib/frappe-sdk.ts` | Frappe SDK initialization and exports |
| `frontend/src/lib/frappe-error.ts` | Error handling utilities for Frappe API |
| `frontend/src/lib/utils.ts` | Utility functions (cn, etc.) |
| `frontend/src/services/agentApi.ts` | Agent CRUD and agent-related API calls |
| `frontend/src/services/flowService.ts` | In-memory flow management service |
| `frontend/src/services/chatApi.ts` | Chat and conversation API |
| `frontend/src/services/mcpApi.ts` | MCP server management API |
| `frontend/src/types/agent.types.ts` | Agent, Tool, Conversation TypeScript types |
| `frontend/src/types/flow.types.ts` | Flow, Node, Edge TypeScript types |
| `frontend/src/hooks/useChatSocket.tsx` | Real-time socket hook for chat |
| `frontend/src/components/app-sidebar.tsx` | Main navigation sidebar |
| `frontend/src/components/ui/*.tsx` | 50+ shadcn/ui base components |
| `frontend/src/components/chat/*.tsx` | Chat-related components |
| `frontend/src/components/agent/*.tsx` | Agent form and configuration components |
| `frontend/src/data/doctypes.ts` | DocType name constants |

## How It Works

### Application Bootstrap

```
main.tsx → App.tsx → BrowserRouter → Providers → Routes
```

1. **main.tsx**: Creates React root with StrictMode
2. **App.tsx**: Sets up:
   - React Router with `/huf` basename
   - Global providers (UserProvider, PermissionsProvider)
   - Socket.io connection for real-time events
   - Route definitions with lazy-loaded pages
   - Toast notifications via Sonner

### Provider Hierarchy

```tsx
<BrowserRouter>
  <UserProvider>        {/* Auth state */}
    <PermissionsProvider>  {/* Role permissions */}
      <FlowProvider>    {/* Flow builder (conditional) */}
        <ModalProvider> {/* Modal state (conditional) */}
          <Routes>...</Routes>
        </ModalProvider>
      </FlowProvider>
    </PermissionsProvider>
  </UserProvider>
</BrowserRouter>
```

### Layout System

**UnifiedLayout** (`layouts/UnifiedLayout.tsx`):
- Wraps all pages with consistent structure
- Includes AppSidebar for navigation
- Dynamic header via UnifiedHeader
- Supports custom header actions per route
- Optional header hiding (for chat page)

```tsx
<UnifiedLayout 
  headerActions={<CustomActions />} 
  breadcrumbs={[{ label: 'Agents', href: '/agents' }]}
  hideHeader={false}
>
  <PageContent />
</UnifiedLayout>
```

### Data Flow Architecture

```
UI Component → Service API → Frappe SDK → Backend
     ↓              ↓
  Context ←── State Update
```

1. **Pages** use services to fetch data
2. **Services** (`services/*Api.ts`) wrap Frappe SDK calls
3. **Contexts** provide shared state (user, permissions, flows)
4. **Components** consume contexts via custom hooks

### Authentication Flow

1. `UserContext.checkAuth()` called on mount
2. Frappe SDK `auth.getLoggedInUser()` validates session
3. On success: fetch user details via `db.getDoc('User')`
4. On failure: redirect to `/login?redirect-to=/huf`
5. `ProtectedRoute` wraps all authenticated routes

### Socket.io Real-time

**Global Socket** (App.tsx):
- Connection status monitoring
- Global events: `tool_call_started`

**Chat Socket** (useChatSocket hook):
- Conversation-specific events
- Events: `conversation:{id}`, `new_agent_message`, tool status updates

### Flow Builder Architecture

```
FlowContext → flowService → In-memory state
     ↓
FlowCanvas (React Flow) → Nodes/Edges
     ↓
Modals for configuration
```

- **FlowContext**: React state management for flows
- **flowService**: In-memory Map-based storage
- **FlowCanvas**: React Flow canvas with custom nodes
- **ModalContext**: Trigger/action configuration modals

### Component Organization

```
components/
├── ui/              # shadcn/ui base components (50+)
├── agent/           # Agent form sections
├── chat/            # Chat interface components
├── ai-elements/     # AI-specific UI elements
├── dashboard/       # Dashboard views
├── tools/           # Tool management components
├── nodes/           # Flow builder node types
├── mcp/             # MCP server components
├── knowledge/       # Knowledge source components
└── modals/          # Shared modal components
```

### API Services Pattern

```typescript
// services/agentApi.ts
export async function getAgent(name: string): Promise<AgentDoc> {
  try {
    const agent = await db.getDoc(doctype.Agent, name);
    return agent as AgentDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching agent ${name}`);
  }
}
```

**Key patterns**:
- All services use `handleFrappeError` for consistent error handling
- Return typed promises with specific return types
- Support pagination with `GetAgentsParams` pattern

### Type Definitions

Core types in `types/`:
- **agent.types.ts**: AgentDoc, AgentTool, AgentConversation, AgentRun
- **flow.types.ts**: Flow, FlowNode, FlowEdge, TriggerConfig, ActionConfig
- **knowledge.types.ts**: KnowledgeSource, KnowledgeInput
- **modal.types.ts**: Modal state types

**Important**: Frappe returns numeric booleans (0/1), not true/false.

## Extension Points

### Adding a New Page

1. Create page component in `pages/YourPage.tsx`
2. Add lazy import in `App.tsx`
3. Add Route in `App.tsx` with `ProtectedRoute`
4. Create header actions component if needed
5. Add navigation item in `components/app-sidebar.tsx`

### Adding a New Service

1. Create `services/yourApi.ts`
2. Import `db`, `call` from `@/lib/frappe-sdk`
3. Use `handleFrappeError` for error handling
4. Export typed functions
5. Add types to appropriate `types/*.types.ts` file

### Adding a New Context

1. Create `contexts/YourContext.tsx`
2. Follow pattern: `createContext` → Provider component → `useYourContext` hook
3. Wrap in App.tsx if global, or specific routes if local
4. Always throw error in hook if used outside provider

### Adding UI Components

**For shadcn/ui components**:
- Use existing components from `components/ui/`
- Follow shadcn/ui patterns (class-variance-authority, cn utility)

**For custom components**:
- Place in appropriate `components/` subdirectory
- Use TypeScript interfaces for props
- Follow existing naming conventions (PascalCase)

### Adding New Types

1. Add to existing file in `types/` if related
2. Or create new `types/your.types.ts`
3. Export from file
4. Import via `@/types/your.types` alias

## Dependencies

### Core Dependencies

| Package | Purpose |
|---------|---------|
| react ^18.3.1 | UI framework |
| react-dom ^18.3.1 | DOM renderer |
| react-router-dom ^7.9.4 | Routing |
| frappe-js-sdk ^1.11.0 | Frappe backend API |
| socket.io-client ^4.7.5 | Real-time communication |

### UI Dependencies

| Package | Purpose |
|---------|---------|
| tailwindcss ^3.4.13 | CSS framework |
| @radix-ui/* | Headless UI primitives |
| lucide-react ^0.577.0 | Icons |
| class-variance-authority ^0.7.1 | Component variants |
| tailwind-merge ^2.5.2 | Tailwind class merging |
| clsx ^2.1.1 | Conditional classes |

### Flow Builder Dependencies

| Package | Purpose |
|---------|---------|
| @xyflow/react ^12.9.3 | React Flow for visual flows |
| reactflow ^11.11.4 | Legacy React Flow (both used) |

### Build Dependencies

| Package | Purpose |
|---------|---------|
| vite ^5.4.8 | Build tool |
| typescript ^5.5.3 | Type checking |
| eslint ^9.11.1 | Linting |
| postcss ^8.4.47 | CSS processing |
| autoprefixer ^10.4.20 | CSS autoprefixing |

## Gotchas

### TypeScript Strictness

**CRITICAL**: The project uses TypeScript strict mode. The build will fail on:

- Unused variables (`error TS6133`)
- Unused imports
- Unused functions
- Implicit any types
- Missing return types on exported functions

**Always clean up after refactoring**:
```bash
cd frontend && yarn typecheck
# or
yarn build  # Runs tsc -b first
```

### Frappe Boolean Handling

Frappe returns `0` and `1` for booleans, not `true`/`false`:

```typescript
// WRONG
if (agent.disabled) { }

// CORRECT
if (agent.disabled === 1) { }
```

Common Frappe boolean fields:
- `disabled: 0 | 1`
- `allow_chat: 0 | 1`
- `persist_conversation: 0 | 1`

### Path Aliases

The project uses Vite path aliases:
- `@/components/*` → `src/components/*`
- `@/lib/*` → `src/lib/*`
- `@/hooks/*` → `src/hooks/*`
- `@/services/*` → `src/services/*`
- `@/types/*` → `src/types/*`
- `@/data/*` → `src/data/*`
- `@/utils/*` → `src/utils/*`

Always use aliases for imports, not relative paths:
```typescript
// GOOD
import { db } from '@/lib/frappe-sdk';

// BAD
import { db } from '../lib/frappe-sdk';
```

### Socket Connection

Socket connection requires:
1. `window.frappe.boot.sitename` to be available
2. Proper socket.io port configuration
3. Connection may fail silently in development without port

Always handle connection errors gracefully with user feedback.

### Provider Order Matters

Contexts must be nested correctly:

```tsx
// CORRECT
<UserProvider>
  <PermissionsProvider>
    <Component />
  </PermissionsProvider>
</UserProvider>

// WRONG - PermissionsContext depends on UserContext
<PermissionsProvider>
  <UserProvider>
    <Component />
  </UserProvider>
</PermissionsProvider>
```

### Error Handling Pattern

Always use `handleFrappeError` from `@/lib/frappe-error`:

```typescript
try {
  const result = await db.getDoc(doctype.Agent, name);
  return result;
} catch (error) {
  handleFrappeError(error, `Error fetching agent ${name}`);
}
```

This ensures consistent error messages and proper type narrowing.

### Lazy Loading

Pages are lazy-loaded in App.tsx:

```typescript
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
```

Always wrap lazy components in `<Suspense>`:

```tsx
<Suspense fallback={<PageLoader />}>
  <AgentsPage />
</Suspense>
```

### Build Output

Build output goes to:
- `huf/public/frontend/` - Built assets
- `huf/www/huf.html` - Copied HTML entry point

The `copy-html-entry` script copies the index.html for Frappe routing.

### Doctype Constants

Always use doctype constants from `@/data/doctypes`:

```typescript
import { doctype } from '@/data/doctypes';

// GOOD
await db.getDoc(doctype.Agent, name);

// BAD
await db.getDoc('Agent', name);
```
