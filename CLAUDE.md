# CLAUDE.md

This file provides context and instructions for Claude Code and other AI coding assistants to effectively work on the Huf Frappe application.

## Project Overview

**Huf** (formerly AgentFlo) is a comprehensive Frappe application for creating and managing conversational AI agents with advanced workflow automation capabilities. It enables:

- **AI Agent Creation**: Define agents with custom instructions, models, and parameters
- **Event-Driven Automation**: Trigger agents on DocType events (validate, submit, insert, etc.)
- **Scheduled Execution**: Run agents at regular intervals (hourly, daily, weekly)
- **Real-Time Chat**: Interactive chat interfaces for agent conversations
- **Comprehensive Tool System**: CRUD operations, custom functions, HTTP requests, MCP integration
- **Knowledge Management**: RAG-based knowledge sources with SQLite FTS5
- **Visual Flow Builder**: Drag-and-drop workflow orchestration (React Flow-based)

**Repository**: https://github.com/tridz-dev/huf

> **Status**: Actively being migrated from an existing implementation. Not recommended for production use at this stage.

## Repository Structure

```
huf/
├── huf/                          # Backend (Frappe app)
│   ├── ai/                       # Core AI logic
│   │   ├── agent_integration.py  # AgentManager, run_agent_sync, run_agent_stream
│   │   ├── agent_stream_renderer.py # SSE page renderer for streaming
│   │   ├── agent_scheduler.py    # Scheduled agent execution
│   │   ├── agent_hooks.py        # DocType event triggers
│   │   ├── conversation_manager.py # Conversation history
│   │   ├── sdk_tools.py          # Tool serialization
│   │   ├── tool_functions.py     # CRUD operations
│   │   ├── tool_registry.py      # Tool discovery from hooks
│   │   ├── tool_serializer.py    # Provider-agnostic tool format
│   │   ├── mcp_client.py         # MCP protocol support
│   │   ├── http_handler.py       # HTTP tools with SSRF protection
│   │   ├── run.py                # Provider routing layer
│   │   ├── providers/            # LLM provider implementations
│   │   │   ├── litellm.py        # Unified LiteLLM provider
│   │   │   ├── openrouter.py     # OpenRouter with retry logic
│   │   │   └── ...
│   │   ├── knowledge/            # RAG/Knowledge management
│   │   │   ├── indexer.py        # Ingestion pipeline
│   │   │   ├── retriever.py      # Search and retrieval
│   │   │   ├── backends/         # Storage backends (SQLite FTS5)
│   │   │   ├── extractors/       # Text extraction (PDF, DOCX, HTML)
│   │   │   └── chunkers/         # Text chunking strategies
│   │   ├── flow_engine.py        # Flow Engine: graph orchestration
│   │   ├── flow_api.py           # Flow whitelisted API endpoints
│   │   ├── flow_eval.py          # Safe expression evaluator for edges
│   │   ├── flow_tool_executor.py # Deterministic tool execution
│   │   ├── flow_orchestrator.py  # Router/orchestrator prompt + JSON parsing
│   │   ├── flow_tools.py         # Flow tool definitions for huf_tools hook
│   │   └── orchestration/        # Multi-step workflow planning
│   ├── huf/doctype/              # DocType definitions (35 total)
│   ├── hooks.py                  # Frappe integration hooks
│   ├── install.py                # Installation/migration hooks
│   ├── www/                      # Web routes
│   ├── public/                   # Static assets
│   └── templates/                # Jinja templates
├── frontend/                     # Frontend (React app)
│   └── src/
│       ├── App.tsx               # Root component, routing, providers
│       ├── main.tsx              # Entry point (React 18 createRoot)
│       ├── pages/                # Page components (18 files)
│       ├── layouts/              # UnifiedLayout, UnifiedHeader
│       ├── components/           # UI components (~150 files)
│       │   ├── agent/            # Agent form tabs (General, Behavior, Triggers, Tools, Advanced)
│       │   ├── chat/             # Chat UI (ChatWindowV2, ChatInput, messages, listings)
│       │   ├── ai-elements/      # AI-specific UI primitives (30 components)
│       │   ├── dashboard/        # Dashboard cards, views, filters, layouts
│       │   ├── nodes/            # Flow builder nodes (Trigger, Action, End)
│       │   ├── modals/           # Flow modals (NodeSelection, ActionSelection, TriggerConfig)
│       │   ├── tools/            # Tool management (forms, cards, modals)
│       │   ├── mcp/              # MCP server details/connection/tools tabs
│       │   └── ui/               # shadcn/ui primitives (54 components)
│       ├── contexts/             # React contexts (User, Flow, Modal, Integrations)
│       ├── hooks/                # Custom hooks (infinite scroll, debounce, chat socket)
│       ├── services/             # API service layer (11 service files)
│       ├── types/                # TypeScript definitions (agent, flow, artifacts, pagination)
│       ├── lib/                  # Frappe SDK wrapper, error handling, cn()
│       ├── data/                 # Static data (doctypes, triggers, actions, colors)
│       ├── config/               # Tool templates JSON
│       └── utils/                # Helpers (socket, time, status, parsers)
├── docker/                       # Docker quick-try environment
│   ├── docker-compose.yml        # MariaDB, Redis, Frappe services
│   └── init.sh                   # Automated setup script
├── docs/                         # Documentation site (Next.js)
├── .github/workflows/            # CI/CD definitions
├── pyproject.toml                # Python config and dependencies
├── package.json                  # Root scripts
└── .pre-commit-config.yaml       # Pre-commit hooks
```

