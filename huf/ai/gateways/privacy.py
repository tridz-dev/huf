"""Private-by-default Slack replies.

``Gateway.private_reply_policy`` decides where an answer to a channel message goes:

- "Reply where asked": no change.
- "Private when marked sensitive": a run flagged with :func:`mark_sensitive` is answered in a DM.
- "Always private": every channel answer is sent as a DM to the asker.

Direct messages are never changed.

Mechanism: a ``resolve_reply_target`` handler (call_first). When the reply must be private it opens a
DM with the sender, posts ONE neutral acknowledgement in the originating channel/thread (it never
contains the answer) and returns the DM channel id. The reply is then sent into that DM, so the
in-memory ``event.thread_id`` is cleared: a channel thread ts is not valid in a DM.

Fail closed: ``hooks._invoke`` swallows ordinary exceptions and ``call_first`` treats ``None`` as "no
change", which would leak the answer into the channel. So this handler never raises and never returns
``None`` once a private reply is required. If the DM cannot be opened (missing ``im:write``, API
error, no token) it posts a neutral "couldn't send privately" note in the thread, clears the thread id
and returns the sender's Slack user id (``chat.postMessage`` to a user id delivers to that user's DM
with the app, never to the channel) or, when even that is unknown, an unusable target. The send then
either lands in a DM or fails, and the event is marked Failed; the answer is never posted to the room.
"""

from __future__ import annotations

import json

import frappe

from huf.ai.gateways import hooks
from huf.ai.gateways.slack_context import get_slack_api

REPLY_WHERE_ASKED = "Reply where asked"
PRIVATE_WHEN_SENSITIVE = "Private when marked sensitive"
ALWAYS_PRIVATE = "Always private"

SENSITIVE_TTL_SECONDS = 3600
_KEY = "huf:gateway:sensitive:"
UNUSABLE_TARGET = "huf-private-reply-unavailable"

ACK_TEXT = "I've sent you a private message."
FAILED_TEXT = "I couldn't send this privately, so I haven't shared it here."


def _cache():
	return frappe.cache()


# ---- sensitivity marking ------------------------------------------------------
def _ids(obj) -> list[str]:
	if not obj:
		return []
	if isinstance(obj, str):
		return [obj]
	out = []
	for attr in ("name", "agent_run"):
		v = getattr(obj, attr, None)
		if v:
			out.append(str(v))
	return out


def mark_sensitive(event_name_or_run, reason: str | None = None) -> None:
	"""Flag a gateway event (or agent run) name as sensitive; short-lived."""
	for ident in _ids(event_name_or_run):
		_cache().set_value(_KEY + ident, reason or "sensitive", expires_in_sec=SENSITIVE_TTL_SECONDS)


def is_marked_sensitive(event) -> bool:
	return any(_cache().get_value(_KEY + i) for i in _ids(event))


def clear_sensitive(event_name_or_run) -> None:
	for ident in _ids(event_name_or_run):
		_cache().delete_value(_KEY + ident)


# ---- room detection -------------------------------------------------------------
def _payload_event(event) -> dict:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception:
			raw = None
	inner = raw.get("event") if isinstance(raw, dict) else None
	return inner if isinstance(inner, dict) else {}


def is_room(event) -> bool:
	"""True for channels/groups/mpims; False for DMs. Unknown shapes count as rooms (fail closed)."""
	ctype = _payload_event(event).get("channel_type")
	if ctype:
		return ctype != "im"
	cid = str(getattr(event, "conversation_id", "") or "")
	return not cid.startswith("D")


# ---- handler ----------------------------------------------------------------------
def _note(gateway, event, text: str) -> None:
	"""Best-effort neutral note in the originating channel/thread; never raises."""
	try:
		get_slack_api(gateway).post_message(event.conversation_id, text, thread_ts=event.thread_id or None)
	except Exception:
		pass


def _fail_closed(gateway, event):
	sender = str(getattr(event, "sender_id", "") or "")
	_note(gateway, event, FAILED_TEXT)
	event.thread_id = None
	return sender or UNUSABLE_TARGET


def resolve_reply_target(gateway, event, reply_text):
	policy = getattr(gateway, "private_reply_policy", None) or REPLY_WHERE_ASKED
	if policy not in (PRIVATE_WHEN_SENSITIVE, ALWAYS_PRIVATE):
		return None
	if not is_room(event):
		return None
	if policy == PRIVATE_WHEN_SENSITIVE and not is_marked_sensitive(event):
		return None
	try:
		sender = str(getattr(event, "sender_id", "") or "")
		if not sender:
			return _fail_closed(gateway, event)
		api = get_slack_api(gateway)
		dm = api.conversations_open([sender])
		if not dm:
			return _fail_closed(gateway, event)
		_note(gateway, event, ACK_TEXT)
		event.thread_id = None
		return dm
	except Exception:
		return _fail_closed(gateway, event)


def reply_ephemeral(gateway, event, text: str):
	"""Post a message only the asker can see, in the originating channel/thread."""
	return get_slack_api(gateway).post_ephemeral(
		event.conversation_id, event.sender_id, text,
		thread_ts=None if str(event.conversation_id or "").startswith("D") else (event.thread_id or None),
	)


hooks.register(hooks.RESOLVE_REPLY_TARGET, resolve_reply_target, provider="slack")
