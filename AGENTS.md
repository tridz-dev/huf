# AGENTS.md

This file provides context and instructions for AI coding agents to effectively work on the Huf Frappe application.

## Project Overview
Huf is a comprehensive Frappe application for creating and managing conversational AI agents with advanced workflow automation capabilities. It allows developers to define agents, equip them with tools to interact with the Frappe framework (e.g., CRUD operations on DocTypes), manage conversation histories, and build complex visual workflows.

The application is built on the Frappe Framework (Python) and uses the standard Frappe directory structure. The core logic for agent integration is located in `huf/ai/`, with a modern React-based frontend providing visual flow building and real-time streaming capabilities.

## Repo Layout
-   `huf/`: The root of the Frappe app.
-   `huf/huf/`: The main Python module.
-   `huf/huf/doctype/`: Contains all DocType definitions, each in its own folder.
    -   `<doctype_name>/<doctype_name>.json`: Schema definition.
    -   `<doctype_name>/<doctype_name>.py`: Server-side controller class.
    -   `<doctype_name>/<doctype_name>.js`: Client-side script.
-   `huf/ai/`: Core Python modules for AI agent integration.
-   `frontend/`: Modern React-based frontend application.
    -   `frontend/src/components/`: React components for UI, flow builder, and agent interactions.
    -   `frontend/src/contexts/`: React context providers for state management.
    -   `frontend/src/services/`: Frontend services for API communication and flow management.
    -   `frontend/src/types/`: TypeScript type definitions.
    -   `frontend/src/pages/`: Page components for different application views.
-   `.github/workflows/`: CI definitions for tests and linting.

## Security Considerations
-   Do not commit secrets or API keys. The `AI Provider` DocType stores API keys in the database using the `Password` field type, which encrypts the value.
-   Custom functions exposed to agents via `Agent Tool Function` must be carefully designed. They are executed with the permissions of the user running the agent. Always validate inputs and perform permission checks inside custom tool functions.
-   **LiteLLM Dependency**: The `litellm` package (>=1.0.0) is required and listed in `pyproject.toml`. It will be automatically installed when running `bench setup requirements`. The post-install hook (`huf/install.py`) checks for LiteLLM and provides guidance if it's missing.

## Detailed Architecture

This section provides a deep dive into the application's structure, including DocTypes and core Python classes, to give the agent maximum context.

### Core Concepts

1.  **Provider & Model**: You start by defining an `AI Provider` (e.g., OpenAI, Anthropic, Google) and the `AI Model` you want to use (e.g., `gpt-4-turbo`, `claude-3-opus`). Huf uses LiteLLM to provide unified access to 100+ LLM providers through a single interface.
2.  **Unified Provider Architecture**: All LLM providers are accessed via LiteLLM, which provides automatic model name normalization, built-in retry logic, cost tracking, and error handling. Model names can be specified in user-friendly format (e.g., `gpt-4-turbo`) and are automatically normalized to LiteLLM format (e.g., `openai/gpt-4-turbo`).
3.  **Tools**: Agents need tools to be useful. An `Agent Tool Function` defines a specific action the agent can perform, such as fetching a document, creating a new one, or calling a custom Python function.
4.  **Agent**: An `Agent` is the central entity. You give it a name, instructions (prompt), temperature, top_p, and assign it a set of tools. Each agent has its own individual settings that are read directly from the Agent DocType. Agents can be configured for scheduling, doc events, or chat.
5.  **Conversation**: When a user interacts with an agent, a `Agent Conversation` is created to track the entire interaction. Each message back-and-forth is stored as an `Agent Message`.
6.  **Execution**: A specific request to the agent and its subsequent actions are logged in an `Agent Run` with token usage and cost tracking.
7.  **Chat Interface**: `Agent Chat` provides a real-time chat UI for conversational agents with markdown rendering.

### Doctypes

Here is a detailed breakdown of the DocTypes used in Huf.

#### 1. AI Provider

Stores credentials for different AI service providers. Huf uses LiteLLM to provide unified access to 100+ LLM providers, including OpenAI, Anthropic, Google, OpenRouter, xAI (Grok), Mistral, and many more.

-   **Python Class**: `AIProvider(Document)`
-   **File**: `huf/huf/doctype/ai_provider/ai_provider.py`

**Fields:**

| Label          | Fieldname      | Type       | Description                               |
| :------------- | :------------- | :--------- | :---------------------------------------- |
| **Provide Name** | `provide_name` | Data       | The unique name of the provider (e.g., OpenAI, Anthropic, Google, OpenRouter). Provider names are case-insensitive and automatically routed to LiteLLM. **Note**: The field name uses "provide_name" (with "provide" instead of "provider") due to existing database schema; this is intentional for backward compatibility. |
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
-   **File**: `huf/huf/doctype/ai_model/ai_model.py`

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
-   **File**: `huf/huf/doctype/agent_tool_function/agent_tool_function.py`

**Fields:**

