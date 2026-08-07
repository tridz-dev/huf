# DocType reference (generated)

**Generated file — do not hand-edit.** Regenerate with `python3 docs/reference/generate_doctypes.py`. Source of truth is `huf/huf/doctype/*/*.json`; if this file and the schema ever disagree, the schema wins and this file is stale — regenerate it.

73 DocTypes as of this generation.

## Agent

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent/agent.json`
- **Naming**: field:agent_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent_name` | Data | required | A unique name for this agent. |
| `provider` | Link -> AI Provider | required | The AI provider that will power this agent (e.g., OpenAI, OpenRouter). |
| `model` | Link -> AI Model | required | The specific AI model to use from the selected provider (e.g., gpt-4-turbo). |
| `tts_model` | Link -> AI Model |  | Specific model for Text-to-Speech (Audio Generation). If unset, defaults to the provider's default TTS model. |
| `tts_voice` | Data |  | Voice to use for TTS (e.g. alloy, echo, onyx). |
| `prompt_mode` | Select -> Local
Template |  | How this agent's prompt is managed. 'Local' uses the instructions field below. 'Template' links to a reusable Agent Prompt. |
| `agent_prompt` | Link -> Agent Prompt |  | Link to a reusable prompt template from the Agent Prompt library. |
| `prompt_version_locked` | Check |  | If checked, this agent will stay on the prompt version it was attached to, ignoring newer versions. |
| `template_version_at_attach` | Int |  | The version number of the prompt template when it was attached to this agent. |
| `copied_from_prompt` | Link -> Agent Prompt |  | If this agent was detached from a template, this tracks the original prompt for traceability. |
| `copied_from_summary_prompt` | Link -> Agent Summary Prompt |  | If this agent was detached from a summary prompt template, this tracks the original summary prompt for traceability. |
| `instructions` | Code |  | The system prompt or instructions that define the agent's personality, goals, and constraints. This is the core logic of the agent. |
| `starter_prompts` | Table -> Agent Starter Prompt |  | Up to 3 starter prompts shown to users when starting a chat with this agent. |
| `temperature` | Float |  | What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic. |
| `agent_tool` | Table -> Agent Tool |  | The set of tools this agent is allowed to use to interact with the system. |
| `agent_mcp_server` | Table -> Agent MCP Server |  | External MCP servers this agent can use for additional tools |
| `top_p` | Float |  | An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of the tokens with top_p probability mass. So 0.1 means only the tokens comprising the top 10% probability mass are considered.  We generally recommend altering this or temperature but not both. |
| `async` | Check |  | Async |
| `run_immediately` | Check |  | When disabled, runs are queued to avoid holding web workers during long LLM and tool calls. Enable only for trusted calls that require a direct response. |
| `disabled` | Check |  | If checked, this agent will be disabled and will not run. |
| `allow_chat` | Check |  | If checked, this agent can be interacted with in the Agent Chat window. |
| `persist_conversation` | Check |  | If checked, the conversation history with this agent will be saved and loaded for future sessions. |
| `agent_knowledge` | Table -> Agent Knowledge |  | Knowledge Sources |
| `agent_skill` | Table -> Agent Skill |  | Reusable skill bundles attached to this agent. |
| `context_strategy` | Select -> Summarize
FIFO
None |  | Choose 'Summarize' to compress old messages via an LLM, or 'FIFO' to simply drop the oldest messages. |
| `history_limit` | Int |  | Max messages before strategy triggers. |
| `summary_ratio` | Float |  | Fraction of history to compress (e.g., 0.7 = 70%). |
| `summary_model` | Link -> AI Model |  | Dedicated lightweight model for this task. |
| `summary_prompt_mode` | Select -> Local
Template |  | How this agent's conversation summary prompt is managed. 'Local' uses the summary prompt field below. 'Template' links to a reusable Agent Summary Prompt. |
| `summary_prompt_template` | Link -> Agent Summary Prompt |  | Link to a reusable summary prompt template from the Agent Summary Prompt library for conversation summarization. |
| `summary_prompt_version_locked` | Check |  | If checked, this agent will stay on the summary prompt version it was attached to, ignoring newer versions. |
| `summary_template_version_at_attach` | Int |  | The version number of the summary prompt template when it was attached to this agent. |
| `summary_prompt` | Code |  | The prompt used to summarize conversation history when the context strategy is 'Summarize'. Leave blank to use the system default. |
| `max_knowledge_tokens` | Int |  | Maximum tokens to use for injected knowledge context. |
| `max_turns` | Int |  | Consecutive actions in a single run. |
| `reasoning_mode` | Select -> Auto
Off
On |  | Auto delegates to provider/model defaults. On forces reasoning. Off disables reasoning. |
| `reasoning_effort` | Select -> Auto
Low
Medium
High |  | Portable effort level for reasoning models (low, medium, high). |
| `reasoning_budget_tokens` | Int |  | Explicit token budget for thinking models (primarily Anthropic extended thinking). |
| `reasoning_summary` | Select -> None
Concise
Detailed |  | Reasoning summary preference (for supported Response APIs). |
| `description` | Small Text |  | A short summary describing what this agent does or is designed for. |
| `last_run` | Datetime |  | Last Run |
| `total_run` | Int |  | Total Run |
| `persist_user_history` | Check |  | When checked, Doc Event and Scheduled runs create / maintain conversation history per initiating user (or trigger owner). If unchecked, a single shared history is used. |
| `provider_brand` | Data |  | Provider Brand |
| `enable_multi_run` | Check |  | Enables multi-step planning and execution. If enabled, the agent will analyze the request to create a step-by-step plan (or use a Default Plan) and execute them sequentially. |
| `enable_prompt_caching` | Check |  | Enable prompt caching to cache repeated prompt content and reduce token costs. Only works with supported providers (OpenAI, Anthropic, Bedrock, Deepseek). |
| `cache_control_type` | Select -> ephemeral
auto |  | Cache control type: 'ephemeral' for Anthropic (charges for cache writes), 'auto' for OpenAI/Deepseek (automatic caching). |
| `cache_system_message` | Check |  | Cache the system message/instructions to avoid re-sending them on every request. |
| `cache_conversation_history` | Check |  | Cache conversation history messages to reduce token usage in multi-turn conversations. |
| `default_plan` | Table -> Agent Orchestration Plan |  | Default Plan |
| `allow_guest` | Check |  | If checked, this agent can be run by Guest users (via API). |
| `allowed_users` | Table MultiSelect -> Agent User |  | Allowed Users |
| `allowed_roles` | Table MultiSelect -> Agent Role |  | Allowed Roles |
| `enable_conversation_data` | Check |  | If enabled, the agent can store key-value pairs in the conversation context. |
| `inject_conversation_data` | Check |  | Auto-injects all active memory items into the LLM system prompt on every turn. Disabling this avoids 'Context Bloat' (saving tokens/cost and improving speed) and allows on-demand access strictly through the 'get_conversation_data' tool. |
| `conversation_data_api_permission` | Select -> 
Read
Write |  | Select API access level. 'Read' allows reading only. 'Write' allows reading and writing. |
| `enable_memory` | Check |  | Enable long-term, scoped memory for this agent. |
| `memory_policy` | Link -> Memory Policy |  | Policy governing memory capture and retrieval. |
| `enable_memory_search_tool` | Check |  | Automatically provide the agent with a tool to search memory records. |
| `enable_memory_write_tool` | Check |  | Automatically provide the agent with a tool to save new memory records. |
| `image_generation_model` | Link -> AI Model |  | Optional: Link specific Model for Image generation tool otherwise default model of the Agent's provider will be used |
| `agent_color` | Data |  | This color will be used to display as the background color of Agent Avatar in Agent Chat. Enter color code including #, ex: #6366F1  |
| `autonaming_of_conversation_title` | Check |  | If enabled, the conversation title will be automatically updated based on the initial context. |
| `stt_model` | Link -> AI Model |  | Specific model for Speech-to-Text (Audio Transcription). If unset, defaults to the provider's default STT model. |
| `allow_file_upload` | Check |  | Allow users to attach files (documents, images) in chat for this agent. |
| `enable_ocr` | Check |  | Route uploaded documents through the OCR extraction pipeline instead of vision/local extraction only. |
| `max_upload_size_mb` | Int |  | Maximum size (in MB) for a single uploaded file. Capped by the global 25 MB limit. |
| `allow_code_execution` | Check |  | Explicit second confirmation enabling the Python Code Execution tool for this agent. The tool stays inert until this is checked and an Execution Profile is selected. |
| `execution_profile` | Link -> Execution Profile |  | Execution Profile that caps modules, network, filesystem, broker capabilities, and resource limits for code runs. If unset, the Code Execution tool remains inert. |
| `execution_shared_dir_limit_mb` | Int |  | Optional per-agent cap (MB) on the per-conversation shared directory. Leave blank to use the Execution Profile default. |
| `allow_ssh` | Check |  | Explicitly allow this agent to use allowlisted SSH Connections. |
| `ssh_connections` | Table -> Agent SSH Connection |  | SSH Connections |
| `max_context_chars` | Int |  | Maximum characters allowed for tool results before truncating and applying include_reference context policy. |
| `show_tool_execution_details` | Check |  | Enable to display tool execution status and responses in the agent output. This includes whether each tool call is completed and its corresponding result. |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |
| `is_system` | Check |  | Is System |

