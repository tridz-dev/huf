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
# Project Management Tools
# ---------------------------------------------------------------------------

JIRA_TOOLS = [
	{
		"tool_name": "jira_get_issue",
		"description": "Retrieve details of a Jira issue. Requires JIRA_SERVER_URL, JIRA_USERNAME, JIRA_TOKEN env vars.",
		"function_path": "huf.ai.tools.jira_tools.handle_get_issue",
		"category": "Project Management Tools",
		"parameters": [
			_p("issue_key", required=True, description="Jira issue key (e.g. PROJ-123)"),
		],
	},
	{
		"tool_name": "jira_create_issue",
		"description": "Create a new Jira issue. Requires JIRA_SERVER_URL, JIRA_USERNAME, JIRA_TOKEN env vars.",
		"function_path": "huf.ai.tools.jira_tools.handle_create_issue",
		"category": "Project Management Tools",
		"parameters": [
			_p("project_key", required=True, description="Jira project key (e.g. PROJ)"),
			_p("summary", required=True, description="Issue summary/title"),
			_p("description", description="Issue description"),
			_p("issuetype", description="Issue type (default: Task)"),
		],
	},
	{
		"tool_name": "jira_search_issues",
		"description": "Search Jira issues using JQL query. Requires JIRA_SERVER_URL, JIRA_USERNAME, JIRA_TOKEN env vars.",
		"function_path": "huf.ai.tools.jira_tools.handle_search_issues",
		"category": "Project Management Tools",
		"parameters": [
			_p("jql", required=True, description="JQL query string"),
			_p("max_results", type="integer", description="Max results (default 50)"),
		],
	},
	{
		"tool_name": "jira_add_comment",
		"description": "Add a comment to a Jira issue. Requires JIRA_SERVER_URL, JIRA_USERNAME, JIRA_TOKEN env vars.",
		"function_path": "huf.ai.tools.jira_tools.handle_add_comment",
		"category": "Project Management Tools",
		"parameters": [
			_p("issue_key", required=True, description="Jira issue key"),
			_p("comment", required=True, description="Comment text"),
		],
	},
]

LINEAR_TOOLS = [
	{
		"tool_name": "linear_get_user",
		"description": "Fetch authenticated Linear user details. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_get_user_details",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "linear_get_teams",
		"description": "Fetch all teams in the Linear workspace. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_get_teams",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "linear_get_issue",
		"description": "Retrieve details of a Linear issue. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_get_issue",
		"category": "Project Management Tools",
		"parameters": [
			_p("issue_id", required=True, description="Linear issue ID"),
		],
	},
	{
		"tool_name": "linear_create_issue",
		"description": "Create a new issue in Linear. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_create_issue",
		"category": "Project Management Tools",
		"parameters": [
			_p("title", required=True, description="Issue title"),
			_p("description", description="Issue description"),
			_p("team_id", required=True, description="Team ID to create the issue in"),
		],
	},
	{
		"tool_name": "linear_update_issue",
		"description": "Update a Linear issue title. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_update_issue",
		"category": "Project Management Tools",
		"parameters": [
			_p("issue_id", required=True, description="Linear issue ID"),
			_p("title", required=True, description="New title"),
		],
	},
	{
		"tool_name": "linear_get_assigned_issues",
		"description": "Get issues assigned to a Linear user. Requires LINEAR_API_KEY env var.",
		"function_path": "huf.ai.tools.linear.handle_get_assigned_issues",
		"category": "Project Management Tools",
		"parameters": [
			_p("user_id", required=True, description="User ID"),
		],
	},
]

