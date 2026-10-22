# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure Telegram update parsing. No Frappe imports, no network.

``parse_update`` turns any Bot API ``Update`` into a typed ``TelegramUpdate``;
``to_event`` maps the ones Huf ingress can act on to a ``NormalizedGatewayEvent`` and returns
``None`` for the rest (my_chat_member, reaction counts, ...), which the caller handles from the
typed object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from huf.ai.gateway_adapters.types import GatewayAttachment, NormalizedGatewayEvent

# (attachment kind, update field, is PhotoSize list)
MEDIA_FIELDS: tuple[tuple[str, str, bool], ...] = (
	("photo", "photo", True),
	("document", "document", False),
	("voice", "voice", False),
	("video", "video", False),
	("audio", "audio", False),
	("video_note", "video_note", False),
	("sticker", "sticker", False),
	("animation", "animation", False),
)

_MESSAGE_KEYS = (
	"message",
	"edited_message",
	"channel_post",
	"edited_channel_post",
	"business_message",
	"edited_business_message",
)
_START_RE = re.compile(r"^/start(?:@\w+)?(?:\s+(\S+))?\s*$")
_CAP = 300


def _cap(value: Any, limit: int = _CAP) -> str:
	text = " ".join(str(value if value is not None else "").split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _map(value: Any) -> Mapping[str, Any]:
	return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class TelegramUpdate:
	"""A parsed update. ``kind`` is the Update field name (e.g. ``message``, ``callback_query``)."""

	kind: str
	update_id: str
	raw: Mapping[str, Any]
	chat_id: str = ""
	chat_type: str = ""
	sender_id: str = ""
	display_name: str = ""
	message_id: str = ""
	message_thread_id: str = ""  # forum topic id (NOT a reply anchor)
	text: str = ""
	edited: bool = False
	is_channel: bool = False
	mentioned: bool = False
	mentions: tuple[str, ...] = ()
	command: str = ""
	start_payload: str = ""
	reply_to_message_id: str = ""
	forward_origin: Mapping[str, Any] = field(default_factory=dict)
	media_group_id: str = ""
	content_kind: str = "text"  # text|media|location|contact|venue|poll|dice|other
	callback_query_id: str = ""
	callback_data: str = ""
	reactions_added: tuple[str, ...] = ()
	reactions_removed: tuple[str, ...] = ()
	member_old_status: str = ""
	member_new_status: str = ""
	attachments_meta: tuple[Mapping[str, Any], ...] = ()
	is_bot: bool = False  # from.is_bot (bot-to-bot loop prevention)
	sender_business_bot: str = ""  # message.sender_business_bot.id
	business_connection_id: str = ""

	@property
	def is_room(self) -> bool:
		return self.chat_type in {"group", "supergroup", "channel"}

	@property
	def bot_blocked(self) -> bool:
		"""my_chat_member shows the bot lost access (user blocked it / it was kicked)."""
		return self.kind == "my_chat_member" and self.member_new_status in {"kicked", "left"}

	@property
	def bot_unblocked(self) -> bool:
		return self.kind == "my_chat_member" and self.member_new_status in {"member", "administrator"} and (
			self.member_old_status in {"kicked", "left"}
		)


def _utf16_slice(text: str, offset: int, length: int) -> str:
	units = text.encode("utf-16-le")
	return units[offset * 2 : (offset + length) * 2].decode("utf-16-le", errors="ignore")


def _emoji_list(reactions: Any) -> list[str]:
	out = []
	for r in reactions or []:
		r = _map(r)
		if r.get("type") == "emoji" and r.get("emoji"):
			out.append(str(r["emoji"]))
		elif r.get("type") == "custom_emoji":
			out.append("custom:" + str(r.get("custom_emoji_id") or ""))
		elif r.get("type") == "paid":
			out.append("paid")
	return out


def _sender_name(user: Mapping[str, Any]) -> str:
	username = str(user.get("username") or "").strip()
	return f"@{username}" if username else str(user.get("first_name") or "").strip()


def _forward_origin(origin: Mapping[str, Any]) -> dict[str, Any]:
	if not origin:
		return {}
	out: dict[str, Any] = {"type": origin.get("type", "")}
	for key in ("sender_user", "chat", "sender_chat"):
		if isinstance(origin.get(key), Mapping):
			out[key + "_id"] = str(origin[key].get("id"))
	if origin.get("sender_user_name"):
		out["sender_user_name"] = _cap(origin["sender_user_name"], 100)
	if origin.get("date") is not None:
		out["date"] = origin["date"]
	return out


def render_non_text(message: Mapping[str, Any]) -> tuple[str, str]:
	"""Agent-readable text for location/contact/venue/poll/dice messages: (content_kind, text)."""
	if message.get("venue"):
		v = _map(message["venue"])
		loc = _map(v.get("location"))
		return "venue", _cap(
			f"[venue] {v.get('title', '')}, {v.get('address', '')} ({loc.get('latitude')},{loc.get('longitude')})"
		)
	if message.get("location"):
		loc = _map(message["location"])
		return "location", f"[location] {loc.get('latitude')},{loc.get('longitude')}"
	if message.get("contact"):
		c = _map(message["contact"])
		name = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x)
		return "contact", _cap(f"[contact] {name} {c.get('phone_number', '')}".strip(), 200)
	if message.get("poll"):
		p = _map(message["poll"])
		options = " | ".join(_cap(_map(o).get("text"), 60) for o in (p.get("options") or [])[:10])
		return "poll", _cap(f"[poll] {p.get('question', '')}: {options}", 600)
	if message.get("dice"):
		d = _map(message["dice"])
		return "dice", f"[dice] {d.get('emoji', '')} {d.get('value', '')}".strip()
	return "", ""


