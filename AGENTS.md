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
4.  **Agent**: An `Agent` is the central entity. You give it a name, instructions (prompt), temperature, top_p, and assign it a set of tools. Each agent has its own individual settings that are read directly from the Agent DocType. Agents can be configured for scheduling, doc events, or chat.
5.  **Conversation**: When a user interacts with an agent, a `Agent Conversation` is created to track the entire interaction. Each message back-and-forth is stored as an `Agent Message`.
6.  **Execution**: A specific request to the agent and its subsequent actions are logged in an `Agent Run` with token usage and cost tracking.
7.  **Chat Interface**: `Agent Chat` provides a real-time chat UI for conversational agents with markdown rendering.

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
| **Slug**       | `slug`         | Data       | A URL-friendly identifier for the provider (e.g., `openai`, `anthropic`). Used for frontend listing and routing. |
| **Chef**       | `chef`         | Data       | The provider's standard display name (e.g., `OpenAI`, `Anthropic`). Used for frontend display and agent listing. |

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

#### 4. Agent

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
| **Persist per User (Doc/Schedule)** | `persist_user_history` | Check | When checked, Doc Event and Scheduled runs create/maintain conversation history per initiating user (or trigger owner). If unchecked, a single shared history is used. Default: 1 (checked). |
| **Description**   | `description`  | Small Text | A brief description of the agent's purpose. |
| **Last Run**      | `last_run`     | Datetime  | Timestamp of the last agent execution (read-only, auto-updated). |
| **Total Run**     | `total_run`    | Int       | Total number of times this agent has been executed (read-only, auto-incremented). |
| **Slug**          | `slug`         | Data      | Provider slug (fetched from provider, hidden field). Used for frontend listing. |
| **Chef**          | `chef`         | Data      | Provider standard name (fetched from provider, hidden field). Used for frontend display. |
| **Enable Multi Run** | `enable_multi_run` | Check | Enables multi-step orchestration mode. When checked, agent runs create an orchestration workflow instead of direct execution. |

**Note**: The `condition` field has been removed from Agent DocType. Conditional triggering is now handled via the `Agent Trigger` DocType.

#### 5. Agent Conversation

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

#### 6. Agent Message

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

#### 7. Agent Run

Logs a single, complete execution cycle of an agent in response to a user prompt.

-   **Python Class**: `AgentRun(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_run/agent_run.py`

**Fields:**

| Label          | Fieldname       | Type       | Description                                                              |
| :------------- | :-------------- | :--------- | :----------------------------------------------------------------------- |
| **Conversation** | `conversation`  | Link       | Link to the `Agent Conversation`.                                        |
| **Agent**        | `agent`         | Link       | Link to the `Agent` that was run.                                        |
| **Run Group**    | `run_group`     | Link       | Link to the `Agent Run Group` (Job ID) that groups related runs. Hidden field. |
| **Prompt**       | `prompt`        | Code       | The user prompt that initiated the run (stored as Code field for better formatting). |
| **Response**     | `response`      | Code       | The final response from the agent (stored as Code field for better formatting). |
| **Status**       | `status`        | Select     | The status of the run (`Started`, `Queued`, `Success`, `Failed`).        |
| **Error Code**   | `error_code`    | Data       | Error code if the run failed (read-only).                                |
| **Error Message**| `error_message` | Long Text  | Any error message if the run failed (read-only).                         |
| **Provider**      | `provider`      | Link       | Link to the `AI Provider` used for this run (read-only).                 |
| **Model**        | `model`         | Link       | Link to the `AI Model` used for this run (read-only).                     |
| **Start Time**   | `start_time`    | Datetime   | Timestamp before requesting provider API (read-only).                    |
| **End Time**     | `end_time`      | Datetime   | Timestamp after provider response is completely generated (read-only).  |
| **Input Tokens** | `input_tokens`  | Int        | Number of tokens in the input (prompt + context) (read-only).            |
| **Output Tokens**| `output_tokens` | Int        | Number of tokens in the output (response) (read-only).                   |
| **Cost**         | `cost`          | Float      | Cost of generating this response based on token usage. Might not be accurate (read-only). |