CLICKUP_TOOLS = [
	{
		"tool_name": "clickup_list_spaces",
		"description": "List all spaces in the ClickUp workspace. Requires CLICKUP_API_KEY and CLICKUP_SPACE_ID env vars.",
		"function_path": "huf.ai.tools.clickup.handle_list_spaces",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "clickup_list_lists",
		"description": "List all lists in a ClickUp space. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_list_lists",
		"category": "Project Management Tools",
		"parameters": [_p("space_id", required=True, description="ClickUp space ID")],
	},
	{
		"tool_name": "clickup_list_tasks",
		"description": "List all tasks in a ClickUp list. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_list_tasks",
		"category": "Project Management Tools",
		"parameters": [_p("list_id", required=True, description="ClickUp list ID")],
	},
	{
		"tool_name": "clickup_get_task",
		"description": "Get details of a ClickUp task. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_get_task",
		"category": "Project Management Tools",
		"parameters": [_p("task_id", required=True, description="ClickUp task ID")],
	},
	{
		"tool_name": "clickup_create_task",
		"description": "Create a new task in a ClickUp list. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_create_task",
		"category": "Project Management Tools",
		"parameters": [
			_p("list_id", required=True, description="ClickUp list ID"),
			_p("task_name", required=True, description="Task name"),
			_p("description", description="Task description"),
		],
	},
	{
		"tool_name": "clickup_update_task",
		"description": "Update a ClickUp task. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_update_task",
		"category": "Project Management Tools",
		"parameters": [
			_p("task_id", required=True, description="ClickUp task ID"),
			_p("name", description="New task name"),
			_p("description", description="New description"),
			_p("status", description="New status"),
		],
	},
	{
		"tool_name": "clickup_delete_task",
		"description": "Delete a ClickUp task. Requires CLICKUP_API_KEY env var.",
		"function_path": "huf.ai.tools.clickup.handle_delete_task",
		"category": "Project Management Tools",
		"parameters": [_p("task_id", required=True, description="ClickUp task ID")],
	},
]

TRELLO_TOOLS = [
	{
		"tool_name": "trello_list_boards",
		"description": "List all Trello boards. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_list_boards",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "trello_get_board_lists",
		"description": "Get all lists on a Trello board. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_get_board_lists",
		"category": "Project Management Tools",
		"parameters": [_p("board_id", required=True, description="Trello board ID")],
	},
	{
		"tool_name": "trello_get_cards",
		"description": "Get all cards in a Trello list. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_get_cards",
		"category": "Project Management Tools",
		"parameters": [_p("list_id", required=True, description="Trello list ID")],
	},
	{
		"tool_name": "trello_create_card",
		"description": "Create a new card in a Trello list. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_create_card",
		"category": "Project Management Tools",
		"parameters": [
			_p("list_id", required=True, description="Trello list ID"),
			_p("name", required=True, description="Card name/title"),
			_p("description", description="Card description"),
		],
	},
	{
		"tool_name": "trello_create_board",
		"description": "Create a new Trello board. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_create_board",
		"category": "Project Management Tools",
		"parameters": [_p("name", required=True, description="Board name")],
	},
	{
		"tool_name": "trello_move_card",
		"description": "Move a Trello card to a different list. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars.",
		"function_path": "huf.ai.tools.trello.handle_move_card",
		"category": "Project Management Tools",
		"parameters": [
			_p("card_id", required=True, description="Card ID to move"),
			_p("list_id", required=True, description="Destination list ID"),
		],
	},
]

NOTION_TOOLS = [
	{
		"tool_name": "notion_create_page",
		"description": "Create a new page in a Notion database. Requires NOTION_API_KEY env var.",
		"function_path": "huf.ai.tools.notion.handle_create_page",
		"category": "Project Management Tools",
		"parameters": [
			_p("title", required=True, description="Page title"),
			_p("content", description="Page content"),
			_p("tag", description="Page tag/category"),
			_p("database_id", description="Notion database ID (or set NOTION_DATABASE_ID env var)"),
		],
	},
	{
		"tool_name": "notion_update_page",
		"description": "Append content to a Notion page. Requires NOTION_API_KEY env var.",
		"function_path": "huf.ai.tools.notion.handle_update_page",
		"category": "Project Management Tools",
		"parameters": [
			_p("page_id", required=True, description="Notion page ID"),
			_p("content", required=True, description="Content to append"),
		],
	},
	{
		"tool_name": "notion_search_pages",
		"description": "Search for pages in a Notion database. Requires NOTION_API_KEY env var.",
		"function_path": "huf.ai.tools.notion.handle_search_pages",
		"category": "Project Management Tools",
		"parameters": [
			_p("tag", description="Tag to filter by"),
			_p("database_id", description="Notion database ID (or set NOTION_DATABASE_ID env var)"),
		],
	},
]

