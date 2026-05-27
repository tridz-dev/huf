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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
		"parameters": [
			_p("name", required=True, description="Lead ID/name"),
		],
	},
	{
		"tool_name": "crm_create_lead",
		"description": "Create a new CRM lead. Optionally provide notes to create a linked note.",
		"function_path": "huf.ai.tools.crm.handle_create_lead",
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
		"category": "CRM Tools",
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
)
