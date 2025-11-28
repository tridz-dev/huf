# Huf (formerly AgentFlo)

Huf is a powerful Frappe application for create, manage, and integrate AI agents directly into Frappe ecosystem. These agents can be equipped with tools to interact with your site's data, automate tasks, and provide intelligent assistance.

**[📚 View Documentation](https://tridz-dev.github.io/agent_flo/)** | **[🐛 Report Issue](https://github.com/tridz-dev/huf/issues)** | **[💬 Discussions](https://github.com/tridz-dev/huf/discussions)**

<br/><br/>
<img width="1905" height="928" alt="image_2025-11-07_18-16-05 (1)" src="https://github.com/user-attachments/assets/61a8511b-80cc-4843-a90c-bfcfc4a45c97" />


<br/>



>  ⚠️ Huf is actively being migrated from an existing implementation into an independent app. The system may not work as expected and is not recommended for use in production environments at this stage. ⚠️ 

## Key Features

-   **AI Provider & Model Management:**
    -   Configure multiple AI providers (OpenAI, OpenRouter, etc.).
    -   Manage different AI models for each provider.

-   **Flexible Agent Creation:**
    -   Create agents with custom instructions, models, and parameters (temperature, top-p).
    -   **Event-Driven Agents:** Trigger agents to run based on any DocType event (e.g., `on_submit`, `after_insert`).
    -   **Scheduled Agents:** Schedule agents to run at regular intervals (hourly, daily, weekly, etc.).
    -   **Chat Agents:** Enable agents for real-time chat conversations.

-   **Powerful Tool System:**
    -   Equip agents with tools to interact with your Frappe site.
    -   **CRUD Operations:** Tools for getting, creating, updating, and deleting documents.
    -   **Custom Functions:** Create tools from your own whitelisted Python functions.
    -   **HTTP Requests:** Allow agents to make `GET` and `POST` requests to external APIs.
    -   **Run Agent Tool:** Enable agents to trigger other agents.

-   **Interactive Interfaces:**
    -   **Agent Console:** A simple interface for testing and debugging agents.
    -   **Agent Chat:** A dedicated, real-time chat UI for interacting with conversational agents.

-   **Comprehensive Logging & Auditing:**
    -   **Agent Run:** Tracks every agent execution, including status, prompt, response, and token usage.
    -   **Agent Conversation:** Stores the complete history of chat sessions.
    -   **Agent Message:** Logs every message exchanged in a conversation.
    -   **Agent Tool Call:** Records every time an agent uses a tool, including the arguments and result.

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app git@github.com:tridz-dev/huf.git
bench install-app huf
bench setup requirements  # Installs dependencies including litellm
```

**Note**: After installation or update, run `bench setup requirements` to ensure all dependencies (including `litellm`) are installed. Then restart your site with `bench restart`.

## Architecture Overview

Huf is built around a set of interconnected DocTypes that define the components of an AI agent. The core logic is handled by Python classes that integrate with an AI provider (like OpenAI) and manage the agent's lifecycle.

### Core Concepts

1.  **AI Provider & Model**: You start by defining an `AI Provider` (e.g., OpenAI) and the `AI Model` you want to use (e.g., `gpt-4`).
2.  **Tools**: Agents need tools to be useful. An `Agent Tool Function` defines a specific action the agent can perform, such as fetching a document, creating a new one, or calling a custom Python function.
3.  **Agent**: The central entity. You give it a name, instructions (prompt), and assign it a set of tools. You can also configure it to run on a schedule or in response to a DocType event.
4.  **Agent Conversation & Chat**: When a user interacts with a chat-enabled agent, an `Agent Conversation` is created to track the interaction. The `Agent Chat` doctype provides the UI for this.
5.  **Execution & Logging**: Every agent task is logged as an `Agent Run`, and each message is stored as an `Agent Message`. Tool calls are logged in `Agent Tool Call`.

## How It Works

1.  **Trigger**: An agent run is initiated either manually (via Agent Console or Agent Chat), on a schedule, or by a DocType event.
2.  **Agent Preparation**: The `AgentManager` class loads the agent's configuration, including its instructions and tools.
3.  **Tool Serialization**: The `sdk_tools.py` module converts the Huf tools into a format that the AI provider's SDK can understand.
4.  **Execution**: The `run_agent_sync` function sends the prompt, conversation history, and available tools to the AI model via the selected provider.
5.  **Tool Use**: If the AI decides to use a tool, the `on_invoke_tool` handler executes the corresponding Python function (e.g., `handle_get_list`, `handle_create_document`, or a custom function).
6.  **Response**: The result of the tool's execution is sent back to the AI, which then formulates a final response.
7.  **Logging**: The entire process, including the final response and any tool calls, is logged in the corresponding doctypes (`Agent Run`, `Agent Message`, `Agent Tool Call`).

### 1. AI Provider

Stores credentials for different AI service providers.

-   **Python Class**: `AIProvider(Document)`
-   **File**: `huf/huf/doctype/ai_provider/ai_provider.py`

**Fields:**

| Label          | Fieldname      | Type       | Description                               |
| :------------- | :------------- | :--------- | :---------------------------------------- |
| **Provide Name** | `provide_name` | Data       | The unique name of the provider (e.g., OpenAI). |
| **API Key**    | `api_key`      | Password   | The API key for the provider.             |

### 2. AI Model

Defines a specific AI model available from a provider.

-   **Python Class**: `AIModel(Document)`
-   **File**: `huf/huf/doctype/ai_model/ai_model.py`

**Fields:**

| Label        | Fieldname    | Type | Description                               |
| :----------- | :----------- | :--- | :---------------------------------------- |
| **Model Name** | `model_name` | Data | The name of the model (e.g., `gpt-4-turbo`). |
| **Provider**   | `provider`   | Link | A link to the `AI Provider` DocType.      |

### 3. Agent Tool Function

Defines a function or "tool" that an agent can use. This is the core of the agent's capabilities.

-   **Python Class**: `AgentToolFunction(Document)`
-   **File**: `huf/huf/doctype/agent_tool_function/agent_tool_function.py`

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

### 4. Agent

The main DocType for creating an AI agent.

-   **Python Class**: `Agent(Document)`
-   **File**: `huf/huf/doctype/agent/agent.py`

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

### 5. Agent Conversation

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

### 6. Agent Message

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

### 7. Agent Run

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

---

## Core Classes and Methods

The primary logic is located in the `huf/ai` directory.

### `agent_integration.py`

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

### `conversation_manager.py`

This file handles the persistence of conversation history.

-   **Class: `ConversationManager`**
    -   `get_or_create_conversation(self, ...)`: Finds the active `Agent Conversation` for a given session or creates a new one.
    -   `add_message(self, ...)`: Creates a new `Agent Message` document and links it to the current conversation.
    -   `get_conversation_history(self, ...)`: Fetches the last N messages from the conversation to provide context to the AI.

### `sdk_tools.py`

This file acts as a bridge between Huf's `Agent Tool Function` DocType and the `agents` SDK's `FunctionTool` class.

-   **Method: `create_agent_tools(agent)`**
    -   Iterates through the tools linked to an `Agent` and uses `create_function_tool` to build them.
-   **Method: `create_function_tool(...)`**
    -   The factory that constructs an SDK-compatible `FunctionTool`.
    -   It dynamically creates an `on_invoke_tool` async handler that calls the appropriate Python function when the AI decides to use a tool.
-   **Method: `handle_get_list`, `handle_create_document`, etc.**
    -   These are the actual functions that get executed when a standard DocType tool is called. They contain the logic to interact with the Frappe database (e.g., `frappe.get_list`, `frappe.get_doc`) and format the response in a way the AI can understand.

### `tool_functions.py`

This file contains the low-level functions that directly perform Frappe database operations.

-   **Methods**: `get_document`, `create_document`, `update_document`, `delete_document`, `submit_document`, `get_list`, etc.
-   These functions are the final step in the tool-use chain, wrapping `frappe.client` or `frappe.get_doc` calls to ensure data is fetched, created, or modified correctly and with proper permissions checks.