ZENDESK_TOOLS = [
	{
		"tool_name": "zendesk_search",
		"description": "Search Zendesk Help Center articles. Requires ZENDESK_USERNAME, ZENDESK_PASSWORD, ZENDESK_COMPANY_NAME env vars.",
		"function_path": "huf.ai.tools.zendesk.handle_search",
		"category": "Project Management Tools",
		"parameters": [_p("query", required=True, description="Search query")],
	},
]

CALCOM_TOOLS = [
	{
		"tool_name": "calcom_get_available_slots",
		"description": "Get available booking slots from Cal.com. Requires CALCOM_API_KEY env var.",
		"function_path": "huf.ai.tools.calcom.handle_get_available_slots",
		"category": "Project Management Tools",
		"parameters": [
			_p("start_date", description="Start date (YYYY-MM-DD)"),
			_p("end_date", description="End date (YYYY-MM-DD)"),
			_p("event_type_id", description="Event type ID (or set CALCOM_EVENT_TYPE_ID env var)"),
		],
	},
	{
		"tool_name": "calcom_create_booking",
		"description": "Create a booking on Cal.com. Requires CALCOM_API_KEY env var.",
		"function_path": "huf.ai.tools.calcom.handle_create_booking",
		"category": "Project Management Tools",
		"parameters": [
			_p("start_time", required=True, description="Booking start time (ISO 8601)"),
			_p("attendee_name", required=True, description="Attendee name"),
			_p("attendee_email", required=True, description="Attendee email"),
			_p("timezone", description="IANA timezone (default: UTC)"),
			_p("event_type_id", description="Event type ID"),
		],
	},
	{
		"tool_name": "calcom_list_bookings",
		"description": "List upcoming Cal.com bookings. Requires CALCOM_API_KEY env var.",
		"function_path": "huf.ai.tools.calcom.handle_list_bookings",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "calcom_cancel_booking",
		"description": "Cancel a Cal.com booking. Requires CALCOM_API_KEY env var.",
		"function_path": "huf.ai.tools.calcom.handle_cancel_booking",
		"category": "Project Management Tools",
		"parameters": [
			_p("booking_id", required=True, description="Booking ID to cancel"),
			_p("reason", description="Cancellation reason"),
		],
	},
]

ZOOM_TOOLS = [
	{
		"tool_name": "zoom_schedule_meeting",
		"description": "Schedule a Zoom meeting. Requires ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET env vars.",
		"function_path": "huf.ai.tools.zoom.handle_schedule_meeting",
		"category": "Project Management Tools",
		"parameters": [
			_p("topic", required=True, description="Meeting topic"),
			_p("start_time", required=True, description="Start time (ISO 8601)"),
			_p("duration", type="integer", description="Duration in minutes (default 30)"),
			_p("timezone", description="Timezone (default UTC)"),
		],
	},
	{
		"tool_name": "zoom_list_meetings",
		"description": "List Zoom meetings. Requires ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET env vars.",
		"function_path": "huf.ai.tools.zoom.handle_list_meetings",
		"category": "Project Management Tools",
		"parameters": [],
	},
	{
		"tool_name": "zoom_get_recordings",
		"description": "Get recordings for a Zoom meeting. Requires Zoom credentials.",
		"function_path": "huf.ai.tools.zoom.handle_get_meeting_recordings",
		"category": "Project Management Tools",
		"parameters": [_p("meeting_id", required=True, description="Zoom meeting ID")],
	},
	{
		"tool_name": "zoom_delete_meeting",
		"description": "Delete a Zoom meeting. Requires Zoom credentials.",
		"function_path": "huf.ai.tools.zoom.handle_delete_meeting",
		"category": "Project Management Tools",
		"parameters": [_p("meeting_id", required=True, description="Zoom meeting ID")],
	},
]

# ---------------------------------------------------------------------------
# Search Tools
# ---------------------------------------------------------------------------

DUCKDUCKGO_TOOLS = [
	{
		"tool_name": "duckduckgo_search",
		"description": "Search the web using DuckDuckGo. No API key required. Requires pip install duckduckgo-search.",
		"function_path": "huf.ai.tools.duckduckgo.handle_search",
		"category": "Search Tools",
		"parameters": [
			_p("query", required=True, description="Search query"),
			_p("max_results", type="integer", description="Max results (default 5)"),
		],
	},
	{
		"tool_name": "duckduckgo_news",
		"description": "Search news using DuckDuckGo. No API key required.",
		"function_path": "huf.ai.tools.duckduckgo.handle_news",
		"category": "Search Tools",
		"parameters": [
			_p("query", required=True, description="News search query"),
			_p("max_results", type="integer", description="Max results (default 5)"),
		],
	},
]

