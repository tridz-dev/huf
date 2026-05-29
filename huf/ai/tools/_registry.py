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
# Developer Tools
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

GMAIL_TOOLS = [
	{
		"tool_name": "gmail_get_emails",
		"description": "Get latest emails from Gmail. Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN env vars.",
		"function_path": "huf.ai.tools.gmail.handle_get_emails",
		"category": "Google Tools",
		"parameters": [
			_p("count", type="integer", description="Number of emails (default 10)"),
			_p("query", description="Gmail search query to filter emails"),
		],
	},
	{
		"tool_name": "gmail_send_email",
		"description": "Send an email via Gmail. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.gmail.handle_send_email",
		"category": "Google Tools",
		"parameters": [
			_p("to", required=True, description="Recipient email address"),
			_p("subject", required=True, description="Email subject"),
			_p("body", required=True, description="Email body (plain text)"),
		],
	},
	{
		"tool_name": "gmail_create_draft",
		"description": "Create a draft email in Gmail. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.gmail.handle_create_draft",
		"category": "Google Tools",
		"parameters": [
			_p("to", required=True, description="Recipient email address"),
			_p("subject", required=True, description="Email subject"),
			_p("body", required=True, description="Email body"),
		],
	},
	{
		"tool_name": "gmail_mark_as_read",
		"description": "Mark an email as read in Gmail. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.gmail.handle_mark_as_read",
		"category": "Google Tools",
		"parameters": [_p("message_id", required=True, description="Gmail message ID")],
	},
]

GOOGLE_SHEETS_TOOLS = [
	{
		"tool_name": "gsheets_read",
		"description": "Read data from a Google Sheets spreadsheet. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_sheets.handle_read_sheet",
		"category": "Google Tools",
		"parameters": [
			_p("spreadsheet_id", required=True, description="Google Sheets spreadsheet ID"),
			_p("range", description="Cell range (e.g. Sheet1!A1:D10, default: Sheet1)"),
		],
	},
	{
		"tool_name": "gsheets_update",
		"description": "Update data in a Google Sheets spreadsheet. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_sheets.handle_update_sheet",
		"category": "Google Tools",
		"parameters": [
			_p("spreadsheet_id", required=True, description="Google Sheets spreadsheet ID"),
			_p("range", required=True, description="Cell range to update"),
			_p("data", required=True, description="2D array of values as JSON string"),
		],
	},
	{
		"tool_name": "gsheets_create",
		"description": "Create a new Google Sheets spreadsheet. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_sheets.handle_create_sheet",
		"category": "Google Tools",
		"parameters": [_p("title", required=True, description="Spreadsheet title")],
	},
]

GOOGLE_CALENDAR_TOOLS = [
	{
		"tool_name": "gcalendar_list_events",
		"description": "List upcoming Google Calendar events. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_calendar.handle_list_events",
		"category": "Google Tools",
		"parameters": [
			_p("limit", type="integer", description="Max events (default 10)"),
			_p("start_date", description="Start date filter (ISO 8601)"),
		],
	},
	{
		"tool_name": "gcalendar_create_event",
		"description": "Create a Google Calendar event. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_calendar.handle_create_event",
		"category": "Google Tools",
		"parameters": [
			_p("title", required=True, description="Event title"),
			_p("start_date", required=True, description="Start datetime (ISO 8601)"),
			_p("end_date", required=True, description="End datetime (ISO 8601)"),
			_p("description", description="Event description"),
			_p("timezone", description="Timezone (default: UTC)"),
		],
	},
	{
		"tool_name": "gcalendar_update_event",
		"description": "Update a Google Calendar event. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_calendar.handle_update_event",
		"category": "Google Tools",
		"parameters": [
			_p("event_id", required=True, description="Google Calendar event ID"),
			_p("title", description="New event title"),
			_p("description", description="New event description"),
		],
	},
	{
		"tool_name": "gcalendar_delete_event",
		"description": "Delete a Google Calendar event. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_calendar.handle_delete_event",
		"category": "Google Tools",
		"parameters": [_p("event_id", required=True, description="Google Calendar event ID")],
	},
]

GOOGLE_MAPS_TOOLS = [
	{
		"tool_name": "gmaps_search_places",
		"description": "Search for places using Google Maps. Requires GOOGLE_MAPS_API_KEY env var.",
		"function_path": "huf.ai.tools.google_maps.handle_search_places",
		"category": "Google Tools",
		"parameters": [_p("query", required=True, description="Place search query")],
	},
	{
		"tool_name": "gmaps_get_directions",
		"description": "Get directions between locations using Google Maps. Requires GOOGLE_MAPS_API_KEY env var.",
		"function_path": "huf.ai.tools.google_maps.handle_get_directions",
		"category": "Google Tools",
		"parameters": [
			_p("origin", required=True, description="Starting location"),
			_p("destination", required=True, description="Destination location"),
			_p("mode", description="Travel mode: driving, walking, bicycling, transit (default: driving)"),
		],
	},
	{
		"tool_name": "gmaps_geocode",
		"description": "Convert an address to coordinates. Requires GOOGLE_MAPS_API_KEY env var.",
		"function_path": "huf.ai.tools.google_maps.handle_geocode",
		"category": "Google Tools",
		"parameters": [_p("address", required=True, description="Address to geocode")],
	},
	{
		"tool_name": "gmaps_reverse_geocode",
		"description": "Convert coordinates to an address. Requires GOOGLE_MAPS_API_KEY env var.",
		"function_path": "huf.ai.tools.google_maps.handle_reverse_geocode",
		"category": "Google Tools",
		"parameters": [
			_p("lat", required=True, description="Latitude"),
			_p("lng", required=True, description="Longitude"),
		],
	},
]

GOOGLE_DRIVE_TOOLS = [
	{
		"tool_name": "gdrive_list_files",
		"description": "List files in Google Drive. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_drive.handle_list_files",
		"category": "Google Tools",
		"parameters": [
			_p("limit", type="integer", description="Max files (default 20)"),
			_p("query", description="Drive search query"),
		],
	},
	{
		"tool_name": "gdrive_get_file",
		"description": "Get metadata of a Google Drive file. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_drive.handle_get_file",
		"category": "Google Tools",
		"parameters": [_p("file_id", required=True, description="Google Drive file ID")],
	},
	{
		"tool_name": "gdrive_search_files",
		"description": "Search for files in Google Drive. Requires Google OAuth credentials.",
		"function_path": "huf.ai.tools.google_drive.handle_search_files",
		"category": "Google Tools",
		"parameters": [_p("query", required=True, description="Search query")],
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
	+ GMAIL_TOOLS
	+ GOOGLE_SHEETS_TOOLS
	+ GOOGLE_CALENDAR_TOOLS
	+ GOOGLE_MAPS_TOOLS
	+ GOOGLE_DRIVE_TOOLS
)