## Tech Stack

### Backend
- **Framework**: Frappe (ERPNext framework)
- **Language**: Python 3.10+
- **Database**: MariaDB (via Frappe)
- **Key Dependencies**:
  - `openai-agents` - AI agent SDK
  - `litellm>=1.0.0` - Multi-provider LLM interface (100+ providers)
  - `llama-index-core>=0.10.0` - RAG/knowledge indexing

### Frontend
- **Framework**: React 18.3.1
- **Language**: TypeScript 5.5.3
- **Build Tool**: Vite 5.4.8
- **Routing**: React Router v7 (`react-router-dom ^7.9.4`, basename `/huf`)
- **Styling**: Tailwind CSS 3.4.13 (CSS variable theming, dark mode via class)
- **UI Components**: Radix UI (shadcn/ui) — 54 primitive components
- **Flow Builder**: XYFlow (`@xyflow/react ^12.9.3`) + ReactFlow (`reactflow ^11.11.4`)
- **State Management**: React Context API (User, Flow, Modal, Integrations)
- **Forms**: React Hook Form 7 + Zod 3
- **Tables**: TanStack React Table (`@tanstack/react-table ^8.21.3`)
- **Chat/Streaming**: SSE via fetch + ReadableStream, Socket.io (`socket.io-client ^4.7.5`)
- **AI SDK**: Vercel AI SDK (`ai ^5.0.106`), Shiki for code highlighting, Streamdown for markdown
- **Icons**: Lucide React (`lucide-react ^0.563.0`)
- **Animations**: Motion (`motion ^12.23.24`), `tailwindcss-animate`
- **Backend SDK**: `frappe-js-sdk ^1.11.0` (auth, db, call)

## Development Commands

### Frontend
```bash
cd frontend
yarn install          # Install dependencies
yarn dev              # Dev server on localhost:8080
yarn build            # Production build to huf/public/frontend/
yarn typecheck        # TypeScript type checking
yarn lint             # ESLint
```

### Backend (Frappe Bench)
```bash
bench get-app huf <repo-path>
bench setup requirements      # Install Python deps (including litellm)
bench new-site <sitename>
bench install-app huf
bench --site <sitename> run-tests --app huf
```

### Root Scripts
```bash
yarn dev              # Run frontend dev server
yarn build            # Build docs + frontend
yarn build-frontend   # Build frontend only
yarn build-docs       # Build documentation
```

### Docker Quick-Try
For quick evaluation without a full Frappe bench setup:
```bash
cd docker
docker compose up
```
This starts MariaDB, Redis, and Frappe with HUF pre-installed. Access at `http://localhost:8000` (admin/admin). First run takes 5-8 minutes for setup.

## Code Style and Conventions

### Python (Backend)

**Formatting**: Ruff with the following settings:
- **Indent**: Tabs
- **Line length**: 110 characters
- **Quote style**: Double quotes
- **Target**: Python 3.10+

**Patterns**:
```python
# Frappe Document Pattern
class AgentDocument(Document):
    def validate(self):
        # Field validation
    def before_save(self):
        # Pre-save logic
    def after_insert(self):
        # Post-insert logic

# Whitelisted API endpoints
@frappe.whitelist()
def my_api_method():
    pass

# Error handling
frappe.throw(_("User-facing error message"))
frappe.log_error("Internal error message")

# Translation markers
_("Translatable string")
```