| Label                   | Fieldname                 | Type    | Description                                                                                             |
| :---------------------- | :------------------------ | :------ | :------------------------------------------------------------------------------------------------------ |
| **Tool Name**           | `tool_name`               | Data    | A unique name for the tool.                                                                             |
| **Description**         | `description`             | Small Text | A clear description of what the tool does. This is crucial as the AI uses it to decide when to use the tool. |
| **Types**               | `types`                   | Select  | The type of function. This determines the underlying logic. Available types: `Get Document`, `Get Multiple Documents`, `Get List`, `Create Document`, `Create Multiple Documents`, `Update Document`, `Update Multiple Documents`, `Delete Document`, `Delete Multiple Documents`, `Submit Document`, `Cancel Document`, `Get Amended Document`, `Custom Function`, `App Provided`, `Attach File to Document`, `Get Report Result`, `Get Value`, `Set Value`, `GET`, `POST`, `Run Agent`, `Speech to Text`. |
| **Reference DocType**   | `reference_doctype`       | Link    | For DocType-related functions, this specifies the target DocType (e.g., `Sales Order`).                 |
| **Function Path**       | `function_path`           | Data    | The dotted path to the Python function for `Custom Function` types (e.g., `my_app.api.my_function`).    |
| **Parameters**          | `parameters`              | Table   | A table of parameters (`Agent Function Params`) the function accepts.                                   |
| **Function Definition** | `function_definition`     | JSON    | (Read Only) The final JSON schema of the function, which is passed to the AI.                           |
| **Base URL**           | `base_url`               | Data    | Optional base URL that will be prefixed to URL provided by agent (for GET/POST types).              |
| **HTTP Headers**       | `http_headers`            | Table   | Custom HTTP headers for API requests (child table of `Agent Tool HTTP Header`).                        |
| **Agent**             | `agent`                  | Link    | Target agent to run (for `Run Agent` type).                                                         |
| **Provider App**       | `provider_app`             | Data    | App that provides this tool (for `App Provided` type).                                                |
| **Pass Parameters as JSON** | `pass_parameters_as_json` | Check | Whether to pass parameters as JSON string (for `Custom Function` type).                              |
<<<<<<< HEAD
| **Tool Type**         | `tool_type`              | Link    | Link to `Agent Tool Type` for categorization. **Required field.**                                   |
=======
| **Tool Type**         | `tool_type`              | Link    | Link to `Agent Tool Type` for categorization.                                                        |
>>>>>>> c26b627 (docs: Update Agent Tool Function documentation with new tool types (GET/POST, Run Agent, Speech to Text, App Provided, Attach File, Get Report, Get/Set Value))

#### 4. Agent

The main DocType for creating an AI agent.

-   **Python Class**: `Agent(Document)`
-   **File**: `huf/huf/doctype/agent/agent.py`

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
| **Persist per User (Doc/Schedule)** | `persist_user_history` | Check | When checked, Doc Event and Scheduled runs create/maintain conversation history per initiating user (or trigger owner). If unchecked, a single shared history is used. Default: 1 (checked). |
| **Description**   | `description`  | Small Text | A brief description of the agent's purpose. |
| **Last Run**      | `last_run`     | Datetime  | Timestamp of the last agent execution (read-only, auto-updated). |
| **Total Run**     | `total_run`    | Int       | Total number of times this agent has been executed (read-only, auto-incremented). |
| **Async**        | `async`        | Check     | Hidden field for async execution (internal use).                                                        |
| **Disabled**      | `disabled`      | Check     | If checked, this agent will be disabled and will not run.                                               |
| **Chef**          | `chef`         | Data      | Provider standard name (fetched from provider, hidden).                                                   |
| **Slug**          | `slug`         | Data      | Provider slug (fetched from provider, hidden).                                                          |

**Note**: The `condition` field has been removed from Agent DocType. Conditional triggering is now handled via the `Agent Trigger` DocType.

#### 5. Agent Conversation

Tracks a continuous conversation with an agent.

-   **Python Class**: `AgentConversation(Document)`
-   **File**: `huf/huf/doctype/agent_conversation/agent_conversation.py`

**Fields:**

| Label            | Fieldname        | Type     | Description                                                              |
| :--------------- | :--------------- | :------- | :----------------------------------------------------------------------- |
| **Title**        | `title`          | Data     | The title of the conversation.                                           |
| **Agent**        | `agent`          | Link     | Link to the `Agent` used in this conversation.                           |
| **Session ID**   | `session_id`     | Data     | A unique ID for the session, typically combining channel and user ID.    |
| **Is Active**    | `is_active`      | Check    | Indicates if the conversation is ongoing.                                |
| **Total Messages** | `total_messages` | Int      | The total number of messages exchanged.                                  |

#### 6. Agent Message

Represents a single message within a conversation.

-   **Python Class**: `AgentMessage(Document)`
-   **File**: `huf/huf/doctype/agent_message/agent_message.py`

**Fields:**

| Label          | Fieldname      | Type      | Description                                                              |
| :------------- | :------------- | :-------- | :----------------------------------------------------------------------- |
| **Conversation** | `conversation` | Link      | Link to the parent `Agent Conversation`.                                 |
| **Role**         | `role`         | Select    | The role of the message sender (`user`, `agent`, or `system`).           |
| **Content**      | `content`      | Long Text | The text content of the message.                                         |
| **Kind**         | `kind`         | Select    | The type of message (`Message`, `Tool Call`, `Tool Result`, `Error`).    |
| **Run**          | `run`          | Link      | Link to the `Agent Run` that generated this message.                     |

#### 7. Agent Run

Logs a single, complete execution cycle of an agent in response to a user prompt.

-   **Python Class**: `AgentRun(Document)`
-   **File**: `huf/huf/doctype/agent_run/agent_run.py`

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

#### 8. Agent Chat

A single DocType providing a real-time chat interface for conversational agents.

-   **Python Class**: `AgentChat(Document)`
-   **File**: `huf/huf/doctype/agent_chat/agent_chat.py`

