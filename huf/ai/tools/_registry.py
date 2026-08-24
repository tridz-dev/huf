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


def _action(choices):
	return _p("action", required=True, description=f"Action to perform. One of: {choices}")


# ---------------------------------------------------------------------------
# Communication & Developer Tools
# Shipped in develop (PR #273). Not refactored — kept exactly as-is.
# ---------------------------------------------------------------------------

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
		"tool_name": "telegram",
		"description": (
			"Manage a Telegram bot. Actions: send_message (chat_id or recipient_name, text/message, parse_mode), "
			"reply_to_message (chat_id or recipient_name, text/message, reply_to_message_id), "
			"send_photo (chat_id or recipient_name, photo/file/file_url, caption), "
			"send_document (chat_id or recipient_name, document/file/file_url, caption), "
			"edit_message_text (chat_id or recipient_name, message_id, text/message), "
			"delete_message (chat_id or recipient_name, message_id), "
			"get_updates (offset, limit), get_chat_info (chat_id or recipient_name), get_me, "
			"set_webhook (url, secret_token), delete_webhook. "
			"Use get_integration_recipient to resolve a human name to a Telegram chat ID."
		),
		"function_path": "huf.ai.tools.telegram.handle_action",
		"category": "Communication Tools",
		"parameters": [
			_action(
				"send_message|reply_to_message|send_photo|send_document|"
				"edit_message_text|delete_message|get_updates|get_chat_info|get_me|set_webhook|delete_webhook"
			),
			_p("chat_id", description="Telegram chat/channel ID (numeric or @username). Alternative to recipient_name."),
			_p("recipient_name", description="Human-friendly recipient name from Integration Settings (alternative to chat_id)."),
			_p("message", description="Message text (alias for text)."),
			_p("text", description="Message or edited text."),
			_p("photo", description="Photo source: Telegram file_id, public URL, or Frappe File docname/file_url."),
			_p("document", description="Document source: Telegram file_id, public URL, or Frappe File docname/file_url."),
			_p("file", description="Generic file source alias for photo/document."),
			_p("file_url", description="Public file URL alias for photo/document."),
			_p("caption", description="Caption for photo/document messages."),
			_p("parse_mode", description="Text formatting: Markdown, HTML, or MarkdownV2."),
			_p("reply_to_message_id", type="integer", description="Message ID to reply to."),
			_p("message_id", type="integer", description="Message ID to edit or delete."),
			_p("url", description="Webhook URL for set_webhook."),
			_p("secret_token", description="Secret token for webhook verification."),
			_p("offset", type="integer", description="Update offset for get_updates."),
			_p("limit", type="integer", description="Max updates for get_updates (max 100)."),
			_p("disable_notification", type="boolean", description="Send message silently."),
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

# ---------------------------------------------------------------------------
# Frappe App Tools  (added in this branch — consolidated action-based)
# ---------------------------------------------------------------------------

CRM_TOOLS = [{
    "tool_name": "frappe_crm",
    "description": "Manage Frappe CRM (standalone app). Actions: list_leads (status, assigned_to, search, limit), get_lead (name), create_lead (first_name required; last_name, email, mobile_no, lead_owner, source, organization, notes), update_lead (name required; any field), list_deals (status, deal_owner, search, limit), get_deal (name), create_deal (organization; or lead to copy from), update_deal (name required; status, deal_value, probability, expected_closure_date), add_note (doctype, docname, content, title), add_task (title, reference_doctype, reference_docname; assigned_to, due_date, priority), list_contacts (search, limit).",
    "function_path": "huf.ai.tools.crm.handle_action",
    "category": "Frappe CRM Tools",
    "parameters": [
        _action("list_leads|get_lead|create_lead|update_lead|list_deals|get_deal|create_deal|update_deal|add_note|add_task|list_contacts"),
        _p("name", description="Document name/ID"),
        _p("first_name", description="Lead first name"),
        _p("last_name", description="Lead last name"),
        _p("email", description="Email address"),
        _p("mobile_no", description="Mobile number"),
        _p("lead_owner", description="Assigned user email"),
        _p("organization", description="Company/organization name"),
        _p("status", description="Status filter or value to set"),
        _p("search", description="Search query"),
        _p("doctype", description="DocType for note/task (CRM Lead or CRM Deal)"),
        _p("docname", description="Document name for note/task"),
        _p("content", description="Note content"),
        _p("title", description="Note or task title"),
        _p("deal_value", type="number", description="Deal value amount"),
        _p("probability", type="integer", description="Win probability 0-100"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

HELPDESK_TOOLS = [{
    "tool_name": "helpdesk",
    "description": "Manage Frappe Helpdesk tickets. Actions: list_tickets (status, priority, team, search, limit), get_ticket (ticket_id — includes comments), create_ticket (subject required; description, customer, priority, type, team), update_ticket (ticket_id required; status, priority, team, description, assigned_to), add_comment (ticket_id, content), list_agents (limit), list_teams (limit), assign_ticket (ticket_id, agent_id).",
    "function_path": "huf.ai.tools.helpdesk.handle_action",
    "category": "Helpdesk Tools",
    "parameters": [
        _action("list_tickets|get_ticket|create_ticket|update_ticket|add_comment|list_agents|list_teams|assign_ticket"),
        _p("ticket_id", description="Ticket ID (HD-XXXXX)"),
        _p("subject", description="Ticket subject"),
        _p("description", description="Ticket description or updated text"),
        _p("status", description="Status: Open, Replied, Resolved, Closed"),
        _p("priority", description="Priority: Low, Medium, High, Urgent"),
        _p("team", description="Team name"),
        _p("customer", description="Customer name"),
        _p("content", description="Comment text"),
        _p("agent_id", description="Agent user ID for assignment"),
        _p("search", description="Search query"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

RAVEN_TOOLS = [{
    "tool_name": "raven",
    "description": "Interact with Frappe Raven internal messaging. Actions: send_message (channel_id or channel_name, text), get_messages (channel_id or channel_name, limit, before_message_id), list_channels (channel_type, limit), get_members (channel_id or channel_name), create_channel (channel_name, type, channel_description, members list), search_messages (query; channel_id or channel_name, limit).",
    "function_path": "huf.ai.tools.raven.handle_action",
    "category": "Raven Tools",
    "parameters": [
        _action("send_message|get_messages|list_channels|get_members|create_channel|search_messages"),
        _p("channel_id", description="Raven channel ID"),
        _p("channel_name", description="Channel name (alternative to channel_id)"),
        _p("text", description="Message text"),
        _p("channel_type", description="Channel type filter: Public, Private, Open"),
        _p("members", description="JSON list of user IDs (for create_channel)"),
        _p("channel_description", description="Channel description"),
        _p("query", description="Search text"),
        _p("before_message_id", description="Pagination cursor"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

# ---------------------------------------------------------------------------
# ERPNext Tools  (added in this branch — consolidated action-based)
# ---------------------------------------------------------------------------

ERPNEXT_TOOLS = [{
    "tool_name": "erpnext",
    "description": "Manage ERPNext transactions and accounting. Actions: list_sales_invoices (customer, status, from_date, to_date, limit), get_sales_invoice (name), create_sales_invoice (customer required, items list [{item_code,qty,rate}], company, posting_date), list_purchase_invoices (supplier, status, from_date, to_date, limit), get_purchase_invoice (name), list_payments (party_type, party, payment_type, from_date, to_date, limit), create_payment (payment_type required [Receive/Pay], party_type required, party required, paid_amount required; mode_of_payment, invoice_name, source_exchange_rate, target_exchange_rate), list_customers (search, customer_group, limit), get_customer (name), list_quotations (party_name, status, from_date, limit), create_quotation (quotation_to required [Customer/Lead], party_name required, items list, transaction_date, valid_till), list_rfqs (status, from_date, limit), get_ledger (account required, from_date, to_date, party_type, party, limit), create_journal_entry (voucher_type, posting_date, company, user_remark, accounts list [{account, debit_in_account_currency, credit_in_account_currency}]).",
    "function_path": "huf.ai.tools.erpnext.handle_action",
    "category": "ERPNext Tools",
    "parameters": [
        _action("list_sales_invoices|get_sales_invoice|create_sales_invoice|list_purchase_invoices|get_purchase_invoice|list_payments|create_payment|list_customers|get_customer|list_quotations|create_quotation|list_rfqs|get_ledger|create_journal_entry"),
        _p("name", description="Document name/ID"),
        _p("customer", description="Customer name"),
        _p("supplier", description="Supplier name"),
        _p("party_type", description="Party type: Customer or Supplier"),
        _p("party", description="Party name"),
        _p("payment_type", description="Payment type: Receive, Pay, Internal Transfer"),
        _p("paid_amount", type="number", description="Payment amount"),
        _p("invoice_name", description="Invoice to link payment to"),
        _p("mode_of_payment", description="Mode of payment"),
        _p("source_exchange_rate", type="number", description="Source exchange rate (if different currency)"),
        _p("target_exchange_rate", type="number", description="Target exchange rate (if different currency)"),
        _p("account", description="Account name (for get_ledger)"),
        _p("status", description="Document status filter"),
        _p("from_date", description="Start date (YYYY-MM-DD)"),
        _p("to_date", description="End date (YYYY-MM-DD)"),
        _p("company", description="Company name (defaults to user default)"),
        _p("posting_date", description="Posting date"),
        _p("items", description="JSON list of items [{item_code, qty, rate}]"),
        _p("accounts", description="JSON list of journal accounts [{account, debit_in_account_currency, credit_in_account_currency}]"),
        _p("voucher_type", description="Journal voucher type"),
        _p("user_remark", description="Journal entry remark"),
        _p("quotation_to", description="Quotation for: Customer or Lead"),
        _p("party_name", description="Customer/Lead name for quotation"),
        _p("search", description="Search query"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

ERPNEXT_CRM_TOOLS = [{
    "tool_name": "erpnext_crm",
    "description": "Manage ERPNext built-in CRM (Lead and Opportunity doctypes — part of ERPNext, different from standalone Frappe CRM). Actions: list_leads (status, lead_owner, search, limit), get_lead (name), create_lead (lead_name required; company_name, email_id, mobile_no, lead_owner, type, industry, territory), update_lead (name required; status, lead_owner, email_id, territory), list_opportunities (status, party_name, from_date, limit), create_opportunity (opportunity_from required [Customer/Lead], party_name required; title, opportunity_type, opportunity_amount, sales_stage, probability, expected_closing), update_opportunity (name required; status, opportunity_amount, sales_stage, probability, expected_closing).",
    "function_path": "huf.ai.tools.erpnext_crm.handle_action",
    "category": "ERPNext CRM Tools",
    "parameters": [
        _action("list_leads|get_lead|create_lead|update_lead|list_opportunities|create_opportunity|update_opportunity"),
        _p("name", description="Document name/ID"),
        _p("lead_name", description="Lead full name"),
        _p("company_name", description="Company name"),
        _p("email_id", description="Email address"),
        _p("mobile_no", description="Mobile number"),
        _p("lead_owner", description="Assigned user email"),
        _p("status", description="Status filter or value to set"),
        _p("territory", description="Territory"),
        _p("industry", description="Industry"),
        _p("opportunity_from", description="Opportunity from: Customer or Lead"),
        _p("party_name", description="Customer or Lead name"),
        _p("opportunity_amount", type="number", description="Opportunity value"),
        _p("sales_stage", description="Sales stage"),
        _p("probability", type="integer", description="Win probability 0-100"),
        _p("expected_closing", description="Expected closing date (YYYY-MM-DD)"),
        _p("search", description="Search query"),
        _p("from_date", description="Filter from date"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

ERPNEXT_INVENTORY_TOOLS = [{
    "tool_name": "erpnext_inventory",
    "description": "Manage ERPNext inventory, items, BOM and stock. Actions: list_items (search, item_group, is_stock_item, limit), get_item (name — item_code), item_prices (item_code, price_list, buying, selling), stock_balance (item_code, warehouse, as_of_date), stock_movements (item_code, warehouse, from_date, to_date, limit), list_stock_entries (stock_entry_type, from_date, to_date, limit), list_warehouses (company, limit), list_delivery_notes (customer, from_date, to_date, limit), list_purchase_receipts (supplier, from_date, to_date, limit), list_boms (item, is_active, is_default, limit), get_bom (name), create_bom (item required, quantity, items list [{item_code, qty, uom, rate}]).",
    "function_path": "huf.ai.tools.erpnext_inventory.handle_action",
    "category": "ERPNext Inventory",
    "parameters": [
        _action("list_items|get_item|item_prices|stock_balance|stock_movements|list_stock_entries|list_warehouses|list_delivery_notes|list_purchase_receipts|list_boms|get_bom|create_bom"),
        _p("name", description="Document name or item_code"),
        _p("item_code", description="Item code"),
        _p("item_group", description="Item group filter"),
        _p("is_stock_item", type="integer", description="1 for stock items only, 0 for all"),
        _p("price_list", description="Price list name"),
        _p("warehouse", description="Warehouse name"),
        _p("as_of_date", description="Stock balance as of date (YYYY-MM-DD)"),
        _p("stock_entry_type", description="Material Issue, Material Receipt, Material Transfer, Manufacture"),
        _p("customer", description="Customer name filter"),
        _p("supplier", description="Supplier name filter"),
        _p("item", description="Item code for BOM filter"),
        _p("is_active", type="integer", description="1 for active BOMs"),
        _p("is_default", type="integer", description="1 for default BOMs"),
        _p("quantity", type="number", description="BOM quantity"),
        _p("items", description="JSON list of BOM items [{item_code, qty, uom, rate}]"),
        _p("from_date", description="Start date (YYYY-MM-DD)"),
        _p("to_date", description="End date (YYYY-MM-DD)"),
        _p("search", description="Search query"),
        _p("company", description="Company name"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

ERPNEXT_REPORT_TOOLS = [
    {
        "tool_name": "erpnext_run_report",
        "description": "Run any ERPNext script or query report by name and get results. Use erpnext_list_reports to discover available report names and their modules. Common reports: 'Balance Sheet', 'Profit and Loss Statement', 'Cash Flow', 'General Ledger', 'Accounts Receivable', 'Accounts Payable', 'Stock Balance', 'Stock Ledger', 'Sales Register', 'Purchase Register', 'Sales Analytics', 'Sales Pipeline Analytics', 'Lead Details'. Pass filters as a JSON object with keys like company, from_date, to_date, fiscal_year, etc.",
        "function_path": "huf.ai.tools.erpnext_reports.handle_run_report",
        "category": "ERPNext Reports",
        "parameters": [
            _p("report_name", required=True, description="Exact report name (case-sensitive). Use erpnext_list_reports to find valid names."),
            _p("filters", description="JSON object of filter key-value pairs. E.g. {\"company\": \"My Company\", \"from_date\": \"2024-01-01\", \"to_date\": \"2024-12-31\"}"),
        ],
    },
    {
        "tool_name": "erpnext_list_reports",
        "description": "List available ERPNext reports by module. Use this to discover report names before calling erpnext_run_report. Available modules: Accounts, Selling, Buying, Stock, Manufacturing, CRM, Helpdesk, Projects, HR.",
        "function_path": "huf.ai.tools.erpnext_reports.handle_list_reports",
        "category": "ERPNext Reports",
        "parameters": [
            _p("module", description="Module to filter by: Accounts, Selling, Buying, Stock, Manufacturing, CRM, Helpdesk, Projects, HR. Leave empty to list all."),
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

GOOGLE_PLACES_TOOLS = [
	{
		"tool_name": "gplaces_text_search",
		"description": (
			"Search for places with a free-text query using the Google Places API (New). "
			"Supports filters (type, rating, price, open now), location bias/restriction, and pagination. "
			"Requires a Google Maps/Places API key in Integration Settings or env (GOOGLE_MAPS_API_KEY, PLACE_API_KEY, GOOGLE_PLACES_API_KEY)."
		),
		"function_path": "huf.ai.tools.google_places.handle_gplaces_text_search",
		"category": "Google Places",
		"parameters": [
			_p("query", required=True, description="Free-text search query, e.g. 'vegan restaurants in Lisbon'"),
			_p("language_code", description="Response language, e.g. 'en', 'fr'"),
			_p("region_code", description="Region bias as CLDR country code, e.g. 'us', 'in'"),
			_p("included_type", description="Restrict to a single place type, e.g. 'restaurant', 'museum'"),
			_p("min_rating", type="number", description="Minimum average user rating (0.0-5.0)"),
			_p("price_levels", description="CSV of PRICE_LEVEL_FREE, PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE"),
			_p("open_now", type="boolean", description="Only return places open at query time"),
			_p("rank_preference", description="RELEVANCE (default) or DISTANCE (requires location)"),
			_p("latitude", type="number", description="Center latitude for location bias/restriction"),
			_p("longitude", type="number", description="Center longitude for location bias/restriction"),
			_p("radius", type="number", description="Search radius in metres (default 50000, min 1)"),
			_p("strict_location", type="boolean", description="With latitude/longitude: hard-restrict to the circle instead of biasing"),
			_p("page_size", type="integer", description="Results per page, 1-20 (default 10)"),
			_p("page_token", description="next_page_token from a previous response to fetch the next page"),
		],
	},
	{
		"tool_name": "gplaces_place_details",
		"description": (
			"Get full details for a single place by place_id: contact info, opening hours, "
			"photos (resource names for gplaces_place_photo), up to 5 reviews, review summary, "
			"accessibility/payment/parking options. Requires a Google Places API key."
		),
		"function_path": "huf.ai.tools.google_places.handle_gplaces_place_details",
		"category": "Google Places",
		"parameters": [
			_p("place_id", required=True, description="Google place ID, e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4'"),
			_p("language_code", description="Response language, e.g. 'en', 'fr'"),
			_p("region_code", description="Region code as CLDR country code, e.g. 'us'"),
		],
	},
	{
		"tool_name": "gplaces_place_photo",
		"description": (
			"Resolve a photo resource name (from gplaces_place_details photos[].name) to a usable image URL. "
			"Requires a Google Places API key."
		),
		"function_path": "huf.ai.tools.google_places.handle_gplaces_place_photo",
		"category": "Google Places",
		"parameters": [
			_p("photo_name", required=True, description="Photo resource name, e.g. 'places/PLACE_ID/photos/PHOTO_ID'"),
			_p("max_height_px", type="integer", description="Max image height in pixels (default 800)"),
			_p("max_width_px", type="integer", description="Max image width in pixels (default 800)"),
			_p("skip_http_redirect", type="boolean", description="Default true: return JSON photoUri. False: follow the media redirect manually"),
		],
	},
	{
		"tool_name": "gplaces_autocomplete",
		"description": (
			"Place autocomplete suggestions for a partial input (cities, districts, neighborhoods by default; "
			"country-level results are filtered out). Results are cached for 24h. "
			"Supports location bias/restriction and origin-based distance sorting. Requires a Google Places API key."
		),
		"function_path": "huf.ai.tools.google_places.handle_gplaces_autocomplete",
		"category": "Google Places",
		"parameters": [
			_p("input", required=True, description="Partial place name typed by the user (max 200 chars)"),
			_p("included_primary_types", description="CSV of primary types (default: locality,sublocality,administrative_area_level_1,administrative_area_level_2,neighborhood)"),
			_p("language_code", description="Response language, e.g. 'en', 'fr'"),
			_p("region_code", description="Region bias as CLDR country code, e.g. 'us'"),
			_p("session_token", description="Session token for billing/session grouping"),
			_p("include_query_predictions", type="boolean", description="Also return query (non-place) predictions"),
			_p("latitude", type="number", description="Center latitude for location bias/restriction"),
			_p("longitude", type="number", description="Center longitude for location bias/restriction"),
			_p("radius", type="number", description="Radius in metres (default 50000, min 1)"),
			_p("strict_location", type="boolean", description="With latitude/longitude: hard-restrict to the circle instead of biasing"),
			_p("origin_latitude", type="number", description="Origin latitude; adds straight-line distance_meters to suggestions"),
			_p("origin_longitude", type="number", description="Origin longitude; adds straight-line distance_meters to suggestions"),
		],
	},
	{
		"tool_name": "gplaces_nearby_search",
		"description": (
			"Search for places near a latitude/longitude using the Google Places API (New). "
			"Filter by included/excluded types and rank by popularity or distance. Requires a Google Places API key."
		),
		"function_path": "huf.ai.tools.google_places.handle_gplaces_nearby_search",
		"category": "Google Places",
		"parameters": [
			_p("latitude", type="number", required=True, description="Center latitude"),
			_p("longitude", type="number", required=True, description="Center longitude"),
			_p("radius", type="number", description="Search radius in metres (default 50000, min 1)"),
			_p("included_types", description="CSV of place types to include, e.g. 'restaurant,cafe'"),
			_p("excluded_types", description="CSV of place types to exclude"),
			_p("included_primary_types", description="CSV of primary types to include"),
			_p("excluded_primary_types", description="CSV of primary types to exclude"),
			_p("max_result_count", type="integer", description="Max results, 1-20 (default 10)"),
			_p("language_code", description="Response language, e.g. 'en', 'fr'"),
			_p("region_code", description="Region code as CLDR country code, e.g. 'us'"),
			_p("rank_preference", description="POPULARITY (default) or DISTANCE"),
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


GOOGLE_MEET_TOOLS = [
	{
		"tool_name": "google_meet_create_space",
		"description": "Create a Google Meet meeting space and return a joinable link. Requires Google OAuth credentials with Meet scope.",
		"function_path": "huf.ai.tools.google_meet.handle_create_meet_space",
		"category": "Google Tools",
		"parameters": [
			_p("access_type", description="Access level: OPEN, TRUSTED, or RESTRICTED (default: OPEN)"),
		],
	},
	{
		"tool_name": "google_meet_create_event",
		"description": "Create a Google Calendar event with an auto-generated Google Meet conference. Requires Google OAuth credentials with Calendar scope.",
		"function_path": "huf.ai.tools.google_meet.handle_create_meet_event",
		"category": "Google Tools",
		"parameters": [
			_p("title", required=True, description="Meeting title"),
			_p("start_date", required=True, description="Start datetime (ISO 8601)"),
			_p("end_date", required=True, description="End datetime (ISO 8601)"),
			_p("description", description="Event description"),
			_p("timezone", description="Timezone (default: UTC)"),
		],
	},
]


SSH_TOOLS = [
	{
		"tool_name": "run_ssh_command",
		"description": (
			"Run one remote SSH command against an admin-managed SSH Connection that the agent "
			"is explicitly allowlisted to use. Supports only non-interactive one-shot command "
			"execution in this version; interactive PTY sessions and managed background jobs are "
			"not available."
		),
		"function_path": "huf.ai.tools.ssh_execution.run_ssh_command",
		"category": "Developer Tools",
		"parameters": [
			_p("connection", required=True, description="Allowlisted SSH Connection name"),
			_p("command", required=True, description="One remote shell command to execute without PTY"),
			_p("timeout_seconds", type="integer", description="Optional execution timeout override in seconds"),
		],
	},
]


# ---------------------------------------------------------------------------
# SERP Tools (SerpApi) — hotels, reviews, YouTube
# ---------------------------------------------------------------------------

SERP_HOTEL_TOOLS = [
	{
		"tool_name": "serp_hotel_search",
		"description": (
			"Search hotels (or vacation rentals) via SerpApi Google Hotels with the full filter set: "
			"guests, price budget, rating, star class, property types, amenities, brands, and boolean toggles. "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings. "
			"Use property_token from each result with serp_hotel_details for full details."
		),
		"function_path": "huf.ai.tools.serp_hotels.handle_serp_hotel_search",
		"category": "SERP",
		"parameters": [
			_p("q", required=True, description="Search query, e.g. 'Hotels in Bandra Mumbai'"),
			_p("check_in_date", required=True, description="Check-in date (YYYY-MM-DD)"),
			_p("check_out_date", required=True, description="Check-out date (YYYY-MM-DD)"),
			_p("adults", type="integer", description="Number of adult guests (default 2, min 1)"),
			_p("children", type="integer", description="Number of children"),
			_p("children_ages", description="Ages of children, comma-separated, e.g. '5,8'"),
			_p("currency", description="ISO currency code for prices (default INR)"),
			_p("gl", description="Country code for the search, e.g. 'in', 'us' (default in)"),
			_p("hl", description="Language code, e.g. 'en' (default en)"),
			_p("sort_by", type="integer", description="Sort order: 3 (lowest price), 8 (highest rating), 13 (most reviewed). Omit for relevance."),
			_p("min_price", type="integer", description="Minimum price per night"),
			_p("max_price", type="integer", description="Maximum price per night"),
			_p("rating", type="integer", description="Minimum guest rating bucket: 7 (3.5+), 8 (4.0+), 9 (4.5+)"),
			_p("hotel_class", description="Star rating(s) 2-5, comma-separated, e.g. '4,5'"),
			_p("property_types", description="SerpApi property-type ID(s), comma-separated"),
			_p("amenities", description="SerpApi amenity ID(s), comma-separated"),
			_p("brands", description="SerpApi hotel-brand ID(s), comma-separated (ignored when vacation_rentals is true)"),
			_p("free_cancellation", type="boolean", description="Only results offering free cancellation"),
			_p("special_offers", type="boolean", description="Only results with special offers"),
			_p("eco_certified", type="boolean", description="Only eco-certified results"),
			_p("vacation_rentals", type="boolean", description="Search vacation rentals instead of hotels"),
			_p("bedrooms", type="integer", description="Minimum bedrooms (vacation rentals only)"),
			_p("bathrooms", type="integer", description="Minimum bathrooms (vacation rentals only)"),
			_p("next_page_token", description="Pagination token from a previous response"),
		],
	},
	{
		"tool_name": "serp_hotel_details",
		"description": (
			"Fetch full details for one hotel by property_token (from serp_hotel_search): per-OTA prices "
			"for the stay, rating and review sentiment breakdown, amenities, images, location. "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_hotels.handle_serp_hotel_details",
		"category": "SERP",
		"parameters": [
			_p("property_token", required=True, description="Hotel token from a serp_hotel_search result"),
			_p("check_in_date", required=True, description="Check-in date (YYYY-MM-DD); prices are quoted for this stay"),
			_p("check_out_date", required=True, description="Check-out date (YYYY-MM-DD)"),
			_p("q", description="Search query the token came from (improves accuracy; default 'Hotels')"),
			_p("adults", type="integer", description="Number of adult guests (default 2)"),
			_p("currency", description="ISO currency code for all prices (default INR)"),
			_p("gl", description="Country code (default in)"),
			_p("hl", description="Language code (default en)"),
		],
	},
	{
		"tool_name": "serp_hotel_details_batch",
		"description": (
			"Fetch details for several hotels in one call, concurrently. Pass the property_tokens returned "
			"by serp_hotel_search. Returns {hotels, errors, requested, succeeded}. "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_hotels.handle_serp_hotel_details_batch",
		"category": "SERP",
		"parameters": [
			_p("property_tokens", required=True, description="Hotel tokens: JSON array, comma-separated string, or list"),
			_p("check_in_date", required=True, description="Check-in date (YYYY-MM-DD)"),
			_p("check_out_date", required=True, description="Check-out date (YYYY-MM-DD)"),
			_p("q", description="Search query the tokens came from (improves accuracy)"),
			_p("adults", type="integer", description="Number of adult guests (default 2)"),
			_p("currency", description="ISO currency code for all prices (default INR)"),
			_p("max_workers", type="integer", description="Thread pool size for parallel lookups (default 8)"),
		],
	},
]

SERP_REVIEW_TOOLS = [
	{
		"tool_name": "serp_google_maps_reviews",
		"description": (
			"Fetch reviews for a place on Google Maps. Pass a human-friendly place_query (e.g. 'Leopold Cafe "
			"Mumbai') and the data_id is resolved internally, or pass data_id/place_id directly to skip search. "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_google_maps_reviews",
		"category": "SERP",
		"parameters": [
			_p("place_query", description="Place search query, e.g. 'Leopold Cafe Mumbai' (alternative to data_id/place_id)"),
			_p("data_id", description="The place's data id, e.g. '0x...:0x...' (preferred if known)"),
			_p("place_id", description="The place id (alternative to data_id)"),
			_p("sort_by", description="Sort order: qualityScore (default), newestFirst, ratingHigh, ratingLow"),
			_p("hl", description="Language code (default en)"),
			_p("gl", description="Country code (default in)"),
			_p("next_page_token", description="Pagination token from a previous response"),
		],
	},
	{
		"tool_name": "serp_google_hotel_reviews",
		"description": (
			"Fetch review data for a hotel: overall rating, star distribution, and per-topic sentiment "
			"breakdown. Pass hotel_query plus stay dates (property_token resolved internally) or a "
			"property_token directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_google_hotel_reviews",
		"category": "SERP",
		"parameters": [
			_p("hotel_query", description="Hotel search query, e.g. 'Taj Mahal Palace Mumbai' (alternative to property_token)"),
			_p("property_token", description="Hotel token from a serp_hotel_search result (skips search)"),
			_p("check_in_date", required=True, description="Check-in date (YYYY-MM-DD)"),
			_p("check_out_date", required=True, description="Check-out date (YYYY-MM-DD)"),
			_p("q", description="Search query the token came from (improves accuracy)"),
			_p("adults", type="integer", description="Number of adult guests (default 2)"),
			_p("currency", description="ISO currency code (default INR)"),
		],
	},
	{
		"tool_name": "serp_tripadvisor_search",
		"description": (
			"Search TripAdvisor to find a place and its place_id (for serp_tripadvisor_reviews). "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_tripadvisor_search",
		"category": "SERP",
		"parameters": [
			_p("q", required=True, description="Search terms, e.g. 'Taj Mahal Palace Mumbai'"),
			_p("ssrc", description="Category filter: a (all), r (restaurants), A (things to do), h (hotels), g (destinations), v (rentals), f (forums)"),
			_p("tripadvisor_domain", description="TripAdvisor domain, e.g. 'www.tripadvisor.in' (default .com)"),
			_p("offset", type="integer", description="Pagination offset (increments of 30)"),
			_p("limit", type="integer", description="Max results (default 30)"),
		],
	},
	{
		"tool_name": "serp_tripadvisor_reviews",
		"description": (
			"Fetch reviews for a TripAdvisor place. Pass a human-friendly place_query (place_id resolved "
			"internally) or a place_id directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_tripadvisor_reviews",
		"category": "SERP",
		"parameters": [
			_p("place_query", description="Place search query (alternative to place_id)"),
			_p("place_id", description="TripAdvisor place id from serp_tripadvisor_search (skips search)"),
			_p("sort_by", description="Sort order: most_recent (default) or detailed_review"),
			_p("rating", description="Filter by rating(s), comma-separated, e.g. '5' or '5,4'"),
			_p("language", description="Language for reviews, e.g. 'en'"),
			_p("tripadvisor_domain", description="TripAdvisor domain, e.g. 'www.tripadvisor.in'"),
			_p("translate", type="boolean", description="Translate reviews to the selected language"),
			_p("offset", type="integer", description="Reviews to skip (default 0)"),
			_p("limit", type="integer", description="Max reviews per request (1-20, default 10)"),
		],
	},
	{
		"tool_name": "serp_yelp_search",
		"description": (
			"Find Yelp businesses and their place_id (for serp_yelp_reviews). "
			"Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_yelp_search",
		"category": "SERP",
		"parameters": [
			_p("find_desc", required=True, description="What to search for, e.g. 'pizza' or a business name"),
			_p("find_loc", required=True, description="Location, e.g. 'New York, NY'"),
			_p("hl", description="Language code (default en)"),
			_p("start", type="integer", description="Result offset for pagination (0, 10, 20, ...)"),
		],
	},
	{
		"tool_name": "serp_yelp_reviews",
		"description": (
			"Fetch reviews for a Yelp business. Pass business_name + location (place_id resolved internally) "
			"or a place_id directly. Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_reviews.handle_serp_yelp_reviews",
		"category": "SERP",
		"parameters": [
			_p("business_name", description="Business name, e.g. \"Joe's Pizza\" (with location, alternative to place_id)"),
			_p("location", description="Business location, e.g. 'New York, NY' (with business_name)"),
			_p("place_id", description="Yelp place id from serp_yelp_search (skips search)"),
			_p("sort_by", description="Sort order: relevance_desc (default), date_desc, date_asc, rating_desc, rating_asc, elites_desc"),
			_p("start", type="integer", description="Result offset for pagination"),
			_p("num", type="integer", description="Number of reviews to return"),
			_p("hl", description="Language code (default en)"),
		],
	},
]

SERP_YOUTUBE_TOOLS = [
	{
		"tool_name": "serp_youtube_search",
		"description": (
			"Search YouTube videos via SerpApi. Returns videos with parsed video_id (usable with "
			"youtube_transcript). Requires SERPAPI_API_KEY env var or serpapi Integration Settings."
		),
		"function_path": "huf.ai.tools.serp_youtube.handle_serp_youtube_search",
		"category": "SERP",
		"parameters": [
			_p("search_query", required=True, description="YouTube search terms"),
			_p("gl", description="Country code (default in)"),
			_p("hl", description="Language code (default en)"),
			_p("sp", description="SerpApi filter/sort token (advanced)"),
		],
	},
	{
		"tool_name": "youtube_transcript",
		"description": (
			"Fetch the transcript/captions for a YouTube video (no SerpApi key required). Accepts a video id "
			"or any YouTube URL (watch, youtu.be, shorts, embed)."
		),
		"function_path": "huf.ai.tools.serp_youtube.handle_youtube_transcript",
		"category": "SERP",
		"parameters": [
			_p("video", required=True, description="YouTube video id or URL (watch, youtu.be, shorts, embed)"),
			_p("languages", description="Preferred language(s), comma-separated, e.g. 'en,hi' (default en); first available match is returned"),
		],
	},
]


# ---------------------------------------------------------------------------
# Builder Tools  (hub-as-builder: typed, capability-gated, diff-before-mutate)
# ---------------------------------------------------------------------------

_CONFIRM_NOTE = (
	"Two-phase contract: call with confirm=false first to preview a diff of the "
	"proposed changes; nothing is mutated until you call again with confirm=true."
)

BUILDER_TOOLS = [
	{
		"tool_name": "create_huf_table",
		"description": (
			"Create a new huf data table (a custom DocType plus registry entry) that agents "
			"and flows can then read/write. 'fields' is a JSON list of field definitions, e.g. "
			"[{\"fieldname\": \"title\", \"fieldtype\": \"Data\", \"label\": \"Title\", \"reqd\": 1}]. "
			+ _CONFIRM_NOTE
			+ " Returns the new DocType name and its live schema. Fails with a clear error if a "
			"table with the same name already exists."
		),
		"function_path": "huf.ai.tools.builder.create_huf_table",
		"category": "Builder",
		"parameters": [
			_p("table_name", required=True, description="Human table name, e.g. 'Customer Feedback'. The DocType becomes 'HF <table_name>'."),
			_p("fields", required=True, description="JSON list of field definitions [{fieldname, fieldtype, label, reqd, options, ...}]"),
			_p("description", description="What the table is for"),
			_p("icon", description="Optional icon name for the table"),
			_p("autoname_method", description="Naming method (default 'Autoincrement')"),
			_p("title_field", description="Field to use as document title"),
			_p("confirm", type="boolean", description="false = preview diff only; true = create the table"),
		],
	},
	{
		"tool_name": "list_table_rows",
		"description": (
			"Read rows from an existing huf data table (created with create_huf_table). "
			"Read-only. Returns the rows plus the total count for pagination."
		),
		"function_path": "huf.ai.tools.builder.list_table_rows",
		"category": "Builder",
		"parameters": [
			_p("table_name", required=True, description="Human table name or Huf Data Table registry name"),
			_p("filters", description="JSON filter object or list, e.g. {\"status\": \"Open\"}"),
			_p("fields", description="JSON list of fieldnames to return (default: all)"),
			_p("limit", type="integer", description="Max rows (default 20)"),
			_p("start", type="integer", description="Offset for pagination (default 0)"),
		],
	},
	{
		"tool_name": "add_table_row",
		"description": (
			"Add a row to an existing huf data table. 'data' is a JSON object of "
			"fieldname/value pairs matching the table's schema (unknown fields are dropped). "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.add_table_row",
		"category": "Builder",
		"parameters": [
			_p("table_name", required=True, description="Human table name or Huf Data Table registry name"),
			_p("data", required=True, description="JSON object of fieldname/value pairs, e.g. {\"title\": \"Hello\", \"status\": \"Open\"}"),
			_p("confirm", type="boolean", description="false = preview diff only; true = insert the row"),
		],
	},
	{
		"tool_name": "update_table_row",
		"description": (
			"Update fields of an existing row in a huf data table. 'data' is a JSON object "
			"of fieldname/value pairs; only changed fields are applied. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.update_table_row",
		"category": "Builder",
		"parameters": [
			_p("table_name", required=True, description="Human table name or Huf Data Table registry name"),
			_p("row_name", required=True, description="Name (ID) of the row to update"),
			_p("data", required=True, description="JSON object of fieldname/value pairs to change"),
			_p("confirm", type="boolean", description="false = preview diff only; true = apply and save"),
		],
	},
	{
		"tool_name": "delete_table_row",
		"description": (
			"Delete a row from a huf data table. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.delete_table_row",
		"category": "Builder",
		"parameters": [
			_p("table_name", required=True, description="Human table name or Huf Data Table registry name"),
			_p("row_name", required=True, description="Name (ID) of the row to delete"),
			_p("confirm", type="boolean", description="false = preview diff only; true = delete the row"),
		],
	},
	{
		"tool_name": "draft_agent",
		"description": (
			"Create a new AI Agent in DRAFT state (disabled=1 - it cannot run yet) with a "
			"local prompt from 'instructions'. The provider must already exist; if it has no "
			"API key configured the draft is still created but the result includes a warning. "
			"The agent is chat-enabled by default (allow_chat=true) so it appears in chat "
			"pickers once published. "
			+ _CONFIRM_NOTE
			+ " Use update_agent_prompt to refine the prompt, attach_agent_tools to give it tools, "
			"and publish_agent to enable it. Fails with a clear error if the agent already exists."
		),
		"function_path": "huf.ai.tools.builder.draft_agent",
		"category": "Builder",
		"parameters": [
			_p("agent_name", required=True, description="Unique agent name (also the document ID)"),
			_p("provider", required=True, description="Existing AI Provider name"),
			_p("model", required=True, description="Existing AI Model name"),
			_p("instructions", required=True, description="System prompt / instructions for the agent"),
			_p("description", description="Short human description of the agent"),
			_p("allow_chat", type="boolean", description="true (default) = chat-enabled so it appears in chat UIs; false = headless/automation-only agent"),
			_p("confirm", type="boolean", description="false = preview diff only; true = create the draft agent"),
		],
	},
	{
		"tool_name": "update_agent_prompt",
		"description": (
			"Update an agent's prompt - either its local instructions or its linked Agent Prompt "
			"template (setting agent_prompt switches the agent to Template prompt mode). "
			+ _CONFIRM_NOTE
			+ " System agents (is_system) can only be modified by System Managers."
		),
		"function_path": "huf.ai.tools.builder.update_agent_prompt",
		"category": "Builder",
		"parameters": [
			_p("agent_name", required=True, description="Name of the agent to update"),
			_p("instructions", description="New local instructions text"),
			_p("agent_prompt", description="Name of an existing Agent Prompt template to link"),
			_p("confirm", type="boolean", description="false = preview diff only; true = apply and save"),
		],
	},
	{
		"tool_name": "attach_agent_tools",
		"description": (
			"Set the full list of tools attached to an agent. 'tool_names' is the complete "
			"proposed set of Agent Tool Function names (it replaces the current list - include "
			"existing tools you want to keep). Every tool must already exist. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.attach_agent_tools",
		"category": "Builder",
		"parameters": [
			_p("agent_name", required=True, description="Name of the agent"),
			_p("tool_names", required=True, description="JSON list of Agent Tool Function names, e.g. [\"get_list\", \"run_flow\"]"),
			_p("confirm", type="boolean", description="false = preview diff only; true = apply and save"),
		],
	},
	{
		"tool_name": "publish_agent",
		"description": (
			"Publish a draft agent (flip disabled from 1 to 0) so it can run. Refuses with a "
			"remediation message if the agent's provider has no API key configured. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.publish_agent",
		"category": "Builder",
		"parameters": [
			_p("agent_name", required=True, description="Name of the draft agent to publish"),
			_p("confirm", type="boolean", description="false = preview diff only; true = apply and save"),
		],
	},
	{
		"tool_name": "create_agent_tool",
		"description": (
			"Create a WORKING declarative document tool (Agent Tool Function) bound to a "
			"DocType. The tool executes immediately — attach it to an agent with "
			"attach_agent_tools and it is callable right away. Use this to give agents "
			"data tools, e.g. an 'add_row'-style named tool for a huf data table's "
			"dynamic doctype like 'HF Social Media Campaign' (types='Create Document'). "
			"Parameters are validated against the DocType: Select fields get options "
			"auto-filled, unknown fields are dropped (see dropped_params in the result). "
			"Custom Function/code/HTTP tools CANNOT be created by this tool. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.create_agent_tool",
		"category": "Builder",
		"parameters": [
			_p("tool_name", required=True, description="Unique tool name (also the document ID)"),
			_p("description", required=True, description="What the tool does — this is what LLMs will see"),
			_p("types", required=True, description="Document tool type, one of: Create Document, Create Multiple Documents, Get Document, Get Multiple Documents, Get List, Update Document, Update Multiple Documents, Delete Document, Delete Multiple Documents, Get Value, Set Value"),
			_p("reference_doctype", required=True, description="DocType the tool operates on, e.g. 'HF Social Media Campaign' for a huf data table"),
			_p("parameters", description="JSON list of parameter definitions [{fieldname, type, label, required, description}]. fieldnames must exist on the reference_doctype (unknown ones are dropped); Select fields get options auto-filled. type one of: string, integer, number, float, boolean, object, array"),
			_p("confirm", type="boolean", description="false = preview diff only; true = create the tool record"),
		],
	},
	{
		"tool_name": "list_provider_options",
		"description": (
			"List every AI Provider with whether it has an API key configured and which "
			"AI Models exist for it, plus a 'suggested' provider+model pair (the first "
			"configured provider and its default chat model). Read-only — call this before "
			"draft_agent to pick a valid provider/model instead of guessing. API key values "
			"are never returned, only a configured true/false flag."
		),
		"function_path": "huf.ai.tools.builder.list_provider_options",
		"category": "Builder",
		"parameters": [],
	},
	{
		"tool_name": "list_agents",
		"description": (
			"List Agents the caller can see (read-only). Returns agent_name, description, "
			"disabled, and is_system for up to 'limit' agents. Use this to discover an "
			"existing agent before turning it into an App with draft_app."
		),
		"function_path": "huf.ai.tools.builder.list_agents",
		"category": "Builder",
		"parameters": [
			_p("limit", type="integer", description="Max number of agents to return (default 20)"),
		],
	},
	{
		"tool_name": "get_agent",
		"description": (
			"Get a single Agent's summary (read-only) — agent_name, description, provider, "
			"model, disabled, is_system, allow_chat. Does NOT return instructions or any "
			"secrets, only enough to decide whether the agent is a suitable App backend."
		),
		"function_path": "huf.ai.tools.builder.get_agent",
		"category": "Builder",
		"parameters": [
			_p("agent_name", required=True, description="Name of the agent to inspect"),
		],
	},
	{
		"tool_name": "list_apps",
		"description": (
			"List HUF App registry records the caller can see (read-only). Returns app_id, "
			"title, description, route, category, enabled for up to 'limit' apps."
		),
		"function_path": "huf.ai.tools.builder.list_apps",
		"category": "Builder",
		"parameters": [
			_p("limit", type="integer", description="Max number of apps to return (default 20)"),
		],
	},
	{
		"tool_name": "get_app",
		"description": (
			"Get a single HUF App record's summary (read-only) — app_id, title, description, "
			"route, icon, category, agent, enabled."
		),
		"function_path": "huf.ai.tools.builder.get_app",
		"category": "Builder",
		"parameters": [
			_p("app_id", required=True, description="ID of the App to inspect"),
		],
	},
	{
		"tool_name": "draft_app",
		"description": (
			"Create a new HUF App backed by an existing Agent (linked, not cloned). The "
			"agent must already exist and be readable by the caller. "
			+ _CONFIRM_NOTE
			+ " Use list_agents/get_agent first to pick agent_name. Fails with a clear "
			"error if app_id already exists or agent_name does not."
		),
		"function_path": "huf.ai.tools.builder.draft_app",
		"category": "Builder",
		"parameters": [
			_p("app_id", required=True, description="Unique App ID (also the document ID)"),
			_p("title", required=True, description="Display title for the App"),
			_p("agent_name", required=True, description="Existing Agent to back this App"),
			_p("description", description="Short human description of the App"),
			_p("route", description="Frontend route; defaults to /apps/<app_id>"),
			_p("category", description="Launcher category, e.g. Create, Plan, Automate (default Other)"),
			_p("confirm", type="boolean", description="false = preview diff only; true = create the App"),
		],
	},
	{
		"tool_name": "update_app",
		"description": (
			"Apply a partial update to an existing HUF App's fields (e.g. title, "
			"description, icon, category, agent). Only the fields passed are changed. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.update_app",
		"category": "Builder",
		"parameters": [
			_p("app_id", required=True, description="ID of the App to update"),
			_p("title", description="New display title"),
			_p("description", description="New description"),
			_p("icon", description="New icon"),
			_p("category", description="New launcher category"),
			_p("agent", description="Existing Agent name to re-link this App to"),
			_p("confirm", type="boolean", description="false = preview diff only; true = apply and save"),
		],
	},
	{
		"tool_name": "install_app",
		"description": (
			"Install (enable) an existing HUF App. Idempotent — re-running with the same "
			"app_id never duplicates the record; an already-enabled app is reported as "
			"already_installed. "
			+ _CONFIRM_NOTE
		),
		"function_path": "huf.ai.tools.builder.install_app",
		"category": "Builder",
		"parameters": [
			_p("app_id", required=True, description="ID of the App to install"),
			_p("confirm", type="boolean", description="false = preview only; true = install the App"),
		],
	},
	{
		"tool_name": "set_app_icon",
		"description": (
			"Set an app's icon from three possible sources: existing site-local asset path, "
			"an uploaded File doc, or a text prompt for AI image generation. All three branches "
			"validate their inputs (path format, File MIME type, image generation success) before "
			"applying. "
			+ _CONFIRM_NOTE
			+ " Note: SVG uploads are flagged for platform-wide sanitization gaps (documented "
			"in the plan's security review §F); SVG validation is limited to acceptance, not "
			"decontamination."
		),
		"function_path": "huf.ai.tools.builder.set_app_icon",
		"category": "Builder",
		"parameters": [
			_p("app_id", required=True, description="ID of the App to set the icon for"),
			_p("source", required=True, description="Source of the icon: 'path' (site-local asset path), 'uploaded' (File doc name), or 'generated' (image generation prompt)"),
			_p("value", required=True, description="The icon value: a path string (for 'path'), a File name (for 'uploaded'), or a prompt (for 'generated')"),
			_p("confirm", type="boolean", description="false = preview diff only; true = set the icon"),
		],
	},
	{
		"tool_name": "ask_user",
		"description": (
			"Ask the user a structured question in the chat. Returns a fenced 'ask-user' "
			"block — include the returned 'block' value VERBATIM in your reply, then STOP "
			"and wait for the user's answer. kind is one of yes_no|single_choice|multi_choice|"
			"input|textarea; the choice kinds require options as "
			"[{id, label, icon?, description?}] (icon must be a supported lucide name; "
			"unsupported icons are dropped with a warning). Use this ONLY when structured UI "
			"is clearly better than a typed reply: confirming right before executing a "
			"mutating plan, choosing from a defined set of options, or collecting a "
			"required value. Do NOT use it for greetings, small talk, open-ended "
			"questions, or normal conversation — answer those in plain prose."
		),
		"function_path": "huf.ai.tools.ask_user.ask_user",
		"category": "Builder",
		"parameters": [
			_p("question", required=True, description="The question to show the user"),
			_p("kind", required=True, description="One of: yes_no, single_choice, multi_choice, input, textarea"),
			_p("options", description="JSON list of options [{id, label, icon?, description?}] — required for single_choice/multi_choice"),
			_p("allow_free_text", type="boolean", description="Allow a free-text answer in addition to options (default true)"),
			_p("suggested_answers", description="JSON list of suggested free-text answers"),
			_p("note", description="Optional extra context shown with the question"),
		],
	},
	{
		"tool_name": "resolve_recent_resource",
		"description": (
			"Resolve a vague reference like 'that agent' or 'the app I just made' to a "
			"concrete document name. Looks at what draft_agent/draft_app have created "
			"(with confirm=true) earlier in THIS conversation and returns the most recent "
			"match for resource_type. Read-only; found=false means nothing of that type "
			"has been created yet in this conversation — ask the user for the name instead "
			"of guessing."
		),
		"function_path": "huf.ai.tools.builder.resolve_recent_resource",
		"category": "Builder",
		"parameters": [
			_p("resource_type", required=True, description="Which kind of recently-created resource to resolve: 'agent' or 'app'"),
		],
	},
]


DOCKER_TOOLS = [
	{
		"tool_name": "docker_execution",
		"description": "Manage Docker containers, images, and Compose deployments with bounded, explicit operations. Compose actions operate on an existing compose file; destructive actions require confirm_destructive=true. Supports local socket, Docker contexts, TLS endpoints, or a Frappe SSH Connection.",
		"function_path": "huf.ai.tools.docker_execution.handle_action",
		"category": "Developer Tools",
		"parameters": [
			_action("list_containers|list_images|inspect_container|logs|stop_container|start_container|restart_container|remove_container|pull_image|run_container|exec_container|compose_up|compose_ps|compose_logs|compose_config|compose_down"),
			_p("container", description="Container name or ID"),
			_p("image", description="Image name"),
			_p("command", description="Command to execute (for exec_container)"),
			_p("name", description="Name for new container (for run_container)"),
			_p("ports", description="Ports to publish (comma separated, e.g. '80:80')"),
			_p("environment", description="Environment variables (comma separated KEY=VALUE entries)"),
			_p("volumes", description="Bind mounts (comma separated host:container[:mode] entries)"),
			_p("network", description="Docker network for a new container"),
			_p("workdir", description="Working directory for run or exec"),
			_p("user", description="User for a new container"),
			_p("memory", description="Memory limit for a new container, e.g. 512m"),
			_p("cpus", type="number", description="CPU limit for a new container"),
			_p("auto_remove", type="boolean", description="Remove the container when it exits"),
			_p("confirm_destructive", type="boolean", description="Required confirmation for stop, restart, or remove"),
			_p("timeout_seconds", type="integer", description="Maximum operation time, capped at 300 seconds"),
			_p("compose_file", description="Path to an existing Docker Compose file"),
			_p("project_dir", description="Compose project directory"),
			_p("project_name", description="Compose project name"),
			_p("services", description="Comma-separated Compose service names"),
			_p("detach", type="boolean", description="Run Compose services in the background (default true)"),
			_p("build", type="boolean", description="Build images before Compose up"),
			_p("wait", type="boolean", description="Wait for services to become healthy"),
			_p("remove_orphans", type="boolean", description="Remove Compose containers not in the file"),
			_p("remove_volumes", type="boolean", description="Remove named volumes during compose_down"),
			_p("tail", type="integer", description="Number of log lines to tail"),
			_p("connection_string", description="Docker daemon URL (unix://, ssh://, tcp://)"),
			_p("context_name", description="Docker context name"),
			_p("ssh_connection", description="Frappe SSH Connection doctype name to use for remote docker execution"),
			_p("tls_verify", type="boolean", description="Enable TLS verification for TCP connections"),
			_p("tls_ca_cert", description="Path to the CA certificate for a TLS Docker daemon"),
			_p("tls_cert", description="Path to the client certificate for a TLS Docker daemon"),
			_p("tls_key", description="Path to the client key for a TLS Docker daemon"),
		],
	},
]


# ---------------------------------------------------------------------------
# Master list
# ---------------------------------------------------------------------------

FRAPPE_CLOUD_TOOLS = [
	{
		"tool_name": "fc_list_benches",
		"description": "List Frappe Cloud benches with optional filters.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_benches",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("filters", description="Optional filters dict"),
		],
	},
	{
		"tool_name": "fc_get_bench",
		"description": "Get details of a Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_get_bench",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
		],
	},
	{
		"tool_name": "fc_create_bench",
		"description": "Create a new Frappe Cloud bench/release group. Optionally pin it to a dedicated server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_create_bench",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("title", required=True, description="Bench title"),
			_p("version", description="Frappe version (e.g. Version 16)"),
			_p("cluster", description="Cluster name (e.g. UAE)"),
			_p("apps", description="List of apps to add"),
			_p("server", description="Optional dedicated server name to host the bench on"),
			_p("saas_app", description="Optional SaaS app name"),
		],
	},
	{
		"tool_name": "fc_bench_options",
		"description": "Get available versions, clusters and apps for creating a new Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_bench_options",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [],
	},
	{
		"tool_name": "fc_archive_bench",
		"description": "Archive/delete a Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_archive_bench",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
		],
	},
	{
		"tool_name": "fc_add_app_to_bench",
		"description": "Add an app to a Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_add_app_to_bench",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
			_p("app", required=True, description="App name"),
			_p("source", required=True, description="App source identifier"),
		],
	},
	{
		"tool_name": "fc_list_sites",
		"description": "List Frappe Cloud sites with optional filters.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_sites",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("filters", description="Optional filters dict"),
		],
	},
	{
		"tool_name": "fc_site_options",
		"description": "Get available options for creating a new Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_site_options",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", description="Bench/release group name"),
		],
	},
	{
		"tool_name": "fc_site_plans",
		"description": "List available plans for a Frappe Cloud bench/release group.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_site_plans",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", description="Bench/release group name"),
		],
	},
	{
		"tool_name": "fc_create_site",
		"description": "Create a new Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_create_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("apps", description="List of apps to install"),
			_p("version", description="Frappe version"),
			_p("domain", description="Domain suffix"),
			_p("plan", description="Plan name"),
			_p("bench", description="Bench/release group name"),
			_p("provider", description="Infrastructure provider"),
			_p("cluster", description="Cluster name"),
		],
	},
	{
		"tool_name": "fc_drop_site",
		"description": "Archive/delete a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_drop_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("force", description="Force archive even if active"),
		],
	},
	{
		"tool_name": "fc_backup_site",
		"description": "Trigger a backup of a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_backup_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("with_files", description="Include files in backup"),
		],
	},
	{
		"tool_name": "fc_download_backup",
		"description": "List downloadable backups for a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_download_backup",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
		],
	},
	{
		"tool_name": "fc_migrate_site",
		"description": "Run migrate on a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_migrate_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("skip_failing_patches", description="Skip failing patches"),
		],
	},
	{
		"tool_name": "fc_clear_cache",
		"description": "Clear cache of a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_clear_cache",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
		],
	},
	{
		"tool_name": "fc_update_site",
		"description": "Update a Frappe Cloud site (pull latest app versions).",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_update_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("skip_backups", description="Skip backups before update"),
		],
	},
	{
		"tool_name": "fc_clone_site",
		"description": "Clone a Frappe Cloud site into another bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_clone_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("source_site", required=True, description="Source site name"),
			_p("bench", required=True, description="Target bench name"),
		],
	},
	{
		"tool_name": "fc_add_app_to_site",
		"description": "Install an app on a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_add_app_to_site",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
			_p("app", required=True, description="App name"),
			_p("plan", description="Marketplace plan name"),
		],
	},
	{
		"tool_name": "fc_get_admin_login_link",
		"description": "Get an admin login link/session for a Frappe Cloud site.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_get_admin_login_link",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("site_name", required=True, description="Site name"),
		],
	},
	{
		"tool_name": "fc_list_webhooks",
		"description": "List registered Frappe Cloud press webhooks.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_webhooks",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("endpoint", description="Filter by endpoint URL"),
			_p("limit", description="Max results"),
		],
	},
	{
		"tool_name": "fc_available_webhook_events",
		"description": "List available Frappe Cloud webhook event types.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_available_webhook_events",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [],
	},
	{
		"tool_name": "fc_add_webhook",
		"description": "Register a new Frappe Cloud press webhook.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_add_webhook",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("endpoint", required=True, description="Webhook endpoint URL"),
			_p("secret", required=True, description="Secret token"),
			_p("events", required=True, description="List of event names"),
		],
	},
	{
		"tool_name": "fc_update_webhook",
		"description": "Update an existing Frappe Cloud press webhook.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_update_webhook",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("name", required=True, description="Webhook document name"),
			_p("endpoint", required=True, description="Webhook endpoint URL"),
			_p("events", required=True, description="List of event names"),
			_p("secret", description="Secret token"),
		],
	},
	{
		"tool_name": "fc_delete_webhook",
		"description": "Delete a Frappe Cloud press webhook.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_delete_webhook",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("name", required=True, description="Webhook document name"),
		],
	},
	{
		"tool_name": "fc_list_ssh_keys",
		"description": "List SSH keys stored in the Frappe Cloud account.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_ssh_keys",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [],
	},
	{
		"tool_name": "fc_add_ssh_key",
		"description": "Add an SSH public key to the Frappe Cloud account.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_add_ssh_key",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("key", required=True, description="SSH public key string"),
		],
	},
	{
		"tool_name": "fc_mark_ssh_key_default",
		"description": "Mark an SSH key as default in the Frappe Cloud account.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_mark_ssh_key_default",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("key_name", required=True, description="SSH key document name"),
		],
	},
	{
		"tool_name": "fc_get_bench_ssh_certificate",
		"description": "Get the SSH certificate for a Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_get_bench_ssh_certificate",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
		],
	},
	{
		"tool_name": "fc_generate_bench_ssh_certificate",
		"description": "Generate/regenerate the SSH certificate for a Frappe Cloud bench.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_generate_bench_ssh_certificate",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
		],
	},
	{
		"tool_name": "fc_list_servers",
		"description": "List Frappe Cloud application and database servers.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_servers",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("filters", description="Optional filters dict, e.g. {\"server_type\": \"App Servers\"}"),
		],
	},
	{
		"tool_name": "fc_get_server",
		"description": "Get details of a Frappe Cloud server (App or Database server).",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_get_server",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_get_server_overview",
		"description": "Get plan and ownership overview for a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_get_server_overview",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_server_options",
		"description": "Return regions and plans available for creating a new Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_server_options",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [],
	},
	{
		"tool_name": "fc_server_plans",
		"description": "List Frappe Cloud server plans for a given server type.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_server_plans",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server_type", description="Server type: Server or Database Server (default: Server)"),
			_p("cluster", description="Filter plans by cluster"),
			_p("platform", description="Filter by platform, e.g. x86_64 or arm64"),
		],
	},
	{
		"tool_name": "fc_create_server",
		"description": "Create a new Frappe Cloud server. Provide only app_plan for a unified server; provide db_plan as well to create separate app and database servers.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_create_server",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("title", required=True, description="Server title"),
			_p("cluster", required=True, description="Cluster name"),
			_p("app_plan", required=True, description="Application server plan name"),
			_p("db_plan", description="Database server plan name (if omitted, creates a unified server)"),
			_p("auto_increase_storage", type="boolean", description="Enable auto-increase storage"),
		],
	},
	{
		"tool_name": "fc_archive_server",
		"description": "Archive/delete a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_archive_server",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_reboot_server",
		"description": "Reboot a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_reboot_server",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_rename_server",
		"description": "Rename (change the title of) a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_rename_server",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
			_p("title", required=True, description="New server title"),
		],
	},
	{
		"tool_name": "fc_change_server_plan",
		"description": "Resize/change the plan of a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_change_server_plan",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
			_p("plan", required=True, description="New server plan name"),
		],
	},
	{
		"tool_name": "fc_server_usage",
		"description": "Get current CPU, memory and disk usage for a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_server_usage",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_list_server_benches",
		"description": "List benches (release groups) running on a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_server_benches",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
		],
	},
	{
		"tool_name": "fc_list_server_jobs",
		"description": "List Agent jobs for a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_server_jobs",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
			_p("limit_page_length", type="integer", description="Max results"),
		],
	},
	{
		"tool_name": "fc_list_server_plays",
		"description": "List Ansible plays for a Frappe Cloud server.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_server_plays",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("server", required=True, description="Server name"),
			_p("limit_page_length", type="integer", description="Max results"),
		],
	},
	{
		"tool_name": "fc_list_bench_jobs",
		"description": "List Agent jobs for a Frappe Cloud bench/release group.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_bench_jobs",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("bench", required=True, description="Bench name"),
			_p("limit_page_length", type="integer", description="Max results"),
		],
	},
	{
		"tool_name": "fc_list_marketplace_apps",
		"description": "List apps available on the Frappe Cloud Marketplace.",
		"function_path": "huf.ai.tools.frappe_cloud.handle_fc_list_marketplace_apps",
		"category": "Frappe Cloud",
		"service": "frappe_cloud",
		"parameters": [
			_p("filters", description="Optional filters dict"),
			_p("limit", type="integer", description="Max results"),
		],
	},
]

def _with_service(tools: list[dict], service: str) -> list[dict]:
	"""Stamp the owning Integration Service key onto each tool definition.

	Tools are already grouped one list per service in this file, so the
	association is declared once here instead of repeated on every entry. The
	key must match an `Integration Service` docname, because that link is what
	lets the UI tell a user which account a tool needs before they attach it.
	An entry that already names a service keeps its own value.
	"""
	return [{**tool, "service": tool.get("service") or service} for tool in tools]


DOCUMENT_ARTIFACT_TOOLS = [
	{
		"tool_name": "list_document_artifacts",
		"description": (
			"List document artifacts (created via <artifact type=\"document\">) in a conversation, "
			"returning each one's id, title, and creation time. A document artifact's id is not "
			"known to you at the moment you emit its <artifact> tag - it only exists once that "
			"message has been saved. Call this tool in a LATER turn to discover the id of a "
			"document created earlier in the conversation before calling export_artifact or "
			"redline_artifact on it."
		),
		"function_path": "huf.ai.tools.document_artifact.handle_list_document_artifacts",
		"category": "Document Tools",
		"parameters": [
			_p("conversation_id", required=True, description="The conversation to list document artifacts for"),
		],
	},
	{
		"tool_name": "export_artifact",
		"description": (
			"Export a document artifact (created via <artifact type=\"document\">) as a "
			"downloadable PDF, DOCX, or HTML file. Only artifacts of type 'document' or "
			"'markdown' can be exported - their content is treated as markdown source."
		),
		"function_path": "huf.ai.tools.document_artifact.handle_export_artifact",
		"category": "Document Tools",
		"parameters": [
			_p("artifact_id", required=True, description="The id/name of the Artifact to export"),
			_p("format", required=True, description="One of 'pdf', 'docx', 'html'"),
		],
	},
	{
		"tool_name": "show_artifact",
		"description": (
			"Open a document artifact (created via <artifact type=\"document\">) in the user's "
			"right-side preview pane, without requiring the user to click anything. Use this "
			"right after producing or updating a document the user should see immediately, or "
			"when returning to a document created earlier in the conversation. As with "
			"export_artifact and redline_artifact, this only works for artifacts that ALREADY "
			"exist - a document's id is not known until the message that created it is saved, so "
			"call list_document_artifacts first if you don't already know the id."
		),
		"function_path": "huf.ai.tools.document_artifact.handle_show_artifact",
		"category": "Document Tools",
		"parameters": [
			_p("artifact_id", required=True, description="The id/name of the Artifact to open in the preview pane"),
		],
	},
	{
		"tool_name": "redline_artifact",
		"description": (
			"Apply tracked-changes (Word redlining) edits to a document artifact, producing a "
			"new derived DOCX with insertions and deletions marked and attributed to an author - "
			"the original artifact content is not modified. Use this when the user asks for "
			"suggested edits or a marked-up revision rather than a silent rewrite."
		),
		"function_path": "huf.ai.tools.document_artifact.handle_redline_artifact",
		"category": "Document Tools",
		"parameters": [
			_p("artifact_id", required=True, description="The id/name of the Artifact to redline"),
			_p("edits", type="json", required=True, description="List of {find, replace} dicts describing the edits to mark as tracked changes"),
			_p("author", description="Attribution for the tracked changes; defaults to the current user"),
		],
	},
]

# ---------------------------------------------------------------------------
# Render Tools — structured JSON in, existing <artifact> markup out. Replace
# hand-authoring Mermaid DSL / Recharts JSX with a small structured payload.
# ---------------------------------------------------------------------------

RENDER_TOOLS = [
	{
		"tool_name": "render_mermaid",
		"description": (
			"Renders a Mermaid diagram from structured nodes/edges. Call this instead of "
			"writing Mermaid syntax yourself. Returns the complete <artifact type=\"mermaid\"> "
			"tag - relay it verbatim in your response."
		),
		"function_path": "huf.ai.tools.render_tools.handle_render_mermaid",
		"category": "Render Tools",
		"parameters": [
			_p("diagram_type", required=True, description="One of: 'graph TD', 'graph LR', 'flowchart TD', 'flowchart LR'"),
			_p("nodes", type="json", required=True, description="JSON list of nodes [{id, label}], e.g. [{\"id\": \"a\", \"label\": \"Start\"}]"),
			_p("edges", type="json", description="JSON list of edges [{from, to, label}], e.g. [{\"from\": \"a\", \"to\": \"b\", \"label\": \"next\"}]. from/to must match declared node ids"),
			_p("title", description="Artifact title (default 'Diagram')"),
		],
	},
	{
		"tool_name": "render_chart",
		"description": (
			"Renders a bar/line/pie/area chart from structured data. Call this instead of "
			"hand-writing Recharts JSX yourself. Returns the complete "
			"<artifact type=\"chart\" language=\"jsx\"> tag - relay it verbatim in your response."
		),
		"function_path": "huf.ai.tools.render_tools.handle_render_chart",
		"category": "Render Tools",
		"parameters": [
			_p("chart_type", required=True, description="One of: 'bar', 'line', 'pie', 'area'"),
			_p("data", type="json", required=True, description="JSON list of row objects, each containing at least the x_key field and every series_key field"),
			_p("series_keys", type="json", description="JSON list of field names to plot as series/values (default ['value'])"),
			_p("x_key", description="Field used for the category/x axis, ignored for 'pie' (default 'label')"),
			_p("colors", type="json", description="Optional JSON list of hex colors, mainly used for pie slices"),
			_p("title", description="Artifact title (default '<Chart Type> Chart')"),
		],
	},
	{
		"tool_name": "list_app_components",
		"description": (
			"Lists the small, explicit allowlist of design-system components (mirrored from "
			"the frontend's JSX whitelist) that render_app_component can render, each with its "
			"accepted props and a short example. Read-only, no confirm needed. Call this before "
			"render_app_component to see what's actually available - hand-authored component "
			"names/props outside this list will not render."
		),
		"function_path": "huf.ai.tools.render_tools.handle_list_app_components",
		"category": "Render Tools",
		"parameters": [],
	},
	{
		"tool_name": "render_app_component",
		"description": (
			"Renders a single design-system component (from the list_app_components allowlist) "
			"with the given props. Call this instead of hand-writing shadcn/ui JSX yourself. "
			+ _CONFIRM_NOTE
			+ " Returns the complete <artifact> tag - relay it verbatim in your response."
		),
		"function_path": "huf.ai.tools.render_tools.handle_render_app_component",
		"category": "Render Tools",
		"parameters": [
			_p("component", required=True, description="Component name, must be one returned by list_app_components"),
			_p("props", type="json", description="JSON object of prop name -> value, e.g. {\"variant\": \"secondary\"}"),
			_p("confirm", type="boolean", description="false = preview artifact only; true = return artifact to relay"),
		],
	},
]

LAZY_DISCOVERY_TOOLS = [
	{
		"tool_name": "list_tool_groups",
		"description": (
			"List the groups your available tools are organized into (by service), with a tool "
			"count and a one-line summary for each group. Use this first when you have many tools "
			"and are not sure which ones are relevant yet - then call describe_tool_group on a "
			"promising group to see its individual tools, and load_tools to actually make the ones "
			"you need callable. If you already know roughly what you're looking for, call "
			"search_tools instead and skip straight to load_tools."
		),
		"function_path": "huf.ai.tools.lazy_discovery.handle_list_tool_groups",
		"category": "Tool Discovery",
		"parameters": [],
	},
	{
		"tool_name": "search_tools",
		"description": (
			"Search for tools by keyword or description across everything you're permitted to use. "
			"Use this when you know roughly what you want to do (e.g. 'send an email', 'create an "
			"invoice') but don't know the exact tool name. Returns matching tools with their service "
			"and description - call load_tools with the tool_name(s) you want before using them."
		),
		"function_path": "huf.ai.tools.lazy_discovery.handle_search_tools",
		"category": "Tool Discovery",
		"parameters": [
			_p("query", required=True, description="Keywords describing the action or capability you're looking for"),
			_p("limit", type="integer", description="Max results to return (default 10)"),
		],
	},
	{
		"tool_name": "describe_tool_group",
		"description": (
			"List every tool in a specific service group (as returned by list_tool_groups), with "
			"each tool's full description. Use this after list_tool_groups to see the individual "
			"tools within a group you're interested in, then call load_tools with the tool_name(s) "
			"you need."
		),
		"function_path": "huf.ai.tools.lazy_discovery.handle_describe_tool_group",
		"category": "Tool Discovery",
		"parameters": [
			_p("service", required=True, description="The service/group name, as returned by list_tool_groups"),
		],
	},
	{
		"tool_name": "load_tools",
		"description": (
			"Make the named tools callable for the rest of this conversation. Call this after "
			"list_tool_groups + describe_tool_group, or after search_tools, once you know exactly "
			"which tool(s) you need. Returns each accepted tool's description and parameters so you "
			"can call it immediately, plus any requested names you're not permitted to use."
		),
		"function_path": "huf.ai.tools.lazy_discovery.handle_load_tools",
		"category": "Tool Discovery",
		"parameters": [
			_p("tool_names", type="json", required=True, description="List of tool_name strings to load"),
		],
	},
]

ALL_INTEGRATION_TOOLS = (
	# Platform capabilities — no external account to connect.
	RECIPIENT_TOOLS
	+ CRM_TOOLS
	+ HELPDESK_TOOLS
	+ RAVEN_TOOLS
	+ ERPNEXT_TOOLS
	+ ERPNEXT_CRM_TOOLS
	+ ERPNEXT_INVENTORY_TOOLS
	+ ERPNEXT_REPORT_TOOLS
	+ BUILDER_TOOLS
	+ SSH_TOOLS
	+ DOCKER_TOOLS
	+ DOCUMENT_ARTIFACT_TOOLS
	+ RENDER_TOOLS
	+ LAZY_DISCOVERY_TOOLS
	# Tools backed by a connectable service. Keys match Integration Service
	# docnames and the SERVICE_NAME each tool module uses for credentials.
	+ _with_service(SLACK_TOOLS, "slack")
	+ _with_service(TELEGRAM_TOOLS, "telegram")
	+ _with_service(GITHUB_TOOLS, "github")
	+ _with_service(GMAIL_TOOLS, "gmail")
	+ _with_service(GOOGLE_SHEETS_TOOLS, "google_sheets")
	+ _with_service(GOOGLE_CALENDAR_TOOLS, "google_calendar")
	+ _with_service(GOOGLE_MAPS_TOOLS, "google_maps")
	# Places is part of Google Maps Platform and shares its API key —
	# `google_places.py` sets SERVICE_NAME = "google_maps".
	+ _with_service(GOOGLE_PLACES_TOOLS, "google_maps")
	+ _with_service(GOOGLE_DRIVE_TOOLS, "google_drive")
	+ _with_service(GOOGLE_MEET_TOOLS, "google_meet")
	+ _with_service(SERP_HOTEL_TOOLS, "serpapi")
	+ _with_service(SERP_REVIEW_TOOLS, "serpapi")
	+ _with_service(SERP_YOUTUBE_TOOLS, "serpapi")
	+ FRAPPE_CLOUD_TOOLS  # entries already declare service="frappe_cloud"
)
