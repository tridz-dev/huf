"""Tool specs for the channel (WhatsApp/CRM/ERP/LMS/commerce) agent tools, aggregated by ``_registry``.

Own ``_p`` copy: ``_registry`` imports this module, so importing it back would be circular.
"""


def _p(name, type="string", required=False, description=""):
	return {
		"label": name.replace("_", " ").title(),
		"fieldname": name,
		"type": type,
		"required": int(required),
		"description": description,
	}


HANDOFF_TOOLS = [
	{
		"tool_name": "handoff_to_solution",
		"description": (
			"Hand the current gateway chat over to another Live solution. From the next message on, the contact is "
			"served by that solution. Sends no message itself; tell the contact what is happening in your own reply. "
			"Only works inside a gateway conversation. Arguments: solution (the solution name or title), "
			"reason (optional, short)."
		),
		"function_path": "huf.ai.tools.handoff.handle_handoff_to_solution",
		"category": "Communication Tools",
		"parameters": [
			_p("solution", required=True, description="Name or title of the Live solution to hand this chat to"),
			_p("reason", description="Optional short reason for the handoff"),
		],
	},
]

HANDOFF_HUMAN_TOOLS = [
	{
		"tool_name": "handoff_to_human",
		"description": (
			"Hand the current WhatsApp conversation to a human. The AI stops answering this chat, a linked ticket/lead "
			"is created when the gateway's handoff target (Helpdesk/CRM) is set, and the contact receives the gateway's "
			"handoff message once. Only works inside a gateway conversation. Arguments: summary (what the human needs "
			"to know), priority (low, normal, high, urgent), target (optional: none, helpdesk, crm, erpnext; defaults "
			"to the gateway setting)."
		),
		"function_path": "huf.ai.tools.handoff.handle_handoff_to_human",
		"category": "Communication Tools",
		"parameters": [
			_p("summary", required=True, description="Short summary of the conversation and what the customer needs"),
			_p("priority", description="low, normal, high or urgent (default normal)"),
			_p("target", description="Optional handoff target: none, helpdesk, crm or erpnext; default is the gateway setting"),
		],
	},
]

# Hub gateway setup (PLAN 4.3 P0a/P0b). Admin-only: each handler checks system.integrations.manage.
# setup_gateway takes only a credentials_ref from the secret form (huf.ai.secrets.stash_secret); the
# schema has no plaintext `credentials` parameter, and the function rejects plaintext in agent context.
GATEWAY_SETUP_TOOLS = [
	{
		"tool_name": "setup_gateway",
		"description": (
			"Create or update a channel Gateway (e.g. WhatsApp) from credentials the user entered in the secret form. "
			"Pass the credentials_ref returned by that form (e.g. SS-0001) and the non-secret fields (phone_number_id, "
			"waba_id, app_id). The secret values are never shown to you. Returns the webhook_url to give the user for "
			"Meta's webhook settings. Admin only."
		),
		"function_path": "huf.ai.tools.gateway_pairing_tools.setup_gateway",
		"category": "Builder",
		"parameters": [
			_p("provider", required=True, description="Channel provider, e.g. WhatsApp"),
			_p("gateway_name", required=True, description="Name for this Gateway instance, e.g. WhatsApp Support"),
			_p(
				"credentials_ref",
				required=True,
				description="credentials_ref from the secret form, e.g. SS-0001. Single use, expires in 30 minutes.",
			),
			_p(
				"non_secret_fields",
				type="object",
				description="Non-secret values: phone_number_id, waba_id, app_id (JSON object of name to value)",
			),
		],
	},
	{
		"tool_name": "test_gateway_health",
		"description": (
			"Run the health probe for a WhatsApp/channel Gateway: whether it is enabled, its last event and last error, "
			"and whether its stored credentials initialize the adapter. Use after the user says they finished entering "
			"credentials in the setup wizard; if the probe is not verified yet, call it again later (poll) rather than "
			"telling the user it is done. Admin only."
		),
		"function_path": "huf.ai.tools.gateway_pairing_tools.test_gateway_health",
		"category": "Builder",
		"parameters": [
			_p("gateway_name", required=True, description="Name of the Gateway document to check"),
		],
	},
	{
		"tool_name": "list_pairing_requests",
		"description": (
			"List pending (unexpired) pairing requests: people who messaged the channel and wait for approval. "
			"Codes are masked. Use it to show who is waiting, then approve_pairing_code after the user confirms. Admin only."
		),
		"function_path": "huf.ai.tools.gateway_pairing_tools.list_pairing_requests",
		"category": "Builder",
		"parameters": [
			_p("gateway_name", description="Optional Gateway name to filter pending requests"),
		],
	},
	{
		"tool_name": "approve_pairing_code",
		"description": (
			"Approve a pending pairing request so that person can chat with the channel. Pass the pairing code the user "
			"gives you (or the entry id from list_pairing_requests). Only call it after the user confirms the person. Admin only."
		),
		"function_path": "huf.ai.tools.gateway_pairing_tools.approve_pairing_code",
		"category": "Builder",
		"parameters": [
			_p("pairing_code_or_id", required=True, description="The pairing code (e.g. PAIR-7A9KXM4Q) or the entry id"),
			_p("gateway_name", description="Gateway the code belongs to (required when using a code)"),
			_p("notes", description="Optional notes recorded with the approval"),
		],
	},
]