**Features:**
-   Real-time chat UI with markdown rendering
-   Message history display
-   Only available for agents with `allow_chat` enabled
-   Server Actions: `huf.ai.agent_chat.get_agent_chat_messages`, `huf.ai.agent_chat.send_agent_chat_message`

#### 9. Agent Console

A singleton DocType providing a simple interface for testing and debugging agents without requiring the full chat interface.

-   **Python Class**: `AgentConsole(Document)`
-   **File**: `huf/huf/doctype/agent_console/agent_console.py`

**Fields:**

| Label          | Fieldname      | Type      | Description                                                              |
| :------------- | :------------- | :-------- | :----------------------------------------------------------------------- |
| **Agent**      | `agent_name`   | Link      | Link to the `Agent` to test.                                             |
| **Prompt**     | `prompt`       | Code      | The prompt/input to send to the agent for testing.                       |
| **Response**   | `response`     | Code      | The agent's response (read-only, auto-populated).                        |
| **Provider**   | `provider`     | Data      | Provider name (read-only, fetched from agent).                           |
| **Model**      | `model`        | Data      | Model name (read-only, fetched from agent).                              |

**Features:**
-   Simple form-based interface for quick agent testing
-   Direct execution of agent prompts
-   Display of agent responses in code format
-   Server Action: `huf.ai.agent_integration.run_agent_sync` (whitelisted)

**Note**: This is a singleton DocType (`issingle: 1`), meaning there is only one instance in the system used as a testing console.

#### 10. Agent Trigger

Defines how and when agents are triggered for execution. This DocType replaces the old `condition` field in the Agent DocType with a comprehensive trigger management system.

-   **Python Class**: `AgentTrigger(Document)`
-   **File**: `huf/huf/doctype/agent_trigger/agent_trigger.py`

**Fields:**

| Label                | Fieldname            | Type      | Description                                                                                             |
| :------------------- | :------------------- | :-------- | :------------------------------------------------------------------------------------------------------ |
| **Trigger Name**     | `trigger_name`       | Data      | Unique name for the trigger (auto-generated).                                                           |
| **Agent**            | `agent`              | Link      | Link to the `Agent` to be executed.                                                                    |
| **Trigger Type**     | `trigger_type`       | Select    | Type of trigger: `Schedule`, `Doc Event`, `Webhook`, `App Event`, `Manual`.                             |
| **Disabled**         | `disabled`           | Check     | Whether the trigger is disabled.                                                                       |
| **Reference Doctype**| `reference_doctype`  | Link      | For Doc Event triggers, the target DocType.                                                            |
| **Doc Event**        | `doc_event`          | Select    | Document lifecycle event (e.g., `after_insert`, `on_submit`, `on_cancel`).                             |
| **Condition**        | `condition`          | Code      | Conditional expression evaluated before triggering (Doc Event only).                                  |
| **Scheduled Interval**| `scheduled_interval` | Select    | For Schedule triggers: `Hourly`, `Daily`, `Weekly`, `Monthly`, `Yearly`.                              |
| **Interval Count**   | `interval_count`     | Int       | Number of intervals between executions (Schedule only).                                               |
| **Last Execution**   | `last_execution`     | Datetime  | Timestamp of last execution (read-only, Schedule only).                                                |
| **Next Execution**   | `next_execution`     | Datetime  | Timestamp of next scheduled execution (read-only, Schedule only).                                       |
| **Webhook Key**      | `webhook_key`        | Data      | Authentication key for webhook triggers.                                                              |
| **Webhook Slug**     | `webhook_slug`       | Data      | URL slug for webhook endpoints.                                                                        |
| **App Name**         | `app_name`           | Data      | For App Event triggers, the name of the app.                                                           |
| **Event Name**       | `event_name`         | Data      | Name of the event to trigger on.                                                                       |
| **Metadata**         | `metadata`           | JSON      | Additional metadata for the trigger.                                                                   |
| **Disabled Reason**  | `disabled_reason`    | Small Text| Reason why the trigger was disabled.                                                                   |
| **Is Virtual**       | `is_virtual`         | Check     | Whether this is a virtual trigger (system-generated).                                                  |
| **Source System**    | `source_system`      | Data      | Source system that created this trigger.                                                               |

**Trigger Types:**
- **Schedule**: Time-based execution with configurable intervals
- **Doc Event**: Triggered by document lifecycle events with optional conditions
- **Webhook**: HTTP endpoint triggers with authentication
- **App Event**: Application-level event triggers
- **Manual**: Manually executed triggers

#### 11. Agent Run Feedback

Captures user feedback on agent responses for quality control and improvement.

-   **Python Class**: `AgentRunFeedback(Document)`
-   **File**: `huf/huf/doctype/agent_run_feedback/agent_run_feedback.py`

**Fields:**

| Label          | Fieldname      | Type      | Description                                                              |
| :------------- | :------------- | :-------- | :----------------------------------------------------------------------- |
| **Feedback**   | `feedback`     | Select    | User feedback: `Thumbs Up` or `Thumbs Down`.                             |
| **Comments**   | `comments`     | Small Text| Optional comments explaining the feedback.                              |
| **Agent Message**| `agent_message`| Link     | Link to the `Agent Message` being rated.                                |
| **Agent**      | `agent`        | Link      | Link to the `Agent` (fetched from agent message).                      |
| **Provider**   | `provider`     | Link      | Link to the `AI Provider` (fetched from agent).                        |
| **Model**      | `model`        | Link      | Link to the `AI Model` (fetched from agent).                            |

