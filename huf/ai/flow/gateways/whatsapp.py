"""WhatsApp additions: buttons, ads, forwarded messages, locations, contacts and orders."""

from __future__ import annotations

from huf.ai.flow.gateways.spec_kit import field, param

PROVIDER = "WhatsApp"
LABEL = "WhatsApp"
NODE_TYPE = "trigger.whatsapp"
# Meta sends no language and WhatsApp groups are not modelled yet (plan Q12).
EXCLUDE_GENERIC = ("chat_scope", "only_when_mentioned")
EVENT_KINDS = [("message", "A WhatsApp message")]


def params() -> list[dict]:
	return [
		param("button_reply_ids", "Only when this button was chosen", "tags", help="The button ids you set when you sent the buttons."),
		param("button_payloads", "Only these button values", "tags"),
		param("ad_tags", "Only people who came from this ad or link", "tags"),
		param("first_message_only", "Only a person's first message", "boolean", default=False),
	]


def fields() -> list[dict]:
	return [
		field("provider", "Channel type", "text", PROVIDER, advanced=True),
		field("wa_id", "WhatsApp number", "text", "15550001111", sensitive=True, advanced=True),
		field("button_id", "Button chosen (id)", "text", "", advanced=True),
		field("button_title", "Button chosen", "text", ""),
		field("button_payload", "Button value", "text", "", advanced=True),
		field("interactive_reply", "Button or list choice", "record", None, advanced=True),
		field("referral", "Ad details", "record", None),
		field("referral_tag", "Ad or link tag", "text", ""),
		field("forwarded", "Forwarded message", "yes_no", False),
		field("contact_name", "Name on the contact card", "text", "", customer_provided=True),
		field("location", "Location shared", "record", None),
		field("contacts", "Contact cards shared", "list", []),
		field("order", "Order placed", "record", None),
		field("hours_since_last_customer_message", "Hours since their last message", "number", 0),
	]
