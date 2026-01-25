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
│   │   ├── agent_integration.py  # AgentManager, run_agent_sync
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
│   │   ├── agent_stream_renderer.py # SSE streaming
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
│   │   └── orchestration/        # Multi-step workflow planning
│   ├── huf/doctype/              # DocType definitions (33 total)
│   ├── hooks.py                  # Frappe integration hooks
│   ├── install.py                # Installation/migration hooks
│   ├── www/                      # Web routes
│   ├── public/                   # Static assets
│   └── templates/                # Jinja templates
├── frontend/                     # Frontend (React app)
│   └── src/
│       ├── pages/                # Page components
│       ├── components/           # UI components
│       │   ├── agent/            # Agent-specific components
│       │   ├── chat/             # Chat interface
│       │   ├── nodes/            # Flow builder nodes
│       │   ├── tools/            # Tool management
│       │   ├── mcp/              # MCP server UI
│       │   └── ui/               # shadcn/ui components
│       ├── contexts/             # React contexts (User, Flow, Modal)
│       ├── hooks/                # Custom React hooks
│       ├── services/             # API service layer
│       ├── types/                # TypeScript definitions
│       └── lib/                  # Utilities (Frappe SDK wrapper)
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
- **Styling**: Tailwind CSS 3.4.13
- **UI Components**: Radix UI (shadcn/ui)
- **Flow Builder**: React Flow / XYFlow
- **State Management**: React Context API
- **Forms**: React Hook Form + Zod

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

**Patterns**:
```typescript
// React Hooks
const [state, setState] = useState(initialValue);
useEffect(() => { /* side effects */ }, [dependencies]);

// API calls via service layer
import { agentApi } from '@/services/agentApi';
const response = await agentApi.getAgents();

// Error handling
import { handleFrappeError } from '@/lib/error';
try { ... } catch (e) { handleFrappeError(e); }

// Types in separate files
import type { Agent } from '@/types/agent.types';
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

## Key Backend Files

### Agent Execution Flow
1. **`agent_integration.py`**: `AgentManager` prepares agents, `run_agent_sync()` is the main API endpoint
2. **`run.py`**: `RunProvider` routes to appropriate LLM provider
3. **`providers/litellm.py`**: Unified provider handling via LiteLLM
4. **`sdk_tools.py`**: Converts `Agent Tool Function` DocTypes to SDK tools
5. **`tool_functions.py`**: Low-level Frappe database operations

### Event-Driven Agents
- **`agent_hooks.py`**: Document event triggers (`after_insert`, `on_submit`, etc.)
- **`agent_scheduler.py`**: Scheduled agent execution

### Knowledge System
- **`knowledge/indexer.py`**: Ingestion pipeline with chunking
- **`knowledge/retriever.py`**: BM25-based search via SQLite FTS5
- **`knowledge/context_builder.py`**: Context assembly for prompts

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
import { call } from '@/lib/frappe';
const result = await call.get('huf.ai.agent_integration.run_agent_sync', {
    agent_name: 'my-agent',
    prompt: 'Hello'
});
```

## Security Considerations

1. **API Keys**: Stored using Frappe's encrypted `Password` field type
2. **SSRF Protection**: `http_handler.py` validates URLs to block private IPs
3. **Tool Permissions**: Custom functions run with the caller's permissions
4. **Input Validation**: Always validate inputs in custom tool functions

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

1. **Frappe Patterns**: Always follow Frappe conventions (Documents, permissions, whitelisting)
2. **Tool Creation**: Tools must return JSON-serializable strings
3. **Frontend State**: Use React Context/hooks, not external state libraries
4. **LiteLLM Dependency**: Required for LLM access, auto-installed via `bench setup requirements`
5. **Model Names**: Can be user-friendly (`gpt-4-turbo`) or LiteLLM format (`openai/gpt-4-turbo`)
6. **MCP Protocol**: HUF is an MCP client only (not a server)
7. **Real-time Updates**: Socket.io for live agent feedback

## Related Documentation

- **AGENTS.md**: Detailed architecture documentation
- **KnowledgePlan.md**: Knowledge system architecture
- **docs/**: Full documentation site
- **README.md**: User-facing project documentation