## Agent Chat

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_chat/agent_chat.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `chat_ui` | HTML |  | Chat UI |
| `agent` | Link -> Agent |  | Agent |

## Agent Console (single)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_console/agent_console.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent_name` | Link -> Agent |  | Agent |
| `prompt` | Code |  | Prompt |
| `response` | Code |  | Response |
| `provider` | Data |  | Provider |
| `model` | Data |  | Model |

## Agent Context Artifact

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_context_artifact/agent_context_artifact.json`
- **Naming**: format:ART-{####}

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `agent_run` | Link -> Agent Run |  | Agent Run |
| `artifact_type` | Select -> JSON
File
Text |  | Artifact Type |
| `summary` | Small Text |  | Summary |
| `payload_json` | Code |  | Payload JSON |
| `payload_file` | Attach |  | Payload File |
| `reference_doctype` | Link -> DocType |  | Reference DocType |
| `reference_name` | Dynamic Link |  | Reference Name |
| `visibility` | Select -> user_visible
model_visible
ui_only
audit_only
developer_only |  | Visibility |
| `context_policy` | Select -> include_full
include_summary
include_reference
include_on_demand
exclude
transient_only
token_budgeted
provider_cached |  | Context Policy |
| `token_estimate` | Int |  | Token Estimate |
| `expires_on` | Datetime |  | Expires On |

## Agent Conversation

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_conversation/agent_conversation.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `title` | Data |  | Auto-generated title based on the first few interactions of the conversation. |
| `summary` | Long Text |  | Rolling summary of the conversation context, used when the history limit is exceeded. |
| `agent` | Link -> Agent |  | The AI Agent configuration used for this conversation. |
| `model` | Link -> AI Model |  | The specific AI model (e.g., GPT-4) used by the agent during this session. |
| `created_at` | Datetime |  | Timestamp when the conversation started. |
| `last_activity` | Datetime |  | Timestamp of the most recent message or activity in this conversation. |
| `is_active` | Check |  | Indicates if the conversation is currently active. Archived conversations may be read-only. |
| `total_messages` | Int |  | Total count of messages exchanged in this conversation. |
| `total_input_tokens` | Int |  | Cumulative number of input tokens sent to the LLM. |
| `total_output_tokens` | Int |  | Cumulative number of output tokens received from the LLM. |
| `total_tokens` | Int |  | Total token usage (Input + Output) for this conversation. |
| `total_cost` | Currency |  | Estimated total cost of the conversation based on model pricing. |
| `session_id` | Data | required | Unique identifier for the session, often linked to a browser session or API client. |
| `channel` | Data |  | The communication channel (e.g., 'API', 'WhatsApp', 'Desk'). |
| `external_id` | Data |  | Optional external reference ID (e.g., a WhatsApp phone number or external user ID). |
| `conversation_data` | JSON |  | Persistent memory store for the agent. Contains structured key-value pairs (user preferences, constraints, etc.) that survive summarization. |

## Agent Execution Approval

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_execution_approval/agent_execution_approval.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent_tool_call` | Link -> Agent Tool Call | required | The agent tool call that is paused pending this approval. |
| `execution_kind` | Select -> code_execution
ssh_exec |  | Execution Kind |
| `requested_capability` | Data |  | The broker capability (dot-string) the sandbox requested, e.g. doc.create or http.request. |
| `code_ref` | Data |  | Hash / artifact reference of the code to be executed. Never stores raw code. |
| `status` | Select -> Pending
Approved
Rejected
Expired |  | Status |
| `expires_on` | Datetime |  | When this approval request expires if left undecided. |
| `approver_role` | Link -> Role |  | Optional role whose members may approve this execution. |
| `approver_users` | Table MultiSelect -> Agent User |  | Specific users who may approve this execution. |
| `decided_by` | Link -> User |  | Decided By |
| `decided_at` | Datetime |  | Decided At |
| `comment` | Small Text |  | Comment |

## Agent Function Params (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_function_params/agent_function_params.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `label` | Data | required | Label |
| `fieldname` | Data | required | Fieldname |
| `type` | Select -> string
integer
number
float
boolean
object
array | required | Type |
| `required` | Check |  | Required |
| `description` | Small Text |  | Description |
| `options` | Small Text |  | Options |
| `child_table_name` | Data |  | Child Table Name |

## Agent Knowledge (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_knowledge/agent_knowledge.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `knowledge_source` | Link -> Knowledge Source | required | Knowledge Source |
| `mode` | Select -> Mandatory
Optional | required | Mode |
| `priority` | Int |  | Priority |
| `max_chunks` | Int |  | Max Chunks |
| `token_budget` | Int |  | Token Budget |
| `description` | Small Text |  | Description |

## Agent MCP Server (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_mcp_server/agent_mcp_server.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `mcp_server` | Link -> MCP Server | required | MCP Server |
| `enabled` | Check |  | Enabled |
| `server_url` | Data |  | Server URL |
| `tool_count` | Int |  | Number of tools available from this MCP server |

## Agent Message

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_message/agent_message.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `user` | Data |  | User |
| `conversation_index` | Int |  | Index in Conversation |
| `content` | Code |  | Content |
| `kind` | Select -> 
Message
Tool Call
Tool Result
Status
Error
Image
Audio
Video |  | Kind |
| `role` | Select -> user
tool
agent
system |  | Role |
| `session_id` | Data |  | Session ID |
| `is_agent_message` | Check |  | Is Agent Message |
| `provider` | Link -> AI Provider |  | Provider |
| `model` | Link -> AI Model |  | Model |
| `agent` | Link -> Agent |  | Agent |
| `agent_run` | Link -> Agent Run |  | Run |
| `status` | Select -> 
Started
Queued
Completed
Failed |  | Status |
| `tool_call` | Link -> Agent Tool Call |  | Tool Calll |
| `tool_name` | Data |  | Tool Name |
| `tool_args` | JSON |  | Tool Args |
| `tool_status` | Data |  | Tool Status |
| `tool_call_id` | Long Text |  | Tool Call ID |
| `tool_calls` | JSON |  | Tool Calls |
| `raw_payload` | JSON |  | Raw Provider Payload |
| `content_type` | Select -> 
Text
JSX
Mermaid
Markdown
Artifact
HTML
Image |  | Content Type |
| `generated_image` | Attach Image |  | Generated Image |
| `generated_audio` | Attach |  | Generated Audio |
| `generated_video` | Attach |  | Generated Video |
| `tts_model` | Link -> AI Model |  | AI Model used for Text-to-Speech in this audio message. |
| `tts_voice` | Data |  | Voice to use for TTS (e.g. alloy, echo, onyx). |
| `stt_model` | Link -> AI Model |  | AI model used for Speech-to-Text transcription in this audio message. |
| `voice_message` | Attach |  | Voice Message |
| `context_policy` | Select -> include_full
include_summary
include_reference
include_on_demand
exclude
transient_only
token_budgeted
provider_cached |  | Context Policy |
| `record_kind` | Select -> message
tool_call
tool_result
retrieval_context
result_snapshot
artifact
summary
status
error
debug_trace |  | Record Kind |
| `context_summary` | Small Text |  | Context Summary |
| `reference_doctype` | Data |  | Reference DocType |
| `reference_name` | Data |  | Reference Name |
| `visibility` | Select -> user_visible
model_visible
ui_only
audit_only
developer_only |  | Visibility |
| `token_estimate` | Int |  | Token Estimate |