#### 8. Agent Run Group

Groups related agent runs together, typically used for scheduled or batch executions.

-   **Python Class**: `AgentRunGroup(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_run_group/agent_run_group.py`

**Fields:**

| Label       | Fieldname   | Type   | Description                                                              |
| :---------- | :---------- | :----- | :----------------------------------------------------------------------- |
| **Job Name** | `job_name`  | Data   | Unique identifier for the job/group (typically a UUID or job ID).       |

**Purpose:**
- Links multiple `Agent Run` documents that are part of the same execution batch or scheduled job.
- Used internally for tracking and grouping related agent executions.

#### 9. Agent Run Feedback

Allows users to provide feedback on agent responses, enabling quality monitoring and improvement.

-   **Python Class**: `AgentRunFeedback(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_run_feedback/agent_run_feedback.py`

**Fields:**

| Label            | Fieldname      | Type      | Description                                                              |
| :--------------- | :------------- | :-------- | :----------------------------------------------------------------------- |
| **Feedback**     | `feedback`     | Select    | User feedback rating (`Thumbs Up` or `Thumbs Down`).                    |
| **Comments**     | `comments`     | Small Text | Optional comments explaining the feedback.                                |
| **Agent Message** | `agent_message` | Link    | Link to the specific `Agent Message` that received feedback.           |
| **Agent**        | `agent`        | Link      | Link to the `Agent` that generated the response.                          |
| **Provider**     | `provider`     | Link      | Link to the `AI Provider` used (fetched from agent).                    |
| **Model**        | `model`        | Link      | Link to the `AI Model` used (fetched from agent).                        |

**Purpose:**
- Enables users to rate agent responses directly from the chat interface.
- Provides data for monitoring agent performance and improving instructions.
- Links feedback to specific messages for detailed analysis.

#### 10. Agent Chat

A single DocType providing a real-time chat interface for conversational agents.

-   **Python Class**: `AgentChat(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_chat/agent_chat.py`

**Features:**
-   Real-time chat UI with markdown rendering
-   Message history display
-   Message actions: copy to clipboard, provide feedback (thumbs up/down)
-   Only available for agents with `allow_chat` enabled
-   Server Actions: `agentflo.ai.agent_chat.get_agent_chat_messages`, `agentflo.ai.agent_chat.send_agent_chat_message`

#### 11. Agent Orchestration

Manages multi-step agent workflows when `enable_multi_run` is enabled on an agent.

-   **Python Class**: `AgentOrchestration(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_orchestration/agent_orchestration.py`

**Fields:**

| Label            | Fieldname                 | Type      | Description                                                              |
| :--------------- | :------------------------ | :-------- | :----------------------------------------------------------------------- |
| **Agent**        | `agent`                   | Link      | Link to the `Agent` that owns this orchestration.                       |
| **Status**       | `status`                  | Select    | Current status (`Planned`, `Running`, `Paused`, `Completed`, `Failed`). |
| **Current Step** | `current_step`            | Int       | Index of the step currently being executed.                             |
| **Last Run**     | `last_run_at`             | Datetime  | Timestamp of the last step execution.                                   |
| **Error Log**    | `error_log`               | Small Text | Error messages from failed steps.                                       |
| **Plan**         | `agent_orchestration_plan`| Table     | Child table containing the execution plan steps.                        |
| **Scratchpad**   | `scratchpad`              | Code      | Intermediate data and outputs from completed steps.                     |

**Purpose:**
- Enables complex multi-step agent workflows
- Stores execution plan generated by planning phase
- Maintains scratchpad for step-to-step context
- Tracks progress and errors across steps

#### 12. Agent Orchestration Plan (Child Table)

Stores individual steps in an orchestration plan.

-   **Python Class**: `AgentOrchestrationPlan(Document)`
-   **File**: `agentflo/agentflo/doctype/agent_orchestration_plan/agent_orchestration_plan.py`

**Fields:**