### TypeScript (Frontend)

**Formatting**: ESLint + Prettier
- **Strict TypeScript mode** enabled
- **noUnusedLocals** and **noUnusedParameters** enabled
- **Path alias**: `@/*` maps to `./src/*`

**Patterns**:
```typescript
// Frappe SDK — all backend calls go through these
import { db, call, auth } from '@/lib/frappe-sdk';

// Service layer — named exports, not default exports
import { getAgents, createAgent } from '@/services/agentApi';

// Error handling — consistent across all services
import { handleFrappeError } from '@/lib/frappe-error';
try { ... } catch (e) { handleFrappeError(e); }

// Types in separate files
import type { Agent, AgentDoc } from '@/types/agent.types';

// DocType names from centralized constants
import { doctype } from '@/data/doctypes';
const agents = await db.getDocList(doctype.Agent, { ... });

// Pagination pattern — fetch limit+1 to detect hasMore
const data = await db.getDocList(doctype.Agent, { limit: pageSize + 1 });
const hasMore = data.length > pageSize;

// Tailwind class merging
import { cn } from '@/lib/utils';
<div className={cn("base-class", isActive && "active-class")} />

// Toast notifications
import { toast } from 'sonner';
toast.success("Agent created");
```

### EditorConfig Settings
- **All files**: LF line endings, UTF-8, final newline
- **Python/JS/CSS**: Tabs (4 spaces), 99 char limit
- **JSON**: Spaces (2), no final newline

## Core DocTypes

| DocType | Purpose |
|---------|---------|
| **AI Provider** | Stores credentials for AI services (OpenAI, Anthropic, Google, etc.) |
| **AI Model** | Specific model configuration linked to a provider |
| **Agent** | Main entity with instructions, tools, model, parameters |
| **Agent Tool Function** | Tool definitions (CRUD, HTTP, custom functions) |
| **Agent Trigger** | Event-driven execution rules (Doc Event, Schedule, Webhook) |
| **Agent Conversation** | Persistent chat session tracking |
| **Agent Message** | Individual messages in conversations |
| **Agent Run** | Execution log with status, response, token usage |
| **Agent Tool Call** | Detailed tool invocation logs |
| **Knowledge Source** | Knowledge base for RAG (SQLite FTS5 backend) |
| **Knowledge Input** | Individual content items (files, text, URLs) |
| **MCP Server** | Model Context Protocol server configuration |
| **Agent Settings** | Global application settings (singleton) |
| **Flow Definition** | Graph-based flow definition stored as JSON |
| **Flow Run** | Single execution instance of a flow |

## Key Backend Files

### Agent Execution Flow
1. **`agent_integration.py`**: `AgentManager` prepares agents, provides both sync and streaming execution:
   - `run_agent_sync()` - Synchronous execution, returns complete response (supports flow tagging via `flow_run_id`, `flow_node_id`, `run_kind`)
   - `run_agent_stream()` - Async generator yielding chunks for real-time streaming
2. **`agent_stream_renderer.py`**: SSE page renderer for `/huf/stream/<agent_name>` endpoint
3. **`run.py`**: `RunProvider` routes to appropriate LLM provider
4. **`providers/litellm.py`**: Unified provider handling via LiteLLM
5. **`sdk_tools.py`**: Converts `Agent Tool Function` DocTypes to SDK tools
6. **`tool_functions.py`**: Low-level Frappe database operations

### Flow Engine
1. **`flow_engine.py`**: Core engine - loads definitions, creates runs, executes nodes, evaluates edges
2. **`flow_api.py`**: Whitelisted REST APIs for flow management and execution
3. **`flow_eval.py`**: AST-based safe expression evaluator for edge conditions
4. **`flow_tool_executor.py`**: Deterministic tool execution reusing sdk_tools handlers
5. **`flow_orchestrator.py`**: Prompt construction and JSON parsing for router/orchestrator
6. **`flow_tools.py`**: Tool definitions registered via `huf_tools` hook

### Streaming Support
HUF supports Server-Sent Events (SSE) for real-time agent response streaming:
- **Endpoint**: `/huf/stream/<agent_name>?prompt=<message>`
- **Demo page**: `/huf/stream` (HTML test interface)
- **Chunk types**: `delta` (partial response), `tool_call`, `complete`, `error`