## Agent Orchestration

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_orchestration/agent_orchestration.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent` | Link -> Agent |  | Agent |
| `status` | Select -> Planned
Running
Paused
Completed
Failed
Cancelled |  | Status |
| `current_step` | Int |  | Current Step |
| `last_run_at` | Datetime |  | Last Run |
| `error_log` | Small Text |  | Error Log |
| `agent_orchestration_plan` | Table -> Agent Orchestration Plan |  | Plan |
| `scratchpad` | Code |  | Scratchpad |
| `parent_run` | Link -> Agent Run |  | Parent Run |
| `conversation` | Link -> Agent Conversation |  | conversation |

## Agent Orchestration Plan (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_orchestration_plan/agent_orchestration_plan.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `step_index` | Int |  | Step Index |
| `status` | Select -> pending
in_progress
done
failed |  | Status |
| `instruction` | Long Text |  | Instruction |
| `output_ref` | Long Text |  | Output |

## Agent Prompt

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_prompt/agent_prompt.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `title` | Data | required | Title |
| `slug` | Data |  | URL-friendly identifier for this prompt template. Auto-generated from title if left blank. |
| `category` | Link -> Agent Prompt Category |  | Category |
| `description` | Small Text |  | Description |
| `is_active` | Check |  | Whether this prompt template is active and available for use. |
| `is_system` | Check |  | System prompts are managed by HUF and cannot be edited by users. |
| `visibility` | Select -> Public
App
Private |  | Controls who can see and use this prompt template. |
| `tags` | Small Text |  | Comma-separated tags for search and filtering. |
| `prompt_body` | Code | required | The prompt template content. This is the system prompt or instructions text. |
| `version` | Int |  | Version number of this prompt. Incremented on each new version. |
| `is_latest` | Check |  | Marks this as the latest version in the prompt lineage. |
| `previous_version` | Link -> Agent Prompt |  | Link to the previous version of this prompt template. |
| `forked_from` | Link -> Agent Prompt |  | If this prompt was forked from another, link to the original prompt. |
| `prompt_group` | Data |  | Shared identifier across all versions of the same prompt lineage. Auto-set on creation. |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |

## Agent Prompt Category

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_prompt_category/agent_prompt_category.json`
- **Naming**: field:category_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `category_name` | Data | required | Category Name |
| `description` | Small Text |  | Description |
| `icon` | Data |  | Icon |
| `color` | Data |  | Hex color code for the category badge, e.g. #6366F1 |
| `parent_category` | Link -> Agent Prompt Category |  | Optional parent category for hierarchical grouping. |

## Agent Role (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_role/agent_role.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `role` | Link -> Role |  | Role |

## Agent Run

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_run/agent_run.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `agent` | Link -> Agent |  | Agent |
| `prompt_template` | Link -> Agent Prompt |  | Prompt Template |
| `status` | Select -> 
Started
Queued
Success
Failed |  | Status |
| `error_code` | Data |  | Error Code |
| `error_message` | Long Text |  | Error Message |
| `response` | Code |  | Response |
| `prompt` | Code |  | Prompt |
| `sequence` | Int |  | Sequence |
| `runtime_context` | JSON |  | Runtime Context |
| `start_time` | Datetime |  | Time stamp before requesting provider API.  |
| `end_time` | Datetime |  | Time stamp after provider response is completely generated. |
| `input_tokens` | Int |  | Number of tokens fed into the model for this response.   |
| `usage_snapshot` | JSON |  | Normalized telemetry snapshot. Null values mean the provider did not report that metric. |
| `reasoning_snapshot` | JSON |  | Reasoning telemetry snapshot containing requested vs resolved policies, native parameters, and fallback details. |
| `output_tokens` | Int |  | Number of tokens in the model response.   |
| `cached_tokens` | Int |  | Number of cached tokens that were reused from prompt cache (reduces cost). |
| `cost` | Float |  | Cost of generating this response. Might not be accurate. |
| `cost_source` | Select -> unknown
provider_reported
custom
litellm |  | Cost Source |
| `cost_calculation_status` | Select -> calculated
unavailable
failed |  | Cost Calculation Status |
| `provider` | Link -> AI Provider |  | Provider |
| `model` | Link -> AI Model |  | Model |
| `parent_run` | Link -> Agent Run |  | Parent Run |
| `is_child` | Check |  | Is child |
| `agent_orchestration` | Link -> Agent Orchestration |  | Agent Orchestration |
| `reference_doctype` | Link -> DocType |  | Reference DocType |
| `reference_name` | Dynamic Link |  | Reference Name |
| `call_recording` | Attach |  | Call Recording |
| `knowledge_sources_used` | JSON |  | Knowledge Sources Used |
| `chunks_injected` | Int |  | Chunks Injected |
| `flow_run` | Link -> Flow Run |  | Flow Run |
| `flow_node_id` | Data |  | Flow Node ID |
| `flow_id` | Data |  | Flow ID |
| `run_kind` | Select -> agent
tool
orchestrator |  | Run Kind |

## Agent Run Analytics Rollup

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_run_analytics_rollup/agent_run_analytics_rollup.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `bucket_start` | Datetime |  | Bucket Start |
| `granularity` | Select -> hour
day |  | Granularity |
| `dimension_key` | Data |  | Dimension Key |
| `agent` | Link -> Agent |  | Agent |
| `provider` | Link -> AI Provider |  | Provider |
| `model` | Link -> AI Model |  | Model |
| `run_kind` | Data |  | Run Kind |
| `run_count` | Int |  | Run Count |
| `success_count` | Int |  | Success Count |
| `failed_count` | Int |  | Failed Count |
| `input_tokens` | Int |  | Input Tokens |
| `output_tokens` | Int |  | Output Tokens |
| `cached_tokens` | Int |  | Cached Tokens |
| `total_cost` | Float |  | Total Cost |
| `duration_ms_sum` | Float |  | Duration Sum (ms) |
| `duration_count` | Int |  | Duration Count |
| `last_recomputed_at` | Datetime |  | Last Recomputed At |

## Agent Run Feedback

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_run_feedback/agent_run_feedback.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `feedback` | Select -> 
Thumbs Up
Thumbs Down |  | Feedback |
| `comments` | Small Text |  | Comments |
| `agent` | Link -> Agent |  | Agent |
| `provider` | Link -> AI Provider |  | Provider |
| `model` | Link -> AI Model |  | Model |
| `agent_message` | Link -> Agent Message |  | Agent Message |

## Agent Settings (single)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_settings/agent_settings.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `default_provider` | Link -> AI Provider |  | Default Provider |
| `default_model` | Link -> AI Model |  | Default Model |
| `skill_destinations` | JSON |  | JSON list of common skill destinations. Example: {"huf-skills": {"repo_url": "https://github.com/tridz-dev/huf-skills", "path": "skills", "ref": "main"}} |
| `last_skill_scans` | JSON |  | Last Skill Scans |

## Agent Skill (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_skill/agent_skill.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `skill` | Link -> Skill | required | Skill |
| `mode` | Select -> Mandatory
Optional | required | Mode |
| `auto_load` | Check |  | Auto Load |
| `priority` | Int |  | Priority |
| `description` | Small Text |  | Override the skill description shown to this agent. |

## Agent SSH Connection (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_ssh_connection/agent_ssh_connection.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `ssh_connection` | Link -> SSH Connection | required | SSH Connection |
| `host` | Data |  | Host |
| `username` | Data |  | Username |
| `enabled` | Check |  | Connection Enabled |

## Agent Starter Prompt (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_starter_prompt/agent_starter_prompt.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `prompt_text` | Small Text | required | Prompt Text |

## Agent Summary Prompt

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_summary_prompt/agent_summary_prompt.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `title` | Data | required | Title |
| `slug` | Data |  | URL-friendly identifier for this summary prompt template. Auto-generated from title if left blank. |
| `category` | Link -> Agent Summary Prompt Category |  | Category |
| `description` | Small Text |  | Description |
| `is_active` | Check |  | Whether this summary prompt template is active and available for use. |
| `is_system` | Check |  | System prompts are managed by HUF and cannot be edited by users. |
| `visibility` | Select -> Public
App
Private |  | Controls who can see and use this summary prompt template. |
| `tags` | Small Text |  | Comma-separated tags for search and filtering. |
| `prompt_body` | Code | required | The summary prompt template content. This is the prompt text used to summarize conversation history. |
| `version` | Int |  | Version number of this summary prompt. Incremented on each new version. |
| `is_latest` | Check |  | Marks this as the latest version in the summary prompt lineage. |
| `previous_version` | Link -> Agent Summary Prompt |  | Link to the previous version of this summary prompt template. |
| `forked_from` | Link -> Agent Summary Prompt |  | If this summary prompt was forked from another, link to the original prompt. |
| `prompt_group` | Data |  | Shared identifier across all versions of the same summary prompt lineage. Auto-set on creation. |

