# AGENTS.md

This file provides context and instructions for AI coding agents to effectively work on the AgentFlo Frappe application.

## Project Overview
AgentFlo is a Frappe application for creating and managing conversational AI agents. It allows developers to define agents, equip them with tools to interact with the Frappe framework (e.g., CRUD operations on DocTypes), and manage conversation histories.

The application is built on the Frappe Framework (Python) and uses the standard Frappe directory structure. The core logic for agent integration is located in `agentflo/ai/`.

## Repo Layout
-   `agentflo/`: The root of the Frappe app.
-   `agentflo/agentflo/`: The main Python module.
-   `agentflo/agentflo/doctype/`: Contains all DocType definitions, each in its own folder.
    -   `<doctype_name>/<doctype_name>.json`: Schema definition.
    -   `<doctype_name>/<doctype_name>.py`: Server-side controller class.
    -   `<doctype_name>/<doctype_name>.js`: Client-side script.
-   `agentflo/ai/`: Core Python modules for AI agent integration.
-   `frontend/`: Modern React frontend application (React 18, TypeScript, Vite).
    -   `frontend/src/`: Source code for the frontend application.
    -   `frontend/src/components/`: Reusable React components.
    -   `frontend/src/pages/`: Page components (Agents, Flows, Data, etc.).
    -   `frontend/src/services/`: API service layer for Frappe integration.
    -   `frontend/src/hooks/`: Custom React hooks (infinite scroll, pagination, etc.).
-   `.github/workflows/`: CI definitions for tests and linting.

## Security Considerations
-   Do not commit secrets or API keys. The `AI Provider` DocType stores API keys in the database using the `Password` field type, which encrypts the value.
-   Custom functions exposed to agents via `Agent Tool Function` must be carefully designed. They are executed with the permissions of the user running the agent. Always validate inputs and perform permission checks inside custom tool functions.
-   **LiteLLM Dependency**: The `litellm` package (>=1.0.0) is required and listed in `pyproject.toml`. It will be automatically installed when running `bench setup requirements`. The post-install hook (`agentflo/install.py`) checks for LiteLLM and provides guidance if it's missing.

## Detailed Architecture

This section provides a deep dive into the application's structure, including DocTypes and core Python classes, to give the agent maximum context.

### Core Concepts

1.  **Provider & Model**: You start by defining an `AI Provider` (e.g., OpenAI, Anthropic, Google) and the `AI Model` you want to use (e.g., `gpt-4-turbo`, `claude-3-opus`). AgentFlo uses LiteLLM to provide unified access to 100+ LLM providers through a single interface.
2.  **Unified Provider Architecture**: All LLM providers are accessed via LiteLLM, which provides automatic model name normalization, built-in retry logic, cost tracking, and error handling. Model names can be specified in user-friendly format (e.g., `gpt-4-turbo`) and are automatically normalized to LiteLLM format (e.g., `openai/gpt-4-turbo`).
3.  **Tools**: Agents need tools to be useful. An `Agent Tool Function` defines a specific action the agent can perform, such as fetching a document, creating a new one, or calling a custom Python function.
4.  **Agent**: An `Agent` is the central entity. You give it a name, instructions (prompt), temperature, top_p, and assign it a set of tools. Each agent has its own individual settings that are read directly from the Agent DocType. Agents track execution statistics (`last_run`, `total_run`).
5.  **Agent Trigger**: A separate DocType that defines when and how agents are triggered. Supports multiple trigger types: Schedule, Doc Event, Webhook, App Event, and Manual. This replaces the old system where triggers were embedded directly in the Agent DocType.
6.  **Conversation**: When a user interacts with an agent, a `Agent Conversation` is created to track the entire interaction. Each message back-and-forth is stored as an `Agent Message`.
7.  **Execution**: A specific request to the agent and its subsequent actions are logged in an `Agent Run` with token usage and cost tracking.
8.  **Chat Interface**: `Agent Chat` provides a real-time chat UI for conversational agents with markdown rendering.
9.  **Frontend**: A modern React-based frontend provides a complete UI for managing agents, flows, and integrations. Built with React 18, TypeScript, Vite, and shadcn/ui components.