### Event-Driven Agents
- **`agent_hooks.py`**: Document event triggers (`after_insert`, `on_submit`, etc.)
- **`agent_scheduler.py`**: Scheduled agent execution

### Knowledge System
- **`knowledge/indexer.py`**: Ingestion pipeline with chunking
- **`knowledge/retriever.py`**: BM25-based search via SQLite FTS5
- **`knowledge/context_builder.py`**: Context assembly for prompts

## Frontend Architecture

### Routing and Navigation

The app uses React Router v7 with `basename="/huf"`. All routes are wrapped in `UserProvider` → `Suspense` → `ProtectedRoute`.

| Route | Page | Layout | Notes |
|-------|------|--------|-------|
| `/` | HomePage | UnifiedLayout | Dashboard with metrics, tabs for agents/flows/executions |
| `/agents` | AgentsPage | UnifiedLayout | Agent grid with search/filter, infinite scroll |
| `/agents/:id` | AgentFormPageWrapper | Breadcrumb layout | Agent create/edit form with tabbed sections |
| `/chat` | ChatPageV2 | UnifiedLayout (no header) | Chat UI with collapsible sidebar |
| `/chat/:chatId` | ChatPageV2 | UnifiedLayout (no header) | Chat with specific conversation |
| `/executions` | Executions | UnifiedLayout | Agent runs table with TanStack Table |
| `/executions/:runId` | AgentRunDetailPage | UnifiedLayout | Run details, child runs |
| `/flows` | FlowListPage | UnifiedLayout + FlowProvider | Flow grid |
| `/flows/:flowId` | FlowCanvasPageWrapper | FlowProvider + ModalProvider | Visual flow builder |
| `/providers` | IntegrationsPageWrapper | IntegrationsContext | AI provider management |
| `/mcp` | McpListingPage | UnifiedLayout | MCP server grid |
| `/mcp/:mcpId` | McpDetailsPageWrapper | Breadcrumb layout | MCP server form with tabs |
| `/data` | DataPage | UnifiedLayout | Placeholder (coming soon) |
| `/view/:messageId` | PreviewViewPage | Standalone | Full-screen message preview |

### Layout System

- **`UnifiedLayout`**: Main layout wrapping most pages. Provides `SidebarProvider` → `AppSidebar` + `SidebarInset` with optional header and breadcrumbs.
- **`UnifiedHeader`**: Renders breadcrumbs or auto-detected page title, plus slot for `headerActions`.
- **`AppSidebar`**: Collapsible sidebar with nav items (Dashboard, Agents, Chat, Executions, Flows, Data, AI Providers, MCP Servers). Shows chat list on mobile.
- **Page Wrapper pattern**: Detail pages use a `*Wrapper` component that adds `UnifiedLayout` with breadcrumbs, delegating content to the inner page component.

### Component Architecture

Components are organized by domain:

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `components/agent/` | Agent form tabs and triggers | `GeneralTab`, `BehaviorTab`, `TriggersTab`, `ToolsTab`, `AdvancedTab`, `TriggerModal` |
| `components/chat/` | Full chat system | `ChatWindowV2`, `ChatInput`, `ChatMessageList`, `ChatMessage`, `ChatListing`, `ChatSidebarContent`, `AgentModelSelector` |
| `components/ai-elements/` | AI-specific UI primitives | `message`, `code-block`, `tool`, `artifact`, `reasoning`, `chain-of-thought`, `prompt-input`, `suggestion` (30 components) |
| `components/dashboard/` | Reusable dashboard building blocks | `PageLayout`, `PageSection`, `FilterBar`, `GridView`, `ItemCard`, `BaseCard`, `LoadMoreButton` |
| `components/tools/` | Tool creation and management | `ToolFormModal`, `ToolCreationForm`, `SelectToolsModal`, `SelectMCPServersModal`, `ToolCard`, `ParameterCard` |
| `components/mcp/` | MCP server management | `DetailsTab`, `ConnectionTab`, `ToolsTab`, `MCPHeader`, `MCPToolDetailModal` |
| `components/nodes/` | Flow builder node components | `TriggerNode`, `ActionNode`, `EndNode` |
| `components/modals/` | Flow builder modals | `NodeSelectionModal`, `ActionSelectionModal`, `TriggerConfigModal` |
| `components/ui/` | shadcn/ui primitives | 54 Radix-based components (dialog, tabs, button, form, select, table, sidebar, etc.) |

