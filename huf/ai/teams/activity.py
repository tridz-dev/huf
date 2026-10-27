"""Inbound Teams activity -> NormalizedGatewayEvent.

Verification (JWT) always happens before this module runs (``verify_inbound`` precedes both the
``ingest_update`` hook and ``normalize_inbound`` in the webhook flow), so nothing here authenticates.
Tenant admission, channel pinning (``channelId`` must be ``msteams``: defence in depth on top of
``auth._verify``) and activity-type filtering do live here.

Untrusted short strings that reach the agent prompt (sender display name, attachment names and URLs, via the
core ``_describe_attachments``) are sanitised here at the source: control/format characters and newlines are
replaced by spaces and lengths are capped, so they cannot break the prompt structure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import unicodedata
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

from huf.ai.gateway_adapters.types import GatewayAttachment, GatewayInboundRequest, NormalizedGatewayEvent

logger = logging.getLogger("huf.teams.activity")

FILE_DOWNLOAD_INFO = "application/vnd.microsoft.teams.file.download.info"
_MAX_HTML_TEXT = 20000
_KNOWN_KINDS = frozenset(
	{
		"typing",
		"messagereaction",
		"invoke",
		"installationupdate",
		"conversationupdate",
		"endofconversation",
		"event",
		"messageupdate",
		"messagedelete",
	}
)
TEAMS_CHANNEL_ID = "msteams"
MAX_DISPLAY_NAME = 80
MAX_ATTACHMENT_NAME = 120
MAX_ATTACHMENT_URL = 2048
_CONVERSATION_TYPES = {"personal": False, "groupchat": True, "channel": True}


def load_activity(request: GatewayInboundRequest) -> dict[str, Any]:
	"""Parse the request body into an activity dict or raise ``ValueError``."""
	try:
		activity = json.loads(request.body.decode("utf-8")) if request.body else None
	except Exception as exc:
		raise ValueError("Invalid Teams Activity JSON payload") from exc
	if not isinstance(activity, dict):
		raise ValueError("Invalid Teams Activity JSON payload")
	return activity


def ignore_kind(activity: Mapping[str, Any]) -> str:
	"""Short, log-safe label for a non-message activity type (``unknown`` for anything unrecognised)."""
	kind = str(activity.get("type") or "").strip().lower()
	return kind if kind in _KNOWN_KINDS else "unknown"


def _tenant_of(activity: Mapping[str, Any]) -> str:
	channel_data = activity.get("channelData") or {}
	conversation = activity.get("conversation") or {}
	tenant = (channel_data.get("tenant") or {}).get("id") if isinstance(channel_data, dict) else None
	return str(tenant or (conversation.get("tenantId") if isinstance(conversation, dict) else "") or "")


def is_teams_channel(activity: Mapping[str, Any]) -> bool:
	"""True only for ``channelId == "msteams"`` (case-insensitive). Web Chat/Direct Line/Emulator are rejected."""
	channel_id = activity.get("channelId")
	return isinstance(channel_id, str) and channel_id.strip().lower() == TEAMS_CHANNEL_ID


def clean_label(value: Any, limit: int) -> str:
	"""Single-line, control-free, length-capped text for prompt-bound labels (names, URLs)."""
	text = "".join(
		" " if unicodedata.category(ch)[0] in ("C", "Z") and ch != " " else ch for ch in str(value or "")
	)
	return " ".join(text.split())[:limit]


def tenant_allowed(activity: Mapping[str, Any], credentials: Mapping[str, str]) -> bool:
	allowed = {str(credentials.get("tenant_id") or "").strip().lower()}
	allowed.update(
		part.strip().lower() for part in str(credentials.get("allowed_tenant_ids") or "").split(",")
	)
	allowed.discard("")
	tenant = _tenant_of(activity).strip().lower()
	return bool(tenant) and tenant in allowed


def bot_id(activity: Mapping[str, Any]) -> str:
	return str((activity.get("recipient") or {}).get("id") or "")


def bot_added(activity: Mapping[str, Any]) -> bool:
	"""True for the install-type updates that make a proactive conversation reference worthwhile."""
	kind = str(activity.get("type") or "").lower()
	action = str(activity.get("action") or "").lower()
	if kind == "installationupdate":
		return action != "remove"
	if kind != "conversationupdate":
		return False
	if action == "add":
		return True
	me = bot_id(activity)
	return bool(me) and any(
		isinstance(member, dict) and member.get("id") == me for member in activity.get("membersAdded") or []
	)


class _TextExtractor(HTMLParser):
	_SKIP = frozenset({"script", "style", "head", "template"})
	_BREAK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"})

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.parts: list[str] = []
		self._skip = 0

	def handle_starttag(self, tag, attrs):
		if tag in self._SKIP:
			self._skip += 1
		elif tag in self._BREAK:
			self.parts.append("\n")

	def handle_endtag(self, tag):
		if tag in self._SKIP:
			self._skip = max(0, self._skip - 1)
		elif tag in self._BREAK:
			self.parts.append("\n")

	def handle_data(self, data):
		if not self._skip:
			self.parts.append(data)


def html_to_text(markup: Any) -> str:
	"""Plain text of an HTML fragment: tags dropped, script/style content discarded, length-capped."""
	if not isinstance(markup, str) or not markup.strip():
		return ""
	parser = _TextExtractor()
	try:
		parser.feed(markup[: _MAX_HTML_TEXT * 4])
		parser.close()
	except Exception:
		return ""
	lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
	return "\n".join(line for line in lines if line)[:_MAX_HTML_TEXT]


def strip_bot_mention(text: str, activity: Mapping[str, Any]) -> tuple[str, bool]:
	"""Remove the ``<at>..</at>`` span of mentions of the bot (entities[] decide) and report if present."""
	me = bot_id(activity)
	mentioned = False
	if not me:
		return text, False
	for entity in activity.get("entities") or []:
		if not isinstance(entity, dict) or str(entity.get("type") or "").lower() != "mention":
			continue
		target = entity.get("mentioned") or {}
		if not isinstance(target, dict) or target.get("id") != me:
			continue
		mentioned = True
		span = entity.get("text")
		if not isinstance(span, str) or not span:
			name = target.get("name")
			span = f"<at>{name}</at>" if name else ""
		if span:
			text = text.replace(span, " ")
	return " ".join(text.split()) if mentioned else text.strip(), mentioned


def _attachments(activity: Mapping[str, Any]) -> tuple[list[GatewayAttachment], list[str]]:
	files: list[GatewayAttachment] = []
	html_texts: list[str] = []
	for attachment in activity.get("attachments") or []:
		if not isinstance(attachment, dict):
			continue
		content_type = str(attachment.get("contentType") or "")
		content = attachment.get("content")
		if content_type == "text/html":
			extracted = html_to_text(content)
			if extracted:
				html_texts.append(extracted)
			continue
		name = clean_label(attachment.get("name"), MAX_ATTACHMENT_NAME)
		if content_type == FILE_DOWNLOAD_INFO:
			info = content if isinstance(content, dict) else {}
			url = info.get("downloadUrl") or attachment.get("contentUrl")
			file_type = str(info.get("fileType") or "")
			mime = (mimetypes.guess_type(name)[0] if name else None) or (
				mimetypes.guess_type(f"x.{file_type}")[0] if file_type else None
			)
			if url:
				files.append(
					GatewayAttachment(
						mime_type=mime or "application/octet-stream",
						filename=name,
						url=clean_label(url, MAX_ATTACHMENT_URL),
						kind="file",
					)
				)
			continue
		content_url = attachment.get("contentUrl")
		if content_url:
			files.append(
				GatewayAttachment(
					mime_type=clean_label(content_type, MAX_ATTACHMENT_NAME),
					filename=name,
					url=clean_label(content_url, MAX_ATTACHMENT_URL),
					kind="file",
				)
			)
	return files, html_texts


def _event_id(activity: Mapping[str, Any], text: str) -> str:
	activity_id = str(activity.get("id") or "").strip()
	if activity_id:
		return activity_id
	# Stable across Bot Connector retries of the same payload (a content digest, not the builtin string hash).
	basis = "\x00".join(
		str(part)
		for part in (
			(activity.get("conversation") or {}).get("id"),
			(activity.get("from") or {}).get("id"),
			activity.get("timestamp") or activity.get("localTimestamp"),
			text,
		)
	)
	return "teams-" + hashlib.sha256(basis.encode()).hexdigest()[:32]


def build_event(activity: dict[str, Any], credentials: Mapping[str, str]) -> NormalizedGatewayEvent | str:
	"""Event for a message activity, or a short ignore kind string (never raises ``ValueError``)."""
	if not is_teams_channel(activity):
		return "channel"
	if str(activity.get("type") or "").lower() != "message":
		return ignore_kind(activity)
	if not tenant_allowed(activity, credentials):
		return "tenant"

	conversation = activity.get("conversation") or {}
	from_account = activity.get("from") or {}
	if not isinstance(conversation, dict) or not isinstance(from_account, dict):
		return "invalid"
	raw_conversation_id = str(conversation.get("id") or "")
	base_id, _, suffix = raw_conversation_id.partition(";messageid=")
	conv_type = str(conversation.get("conversationType") or "").lower()
	is_room = _CONVERSATION_TYPES.get(conv_type, bool(conversation.get("isGroup")))

	text, mentioned = strip_bot_mention(str(activity.get("text") or ""), activity)
	files, html_texts = _attachments(activity)
	extra = [t for t in html_texts if t not in text]
	if extra:
		text = "\n".join(part for part in (text, *extra) if part)
	if not text and not files:
		return "empty"

	sender_id = str(
		from_account.get("aadObjectId") or from_account.get("id") or from_account.get("name") or ""
	)
	if not base_id.strip() or not sender_id.strip():
		return "invalid"

	event_id = _event_id(activity, text)
	thread_id = None
	if conv_type == "channel":
		thread_id = suffix or str(activity.get("replyToId") or "") or event_id
	return NormalizedGatewayEvent(
		provider_event_id=event_id,
		sender_id=sender_id,
		conversation_id=base_id,
		message_text=text,
		thread_id=thread_id,
		is_room=is_room,
		mentioned=mentioned or not is_room,
		raw_payload=activity,
		display_name=clean_label(from_account.get("name"), MAX_DISPLAY_NAME),
		attachments=tuple(files),
	)


def normalize(request: GatewayInboundRequest, credentials: Mapping[str, str]) -> NormalizedGatewayEvent:
	"""Direct-call normalisation (the webhook path filters through ``hooks.ingest_update`` first).

	Request authenticity was established earlier by ``verify_inbound``. Raises ``ValueError`` when the
	activity is not an admissible message (the webhook never reaches here for those).
	"""
	event = build_event(load_activity(request), credentials)
	if isinstance(event, str):
		logger.info("Teams activity not normalised: %s", event)
		raise ValueError(f"Teams activity ignored: {event}")
	return event