### Doctypes

Here is a detailed breakdown of the DocTypes used in AgentFlo.

#### 1. AI Provider

Stores credentials for different AI service providers. AgentFlo uses LiteLLM to provide unified access to 100+ LLM providers, including OpenAI, Anthropic, Google, OpenRouter, xAI (Grok), Mistral, and many more.

-   **Python Class**: `AIProvider(Document)`
-   **File**: `agentflo/agentflo/doctype/ai_provider/ai_provider.py`

**Fields:**

| Label          | Fieldname      | Type       | Description                               |
| :------------- | :------------- | :--------- | :---------------------------------------- |
| **Provide Name** | `provide_name` | Data       | The unique name of the provider (e.g., OpenAI, Anthropic, Google, OpenRouter). Provider names are case-insensitive and automatically routed to LiteLLM. |
| **API Key**    | `api_key`      | Password   | The API key for the provider. Stored securely using Frappe's Password field type.             |

**Supported Providers via LiteLLM:**
- OpenAI (OpenAI, OpenRouter with OpenAI models)
- Anthropic (Claude models)
- Google (Gemini models)
- OpenRouter (access to 500+ models)
- xAI (Grok models)
- Mistral
- And 100+ other providers supported by LiteLLM

For providers not in the standard list, you can use LiteLLM format in the model name (e.g., `xai/grok-4` for Grok, `mistral/mistral-large` for Mistral).

#### 2. AI Model

Defines a specific AI model available from a provider. Model names are automatically normalized to LiteLLM format, so you can use user-friendly names (e.g., `gpt-4-turbo`) or LiteLLM format (e.g., `openai/gpt-4-turbo`).