Root-level components include `FlowCanvas`, `FlowNode`, `RightSidebar`, `ProtectedRoute`, `AppSidebar`, `UserAvatar`, and per-page header actions.

### Service Layer

All backend communication goes through service files in `src/services/`. Services use the Frappe JS SDK (`db`, `call`, `auth` from `@/lib/frappe-sdk`).

| Service | Purpose | Key Exports |
|---------|---------|-------------|
| `agentApi.ts` | Agent CRUD, triggers, DocTypes | `getAgents`, `getAgent`, `createAgent`, `updateAgent`, `runAgentTest`, `getAgentTriggers`, `createAgentTrigger` |
| `agentRunApi.ts` | Agent run queries | `getAgentRuns` (with pagination, search, status, agent filters) |
| `chatApi.ts` | Conversations and messages | `getConversations`, `getConversationMessages`, `newConversation`, `sendMessageToConversation`, `createAgentRunFeedback` |
| `streamChatApi.ts` | SSE streaming with REST fallback | `streamAgentResponse` (async generator), `sendMessage`, `checkStreamingAvailable` |
| `dashboardApi.ts` | Dashboard metrics | `getAgentRunsCountLast7Days`, `getAgentRunsForMetrics`, `getRecentAgentRuns` |
| `flowService.ts` | In-memory flow management | `flowService` singleton (Map-based CRUD, subscription pattern) |
| `mcpApi.ts` | MCP server management | `getMCPServers`, `createMCPServer`, `syncMCPTools`, `testMCPConnection` |
| `providerApi.ts` | AI provider/model CRUD | `getProviders`, `getProvider`, `createProvider`, `getModels` |
| `toolApi.ts` | Tool function management | `getToolFunctions`, `createToolFunction`, `updateToolFunction`, `fetchToolParametersFromCode` |
| `utilsApi.ts` | Generic helpers | `fetchDocCount` (via `frappe.client.get_count`) |
| `mockApi.ts` | Development mock data | `mockApi` with static providers, models, tools, agents |

**Common patterns across services:**
- Pagination uses `limit + 1` trick to detect `hasMore`, with `fetchDocCount` for totals
- All errors handled via `handleFrappeError` from `@/lib/frappe-error`
- DocType names referenced from `@/data/doctypes` constants
- Return types follow `PaginatedResponse<T>` interface

### State Management (Contexts)

| Context | Provider | Purpose |
|---------|----------|---------|
| `UserContext` | `UserProvider` | Authentication state, user info, login redirect. Uses `auth.getLoggedInUser()` and `db.getDoc`. |
| `FlowContext` | `FlowProvider` | Flow builder state. Subscribes to `flowService` for flows, active flow, selected node. |
| `ModalContext` | `ModalProvider` | Flow builder modal state (trigger/action config dialogs). |
| `IntegrationsContext` | `IntegrationsProvider` | Integrations page callback (`onAddProvider`). |

### Custom Hooks

| Hook | Purpose |
|------|---------|
| `useInfiniteScroll` | Pagination with Intersection Observer, debounced search/filters, forward/reverse direction |
| `useDebounce` | Generic value debouncing |
| `useChatSocket` | Socket.io subscription for real-time tool calls and new messages in a conversation |
| `useIsMobile` | Viewport detection (< 768px) via `matchMedia` |
| `usePageData` | Fetch + client-side search/filter for page data |

Chat-specific hooks live in `components/chat/`: `useChatList`, `useChatAgentIdentity`, `useChatScrollToBottom`.

### Type Definitions

| File | Key Types |
|------|-----------|
| `agent.types.ts` | `Agent`, `AgentDoc`, `AIProvider`, `AIModel`, `AgentToolFunctionRef`, `AgentTrigger`, `AgentConversation`, `AgentMessage`, `AgentRun` |
| `flow.types.ts` | `Flow`, `FlowNode`, `FlowEdge`, `FlowNodeData`, `FlowStatus`, trigger/action configs (extends React Flow types) |
| `artifact.types.ts` | `ArtifactType`, `ParsedArtifact`, `ParsedWebPreview`, `ParsedJSXPreview` |
| `pagination.ts` | `PaginationParams`, `PaginatedResponse<T>` |
| `modal.types.ts` | `TriggerOption`, `ActionOption` (for node selection modal) |
| `toolTemplate.types.ts` | `ToolTemplate`, `ToolFormData` |