## Agent Summary Prompt Category

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_summary_prompt_category/agent_summary_prompt_category.json`
- **Naming**: field:category_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `category_name` | Data | required | Category Name |
| `description` | Small Text |  | Description |
| `icon` | Data |  | Icon |
| `color` | Data |  | Hex color code for the category badge, e.g. #6366F1 |
| `parent_category` | Link -> Agent Summary Prompt Category |  | Optional parent category for hierarchical grouping. |

## Agent Tool (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_tool/agent_tool.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `tool` | Link -> Agent Tool Function | required | Tool |
| `type` | Data |  | Type |
| `description` | Small Text |  | Description |

## Agent Tool Call

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_tool_call/agent_tool_call.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent_run` | Link -> Agent Run |  | Agent Run |
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `tool_args` | JSON |  | Tool Args |
| `tool_result` | JSON |  | Tool Result |
| `call_id` | Long Text |  | Call ID |
| `error_message` | Small Text |  | Error Message |
| `execution_kind` | Data |  | Execution Kind |
| `status` | Select -> Started
Queued
Completed
Failed |  | Status |
| `tool` | Data |  | Tool Name |
| `is_mcp_tool` | Check |  | Is MCP Tool |
| `mcp_server` | Link -> MCP Server |  | MCP Server |
| `execution_profile` | Link -> Execution Profile |  | Execution Profile that governed this code execution call. |
| `ssh_connection` | Link -> SSH Connection |  | SSH Connection |
| `execution_profile_snapshot` | JSON |  | Snapshot of the governing execution policy captured at call time so later edits do not change the audit meaning of this record. |
| `code_ref` | Data |  | Hash / artifact reference of the executed payload. Never stores the raw command or code inline. |
| `exit_status` | Select -> 
Ok
Timeout
OOM
Error
Killed |  | How the sandboxed execution terminated. |
| `resource_usage` | JSON |  | Measured resource usage for the run (cpu_s, wall_s, mem_mb_peak, output_bytes). |
| `limits_hit` | Check |  | Set when the execution hit one or more of its resource limits (wall/CPU/memory/output). |

## Agent Tool Function

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_tool_function/agent_tool_function.json`
- **Naming**: field:tool_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `tool_name` | Data | required | Tool Name |
| `description` | Small Text | required | Description |
| `types` | Select -> 
Get Document
Get Multiple Documents
Get List
Create Document
Create Multiple Documents
Update Document
Update Multiple Documents
Delete Document
Delete Multiple Documents
Submit Document
Cancel Document
Get Amended Document
Custom Function
App Provided
Attach File to Document
Get Report Result
Get Value
Set Value
GET
POST
Run Agent
Client Side Tool
Get Conversation Data
Set Conversation Data
Load Conversation Data
Perplexity Search
Code Execution
Save Memory Record
Search Memory Records
Get Memory Record
Archive Memory Record
Promote Memory to Knowledge |  | Types |
| `reference_doctype` | Link -> DocType |  | Reference DocType |
| `required_permission` | Select -> 
read
write
create
delete
submit
cancel |  | Permission level required to use this tool |
| `is_read_only` | Check |  | If checked, this tool does not modify data |
| `allowed_for_guest` | Check |  | If checked, Guest users can use this tool |
| `parameters` | Table -> Agent Function Params |  | Parameters |
| `params` | JSON |  | Params JSON |
| `function_definition` | JSON |  | Function Definition |
| `function_path` | Data |  | Function Path |
| `pass_parameters_as_json` | Check |  | Pass parameters as JSON |
| `provider_app` | Data |  | Provider App |
| `service` | Data |  | Integration service key this tool belongs to (e.g. frappe_cloud) |
| `base_url` | Data |  | Optional base URL that will be prefixed to the URL provided by the agent |
| `http_headers` | Table -> Agent Tool HTTP Header |  | HTTP Headers |
| `agent` | Link -> Agent |  | Agent |
| `tool_type` | Link -> Agent Tool Type | required | Tool Type |
| `function_name` | Data |  | Function Name |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |

## Agent Tool HTTP Header (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_tool_http_header/agent_tool_http_header.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `key` | Data |  | Key |
| `value` | Data |  | Value |

## Agent Tool Type

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_tool_type/agent_tool_type.json`
- **Naming**: field:name1

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `name1` | Data | required | Name |

