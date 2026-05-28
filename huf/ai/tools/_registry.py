"""
Central registry of all integration tool definitions.

Each entry is a dict with:
  - tool_name: unique identifier
  - description: what the LLM sees
  - function_path: dotted path to the handler
  - category: Agent Tool Type label
  - parameters: list of parameter definitions
"""


def _p(name, type="string", required=False, description=""):
	return {
		"label": name.replace("_", " ").title(),
		"fieldname": name,
		"type": type,
		"required": int(required),
		"description": description,
	}


# ---------------------------------------------------------------------------
# Communication Tools
# ---------------------------------------------------------------------------

SLACK_TOOLS = [
	{
		"tool_name": "slack_send_message",
		"description": "Send a message to a Slack channel. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_send_message",
		"category": "Communication Tools",
		"parameters": [
			_p("channel", required=True, description="Channel ID or name to send the message to"),
			_p("text", required=True, description="Message text (supports Slack mrkdwn formatting)"),
		],
	},
	{
		"tool_name": "slack_send_thread_reply",
		"description": "Reply to a message thread in a Slack channel. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_send_message_thread",
		"category": "Communication Tools",
		"parameters": [
			_p("channel", required=True, description="Channel ID or name"),
			_p("text", required=True, description="Reply text"),
			_p("thread_ts", required=True, description="Timestamp of the parent message"),
		],
	},
	{
		"tool_name": "slack_list_channels",
		"description": "List all channels in the Slack workspace. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_list_channels",
		"category": "Communication Tools",
		"parameters": [],
	},
	{
		"tool_name": "slack_get_channel_history",
		"description": "Get message history of a Slack channel. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_get_channel_history",
		"category": "Communication Tools",
		"parameters": [
			_p("channel", required=True, description="Channel ID to fetch history from"),
			_p("limit", type="integer", description="Max messages to fetch (default 100)"),
		],
	},
	{
		"tool_name": "slack_search_messages",
		"description": "Search messages across the Slack workspace. Supports modifiers like from:@user, in:#channel. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_search_messages",
		"category": "Communication Tools",
		"parameters": [
			_p("query", required=True, description="Search query"),
			_p("limit", type="integer", description="Max results (default 20, max 100)"),
		],
	},
	{
		"tool_name": "slack_list_users",
		"description": "List all users in the Slack workspace. Requires SLACK_TOKEN env var.",
		"function_path": "huf.ai.tools.slack.handle_list_users",
		"category": "Communication Tools",
		"parameters": [
			_p("limit", type="integer", description="Max users to fetch (default 100)"),
		],
	},
]

DISCORD_TOOLS = [
	{
		"tool_name": "discord_send_message",
		"description": "Send a message to a Discord channel. Requires DISCORD_BOT_TOKEN env var.",
		"function_path": "huf.ai.tools.discord.handle_send_message",
		"category": "Communication Tools",
		"parameters": [
			_p("channel_id", required=True, description="Discord channel ID"),
			_p("message", required=True, description="Message text to send"),
		],
	},
	{
		"tool_name": "discord_get_messages",
		"description": "Get message history of a Discord channel. Requires DISCORD_BOT_TOKEN env var.",
		"function_path": "huf.ai.tools.discord.handle_get_channel_messages",
		"category": "Communication Tools",
		"parameters": [
			_p("channel_id", required=True, description="Discord channel ID"),
			_p("limit", type="integer", description="Max messages (default 50)"),
		],
	},
	{
		"tool_name": "discord_list_channels",
		"description": "List all channels in a Discord server. Requires DISCORD_BOT_TOKEN env var.",
		"function_path": "huf.ai.tools.discord.handle_list_channels",
		"category": "Communication Tools",
		"parameters": [
			_p("guild_id", required=True, description="Discord server (guild) ID"),
		],
	},
	{
		"tool_name": "discord_delete_message",
		"description": "Delete a message from a Discord channel. Requires DISCORD_BOT_TOKEN env var.",
		"function_path": "huf.ai.tools.discord.handle_delete_message",
		"category": "Communication Tools",
		"parameters": [
			_p("channel_id", required=True, description="Discord channel ID"),
			_p("message_id", required=True, description="Message ID to delete"),
		],
	},
]

TELEGRAM_TOOLS = [
	{
		"tool_name": "telegram_send_message",
		"description": "Send a message via Telegram bot. Requires TELEGRAM_TOKEN env var.",
		"function_path": "huf.ai.tools.telegram.handle_send_message",
		"category": "Communication Tools",
		"parameters": [
			_p("chat_id", required=True, description="Telegram chat ID to send to"),
			_p("message", required=True, description="Message text"),
		],
	},
]

# ---------------------------------------------------------------------------