#### 12. Agent Run Group

Groups related agent executions together for batch processing and organization.

-   **Python Class**: `AgentRunGroup(Document)`
-   **File**: `huf/huf/doctype/agent_run_group/agent_run_group.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Job Name** | `job_name`   | Data | Unique name for the batch job.            |

#### 13. Agent Settings

Global application settings for the Huf system (singleton DocType).

-   **Python Class**: `AgentSettings(Document)`
-   **File**: `huf/huf/doctype/agent_settings/agent_settings.py`

**Fields:**

| Label               | Fieldname          | Type | Description                               |
| :------------------ | :----------------- | :--- | :---------------------------------------- |
| **Default Provider**| `default_provider`  | Link | Default `AI Provider` for new agents.    |
| **Default Model**   | `default_model`     | Link | Default `AI Model` for new agents.       |

#### 14. AI Provider Settings

Provider-specific configuration settings (singleton DocType).

-   **Python Class**: `AIProviderSettings(Document)`
-   **File**: `huf/huf/doctype/ai_provider_settings/ai_provider_settings.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Provider** | `provider`   | Link | Link to the `AI Provider` to configure.  |

#### 15. Agent Tool HTTP Header

Child table for defining custom HTTP headers for tool requests (table DocType).

-   **Python Class**: `AgentToolHttpHeader(Document)`
-   **File**: `huf/huf/doctype/agent_tool_http_header/agent_tool_http_header.py`

**Fields:**

| Label    | Fieldname | Type | Description                               |
| :------- | :-------- | :--- | :---------------------------------------- |
| **Key**  | `key`     | Data | HTTP header name.                         |
| **Value**| `value`   | Data | HTTP header value.                        |

**Usage**: Used as a child table in `Agent Tool Function` to provide custom HTTP authentication headers for API-based tools.

#### 16. Agent Tool Type

Categorization DocType for organizing and grouping agent tools by type or purpose.

-   **Python Class**: `AgentToolType(Document)`
-   **File**: `huf/huf/doctype/agent_tool_type/agent_tool_type.py`

**Fields:**

| Label    | Fieldname | Type | Description                               |
| :------- | :-------- | :--- | :---------------------------------------- |
| **Name** | `name1`   | Data | Unique name for the tool type category (e.g., "Database", "HTTP", "Custom", "Built-in"). Required field. |

**Usage**: Used by `Agent Tool Function` DocType via the `tool_type` link field for categorization and organization. This allows users to group tools by functionality, making it easier to manage large tool libraries.

**Examples**: Tool types might include categories like "Document Operations", "HTTP Requests", "Custom Functions", "App Provided", "Built-in Tools", etc.
### Core Classes and Methods

The primary logic is located in the `huf/ai` directory.

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

This file acts as a bridge between Huf's `Agent Tool Function` DocType and the `agents` SDK's `FunctionTool` class.

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

#### `providers/openrouter.py`

This file implements the OpenRouter provider with custom retry logic and enhanced error handling.

-   **Function: `run(agent, enhanced_prompt, provider, model, context=None)`**
    -   Main async function that handles OpenRouter API interactions.
    -   **API Key Management**: Retrieves API key from `AI Provider` DocType using secure password field.
    -   **Multi-turn Tool Calling**: Supports multiple rounds of tool calling in a single agent run (up to 10 rounds).
    -   **Retry Logic**: Implements exponential backoff for rate limit (429) errors with up to 5 retries.
    -   **Tool Serialization**: Uses `tool_serializer.serialize_tools()` for provider-agnostic tool format.
    -   **Usage Tracking**: Accumulates token usage across multiple rounds of tool calling.
-   **Function: `_post_with_retry(url, headers, payload, max_retries=5)`**
    -   Handles HTTP POST requests with automatic retry for rate limiting.
    -   Implements exponential backoff with random jitter to avoid thundering herd problems.
    -   Retry logic: Starts with 1 second delay, doubles on each retry, adds random jitter (0-0.5s).
    -   Retries up to 5 times on HTTP 429 (rate limit) errors.
    -   Provides clear error messages when all retries are exhausted.
-   **Function: `_execute_tool_call(tool, args_json)`**
    -   Executes a tool call asynchronously by calling `tool.on_invoke_tool(None, args_json)`.
    -   Returns the result from tool execution.
-   **Function: `_find_tool(agent, tool_name)`**
    -   Finds a tool by name in the agent's tools list using generator expression with `next()`.
    -   Returns the first matching tool or `None` if not found.
-   **Error Handling**: Comprehensive error handling for API errors, tool execution failures, and malformed responses.
-   **Response Format**: Returns `SimpleResult` object with final output, usage statistics, and new items.

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
    -   If model already includes provider prefix (e.g., `openai/gpt-4-turbo`), uses as-is.
    -   Provider prefix mapping includes: `openai`, `anthropic`, `google`, `gemini` (alias), `openrouter`, `xai`, `grok` (alias), `mistral`, `alibaba`/`dashscope`, `cohere`, `perplexity`, `meta`/`meta-llama`.
