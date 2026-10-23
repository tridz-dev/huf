# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Business ("Secretary") mode: OBSERVE-ONLY by default (R9).

Verified against https://core.telegram.org/bots/api:

- Updates: ``business_connection`` (bot connected / disconnected / connection edited),
  ``business_message`` (new message in a connected account's chat), ``edited_business_message``,
  ``deleted_business_messages`` (``BusinessMessagesDeleted``: ``business_connection_id``, ``chat``,
  ``message_ids``). All four must be in ``allowed_updates`` (see ``telegram_client.ALLOWED_UPDATES``).
- ``BusinessConnection``: ``id``, ``user`` (the account owner), ``user_chat_id`` (private chat with the
  owner; the bot can message it), ``date``, ``rights`` (``BusinessBotRights``, optional), ``is_enabled``.
- ``BusinessBotRights`` (all optional booleans): ``can_reply``, ``can_read_messages``,
  ``can_delete_sent_messages``, ``can_delete_all_messages``, plus profile/gift/story rights we never use.
- ``getBusinessConnection(business_connection_id)`` -> ``BusinessConnection``.
- Send methods take an optional ``business_connection_id``: the message is sent AS the account owner.
- ``readBusinessMessage(business_connection_id, chat_id, message_id)`` needs ``can_read_messages`` and a chat
  active in the last 24h. ``deleteBusinessMessages(business_connection_id, message_ids[1..100])`` needs
  ``can_delete_sent_messages`` (own) or ``can_delete_all_messages`` (any).
- ``Message.business_connection_id`` marks a business chat message; ``Message.sender_business_bot`` is set only
  on outgoing messages sent by a bot on behalf of the account. ``getMe.can_connect_to_business`` is the flag.
- In a business chat ``chat.id`` is the customer; the owner's own messages carry ``from.id == user.id``.

SAFETY: the bot speaks as a real person. Policy per business message (``register_business_policy``):
``ignore`` | ``observe`` (default: recorded, never answered) | ``draft`` (proposed reply goes to the OWNER's
chat with approve / edit / reject buttons; nothing reaches the customer until approved) | ``reply``
(auto-reply). ``draft`` / ``reply`` are downgraded to ``observe`` unless the connection is enabled and holds
``can_reply``. The owner's own messages, bot-sent messages (``sender_business_bot``) and bot senders never
trigger a policy (loop prevention). Edits and deletions are only ever recorded.

The connection store lives in the frappe cache (no DocType fields); observations are a capped cache list.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable

import frappe

from huf.ai.gateway_adapters import telegram_keyboards as kb

POLICIES = ("ignore", "observe", "draft", "reply")
DEFAULT_POLICY = "observe"
CALLBACK_PREFIX = "bz"
CONN_TTL = 90 * 24 * 3600
DRAFT_TTL = 24 * 3600
OBS_MAX = 100
TEXT_CAP = 500

BUSINESS_KINDS = (
	"business_connection",
	"business_message",
	"edited_business_message",
	"deleted_business_messages",
)


# Returned by an async draft producer that enqueued its job: the draft will reach the owner later.
DRAFT_QUEUED = object()


class BusinessReplyBlocked(Exception):
	"""A business send was refused locally (unknown / disabled connection or missing right)."""

	def __init__(self, reason: str) -> None:
		self.reason = reason
		super().__init__(f"Business action blocked: {reason}")


# -- cache ---------------------------------------------------------------------------------------


def _cache():
	return frappe.cache()


def _get(key: str) -> Any:
	value = _cache().get_value(key)
	if isinstance(value, (str, bytes)):
		try:
			return json.loads(value)
		except ValueError:
			return None
	return value


def _put(key: str, value: Any, ttl: int) -> None:
	_cache().set_value(key, json.dumps(value), expires_in_sec=ttl)


def _conn_key(connection_id: str) -> str:
	return f"huf:tgbiz:conn:{connection_id}"


# -- connection store ----------------------------------------------------------------------------


def _rights(raw: dict) -> dict[str, bool]:
	rights = raw.get("rights")
	if not isinstance(rights, dict):
		# Older API shape: a bare top-level can_reply.
		rights = {"can_reply": raw["can_reply"]} if "can_reply" in raw else {}
	return {k: bool(v) for k, v in rights.items()}


def connection_from_api(raw: dict, gateway_name: str = "") -> dict | None:
	"""Normalize a BusinessConnection object to the stored shape (None when it has no id / owner)."""
	if not isinstance(raw, dict) or not raw.get("id"):
		return None
	user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
	if user.get("id") is None:
		return None
	return {
		"id": str(raw["id"]),
		"gateway": gateway_name,
		"owner_id": str(user["id"]),
		"owner_name": str(user.get("first_name") or user.get("username") or ""),
		"user_chat_id": str(raw.get("user_chat_id") or user["id"]),
		"rights": _rights(raw),
		"is_enabled": bool(raw.get("is_enabled", True)),
	}


def store_connection(conn: dict) -> None:
	_put(_conn_key(conn["id"]), conn, CONN_TTL)


def get_connection(connection_id: str, adapter: Any = None, gateway_name: str = "") -> dict | None:
	"""Stored connection, else one ``getBusinessConnection`` refresh (stored). None when unknown."""
	if not connection_id:
		return None
	conn = _get(_conn_key(connection_id))
	if conn or adapter is None:
		return conn or None
	try:
		raw = adapter.client.call("getBusinessConnection", {"business_connection_id": connection_id})
	except Exception:
		return None
	conn = connection_from_api(raw, gateway_name)
	if conn:
		store_connection(conn)
	return conn


def can(conn: dict | None, right: str) -> bool:
	return bool(conn and conn.get("is_enabled") and conn.get("rights", {}).get(right))


# -- policy --------------------------------------------------------------------------------------


@dataclass
class BusinessContext:
	gateway: Any
	adapter: Any
	parsed: Any
	connection: dict | None
	kind: str
	direction: str  # incoming | outgoing
	extra: dict = field(default_factory=dict)


_POLICY: Callable[[BusinessContext], str] = lambda ctx: DEFAULT_POLICY  # noqa: E731
_DRAFT_PRODUCER: Callable[[BusinessContext], str | None] | None = None
_OBSERVERS: list[Callable[[dict], None]] = []


def register_business_policy(fn: Callable[[BusinessContext], str]) -> None:
	"""``fn(ctx) -> ignore|observe|draft|reply``. Anything else is treated as ``observe``."""
	global _POLICY
	_POLICY = fn


def register_draft_producer(fn: Callable[[BusinessContext], str | None] | None) -> None:
	"""``fn(ctx) -> proposed reply text`` (the coordinator wires the agent run here)."""
	global _DRAFT_PRODUCER
	_DRAFT_PRODUCER = fn


def register_observer(fn: Callable[[dict], None]) -> None:
	_OBSERVERS.append(fn)


def resolve_policy(ctx: BusinessContext) -> tuple[str, str]:
	"""Returns ``(effective_policy, reason)``; unsafe requests are downgraded to observe."""
	try:
		wanted = _POLICY(ctx)
	except Exception:
		return DEFAULT_POLICY, "policy_error"
	if wanted not in POLICIES:
		return DEFAULT_POLICY, "invalid_policy"
	if wanted in ("draft", "reply"):
		if not can(ctx.connection, "can_reply"):
			return DEFAULT_POLICY, "no_reply_right"
		if wanted == "draft" and _DRAFT_PRODUCER is None:
			return DEFAULT_POLICY, "no_draft_producer"
	return wanted, ""


# -- observations --------------------------------------------------------------------------------


def record_observation(gateway_name: str, entry: dict) -> None:
	entry = dict(entry)
	if entry.get("text"):
		entry["text"] = str(entry["text"])[:TEXT_CAP]
	key = f"huf:tgbiz:obs:{gateway_name}"
	items = (_get(key) or [])[-(OBS_MAX - 1) :] + [entry]
	_put(key, items, CONN_TTL)
	frappe.logger("huf").info(
		f"Telegram business {gateway_name}: {entry.get('event')} conn={entry.get('connection_id')}"
	)
	for fn in _OBSERVERS:
		try:
			fn(entry)
		except Exception:
			pass


def observations(gateway_name: str) -> list[dict]:
	return _get(f"huf:tgbiz:obs:{gateway_name}") or []


# -- update handlers -----------------------------------------------------------------------------


def _ack(note: str, **extra: Any) -> dict:
	return {"success": True, "ignored": "business", "note": note, **extra}


def handle_business_connection(gateway, adapter, parsed, request=None) -> dict:
	conn = connection_from_api(parsed.raw.get("business_connection") or {}, gateway.name)
	if conn is None:
		return _ack("business_connection without id/owner; dropped")
	store_connection(conn)
	record_observation(
		gateway.name,
		{
			"event": "connection",
			"connection_id": conn["id"],
			"owner_id": conn["owner_id"],
			"enabled": conn["is_enabled"],
			"can_reply": can(conn, "can_reply"),
		},
	)
	return _ack("connection stored", connection_id=conn["id"], enabled=conn["is_enabled"])


def _direction(parsed, conn: dict | None) -> str:
	if conn:
		return "outgoing" if parsed.sender_id == conn["owner_id"] else "incoming"
	# Unknown owner: in a business chat chat.id is the customer, so anyone else is the owner.
	return "incoming" if parsed.sender_id == parsed.chat_id else "outgoing"


def handle_business_message(gateway, adapter, parsed, request=None) -> dict:
	conn = get_connection(parsed.business_connection_id, adapter, gateway.name)
	direction = _direction(parsed, conn)
	base = {
		"connection_id": parsed.business_connection_id,
		"chat_id": parsed.chat_id,
		"message_id": parsed.message_id,
		"sender_id": parsed.sender_id,
		"direction": direction,
		"text": parsed.text,
	}
	edited = parsed.kind == "edited_business_message"
	# Loop prevention: never act on the owner's own messages, bot-sent messages, or bot senders.
	if direction == "outgoing" or parsed.sender_business_bot or parsed.is_bot:
		record_observation(gateway.name, {**base, "event": "outgoing" if not edited else "outgoing_edit"})
		return _ack("own/bot message recorded; no reply", policy="ignore")
	if conn is None:
		record_observation(gateway.name, {**base, "event": "message", "note": "unknown_connection"})
		return _ack("unknown connection; observed only", policy="observe")
	if not conn["is_enabled"]:
		record_observation(gateway.name, {**base, "event": "message", "note": "connection_disabled"})
		return _ack("connection disabled; observed only", policy="observe")
	ctx = BusinessContext(gateway, adapter, parsed, conn, parsed.kind, direction)
	policy, reason = resolve_policy(ctx)
	if edited:  # edits never trigger a reply
		policy = policy if policy == "ignore" else "observe"
	if policy == "ignore":
		return _ack("policy ignore", policy="ignore")
	record_observation(
		gateway.name, {**base, "event": "edit" if edited else "message", "policy": policy, "note": reason}
	)
	if policy == "draft":
		text = None
		try:
			text = _DRAFT_PRODUCER(ctx)
		except Exception as exc:
			frappe.logger("huf").warning(f"Telegram business draft failed: {type(exc).__name__}")
		if text is DRAFT_QUEUED:
			return _ack("draft queued", policy="draft", draft_queued=True)
		if text:
			draft_id = deliver_draft(
				adapter, conn, parsed.chat_id, parsed.message_id, text, parsed.display_name
			)
			return _ack("draft sent to owner", policy="draft", draft_id=draft_id)
		return _ack("no draft produced", policy="observe")
	if policy == "reply":
		return _ack(
			"auto-reply requires the agent-run trigger (coordinator)", policy="reply", needs_agent_run=True
		)
	return _ack("observed", policy="observe")


def handle_deleted_business_messages(gateway, adapter, parsed, request=None) -> dict:
	raw = parsed.raw.get("deleted_business_messages") or {}
	record_observation(
		gateway.name,
		{
			"event": "deleted",
			"connection_id": str(raw.get("business_connection_id") or ""),
			"chat_id": parsed.chat_id,
			"message_ids": list(raw.get("message_ids") or [])[:100],
		},
	)
	return _ack("deletion recorded")


# -- sending as the business account --------------------------------------------------------------


def _client(sender: Any):
	return getattr(sender, "client", sender)


def reply_as_business(
	connection_id: str, chat_id: Any, text: str, *, sender: Any, reply_to: Any = None
) -> list[Any]:
	"""sendMessage with ``business_connection_id`` (AS the owner). Needs an enabled connection with can_reply."""
	conn = get_connection(connection_id)
	if conn is None:
		raise BusinessReplyBlocked("unknown_connection")
	if not conn["is_enabled"]:
		raise BusinessReplyBlocked("connection_disabled")
	if not can(conn, "can_reply"):
		raise BusinessReplyBlocked("no_reply_right")
	text = (text or "").strip()
	if not text:
		raise ValueError("Reply text is required")
	results = []
	for i in range(0, len(text), 4096):
		payload: dict[str, Any] = {
			"business_connection_id": connection_id,
			"chat_id": chat_id,
			"text": text[i : i + 4096],
		}
		if i == 0 and reply_to not in (None, ""):
			payload["reply_parameters"] = {"message_id": int(reply_to), "allow_sending_without_reply": True}
		results.append(_client(sender).call("sendMessage", payload))
	return results


def mark_read(connection_id: str, chat_id: Any, message_id: Any, *, sender: Any) -> Any:
	if not can(get_connection(connection_id), "can_read_messages"):
		raise BusinessReplyBlocked("no_read_right")
	return _client(sender).call(
		"readBusinessMessage",
		{"business_connection_id": connection_id, "chat_id": chat_id, "message_id": int(message_id)},
	)


def delete_messages(connection_id: str, message_ids: list[int], *, sender: Any, own_only: bool = True) -> Any:
	conn = get_connection(connection_id)
	right = "can_delete_sent_messages" if own_only else "can_delete_all_messages"
	if not (can(conn, right) or can(conn, "can_delete_all_messages")):
		raise BusinessReplyBlocked("no_delete_right")
	ids = [int(i) for i in message_ids][:100]
	return _client(sender).call(
		"deleteBusinessMessages", {"business_connection_id": connection_id, "message_ids": ids}
	)


# -- draft -> approve plumbing --------------------------------------------------------------------


def _draft_key(draft_id: str) -> str:
	return f"huf:tgbiz:draft:{draft_id}"


def deliver_draft(adapter, conn: dict, chat_id: str, message_id: str, text: str, who: str = "") -> str:
	"""Store the proposed reply and send it to the OWNER with approve / edit / reject buttons."""
	draft_id = secrets.token_hex(5)
	_put(
		_draft_key(draft_id),
		{
			"id": draft_id,
			"connection_id": conn["id"],
			"owner_id": conn["owner_id"],
			"chat_id": str(chat_id),
			"message_id": str(message_id),
			"text": text,
			"status": "pending",
			"who": who or str(chat_id),
			"owner_chat": str(conn["user_chat_id"]),
			"owner_msg_id": "",
		},
		DRAFT_TTL,
	)
	owner_chat = conn["user_chat_id"]

	def button(label: str, action: str):
		return kb.callback_button(
			label, adapter.sign_callback_data(f"{CALLBACK_PREFIX}:{action}:{draft_id}", owner_chat)
		)

	markup = kb.inline_keyboard([[button("Approve", "a"), button("Edit", "e"), button("Reject", "r")]])
	header = f"Draft reply to {who or chat_id}:\n\n"
	sent = adapter.sender.send_text(owner_chat, header + text, markup=markup)
	try:
		draft = get_draft(draft_id)
		draft["owner_msg_id"] = str((sent[0] or {}).get("message_id") or "")
		_put(_draft_key(draft_id), draft, DRAFT_TTL)
	except Exception:
		pass
	return draft_id


def get_draft(draft_id: str) -> dict | None:
	return _get(_draft_key(draft_id))


def _finish(draft: dict, status: str) -> None:
	draft["status"] = status
	_put(_draft_key(draft["id"]), draft, DRAFT_TTL)


_REASONS = {
	"unknown_connection": "the business connection is no longer available",
	"connection_disabled": "the business connection is turned off",
	"no_reply_right": "the account no longer allows the bot to reply",
}


def classify_send_error(exc: Exception) -> tuple[str, str]:
	"""``(kind, plain_reason)``; kind is ``transient`` | ``rights`` | ``permanent``. Never includes secrets."""
	if isinstance(exc, BusinessReplyBlocked):
		return "rights", _REASONS.get(exc.reason, "the bot is not allowed to reply for this account")
	desc = str(getattr(exc, "description", "") or "").lower()
	if hasattr(exc, "retryable"):
		if "rights" in desc or "permission" in desc:
			return "rights", "the bot does not have the rights to reply for this account"
		if getattr(exc, "flood_control", False):
			return "transient", "Telegram is rate limiting requests, try again shortly"
		if exc.retryable:
			return "transient", "Telegram had a temporary problem"
		if "connection" in desc and "not found" in desc:
			return "permanent", "the business connection was not found"
		if getattr(exc, "blocked_by_user", False) or getattr(exc, "chat_not_found", False):
			return "permanent", "the customer chat is unavailable"
		return "permanent", "Telegram refused the message"
	return "transient", "an unexpected error occurred"


def _notify_owner(adapter, chat_id: Any, text: str) -> None:
	try:
		adapter.sender.send_text(chat_id, text)
	except Exception:
		pass


def _answer(adapter, parsed, text: str) -> None:
	cqid = getattr(parsed, "callback_query_id", "")
	if not cqid:
		return
	try:
		adapter.answer_callback(cqid, text)
	except Exception:
		pass


def _close_draft_message(adapter, draft: dict, outcome: str, parsed=None) -> None:
	"""Replace the draft's buttons with the outcome line (best effort)."""
	chat = draft.get("owner_chat") or draft.get("owner_id")
	msg_id = draft.get("owner_msg_id") or getattr(parsed, "message_id", "")
	if not chat or not msg_id:
		return
	body = f"Draft reply to {draft.get('who') or draft.get('chat_id')}:\n\n{draft['text']}\n\n{outcome}"
	try:
		adapter.sender.edit_message_text(chat, msg_id, body, markup={"inline_keyboard": []})
	except Exception:
		try:
			adapter.sender.edit_message_reply_markup(chat, msg_id, None)
		except Exception:
			pass


_TOASTS = {
	"approved": "Sent",
	"rejected": "Rejected",
	"editing": "Send your replacement text",
	"stale": "This draft was already handled",
	"forbidden": "Only the account owner can do this",
	"blocked": "Could not send",
	"retry": "Could not send, tap Approve to retry",
	"failed": "Could not send",
}
_OUTCOMES = {"approved": "Sent.", "rejected": "Rejected."}


def handle_draft_callback(adapter, parsed, payload: str | None) -> dict | None:
	"""Handle a verified ``bz:<a|e|r>:<draft_id>`` callback. None = not a business-draft callback.

	Returns ``{"handled": True, "result": approved|rejected|editing|stale|forbidden|blocked|retry|failed}``.
	Always answers the callback query and never raises (the webhook must ack 200).
	"""
	if not payload or not payload.startswith(CALLBACK_PREFIX + ":"):
		return None
	try:
		out = _draft_callback(adapter, parsed, payload)
	except Exception as exc:  # last resort: never 500 the webhook
		frappe.logger("huf").warning(f"Telegram business draft callback failed: {type(exc).__name__}")
		out = {"result": "failed", "reason": "an unexpected error occurred"}
	result = out.get("result", "stale")
	toast = out.get("toast") or _TOASTS.get(result, "")
	if result in ("blocked", "retry", "failed") and out.get("reason") and not out.get("toast"):
		toast = f"Could not send: {out['reason']}"
	_answer(adapter, parsed, toast)
	return {"handled": True, **{k: v for k, v in out.items() if k != "toast"}}


def _draft_callback(adapter, parsed, payload: str) -> dict:
	parts = payload.split(":")
	if len(parts) != 3:
		return {"result": "stale"}
	action, draft_id = parts[1], parts[2]
	draft = get_draft(draft_id)
	if not draft:
		return {"result": "stale"}
	if str(parsed.sender_id) != draft["owner_id"]:
		return {"result": "forbidden"}
	if draft["status"] == "failed":
		return {
			"result": "failed",
			"reason": "this draft failed and can't be retried",
			"toast": "This draft failed to send and can't be retried",
		}
	if draft["status"] not in ("pending", "editing"):
		return {"result": "stale"}
	if action == "r":
		_finish(draft, "rejected")
		_close_draft_message(adapter, draft, _OUTCOMES["rejected"], parsed)
		return {"result": "rejected"}
	if action == "e":
		_finish(draft, "editing")
		return {"result": "editing", "draft_id": draft_id}
	if action == "a":
		out = _send_draft(adapter, draft, draft["text"], restore="pending", parsed=parsed)
		if out["result"] == "approved":
			_close_draft_message(adapter, draft, _OUTCOMES["approved"], parsed)
		elif out["result"] == "failed":
			_close_draft_message(adapter, draft, "Could not be sent.", parsed)
		return out
	return {"result": "stale"}


def submit_edit(adapter, draft_id: str, owner_id: Any, new_text: str) -> dict:
	"""The owner's replacement text for a draft in the ``editing`` state; sends it as the owner."""
	draft = get_draft(draft_id)
	if not draft or draft["status"] != "editing":
		return {"result": "stale"}
	if str(owner_id) != draft["owner_id"]:
		return {"result": "forbidden"}
	out = _send_draft(adapter, draft, new_text, restore="editing")
	if out["result"] == "approved":
		draft["text"] = new_text
		_close_draft_message(adapter, draft, _OUTCOMES["approved"])
	elif out["result"] == "failed":
		_close_draft_message(adapter, draft, "Could not be sent.")
	return out


def _send_draft(adapter, draft: dict, text: str, restore: str = "pending", parsed=None) -> dict:
	"""Send as the owner. Never raises: failures reset the draft (``restore``) or mark it ``failed``."""
	_finish(draft, "sending")  # claim first: a double tap must not send twice
	try:
		reply_as_business(
			draft["connection_id"],
			draft["chat_id"],
			text,
			sender=adapter.sender,
			reply_to=draft["message_id"],
		)
	except Exception as exc:
		kind, reason = classify_send_error(exc)
		frappe.logger("huf").warning(f"Telegram business draft send failed ({type(exc).__name__}, {kind})")
		blocked = isinstance(exc, BusinessReplyBlocked)
		if kind == "permanent":
			_finish(draft, "failed")
			result, note = "failed", "This draft can't be retried."
		else:
			_finish(draft, restore)
			result = "blocked" if blocked else "retry"
			note = (
				"Send your replacement text again to retry."
				if restore == "editing"
				else "Tap Approve to retry."
			)
		_notify_owner(
			adapter, draft.get("owner_chat") or draft["owner_id"], f"Could not send: {reason}. {note}"
		)
		out = {"result": result, "reason": reason}
		if blocked:
			out["reason_code"] = exc.reason
		return out
	_finish(draft, "sent")
	return {"result": "approved"}