## Agent Trigger

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_trigger/agent_trigger.json`
- **Naming**: field:trigger_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `trigger_name` | Data | required | Trigger Name |
| `agent` | Link -> Agent | required | Agent |
| `trigger_type` | Select -> 
Schedule
Doc Event
Webhook
App Event
Manual |  | Trigger Type |
| `disabled` | Check |  | Disabled |
| `status` | Select -> 
Draft
Active
Disabled
Error |  | Status |
| `interval_count` | Int |  | Interval Count |
| `reference_doctype` | Link -> DocType |  | Reference Doctype |
| `doc_event` | Select -> 
before_insert
after_insert
validate
before_save
after_save
before_submit
on_submit
on_update
after_submit
on_cancel
before_rename
after_rename
on_trash
after_delete |  | Doc Event |
| `condition` | Code |  | Condition |
| `webhook_key` | Data |  | Webhook Key |
| `webhook_slug` | Data |  | Webhook Slug |
| `app_name` | Data |  | App Name |
| `event_name` | Data |  | Event Name |
| `last_execution` | Datetime |  | Last Execution |
| `next_execution` | Datetime |  | Next Execution |
| `metadata` | JSON |  | MetaData |
| `disabled_reason` | Small Text |  | Disabled Reason |
| `is_virtual` | Check |  | Is Virtual |
| `source_system` | Data |  | Source System |
| `scheduled_interval` | Select -> 
Hourly
Daily
Weekly
Monthly
Yearly |  | Scheduled Interval |
| `prompt_field` | Select |  | Enter the fieldname from the Reference DocType that contains the user's instructions. |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |
| `file_attachments` | Table -> Agent Trigger Attachment |  | Fetch files from specific DocFields or Child Tables |

## Agent Trigger Attachment (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_trigger_attachment/agent_trigger_attachment.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `source_type` | Select -> DocField
Child Table Field | required | Source Type |
| `child_table` | Select |  | Child Table |
| `field_name` | Data | required | Attach Field Name |

## Agent User (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/agent_user/agent_user.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `user` | Link -> User |  | User |

## AI Model

- **Module**: Huf
- **Schema**: `huf/huf/doctype/ai_model/ai_model.json`
- **Naming**: field:model_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `provider` | Link -> AI Provider | required | Provider |
| `model_name` | Data | required | Model Name |
| `modalities` | Data |  | Select one or more supported modalities / tasks for this model. Used to filter model pickers (e.g. image generation, TTS, transcription, document OCR/vision). |
| `supports_reasoning` | Check |  | Check to force reasoning support on for this model (overriding automatic LiteLLM detection). |
| `reasoning_config_override` | Code |  | Optional JSON object to override reasoning capabilities (e.g. supports_thinking_blocks, supported_efforts). |
| `use_custom_pricing` | Check |  | Check this to activate the custom prices below. When unchecked, LiteLLM's automatic pricing is used regardless of what is entered below. |
| `input_cost_per_1m_tokens` | Float |  | Cost in USD per 1 million prompt/input tokens. E.g. enter 2.50 for $2.50 per 1M tokens. Enter 0 for free/self-hosted models. |
| `output_cost_per_1m_tokens` | Float |  | Cost in USD per 1 million completion/output tokens. E.g. enter 10.00 for $10.00 per 1M tokens. |
| `cached_input_cost_per_1m_tokens` | Float |  | Optional. Cost for prompt cache reads (cache hits) in USD per 1M tokens. E.g. Anthropic charges $0.30/1M for cache reads vs $3.00/1M for regular input. Leave as 0 if not applicable. |

## AI Provider

- **Module**: Huf
- **Schema**: `huf/huf/doctype/ai_provider/ai_provider.json`
- **Naming**: field:provider_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `provider_name` | Data | required | Provider Name |
| `api_key` | Password |  | API Key |
| `provider_brand` | Select -> openai
anthropic
google
openrouter
xai
groq
mistral
deepseek
perplexity
cohere
huggingface
elevenlabs
amazon-bedrock
azure
alibaba
togetherai
meta
ollama
lmstudio
fireworks-ai
cerebras
deepinfra
google-vertex
nvidia
moonshot
ai21
baseten
cloudflare-workers-ai
clarifai
nomic
replicate
sagemaker
stability-ai
vllm
watsonx
other | required | Provider Brand |
| `is_local_llm` | Check |  | Is Local LLM |
| `url` | Data |  | URL |
| `port` | Int |  | PORT |
| `api_base_url` | Data |  | e.g. http://host.docker.internal:11434 for Ollama, or https://api.moonshot.cn/v1 for Moonshot China |

## Elevenlabs Settings (single)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/elevenlabs_settings/elevenlabs_settings.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `agent_id` | Data |  | Agent ID |
| `provider` | Link -> AI Provider |  | Provider |
| `webhook_secret` | Password |  | webhook_secret |

## Execution Profile

- **Module**: Huf
- **Schema**: `huf/huf/doctype/execution_profile/execution_profile.json`
- **Naming**: field:profile_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `profile_name` | Data | required | A unique, human-readable name for this execution profile. |
| `is_builtin` | Check |  | If checked, this is a built-in profile shipped with Huf. Built-in profiles are reused across agents and snapshotted at execution time. |
| `disabled` | Check |  | If checked, this profile is disabled and cannot be used for new executions. |
| `approval_mode` | Select -> Auto Approve
Ask Every Time
Never Allow |  | How executions under this profile are approved. 'Ask Every Time' creates an Agent Execution Approval record and pauses the tool call until approved. |
| `filesystem_policy` | Select -> None
Scratch Only
Shared Directory |  | Filesystem access granted to the sandboxed interpreter. |
| `network_policy` | Link -> Network Access Policy |  | Optional network egress allowlist applied to the sandbox broker's http.request capability. |
| `allowed_modules` | JSON |  | List of stdlib/library module names the sandboxed interpreter is allowed to import. |
| `max_wall_time_s` | Int |  | Maximum wall-clock time (seconds) a single execution may run. |
| `max_cpu_seconds` | Int |  | Maximum CPU time (seconds) a single execution may consume. |
| `max_memory_mb` | Int |  | Maximum memory (MB) the sandboxed interpreter may allocate. |
| `max_output_bytes` | Int |  | Maximum combined stdout/stderr size (bytes) captured from an execution. |
| `permissions` | Table -> Execution Profile Permission |  | Capabilities the sandbox broker is allowed to invoke back into Frappe under the acting user's permissions. |

## Execution Profile Permission (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/execution_profile_permission/execution_profile_permission.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `capability` | Data | required | Dot-string capability this profile grants to the sandbox broker, e.g. doc.read, doc.create, email.send, http.request. |
| `reference_doctype` | Link -> DocType |  | Optional DocType scope for the capability (e.g. limit doc.read to a specific DocType). |
| `is_read_only` | Check |  | If checked, this capability only permits read operations. |

## Flow Definition

- **Module**: Huf
- **Schema**: `huf/huf/doctype/flow_definition/flow_definition.json`
- **Naming**: field:flow_id

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `flow_id` | Data | required | Flow ID |
| `flow_name` | Data | required | Flow Name |
| `status` | Select -> Draft
Active
Archived |  | Status |
| `version` | Int |  | Version |
| `schema_version` | Int |  | Schema Version |
| `definition_json` | JSON | required | Definition JSON |
| `is_system` | Check |  | Is System |
| `updated_by` | Link -> User |  | Updated By |
| `updated_at` | Datetime |  | Updated At |

## Flow Run

- **Module**: Huf
- **Schema**: `huf/huf/doctype/flow_run/flow_run.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `flow_definition` | Link -> Flow Definition | required | Flow Definition |
| `flow_id` | Data |  | Flow ID |
| `flow_version` | Int |  | Flow Version |
| `mode` | Select -> Normal
Agentic |  | Mode |
| `status` | Select -> Queued
Running
Waiting Approval
Waiting User
Success
Failed |  | Status |
| `trigger_type` | Select -> Manual
Webhook
Schedule
Doc Event
Gateway |  | Trigger Type |
| `current_node_id` | Data |  | Current Node ID |
| `hop_count` | Int |  | Hop Count |
| `max_hops` | Int |  | Max Hops |
| `last_agent_run` | Link -> Agent Run |  | Last Agent Run |
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `context_json` | JSON |  | Context JSON |
| `trigger_payload` | JSON |  | Trigger Payload |
| `waiting` | JSON |  | Waiting |
| `last_error` | Small Text |  | Last Error |
| `started_at` | Datetime |  | Started At |
| `completed_at` | Datetime |  | Completed At |

## Frappe Cloud Cached Bench (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/frappe_cloud_cached_bench/frappe_cloud_cached_bench.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `bench_name` | Data | required | Bench Name |
| `app_version` | Data |  | App Version |

## Frappe Cloud Cached Site (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/frappe_cloud_cached_site/frappe_cloud_cached_site.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `site_name` | Data | required | Site Name |
| `bench` | Data |  | Bench |

## Gateway

- **Module**: Huf
- **Schema**: `huf/huf/doctype/gateway/gateway.json`
- **Naming**: field:gateway_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `gateway_name` | Data | required | Gateway name |
| `provider` | Select -> WhatsApp
Messenger
Instagram
Telegram
Slack
Discord
Email
SMS
Google Chat
VK
WeCom
Microsoft Teams | required | Channel |
| `is_enabled` | Check |  | Enabled |
| `integration_settings` | Link -> Integration Settings |  | Existing integration that owns this channel's credentials. VK and WeCom gateways require it; use its Password credential rows for the adapter's documented keys. |
| `execution_user` | Link -> User |  | The least-privileged Huf user used when this gateway starts an Agent or Flow. Never use Administrator. |
| `description` | Small Text |  | What this gateway is for |
| `direct_policy` | Select -> Disabled
Pairing
Allow list
Open |  | Direct messages are denied unless an approved Gateway Access Entry matches. Pairing creates a pending request but never executes the triggering message. |
| `room_policy` | Select -> Disabled
Allow list
Open |  | Rooms/channels are denied unless an approved room access entry matches. |
| `room_sender_policy` | Select -> Allow list
Open |  | Applies after room admission. Direct-message pairing never grants room access. |
| `mention_required` | Check |  | Require mention in rooms |
| `pairing_ttl_minutes` | Int |  | Pairing request expiry (minutes) |
| `default_target_type` | Select -> 
Agent
Flow |  | When no route matches, send to |
| `default_agent` | Link -> Agent |  | Default agent |
| `default_flow` | Link -> Flow Definition |  | Default flow |
| `last_event_at` | Datetime |  | Last event |
| `last_error` | Small Text |  | Last error |

## Gateway Access Entry

- **Module**: Huf
- **Schema**: `huf/huf/doctype/gateway_access_entry/gateway_access_entry.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `gateway` | Link -> Gateway | required | Gateway |
| `entry_type` | Select -> Sender
Room | required | Applies to |
| `provider` | Data | required | Provider |
| `external_id` | Data | required | Canonical provider ID |
| `state` | Select -> Pending
Approved
Revoked | required | State |
| `expires_at` | Datetime |  | Expires at |
| `display_label` | Data |  | Display label |
| `approved_by` | Link -> User |  | Approved by |
| `approved_at` | Datetime |  | Approved at |
| `revoked_at` | Datetime |  | Revoked at |
| `notes` | Small Text |  | Notes |

## Gateway Binding

- **Module**: Huf
- **Schema**: `huf/huf/doctype/gateway_binding/gateway_binding.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `gateway` | Link -> Gateway | required | Gateway |
| `priority` | Int | required | Priority |
| `is_enabled` | Check |  | Enabled |
| `match_type` | Select -> Any conversation
Direct message
Room or channel
Thread
Sender | required | When a message comes from |
| `match_value` | Data |  | Provider identifier to match. Leave blank only for Any conversation. |
| `target_type` | Select -> Agent
Flow | required | Target |
| `agent` | Link -> Agent |  | Agent |
| `flow` | Link -> Flow Definition |  | Flow |
| `description` | Small Text |  | What this route does |

## Gateway Event