-   **Function: `_setup_api_key(provider_name, api_key, completion_kwargs)`**
    -   Sets up API key for LiteLLM completion call.
    -   Handles special cases where providers require environment variables: OpenRouter (`OPENROUTER_API_KEY`), xAI/Grok (`XAI_API_KEY`), Mistral (`MISTRAL_API_KEY`), Dashscope/Alibaba (`DASHSCOPE_API_KEY`), Google (`GEMINI_API_KEY`), Cohere (`COHERE_API_KEY`), Perplexity (`PERPLEXITY_API_KEY`).
    -   For other providers, sets `api_key` parameter directly in completion kwargs.
-   **Function: `_execute_tool_call(tool, args_json)`**
    -   Executes a tool call asynchronously by calling `tool.on_invoke_tool(None, args_json)`.
    -   Returns the result from tool execution.
-   **Function: `_find_tool(agent, tool_name)`**
    -   Finds a tool by name in the agent's tools list using generator expression.
    -   Returns the first matching tool or `None` if not found.

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
    -   Uses caching (`huf:doc_event_agents`) for performance.
    -   Loads agent settings (instructions, provider, model) from the Agent DocType.
-   **Function: `clear_doc_event_agents_cache(...)`**
    -   Clears the cache when Agent or Agent Trigger documents are modified.
-   **Function: `run_hooked_agents(doc, method)`**
    -   Called by Frappe document hooks (e.g., `after_insert`, `on_submit`).
    -   Matches agents based on doctype and event type.
    -   **Duplicate Prevention**: Uses cache-based locking to prevent duplicate agent runs for the same document event. Lock expires after 30 seconds.
    -   Evaluates trigger conditions via `safe_eval` before triggering.
    -   Enqueues agent execution as background jobs with unique job IDs (includes UUID to prevent conflicts).
    -   Passes `initiating_user` and `channel_id` to track the source of the trigger.
-   **Function: `run_agent_for_doc(...)`**
    -   Background worker that executes agents triggered by document events.
    -   **Per-User Conversation Support**: Checks the agent's `persist_user_history` field:
        -   If `True`: Creates/maintains conversation history per initiating user (or document owner/modified_by).
        -   If `False`: Uses a shared conversation history (`shared:{agent_name}`).
    -   Constructs a prompt that includes the event name and document identifiers.
    -   Calls `run_agent_sync()` with appropriate `channel_id` and `external_id` parameters for conversation management.

#### `agent_scheduler.py`

This file handles scheduled agent execution based on `Agent Trigger` configurations.

-   **Function: `run_scheduled_agents()` (Whitelisted)**
    -   Main scheduler function that finds and executes scheduled agents.
    -   Queries `Agent Trigger` DocType for active schedule triggers with `next_execution` <= current time.
    -   For each trigger:
        -   Loads the associated Agent and executes it with instructions as prompt.
        -   Updates `last_execution` and calculates `next_execution` based on interval.
        -   Supports `Hourly`, `Daily`, `Weekly`, `Monthly`, `Yearly` intervals with configurable `interval_count`.
    -   Error handling with logging for failed executions.
    -   Commits database changes after each successful execution.

#### `agent_stream_renderer.py`

This file provides Server-Sent Events (SSE) streaming for real-time agent responses.

-   **Class: `AgentStreamRenderer(BaseRenderer)`**
    -   Custom page renderer for SSE streaming endpoints.
    -   **Routes**:
        -   `/huf/stream/<agent_name>` - SSE endpoint for streaming agent responses
        -   `/huf/stream` - HTML demo page with EventSource client for testing
-   **Method: `render()`**
    -   Routes requests to appropriate handler based on path.
    -   Handles both HTML demo page and SSE stream generation.
-   **Method: `_render_agent_stream(agent_name: str)`**
    -   Generates SSE stream for agent responses.
    -   Extracts prompt from query parameters or POST body.
    -   Loads agent configuration (provider, model) from Agent DocType.
    -   Creates async generator wrapper for Werkzeug Response compatibility.
    -   Streams real-time deltas, tool calls, and completion events.
    -   Error handling with proper SSE error messages.
-   **Method: `_render_html_page()`**
    -   Renders comprehensive HTML demo page for testing SSE streaming.
    -   Includes EventSource client, real-time status updates, and UI controls.
    -   Professional styling with responsive design.

#### `speech_to_text.py`

This file provides OpenAI Whisper integration for audio transcription.

-   **Function: `transcribe_audio(audio_file_url: str, language: str = "en")` (Whitelisted)**
    -   Transcribes audio files using OpenAI's Whisper model.
    -   Supports both local Frappe files (`/files/...`) and remote URLs.
    -   Downloads remote audio files to temporary storage for processing.
    -   **Parameters**:
        -   `audio_file_url`: Path or URL to audio file
        -   `language`: Language code (default: "en")
    -   **Returns**: Dictionary with `success`, `text`, `language`, and `audio_file_url` fields.
    -   **Error Handling**: Returns structured error messages for API key issues, download failures, or transcription errors.
    -   **Security**: Validates OpenAI API key configuration before processing.
    -   **Cleanup**: Automatically removes temporary files after transcription.

#### `tool_registry.py`

This file provides automatic tool discovery and synchronization from app hooks.

-   **Function: `_iter_declared_tools()`**
    -   Iterates through tools registered via `huf_tools` hook in apps.
    -   Supports both single tool and list of tools per hook entry.
-   **Function: `validate_tool_def(d)`**
    -   Validates tool definition structure and function availability.
    -   Checks required fields: `tool_name`, `description`, `function_path`, `parameters`.
    -   Dynamically imports and validates function callability.
