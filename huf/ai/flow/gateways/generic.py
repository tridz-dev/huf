"""The base spec every gateway shares: filters that need nothing provider-specific, and the flat ``input.*`` payload."""

from __future__ import annotations

from huf.ai.flow.gateways.spec_kit import field, param

MESSAGE_KINDS = [
	("text", "Text"),
	("image", "Photo"),
	("audio", "Audio file"),
	("voice", "Voice note"),
	("video", "Video"),
	("document", "File"),
	("sticker", "Sticker"),
	("location", "Location"),
	("contact", "Contact card"),
	("button_reply", "Button chosen"),
	("list_reply", "List item chosen"),
	("order", "Order"),
	("other", "Something else"),
]

GENERIC_EVENT_KINDS = [("message", "A message")]

GROUP_ONLY = {"key": "chat_scope", "in": ["groups", "both"]}


def generic_params() -> list[dict]:
	return [
		param(
			"only_senders", "Only these people", "people",
			help="Leave empty to answer everyone the channel lets in. Names shown here can be faked on channels that do not sign their messages.",
		),
		param("message_kinds", "Only these kinds of message", "multiselect", options=MESSAGE_KINDS, help="Leave empty for every kind."),
		param("keywords", "Only messages that contain", "tags", help="Any of these words. Capital letters do not matter."),
		param("starts_with", "Only messages that start with", "text"),
		param(
			"chat_scope", "Where", "select", default="both",
			options=[("direct", "One-to-one chats"), ("groups", "Groups"), ("both", "Both")],
		),
		param("only_when_mentioned", "Only when the bot is mentioned", "boolean", default=False, show_when=GROUP_ONLY),
		param("has_attachment", "Only messages with a file", "boolean", default=False),
		param("ignore_bots", "Ignore messages from other bots", "boolean", default=True),
		param(
			"max_runs_per_sender_per_hour", "Most runs per person per hour", "number", default=30, section="more",
			help="Further messages from the same person that hour are skipped.",
		),
		param(
			"allow_parallel", "Handle several messages from one chat at the same time", "boolean", default=False, section="more",
			help="Off by default so answers to one chat keep their order.",
		),
	]


def generic_fields() -> list[dict]:
	return [
		field("text", "Message text", "text", "Hi, is my order ready?", customer_provided=True),
		field("message", "Message text (same as above)", "text", "Hi, is my order ready?", customer_provided=True, advanced=True),
		field("display_name", "Sender name", "text", "Asha", customer_provided=True),
		field("sender_id", "Sender id", "text", "15550001111", sensitive=True, advanced=True),
		field("message_type", "Kind of message", "text", "text"),
		field("kind", "Event kind", "text", "message"),
		field("attachments", "Files", "list", []),
		field("received_at", "Received at", "datetime", "2026-01-15 17:15:00"),
		field("is_room", "In a group", "yes_no", False),
		field("mentioned", "Mentioned the bot", "yes_no", False),
		field("language", "Language", "text", ""),
		field("transcript", "Voice note as text", "text", "", customer_provided=True),
		field("reply_to_message_id", "Replying to", "text", None, advanced=True),
		field("conversation_id", "Conversation id", "text", "15550001111", advanced=True),
		field("thread_id", "Thread id", "text", "15550001111", advanced=True),
		field("message_id", "Message id", "text", "m-0001", advanced=True),
		field("gateway", "Channel record", "text", "Support", advanced=True),
		field("provider", "Channel type", "text", "Slack", advanced=True),
		field("gateway_event", "Message record", "text", "GWE-0001", advanced=True),
	]