def media_refs(message: Mapping[str, Any]) -> list[dict[str, Any]]:
	"""File references on a message: dicts with kind, file_id, mime_type, filename, file_unique_id."""
	refs = []
	for kind, field_name, is_list in MEDIA_FIELDS:
		value = message.get(field_name)
		if not value:
			continue
		obj = value[-1] if is_list and isinstance(value, list) and value else value
		if not isinstance(obj, Mapping) or not obj.get("file_id"):
			continue
		if kind == "document" and _map(message.get("animation")).get("file_id") == obj.get("file_id"):
			continue  # Telegram mirrors animations into ``document`` for old clients
		refs.append(
			{
				"kind": kind,
				"file_id": str(obj["file_id"]),
				"file_unique_id": str(obj.get("file_unique_id") or ""),
				"mime_type": str(obj.get("mime_type") or ("image/jpeg" if kind == "photo" else "")),
				"filename": str(obj.get("file_name") or ""),
				"file_size": int(obj.get("file_size") or 0),
			}
		)
	return refs


def _parse_message(kind: str, update: Mapping[str, Any], message: Mapping[str, Any]) -> TelegramUpdate:
	chat = _map(message.get("chat"))
	sender = _map(message.get("from"))
	sender_chat = _map(message.get("sender_chat"))
	is_channel = kind in ("channel_post", "edited_channel_post")
	if sender.get("id") is not None:
		sender_id = str(sender["id"])
	else:  # channel posts / anonymous admins carry sender_chat or only chat
		sender_id = str(sender_chat.get("id") or (chat.get("id") if is_channel else "") or "")
	text = str(message.get("text") or message.get("caption") or "")
	entities = list(message.get("entities") or []) + list(message.get("caption_entities") or [])
	mentions = []
	mentioned = False
	command = ""
	for ent in entities:
		etype = ent.get("type")
		if etype in ("mention", "bot_command", "text_mention"):
			mentioned = True
		if etype == "mention":
			mentions.append(_utf16_slice(text, int(ent.get("offset", 0)), int(ent.get("length", 0))))
		elif etype == "text_mention" and isinstance(ent.get("user"), Mapping):
			mentions.append("user:" + str(ent["user"].get("id")))
		elif etype == "bot_command" and not command and int(ent.get("offset", 0)) == 0:
			command = _utf16_slice(text, 0, int(ent.get("length", 0))).lstrip("/").split("@", 1)[0].lower()
	start = _START_RE.match(text) if message.get("text") else None
	kind_nt, rendered = render_non_text(message)
	refs = media_refs(message)
	content_kind = kind_nt or ("media" if refs else "text")
	if rendered:
		text = f"{text}\n{rendered}".strip() if text else rendered
	reply = _map(message.get("reply_to_message"))
	return TelegramUpdate(
		kind=kind,
		update_id=str(update.get("update_id") or ""),
		raw=update,
		chat_id=str(chat.get("id") if chat.get("id") is not None else ""),
		chat_type=str(chat.get("type") or "private"),
		sender_id=sender_id,
		display_name=_sender_name(sender) or str(sender_chat.get("title") or (chat.get("title") if is_channel else "") or ""),
		message_id=str(message["message_id"]) if message.get("message_id") is not None else "",
		message_thread_id=str(message["message_thread_id"]) if message.get("message_thread_id") is not None else "",
		text=text,
		edited=kind.startswith("edited_"),
		is_channel=is_channel,
		mentioned=mentioned,
		mentions=tuple(mentions),
		command=command,
		start_payload=(start.group(1) or "") if start else "",
		reply_to_message_id=str(reply["message_id"]) if reply.get("message_id") is not None else "",
		forward_origin=_forward_origin(_map(message.get("forward_origin"))),
		media_group_id=str(message.get("media_group_id") or ""),
		content_kind=content_kind,
		attachments_meta=tuple(refs),
		is_bot=bool(sender.get("is_bot")),
		sender_business_bot=str(_map(message.get("sender_business_bot")).get("id") or ""),
		business_connection_id=str(message.get("business_connection_id") or ""),
	)


