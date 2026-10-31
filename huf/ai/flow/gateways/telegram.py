"""Telegram additions: commands, button taps, topics, chat types and Mini App data."""

from __future__ import annotations

from huf.ai.flow.gateways.spec_kit import field, param

PROVIDER = "Telegram"
LABEL = "Telegram"
NODE_TYPE = "trigger.telegram"
EXCLUDE_GENERIC: tuple = ()
EVENT_KINDS = [("message", "A Telegram message"), ("callback", "A button tap")]


def params() -> list[dict]:
	return [
		param("only_chats", "Only these chats", "tags", help="Chat ids or @names."),
		param(
			"chat_kinds", "Only these kinds of chat", "multiselect",
			options=[("private", "Private chats"), ("group", "Groups"), ("supergroup", "Large groups"), ("channel", "Channels")],
		),
		param("topics", "Only these topics", "tags", help="Topic ids inside a group with topics."),
		param("commands", "Only these commands", "tags", help="For example start or help, without the slash."),
		param("callback_prefixes", "Only buttons whose value starts with", "tags"),
		param("language", "Only these languages", "tags", help="Language codes such as en or hi."),
		param("include_edits", "Also when a message is edited", "boolean", default=False, section="more"),
		param("include_channel_posts", "Also posts in channels", "boolean", default=False, section="more"),
	]


def fields() -> list[dict]:
	return [
		field("telegram_user_id", "Telegram user id", "text", "1001", sensitive=True, advanced=True),
		field("telegram_chat_id", "Telegram chat id", "text", "1001", advanced=True),
		field("telegram_chat_type", "Chat type", "text", "private"),
		field("message_thread_id", "Topic id (same as below)", "text", "", advanced=True),
		field("topic_id", "Topic", "text", ""),
		field("command", "Command", "text", ""),
		field("command_args", "Text after the command", "text", "", customer_provided=True),
		field("callback_data", "Button value", "text", "", advanced=True),
		field("callback_query_id", "Button tap id", "text", "", advanced=True),
		field("username", "Username", "text", "asha_k", customer_provided=True),
		field("edited", "Edited message", "yes_no", False),
		field("is_channel_post", "Channel post", "yes_no", False),
		field("web_app_data", "Mini App data", "record", None, customer_provided=True),
		field("sender_is_bot", "Sent by a bot", "yes_no", False),
		field("business_connection_id", "Business connection id", "text", "", advanced=True),
	]