| Label            | Fieldname    | Type      | Description                                                              |
| :--------------- | :----------- | :-------- | :----------------------------------------------------------------------- |
| **Step Index**   | `step_index` | Int       | Order of the step in the plan (1, 2, 3...).                             |
| **Instruction**  | `instruction`| Long Text | The specific instruction for this step.                                 |
| **Status**       | `status`     | Select    | Step status (`pending`, `in_progress`, `done`, `failed`).               |
| **Output Ref**   | `output_ref` | Data      | Reference to the step's output or result.                               |

**Purpose:**
- Stores atomic steps generated by the planning phase
- Tracks individual step execution status
- Links step outputs for debugging and analysis

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
    -   **Multi-Run Detection**: If agent has `enable_multi_run` enabled and channel is not `orchestration` or `orchestration_planning`, creates orchestration instead of direct execution.
    -   It orchestrates the entire process:
        1.  Checks for `enable_multi_run` flag → creates orchestration if enabled.
        2.  Initializes `ConversationManager` to handle the conversation history.
        3.  Creates or retrieves the `Agent Conversation` document.
        4.  Adds the user's new message to the conversation.
        5.  Creates an `Agent Run` document to log the execution.
        6.  Initializes `AgentManager` to prepare the agent.
        7.  Creates context dictionary with `agent_name` (required for LiteLLM provider to access Agent DocType settings).
        8.  Calls `RunProvider.run()` which routes to the appropriate provider (LiteLLM for most providers).
        9.  Adds the agent's final response to the conversation.
        10. Updates the `Agent Run` status to `Success` or `Failed`.

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
    -   Loads agent settings (instructions, provider, model) from the Agent DocType.
-   **Function: `clear_doc_event_agents_cache(...)`**
    -   Clears the cache when Agent or Agent Trigger documents are modified.
-   **Function: `run_hooked_agents(doc, method)`**
    -   Called by Frappe document hooks (e.g., `after_insert`, `on_submit`).
    -   **Migration Safety**: Skips agent hooks during migration to prevent circular dependencies when Agent Trigger DocType is being created.
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

#### `orchestration/orchestrator.py`

This file handles multi-step agent orchestration for complex tasks that require planning and sequential execution.

-   **Function: `create_orchestration(agent_name, user_prompt)`**
    -   Creates a new `Agent Orchestration` document when `enable_multi_run` is enabled.
    -   Loads agent doc to get provider and model settings.
    -   Calls `run_planning()` to break down the user's objective into atomic steps.
    -   Creates `agent_orchestration_plan` child table entries for each step.
    -   Returns the orchestration document name.
-   **Function: `parse_plan_steps(text)`**
    -   Parses numbered list output from planning agent into a Python list of step instructions.
    -   Handles multiple formats: `1. Step`, `1) Step`, `1: Step`.
-   **Function: `execute_next_step(orch)`**
    -   Executes the next pending step in the orchestration plan.
    -   Updates step status to `in_progress`, then `done` after completion.
    -   Calls `run_agent_sync()` with step-specific prompt, provider, model, and scratchpad context.
    -   Uses `channel_id="orchestration"` to prevent infinite loop with multi-run detection.
    -   Updates orchestration scratchpad with step outputs.
    -   Marks orchestration as `Completed` when all steps are done.
    -   Handles errors gracefully and logs to `error_log` field.

#### `orchestration/scheduler.py`

This file processes orchestration steps via scheduled tasks.

-   **Function: `process_orchestrations()`**
    -   Called every minute via cron scheduler (`*/1 * * * *`).
    -   Checks if `Agent Orchestration` DocType exists (migration safety).
    -   Finds all orchestrations with status `Planned` or `Running`.
    -   Executes the next pending step for each orchestration.
    -   Logs errors for failed steps.

#### `orchestration/planning.py`

This file handles the planning phase of orchestration.

-   **Function: `run_planning(agent_name, user_prompt, provider, model)`**
    -   Calls the agent with a planning prompt to break down objectives into steps.
    -   Uses `channel_id="orchestration_planning"` to prevent infinite loop.
    -   Returns a numbered list of atomic steps, or empty string on failure.
    -   Uses a specialized planning prompt with clear formatting rules.