def parse_update(update: Mapping[str, Any]) -> TelegramUpdate:
	"""Parse any Update. Unknown update types come back with ``kind == "unsupported"``."""
	update_id = str(update.get("update_id") or "")
	for key in _MESSAGE_KEYS:
		if isinstance(update.get(key), Mapping):
			return _parse_message(key, update, update[key])
	cq = _map(update.get("callback_query"))
	if cq:
		msg = _map(cq.get("message"))
		chat = _map(msg.get("chat"))
		sender = _map(cq.get("from"))
		return TelegramUpdate(
			kind="callback_query",
			update_id=update_id,
			raw=update,
			chat_id=str(chat.get("id") if chat.get("id") is not None else sender.get("id", "")),
			chat_type=str(chat.get("type") or "private"),
			sender_id=str(sender.get("id") or ""),
			display_name=_sender_name(sender),
			message_id=str(msg.get("message_id") or ""),
			message_thread_id=str(msg["message_thread_id"]) if msg.get("message_thread_id") is not None else "",
			is_bot=bool(sender.get("is_bot")),
			text=str(cq.get("data") or ""),
			callback_query_id=str(cq.get("id") or ""),
			callback_data=str(cq.get("data") or ""),
		)
	mr = _map(update.get("message_reaction"))
	if mr:
		user = _map(mr.get("user"))
		actor = _map(mr.get("actor_chat"))
		old, new = _emoji_list(mr.get("old_reaction")), _emoji_list(mr.get("new_reaction"))
		return TelegramUpdate(
			kind="message_reaction",
			update_id=update_id,
			raw=update,
			chat_id=str(_map(mr.get("chat")).get("id", "")),
			chat_type=str(_map(mr.get("chat")).get("type") or "private"),
			sender_id=str(user.get("id") or actor.get("id") or ""),
			display_name=_sender_name(user),
			message_id=str(mr.get("message_id") or ""),
			reactions_added=tuple(e for e in new if e not in old),
			reactions_removed=tuple(e for e in old if e not in new),
		)
	if update.get("message_reaction_count"):
		mc = _map(update["message_reaction_count"])
		return TelegramUpdate(
			kind="message_reaction_count", update_id=update_id, raw=update,
			chat_id=str(_map(mc.get("chat")).get("id", "")), message_id=str(mc.get("message_id") or ""),
		)
	for key in ("deleted_business_messages", "business_connection"):
		bm = _map(update.get(key))
		if bm:
			user = _map(bm.get("user"))
			return TelegramUpdate(
				kind=key,
				update_id=update_id,
				raw=update,
				chat_id=str(_map(bm.get("chat")).get("id", user.get("id", ""))),
				sender_id=str(user.get("id") or ""),
				business_connection_id=str(bm.get("business_connection_id") or bm.get("id") or ""),
			)
	for key in ("my_chat_member", "chat_member"):
		cm = _map(update.get(key))
		if cm:
			return TelegramUpdate(
				kind=key,
				update_id=update_id,
				raw=update,
				chat_id=str(_map(cm.get("chat")).get("id", "")),
				chat_type=str(_map(cm.get("chat")).get("type") or "private"),
				sender_id=str(_map(cm.get("from")).get("id") or ""),
				is_bot=bool(_map(cm.get("from")).get("is_bot")),
				member_old_status=str(_map(cm.get("old_chat_member")).get("status") or ""),
				member_new_status=str(_map(cm.get("new_chat_member")).get("status") or ""),
			)
	return TelegramUpdate(kind="unsupported", update_id=update_id, raw=update)


_NO_EVENT_KINDS = (
	"my_chat_member",
	"chat_member",
	"message_reaction_count",
	"unsupported",
	"business_connection",
	"deleted_business_messages",
)


def to_event(parsed: TelegramUpdate, attachments: tuple[GatewayAttachment, ...] = ()) -> NormalizedGatewayEvent | None:
	"""Map a parsed update to a Huf event, or ``None`` when ingress has no event for it.

	Raises ``ValueError`` when an update that should become an event lacks identifiers.
	"""
	if parsed.kind in _NO_EVENT_KINDS:
		return None
	if not parsed.update_id or not parsed.sender_id or not parsed.chat_id:
		raise ValueError("Telegram update is missing update, sender, or chat identifiers")
	if parsed.kind == "message_reaction":
		emoji = parsed.reactions_added[0] if parsed.reactions_added else ""
		return NormalizedGatewayEvent(
			provider_event_id=parsed.update_id,
			sender_id=parsed.sender_id,
			conversation_id=parsed.chat_id,
			message_text="",
			is_room=parsed.is_room,
			raw_payload=parsed.raw,
			display_name=parsed.display_name,
			kind="reaction",
			reaction_emoji=emoji,
			reaction_to=parsed.message_id,
		)
	return NormalizedGatewayEvent(
		provider_event_id=parsed.update_id,
		sender_id=parsed.sender_id,
		conversation_id=parsed.chat_id,
		message_text=parsed.text,
		thread_id=parsed.message_id or None,
		is_room=parsed.is_room,
		mentioned=parsed.mentioned,
		raw_payload=parsed.raw,
		display_name=parsed.display_name,
		attachments=attachments,
	)