GITHUB_TOOLS = [
	{
		"tool_name": "github_list_repos",
		"description": "List GitHub repositories for the authenticated user. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_list_repos",
		"category": "Developer Tools",
		"parameters": [],
	},
	{
		"tool_name": "github_get_repo",
		"description": "Get details of a GitHub repository. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_get_repo",
		"category": "Developer Tools",
		"parameters": [_p("repo_name", required=True, description="Repository (owner/name)")],
	},
	{
		"tool_name": "github_create_issue",
		"description": "Create a GitHub issue. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_create_issue",
		"category": "Developer Tools",
		"parameters": [
			_p("repo_name", required=True, description="Repository (owner/name)"),
			_p("title", required=True, description="Issue title"),
			_p("body", description="Issue body"),
		],
	},
	{
		"tool_name": "github_create_pr",
		"description": "Create a GitHub pull request. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_create_pull_request",
		"category": "Developer Tools",
		"parameters": [
			_p("repo_name", required=True, description="Repository (owner/name)"),
			_p("title", required=True, description="PR title"),
			_p("body", description="PR description"),
			_p("head", required=True, description="Head branch"),
			_p("base", required=True, description="Base branch"),
		],
	},
	{
		"tool_name": "github_get_file",
		"description": "Get file content from a GitHub repository. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_get_file_content",
		"category": "Developer Tools",
		"parameters": [
			_p("repo_name", required=True, description="Repository (owner/name)"),
			_p("path", required=True, description="File path in repository"),
		],
	},
	{
		"tool_name": "github_search_code",
		"description": "Search code across GitHub. Requires GITHUB_ACCESS_TOKEN env var.",
		"function_path": "huf.ai.tools.github.handle_search_code",
		"category": "Developer Tools",
		"parameters": [_p("query", required=True, description="Code search query")],
	},
]

RECIPIENT_TOOLS = [
	{
		"tool_name": "get_integration_recipient",
		"description": (
			"Look up a named recipient's service-specific ID from Integration Settings. "
			"Use this before sending a message to resolve a human name (e.g. 'John Doe', 'Sales Team') "
			"to the correct Telegram Chat ID, Slack User/Channel ID, Discord Channel ID, etc. "
			"Call this tool first, then pass the returned recipient_id to the relevant send tool."
		),
		"function_path": "huf.ai.tools.recipient.handle_get_recipient",
		"category": "Communication Tools",
		"parameters": [
			_p("service", required=True, description="The service name, e.g. 'telegram', 'slack', 'discord'"),
			_p("recipient_name", required=True, description="Human-friendly recipient name as stored in Integration Settings, e.g. 'John Doe'"),
		],
	},
]

# ---------------------------------------------------------------------------
# CRM Tools
# ---------------------------------------------------------------------------