- **Module**: Huf
- **Schema**: `huf/huf/doctype/gateway_event/gateway_event.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `gateway` | Link -> Gateway | required | Gateway |
| `idempotency_key` | Data | required | Idempotency key |
| `provider_event_id` | Data |  | Provider event ID |
| `status` | Select -> Received
Rejected
Unrouted
Queued
Running
Succeeded
Failed |  | Status |
| `received_at` | Datetime |  | Received at |
| `verified_sender` | Check |  | Sender verified |
| `sender_id` | Data |  | Sender |
| `conversation_id` | Data |  | Provider conversation |
| `thread_id` | Data |  | Provider thread |
| `message_text` | Small Text |  | Message |
| `binding` | Link -> Gateway Binding |  | Matched route |
| `target_type` | Select -> Agent
Flow |  | Target type |
| `target_agent` | Link -> Agent |  | Target agent |
| `target_flow` | Link -> Flow Definition |  | Target flow |
| `agent_run` | Link -> Agent Run |  | Agent run |
| `flow_run` | Link -> Flow Run |  | Flow run |
| `raw_payload` | JSON |  | Provider payload |
| `error_message` | Small Text |  | Error |

## Groq Settings (single)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/groq_settings/groq_settings.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `provider` | Link -> AI Provider |  | Provider |
| `api_url` | Data |  | API URL |
| `method` | Select -> POST
GET |  | Method |
| `auth_type` | Select -> Bearer Token
API Key Header
None |  | Auth Type |
| `file_param` | Data |  | File Param |
| `model` | Data |  | Model |
| `enabled` | Check |  | Enabled |
| `api_key` | Password |  | API Key |
| `response_path` | Data |  | Response Path |

## HUF App

- **Module**: Huf
- **Schema**: `huf/huf/doctype/huf_app/huf_app.json`
- **Naming**: field:app_id

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `app_id` | Data | required | App ID |
| `title` | Data | required | Title |
| `description` | Small Text |  | Description |
| `route` | Data | required | Route |
| `icon` | Data |  | Icon |
| `category` | Data |  | Category |
| `sort_order` | Int |  | Sort Order |
| `version` | Data |  | Version |
| `launch_mode` | Select -> 
Route |  | Launch Mode |
| `required_huf_version` | Data |  | Required HUF Version |
| `permission_method` | Data |  | Permission Method |
| `exposed_tables` | Small Text |  | Exposed Tables |
| `enabled` | Check |  | Enabled |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |
| `manifest_hash` | Data |  | Manifest Hash |
| `last_synced_at` | Datetime |  | Last Synced At |
| `sync_status` | Select -> 
Active
Invalid
Missing |  | Sync Status |
| `sync_error` | Small Text |  | Sync Error |

## Huf Data Table

- **Module**: Huf
- **Schema**: `huf/huf/doctype/huf_data_table/huf_data_table.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `table_name` | Data | required | Table Name |
| `doctype_name` | Data | required | DocType Name |
| `autoname_method` | Select -> Autoincrement
Hash
By Field |  | Naming Method |
| `title_field_name` | Data |  | Title Field |
| `description` | Small Text |  | Description |
| `table_group` | Data |  | Table Group |
| `icon` | Data |  | Icon |
| `field_count` | Int |  | Field Count |
| `record_count` | Int |  | Record Count |
| `is_active` | Check |  | Is Active |

## Huf Role

- **Module**: Huf
- **Schema**: `huf/huf/doctype/huf_role/huf_role.json`
- **Naming**: field:role_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `role_name` | Data | required | Role Name |
| `description` | Small Text |  | Description |
| `is_system_role` | Check |  | System roles cannot be deleted or renamed. |
| `frappe_role` | Link -> Role |  | The underlying Frappe role that enforces DocType-level permissions. |
| `permissions` | Table -> Huf Role Permission |  | Capabilities |

## Huf Role Permission (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/huf_role_permission/huf_role_permission.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `capability` | Select -> agent.use
agent.create
agent.edit
agent.delete
agent.view_all
chat.use
chat.view_own
chat.view_all
knowledge.use
knowledge.create
knowledge.manage
tools.use
tools.create
tools.manage
flows.use
flows.create
flows.manage
system.providers.manage
system.models.manage
system.mcp.manage
system.integrations.manage
system.settings.manage
data.tables.manage
data.records.create
data.records.view_own
data.records.view_all
data.records.edit_own
data.records.edit_all
users.invite
users.manage
roles.manage
execution_profile.manage
network_access_policy.manage
execution.approve
code_execution.run
ssh_connection.manage
ssh.run
ssh.approve
docker.run | required | Capability |
| `label` | Data |  | Label |

## Huf User Role

- **Module**: Huf
- **Schema**: `huf/huf/doctype/huf_user_role/huf_user_role.json`
- **Naming**: field:user

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `user` | Link -> User | required | User |
| `full_name` | Data |  | Full Name |
| `huf_role` | Link -> Huf Role | required | Huf Role |
| `enabled` | Check |  | Enabled |
| `invited_by` | Link -> User |  | Invited By |
| `invited_on` | Datetime |  | Invited On |

## Integration Credential (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/integration_credential/integration_credential.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `key` | Data | required | Key |
| `value` | Password | required | Value |
| `description` | Small Text |  | Description |

## Integration Recipient (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/integration_recipient/integration_recipient.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `recipient_name` | Data | required | A human-friendly label for this recipient (e.g. John Doe, Sales Alerts, Engineering Team) |
| `recipient_id` | Data | required | Service-specific ID: Telegram Chat ID, Slack User/Channel ID, Discord Channel ID, email address, etc. |
| `user` | Link -> User |  | Optionally link to a Frappe User account |

## Integration Service

- **Module**: Huf
- **Schema**: `huf/huf/doctype/integration_service/integration_service.json`
- **Naming**: field:service_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `service_name` | Data | required | Service Name |
| `category` | Select -> Communication
Project Management
Search
Data Sources
Finance
Google
Developer
Cloud
Media
Other | required | Category |
| `description` | Small Text |  | Description |
| `documentation_url` | Data |  | Documentation URL |
| `required_credentials` | JSON |  | JSON array of required credential keys. Example: [{"key": "api_key", "label": "API Key", "required": true}] |
| `is_builtin` | Check |  | Is Built-in |

## Integration Settings

