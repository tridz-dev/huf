"""Solution intents (pure data, no frappe import).

Mirrors the INTENTS array of the Huf Solutions mockup. Ids double as the
purpose values of the Solution doctype, plus 'custom'.
"""

INTENTS = [
	{
		"id": "answer",
		"name": "Answer questions",
		"desc": "Replies from your docs, FAQ or catalog. Hands off when unsure.",
		"icon": "circle-help",
		"sample_name": "Shop FAQ",
		"entry": "catchall",
		"keywords": [],
		"ref": "",
		"suggested_templates": ["welcome_opt_in"],
		"policy": ["Replies only inside the 24-hour window", "Message customers first: off"],
	},
	{
		"id": "orders",
		"name": "Take orders",
		"desc": "Browse the menu, build an order, confirm pickup or delivery.",
		"icon": "shopping-bag",
		"sample_name": "Order desk",
		"entry": "keywords",
		"keywords": ["order", "menu", "cake"],
		"ref": "weekend_special",
		"suggested_templates": ["order_ready_pickup", "weekend_croissant_special"],
		"policy": ["Message first allowed with approved templates", "Daily cap: 400 for this entry point"],
	},
	{
		"id": "support",
		"name": "Support & handoff",
		"desc": "Sort the problem, collect details, pass to a person.",
		"icon": "life-buoy",
		"sample_name": "Support desk",
		"entry": "keywords",
		"keywords": ["help", "refund", "wrong", "complaint"],
		"ref": "",
		"suggested_templates": ["care_request_received"],
		"policy": ["Hand off to a person after 2 failed answers", "Message first: off"],
	},
	{
		"id": "bookings",
		"name": "Bookings",
		"desc": "Appointments, reservations, quotes and reminders.",
		"icon": "calendar-days",
		"sample_name": "Catering bookings",
		"entry": "keywords",
		"keywords": ["book", "event", "quote", "catering"],
		"ref": "office_lunch",
		"suggested_templates": ["catering_quote_ready", "welcome_opt_in"],
		"policy": ["Reminder templates on", "Daily cap: 500 for this entry point"],
	},
	{
		"id": "updates",
		"name": "Send updates",
		"desc": "Outbound only: order status, alerts and broadcasts using approved templates.",
		"icon": "bell",
		"sample_name": "Order updates",
		"entry": "none",
		"keywords": [],
		"ref": "",
		"suggested_templates": ["order_ready_pickup", "delivery_delay_notice"],
		"policy": ["Templates only, with an opt-in check", "Daily cap: 300"],
	},
	{
		"id": "team",
		"name": "Team & internal",
		"desc": "Staff ask questions, log entries or approve requests from WhatsApp.",
		"icon": "users",
		"sample_name": "Staff desk",
		"entry": "allowlist",
		"keywords": [],
		"ref": "",
		"suggested_templates": [],
		"policy": ["Only allow-listed staff numbers may message", "No messages to customers"],
	},
]

PURPOSES = tuple(i["id"] for i in INTENTS) + ("custom",)

_BY_ID = {i["id"]: i for i in INTENTS}


def get_intent(intent_id):
	"""Return the intent dict for an id, or None if unknown."""
	return _BY_ID.get(intent_id)


def intent_ids():
	"""Return intent ids in mockup order."""
	return [i["id"] for i in INTENTS]