CRM_LEAD_TOOLS = [
	{
		"tool_name": "create_lead",
		"description": (
			"Create (or find) the Frappe CRM Lead for the current WhatsApp contact, matched by phone. "
			"Only works inside a gateway conversation and when Frappe CRM is installed. "
			"Arguments: name (optional), email (optional), note (optional, added to the lead)."
		),
		"function_path": "huf.ai.channels.tools.crm.handle_create_lead",
		"category": "Communication Tools",
		"parameters": [
			_p("name", description="Contact's name"),
			_p("email", description="Contact's email"),
			_p("note", description="Note to add to the lead"),
		],
	},
]


# Channel conversation tools (BE-ADAPT-HD): FYI ticket without handoff.
CHANNEL_HELPDESK_TOOLS = [
	{
		"tool_name": "create_ticket",
		"description": "Create a Helpdesk ticket (FYI, no handoff) for the current channel conversation. The conversation stays with the AI.",
		"function_path": "huf.ai.channels.tools.create_ticket",
		"category": "Helpdesk Tools",
		"parameters": [
			_p("summary", required=True, description="What the ticket is about"),
			_p("priority", description="low, normal, high or urgent (default normal)"),
		],
	},
]


# ERPNext channel tools (BE-ADAPT-ERP): bound to the current conversation's customer; orders are draft only.
ERP_CHANNEL_TOOLS = [
	{
		"tool_name": "erp_lookup_customer",
		"description": "Find the ERPNext customer and contact for a phone number. Defaults to the conversation sender.",
		"function_path": "huf.ai.channels.tools.erp.lookup_customer",
		"category": "ERPNext Tools",
		"parameters": [_p("phone", description="Phone number (optional; defaults to the conversation sender)")],
	},
	{
		"tool_name": "erp_create_order",
		"description": "Create a DRAFT Sales Order for the conversation's customer (never submitted; staff confirm it).",
		"function_path": "huf.ai.channels.tools.erp.create_order",
		"category": "ERPNext Tools",
		"parameters": [
			_p("items", type="array", required=True, description="List of {item_code, qty}"),
			_p("delivery_date", description="Requested delivery date (YYYY-MM-DD)"),
		],
	},
	{
		"tool_name": "erp_order_status",
		"description": "Status, delivery and billing of the conversation customer's recent orders, or of one order.",
		"function_path": "huf.ai.channels.tools.erp.order_status",
		"category": "ERPNext Tools",
		"parameters": [_p("order_name", description="Sales Order name (optional)")],
	},
]


# Commerce blueprint (BE-CATALOG): send catalog products as interactive product / product_list messages.
COMMERCE_TOOLS = [
	{
		"tool_name": "send_products",
		"description": "Send catalog products to the customer as a WhatsApp product card (one item) or product list (several). item_codes are ERPNext Item codes (the catalog retailer ids). Same window, opt-out and recipient rules as every WhatsApp send.",
		"function_path": "huf.ai.channels.commerce.messages.send_products",
		"category": "Communication Tools",
		"parameters": [
			_p("item_codes", type="array", required=True, description="Item codes to show (max 30)"),
			_p("header", description="Header text for a product list (max 60)"),
			_p("body", description="Message text shown with the products"),
		],
	},
]


# WhatsApp Flows (BE-FLOWS): send a Flow form to the current conversation's contact.
WA_FLOW_TOOLS = [
	{
		"tool_name": "send_wa_flow",
		"description": "Send a WhatsApp Flow (a native form) to the current conversation's contact. The submitted answers come back as a 'Form submitted: key=value' message.",
		"function_path": "huf.ai.channels.wa_flows.handle_send_wa_flow",
		"category": "Communication Tools",
		"parameters": [
			_p("flow_name", required=True, description="Name of a synced, published WhatsApp Flow"),
			_p("cta", required=True, description="Button label that opens the form (max 30 chars)"),
			_p("screen", description="Optional first screen id"),
			_p("data", type="object", description="Optional data for the first screen"),
		],
	},
]


# BE-LMS: Frappe LMS agent tools (enroll, progress, certificate) and the lesson-reminder job.
LMS_TOOLS = [
	{
		"tool_name": "lms_list_courses",
		"description": "List the published Frappe LMS courses.",
		"function_path": "huf.ai.channels.tools.lms.lms_list_courses",
		"category": "Communication Tools",
		"parameters": [],
	},
	{
		"tool_name": "lms_enroll",
		"description": (
			"Enroll the current WhatsApp contact in a published LMS course. Only works when the number matches an existing account; "
			"never creates an account. Argument: course (name or title)."
		),
		"function_path": "huf.ai.channels.tools.lms.lms_enroll",
		"category": "Communication Tools",
		"parameters": [_p("course", required=True, description="Course name or title")],
	},
	{
		"tool_name": "lms_my_progress",
		"description": "Show the current WhatsApp contact's LMS enrollments and progress.",
		"function_path": "huf.ai.channels.tools.lms.lms_my_progress",
		"category": "Communication Tools",
		"parameters": [],
	},
	{
		"tool_name": "lms_send_certificate",
		"description": "Send the current contact's certificate PDF for a course as a WhatsApp document. Argument: course (name or title).",
		"function_path": "huf.ai.channels.tools.lms.lms_send_certificate",
		"category": "Communication Tools",
		"parameters": [_p("course", required=True, description="Course name or title")],
	},
]


CHANNEL_TOOLS = (
	HANDOFF_HUMAN_TOOLS
	+ CRM_LEAD_TOOLS
	+ GATEWAY_SETUP_TOOLS
	+ ERP_CHANNEL_TOOLS
	+ CHANNEL_HELPDESK_TOOLS
	+ COMMERCE_TOOLS
	+ WA_FLOW_TOOLS
	+ LMS_TOOLS
)
