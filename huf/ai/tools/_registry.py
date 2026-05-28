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
# Communication Tools
# ---------------------------------------------------------------------------

SLACK_TOOLS = [{
    "tool_name": "slack",
    "description": "Interact with Slack workspace. Actions: send_message (channel, text), reply_thread (channel, text, thread_ts), list_channels, get_history (channel, limit), search_messages (query, limit), list_users (limit).",
    "function_path": "huf.ai.tools.slack.handle_action",
    "category": "Communication Tools",
    "parameters": [
        _action("send_message|reply_thread|list_channels|get_history|search_messages|list_users"),
        _p("channel", description="Channel ID or name"),
        _p("text", description="Message text"),
        _p("thread_ts", description="Parent message timestamp (for reply_thread)"),
        _p("query", description="Search query (for search_messages)"),
        _p("limit", type="integer", description="Max results"),
    ],
}]

DISCORD_TOOLS = [{
    "tool_name": "discord",
    "description": "Interact with Discord. Actions: send_message (channel_id, message), get_messages (channel_id, limit), list_channels (guild_id), delete_message (channel_id, message_id).",
    "function_path": "huf.ai.tools.discord.handle_action",
    "category": "Communication Tools",
    "parameters": [
        _action("send_message|get_messages|list_channels|delete_message"),
        _p("channel_id", description="Discord channel ID"),
        _p("guild_id", description="Discord server (guild) ID"),
        _p("message", description="Message text"),
        _p("message_id", description="Message ID to delete"),
        _p("limit", type="integer", description="Max messages"),
    ],
}]

TELEGRAM_TOOLS = [{
    "tool_name": "telegram",
    "description": "Send messages via Telegram bot. Actions: send_message (chat_id, message).",
    "function_path": "huf.ai.tools.telegram.handle_action",
    "category": "Communication Tools",
    "parameters": [
        _action("send_message"),
        _p("chat_id", description="Telegram chat ID"),
        _p("message", description="Message text"),
    ],
}]

GITHUB_TOOLS = [{
    "tool_name": "github",
    "description": "Interact with GitHub. Actions: list_repos, get_repo (repo_name), create_issue (repo_name, title, body), create_pr (repo_name, title, head, base, body), get_file (repo_name, path), search_code (query).",
    "function_path": "huf.ai.tools.github.handle_action",
    "category": "Developer Tools",
    "parameters": [
        _action("list_repos|get_repo|create_issue|create_pr|get_file|search_code"),
        _p("repo_name", description="Repository (owner/name)"),
        _p("title", description="Issue or PR title"),
        _p("body", description="Issue or PR body"),
        _p("head", description="Head branch (for create_pr)"),
        _p("base", description="Base branch (for create_pr)"),
        _p("path", description="File path in repo (for get_file)"),
        _p("query", description="Search query (for search_code)"),
    ],
}]

RECIPIENT_TOOLS = [{
    "tool_name": "get_integration_recipient",
    "description": "Look up a named recipient's service-specific ID (Slack user/channel, Telegram chat, Discord channel) from Integration Settings. Use before sending messages to resolve human names to IDs.",
    "function_path": "huf.ai.tools.recipient.handle_get_recipient",
    "category": "Communication Tools",
    "parameters": [
        _p("service", required=True, description="Service name: telegram, slack, discord"),
        _p("recipient_name", required=True, description="Human-friendly name as stored in Integration Settings"),
    ],
}]

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

ERPNEXT_TOOLS = [{
    "tool_name": "erpnext",
    "description": "Manage ERPNext transactions and accounting. Actions: list_sales_invoices (customer, status, from_date, to_date, limit), get_sales_invoice (name), create_sales_invoice (customer required, items list [{item_code,qty,rate}], company, posting_date), list_purchase_invoices (supplier, status, from_date, to_date, limit), get_purchase_invoice (name), list_payments (party_type, party, payment_type, from_date, to_date, limit), create_payment (payment_type required [Receive/Pay], party_type required, party required, paid_amount required; mode_of_payment, invoice_name), list_customers (search, customer_group, limit), get_customer (name), list_quotations (party_name, status, from_date, limit), create_quotation (quotation_to required [Customer/Lead], party_name required, items list, transaction_date, valid_till), list_rfqs (status, from_date, limit), get_ledger (account required, from_date, to_date, party_type, party, limit), create_journal_entry (voucher_type, posting_date, company, user_remark, accounts list [{account, debit_in_account_currency, credit_in_account_currency}]).",
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