TAVILY_TOOLS = [
	{
		"tool_name": "tavily_search",
		"description": "AI-optimized web search using Tavily. Returns answers and results. Requires TAVILY_API_KEY env var.",
		"function_path": "huf.ai.tools.tavily.handle_search",
		"category": "Search Tools",
		"parameters": [
			_p("query", required=True, description="Search query"),
			_p("max_results", type="integer", description="Max results (default 5)"),
			_p("search_depth", description="'basic' or 'advanced' (default: advanced)"),
		],
	},
	{
		"tool_name": "tavily_extract_url",
		"description": "Extract content from URLs using Tavily. Requires TAVILY_API_KEY env var.",
		"function_path": "huf.ai.tools.tavily.handle_extract_url",
		"category": "Search Tools",
		"parameters": [
			_p("urls", required=True, description="Comma-separated URLs to extract content from"),
		],
	},
]

SERPER_TOOLS = [
	{
		"tool_name": "serper_search_web",
		"description": "Search Google via Serper API. Requires SERPER_API_KEY env var.",
		"function_path": "huf.ai.tools.serper.handle_search_web",
		"category": "Search Tools",
		"parameters": [_p("query", required=True, description="Search query")],
	},
	{
		"tool_name": "serper_search_news",
		"description": "Search news via Serper API. Requires SERPER_API_KEY env var.",
		"function_path": "huf.ai.tools.serper.handle_search_news",
		"category": "Search Tools",
		"parameters": [_p("query", required=True, description="News search query")],
	},
	{
		"tool_name": "serper_search_scholar",
		"description": "Search academic papers via Serper API. Requires SERPER_API_KEY env var.",
		"function_path": "huf.ai.tools.serper.handle_search_scholar",
		"category": "Search Tools",
		"parameters": [_p("query", required=True, description="Academic search query")],
	},
]

SERPAPI_TOOLS = [
	{
		"tool_name": "serpapi_search_google",
		"description": "Search Google using SerpApi. Requires SERP_API_KEY env var.",
		"function_path": "huf.ai.tools.serpapi.handle_search_google",
		"category": "Search Tools",
		"parameters": [_p("query", required=True, description="Search query")],
	},
	{
		"tool_name": "serpapi_search_youtube",
		"description": "Search YouTube using SerpApi. Requires SERP_API_KEY env var.",
		"function_path": "huf.ai.tools.serpapi.handle_search_youtube",
		"category": "Search Tools",
		"parameters": [_p("query", required=True, description="YouTube search query")],
	},
]

BRAVE_SEARCH_TOOLS = [
	{
		"tool_name": "brave_search",
		"description": "Privacy-focused web search using Brave Search. Requires BRAVE_API_KEY env var.",
		"function_path": "huf.ai.tools.brave_search.handle_search",
		"category": "Search Tools",
		"parameters": [
			_p("query", required=True, description="Search query"),
			_p("max_results", type="integer", description="Max results (default 5)"),
			_p("country", description="Country code (e.g. US)"),
		],
	},
]

BAIDU_SEARCH_TOOLS = [
	{
		"tool_name": "baidu_search",
		"description": "Search using Baidu (Chinese search engine). No API key required.",
		"function_path": "huf.ai.tools.baidu_search.handle_search",
		"category": "Search Tools",
		"parameters": [
			_p("query", required=True, description="Search query"),
			_p("max_results", type="integer", description="Max results (default 5)"),
		],
	},
]

# ---------------------------------------------------------------------------
# Data Source Tools
# ---------------------------------------------------------------------------

