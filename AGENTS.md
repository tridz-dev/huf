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

## Detailed Architecture

This section provides a deep dive into the application's structure, including DocTypes and core Python classes, to give the agent maximum context.

### Core Concepts

1.  **Provider & Model**: You start by defining an `AI Provider` (e.g., OpenAI) and the `AI Model` you want to use (e.g., `gpt-4`).
2.  **Tools**: Agents need tools to be useful. An `Agent Tool Function` defines a specific action the agent can perform, such as fetching a document, creating a new one, or calling a custom Python function.
3.  **Agent**: An `Agent` is the central entity. You give it a name, instructions (prompt), and assign it a set of tools. Agents can be configured for scheduling, doc events, or chat.
4.  **Conversation**: When a user interacts with an agent, a `Agent Conversation` is created to track the entire interaction. Each message back-and-forth is stored as an `Agent Message`.
5.  **Execution**: A specific request to the agent and its subsequent actions are logged in an `Agent Run` with token usage and cost tracking.
6.  **Chat Interface**: `Agent Chat` provides a real-time chat UI for conversational agents with markdown rendering.

### Doctypes

Here is a detailed breakdown of the DocTypes used in AgentFlo.

#### 1. AI Provider

Stores credentials for different AI service providers.

-   **Python Class**: `AIProvider(Document)`
-   **File**: `agentflo/agentflo/doctype/ai_provider/ai_provider.py`

**Fields:**

| Label          | Fieldname      | Type       | Description                               |
| :------------- | :------------- | :--------- | :---------------------------------------- |
| **Provide Name** | `provide_name` | Data       | The unique name of the provider (e.g., OpenAI). |
| **API Key**    | `api_key`      | Password   | The API key for the provider.             |

#### 2. AI Model

Defines a specific AI model available from a provider.

-   **Python Class**: `AIModel(Document)`
-   **File**: `agentflo/agentflo/doctype/ai_model/ai_model.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Model Name** | `model_name` | Data | The name of the model (e.g., `gpt-4-turbo`). |
| **Provider**   | `provider`   | Link | A link to the `AI Provider` DocType.      |

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
| **Instructions** | `instructions` | Long Text | The system prompt or instructions that define the agent's personality, goals, and constraints.          |
| **Agent Tool**   | `agent_tool`   | Table     | A child table (`Agent Tool`) linking to the `Agent Tool Function`s that this agent is allowed to use. |
| **Temperature**  | `temperature`  | Float     | Controls the randomness of the AI's output.                                                             |
| **Top P**        | `top_p`        | Float     | An alternative to temperature for controlling randomness.                                               |
| **Enable Chat**  | `enable_chat`  | Check     | Enables the Agent Chat interface for real-time conversations.                                           |
| **Condition**    | `condition`    | Code      | Python expression for conditional triggering on document events (e.g., `doc.grand_total > 10000`).     |

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
    -   `create_agent(self)`: Constructs an `Agent` object from the `agents` SDK, passing the instructions, model, and tools.
-   **Method: `run_agent_sync(...)`**
    -   This is the main whitelisted Frappe API endpoint for running an agent.
    -   It orchestrates the entire process:
        1.  Initializes `ConversationManager` to handle the conversation history.
        2.  Creates or retrieves the `Agent Conversation` document.
        3.  Adds the user's new message to the conversation.
        4.  Creates an `Agent Run` document to log the execution.
        5.  Initializes `AgentManager` to prepare the agent.
        6.  Calls `Runner.run()` from the `agents` SDK to execute the agent with the prompt and conversation history.
        7.  Adds the agent's final response to the conversation.
        8.  Updates the `Agent Run` status to `Success` or `Failed`.

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

#### `agent_chat.py`

This file provides the backend API for the Agent Chat interface.

-   **Method: `get_agent_chat_messages(...)` (Whitelisted)**
    -   Retrieves message history for the chat UI.
    -   Returns formatted messages with role, content, and timestamps.
-   **Method: `send_agent_chat_message(...)` (Whitelisted)**
    -   Processes user input from the chat interface.
    -   Calls the agent and returns the response.
    -   Manages chat-specific conversation persistence and message formatting.