CRM_TOOLS = [
	{
		"tool_name": "crm_get_leads",
		"description": "List CRM leads with optional filters (status, assigned_to, search). Returns paginated list with key fields.",
		"function_path": "huf.ai.tools.crm.handle_get_leads",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("status", description="Filter by lead status"),
			_p("assigned_to", description="Filter by lead owner email"),
			_p("search", description="Search across first_name, last_name, email, organization"),
			_p("limit", type="integer", description="Max leads to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "crm_get_lead",
		"description": "Get a single CRM lead by name/ID with all fields.",
		"function_path": "huf.ai.tools.crm.handle_get_lead",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("name", required=True, description="Lead ID/name"),
		],
	},
	{
		"tool_name": "crm_create_lead",
		"description": "Create a new CRM lead. Optionally provide notes to create a linked note.",
		"function_path": "huf.ai.tools.crm.handle_create_lead",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("first_name", required=True, description="First name of the lead"),
			_p("last_name", description="Last name of the lead"),
			_p("email", description="Email address"),
			_p("mobile_no", description="Mobile number"),
			_p("lead_owner", description="User email who owns this lead"),
			_p("source", description="Lead source"),
			_p("organization", description="Organization/company name"),
			_p("notes", description="Additional notes (creates a linked FCRM Note)"),
		],
	},
	{
		"tool_name": "crm_update_lead",
		"description": "Update fields on an existing CRM lead.",
		"function_path": "huf.ai.tools.crm.handle_update_lead",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("name", required=True, description="Lead ID/name"),
			_p("lead_name", description="Computed lead name (auto-generated if not set)"),
			_p("status", description="Lead status"),
			_p("lead_owner", description="Lead owner email"),
			_p("first_name", description="First name"),
			_p("last_name", description="Last name"),
			_p("email", description="Email"),
			_p("mobile_no", description="Mobile number"),
			_p("organization", description="Organization"),
			_p("website", description="Website"),
			_p("job_title", description="Job title"),
			_p("industry", description="Industry"),
			_p("source", description="Source"),
			_p("territory", description="Territory"),
			_p("details", description="Details / description"),
			_p("converted", type="Check", description="Mark as converted"),
			_p("lost_reason", description="Lost reason"),
			_p("lost_notes", description="Lost notes"),
		],
	},
	{
		"tool_name": "crm_get_deals",
		"description": "List CRM deals with optional filters (status, assigned_to, organization, search).",
		"function_path": "huf.ai.tools.crm.handle_get_deals",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("status", description="Filter by deal status"),
			_p("assigned_to", description="Filter by deal owner email"),
			_p("organization", description="Filter by organization name"),
			_p("search", description="Search across organization and lead name"),
			_p("limit", type="integer", description="Max deals to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "crm_create_deal",
		"description": "Create a CRM deal from a lead or standalone. Provide either lead or organization.",
		"function_path": "huf.ai.tools.crm.handle_create_deal",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("lead", description="Lead ID to convert into a deal"),
			_p("organization", description="Organization name (required if lead is not provided)"),
			_p("deal_owner", description="Deal owner email"),
			_p("status", description="Deal status"),
			_p("deal_value", type="number", description="Deal value amount"),
			_p("probability", type="number", description="Probability of closing (0-100)"),
			_p("expected_closure_date", description="Expected closure date (YYYY-MM-DD)"),
			_p("next_step", description="Next step description"),
			_p("currency", description="Currency code"),
		],
	},
	{
		"tool_name": "crm_update_deal",
		"description": "Update an existing CRM deal (status, value, probability, close_date, etc.).",
		"function_path": "huf.ai.tools.crm.handle_update_deal",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("name", required=True, description="Deal ID/name"),
			_p("status", description="Deal status"),
			_p("deal_value", type="number", description="Deal value"),
			_p("probability", type="number", description="Probability"),
			_p("expected_closure_date", description="Expected closure date"),
			_p("closed_date", description="Actual closed date"),
			_p("deal_owner", description="Deal owner email"),
			_p("organization", description="Organization"),
			_p("next_step", description="Next step"),
			_p("currency", description="Currency"),
			_p("lost_reason", description="Lost reason"),
			_p("lost_notes", description="Lost notes"),
		],
	},
	{
		"tool_name": "crm_add_note",
		"description": "Add a note to a CRM lead or deal.",
		"function_path": "huf.ai.tools.crm.handle_add_note",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("doctype", required=True, description="Target DocType: CRM Lead or CRM Deal"),
			_p("docname", required=True, description="Target document name/ID"),
			_p("content", required=True, description="Note content"),
			_p("title", description="Note title (default 'Note')"),
		],
	},
	{
		"tool_name": "crm_add_task",
		"description": "Create a task linked to a CRM lead or deal.",
		"function_path": "huf.ai.tools.crm.handle_add_task",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("reference_doctype", required=True, description="CRM Lead or CRM Deal"),
			_p("reference_docname", required=True, description="Document name/ID"),
			_p("title", required=True, description="Task title"),
			_p("description", description="Task description"),
			_p("assigned_to", description="Assigned user email"),
			_p("due_date", description="Due date (YYYY-MM-DD)"),
			_p("priority", description="Priority (Low, Medium, High, Urgent)"),
			_p("status", description="Status"),
			_p("start_date", description="Start date (YYYY-MM-DD)"),
		],
	},
	{
		"tool_name": "crm_get_contacts",
		"description": "List/search CRM contacts linked to deals.",
		"function_path": "huf.ai.tools.crm.handle_get_contacts",
		"category": "Frappe CRM Tools",
		"parameters": [
			_p("search", description="Search across full_name, email, mobile_no"),
			_p("deal", description="Filter by parent deal ID"),
			_p("limit", type="integer", description="Max contacts to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
]

# ---------------------------------------------------------------------------
# Helpdesk Tools
# ---------------------------------------------------------------------------

HELPDESK_TOOLS = [
	{
		"tool_name": "helpdesk_get_tickets",
		"description": "List helpdesk tickets with optional filters (status, priority, assigned_to, team, search).",
		"function_path": "huf.ai.tools.helpdesk.handle_get_tickets",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("status", description="Filter by ticket status"),
			_p("priority", description="Filter by priority"),
			_p("assigned_to", description="Filter by assigned agent user ID"),
			_p("team", description="Filter by team (agent_group)"),
			_p("ticket_type", description="Filter by ticket type"),
			_p("search", description="Search across subject and raised_by"),
			_p("limit", type="integer", description="Max tickets to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "helpdesk_get_ticket",
		"description": "Get a single helpdesk ticket by ID with comments.",
		"function_path": "huf.ai.tools.helpdesk.handle_get_ticket",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("name", required=True, description="Ticket ID/name"),
		],
	},
	{
		"tool_name": "helpdesk_create_ticket",
		"description": "Create a new helpdesk support ticket.",
		"function_path": "huf.ai.tools.helpdesk.handle_create_ticket",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("subject", required=True, description="Ticket subject"),
			_p("description", description="Ticket description"),
			_p("raised_by", description="Email of the requester"),
			_p("customer", description="Customer ID (HD Customer)"),
			_p("contact", description="Contact ID (Contact)"),
			_p("priority", description="Priority"),
			_p("ticket_type", description="Ticket type"),
			_p("team", description="Team to assign (agent_group)"),
		],
	},
	{
		"tool_name": "helpdesk_update_ticket",
		"description": "Update an existing helpdesk ticket (status, priority, assigned_to, team).",
		"function_path": "huf.ai.tools.helpdesk.handle_update_ticket",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("name", required=True, description="Ticket ID/name"),
			_p("status", description="Ticket status"),
			_p("priority", description="Priority"),
			_p("assigned_to", description="Agent user ID to assign"),
			_p("team", description="Team (agent_group)"),
			_p("ticket_type", description="Ticket type"),
			_p("subject", description="Subject"),
			_p("description", description="Description"),
			_p("resolution_details", description="Resolution details"),
			_p("contact", description="Contact"),
			_p("customer", description="Customer"),
		],
	},
	{
		"tool_name": "helpdesk_add_comment",
		"description": "Add a comment/reply to a helpdesk ticket.",
		"function_path": "huf.ai.tools.helpdesk.handle_add_comment",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("ticket_id", required=True, description="Ticket ID"),
			_p("content", required=True, description="Comment content"),
			_p("commented_by", description="User ID (defaults to current user)"),
		],
	},
	{
		"tool_name": "helpdesk_get_agents",
		"description": "List helpdesk agents.",
		"function_path": "huf.ai.tools.helpdesk.handle_get_agents",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("is_active", type="Check", description="Filter by active status"),
			_p("search", description="Search by agent name"),
			_p("limit", type="integer", description="Max agents to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "helpdesk_get_teams",
		"description": "List helpdesk teams.",
		"function_path": "huf.ai.tools.helpdesk.handle_get_teams",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("search", description="Search by team name"),
			_p("limit", type="integer", description="Max teams to fetch (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "helpdesk_assign_ticket",
		"description": "Assign a helpdesk ticket to an agent.",
		"function_path": "huf.ai.tools.helpdesk.handle_assign_ticket",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("ticket_id", required=True, description="Ticket ID"),
			_p("agent_id", description="Agent user ID (defaults to current user)"),
		],
	},
]

