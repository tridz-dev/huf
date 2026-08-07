# Integration tool reference (generated)

**Generated file — do not hand-edit.** Regenerate with `python3 docs/reference/generate_tools.py`. Source of truth is `huf/ai/tools/_registry.py` (`ALL_INTEGRATION_TOOLS`); if this file and the registry ever disagree, the registry wins and this file is stale — regenerate it.

121 registered integration tools across 14 categories as of this generation. Core/standard tools (ocr_document, generate_image, generate_audio, transcribe_audio — re-exported from `huf/ai/sdk_tools.py`) are documented separately in [`../architecture/tools-and-integrations.md`](../architecture/tools-and-integrations.md).

## Builder

### `create_huf_table`

Create a new huf data table (a custom DocType plus registry entry) that agents and flows can then read/write. 'fields' is a JSON list of field definitions, e.g. [{"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1}]. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true. Returns the new DocType name and its live schema. Fails with a clear error if a table with the same name already exists.

- **Function**: `huf.ai.tools.builder.create_huf_table`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `table_name` | string | yes | Human table name, e.g. 'Customer Feedback'. The DocType becomes 'HF <table_name>'. |
  | `fields` | string | yes | JSON list of field definitions [{fieldname, fieldtype, label, reqd, options, ...}] |
  | `description` | string |  | What the table is for |
  | `icon` | string |  | Optional icon name for the table |
  | `autoname_method` | string |  | Naming method (default 'Autoincrement') |
  | `title_field` | string |  | Field to use as document title |
  | `confirm` | boolean |  | false = preview diff only; true = create the table |

### `list_table_rows`

Read rows from an existing huf data table (created with create_huf_table). Read-only. Returns the rows plus the total count for pagination.

- **Function**: `huf.ai.tools.builder.list_table_rows`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `table_name` | string | yes | Human table name or Huf Data Table registry name |
  | `filters` | string |  | JSON filter object or list, e.g. {"status": "Open"} |
  | `fields` | string |  | JSON list of fieldnames to return (default: all) |
  | `limit` | integer |  | Max rows (default 20) |
  | `start` | integer |  | Offset for pagination (default 0) |

### `add_table_row`

Add a row to an existing huf data table. 'data' is a JSON object of fieldname/value pairs matching the table's schema (unknown fields are dropped). Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.add_table_row`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `table_name` | string | yes | Human table name or Huf Data Table registry name |
  | `data` | string | yes | JSON object of fieldname/value pairs, e.g. {"title": "Hello", "status": "Open"} |
  | `confirm` | boolean |  | false = preview diff only; true = insert the row |

### `update_table_row`

Update fields of an existing row in a huf data table. 'data' is a JSON object of fieldname/value pairs; only changed fields are applied. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.update_table_row`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `table_name` | string | yes | Human table name or Huf Data Table registry name |
  | `row_name` | string | yes | Name (ID) of the row to update |
  | `data` | string | yes | JSON object of fieldname/value pairs to change |
  | `confirm` | boolean |  | false = preview diff only; true = apply and save |

### `delete_table_row`

Delete a row from a huf data table. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.delete_table_row`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `table_name` | string | yes | Human table name or Huf Data Table registry name |
  | `row_name` | string | yes | Name (ID) of the row to delete |
  | `confirm` | boolean |  | false = preview diff only; true = delete the row |

### `draft_agent`

Create a new AI Agent in DRAFT state (disabled=1 - it cannot run yet) with a local prompt from 'instructions'. The provider must already exist; if it has no API key configured the draft is still created but the result includes a warning. The agent is chat-enabled by default (allow_chat=true) so it appears in chat pickers once published. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true. Use update_agent_prompt to refine the prompt, attach_agent_tools to give it tools, and publish_agent to enable it. Fails with a clear error if the agent already exists.

- **Function**: `huf.ai.tools.builder.draft_agent`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `agent_name` | string | yes | Unique agent name (also the document ID) |
  | `provider` | string | yes | Existing AI Provider name |
  | `model` | string | yes | Existing AI Model name |
  | `instructions` | string | yes | System prompt / instructions for the agent |
  | `description` | string |  | Short human description of the agent |
  | `allow_chat` | boolean |  | true (default) = chat-enabled so it appears in chat UIs; false = headless/automation-only agent |
  | `confirm` | boolean |  | false = preview diff only; true = create the draft agent |

### `update_agent_prompt`

Update an agent's prompt - either its local instructions or its linked Agent Prompt template (setting agent_prompt switches the agent to Template prompt mode). Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true. System agents (is_system) can only be modified by System Managers.

- **Function**: `huf.ai.tools.builder.update_agent_prompt`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `agent_name` | string | yes | Name of the agent to update |
  | `instructions` | string |  | New local instructions text |
  | `agent_prompt` | string |  | Name of an existing Agent Prompt template to link |
  | `confirm` | boolean |  | false = preview diff only; true = apply and save |

### `attach_agent_tools`

Set the full list of tools attached to an agent. 'tool_names' is the complete proposed set of Agent Tool Function names (it replaces the current list - include existing tools you want to keep). Every tool must already exist. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.attach_agent_tools`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `agent_name` | string | yes | Name of the agent |
  | `tool_names` | string | yes | JSON list of Agent Tool Function names, e.g. ["get_list", "run_flow"] |
  | `confirm` | boolean |  | false = preview diff only; true = apply and save |

### `publish_agent`

Publish a draft agent (flip disabled from 1 to 0) so it can run. Refuses with a remediation message if the agent's provider has no API key configured. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.publish_agent`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `agent_name` | string | yes | Name of the draft agent to publish |
  | `confirm` | boolean |  | false = preview diff only; true = apply and save |

### `create_agent_tool`

Create a WORKING declarative document tool (Agent Tool Function) bound to a DocType. The tool executes immediately — attach it to an agent with attach_agent_tools and it is callable right away. Use this to give agents data tools, e.g. an 'add_row'-style named tool for a huf data table's dynamic doctype like 'HF Social Media Campaign' (types='Create Document'). Parameters are validated against the DocType: Select fields get options auto-filled, unknown fields are dropped (see dropped_params in the result). Custom Function/code/HTTP tools CANNOT be created by this tool. Two-phase contract: call with confirm=false first to preview a diff of the proposed changes; nothing is mutated until you call again with confirm=true.

- **Function**: `huf.ai.tools.builder.create_agent_tool`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `tool_name` | string | yes | Unique tool name (also the document ID) |
  | `description` | string | yes | What the tool does — this is what LLMs will see |
  | `types` | string | yes | Document tool type, one of: Create Document, Create Multiple Documents, Get Document, Get Multiple Documents, Get List, Update Document, Update Multiple Documents, Delete Document, Delete Multiple Documents, Get Value, Set Value |
  | `reference_doctype` | string | yes | DocType the tool operates on, e.g. 'HF Social Media Campaign' for a huf data table |
  | `parameters` | string |  | JSON list of parameter definitions [{fieldname, type, label, required, description}]. fieldnames must exist on the reference_doctype (unknown ones are dropped); Select fields get options auto-filled. type one of: string, integer, number, float, boolean, object, array |
  | `confirm` | boolean |  | false = preview diff only; true = create the tool record |

### `list_provider_options`

List every AI Provider with whether it has an API key configured and which AI Models exist for it, plus a 'suggested' provider+model pair (the first configured provider and its default chat model). Read-only — call this before draft_agent to pick a valid provider/model instead of guessing. API key values are never returned, only a configured true/false flag.

- **Function**: `huf.ai.tools.builder.list_provider_options`

### `ask_user`

Ask the user a structured question in the chat. Returns a fenced 'ask-user' block — include the returned 'block' value VERBATIM in your reply, then STOP and wait for the user's answer. kind is one of yes_no|single_choice|multi_choice|input|textarea; the choice kinds require options as [{id, label, icon?, description?}] (icon must be a supported lucide name; unsupported icons are dropped with a warning). Use this ONLY when structured UI is clearly better than a typed reply: confirming right before executing a mutating plan, choosing from a defined set of options, or collecting a required value. Do NOT use it for greetings, small talk, open-ended questions, or normal conversation — answer those in plain prose.

- **Function**: `huf.ai.tools.ask_user.ask_user`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `question` | string | yes | The question to show the user |
  | `kind` | string | yes | One of: yes_no, single_choice, multi_choice, input, textarea |
  | `options` | string |  | JSON list of options [{id, label, icon?, description?}] — required for single_choice/multi_choice |
  | `allow_free_text` | boolean |  | Allow a free-text answer in addition to options (default true) |
  | `suggested_answers` | string |  | JSON list of suggested free-text answers |
  | `note` | string |  | Optional extra context shown with the question |

## Communication Tools

### `get_integration_recipient`

Look up a named recipient's service-specific ID from Integration Settings. Use this before sending a message to resolve a human name (e.g. 'John Doe', 'Sales Team') to the correct Telegram Chat ID, Slack User/Channel ID, Discord Channel ID, etc. Call this tool first, then pass the returned recipient_id to the relevant send tool.

- **Function**: `huf.ai.tools.recipient.handle_get_recipient`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `service` | string | yes | The service name, e.g. 'telegram', 'slack', 'discord' |
  | `recipient_name` | string | yes | Human-friendly recipient name as stored in Integration Settings, e.g. 'John Doe' |

### `slack_send_message`

Send a message to a Slack channel. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_send_message`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel` | string | yes | Channel ID or name to send the message to |
  | `text` | string | yes | Message text (supports Slack mrkdwn formatting) |

### `slack_send_thread_reply`

Reply to a message thread in a Slack channel. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_send_message_thread`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel` | string | yes | Channel ID or name |
  | `text` | string | yes | Reply text |
  | `thread_ts` | string | yes | Timestamp of the parent message |

### `slack_list_channels`

List all channels in the Slack workspace. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_list_channels`

### `slack_get_channel_history`

Get message history of a Slack channel. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_get_channel_history`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel` | string | yes | Channel ID to fetch history from |
  | `limit` | integer |  | Max messages to fetch (default 100) |

### `slack_search_messages`

Search messages across the Slack workspace. Supports modifiers like from:@user, in:#channel. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_search_messages`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `query` | string | yes | Search query |
  | `limit` | integer |  | Max results (default 20, max 100) |

### `slack_list_users`

List all users in the Slack workspace. Requires SLACK_TOKEN env var.

- **Function**: `huf.ai.tools.slack.handle_list_users`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `limit` | integer |  | Max users to fetch (default 100) |

### `discord_send_message`

Send a message to a Discord channel. Requires DISCORD_BOT_TOKEN env var.

- **Function**: `huf.ai.tools.discord.handle_send_message`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel_id` | string | yes | Discord channel ID |
  | `message` | string | yes | Message text to send |

### `discord_get_messages`

Get message history of a Discord channel. Requires DISCORD_BOT_TOKEN env var.

- **Function**: `huf.ai.tools.discord.handle_get_channel_messages`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel_id` | string | yes | Discord channel ID |
  | `limit` | integer |  | Max messages (default 50) |

### `discord_list_channels`

List all channels in a Discord server. Requires DISCORD_BOT_TOKEN env var.

- **Function**: `huf.ai.tools.discord.handle_list_channels`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `guild_id` | string | yes | Discord server (guild) ID |

### `discord_delete_message`

Delete a message from a Discord channel. Requires DISCORD_BOT_TOKEN env var.

- **Function**: `huf.ai.tools.discord.handle_delete_message`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `channel_id` | string | yes | Discord channel ID |
  | `message_id` | string | yes | Message ID to delete |

### `telegram`

Manage a Telegram bot. Actions: send_message (chat_id or recipient_name, text/message, parse_mode), reply_to_message (chat_id or recipient_name, text/message, reply_to_message_id), send_photo (chat_id or recipient_name, photo/file/file_url, caption), send_document (chat_id or recipient_name, document/file/file_url, caption), edit_message_text (chat_id or recipient_name, message_id, text/message), delete_message (chat_id or recipient_name, message_id), get_updates (offset, limit), get_chat_info (chat_id or recipient_name), get_me, set_webhook (url, secret_token), delete_webhook. Use get_integration_recipient to resolve a human name to a Telegram chat ID.

- **Function**: `huf.ai.tools.telegram.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: send_message\|reply_to_message\|send_photo\|send_document\|edit_message_text\|delete_message\|get_updates\|get_chat_info\|get_me\|set_webhook\|delete_webhook |
  | `chat_id` | string |  | Telegram chat/channel ID (numeric or @username). Alternative to recipient_name. |
  | `recipient_name` | string |  | Human-friendly recipient name from Integration Settings (alternative to chat_id). |
  | `message` | string |  | Message text (alias for text). |
  | `text` | string |  | Message or edited text. |
  | `photo` | string |  | Photo source: Telegram file_id, public URL, or Frappe File docname/file_url. |
  | `document` | string |  | Document source: Telegram file_id, public URL, or Frappe File docname/file_url. |
  | `file` | string |  | Generic file source alias for photo/document. |
  | `file_url` | string |  | Public file URL alias for photo/document. |
  | `caption` | string |  | Caption for photo/document messages. |
  | `parse_mode` | string |  | Text formatting: Markdown, HTML, or MarkdownV2. |
  | `reply_to_message_id` | integer |  | Message ID to reply to. |
  | `message_id` | integer |  | Message ID to edit or delete. |
  | `url` | string |  | Webhook URL for set_webhook. |
  | `secret_token` | string |  | Secret token for webhook verification. |
  | `offset` | integer |  | Update offset for get_updates. |
  | `limit` | integer |  | Max updates for get_updates (max 100). |
  | `disable_notification` | boolean |  | Send message silently. |

## Developer Tools

### `github_list_repos`

List GitHub repositories for the authenticated user. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_list_repos`

### `github_get_repo`

Get details of a GitHub repository. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_get_repo`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `repo_name` | string | yes | Repository (owner/name) |

### `github_create_issue`

Create a GitHub issue. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_create_issue`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `repo_name` | string | yes | Repository (owner/name) |
  | `title` | string | yes | Issue title |
  | `body` | string |  | Issue body |

### `github_create_pr`

Create a GitHub pull request. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_create_pull_request`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `repo_name` | string | yes | Repository (owner/name) |
  | `title` | string | yes | PR title |
  | `body` | string |  | PR description |
  | `head` | string | yes | Head branch |
  | `base` | string | yes | Base branch |

### `github_get_file`

Get file content from a GitHub repository. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_get_file_content`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `repo_name` | string | yes | Repository (owner/name) |
  | `path` | string | yes | File path in repository |

### `github_search_code`

Search code across GitHub. Requires GITHUB_ACCESS_TOKEN env var.

- **Function**: `huf.ai.tools.github.handle_search_code`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `query` | string | yes | Code search query |

### `run_ssh_command`

Run one remote SSH command against an admin-managed SSH Connection that the agent is explicitly allowlisted to use. Supports only non-interactive one-shot command execution in this version; interactive PTY sessions and managed background jobs are not available.

- **Function**: `huf.ai.tools.ssh_execution.run_ssh_command`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `connection` | string | yes | Allowlisted SSH Connection name |
  | `command` | string | yes | One remote shell command to execute without PTY |
  | `timeout_seconds` | integer |  | Optional execution timeout override in seconds |

### `docker_execution`

Manage Docker containers, images, and Compose deployments with bounded, explicit operations. Compose actions operate on an existing compose file; destructive actions require confirm_destructive=true. Supports local socket, Docker contexts, TLS endpoints, or a Frappe SSH Connection.

- **Function**: `huf.ai.tools.docker_execution.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_containers\|list_images\|inspect_container\|logs\|stop_container\|start_container\|restart_container\|remove_container\|pull_image\|run_container\|exec_container\|compose_up\|compose_ps\|compose_logs\|compose_config\|compose_down |
  | `container` | string |  | Container name or ID |
  | `image` | string |  | Image name |
  | `command` | string |  | Command to execute (for exec_container) |
  | `name` | string |  | Name for new container (for run_container) |
  | `ports` | string |  | Ports to publish (comma separated, e.g. '80:80') |
  | `environment` | string |  | Environment variables (comma separated KEY=VALUE entries) |
  | `volumes` | string |  | Bind mounts (comma separated host:container[:mode] entries) |
  | `network` | string |  | Docker network for a new container |
  | `workdir` | string |  | Working directory for run or exec |
  | `user` | string |  | User for a new container |
  | `memory` | string |  | Memory limit for a new container, e.g. 512m |
  | `cpus` | number |  | CPU limit for a new container |
  | `auto_remove` | boolean |  | Remove the container when it exits |
  | `confirm_destructive` | boolean |  | Required confirmation for stop, restart, or remove |
  | `timeout_seconds` | integer |  | Maximum operation time, capped at 300 seconds |
  | `compose_file` | string |  | Path to an existing Docker Compose file |
  | `project_dir` | string |  | Compose project directory |
  | `project_name` | string |  | Compose project name |
  | `services` | string |  | Comma-separated Compose service names |
  | `detach` | boolean |  | Run Compose services in the background (default true) |
  | `build` | boolean |  | Build images before Compose up |
  | `wait` | boolean |  | Wait for services to become healthy |
  | `remove_orphans` | boolean |  | Remove Compose containers not in the file |
  | `remove_volumes` | boolean |  | Remove named volumes during compose_down |
  | `tail` | integer |  | Number of log lines to tail |
  | `connection_string` | string |  | Docker daemon URL (unix://, ssh://, tcp://) |
  | `context_name` | string |  | Docker context name |
  | `ssh_connection` | string |  | Frappe SSH Connection doctype name to use for remote docker execution |
  | `tls_verify` | boolean |  | Enable TLS verification for TCP connections |
  | `tls_ca_cert` | string |  | Path to the CA certificate for a TLS Docker daemon |
  | `tls_cert` | string |  | Path to the client certificate for a TLS Docker daemon |
  | `tls_key` | string |  | Path to the client key for a TLS Docker daemon |

## ERPNext CRM Tools

### `erpnext_crm`

Manage ERPNext built-in CRM (Lead and Opportunity doctypes — part of ERPNext, different from standalone Frappe CRM). Actions: list_leads (status, lead_owner, search, limit), get_lead (name), create_lead (lead_name required; company_name, email_id, mobile_no, lead_owner, type, industry, territory), update_lead (name required; status, lead_owner, email_id, territory), list_opportunities (status, party_name, from_date, limit), create_opportunity (opportunity_from required [Customer/Lead], party_name required; title, opportunity_type, opportunity_amount, sales_stage, probability, expected_closing), update_opportunity (name required; status, opportunity_amount, sales_stage, probability, expected_closing).

- **Function**: `huf.ai.tools.erpnext_crm.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_leads\|get_lead\|create_lead\|update_lead\|list_opportunities\|create_opportunity\|update_opportunity |
  | `name` | string |  | Document name/ID |
  | `lead_name` | string |  | Lead full name |
  | `company_name` | string |  | Company name |
  | `email_id` | string |  | Email address |
  | `mobile_no` | string |  | Mobile number |
  | `lead_owner` | string |  | Assigned user email |
  | `status` | string |  | Status filter or value to set |
  | `territory` | string |  | Territory |
  | `industry` | string |  | Industry |
  | `opportunity_from` | string |  | Opportunity from: Customer or Lead |
  | `party_name` | string |  | Customer or Lead name |
  | `opportunity_amount` | number |  | Opportunity value |
  | `sales_stage` | string |  | Sales stage |
  | `probability` | integer |  | Win probability 0-100 |
  | `expected_closing` | string |  | Expected closing date (YYYY-MM-DD) |
  | `search` | string |  | Search query |
  | `from_date` | string |  | Filter from date |
  | `limit` | integer |  | Max results |

## ERPNext Inventory

### `erpnext_inventory`

Manage ERPNext inventory, items, BOM and stock. Actions: list_items (search, item_group, is_stock_item, limit), get_item (name — item_code), item_prices (item_code, price_list, buying, selling), stock_balance (item_code, warehouse, as_of_date), stock_movements (item_code, warehouse, from_date, to_date, limit), list_stock_entries (stock_entry_type, from_date, to_date, limit), list_warehouses (company, limit), list_delivery_notes (customer, from_date, to_date, limit), list_purchase_receipts (supplier, from_date, to_date, limit), list_boms (item, is_active, is_default, limit), get_bom (name), create_bom (item required, quantity, items list [{item_code, qty, uom, rate}]).

- **Function**: `huf.ai.tools.erpnext_inventory.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_items\|get_item\|item_prices\|stock_balance\|stock_movements\|list_stock_entries\|list_warehouses\|list_delivery_notes\|list_purchase_receipts\|list_boms\|get_bom\|create_bom |
  | `name` | string |  | Document name or item_code |
  | `item_code` | string |  | Item code |
  | `item_group` | string |  | Item group filter |
  | `is_stock_item` | integer |  | 1 for stock items only, 0 for all |
  | `price_list` | string |  | Price list name |
  | `warehouse` | string |  | Warehouse name |
  | `as_of_date` | string |  | Stock balance as of date (YYYY-MM-DD) |
  | `stock_entry_type` | string |  | Material Issue, Material Receipt, Material Transfer, Manufacture |
  | `customer` | string |  | Customer name filter |
  | `supplier` | string |  | Supplier name filter |
  | `item` | string |  | Item code for BOM filter |
  | `is_active` | integer |  | 1 for active BOMs |
  | `is_default` | integer |  | 1 for default BOMs |
  | `quantity` | number |  | BOM quantity |
  | `items` | string |  | JSON list of BOM items [{item_code, qty, uom, rate}] |
  | `from_date` | string |  | Start date (YYYY-MM-DD) |
  | `to_date` | string |  | End date (YYYY-MM-DD) |
  | `search` | string |  | Search query |
  | `company` | string |  | Company name |
  | `limit` | integer |  | Max results |

## ERPNext Reports

### `erpnext_run_report`

Run any ERPNext script or query report by name and get results. Use erpnext_list_reports to discover available report names and their modules. Common reports: 'Balance Sheet', 'Profit and Loss Statement', 'Cash Flow', 'General Ledger', 'Accounts Receivable', 'Accounts Payable', 'Stock Balance', 'Stock Ledger', 'Sales Register', 'Purchase Register', 'Sales Analytics', 'Sales Pipeline Analytics', 'Lead Details'. Pass filters as a JSON object with keys like company, from_date, to_date, fiscal_year, etc.

- **Function**: `huf.ai.tools.erpnext_reports.handle_run_report`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `report_name` | string | yes | Exact report name (case-sensitive). Use erpnext_list_reports to find valid names. |
  | `filters` | string |  | JSON object of filter key-value pairs. E.g. {"company": "My Company", "from_date": "2024-01-01", "to_date": "2024-12-31"} |

### `erpnext_list_reports`

List available ERPNext reports by module. Use this to discover report names before calling erpnext_run_report. Available modules: Accounts, Selling, Buying, Stock, Manufacturing, CRM, Helpdesk, Projects, HR.

- **Function**: `huf.ai.tools.erpnext_reports.handle_list_reports`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `module` | string |  | Module to filter by: Accounts, Selling, Buying, Stock, Manufacturing, CRM, Helpdesk, Projects, HR. Leave empty to list all. |

## ERPNext Tools

### `erpnext`

Manage ERPNext transactions and accounting. Actions: list_sales_invoices (customer, status, from_date, to_date, limit), get_sales_invoice (name), create_sales_invoice (customer required, items list [{item_code,qty,rate}], company, posting_date), list_purchase_invoices (supplier, status, from_date, to_date, limit), get_purchase_invoice (name), list_payments (party_type, party, payment_type, from_date, to_date, limit), create_payment (payment_type required [Receive/Pay], party_type required, party required, paid_amount required; mode_of_payment, invoice_name, source_exchange_rate, target_exchange_rate), list_customers (search, customer_group, limit), get_customer (name), list_quotations (party_name, status, from_date, limit), create_quotation (quotation_to required [Customer/Lead], party_name required, items list, transaction_date, valid_till), list_rfqs (status, from_date, limit), get_ledger (account required, from_date, to_date, party_type, party, limit), create_journal_entry (voucher_type, posting_date, company, user_remark, accounts list [{account, debit_in_account_currency, credit_in_account_currency}]).

- **Function**: `huf.ai.tools.erpnext.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_sales_invoices\|get_sales_invoice\|create_sales_invoice\|list_purchase_invoices\|get_purchase_invoice\|list_payments\|create_payment\|list_customers\|get_customer\|list_quotations\|create_quotation\|list_rfqs\|get_ledger\|create_journal_entry |
  | `name` | string |  | Document name/ID |
  | `customer` | string |  | Customer name |
  | `supplier` | string |  | Supplier name |
  | `party_type` | string |  | Party type: Customer or Supplier |
  | `party` | string |  | Party name |
  | `payment_type` | string |  | Payment type: Receive, Pay, Internal Transfer |
  | `paid_amount` | number |  | Payment amount |
  | `invoice_name` | string |  | Invoice to link payment to |
  | `mode_of_payment` | string |  | Mode of payment |
  | `source_exchange_rate` | number |  | Source exchange rate (if different currency) |
  | `target_exchange_rate` | number |  | Target exchange rate (if different currency) |
  | `account` | string |  | Account name (for get_ledger) |
  | `status` | string |  | Document status filter |
  | `from_date` | string |  | Start date (YYYY-MM-DD) |
  | `to_date` | string |  | End date (YYYY-MM-DD) |
  | `company` | string |  | Company name (defaults to user default) |
  | `posting_date` | string |  | Posting date |
  | `items` | string |  | JSON list of items [{item_code, qty, rate}] |
  | `accounts` | string |  | JSON list of journal accounts [{account, debit_in_account_currency, credit_in_account_currency}] |
  | `voucher_type` | string |  | Journal voucher type |
  | `user_remark` | string |  | Journal entry remark |
  | `quotation_to` | string |  | Quotation for: Customer or Lead |
  | `party_name` | string |  | Customer/Lead name for quotation |
  | `search` | string |  | Search query |
  | `limit` | integer |  | Max results |

## Frappe CRM Tools

### `frappe_crm`

Manage Frappe CRM (standalone app). Actions: list_leads (status, assigned_to, search, limit), get_lead (name), create_lead (first_name required; last_name, email, mobile_no, lead_owner, source, organization, notes), update_lead (name required; any field), list_deals (status, deal_owner, search, limit), get_deal (name), create_deal (organization; or lead to copy from), update_deal (name required; status, deal_value, probability, expected_closure_date), add_note (doctype, docname, content, title), add_task (title, reference_doctype, reference_docname; assigned_to, due_date, priority), list_contacts (search, limit).

- **Function**: `huf.ai.tools.crm.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_leads\|get_lead\|create_lead\|update_lead\|list_deals\|get_deal\|create_deal\|update_deal\|add_note\|add_task\|list_contacts |
  | `name` | string |  | Document name/ID |
  | `first_name` | string |  | Lead first name |
  | `last_name` | string |  | Lead last name |
  | `email` | string |  | Email address |
  | `mobile_no` | string |  | Mobile number |
  | `lead_owner` | string |  | Assigned user email |
  | `organization` | string |  | Company/organization name |
  | `status` | string |  | Status filter or value to set |
  | `search` | string |  | Search query |
  | `doctype` | string |  | DocType for note/task (CRM Lead or CRM Deal) |
  | `docname` | string |  | Document name for note/task |
  | `content` | string |  | Note content |
  | `title` | string |  | Note or task title |
  | `deal_value` | number |  | Deal value amount |
  | `probability` | integer |  | Win probability 0-100 |
  | `limit` | integer |  | Max results |

## Frappe Cloud

### `fc_list_benches`

List Frappe Cloud benches with optional filters.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_benches`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `filters` | string |  | Optional filters dict |

### `fc_get_bench`

Get details of a Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_get_bench`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |

### `fc_create_bench`

Create a new Frappe Cloud bench/release group. Optionally pin it to a dedicated server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_create_bench`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `title` | string | yes | Bench title |
  | `version` | string |  | Frappe version (e.g. Version 16) |
  | `cluster` | string |  | Cluster name (e.g. UAE) |
  | `apps` | string |  | List of apps to add |
  | `server` | string |  | Optional dedicated server name to host the bench on |
  | `saas_app` | string |  | Optional SaaS app name |

### `fc_bench_options`

Get available versions, clusters and apps for creating a new Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_bench_options`
- **Service**: `frappe_cloud`

### `fc_archive_bench`

Archive/delete a Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_archive_bench`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |

### `fc_add_app_to_bench`

Add an app to a Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_add_app_to_bench`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |
  | `app` | string | yes | App name |
  | `source` | string | yes | App source identifier |

### `fc_list_sites`

List Frappe Cloud sites with optional filters.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_sites`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `filters` | string |  | Optional filters dict |

### `fc_site_options`

Get available options for creating a new Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_site_options`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string |  | Bench/release group name |

### `fc_site_plans`

List available plans for a Frappe Cloud bench/release group.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_site_plans`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string |  | Bench/release group name |

### `fc_create_site`

Create a new Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_create_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `apps` | string |  | List of apps to install |
  | `version` | string |  | Frappe version |
  | `domain` | string |  | Domain suffix |
  | `plan` | string |  | Plan name |
  | `bench` | string |  | Bench/release group name |
  | `provider` | string |  | Infrastructure provider |
  | `cluster` | string |  | Cluster name |

### `fc_drop_site`

Archive/delete a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_drop_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `force` | string |  | Force archive even if active |

### `fc_backup_site`

Trigger a backup of a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_backup_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `with_files` | string |  | Include files in backup |

### `fc_download_backup`

List downloadable backups for a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_download_backup`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |

### `fc_migrate_site`

Run migrate on a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_migrate_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `skip_failing_patches` | string |  | Skip failing patches |

### `fc_clear_cache`

Clear cache of a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_clear_cache`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |

### `fc_update_site`

Update a Frappe Cloud site (pull latest app versions).

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_update_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `skip_backups` | string |  | Skip backups before update |

### `fc_clone_site`

Clone a Frappe Cloud site into another bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_clone_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `source_site` | string | yes | Source site name |
  | `bench` | string | yes | Target bench name |

### `fc_add_app_to_site`

Install an app on a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_add_app_to_site`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |
  | `app` | string | yes | App name |
  | `plan` | string |  | Marketplace plan name |

### `fc_get_admin_login_link`

Get an admin login link/session for a Frappe Cloud site.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_get_admin_login_link`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `site_name` | string | yes | Site name |

### `fc_list_webhooks`

List registered Frappe Cloud press webhooks.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_webhooks`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `endpoint` | string |  | Filter by endpoint URL |
  | `limit` | string |  | Max results |

### `fc_available_webhook_events`

List available Frappe Cloud webhook event types.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_available_webhook_events`
- **Service**: `frappe_cloud`

### `fc_add_webhook`

Register a new Frappe Cloud press webhook.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_add_webhook`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `endpoint` | string | yes | Webhook endpoint URL |
  | `secret` | string | yes | Secret token |
  | `events` | string | yes | List of event names |

### `fc_update_webhook`

Update an existing Frappe Cloud press webhook.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_update_webhook`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `name` | string | yes | Webhook document name |
  | `endpoint` | string | yes | Webhook endpoint URL |
  | `events` | string | yes | List of event names |
  | `secret` | string |  | Secret token |

### `fc_delete_webhook`

Delete a Frappe Cloud press webhook.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_delete_webhook`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `name` | string | yes | Webhook document name |

### `fc_list_ssh_keys`

List SSH keys stored in the Frappe Cloud account.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_ssh_keys`
- **Service**: `frappe_cloud`

### `fc_add_ssh_key`

Add an SSH public key to the Frappe Cloud account.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_add_ssh_key`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `key` | string | yes | SSH public key string |

### `fc_mark_ssh_key_default`

Mark an SSH key as default in the Frappe Cloud account.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_mark_ssh_key_default`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `key_name` | string | yes | SSH key document name |

### `fc_get_bench_ssh_certificate`

Get the SSH certificate for a Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_get_bench_ssh_certificate`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |

### `fc_generate_bench_ssh_certificate`

Generate/regenerate the SSH certificate for a Frappe Cloud bench.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_generate_bench_ssh_certificate`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |

### `fc_list_servers`

List Frappe Cloud application and database servers.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_servers`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `filters` | string |  | Optional filters dict, e.g. {"server_type": "App Servers"} |

### `fc_get_server`

Get details of a Frappe Cloud server (App or Database server).

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_get_server`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_get_server_overview`

Get plan and ownership overview for a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_get_server_overview`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_server_options`

Return regions and plans available for creating a new Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_server_options`
- **Service**: `frappe_cloud`

### `fc_server_plans`

List Frappe Cloud server plans for a given server type.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_server_plans`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server_type` | string |  | Server type: Server or Database Server (default: Server) |
  | `cluster` | string |  | Filter plans by cluster |
  | `platform` | string |  | Filter by platform, e.g. x86_64 or arm64 |

### `fc_create_server`

Create a new Frappe Cloud server. Provide only app_plan for a unified server; provide db_plan as well to create separate app and database servers.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_create_server`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `title` | string | yes | Server title |
  | `cluster` | string | yes | Cluster name |
  | `app_plan` | string | yes | Application server plan name |
  | `db_plan` | string |  | Database server plan name (if omitted, creates a unified server) |
  | `auto_increase_storage` | boolean |  | Enable auto-increase storage |

### `fc_archive_server`

Archive/delete a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_archive_server`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_reboot_server`

Reboot a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_reboot_server`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_rename_server`

Rename (change the title of) a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_rename_server`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |
  | `title` | string | yes | New server title |

### `fc_change_server_plan`

Resize/change the plan of a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_change_server_plan`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |
  | `plan` | string | yes | New server plan name |

### `fc_server_usage`

Get current CPU, memory and disk usage for a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_server_usage`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_list_server_benches`

List benches (release groups) running on a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_server_benches`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |

### `fc_list_server_jobs`

List Agent jobs for a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_server_jobs`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |
  | `limit_page_length` | integer |  | Max results |

### `fc_list_server_plays`

List Ansible plays for a Frappe Cloud server.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_server_plays`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `server` | string | yes | Server name |
  | `limit_page_length` | integer |  | Max results |

### `fc_list_bench_jobs`

List Agent jobs for a Frappe Cloud bench/release group.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_bench_jobs`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `bench` | string | yes | Bench name |
  | `limit_page_length` | integer |  | Max results |

### `fc_list_marketplace_apps`

List apps available on the Frappe Cloud Marketplace.

- **Function**: `huf.ai.tools.frappe_cloud.handle_fc_list_marketplace_apps`
- **Service**: `frappe_cloud`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `filters` | string |  | Optional filters dict |
  | `limit` | integer |  | Max results |

## Google Places

### `gplaces_text_search`

Search for places with a free-text query using the Google Places API (New). Supports filters (type, rating, price, open now), location bias/restriction, and pagination. Requires a Google Maps/Places API key in Integration Settings or env (GOOGLE_MAPS_API_KEY, PLACE_API_KEY, GOOGLE_PLACES_API_KEY).

- **Function**: `huf.ai.tools.google_places.handle_gplaces_text_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `query` | string | yes | Free-text search query, e.g. 'vegan restaurants in Lisbon' |
  | `language_code` | string |  | Response language, e.g. 'en', 'fr' |
  | `region_code` | string |  | Region bias as CLDR country code, e.g. 'us', 'in' |
  | `included_type` | string |  | Restrict to a single place type, e.g. 'restaurant', 'museum' |
  | `min_rating` | number |  | Minimum average user rating (0.0-5.0) |
  | `price_levels` | string |  | CSV of PRICE_LEVEL_FREE, PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE |
  | `open_now` | boolean |  | Only return places open at query time |
  | `rank_preference` | string |  | RELEVANCE (default) or DISTANCE (requires location) |
  | `latitude` | number |  | Center latitude for location bias/restriction |
  | `longitude` | number |  | Center longitude for location bias/restriction |
  | `radius` | number |  | Search radius in metres (default 50000, min 1) |
  | `strict_location` | boolean |  | With latitude/longitude: hard-restrict to the circle instead of biasing |
  | `page_size` | integer |  | Results per page, 1-20 (default 10) |
  | `page_token` | string |  | next_page_token from a previous response to fetch the next page |

### `gplaces_place_details`

Get full details for a single place by place_id: contact info, opening hours, photos (resource names for gplaces_place_photo), up to 5 reviews, review summary, accessibility/payment/parking options. Requires a Google Places API key.

- **Function**: `huf.ai.tools.google_places.handle_gplaces_place_details`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `place_id` | string | yes | Google place ID, e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4' |
  | `language_code` | string |  | Response language, e.g. 'en', 'fr' |
  | `region_code` | string |  | Region code as CLDR country code, e.g. 'us' |

### `gplaces_place_photo`

Resolve a photo resource name (from gplaces_place_details photos[].name) to a usable image URL. Requires a Google Places API key.

- **Function**: `huf.ai.tools.google_places.handle_gplaces_place_photo`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `photo_name` | string | yes | Photo resource name, e.g. 'places/PLACE_ID/photos/PHOTO_ID' |
  | `max_height_px` | integer |  | Max image height in pixels (default 800) |
  | `max_width_px` | integer |  | Max image width in pixels (default 800) |
  | `skip_http_redirect` | boolean |  | Default true: return JSON photoUri. False: follow the media redirect manually |

### `gplaces_autocomplete`

Place autocomplete suggestions for a partial input (cities, districts, neighborhoods by default; country-level results are filtered out). Results are cached for 24h. Supports location bias/restriction and origin-based distance sorting. Requires a Google Places API key.

- **Function**: `huf.ai.tools.google_places.handle_gplaces_autocomplete`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `input` | string | yes | Partial place name typed by the user (max 200 chars) |
  | `included_primary_types` | string |  | CSV of primary types (default: locality,sublocality,administrative_area_level_1,administrative_area_level_2,neighborhood) |
  | `language_code` | string |  | Response language, e.g. 'en', 'fr' |
  | `region_code` | string |  | Region bias as CLDR country code, e.g. 'us' |
  | `session_token` | string |  | Session token for billing/session grouping |
  | `include_query_predictions` | boolean |  | Also return query (non-place) predictions |
  | `latitude` | number |  | Center latitude for location bias/restriction |
  | `longitude` | number |  | Center longitude for location bias/restriction |
  | `radius` | number |  | Radius in metres (default 50000, min 1) |
  | `strict_location` | boolean |  | With latitude/longitude: hard-restrict to the circle instead of biasing |
  | `origin_latitude` | number |  | Origin latitude; adds straight-line distance_meters to suggestions |
  | `origin_longitude` | number |  | Origin longitude; adds straight-line distance_meters to suggestions |

### `gplaces_nearby_search`

Search for places near a latitude/longitude using the Google Places API (New). Filter by included/excluded types and rank by popularity or distance. Requires a Google Places API key.

- **Function**: `huf.ai.tools.google_places.handle_gplaces_nearby_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `latitude` | number | yes | Center latitude |
  | `longitude` | number | yes | Center longitude |
  | `radius` | number |  | Search radius in metres (default 50000, min 1) |
  | `included_types` | string |  | CSV of place types to include, e.g. 'restaurant,cafe' |
  | `excluded_types` | string |  | CSV of place types to exclude |
  | `included_primary_types` | string |  | CSV of primary types to include |
  | `excluded_primary_types` | string |  | CSV of primary types to exclude |
  | `max_result_count` | integer |  | Max results, 1-20 (default 10) |
  | `language_code` | string |  | Response language, e.g. 'en', 'fr' |
  | `region_code` | string |  | Region code as CLDR country code, e.g. 'us' |
  | `rank_preference` | string |  | POPULARITY (default) or DISTANCE |

## Google Tools

### `gmail_get_emails`

Get latest emails from Gmail. Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN env vars.

- **Function**: `huf.ai.tools.gmail.handle_get_emails`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `count` | integer |  | Number of emails (default 10) |
  | `query` | string |  | Gmail search query to filter emails |

### `gmail_send_email`

Send an email via Gmail. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.gmail.handle_send_email`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `to` | string | yes | Recipient email address |
  | `subject` | string | yes | Email subject |
  | `body` | string | yes | Email body (plain text) |

### `gmail_create_draft`

Create a draft email in Gmail. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.gmail.handle_create_draft`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `to` | string | yes | Recipient email address |
  | `subject` | string | yes | Email subject |
  | `body` | string | yes | Email body |

### `gmail_mark_as_read`

Mark an email as read in Gmail. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.gmail.handle_mark_as_read`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `message_id` | string | yes | Gmail message ID |

### `gsheets_read`

Read data from a Google Sheets spreadsheet. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_sheets.handle_read_sheet`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `spreadsheet_id` | string | yes | Google Sheets spreadsheet ID |
  | `range` | string |  | Cell range (e.g. Sheet1!A1:D10, default: Sheet1) |

### `gsheets_update`

Update data in a Google Sheets spreadsheet. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_sheets.handle_update_sheet`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `spreadsheet_id` | string | yes | Google Sheets spreadsheet ID |
  | `range` | string | yes | Cell range to update |
  | `data` | string | yes | 2D array of values as JSON string |

### `gsheets_create`

Create a new Google Sheets spreadsheet. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_sheets.handle_create_sheet`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `title` | string | yes | Spreadsheet title |

### `gcalendar_list_events`

List upcoming Google Calendar events. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_calendar.handle_list_events`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `limit` | integer |  | Max events (default 10) |
  | `start_date` | string |  | Start date filter (ISO 8601) |

### `gcalendar_create_event`

Create a Google Calendar event. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_calendar.handle_create_event`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `title` | string | yes | Event title |
  | `start_date` | string | yes | Start datetime (ISO 8601) |
  | `end_date` | string | yes | End datetime (ISO 8601) |
  | `description` | string |  | Event description |
  | `timezone` | string |  | Timezone (default: UTC) |

### `gcalendar_update_event`

Update a Google Calendar event. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_calendar.handle_update_event`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `event_id` | string | yes | Google Calendar event ID |
  | `title` | string |  | New event title |
  | `description` | string |  | New event description |

### `gcalendar_delete_event`

Delete a Google Calendar event. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_calendar.handle_delete_event`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `event_id` | string | yes | Google Calendar event ID |

### `gmaps_search_places`

Search for places using Google Maps. Requires GOOGLE_MAPS_API_KEY env var.

- **Function**: `huf.ai.tools.google_maps.handle_search_places`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `query` | string | yes | Place search query |

### `gmaps_get_directions`

Get directions between locations using Google Maps. Requires GOOGLE_MAPS_API_KEY env var.

- **Function**: `huf.ai.tools.google_maps.handle_get_directions`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `origin` | string | yes | Starting location |
  | `destination` | string | yes | Destination location |
  | `mode` | string |  | Travel mode: driving, walking, bicycling, transit (default: driving) |

### `gmaps_geocode`

Convert an address to coordinates. Requires GOOGLE_MAPS_API_KEY env var.

- **Function**: `huf.ai.tools.google_maps.handle_geocode`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `address` | string | yes | Address to geocode |

### `gmaps_reverse_geocode`

Convert coordinates to an address. Requires GOOGLE_MAPS_API_KEY env var.

- **Function**: `huf.ai.tools.google_maps.handle_reverse_geocode`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `lat` | string | yes | Latitude |
  | `lng` | string | yes | Longitude |

### `gdrive_list_files`

List files in Google Drive. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_drive.handle_list_files`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `limit` | integer |  | Max files (default 20) |
  | `query` | string |  | Drive search query |

### `gdrive_get_file`

Get metadata of a Google Drive file. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_drive.handle_get_file`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `file_id` | string | yes | Google Drive file ID |

### `gdrive_search_files`

Search for files in Google Drive. Requires Google OAuth credentials.

- **Function**: `huf.ai.tools.google_drive.handle_search_files`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `query` | string | yes | Search query |

### `google_meet_create_space`

Create a Google Meet meeting space and return a joinable link. Requires Google OAuth credentials with Meet scope.

- **Function**: `huf.ai.tools.google_meet.handle_create_meet_space`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `access_type` | string |  | Access level: OPEN, TRUSTED, or RESTRICTED (default: OPEN) |

### `google_meet_create_event`

Create a Google Calendar event with an auto-generated Google Meet conference. Requires Google OAuth credentials with Calendar scope.

- **Function**: `huf.ai.tools.google_meet.handle_create_meet_event`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `title` | string | yes | Meeting title |
  | `start_date` | string | yes | Start datetime (ISO 8601) |
  | `end_date` | string | yes | End datetime (ISO 8601) |
  | `description` | string |  | Event description |
  | `timezone` | string |  | Timezone (default: UTC) |

## Helpdesk Tools

### `helpdesk`

Manage Frappe Helpdesk tickets. Actions: list_tickets (status, priority, team, search, limit), get_ticket (ticket_id — includes comments), create_ticket (subject required; description, customer, priority, type, team), update_ticket (ticket_id required; status, priority, team, description, assigned_to), add_comment (ticket_id, content), list_agents (limit), list_teams (limit), assign_ticket (ticket_id, agent_id).

- **Function**: `huf.ai.tools.helpdesk.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: list_tickets\|get_ticket\|create_ticket\|update_ticket\|add_comment\|list_agents\|list_teams\|assign_ticket |
  | `ticket_id` | string |  | Ticket ID (HD-XXXXX) |
  | `subject` | string |  | Ticket subject |
  | `description` | string |  | Ticket description or updated text |
  | `status` | string |  | Status: Open, Replied, Resolved, Closed |
  | `priority` | string |  | Priority: Low, Medium, High, Urgent |
  | `team` | string |  | Team name |
  | `customer` | string |  | Customer name |
  | `content` | string |  | Comment text |
  | `agent_id` | string |  | Agent user ID for assignment |
  | `search` | string |  | Search query |
  | `limit` | integer |  | Max results |

## Raven Tools

### `raven`

Interact with Frappe Raven internal messaging. Actions: send_message (channel_id or channel_name, text), get_messages (channel_id or channel_name, limit, before_message_id), list_channels (channel_type, limit), get_members (channel_id or channel_name), create_channel (channel_name, type, channel_description, members list), search_messages (query; channel_id or channel_name, limit).

- **Function**: `huf.ai.tools.raven.handle_action`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `action` | string | yes | Action to perform. One of: send_message\|get_messages\|list_channels\|get_members\|create_channel\|search_messages |
  | `channel_id` | string |  | Raven channel ID |
  | `channel_name` | string |  | Channel name (alternative to channel_id) |
  | `text` | string |  | Message text |
  | `channel_type` | string |  | Channel type filter: Public, Private, Open |
  | `members` | string |  | JSON list of user IDs (for create_channel) |
  | `channel_description` | string |  | Channel description |
  | `query` | string |  | Search text |
  | `before_message_id` | string |  | Pagination cursor |
  | `limit` | integer |  | Max results |

## SERP

### `serp_hotel_search`

Search hotels (or vacation rentals) via SerpApi Google Hotels with the full filter set: guests, price budget, rating, star class, property types, amenities, brands, and boolean toggles. Requires SERPAPI_API_KEY env var or serpapi Integration Settings. Use property_token from each result with serp_hotel_details for full details.

- **Function**: `huf.ai.tools.serp_hotels.handle_serp_hotel_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `q` | string | yes | Search query, e.g. 'Hotels in Bandra Mumbai' |
  | `check_in_date` | string | yes | Check-in date (YYYY-MM-DD) |
  | `check_out_date` | string | yes | Check-out date (YYYY-MM-DD) |
  | `adults` | integer |  | Number of adult guests (default 2, min 1) |
  | `children` | integer |  | Number of children |
  | `children_ages` | string |  | Ages of children, comma-separated, e.g. '5,8' |
  | `currency` | string |  | ISO currency code for prices (default INR) |
  | `gl` | string |  | Country code for the search, e.g. 'in', 'us' (default in) |
  | `hl` | string |  | Language code, e.g. 'en' (default en) |
  | `sort_by` | integer |  | Sort order: 3 (lowest price), 8 (highest rating), 13 (most reviewed). Omit for relevance. |
  | `min_price` | integer |  | Minimum price per night |
  | `max_price` | integer |  | Maximum price per night |
  | `rating` | integer |  | Minimum guest rating bucket: 7 (3.5+), 8 (4.0+), 9 (4.5+) |
  | `hotel_class` | string |  | Star rating(s) 2-5, comma-separated, e.g. '4,5' |
  | `property_types` | string |  | SerpApi property-type ID(s), comma-separated |
  | `amenities` | string |  | SerpApi amenity ID(s), comma-separated |
  | `brands` | string |  | SerpApi hotel-brand ID(s), comma-separated (ignored when vacation_rentals is true) |
  | `free_cancellation` | boolean |  | Only results offering free cancellation |
  | `special_offers` | boolean |  | Only results with special offers |
  | `eco_certified` | boolean |  | Only eco-certified results |
  | `vacation_rentals` | boolean |  | Search vacation rentals instead of hotels |
  | `bedrooms` | integer |  | Minimum bedrooms (vacation rentals only) |
  | `bathrooms` | integer |  | Minimum bathrooms (vacation rentals only) |
  | `next_page_token` | string |  | Pagination token from a previous response |

### `serp_hotel_details`

Fetch full details for one hotel by property_token (from serp_hotel_search): per-OTA prices for the stay, rating and review sentiment breakdown, amenities, images, location. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_hotels.handle_serp_hotel_details`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `property_token` | string | yes | Hotel token from a serp_hotel_search result |
  | `check_in_date` | string | yes | Check-in date (YYYY-MM-DD); prices are quoted for this stay |
  | `check_out_date` | string | yes | Check-out date (YYYY-MM-DD) |
  | `q` | string |  | Search query the token came from (improves accuracy; default 'Hotels') |
  | `adults` | integer |  | Number of adult guests (default 2) |
  | `currency` | string |  | ISO currency code for all prices (default INR) |
  | `gl` | string |  | Country code (default in) |
  | `hl` | string |  | Language code (default en) |

### `serp_hotel_details_batch`

Fetch details for several hotels in one call, concurrently. Pass the property_tokens returned by serp_hotel_search. Returns {hotels, errors, requested, succeeded}. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_hotels.handle_serp_hotel_details_batch`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `property_tokens` | string | yes | Hotel tokens: JSON array, comma-separated string, or list |
  | `check_in_date` | string | yes | Check-in date (YYYY-MM-DD) |
  | `check_out_date` | string | yes | Check-out date (YYYY-MM-DD) |
  | `q` | string |  | Search query the tokens came from (improves accuracy) |
  | `adults` | integer |  | Number of adult guests (default 2) |
  | `currency` | string |  | ISO currency code for all prices (default INR) |
  | `max_workers` | integer |  | Thread pool size for parallel lookups (default 8) |

### `serp_google_maps_reviews`

Fetch reviews for a place on Google Maps. Pass a human-friendly place_query (e.g. 'Leopold Cafe Mumbai') and the data_id is resolved internally, or pass data_id/place_id directly to skip search. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_google_maps_reviews`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `place_query` | string |  | Place search query, e.g. 'Leopold Cafe Mumbai' (alternative to data_id/place_id) |
  | `data_id` | string |  | The place's data id, e.g. '0x...:0x...' (preferred if known) |
  | `place_id` | string |  | The place id (alternative to data_id) |
  | `sort_by` | string |  | Sort order: qualityScore (default), newestFirst, ratingHigh, ratingLow |
  | `hl` | string |  | Language code (default en) |
  | `gl` | string |  | Country code (default in) |
  | `next_page_token` | string |  | Pagination token from a previous response |

### `serp_google_hotel_reviews`

Fetch review data for a hotel: overall rating, star distribution, and per-topic sentiment breakdown. Pass hotel_query plus stay dates (property_token resolved internally) or a property_token directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_google_hotel_reviews`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `hotel_query` | string |  | Hotel search query, e.g. 'Taj Mahal Palace Mumbai' (alternative to property_token) |
  | `property_token` | string |  | Hotel token from a serp_hotel_search result (skips search) |
  | `check_in_date` | string | yes | Check-in date (YYYY-MM-DD) |
  | `check_out_date` | string | yes | Check-out date (YYYY-MM-DD) |
  | `q` | string |  | Search query the token came from (improves accuracy) |
  | `adults` | integer |  | Number of adult guests (default 2) |
  | `currency` | string |  | ISO currency code (default INR) |

### `serp_tripadvisor_search`

Search TripAdvisor to find a place and its place_id (for serp_tripadvisor_reviews). Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_tripadvisor_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `q` | string | yes | Search terms, e.g. 'Taj Mahal Palace Mumbai' |
  | `ssrc` | string |  | Category filter: a (all), r (restaurants), A (things to do), h (hotels), g (destinations), v (rentals), f (forums) |
  | `tripadvisor_domain` | string |  | TripAdvisor domain, e.g. 'www.tripadvisor.in' (default .com) |
  | `offset` | integer |  | Pagination offset (increments of 30) |
  | `limit` | integer |  | Max results (default 30) |

### `serp_tripadvisor_reviews`

Fetch reviews for a TripAdvisor place. Pass a human-friendly place_query (place_id resolved internally) or a place_id directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_tripadvisor_reviews`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `place_query` | string |  | Place search query (alternative to place_id) |
  | `place_id` | string |  | TripAdvisor place id from serp_tripadvisor_search (skips search) |
  | `sort_by` | string |  | Sort order: most_recent (default) or detailed_review |
  | `rating` | string |  | Filter by rating(s), comma-separated, e.g. '5' or '5,4' |
  | `language` | string |  | Language for reviews, e.g. 'en' |
  | `tripadvisor_domain` | string |  | TripAdvisor domain, e.g. 'www.tripadvisor.in' |
  | `translate` | boolean |  | Translate reviews to the selected language |
  | `offset` | integer |  | Reviews to skip (default 0) |
  | `limit` | integer |  | Max reviews per request (1-20, default 10) |

### `serp_yelp_search`

Find Yelp businesses and their place_id (for serp_yelp_reviews). Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_yelp_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `find_desc` | string | yes | What to search for, e.g. 'pizza' or a business name |
  | `find_loc` | string | yes | Location, e.g. 'New York, NY' |
  | `hl` | string |  | Language code (default en) |
  | `start` | integer |  | Result offset for pagination (0, 10, 20, ...) |

### `serp_yelp_reviews`

Fetch reviews for a Yelp business. Pass business_name + location (place_id resolved internally) or a place_id directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_reviews.handle_serp_yelp_reviews`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `business_name` | string |  | Business name, e.g. "Joe's Pizza" (with location, alternative to place_id) |
  | `location` | string |  | Business location, e.g. 'New York, NY' (with business_name) |
  | `place_id` | string |  | Yelp place id from serp_yelp_search (skips search) |
  | `sort_by` | string |  | Sort order: relevance_desc (default), date_desc, date_asc, rating_desc, rating_asc, elites_desc |
  | `start` | integer |  | Result offset for pagination |
  | `num` | integer |  | Number of reviews to return |
  | `hl` | string |  | Language code (default en) |

### `serp_youtube_search`

Search YouTube videos via SerpApi. Returns videos with parsed video_id (usable with youtube_transcript). Requires SERPAPI_API_KEY env var or serpapi Integration Settings.

- **Function**: `huf.ai.tools.serp_youtube.handle_serp_youtube_search`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `search_query` | string | yes | YouTube search terms |
  | `gl` | string |  | Country code (default in) |
  | `hl` | string |  | Language code (default en) |
  | `sp` | string |  | SerpApi filter/sort token (advanced) |

### `youtube_transcript`

Fetch the transcript/captions for a YouTube video (no SerpApi key required). Accepts a video id or any YouTube URL (watch, youtu.be, shorts, embed).

- **Function**: `huf.ai.tools.serp_youtube.handle_youtube_transcript`
- **Parameters**:

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `video` | string | yes | YouTube video id or URL (watch, youtu.be, shorts, embed) |
  | `languages` | string |  | Preferred language(s), comma-separated, e.g. 'en,hi' (default en); first available match is returned |