### Static Data

The `src/data/` directory contains static configuration:
- `doctypes.ts` — Centralized DocType name constants used across all services
- `triggers.ts` — Trigger type options for the flow builder
- `actions.ts` — Action type options for the flow builder
- `color.ts` — Color palette constants
- `mcp.ts` — MCP-related static data

### Utilities

| File | Purpose |
|------|---------|
| `lib/frappe-sdk.ts` | Frappe JS SDK initialization (`frappe`, `auth`, `db`, `call`) |
| `lib/frappe-error.ts` | Frappe error parsing and handling (`handleFrappeError`, `getFrappeErrorMessage`) |
| `lib/utils.ts` | `cn()` — Tailwind class merging via `clsx` + `tailwind-merge` |
| `utils/socket.ts` | `createFrappeSocket` — Socket.io client for Frappe real-time events |
| `utils/artifactParser.ts` | Parses AI-generated artifacts from message content |
| `utils/jsxPreviewParser.ts` | Parses JSX preview blocks from messages |
| `utils/webPreviewParser.ts` | Parses web preview blocks from messages |
| `utils/formValidation.ts` | Form validation utilities |
| `utils/status.ts` | Status label/color mapping |
| `utils/time.ts` | Time formatting helpers |
| `utils/getInitials.ts` | User initials extraction |

## API Patterns

### Whitelisted Methods
```python
# Backend API call
@frappe.whitelist()
def run_agent_sync(agent_name, prompt, channel_id=None, external_id=None):
    ...
```

### Frontend API Calls
```typescript
// Using Frappe JS SDK
import { db, call } from '@/lib/frappe-sdk';

// DocType operations (via db)
const agents = await db.getDocList('Agent', {
    fields: ['name', 'agent_name', 'model'],
    filters: [['disabled', '=', 0]],
    limit: 20,
    orderBy: { field: 'modified', order: 'desc' },
});
const agent = await db.getDoc('Agent', agentName);

// RPC calls (via call)
const result = await call.post('huf.ai.agent_integration.run_agent_sync', {
    agent_name: 'my-agent',
    prompt: 'Hello'
});

// SSE streaming (via fetch + ReadableStream)
const response = await fetch(`/huf/stream/${agentName}?prompt=${encodeURIComponent(prompt)}`);
const reader = response.body.getReader();
// Parse SSE lines: data.type is 'delta' | 'tool_call' | 'complete' | 'error'
```

### Flow Engine API Calls
```python
# Start a flow
result = frappe.call('huf.ai.flow_api.run_flow', flow_id='my-flow', payload={'key': 'value'})

# Get flow run status
status = frappe.call('huf.ai.flow_api.get_flow_run', flow_run_id='FR-00001')

# Approve a waiting flow
frappe.call('huf.ai.flow_api.approve_flow_run', flow_run_id='FR-00001', comment='Looks good')

# Webhook trigger (external)
# POST /api/method/huf.ai.flow_api.flow_webhook?flow_id=my-flow&webhook_key=secret
```

## Security Considerations

1. **API Keys**: Stored using Frappe's encrypted `Password` field type
2. **SSRF Protection**: `http_handler.py` validates URLs to block private IPs
3. **Tool Permissions**: Custom functions run with the caller's permissions
4. **Input Validation**: Always validate inputs in custom tool functions
5. **Flow Expressions**: AST-based restricted evaluator prevents code injection in edge conditions
6. **Flow Router**: LLM routing decisions constrained to valid candidate edges

## Pre-commit Hooks

The project uses pre-commit hooks for code quality:
- **Ruff**: Import sorting, linting, formatting
- **Prettier**: JavaScript/Vue/SCSS formatting
- **ESLint**: JavaScript linting
- **YAML/JSON/TOML**: Syntax validation

Run hooks manually:
```bash
pre-commit run --all-files
```

## Testing

### Backend Tests
```bash
bench --site test_site run-tests --app huf
```

Test files are located in:
- `huf/huf/doctype/*/test_*.py`
- `huf/ai/knowledge/tests/`

### Frontend
- ESLint + TypeScript type checking
- No unit tests currently