HACKERNEWS_TOOLS = [
	{
		"tool_name": "hackernews_top_stories",
		"description": "Get top stories from Hacker News. No API key required.",
		"function_path": "huf.ai.tools.hackernews.handle_get_top_stories",
		"category": "Data Source Tools",
		"parameters": [
			_p("num_stories", type="integer", description="Number of stories (default 10)"),
		],
	},
	{
		"tool_name": "hackernews_get_user",
		"description": "Get details of a Hacker News user. No API key required.",
		"function_path": "huf.ai.tools.hackernews.handle_get_user",
		"category": "Data Source Tools",
		"parameters": [_p("username", required=True, description="HN username")],
	},
]

REDDIT_TOOLS = [
	{
		"tool_name": "reddit_top_posts",
		"description": "Get top posts from a subreddit. Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.",
		"function_path": "huf.ai.tools.reddit.handle_get_top_posts",
		"category": "Data Source Tools",
		"parameters": [
			_p("subreddit", required=True, description="Subreddit name (without r/)"),
			_p("time_filter", description="Time filter: hour, day, week, month, year, all (default: week)"),
			_p("limit", type="integer", description="Max posts (default 10)"),
		],
	},
	{
		"tool_name": "reddit_get_user",
		"description": "Get info about a Reddit user. Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.",
		"function_path": "huf.ai.tools.reddit.handle_get_user_info",
		"category": "Data Source Tools",
		"parameters": [_p("username", required=True, description="Reddit username")],
	},
]

WIKIPEDIA_TOOLS = [
	{
		"tool_name": "wikipedia_search",
		"description": "Search Wikipedia and get a summary. No API key required.",
		"function_path": "huf.ai.tools.wikipedia.handle_search",
		"category": "Data Source Tools",
		"parameters": [_p("query", required=True, description="Topic to search for")],
	},
]

YOUTUBE_TOOLS = [
	{
		"tool_name": "youtube_get_video_data",
		"description": "Get metadata (title, author, views) of a YouTube video. Requires pip install pytubefix.",
		"function_path": "huf.ai.tools.youtube.handle_get_video_data",
		"category": "Data Source Tools",
		"parameters": [_p("url", required=True, description="YouTube video URL")],
	},
	{
		"tool_name": "youtube_get_captions",
		"description": "Get transcript/captions of a YouTube video. Requires pip install youtube-transcript-api.",
		"function_path": "huf.ai.tools.youtube.handle_get_captions",
		"category": "Data Source Tools",
		"parameters": [_p("url", required=True, description="YouTube video URL")],
	},
]

OPENWEATHER_TOOLS = [
	{
		"tool_name": "openweather_current",
		"description": "Get current weather for a location. Requires OPENWEATHER_API_KEY env var.",
		"function_path": "huf.ai.tools.openweather.handle_get_current_weather",
		"category": "Data Source Tools",
		"parameters": [_p("location", required=True, description="City name or location")],
	},
	{
		"tool_name": "openweather_forecast",
		"description": "Get 5-day weather forecast. Requires OPENWEATHER_API_KEY env var.",
		"function_path": "huf.ai.tools.openweather.handle_get_forecast",
		"category": "Data Source Tools",
		"parameters": [_p("location", required=True, description="City name or location")],
	},
	{
		"tool_name": "openweather_air_pollution",
		"description": "Get air pollution data. Requires OPENWEATHER_API_KEY env var.",
		"function_path": "huf.ai.tools.openweather.handle_get_air_pollution",
		"category": "Data Source Tools",
		"parameters": [_p("location", required=True, description="City name or location")],
	},
]

# ---------------------------------------------------------------------------
# Finance Tools
# ---------------------------------------------------------------------------