-   **Function: `upsert_tool_doc(d)`**
    -   Creates or updates `Agent Tool Function` documents from hook definitions.
    -   Sets tool type to "App Provided" for auto-discovered tools.
    -   Converts parameter definitions to Frappe table format.
-   **Function: `_get_app_modified_time(app_name)`**
    -   Gets modification time of app's `hooks.py` file as proxy for app changes.
    -   Used for cache invalidation decisions.
-   **Caching System**: Uses `Agent Settings` singleton to store last sync timestamps.
-   **Sync Logic**: Only syncs when apps have been modified since last sync.

#### `tool_serializer.py`

This file provides provider-agnostic tool serialization for multi-provider AI agents.

-   **Function: `serialize_tools(tools: list)`**
    -   Converts custom `FunctionTool` objects into standard JSON schema format.
    -   **Purpose**: Ensures compatibility with OpenAI, OpenRouter, Anthropic, and other providers.
    -   **Input**: List of `FunctionTool` objects created by `sdk_tools.create_agent_tools`.
    -   **Output**: List of dictionaries in OpenAI/OpenRouter-compatible schema.
    -   **Schema Structure**:
        ```json
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "Tool description",
                "parameters": {...}
            }
        }
        ```
    -   **Error Handling**: Gracefully handles missing attributes with empty defaults.
    -   **Provider Compatibility**: Standardizes tool format across all LLM providers.

#### `http_handler.py`

This file provides secure HTTP request handling with SSRF protection for agent tools.

-   **Function: `validate_url(url, tool_name=None)`**
    -   Validates URLs to prevent SSRF (Server-Side Request Forgery) attacks.
    -   **Security Features**:
        -   Blocks private IP ranges (127.*, 10.*, 172.16-31.*, 192.168.*)
        -   Blocks localhost and IPv6 localhost
        -   Only allows HTTP/HTTPS protocols
        -   Validates against tool's base URL if specified
-   **Function: `handle_http_request(method, url, ...)` (Whitelisted)**
    -   Generic HTTP request handler with tool-defined header support.
    -   **Features**:
        -   Merges tool-defined headers with request headers
        -   Supports base URL configuration from `Agent Tool Function`
        -   Handles both form data and JSON payloads
        -   30-second timeout for all requests
    -   **Response Format**: Standardized response with `success`, `status_code`, `headers`, `data`, and `final_url`.
    -   **Error Handling**: Provides AI-friendly suggestions for common errors.
-   **Function: `handle_get_request(...)` and `handle_post_request(...)` (Whitelisted)**
    -   Convenience wrappers for GET and POST requests.
    -   POST handler includes JSON parsing and validation logic.
    -   Automatic conversion between form data and JSON based on content type.

## Frontend Flow Builder System

The Huf frontend includes a visual flow builder that allows users to create, manage, and execute complex workflows using a drag-and-drop interface. This system provides a professional UI for designing automated workflows with various node types and configurations.

**Note**: The flow builder is currently in active development. Core infrastructure (FlowCanvas, FlowContext, flowService) is implemented, but some advanced features may be in progress or planned.

### Architecture Overview

The flow builder is built on React Flow and provides:
- **Visual Canvas**: Drag-and-drop interface for creating workflows
- **Node System**: Extensible node types for different workflow components
- **Real-time Updates**: Live flow editing and validation
- **Flow Management**: Organization and versioning of workflows (in-memory storage via FlowService)
- **Context-based State**: Centralized state management for flow operations via FlowContext

### Core Components

#### Flow Service (`frontend/src/services/flowService.ts`)

In-memory flow management service that handles all flow operations.

-   **Class: `FlowService`**
    -   Manages flow storage in memory with Map-based structure (`private flows: Map<string, Flow>`)
    -   Provides subscription-based updates for reactive UI via listener pattern
    -   Handles flow CRUD operations (Create, Read, Update, Delete)
    -   Maintains flow metadata and full flow objects
    -   Initializes with default example flows (webform, untitled, email automation)
-   **Key Methods**:
    -   `getAllFlows()`: Returns list of flow metadata as array
    -   `getFlow(id)`: Retrieves complete flow by ID from Map
    -   `createFlow(name, category)`: Creates new flow with default structure and unique ID
    -   `updateFlow(id, updates)`: Updates flow properties and notifies subscribers
    -   `updateFlowName(id, name)`: Updates flow name specifically
    -   `deleteFlow(id)`: Removes flow from storage
    -   `subscribe(callback)`: Subscription system for state changes, returns unsubscribe function
    -   `notify()`: Internal method to notify all subscribers of changes

#### Flow Context (`frontend/src/contexts/FlowContext.tsx`)

React context provider for centralized flow state management.

-   **Interface: `FlowContextType`**
    -   Provides access to flows, active flow, and selected node
    -   Offers methods for flow manipulation (create, update, delete)
    -   Handles node and edge operations (add, update, delete)
    -   Manages flow selection and navigation
-   **State Management**:
    -   `flows`: Array of flow metadata
    -   `activeFlowId`: Currently selected flow ID
    -   `activeFlow`: Complete flow object for active flow
    -   `selectedNodeId`: Currently selected node for configuration

#### Flow Canvas (`frontend/src/components/FlowCanvas.tsx`)

Main visual editor component built on React Flow.

-   **Features**:
    -   Drag-and-drop node placement
    -   Visual connection creation between nodes
    -   Real-time canvas updates
    -   Mini-map and controls for navigation
    -   Responsive design with collapsible sidebars