# ---------------------------------------------------------------------------
# Raven Tools
# ---------------------------------------------------------------------------

RAVEN_TOOLS = [
	{
		"tool_name": "raven_send_message",
		"description": "Send a message to a Raven channel by channel_id or channel_name.",
		"function_path": "huf.ai.tools.raven.handle_send_message",
		"category": "Raven Tools",
		"parameters": [
			_p("channel_id", description="Raven Channel ID"),
			_p("channel_name", description="Raven Channel name (alternative to channel_id)"),
			_p("text", required=True, description="Message text"),
			_p("message_type", description="Message type: Text, Image, File, Poll, System (default Text)"),
			_p("is_reply", type="Check", description="Whether this is a reply"),
			_p("linked_message", description="Message ID being replied to"),
		],
	},
	{
		"tool_name": "raven_get_messages",
		"description": "Get recent messages from a Raven channel with pagination.",
		"function_path": "huf.ai.tools.raven.handle_get_messages",
		"category": "Raven Tools",
		"parameters": [
			_p("channel_id", description="Raven Channel ID"),
			_p("channel_name", description="Raven Channel name (alternative to channel_id)"),
			_p("limit", type="integer", description="Max messages to fetch (default 20)"),
			_p("before_message_id", description="Fetch messages before this message ID"),
		],
	},
	{
		"tool_name": "raven_list_channels",
		"description": "List all Raven channels. Optionally filter by type (public, private, dm).",
		"function_path": "huf.ai.tools.raven.handle_list_channels",
		"category": "Raven Tools",
		"parameters": [
			_p("channel_type", description="Filter by type: public, private, dm"),
			_p("limit", type="integer", description="Max channels to fetch (default 50)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "raven_get_channel_members",
		"description": "Get members of a Raven channel.",
		"function_path": "huf.ai.tools.raven.handle_get_channel_members",
		"category": "Raven Tools",
		"parameters": [
			_p("channel_id", description="Raven Channel ID"),
			_p("channel_name", description="Raven Channel name (alternative to channel_id)"),
			_p("limit", type="integer", description="Max members to fetch (default 100)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "raven_create_channel",
		"description": "Create a new Raven channel and optionally add members.",
		"function_path": "huf.ai.tools.raven.handle_create_channel",
		"category": "Raven Tools",
		"parameters": [
			_p("channel_name", required=True, description="Name of the new channel"),
			_p("channel_type", description="Type: Public, Private, Open (default Public)"),
			_p("channel_description", description="Channel description"),
			_p("workspace", description="Workspace ID"),
			_p("members", description="List of Raven User IDs to add as members"),
		],
	},
	{
		"tool_name": "raven_search_messages",
		"description": "Search messages across Raven channels or within a specific channel.",
		"function_path": "huf.ai.tools.raven.handle_search_messages",
		"category": "Raven Tools",
		"parameters": [
			_p("query", required=True, description="Search text"),
			_p("channel_id", description="Restrict search to a specific channel ID"),
			_p("channel_name", description="Restrict search to a specific channel name"),
			_p("limit", type="integer", description="Max results (default 20)"),
			_p("offset", type="integer", description="Offset for pagination (default 0)"),
		],
	},
]


# ---------------------------------------------------------------------------
# ERPNext Tools
# ---------------------------------------------------------------------------

ERPNEXT_TOOLS = [
	{
		"tool_name": "erpnext_get_sales_invoices",
		"description": "List ERPNext sales invoices with optional filters (customer, status, date range). Returns key fields including grand_total and outstanding_amount.",
		"function_path": "huf.ai.tools.erpnext.handle_get_sales_invoices",
		"category": "ERPNext Tools",
		"parameters": [
			_p("customer", description="Filter by customer ID"),
			_p("status", description="Filter by status: Draft, Submitted, Paid, Overdue, Return, Cancelled"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max invoices to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_sales_invoice",
		"description": "Get a single ERPNext sales invoice by name with full details including items child table.",
		"function_path": "huf.ai.tools.erpnext.handle_get_sales_invoice",
		"category": "ERPNext Tools",
		"parameters": [
			_p("name", required=True, description="Sales Invoice ID/name"),
		],
	},
	{
		"tool_name": "erpnext_create_sales_invoice",
		"description": "Create a draft ERPNext sales invoice. Provide customer and line items.",
		"function_path": "huf.ai.tools.erpnext.handle_create_sales_invoice",
		"category": "ERPNext Tools",
		"parameters": [
			_p("customer", required=True, description="Customer ID"),
			_p("company", description="Company name"),
			_p("posting_date", description="Invoice date (YYYY-MM-DD)"),
			_p("items", type="json", description="List of line items: [{item_code, qty, rate}]"),
		],
	},
	{
		"tool_name": "erpnext_get_purchase_invoices",
		"description": "List ERPNext purchase invoices with optional filters (supplier, status, date range).",
		"function_path": "huf.ai.tools.erpnext.handle_get_purchase_invoices",
		"category": "ERPNext Tools",
		"parameters": [
			_p("supplier", description="Filter by supplier ID"),
			_p("status", description="Filter by status: Draft, Submitted, Paid, Overdue, Cancelled"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max invoices to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_purchase_invoice",
		"description": "Get a single ERPNext purchase invoice by name with full details including items child table.",
		"function_path": "huf.ai.tools.erpnext.handle_get_purchase_invoice",
		"category": "ERPNext Tools",
		"parameters": [
			_p("name", required=True, description="Purchase Invoice ID/name"),
		],
	},
	{
		"tool_name": "erpnext_get_payments",
		"description": "List ERPNext payment entries with optional filters (party_type, party, payment_type, date range).",
		"function_path": "huf.ai.tools.erpnext.handle_get_payments",
		"category": "ERPNext Tools",
		"parameters": [
			_p("party_type", description="Filter by party type: Customer, Supplier"),
			_p("party", description="Filter by party name/ID"),
			_p("payment_type", description="Filter by payment type: Receive, Pay, Internal Transfer"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max payments to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_create_payment",
		"description": "Create a draft ERPNext payment entry. Optionally link to a Sales or Purchase Invoice.",
		"function_path": "huf.ai.tools.erpnext.handle_create_payment",
		"category": "ERPNext Tools",
		"parameters": [
			_p("payment_type", required=True, description="Payment type: Receive, Pay, Internal Transfer"),
			_p("party_type", required=True, description="Party type: Customer, Supplier"),
			_p("party", required=True, description="Party name/ID"),
			_p("company", description="Company name"),
			_p("posting_date", description="Payment date (YYYY-MM-DD)"),
			_p("paid_amount", required=True, description="Amount paid"),
			_p("mode_of_payment", description="Mode of payment"),
			_p("paid_from", description="Paid from account"),
			_p("paid_to", description="Paid to account"),
			_p("invoice_name", description="Sales or Purchase Invoice to link as reference"),
		],
	},
	{
		"tool_name": "erpnext_get_quotations",
		"description": "List ERPNext quotations with optional filters (party_name, status, date range).",
		"function_path": "huf.ai.tools.erpnext.handle_get_quotations",
		"category": "ERPNext Tools",
		"parameters": [
			_p("party_name", description="Filter by party name/ID"),
			_p("status", description="Filter by quotation status"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max quotations to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_create_quotation",
		"description": "Create a draft ERPNext quotation. Provide quotation_to, party_name, and line items.",
		"function_path": "huf.ai.tools.erpnext.handle_create_quotation",
		"category": "ERPNext Tools",
		"parameters": [
			_p("quotation_to", required=True, description="Quotation to: Customer or Lead"),
			_p("party_name", required=True, description="Customer or Lead ID"),
			_p("company", description="Company name"),
			_p("transaction_date", description="Quotation date (YYYY-MM-DD)"),
			_p("valid_till", description="Valid until date (YYYY-MM-DD)"),
			_p("items", type="json", description="List of line items: [{item_code, qty, rate}]"),
		],
	},
	{
		"tool_name": "erpnext_get_customers",
		"description": "List/search ERPNext customers with optional filters (customer_group, territory, search query).",
		"function_path": "huf.ai.tools.erpnext.handle_get_customers",
		"category": "ERPNext Tools",
		"parameters": [
			_p("search", description="Search across name, customer_name, or customer_group"),
			_p("customer_group", description="Filter by customer group"),
			_p("territory", description="Filter by territory"),
			_p("limit", type="integer", description="Max customers to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_customer",
		"description": "Get a single ERPNext customer by name with address and contact details.",
		"function_path": "huf.ai.tools.erpnext.handle_get_customer",
		"category": "ERPNext Tools",
		"parameters": [
			_p("name", required=True, description="Customer ID/name"),
		],
	},
	{
		"tool_name": "erpnext_get_account_ledger",
		"description": "Query GL entries for an account with running balance. GL Entry is read-only.",
		"function_path": "huf.ai.tools.erpnext.handle_get_account_ledger",
		"category": "ERPNext Tools",
		"parameters": [
			_p("account", required=True, description="Account name/ID"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("party_type", description="Filter by party type"),
			_p("party", description="Filter by party name/ID"),
			_p("limit", type="integer", description="Max entries to fetch (default 50)"),
		],
	},
	{
		"tool_name": "erpnext_create_journal_entry",
		"description": "Create a draft ERPNext journal entry. Total debit must equal total credit.",
		"function_path": "huf.ai.tools.erpnext.handle_create_journal_entry",
		"category": "ERPNext Tools",
		"parameters": [
			_p("voucher_type", description="Voucher type: Journal Entry, Contra Entry, etc."),
			_p("posting_date", required=True, description="Posting date (YYYY-MM-DD)"),
			_p("company", required=True, description="Company name"),
			_p("user_remark", description="User remark / narration"),
			_p("accounts", type="json", required=True, description="Account lines: [{account, debit_in_account_currency, credit_in_account_currency, party_type, party, cost_center}]"),
		],
	},
	{
		"tool_name": "erpnext_get_rfqs",
		"description": "List ERPNext requests for quotation with optional filters (status, date range).",
		"function_path": "huf.ai.tools.erpnext.handle_get_rfqs",
		"category": "ERPNext Tools",
		"parameters": [
			_p("status", description="Filter by RFQ status"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max RFQs to fetch (default 20)"),
		],
	},
]

# ---------------------------------------------------------------------------
# ERPNext CRM Tools
# ---------------------------------------------------------------------------

ERPNEXT_CRM_TOOLS = [
	{
		"tool_name": "erpnext_crm_get_leads",
		"description": "List ERPNext leads with optional filters (status, lead_owner, search). Returns key fields.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_get_leads",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("status", description="Filter by lead status"),
			_p("lead_owner", description="Filter by lead owner email"),
			_p("search", description="Search across lead_name, company_name, email_id"),
			_p("limit", type="integer", description="Max leads to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_crm_get_lead",
		"description": "Get a single ERPNext lead by name with all fields.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_get_lead",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("name", required=True, description="Lead ID/name"),
		],
	},
	{
		"tool_name": "erpnext_crm_create_lead",
		"description": "Create a new ERPNext lead.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_create_lead",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("lead_name", required=True, description="Full name of the lead"),
			_p("company_name", description="Company name"),
			_p("email_id", description="Email address"),
			_p("mobile_no", description="Mobile number"),
			_p("phone", description="Phone number"),
			_p("lead_owner", description="User email who owns this lead"),
			_p("status", description="Lead status (default: Lead)"),
			_p("type", description="Lead type"),
			_p("market_segment", description="Market segment"),
			_p("industry", description="Industry"),
			_p("territory", description="Territory"),
			_p("website", description="Website URL"),
		],
	},
	{
		"tool_name": "erpnext_crm_update_lead",
		"description": "Update fields on an existing ERPNext lead.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_update_lead",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("name", required=True, description="Lead ID/name"),
			_p("status", description="Lead status"),
			_p("lead_owner", description="Lead owner email"),
			_p("email_id", description="Email address"),
			_p("mobile_no", description="Mobile number"),
			_p("territory", description="Territory"),
			_p("qualification_status", description="Qualification status"),
		],
	},
	{
		"tool_name": "erpnext_crm_get_opportunities",
		"description": "List ERPNext opportunities with optional filters (status, party_name, expected closing from date).",
		"function_path": "huf.ai.tools.erpnext_crm.handle_get_opportunities",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("status", description="Filter by opportunity status"),
			_p("party_name", description="Filter by party name/ID"),
			_p("from_date", description="Expected closing from date (YYYY-MM-DD)"),
			_p("limit", type="integer", description="Max opportunities to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_crm_create_opportunity",
		"description": "Create a new ERPNext opportunity linked to a Customer or Lead.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_create_opportunity",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("opportunity_from", required=True, description="Opportunity from: Customer or Lead"),
			_p("party_name", required=True, description="Customer or Lead ID"),
			_p("title", description="Opportunity title"),
			_p("opportunity_type", description="Opportunity type"),
			_p("expected_closing", description="Expected closing date (YYYY-MM-DD)"),
			_p("opportunity_amount", type="number", description="Opportunity amount"),
			_p("sales_stage", description="Sales stage"),
			_p("probability", type="number", description="Probability (0-100)"),
			_p("currency", description="Currency code"),
		],
	},
	{
		"tool_name": "erpnext_crm_update_opportunity",
		"description": "Update fields on an existing ERPNext opportunity.",
		"function_path": "huf.ai.tools.erpnext_crm.handle_update_opportunity",
		"category": "ERPNext CRM Tools",
		"parameters": [
			_p("name", required=True, description="Opportunity ID/name"),
			_p("status", description="Opportunity status"),
			_p("opportunity_amount", type="number", description="Opportunity amount"),
			_p("sales_stage", description="Sales stage"),
			_p("probability", type="number", description="Probability"),
			_p("expected_closing", description="Expected closing date (YYYY-MM-DD)"),
			_p("order_lost_reason", description="Reason if order lost"),
		],
	},
]

# ---------------------------------------------------------------------------
# ERPNext Inventory Tools
# ---------------------------------------------------------------------------

ERPNEXT_INVENTORY_TOOLS = [
	{
		"tool_name": "erpnext_get_items",
		"description": "List ERPNext items with optional search across item_code, item_name, and item_group. Filter by item_group, is_stock_item, or disabled status.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_items",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("search", description="Search across item_code, item_name, or item_group"),
			_p("item_group", description="Filter by item group"),
			_p("is_stock_item", type="Check", description="Filter by stock item flag"),
			_p("disabled", type="Check", description="Include disabled items (default 0)"),
			_p("limit", type="integer", description="Max items to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_item",
		"description": "Get a single ERPNext item by name with full details including item_defaults child table.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_item",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("name", required=True, description="Item ID/name (item_code)"),
		],
	},
	{
		"tool_name": "erpnext_get_item_prices",
		"description": "List ERPNext item prices for an item with optional filters (price_list, buying, selling).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_item_prices",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("item_code", description="Filter by item code"),
			_p("price_list", description="Filter by price list name"),
			_p("buying", type="Check", description="Filter buying prices"),
			_p("selling", type="Check", description="Filter selling prices"),
			_p("limit", type="integer", description="Max prices to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_boms",
		"description": "List ERPNext BOMs (Bill of Materials) with optional filters (item, is_active, is_default, company).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_boms",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("item", description="Filter by finished item code"),
			_p("is_active", type="Check", description="Filter by active status"),
			_p("is_default", type="Check", description="Filter by default status"),
			_p("company", description="Filter by company"),
			_p("limit", type="integer", description="Max BOMs to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_bom",
		"description": "Get a single ERPNext BOM by name with items and operations child tables.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_bom",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("name", required=True, description="BOM ID/name"),
		],
	},
	{
		"tool_name": "erpnext_create_bom",
		"description": "Create a draft ERPNext BOM. Provide finished item, quantity, and raw material line items.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_create_bom",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("item", required=True, description="Finished item code"),
			_p("quantity", type="number", description="Quantity to manufacture (default 1)"),
			_p("uom", description="Unit of measure"),
			_p("company", description="Company name"),
			_p("is_default", type="Check", description="Set as default BOM (default 1)"),
			_p("items", type="json", description="Raw material lines: [{item_code, qty, uom, rate}]"),
		],
	},
	{
		"tool_name": "erpnext_get_stock_balance",
		"description": "Get current stock balance per item and warehouse from Stock Ledger Entry. Optionally filter by item_code, warehouse, or as_of_date.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_stock_balance",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("item_code", description="Filter by item code"),
			_p("warehouse", description="Filter by warehouse"),
			_p("as_of_date", description="Balance as of date (YYYY-MM-DD)"),
		],
	},
	{
		"tool_name": "erpnext_get_stock_movements",
		"description": "List ERPNext stock ledger entries with optional filters (item_code, warehouse, date range, voucher_type).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_stock_movements",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("item_code", description="Filter by item code"),
			_p("warehouse", description="Filter by warehouse"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("voucher_type", description="Filter by voucher type"),
			_p("limit", type="integer", description="Max entries to fetch (default 50)"),
		],
	},
	{
		"tool_name": "erpnext_get_stock_entries",
		"description": "List ERPNext stock entry documents (Material Issue, Receipt, Transfer, Manufacture) with optional filters.",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_stock_entries",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("stock_entry_type", description="Filter by type: Material Issue, Material Receipt, Material Transfer, Manufacture"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("docstatus", type="integer", description="Filter by docstatus: 0=Draft, 1=Submitted, 2=Cancelled"),
			_p("limit", type="integer", description="Max entries to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_warehouses",
		"description": "List ERPNext warehouses with optional filters (company, warehouse_type, disabled).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_warehouses",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("company", description="Filter by company"),
			_p("warehouse_type", description="Filter by warehouse type"),
			_p("disabled", type="Check", description="Include disabled warehouses (default 0)"),
			_p("limit", type="integer", description="Max warehouses to fetch (default 50)"),
		],
	},
	{
		"tool_name": "erpnext_get_delivery_notes",
		"description": "List ERPNext delivery notes with optional filters (customer, date range, docstatus).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_delivery_notes",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("customer", description="Filter by customer ID"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("docstatus", type="integer", description="Filter by docstatus"),
			_p("limit", type="integer", description="Max notes to fetch (default 20)"),
		],
	},
	{
		"tool_name": "erpnext_get_purchase_receipts",
		"description": "List ERPNext purchase receipts with optional filters (supplier, date range, docstatus).",
		"function_path": "huf.ai.tools.erpnext_inventory.handle_get_purchase_receipts",
		"category": "ERPNext Inventory",
		"parameters": [
			_p("supplier", description="Filter by supplier ID"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("docstatus", type="integer", description="Filter by docstatus"),
			_p("limit", type="integer", description="Max receipts to fetch (default 20)"),
		],
	},
]

# ---------------------------------------------------------------------------
# ERPNext Report Tools
# ---------------------------------------------------------------------------

ERPNEXT_REPORT_TOOLS = [
	{
		"tool_name": "erpnext_balance_sheet",
		"description": "Run ERPNext Balance Sheet report. Key filters: company (required), fiscal_year or from_fiscal_year/to_fiscal_year, periodicity (Monthly/Quarterly/Half-Yearly/Yearly), accumulated_values.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_balance_sheet",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("fiscal_year", description="Fiscal year"),
			_p("from_fiscal_year", description="From fiscal year"),
			_p("to_fiscal_year", description="To fiscal year"),
			_p("periodicity", description="Monthly, Quarterly, Half-Yearly, or Yearly"),
			_p("accumulated_values", type="Check", description="Show accumulated values (default 1)"),
		],
	},
	{
		"tool_name": "erpnext_profit_and_loss",
		"description": "Run ERPNext Profit and Loss Statement report. Key filters: company (required), fiscal_year, periodicity, from_date, to_date.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_profit_and_loss",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("fiscal_year", description="Fiscal year"),
			_p("periodicity", description="Monthly, Quarterly, Half-Yearly, or Yearly"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
		],
	},
	{
		"tool_name": "erpnext_trial_balance",
		"description": "Run ERPNext Trial Balance report. Key filters: company (required), from_date, to_date, show_zero_values.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_trial_balance",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("show_zero_values", type="Check", description="Show accounts with zero balance (default 0)"),
		],
	},
	{
		"tool_name": "erpnext_general_ledger",
		"description": "Run ERPNext General Ledger report. Key filters: company (required), from_date, to_date, account, party_type, party, voucher_no, group_by, limit.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_general_ledger",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("account", description="Account name/ID"),
			_p("party_type", description="Party type"),
			_p("party", description="Party name/ID"),
			_p("voucher_no", description="Voucher number"),
			_p("group_by", description="Group by Voucher or Group by Account"),
			_p("limit", type="integer", description="Max rows to return (default 500)"),
		],
	},
	{
		"tool_name": "erpnext_accounts_receivable",
		"description": "Run ERPNext Accounts Receivable report. Key filters: company (required), report_date, ageing_based_on (Due Date/Posting Date), range1/range2/range3, customer.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_accounts_receivable",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("report_date", description="Report as-of date (YYYY-MM-DD)"),
			_p("ageing_based_on", description="Due Date or Posting Date"),
			_p("range1", type="integer", description="Ageing range 1 in days (default 30)"),
			_p("range2", type="integer", description="Ageing range 2 in days (default 60)"),
			_p("range3", type="integer", description="Ageing range 3 in days (default 90)"),
			_p("customer", description="Filter by customer ID"),
			_p("payment_terms_template", description="Filter by payment terms template"),
		],
	},
	{
		"tool_name": "erpnext_accounts_payable",
		"description": "Run ERPNext Accounts Payable report. Key filters: company (required), report_date, ageing_based_on, range1/range2/range3, supplier.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_accounts_payable",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("report_date", description="Report as-of date (YYYY-MM-DD)"),
			_p("ageing_based_on", description="Due Date or Posting Date"),
			_p("range1", type="integer", description="Ageing range 1 in days (default 30)"),
			_p("range2", type="integer", description="Ageing range 2 in days (default 60)"),
			_p("range3", type="integer", description="Ageing range 3 in days (default 90)"),
			_p("supplier", description="Filter by supplier ID"),
		],
	},
	{
		"tool_name": "erpnext_bank_reconciliation",
		"description": "Run ERPNext Bank Reconciliation Statement report. Key filters: company (required), account (bank account, required), from_date, to_date, include_pos_transactions.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_bank_reconciliation",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", required=True, description="Company name"),
			_p("account", required=True, description="Bank account name/ID"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("include_pos_transactions", type="Check", description="Include POS transactions (default 0)"),
		],
	},
	{
		"tool_name": "erpnext_sales_register",
		"description": "Run ERPNext Sales Register report. Key filters: company, from_date (required), to_date (required), customer, item_code.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_sales_register",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", required=True, description="Start date (YYYY-MM-DD)"),
			_p("to_date", required=True, description="End date (YYYY-MM-DD)"),
			_p("customer", description="Filter by customer ID"),
			_p("item_code", description="Filter by item code"),
		],
	},
	{
		"tool_name": "erpnext_sales_order_analysis",
		"description": "Run ERPNext Sales Order Analysis report. Key filters: company, from_date, to_date, customer, item_code, status.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_sales_order_analysis",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("customer", description="Filter by customer ID"),
			_p("item_code", description="Filter by item code"),
			_p("status", description="Filter by status: Draft, To Deliver and Bill, Completed, etc."),
		],
	},
	{
		"tool_name": "erpnext_customer_acquisition",
		"description": "Run ERPNext Customer Acquisition and Loyalty report. Key filters: company, from_date, to_date, customer_group, territory.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_customer_acquisition",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("customer_group", description="Filter by customer group"),
			_p("territory", description="Filter by territory"),
		],
	},
	{
		"tool_name": "erpnext_stock_balance_report",
		"description": "Run ERPNext Stock Balance report (native ERPNext report). Key filters: company, from_date, to_date, item_code, warehouse, item_group.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_stock_balance_report",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("item_code", description="Filter by item code"),
			_p("warehouse", description="Filter by warehouse"),
			_p("item_group", description="Filter by item group"),
		],
	},
	{
		"tool_name": "erpnext_stock_ledger_report",
		"description": "Run ERPNext Stock Ledger report (native ERPNext report). Key filters: company, from_date (required), to_date (required), item_code, warehouse, voucher_no.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_stock_ledger_report",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", required=True, description="Start date (YYYY-MM-DD)"),
			_p("to_date", required=True, description="End date (YYYY-MM-DD)"),
			_p("item_code", description="Filter by item code"),
			_p("warehouse", description="Filter by warehouse"),
			_p("voucher_no", description="Filter by voucher number"),
		],
	},
	{
		"tool_name": "erpnext_item_wise_sales",
		"description": "Run ERPNext Item-wise Sales Register report. Key filters: company, from_date, to_date, item_code, customer.",
		"function_path": "huf.ai.tools.erpnext_reports.handle_item_wise_sales",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("item_code", description="Filter by item code"),
			_p("customer", description="Filter by customer ID"),
		],
	},
	{
		"tool_name": "erpnext_gross_profit",
		"description": "Run ERPNext Gross Profit report. Key filters: company, from_date, to_date, group_by (Invoice/Item Code/Item Group/Customer/Customer Group).",
		"function_path": "huf.ai.tools.erpnext_reports.handle_gross_profit",
		"category": "ERPNext Reports",
		"parameters": [
			_p("company", description="Company name"),
			_p("from_date", description="Start date (YYYY-MM-DD)"),
			_p("to_date", description="End date (YYYY-MM-DD)"),
			_p("group_by", description="Group by: Invoice, Item Code, Item Group, Customer, Customer Group"),
		],
	},
]

# ---------------------------------------------------------------------------
# Master list: every tool grouped for easy iteration
# ---------------------------------------------------------------------------

ALL_INTEGRATION_TOOLS = (
	RECIPIENT_TOOLS
	+ SLACK_TOOLS
	+ DISCORD_TOOLS
	+ TELEGRAM_TOOLS
	+ GITHUB_TOOLS
	+ CRM_TOOLS
	+ HELPDESK_TOOLS
	+ RAVEN_TOOLS
	+ ERPNEXT_TOOLS
	+ ERPNEXT_CRM_TOOLS
	+ ERPNEXT_INVENTORY_TOOLS
	+ ERPNEXT_REPORT_TOOLS
)