-   **Python Class**: `AIModel(Document)`
-   **File**: `agentflo/agentflo/doctype/ai_model/ai_model.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Model Name** | `model_name` | Data | The name of the model (e.g., `gpt-4-turbo`, `claude-3-opus`, `gpt-5-mini`). Can be specified in user-friendly format - the system automatically adds provider prefix. Alternatively, use LiteLLM format (e.g., `openai/gpt-4-turbo`) for explicit provider specification. |
| **Provider**   | `provider`   | Link | A link to the `AI Provider` DocType. The provider name is used to determine the provider prefix for model normalization.      |

**Model Name Normalization:**
- User-friendly names: `gpt-4-turbo` → automatically normalized to `openai/gpt-4-turbo`
- Provider prefix mapping: `gemini` → `google`, `grok` → `xai`
- LiteLLM format: `openai/gpt-4-turbo` → used as-is (no normalization needed)

#### 3. Agent Tool Function

Defines a function or "tool" that an agent can use. This is the core of the agent's capabilities.

-   **Python Class**: `AgentToolFunction(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_tool_function/agent_tool_function.py`

**Fields:**

| Label                   | Fieldname                 | Type    | Description                                                                                             |
| :---------------------- | :------------------------ | :------ | :------------------------------------------------------------------------------------------------------ |
| **Tool Name**           | `tool_name`               | Data    | A unique name for the tool.                                                                             |
| **Description**         | `description`             | Small Text | A clear description of what the tool does. This is crucial as the AI uses it to decide when to use the tool. |
| **Types**               | `types`                   | Select  | The type of function (e.g., `Get Document`, `Create Document`, `Custom Function`). This determines the underlying logic. |
| **Reference DocType**   | `reference_doctype`       | Link    | For DocType-related functions, this specifies the target DocType (e.g., `Sales Order`).                 |
| **Function Path**       | `function_path`           | Data    | The dotted path to the Python function for `Custom Function` types (e.g., `my_app.api.my_function`).    |
| **Parameters**          | `parameters`              | Table   | A table of parameters (`Agent Function Params`) the function accepts.                                   |
| **Function Definition** | `function_definition`     | JSON    | (Read Only) The final JSON schema of the function, which is passed to the AI.                           |

#### 4. Agent Tool Type

Defines categories or types for agent tool functions. Used for organizing and categorizing tools.

-   **Python Class**: `AgentToolType(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_tool_type/agent_tool_type.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Name**     | `name1`      | Data | The name of the tool type (e.g., `CRUD`, `Custom`, `Integration`). |

**Note**: This DocType provides a way to categorize agent tools for better organization in the UI.

#### 5. Agent

The main DocType for creating an AI agent.

-   **Python Class**: `Agent(Document)`
-   **File**: `agentflo/agentflo/doctype/agent/agent.py`

**Fields:**

| Label          | Fieldname      | Type      | Description                                                                                             |
| :------------- | :------------- | :-------- | :------------------------------------------------------------------------------------------------------ |
| **Agent Name**   | `agent_name`   | Data      | A unique name for the agent.                                                                            |
| **Provider**     | `provider`     | Link      | Link to the `AI Provider`.                                                                              |
| **Model**        | `model`        | Link      | Link to the `AI Model`.                                                                                 |
| **Instructions** | `instructions` | Code      | The system prompt or instructions that define the agent's personality, goals, and constraints.          |
| **Agent Tool**   | `agent_tool`   | Table     | A child table (`Agent Tool`) linking to the `Agent Tool Function`s that this agent is allowed to use. |
| **Temperature**  | `temperature`  | Float     | Controls the randomness of the AI's output.                                                             |
| **Top P**        | `top_p`        | Float     | An alternative to temperature for controlling randomness.                                               |
| **Allow Chat**    | `allow_chat`   | Check     | Enables the Agent Chat interface for real-time conversations.                                           |
| **Persist Conversation** | `persist_conversation` | Check | Whether to maintain conversation history across runs. |
| **Description**   | `description`  | Small Text | A brief description of the agent's purpose. |
| **Last Run**      | `last_run`     | Datetime  | Timestamp of the last agent execution (read-only, auto-updated). |
| **Total Run**     | `total_run`    | Int       | Total number of times this agent has been executed (read-only, auto-incremented). |

**Note**: The `condition` field has been removed from Agent DocType. Conditional triggering is now handled via the `Agent Trigger` DocType.

#### 6. Agent Trigger

Defines when and how an agent should be triggered. This is a separate DocType that replaced the old embedded trigger system in the Agent DocType.

-   **Python Class**: `AgentTrigger(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_trigger/agent_trigger.py`

**Fields:**

| Label                | Fieldname           | Type      | Description                                                                                             |
| :------------------- | :------------------- | :-------- | :------------------------------------------------------------------------------------------------------ |
| **Trigger Name**     | `trigger_name`       | Data      | A unique name for the trigger.                                                                          |
| **Agent**            | `agent`              | Link      | Link to the `Agent` that should be triggered.                                                           |
| **Trigger Type**     | `trigger_type`       | Select    | Type of trigger: `Schedule`, `Doc Event`, `Webhook`, `App Event`, or `Manual`.                         |
| **Status**           | `status`             | Select    | Current status: `Draft`, `Active`, `Disabled`, `Error`.                                                |
| **Disabled**         | `disabled`           | Check     | Whether the trigger is disabled.                                                                        |
| **Scheduled Interval** | `scheduled_interval` | Select    | For Schedule triggers: `Hourly`, `Daily`, `Weekly`, `Monthly`, `Yearly`.                                |
| **Interval Count**   | `interval_count`     | Int       | For Schedule triggers: Number of intervals between executions.                                         |
| **Next Execution**   | `next_execution`     | Datetime  | For Schedule triggers: When the trigger will next execute (read-only, auto-calculated).                |
| **Last Execution**   | `last_execution`     | Datetime  | For Schedule triggers: When the trigger last executed (read-only, auto-updated).                      |
| **Reference DocType** | `reference_doctype`  | Link      | For Doc Event triggers: The DocType to monitor.                                                         |
| **Doc Event**        | `doc_event`          | Select    | For Doc Event triggers: Event to listen for (e.g., `after_insert`, `on_submit`, `before_save`).       |
| **Condition**        | `condition`          | Code      | For Doc Event triggers: Python expression to evaluate before triggering (e.g., `doc.grand_total > 10000`). |
| **Webhook Key**      | `webhook_key`        | Data      | For Webhook triggers: Authentication key for the webhook.                                               |
| **Webhook Slug**     | `webhook_slug`       | Data      | For Webhook triggers: URL slug for the webhook endpoint.                                               |
| **App Name**         | `app_name`           | Data      | For App Event triggers: Name of the app emitting the event.                                            |
| **Event Name**       | `event_name`         | Data      | For App Event triggers: Name of the event to listen for.                                               |
| **Metadata**         | `metadata`           | JSON      | Additional metadata for the trigger.                                                                    |
| **Disabled Reason**  | `disabled_reason`    | Small Text | Reason why the trigger was disabled (if applicable).                                                  |

**Trigger Types:**
-   **Schedule**: Executes agents on a recurring schedule (hourly, daily, weekly, monthly, yearly).
-   **Doc Event**: Triggers agents when specific document events occur (e.g., after_insert, on_submit).
-   **Webhook**: Triggers agents via HTTP webhook calls.
-   **App Event**: Triggers agents when custom app events are emitted.
-   **Manual**: Triggers agents manually via API or UI.

**Architecture Notes:**
-   Triggers are managed separately from agents, allowing multiple triggers per agent.
-   Doc Event triggers are cached for performance (`agent_hooks.py`).
-   Scheduled triggers are executed by a background job (`agent_scheduler.py`).
-   The frontend provides a dedicated UI for managing triggers in the Agent form.

#### 7. Agent Conversation

Tracks a continuous conversation with an agent.

-   **Python Class**: `AgentConversation(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_conversation/agent_conversation.py`

**Fields:**

| Label            | Fieldname        | Type     | Description                                                              |
| :--------------- | :--------------- | :------- | :----------------------------------------------------------------------- |
| **Title**        | `title`          | Data     | The title of the conversation.                                           |
| **Agent**        | `agent`          | Link     | Link to the `Agent` used in this conversation.                           |
| **Session ID**   | `session_id`     | Data     | A unique ID for the session, typically combining channel and user ID.    |
| **Is Active**    | `is_active`      | Check    | Indicates if the conversation is ongoing.                                |
| **Total Messages** | `total_messages` | Int      | The total number of messages exchanged.                                  |

#### 8. Agent Message

Represents a single message within a conversation.

-   **Python Class**: `AgentMessage(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_message/agent_message.py`

**Fields:**

| Label          | Fieldname      | Type      | Description                                                              |
| :------------- | :------------- | :-------- | :----------------------------------------------------------------------- |
| **Conversation** | `conversation` | Link      | Link to the parent `Agent Conversation`.                                 |
| **Role**         | `role`         | Select    | The role of the message sender (`user`, `agent`, or `system`).           |
| **Content**      | `content`      | Long Text | The text content of the message.                                         |
| **Kind**         | `kind`         | Select    | The type of message (`Message`, `Tool Call`, `Tool Result`, `Error`).    |
| **Run**          | `run`          | Link      | Link to the `Agent Run` that generated this message.                     |

#### 9. Agent Run

Logs a single, complete execution cycle of an agent in response to a user prompt.

-   **Python Class**: `AgentRun(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_run/agent_run.py`

**Fields:**

| Label          | Fieldname       | Type       | Description                                                              |
| :------------- | :-------------- | :--------- | :----------------------------------------------------------------------- |
| **Conversation** | `conversation`  | Link       | Link to the `Agent Conversation`.                                        |
| **Agent**        | `agent`         | Link       | Link to the `Agent` that was run.                                        |
| **Prompt**       | `prompt`        | Small Text | The user prompt that initiated the run.                                  |
| **Response**     | `response`      | Small Text | The final response from the agent.                                       |
| **Status**       | `status`        | Select     | The status of the run (`Started`, `Queued`, `Success`, `Failed`).        |
| **Error Message**| `error_message` | Small Text | Any error message if the run failed.                                     |
| **Input Tokens** | `input_tokens`  | Int        | Number of tokens in the input (prompt + context).                        |
| **Output Tokens**| `output_tokens` | Int        | Number of tokens in the output (response).                               |
| **Total Tokens** | `total_tokens`  | Int        | Total tokens used (input + output).                                      |
| **Total Cost**   | `total_cost`    | Currency   | Total cost of the agent run based on token usage.                        |

#### 10. Agent Chat

A single DocType providing a real-time chat interface for conversational agents.

-   **Python Class**: `AgentChat(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_chat/agent_chat.py`

**Features:**
-   Real-time chat UI with markdown rendering
-   Message history display
-   Only available for agents with `enable_chat` enabled
-   Server Actions: `agentflo.ai.agent_chat.get_agent_chat_messages`, `agentflo.ai.agent_chat.send_agent_chat_message`

### Core Classes and Methods

The primary logic is located in the `agentflo/ai` directory.

#### `agent_integration.py`

This file contains the main logic for creating and running agents.

-   **Class: `AgentManager`**
    -   This class is responsible for preparing an agent for execution.
    -   `__init__(self, agent_name, ...)`: Initializes the manager by loading the `Agent` DocType, the `AI Provider` settings, and setting up the tools.
    -   `_setup_tools(self)`: Dynamically creates and loads the toolset for the agent. It combines built-in CRUD tools with custom tools defined in `Agent Tool Function`.
    -   `create_agent(self)`: Constructs an `Agent` object from the `agents` SDK, passing the instructions, model, tools, and model_settings (temperature, top_p) from the Agent DocType.
-   **Method: `run_agent_sync(...)`**
    -   This is the main whitelisted Frappe API endpoint for running an agent.
    -   It orchestrates the entire process:
        1.  Initializes `ConversationManager` to handle the conversation history.
        2.  Creates or retrieves the `Agent Conversation` document.
        3.  Adds the user's new message to the conversation.
        4.  Creates an `Agent Run` document to log the execution.
        5.  Initializes `AgentManager` to prepare the agent.
        6.  Creates context dictionary with `agent_name` (required for LiteLLM provider to access Agent DocType settings).
        7.  Calls `RunProvider.run()` which routes to the appropriate provider (LiteLLM for most providers).
        8.  Adds the agent's final response to the conversation.
        9.  Updates the `Agent Run` status to `Success` or `Failed`.

#### `conversation_manager.py`

This file handles the persistence of conversation history.

-   **Class: `ConversationManager`**
    -   `get_or_create_conversation(self, ...)`: Finds the active `Agent Conversation` for a given session or creates a new one.
    -   `add_message(self, ...)`: Creates a new `Agent Message` document and links it to the current conversation.
    -   `get_conversation_history(self, ...)`: Fetches the last N messages from the conversation to provide context to the AI.
    -   `persist_conversation(self, ...)`: Saves conversation state and ensures database commits for real-time updates.

#### `sdk_tools.py`

This file acts as a bridge between AgentFlo's `Agent Tool Function` DocType and the `agents` SDK's `FunctionTool` class.

-   **Method: `create_agent_tools(agent)`**
    -   Iterates through the tools linked to an `Agent` and uses `create_function_tool` to build them.
-   **Method: `create_function_tool(...)`**
    -   The factory that constructs an SDK-compatible `FunctionTool`.
    -   It dynamically creates an `on_invoke_tool` async handler that calls the appropriate Python function when the AI decides to use a tool.
-   **Method: `handle_get_list`, `handle_create_document`, etc.**
    -   These are the actual functions that get executed when a standard DocType tool is called. They contain the logic to interact with the Frappe database (e.g., `frappe.get_list`, `frappe.get_doc`) and format the response in a way the AI can understand.

#### `tool_functions.py`

This file contains the low-level functions that directly perform Frappe database operations.

-   **Methods**: `get_document`, `create_document`, `update_document`, `delete_document`, `submit_document`, `get_list`, etc.
-   These functions are the final step in the tool-use chain, wrapping `frappe.client` or `frappe.get_doc` calls to ensure data is fetched, created, or modified correctly and with proper permissions checks.

#### `run.py`

This file provides the central routing layer for AI providers.

-   **Class: `RunProvider`**
    -   Central routing layer that directs provider requests to the appropriate implementation.
    -   `run(agent, enhanced_prompt, provider, model, context=None)`: Routes provider requests to LiteLLM for supported providers (OpenAI, Anthropic, Google, Gemini, OpenRouter).
    -   **Provider Routing**: Automatically routes standard providers to LiteLLM unified provider.
    -   **Fallback Mechanism**: For unsupported providers, attempts to load custom provider modules.
    -   **Error Handling**: Provides helpful error messages if LiteLLM is not installed or if provider is not found.

#### `providers/litellm.py`

This file implements the unified LiteLLM provider that handles all LLM interactions.

-   **Function: `run(agent, enhanced_prompt, provider, model, context=None)`**
    -   Main async function that handles LLM interactions via LiteLLM.
    -   **Agent Settings Access**: Reads temperature and top_p directly from Agent DocType (priority 1), falls back to `agent.model_settings` (priority 2), or uses defaults.
    -   **Model Normalization**: Automatically normalizes model names to LiteLLM format (e.g., `gpt-4-turbo` → `openai/gpt-4-turbo`).
    -   **Multi-turn Tool Calling**: Supports multiple rounds of tool calling in a single agent run.
    -   **Error Handling**: Specific handling for `InternalServerError`, `RateLimitError`, and general `APIError`.
    -   **Parameter Handling**: Automatically drops unsupported parameters for models with restrictions (e.g., gpt-5 models only support temperature=1).
    -   **API Key Management**: Handles API key setup for different providers, including special handling for OpenRouter (requires environment variable).
-   **Function: `_normalize_model_name(model, provider)`**
    -   Normalizes model names to LiteLLM format by adding provider prefix.
    -   Handles provider aliases (e.g., `gemini` → `google`, `grok` → `xai`).
    -   Supports both user-friendly names and LiteLLM format names.
-   **Function: `_setup_api_key(provider_name, api_key, completion_kwargs)`**
    -   Sets up API key for LiteLLM completion call.
    -   Handles special cases like OpenRouter (requires `OPENROUTER_API_KEY` environment variable).
-   **Function: `_execute_tool_call(tool, args_json)`**
    -   Executes a tool call and returns the result.
-   **Function: `_find_tool(agent, tool_name)`**
    -   Finds a tool by name in the agent's tools list.

#### `agent_chat.py`

This file provides the backend API for the Agent Chat interface.

-   **Method: `get_agent_chat_messages(...)` (Whitelisted)**
    -   Retrieves message history for the chat UI.
    -   Returns formatted messages with role, content, and timestamps.
-   **Method: `send_agent_chat_message(...)` (Whitelisted)**
    -   Processes user input from the chat interface.
    -   Calls the agent and returns the response.
    -   Manages chat-specific conversation persistence and message formatting.

#### `agent_hooks.py`

This file handles document event-based agent triggering.

-   **Function: `get_doc_event_agents(event: str)`**
    -   Fetches and caches Doc Event triggers from the `Agent Trigger` DocType.
    -   Returns a list of agent configurations that should be triggered for a given document event.
    -   Uses caching (`agentflo:doc_event_agents`) for performance.
-   **Function: `clear_doc_event_agents_cache(...)`**
    -   Clears the cache when Agent or Agent Trigger documents are modified.
-   **Function: `trigger_agent_on_doc_event(doc, method)`**
    -   Called by Frappe document hooks (e.g., `after_insert`, `on_submit`).
    -   Evaluates trigger conditions and executes matching agents.
    -   Supports conditional execution via Python expressions.

#### `agent_scheduler.py`

This file handles scheduled agent execution.

-   **Function: `run_scheduled_agents()` (Whitelisted)**
    -   Executes agents that are scheduled to run based on their `Agent Trigger` configurations.
    -   Queries `Agent Trigger` DocType for triggers with `trigger_type="Schedule"` and `next_execution <= now`.
    -   Updates `last_execution` and calculates `next_execution` after each run.
    -   Should be called periodically (e.g., via cron job or Frappe scheduler).

## Frontend Architecture

AgentFlo includes a modern React-based frontend application located in the `frontend/` directory. The frontend provides a complete UI for managing agents, workflows, and integrations.

### Technology Stack

-   **Framework**: React 18 with TypeScript
-   **Build Tool**: Vite
-   **UI Library**: shadcn/ui (60+ components)
-   **Styling**: Tailwind CSS
-   **Routing**: React Router
-   **State Management**: React Context API + Custom Hooks
-   **Forms**: React Hook Form + Zod
-   **Flow Builder**: React Flow
-   **Icons**: Lucide React (1000+ icons)

### Frontend Structure

```
frontend/src/
├── components/
│   ├── dashboard/         # Reusable dashboard framework components
│   │   ├── layouts/       # PageLayout, PageSection
│   │   ├── views/         # GridView, ListView
│   │   ├── cards/         # BaseCard, StatCard, ItemCard
│   │   └── filters/        # FilterBar
│   ├── ui/                # shadcn/ui components (60+)
│   ├── agent/             # Agent-specific components
│   │   ├── AgentHeader.tsx
│   │   ├── GeneralTab.tsx
│   │   ├── BehaviorTab.tsx
│   │   ├── ToolsTab.tsx
│   │   ├── TriggersTab.tsx
│   │   └── TriggerModal.tsx
│   ├── nodes/             # Flow builder nodes
│   ├── modals/            # Configuration modals
│   └── ...
├── pages/
│   ├── HomePage.tsx       # Dashboard overview
│   ├── AgentsPage.tsx     # Agent list with pagination
│   ├── AgentFormPage.tsx  # Agent creation/editing
│   ├── FlowListPage.tsx   # Flow list
│   ├── FlowCanvasPage.tsx # Flow builder canvas
│   ├── DataPage.tsx       # Data management
│   └── IntegrationsPage.tsx
├── services/              # API service layer
│   ├── agentApi.ts        # Agent CRUD operations
│   ├── flowService.ts     # Flow operations
│   ├── toolApi.ts         # Tool operations
│   └── providerApi.ts     # Provider operations
├── hooks/
│   ├── useInfiniteScroll.ts  # Infinite scroll pagination
│   ├── usePageData.ts        # Dashboard data management
│   └── ...
├── contexts/              # React contexts
│   ├── UserContext.tsx
│   ├── FlowContext.tsx
│   └── ModalContext.tsx
├── types/                 # TypeScript type definitions
│   ├── agent.types.ts
│   ├── flow.types.ts
│   └── ...
└── lib/
    ├── frappe-sdk.ts      # Frappe JS SDK wrapper
    └── frappe-error.ts    # Error handling utilities
```

### Key Frontend Features

#### Dashboard Framework

The frontend includes a reusable dashboard framework that significantly reduces code duplication:

-   **PageLayout**: Provides consistent page structure with filters and actions
-   **GridView**: Responsive grid layout with customizable columns
-   **ItemCard**: Standardized card component for displaying entities
-   **FilterBar**: Search and filter controls
-   **usePageData**: Hook for managing paginated data with search/filter

**Example Usage:**
```tsx
import { PageLayout, GridView, ItemCard } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';

export function AgentsPage() {
  const { items, hasMore, loadMore } = useInfiniteScroll({
    fetchFn: getAgents,
    pageSize: 20,
  });

  return (
    <PageLayout subtitle="Manage your AI agents">
      <GridView
        items={items}
        columns={{ sm: 1, md: 2, lg: 3 }}
        renderItem={(agent) => <ItemCard title={agent.agent_name} />}
      />
    </PageLayout>
  );
}
```

#### Agent Management UI

The frontend provides a comprehensive UI for managing agents:

-   **AgentsPage**: List view with search, filters, and pagination
-   **AgentFormPage**: Multi-tab form for creating/editing agents
    -   General Tab: Basic agent configuration
    -   Behavior Tab: Conversation settings
    -   Tools Tab: Tool assignment
    -   Triggers Tab: Trigger management (Schedule, Doc Event, Webhook, etc.)
-   **TriggerModal**: Modal for creating/editing agent triggers
-   **TriggerFieldsRenderer**: Dynamic form fields based on trigger type

#### Flow Builder

The frontend includes a visual flow builder powered by React Flow:

-   **FlowCanvas**: Main canvas component
-   **FlowNode**: Base node component
-   **TriggerNode, ActionNode, EndNode**: Specific node types
-   **NodeSelectionModal**: Modal for selecting node types
-   **TriggerConfigModal**: Modal for configuring trigger nodes

#### API Integration

The frontend uses the Frappe JS SDK (`frappe-sdk.ts`) to interact with the backend:

-   **agentApi.ts**: CRUD operations for agents and triggers
    -   `getAgents()`: Paginated agent listing with search/filter
    -   `getAgent()`: Fetch single agent
    -   `createAgent()`, `updateAgent()`: Agent CRUD
    -   `getAgentTriggers()`: List triggers for an agent
    -   `createAgentTrigger()`, `updateAgentTrigger()`: Trigger CRUD
    -   `getTriggerTypes()`: Fetch available trigger types
-   **flowService.ts**: Flow operations
-   **toolApi.ts**: Tool operations
-   **providerApi.ts**: Provider operations

### Frontend Development

**Setup:**
```bash
cd frontend
npm install
npm run dev
```

**Build:**
```bash
npm run build
```

**Key Scripts:**
-   `npm run dev`: Start development server
-   `npm run build`: Build for production
-   `npm run preview`: Preview production build
-   `npm run lint`: Lint code
-   `npm run typecheck`: Type check

### Frontend Documentation

Additional frontend documentation is available in `frontend/docs/`:

-   **CONTRIBUTE.md**: Contributing guide and UI framework usage
-   **QUICK_START.md**: Quick reference for framework components
-   **DASHBOARD_FRAMEWORK.md**: Detailed framework documentation
-   **FEATURES.md**: Flow builder features
-   **ARCHITECTURE.md**: System architecture

## Recent Changes

### Agent Trigger System Migration

The trigger system was refactored to use a separate `Agent Trigger` DocType:

-   **Removed**: Direct trigger configuration from Agent DocType (`condition` field removed)
-   **Added**: `Agent Trigger` DocType with support for multiple trigger types
-   **Benefits**: Multiple triggers per agent, better organization, cleaner separation of concerns
-   **Frontend**: New TriggersTab component for managing triggers in the agent form

### Frontend Addition

A complete React frontend was added:

-   Modern React 18 + TypeScript + Vite setup
-   Dashboard framework for rapid page development
-   Flow builder with React Flow
-   Comprehensive agent management UI
-   60+ shadcn/ui components
-   Infinite scroll and pagination support

### Agent Statistics Tracking

Agent DocType now tracks execution statistics:

-   `last_run`: Timestamp of last execution
-   `total_run`: Total execution count
-   Auto-updated by the agent execution system