-   **Node Types Supported**:
    -   **Trigger Nodes**: Workflow entry points (webhook, schedule, doc-event, app-trigger)
    -   **Action Nodes**: Processing steps (transform, router, human-in-loop, loop, code)
    -   **Utility Nodes**: Helper functions (email, file, date, webhook, http)
    -   **End Nodes**: Workflow termination points

### Node Types and Configurations

#### Trigger Nodes

-   **Webhook Trigger**: HTTP endpoint triggers with configurable URLs and authentication
-   **Schedule Trigger**: Time-based triggers with cron expressions and intervals
-   **Document Event Trigger**: Frappe document lifecycle events (save, update, delete)
-   **App Trigger**: Integration with external applications (Gmail, Calendar, Slack, Notion, HubSpot, Sheets)

#### Action Nodes

-   **Transform Action**: Data transformation operations (copy, map, concat, split)
-   **Router Action**: Conditional branching with multiple paths
-   **Human-in-Loop Action**: Approval workflows with timeout and approver lists
-   **Loop Action**: Iterative processing with configurable iteration limits
-   **Code Action**: Custom JavaScript/Python/TypeScript code execution

#### Utility Nodes

-   **Email Utility**: Send emails with templates and dynamic content
-   **File Utility**: File operations (read, write, delete)
-   **Date Utility**: Date formatting and arithmetic operations
-   **Webhook Utility**: HTTP requests to external services
-   **HTTP Utility**: Advanced HTTP operations with custom headers

### Flow Data Structure

#### Flow Object

```typescript
interface Flow {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'error';
  category?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  createdAt: Date;
  updatedAt: Date;
  version: number;
}
```

#### Node Configuration

Each node supports type-specific configuration:

-   **Trigger Config**: Webhook URLs, schedule intervals, document events
-   **Action Config**: Transformation rules, routing conditions, code snippets
-   **Utility Config**: Email templates, file paths, HTTP endpoints

### UI Components

#### Flow Management

-   **Flows Sidebar**: List of all flows with search and filtering
-   **Flow Header Actions**: Create, duplicate, delete, export operations
-   **Flow Categories**: Organization by custom categories

#### Canvas Controls

-   **Mini-map**: Overview of large flows for navigation
-   **Zoom Controls**: Zoom in/out and fit-to-screen
-   **Grid Layout**: Aligned node placement with snap-to-grid
-   **Background Patterns**: Visual distinction between different areas

#### Node Configuration

-   **Node Selection Modal**: Add new nodes with type selection
-   **Configuration Panels**: Side panels for node-specific settings
-   **Validation**: Real-time validation of node configurations
-   **Connection Rules**: Enforced connection rules between node types

### Integration with Backend

The flow builder integrates with the Huf backend through:

-   **Flow Execution**: Flows can be executed and monitored
-   **Agent Integration**: Flow nodes can trigger and interact with Huf agents
-   **Document Events**: Flows respond to Frappe document changes
-   **API Endpoints**: RESTful API for flow management

### Usage Patterns

1. **Create Flow**: Start with a trigger node to define entry point
2. **Add Actions**: Connect action nodes to process data
3. **Configure Nodes**: Set up parameters and conditions for each node
4. **Test Flow**: Validate flow logic and connections
5. **Deploy Flow**: Activate flow for production execution
6. **Monitor**: Track flow execution and performance

### File Structure

```
frontend/src/
├── components/
│   ├── FlowCanvas.tsx          # Main canvas component
│   ├── nodes/                 # Node type components
│   │   ├── TriggerNode.tsx
│   │   ├── ActionNode.tsx
│   │   └── EndNode.tsx
│   └── modals/               # Configuration modals
├── contexts/
│   └── FlowContext.tsx         # State management
├── services/
│   └── flowService.ts         # Flow operations
└── types/
    └── flow.types.ts           # TypeScript definitions
```

## Streaming Architecture

The Huf system includes Server-Sent Events (SSE) streaming capabilities for real-time agent responses, enabling live interaction with AI agents without traditional request-response cycles.

### SSE Implementation

#### Agent Stream Renderer (`huf/ai/agent_stream_renderer.py`)

-   **Class: `AgentStreamRenderer(BaseRenderer)`**
    -   Custom page renderer that handles SSE streaming for agents
    -   Integrates with Frappe's website routing system
    -   Provides both streaming endpoints and demo interface

#### Streaming Endpoints

-   **`/huf/stream/<agent_name>`** - SSE endpoint for streaming agent responses
    -   Accepts `prompt` parameter via query string or POST body
    -   Supports optional parameters: `channel_id`, `external_id`, `conversation_id`
    -   Returns real-time deltas, tool calls, and completion events
    -   Handles error conditions with proper SSE error messages

-   **`/huf/stream`** - HTML demo page with EventSource client for testing
    -   Professional UI for testing streaming capabilities
    -   Real-time status updates and response display
    -   Supports both GET and POST request methods
    -   Includes error handling and connection management

#### Streaming Data Format

The SSE stream emits JSON events with the following structure:

```json
{
  "type": "delta",
  "content": "Partial response text",
  "full_response": "Accumulated response so far"
}
```

**Event Types**:
-   `delta`: Partial response content during generation
-   `tool_call`: Information about tool being executed
-   `complete`: Final response when generation is finished
-   `error`: Error information if streaming fails

#### Client Integration