## CI/CD Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to develop | Backend tests with Frappe environment |
| `linter.yml` | Pull requests | Pre-commit, Semgrep, pip-audit |
| `pages.yml` | Merge to main | Documentation deployment |

## Important Notes for AI Assistants

### Backend
1. **Frappe Patterns**: Always follow Frappe conventions (Documents, permissions, whitelisting)
2. **Tool Creation**: Tools must return JSON-serializable strings
3. **LiteLLM Dependency**: Required for LLM access, auto-installed via `bench setup requirements`
4. **Model Names**: Can be user-friendly (`gpt-4-turbo`) or LiteLLM format (`openai/gpt-4-turbo`)
5. **MCP Protocol**: HUF is an MCP client only (not a server)
6. **Streaming vs Sync**: Use `run_agent_stream()` for chat UIs, `run_agent_sync()` for triggers/automation
7. **Flow Engine**: Graph orchestration via JSON definitions; no separate Node/Edge doctypes; Agent Run serves as node-run log
8. **Flow Modes**: Normal (deterministic edges) vs Agentic (orchestrator-in-the-loop); both constrained to graph topology

### Frontend
9. **State Management**: Use React Context/hooks only — no Redux, Zustand, or other external state libraries
10. **API Layer**: All backend calls go through `src/services/` files using `db`/`call` from `@/lib/frappe-sdk` — never call Frappe APIs directly from components
11. **DocType Constants**: Always reference DocType names from `@/data/doctypes` — never use raw strings
12. **Error Handling**: Use `handleFrappeError` from `@/lib/frappe-error` in all service catch blocks
13. **UI Components**: Use existing shadcn/ui primitives from `components/ui/` — don't create custom low-level UI components
14. **Page Structure**: List pages use `PageLayout` + `FilterBar` + `GridView`/`ItemCard` from `components/dashboard/`. Detail pages use the `*Wrapper` + inner page pattern with breadcrumbs.
15. **Pagination**: Follow the `limit + 1` pattern with `PaginatedResponse<T>` — use `useInfiniteScroll` hook for infinite scroll pages
16. **Styling**: Use Tailwind classes with `cn()` for conditional merging — no CSS modules or styled-components
17. **Toasts**: Use `sonner` (`toast.success()`, `toast.error()`) — not native alerts or custom toast implementations
18. **Real-time**: Socket.io for live agent feedback (tool calls, new messages), SSE via fetch ReadableStream for streaming responses
19. **Routing**: All routes are under `/huf` basename — use React Router `Link` and `useNavigate` for navigation
20. **TypeScript Strictness**: The project enforces strict TypeScript settings. Always clean up and remove unused imports, variables, and functions to prevent build failures (e.g., TS6133).

### General
21. **Docker Dev**: Use `docker/` for quick evaluation; use Frappe bench for full development

## Related Documentation

- **AGENTS.md**: Detailed architecture documentation
- **KnowledgePlan.md**: Knowledge system architecture
- **docs/**: Full documentation site
- **README.md**: User-facing project documentation

---

## Development Environment

Huf runs inside a Frappe devcontainer. Full docs: `/Users/safwan/Code/Docker/frappe_docker/AGENTS.md`

| Key | Value |
| :-- | :---- |
| Container | `frappe_docker_devcontainer-frappe-1` |
| Bench (host) | `/Users/safwan/Code/Docker/frappe_docker/development/16` |
| Bench (container) | `/workspace/development/16` |
| Site | `huf.localhost` |
| Web port | `8000` (may vary — check `bench start` output) |
| API credentials | `HFL_API_KEY` / `HFL_API_SECRET` in `/Users/safwan/Code/Docker/frappe_docker/.env` |

### Run tests

```bash
# From host
docker exec -it frappe_docker_devcontainer-frappe-1 \
  bash -c "cd /workspace/development/16 && bench --site huf.localhost run-tests --app huf"

# Inside container
cd /workspace/development/16
bench --site huf.localhost migrate
bench --site huf.localhost run-tests --app huf
bench --site huf.localhost run-tests --app huf --module huf.ai.skills.tests
```

### REST API

```bash
source /Users/safwan/Code/Docker/frappe_docker/.env
curl -s http://huf.localhost:8000/api/method/frappe.auth.get_logged_user \
  -H "Authorization: token ${HFL_API_KEY}:${HFL_API_SECRET}"
```