YFINANCE_TOOLS = [
	{
		"tool_name": "yfinance_stock_price",
		"description": "Get current stock price. Requires pip install yfinance. No API key needed.",
		"function_path": "huf.ai.tools.yfinance.handle_get_stock_price",
		"category": "Finance Tools",
		"parameters": [_p("symbol", required=True, description="Stock symbol (e.g. AAPL)")],
	},
	{
		"tool_name": "yfinance_company_info",
		"description": "Get company information for a stock. Requires pip install yfinance.",
		"function_path": "huf.ai.tools.yfinance.handle_get_company_info",
		"category": "Finance Tools",
		"parameters": [_p("symbol", required=True, description="Stock symbol (e.g. AAPL)")],
	},
	{
		"tool_name": "yfinance_historical_prices",
		"description": "Get historical stock prices. Requires pip install yfinance.",
		"function_path": "huf.ai.tools.yfinance.handle_get_historical_prices",
		"category": "Finance Tools",
		"parameters": [
			_p("symbol", required=True, description="Stock symbol"),
			_p("period", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y (default: 1mo)"),
			_p("interval", description="Interval: 1m, 5m, 1h, 1d, 1wk (default: 1d)"),
		],
	},
	{
		"tool_name": "yfinance_analyst_recommendations",
		"description": "Get analyst recommendations for a stock. Requires pip install yfinance.",
		"function_path": "huf.ai.tools.yfinance.handle_get_analyst_recommendations",
		"category": "Finance Tools",
		"parameters": [_p("symbol", required=True, description="Stock symbol")],
	},
	{
		"tool_name": "yfinance_company_news",
		"description": "Get recent news for a stock. Requires pip install yfinance.",
		"function_path": "huf.ai.tools.yfinance.handle_get_company_news",
		"category": "Finance Tools",
		"parameters": [
			_p("symbol", required=True, description="Stock symbol"),
			_p("num_stories", type="integer", description="Number of stories (default 5)"),
		],
	},
]

SHOPIFY_TOOLS = [
	{
		"tool_name": "shopify_get_shop_info",
		"description": "Get Shopify store information. Requires SHOPIFY_SHOP_NAME and SHOPIFY_ACCESS_TOKEN env vars.",
		"function_path": "huf.ai.tools.shopify.handle_get_shop_info",
		"category": "Finance Tools",
		"parameters": [],
	},
	{
		"tool_name": "shopify_get_products",
		"description": "Get products from a Shopify store. Requires SHOPIFY_SHOP_NAME and SHOPIFY_ACCESS_TOKEN env vars.",
		"function_path": "huf.ai.tools.shopify.handle_get_products",
		"category": "Finance Tools",
		"parameters": [_p("max_results", type="integer", description="Max products (default 50)")],
	},
	{
		"tool_name": "shopify_get_orders",
		"description": "Get orders from a Shopify store. Requires SHOPIFY_SHOP_NAME and SHOPIFY_ACCESS_TOKEN env vars.",
		"function_path": "huf.ai.tools.shopify.handle_get_orders",
		"category": "Finance Tools",
		"parameters": [_p("max_results", type="integer", description="Max orders (default 50)")],
	},
	{
		"tool_name": "shopify_get_inventory",
		"description": "Get inventory levels from a Shopify store. Requires SHOPIFY_SHOP_NAME and SHOPIFY_ACCESS_TOKEN env vars.",
		"function_path": "huf.ai.tools.shopify.handle_get_inventory",
		"category": "Finance Tools",
		"parameters": [],
	},
]

# ---------------------------------------------------------------------------
# Google Suite Tools
# ---------------------------------------------------------------------------

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

DOCKER_TOOLS = [
	{
		"tool_name": "docker_list_containers",
		"description": "List Docker containers. Requires Docker daemon access.",
		"function_path": "huf.ai.tools.docker_tools.handle_list_containers",
		"category": "Developer Tools",
		"parameters": [_p("all", type="boolean", description="Include stopped containers")],
	},
	{
		"tool_name": "docker_run_container",
		"description": "Run a Docker container. Requires Docker daemon access.",
		"function_path": "huf.ai.tools.docker_tools.handle_run_container",
		"category": "Developer Tools",
		"parameters": [
			_p("image", required=True, description="Docker image name"),
			_p("command", description="Command to run"),
			_p("name", description="Container name"),
		],
	},
	{
		"tool_name": "docker_get_logs",
		"description": "Get logs from a Docker container. Requires Docker daemon access.",
		"function_path": "huf.ai.tools.docker_tools.handle_get_container_logs",
		"category": "Developer Tools",
		"parameters": [
			_p("container_id", required=True, description="Container ID or name"),
			_p("tail", type="integer", description="Number of log lines (default 100)"),
		],
	},
	{
		"tool_name": "docker_list_images",
		"description": "List Docker images. Requires Docker daemon access.",
		"function_path": "huf.ai.tools.docker_tools.handle_list_images",
		"category": "Developer Tools",
		"parameters": [],
	},
	{
		"tool_name": "docker_pull_image",
		"description": "Pull a Docker image. Requires Docker daemon access.",
		"function_path": "huf.ai.tools.docker_tools.handle_pull_image",
		"category": "Developer Tools",
		"parameters": [_p("image_name", required=True, description="Image name to pull")],
	},
]

# ---------------------------------------------------------------------------
# AWS Tools
# ---------------------------------------------------------------------------

AWS_SES_TOOLS = [
	{
		"tool_name": "aws_ses_send_email",
		"description": "Send an email using Amazon SES. Requires AWS credentials and pip install boto3.",
		"function_path": "huf.ai.tools.aws_ses.handle_send_email",
		"category": "Cloud Tools",
		"parameters": [
			_p("receiver_email", required=True, description="Recipient email address"),
			_p("subject", required=True, description="Email subject"),
			_p("body", required=True, description="Email body (HTML supported)"),
			_p("sender", description="Sender email (or set AWS_SES_SENDER env var)"),
		],
	},
]

# ---------------------------------------------------------------------------
# Media Tools
# ---------------------------------------------------------------------------

UNSPLASH_TOOLS = [
	{
		"tool_name": "unsplash_search_photos",
		"description": "Search for photos on Unsplash. Requires UNSPLASH_ACCESS_KEY env var.",
		"function_path": "huf.ai.tools.unsplash.handle_search_photos",
		"category": "Media Tools",
		"parameters": [
			_p("query", required=True, description="Photo search query"),
			_p("per_page", type="integer", description="Results per page (default 10)"),
		],
	},
	{
		"tool_name": "unsplash_random_photo",
		"description": "Get a random photo from Unsplash. Requires UNSPLASH_ACCESS_KEY env var.",
		"function_path": "huf.ai.tools.unsplash.handle_get_random_photo",
		"category": "Media Tools",
		"parameters": [_p("query", description="Optional topic to filter by")],
	},
]

GIPHY_TOOLS = [
	{
		"tool_name": "giphy_search",
		"description": "Search for GIFs on Giphy. Requires GIPHY_API_KEY env var.",
		"function_path": "huf.ai.tools.giphy.handle_search_gifs",
		"category": "Media Tools",
		"parameters": [
			_p("query", required=True, description="GIF search query"),
			_p("limit", type="integer", description="Max GIFs (default 10)"),
		],
	},
	{
		"tool_name": "giphy_trending",
		"description": "Get trending GIFs from Giphy. Requires GIPHY_API_KEY env var.",
		"function_path": "huf.ai.tools.giphy.handle_trending_gifs",
		"category": "Media Tools",
		"parameters": [_p("limit", type="integer", description="Max GIFs (default 10)")],
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
# Master list: every tool grouped for easy iteration
# ---------------------------------------------------------------------------

ALL_INTEGRATION_TOOLS = (
	RECIPIENT_TOOLS
	+ SLACK_TOOLS
	+ DISCORD_TOOLS
	+ TELEGRAM_TOOLS
	+ JIRA_TOOLS
	+ LINEAR_TOOLS
	+ CLICKUP_TOOLS
	+ TRELLO_TOOLS
	+ NOTION_TOOLS
	+ ZENDESK_TOOLS
	+ CALCOM_TOOLS
	+ ZOOM_TOOLS
	+ DUCKDUCKGO_TOOLS
	+ TAVILY_TOOLS
	+ SERPER_TOOLS
	+ SERPAPI_TOOLS
	+ BRAVE_SEARCH_TOOLS
	+ BAIDU_SEARCH_TOOLS
	+ HACKERNEWS_TOOLS
	+ REDDIT_TOOLS
	+ WIKIPEDIA_TOOLS
	+ YOUTUBE_TOOLS
	+ OPENWEATHER_TOOLS
	+ YFINANCE_TOOLS
	+ SHOPIFY_TOOLS
	+ GMAIL_TOOLS
	+ GOOGLE_SHEETS_TOOLS
	+ GOOGLE_CALENDAR_TOOLS
	+ GOOGLE_MAPS_TOOLS
	+ GOOGLE_DRIVE_TOOLS
	+ GITHUB_TOOLS
	+ DOCKER_TOOLS
	+ AWS_SES_TOOLS
	+ UNSPLASH_TOOLS
	+ GIPHY_TOOLS
)