**JavaScript EventSource Example**:
```javascript
const eventSource = new EventSource('/huf/stream/my-agent?prompt=Hello');

eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  if (data.type === 'delta') {
    // Update UI with partial response
    updateResponse(data.full_response);
  }
};

eventSource.addEventListener('complete', function(event) {
  const data = JSON.parse(event.data);
  // Handle final response
  finalizeResponse(data.full_response);
});
```

#### Features

-   **Real-time Streaming**: Live response updates as they're generated
-   **Tool Call Visibility**: Shows when agents are using tools
-   **Error Handling**: Graceful error reporting and recovery
-   **Connection Management**: Automatic cleanup and timeout handling
-   **Cross-browser Compatibility**: Works with modern browsers supporting EventSource
-   **Security**: Inherits agent permissions and authentication

#### Usage Patterns

1. **Direct Integration**: Use EventSource directly in web applications
2. **React Components**: Build custom React components for streaming UI
3. **Testing**: Use demo page at `/huf/stream` for development
4. **Monitoring**: Track streaming performance and error rates

#### Technical Details

-   **Async Generator**: Uses Python async generators for efficient streaming
-   **Werkzeug Integration**: Compatible with Frappe's web framework
-   **Memory Management**: Automatic cleanup of temporary resources
-   **Error Recovery**: Handles network interruptions and timeouts
-   **Response Accumulation**: Maintains full response context throughout stream

## Security Enhancements

The Huf system includes several security enhancements to protect against common vulnerabilities and ensure safe agent operations.

### SSRF Protection

#### URL Validation (`http_handler.py`)

-   **Function: `validate_url(url, tool_name=None)`**
    -   Validates URLs to prevent SSRF (Server-Side Request Forgery) attacks
    -   **Security Features**:
        -   Blocks private IP ranges (127.*, 10.*, 172.16-31.*, 192.168.*)
        -   Blocks localhost and IPv6 localhost
        -   Only allows HTTP/HTTPS protocols
        -   Validates against tool's base URL if specified
    -   **Private IP Pattern**: Uses regex to match and block private network ranges
    -   **Protocol Validation**: Ensures only allowed protocols are used

#### HTTP Request Security

-   **Base URL Validation**: Tools can specify allowed base URLs for additional security
-   **Header Management**: Secure handling of custom HTTP headers
-   **Timeout Protection**: 30-second timeout prevents hanging requests
-   **Error Sanitization**: Clean error messages that don't expose system information

### API Key Management

-   **Password Field Type**: API keys stored using Frappe's encrypted Password field
-   **Environment Variables**: Sensitive keys (like OpenRouter) use environment variables
-   **Provider Isolation**: Each provider's keys are stored separately
-   **Access Control**: Proper permissions for accessing API key configurations

## Tool Discovery System

The Huf system provides automatic tool discovery and synchronization from app hooks, enabling apps to register tools that become available to agents automatically.

### Hook-Based Registration

#### Tool Registration Hook

-   **Hook Name**: `huf_tools`
-   **Registration Format**: Apps can register single tools or lists of tools
-   **Hook Definition**: In app's `hooks.py` file:
    ```python
    huf_tools = [
        "my_app.tools.custom_tool",
        ["my_app.tools.tool1", "my_app.tools.tool2"]
    ]
    ```

#### Tool Definition Structure

Each registered tool must include:

-   **tool_name**: Unique identifier for the tool
-   **description**: Clear description of what the tool does
-   **function_path**: Dotted path to the Python function
-   **parameters**: Array of parameter definitions with types and requirements

#### Validation and Import

-   **Function Validation**: Dynamically imports and validates function callability
-   **Structure Validation**: Ensures all required fields are present
-   **Type Checking**: Validates parameter types and requirements
-   **Error Handling**: Clear error messages for invalid tool definitions

### Synchronization Process

#### Automatic Sync (`tool_registry.py`)

-   **Trigger**: Sync occurs when apps are modified or on system startup
-   **Cache Management**: Uses `Agent Settings` singleton to track last sync times
-   **App Modification Detection**: Checks `hooks.py` file modification times
-   **Incremental Updates**: Only processes apps that have changed since last sync

#### Tool Document Creation

-   **Upsert Logic**: Creates new or updates existing `Agent Tool Function` documents
-   **Tool Type**: Automatically set to "App Provided" for discovered tools
-   **Parameter Conversion**: Converts hook parameter definitions to Frappe table format
-   **Metadata Preservation**: Maintains tool metadata and relationships

### Caching System

#### Performance Optimization

-   **Tool Discovery Cache**: Caches discovered tools to avoid repeated processing
-   **App Modification Cache**: Tracks modification times of app hook files
-   **Cache Invalidation**: Automatically clears cache when apps are updated
-   **Memory Efficiency**: Uses efficient data structures for caching

#### Cache Keys

-   **huf:discovered_tools**: Cache for discovered tool definitions
-   **huf:app_modification_times**: Cache for app file modification times
-   **Agent Settings**: Singleton document used for persistent cache storage

### Integration with Agent System

#### Tool Availability

-   **Automatic Inclusion**: Discovered tools automatically available in agent tool selection
-   **Type Classification**: Properly categorized as "App Provided" tools
-   **Parameter Handling**: Full parameter support with type validation
-   **Execution**: Uses same execution pipeline as manually defined tools

#### Multi-App Support

-   **App Isolation**: Tools from different apps are properly namespaced
-   **Conflict Resolution**: Handles tool name conflicts across apps
-   **Dependency Management**: Ensures app dependencies are properly loaded
-   **Version Compatibility**: Supports tool versioning and compatibility checks