- **Module**: Huf
- **Schema**: `huf/huf/doctype/integration_settings/integration_settings.json`
- **Naming**: format:{service}-{####}

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `service` | Link -> Integration Service | required | Integration Service |
| `is_active` | Check |  | Is Active |
| `is_default` | Check |  | Use this as the default credential set for this service |
| `credentials` | Table -> Integration Credential | required | Add all required credentials for this integration |
| `recipients` | Table -> Integration Recipient |  | Define named recipients for this service. The agent can look up a recipient by name and get their service-specific ID (e.g. Telegram Chat ID, Slack User ID, Discord Channel ID). |
| `telegram_agent` | Link -> Agent |  | HUF Agent that will respond to messages received by this Telegram bot |
| `telegram_auto_setup_webhook` | Check |  | Automatically call setWebhook when this document is saved |
| `telegram_webhook_secret` | Password |  | Webhook Secret |
| `telegram_webhook_url` | Data |  | Webhook URL |
| `telegram_webhook_status` | Small Text |  | Webhook Status |
| `telegram_last_webhook_setup` | Datetime |  | Last Webhook Setup |
| `last_used` | Datetime |  | Last Used |
| `last_error` | Small Text |  | Last Error |

## Knowledge Input

- **Module**: Huf
- **Schema**: `huf/huf/doctype/knowledge_input/knowledge_input.json`
- **Naming**: Random

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `knowledge_source` | Link -> Knowledge Source | required | Knowledge Source |
| `input_type` | Select -> File
Text
URL | required | Input Type |
| `file` | Attach |  | Indexing time depends on file size and your embedding provider's speed. If indexing times out, increase litellm_embedding_timeout in site_config (default: 600s). |
| `file_name` | Data |  | File Name |
| `file_type` | Data |  | File Type |
| `text` | Long Text |  | Text |
| `url` | Data |  | URL |
| `source_hash` | Data |  | Source Hash |
| `chunks_created` | Int |  | Chunks Created |
| `character_count` | Int |  | Character Count |
| `processed_at` | Datetime |  | Processed At |
| `error_message` | Small Text |  | Error Message |
| `status` | Select -> Pending
Processing
Indexed
Error |  | Status |

## Knowledge Source

- **Module**: Huf
- **Schema**: `huf/huf/doctype/knowledge_source/knowledge_source.json`
- **Naming**: field:source_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `source_name` | Data | required | Source Name |
| `description` | Small Text |  | Description |
| `knowledge_type` | Select -> sqlite_fts
sqlite_vec
sqlite_hybrid
chroma
pgvector
redis
zvec
weaviate
faiss
pinecone | required | Knowledge Type |
| `scope` | Select -> Site
Workspace
Agent
Global | required | Scope |
| `embedding_model` | Data |  | LiteLLM model identifier, e.g. openai/text-embedding-3-small |
| `vector_dimension` | Int |  | Must match the embedding model output dimensionality |
| `embedding_provider` | Link -> AI Provider |  | AI Provider for API key resolution |
| `chroma_mode` | Select -> File
Server |  | File: store on disk. Server: connect to a running Chroma server. |
| `chroma_host` | Data |  | Hostname or IP of the Chroma server (only used in Server mode) |
| `chroma_port` | Int |  | Port of the Chroma server (only used in Server mode) |
| `chroma_ssl` | Check |  | Enable if your Chroma server uses HTTPS |
| `pgvector_connection_mode` | Select -> External PostgreSQL
Site PostgreSQL |  | External PostgreSQL is recommended for MariaDB-backed Frappe sites. Site PostgreSQL is only valid when the Frappe site database is PostgreSQL. |
| `pgvector_table_name` | Data |  | PGVector table used for this knowledge source. Keep this stable after indexing. |
| `pgvector_distance_metric` | Select -> cosine
l2
inner_product |  | Vector distance metric used for retrieval. |
| `pgvector_host` | Data |  | Host |
| `pgvector_port` | Int |  | Port |
| `pgvector_database` | Data |  | Database |
| `pgvector_user` | Data |  | User |
| `pgvector_password` | Password |  | Password |
| `pgvector_sslmode` | Select -> prefer
require
disable
allow
verify-ca
verify-full |  | SSL Mode |
| `pgvector_index_type` | Select -> none
hnsw
ivfflat |  | Preferred vector index type. Backend implementation may create or validate this later. |
| `advanced_config` | Code |  | Backend-specific tuning parameters (e.g. HNSW settings). Controlled by the backend schema. |
| `storage_mode` | Select -> Frappe File | required | Storage Mode |
| `sqlite_file` | Attach |  | SQLite File |
| `sqlite_file_path` | Data |  | SQLite File Path |
| `chunk_size` | Int |  | Chunk Size |
| `chunk_overlap` | Int |  | Chunk Overlap |
| `status` | Select -> Pending
Indexing
Ready
Error
Rebuilding |  | Status |
| `last_indexed_at` | Datetime |  | Last Indexed At |
| `total_chunks` | Int |  | Total Chunks |
| `total_inputs` | Int |  | Total Inputs |
| `index_size_bytes` | Int |  | Index Size (bytes) |
| `error_message` | Small Text |  | Error Message |
| `disabled` | Check |  | Disabled |
| `test_connection` | Button |  | Test Connection |
| `source_app` | Data |  | Source App |
| `source_file` | Data |  | Source File |

## MCP Server

- **Module**: Huf
- **Schema**: `huf/huf/doctype/mcp_server/mcp_server.json`
- **Naming**: field:server_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `server_name` | Data | required | Unique identifier for this MCP server (e.g., 'gmail', 'github', 'frappe-erp') |
| `description` | Small Text |  | What capabilities this MCP server provides |
| `enabled` | Check |  | Enabled |
| `tool_namespace` | Data |  | Optional prefix for tool names (e.g., 'gmail' results in 'gmail.send_email') |
| `timeout_seconds` | Int |  | Request timeout for MCP server calls |
| `transport_type` | Select -> http
sse | required | Transport Type |
| `server_url` | Data | required | MCP server endpoint URL (e.g., 'https://mcp.example.com/mcp') |
| `auth_type` | Select -> none
api_key
bearer_token
custom_header
oauth |  | Auth Type |
| `auth_header_name` | Data |  | Header name for authentication (e.g., 'Authorization', 'X-API-Key') |
| `auth_header_value` | Password |  | The API key, bearer token, or header value (stored encrypted) |
| `oauth_status` | Select -> Not Connected
Connected
Token Expired |  | OAuth Status |
| `oauth_connect_button` | Button |  | Connect |
| `oauth_disconnect_button` | Button |  | Disconnect |
| `oauth_scope` | Small Text |  | Space-separated OAuth scopes (e.g. 'read write'). Leave blank for provider default. |
| `oauth_extra_authorize_params` | Small Text |  | Additional URL parameters for the authorization endpoint (e.g. {"user_scope": "...", "access_type": "offline"}) |
| `oauth_redirect_uri` | Data |  | Optional: Override the callback URL for strict providers or local testing. Leave blank to use HUF's default: {site_url}/mcp-oauth-callback. |
| `oauth_authorization_endpoint` | Data |  | e.g. https://higgsfield.ai/oauth/authorize |
| `oauth_token_endpoint` | Data |  | e.g. https://higgsfield.ai/oauth/token |
| `oauth_client_id` | Small Text |  | Client ID |
| `oauth_client_secret` | Password |  | Stored encrypted. Leave blank if using PKCE-only public client. |
| `oauth_access_token` | Password |  | Set automatically after OAuth flow. Stored encrypted. |
| `oauth_refresh_token` | Password |  | Set automatically after OAuth flow. Stored encrypted. |
| `oauth_token_expires_at` | Datetime |  | Token Expires At |
| `oauth_discovery_status` | Select -> Not Started
In Progress
Ready
Failed |  | Discovery Status |
| `oauth_resource_metadata_url` | Data |  | Resource Metadata URL |
| `oauth_authorization_server` | Data |  | Authorization Server |
| `oauth_registration_endpoint` | Data |  | Discovered DCR endpoint. |
| `oauth_client_registration_method` | Data |  | Client Registration Method |
| `oauth_metadata_json` | Code |  | Discovered Metadata JSON |
| `oauth_last_discovered_at` | Datetime |  | Last Discovered At |
| `oauth_discovery_error` | Small Text |  | Discovery Error |
| `custom_headers` | Table -> MCP Server Header |  | Additional HTTP headers to send with MCP requests |
| `sync_tools_button` | Button |  | Fetch available tools from the MCP server |
| `tools` | Table -> MCP Server Tool |  | Manage enabled tools from this server |
| `last_sync` | Datetime |  | Last Synced |
| `available_tools` | Code |  | Cached list of tools available from this MCP server |
| `enable_auto_sync` | Check |  | Automatically sync tools periodically |
| `auto_sync_interval` | Int |  | Interval in hours to auto-sync tools |

## MCP Server Header (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/mcp_server_header/mcp_server_header.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `header_name` | Data | required | Header Name |
| `header_value` | Data | required | Header Value |

## MCP Server Tool (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/mcp_server_tool/mcp_server_tool.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `tool_name` | Data | required | Tool Name |
| `enabled` | Check |  | Enabled |
| `description` | Small Text |  | Description |
| `parameters` | Code |  | Parameters |

## Memory Policy

- **Module**: Huf
- **Schema**: `huf/huf/doctype/memory_policy/memory_policy.json`
- **Naming**: field:policy_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `policy_name` | Data | required | Policy Name |
| `description` | Small Text |  | What this policy is for and what it does — shown to whoever is choosing a policy for an agent. |
| `enabled` | Check |  | Enabled |
| `agent` | Link -> Agent |  | Agent |
| `scope_type` | Select -> Conversation
User
Role
Agent
Workspace
Site
Global | required | Scope Type |
| `scope_key` | Data |  | Optional default scope key for this policy. If empty, runtime context decides. |
| `capture_mode` | Select -> Manual
Agent Suggested
Automatic | required | Capture Mode |
| `learning_agent` | Link -> Agent |  | Optional dedicated agent to handle background memory extraction |
| `approval_required` | Check |  | Approval Required |
| `default_status` | Select -> Draft
Active | required | Default Status |
| `allowed_record_types` | Small Text |  | Optional newline-separated allowed record types. Empty means all types are allowed. |
| `inject_mode` | Select -> Never
Relevant Only
Always
Tool Only | required | Inject Mode |
| `max_records` | Int |  | Max Records |
| `token_budget` | Int |  | Token Budget |
| `allow_agent_write` | Check |  | Allow Agent Write |
| `allow_user_scope_write` | Check |  | Allow User Scope Write |
| `allow_role_scope_write` | Check |  | Allow Role Scope Write |
| `allow_agent_scope_write` | Check |  | Allow Agent Scope Write |
| `allow_site_scope_write` | Check |  | Allow Site Scope Write |
| `auto_promote_to_knowledge` | Check |  | Auto Promote to Knowledge |
| `knowledge_source` | Link -> Knowledge Source |  | Knowledge Source |
| `promotion_min_confidence` | Float |  | Min Confidence |
| `promotion_min_importance` | Float |  | Min Importance |
| `ttl_days` | Int |  | TTL Days |
| `metadata_json` | JSON |  | Metadata JSON |

## Memory Record

- **Module**: Huf
- **Schema**: `huf/huf/doctype/memory_record/memory_record.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `title` | Data | required | Title |
| `record_type` | Select -> Fact
Preference
Research Note
Decision
Extracted Data
State
Summary
Policy Hint
Observation
Insight
Custom | required | Record Type |
| `status` | Select -> Draft
Active
Archived
Expired
Superseded
Rejected | required | Status |
| `scope_type` | Select -> Conversation
User
Role
Agent
Workspace
Site
Global | required | Scope Type |
| `scope_key` | Data | required | Concrete scope identifier. |
| `visibility` | Select -> Private
Shared with Agent
Shared with Role
Site
Global | required | Visibility |
| `summary_text` | Text Editor | required | Summary Text |
| `data_json` | JSON |  | Canonical structured payload for this memory/data record. |
| `agent` | Link -> Agent |  | Agent |
| `conversation` | Link -> Agent Conversation |  | Conversation |
| `run` | Link -> Agent Run |  | Run |
| `source_type` | Select -> Conversation
Run
Manual
Event
Scheduled
Imported
Tool Output
Extracted | required | Source Type |
| `source_message` | Data |  | Source Message |
| `raw_context_excerpt` | Long Text |  | Raw Context Excerpt |
| `confidence` | Float |  | Confidence |
| `importance_score` | Float |  | Importance Score |
| `tags` | Small Text |  | Tags |
| `effective_from` | Datetime |  | Effective From |
| `effective_until` | Datetime |  | Effective Until |
| `ttl_days` | Int |  | TTL Days |
| `supersedes_memory_record` | Link -> Memory Record |  | Supersedes Memory Record |
| `metadata_json` | JSON |  | Metadata JSON |
| `promote_to_knowledge` | Check |  | Promote to Knowledge |
| `knowledge_source` | Link -> Knowledge Source |  | Knowledge Source |
| `knowledge_input` | Link -> Knowledge Input |  | Knowledge Input |
| `projection_status` | Select -> Not Indexed
Queued
Projected
Error
Removed |  | Projection Status |
| `last_projected_at` | Datetime |  | Last Projected At |
| `projection_error` | Small Text |  | Projection Error |

## Network Access Policy

- **Module**: Huf
- **Schema**: `huf/huf/doctype/network_access_policy/network_access_policy.json`
- **Naming**: field:policy_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `policy_name` | Data | required | A unique, human-readable name for this network access policy. |
| `rules` | Table -> Network Access Policy Rule |  | Allowlist of destination host/IP, port, and protocol combinations the sandbox broker may reach. |

## Network Access Policy Rule (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/network_access_policy_rule/network_access_policy_rule.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `host_or_cidr` | Data | required | Allowed destination hostname, IP address, or CIDR range (e.g. api.example.com or 10.0.0.0/8). |
| `port_range` | Data |  | Optional allowed port or port range (e.g. 443 or 1000-2000). Leave blank to allow any port. |
| `protocol` | Select -> https
http
tcp |  | Protocol |

## OpenAI Settings (single)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/openai_settings/openai_settings.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `provider` | Link -> AI Provider |  | Provider |
| `api_url` | Data |  | API URL |
| `method` | Select -> POST
GET |  | Method |
| `auth_type` | Select -> Bearer Token
API Key Header
None |  | Auth Type |
| `file_param` | Data |  | File Param |
| `model` | Data |  | Model |
| `enabled` | Check |  | Enabled |
| `api_key` | Password |  | API Key |
| `response_path` | Data |  | Response Path |

## Skill

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill/skill.json`
- **Naming**: field:skill_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `skill_name` | Data | required | Machine identifier for this skill. Use snake_case. |
| `title` | Data | required | Title |
| `skill_category` | Link -> Skill Category |  | Skill Category |
| `description` | Small Text |  | Description |
| `status` | Select -> Draft
Active
Error
Disabled | required | Status |
| `source_type` | Select -> Local
Git
Common Destination
App Provided | required | Source Type |
| `auto_load` | Check |  | If checked, this skill is loaded automatically when attached to an agent in Mandatory mode. |
| `skill_icon` | Data |  | Skill Icon |
| `source_url` | Data |  | Git URL or common destination URL this skill was imported from. |
| `source_path` | Data |  | Sub-path inside the source repository. |
| `source_ref` | Data |  | Branch, tag or commit reference. |
| `provider_app` | Data |  | App name when this skill is provided via the huf_skills hook. |
| `author` | Data |  | Author |
| `version` | Data |  | Version |
| `instructions` | Long Text |  | Guidelines injected into the agent system prompt when this skill is loaded. |
| `skill_tools` | Table -> Skill Tool |  | Tools |
| `skill_knowledge` | Table -> Skill Knowledge |  | Knowledge Sources |
| `skill_prompts` | Table -> Skill Prompt |  | Prompts |
| `skill_mcp_servers` | Table -> Skill MCP Server |  | MCP Servers |

## Skill Category

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_category/skill_category.json`
- **Naming**: field:category_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `category_name` | Data | required | Category Name |
| `description` | Small Text |  | Description |
| `icon` | Data |  | Icon |
| `color` | Data |  | Hex color code for the category badge, e.g. #6366F1 |
| `parent_category` | Link -> Skill Category |  | Optional parent category for hierarchical grouping. |

## Skill Import Log

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_import_log/skill_import_log.json`
- **Naming**: hash

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `skill` | Link -> Skill |  | Skill |
| `status` | Select -> Success
Error | required | Status |
| `source_url` | Data |  | Source URL |
| `source_ref` | Data |  | Source Ref |
| `error_message` | Small Text |  | Error Message |

## Skill Knowledge (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_knowledge/skill_knowledge.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `knowledge_source` | Link -> Knowledge Source | required | Knowledge Source |
| `mode` | Select -> Mandatory
Optional | required | Mode |
| `max_chunks` | Int |  | Max Chunks |
| `token_budget` | Int |  | Token Budget |
| `description` | Small Text |  | Description |

## Skill MCP Server (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_mcp_server/skill_mcp_server.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `mcp_server` | Link -> MCP Server | required | MCP Server |
| `enabled` | Check |  | Enabled |

## Skill Prompt (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_prompt/skill_prompt.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `prompt` | Link -> Agent Prompt | required | Prompt |
| `usage` | Select -> System
User | required | Usage |

## Skill Tool (child table)

- **Module**: Huf
- **Schema**: `huf/huf/doctype/skill_tool/skill_tool.json`
- **Naming**: -

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `tool` | Link -> Agent Tool Function | required | Tool |
| `required` | Check |  | Required |
| `description` | Small Text |  | Override the tool description for this skill. |

## SSH Connection

- **Module**: Huf
- **Schema**: `huf/huf/doctype/ssh_connection/ssh_connection.json`
- **Naming**: field:display_name

| Fieldname | Type | Required | Description |
|---|---|---|---|
| `display_name` | Data | required | Display Name |
| `enabled` | Check |  | Enabled |
| `host` | Data | required | Host |
| `port` | Int | required | Port |
| `username` | Data | required | Username |
| `auth_method` | Select -> Password
Private Key | required | Auth Method |
| `password` | Password |  | Password |
| `private_key` | Password |  | Private Key |
| `private_key_passphrase` | Password |  | Private Key Passphrase |
| `host_key_verification` | Select -> Strict (Pinned) | required | Host Key Verification |
| `host_key_fingerprint` | Data |  | Host Key Fingerprint |
| `host_key_type` | Data |  | Host Key Type |
| `host_key_enrolled_by` | Link -> User |  | Host Key Enrolled By |
| `host_key_enrolled_on` | Datetime |  | Host Key Enrolled On |
| `last_tested_on` | Datetime |  | Last Tested On |
| `last_test_status` | Data |  | Last Test Status |
| `key_rotated_on` | Datetime |  | Key Rotated On |
| `last_error` | Small Text |  | Last Error |
