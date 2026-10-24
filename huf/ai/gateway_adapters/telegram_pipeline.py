# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram reply pipeline: format, split, send parts idempotently, classify failures.

Mirrors the WhatsApp pipeline in ``gateway_service`` (``_attempt_reply_parts`` /
``_handle_reply_send_failure``) but is reached through provider hooks. ``parts`` are source-markdown
chunks (<= 4096) so a retry can re-render exactly the unsent remainder; rendering to Telegram HTML
(with a one-shot plain fallback on parse errors) happens in ``TelegramSender``.

Extension points for later work packages (all no-ops here): ``reply_markup_for`` (buttons, WP-5),
``before_send`` (voice / media / streaming finalize, WP-4/6/7).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from huf.ai.gateway_adapters import telegram_blocks as blocks
from huf.ai.gateway_adapters import telegram_messages
from huf.ai.gateway_adapters.telegram_client import TelegramApiError
from huf.ai.gateway_adapters.telegram_format import MODE_HTML, split_message
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender

BACKOFF_BASE_SECONDS = 5.0
BACKOFF_MAX_SECONDS = 300.0
OPT_OUT_NOTE = "Recipient blocked the bot: reply not sent"


class TelegramPartsError(Exception):
	"""A multi-part reply stopped part-way: ``sent_ids`` went out, ``remaining`` parts did not."""

	def __init__(self, cause: BaseException, sent_ids: list, remaining: list[str]):
		super().__init__(str(cause))
		self.cause = cause
		self.sent_ids = list(sent_ids)
		self.remaining = list(remaining)


# -- extension points ---------------------------------------------------------------------------


def reply_markup_for(event: Any, gateway: Any, response_text: str) -> dict | None:
	"""Inline/reply keyboard for the last part (agent ``telegram-buttons`` block); None = no keyboard."""
	from huf.ai.gateway_adapters import telegram_buttons

	return telegram_buttons.markup_for(event, gateway, response_text)


def before_send(event: Any, gateway: Any, parts: list[str]) -> list[str]:
	"""Hook to adjust/replace parts before sending (media, voice, streaming finalize)."""
	from huf.ai.gateway_adapters import telegram_stream

	return telegram_stream.before_send(event, gateway, parts)


# -- pure helpers -------------------------------------------------------------------------------


def make_parts(response: str, scope: str = "") -> list[str]:
	"""Split the agent reply into parts; strip and remember its ``telegram-media`` / ``telegram-buttons`` blocks.

	Nothing is dropped silently: every block problem is recorded (operator log, Gateway Event note and the
	agent's next-run feedback, see ``telegram_blocks.record``), and a reply that would otherwise be empty
	becomes a short plain text naming the problem."""
	from huf.ai.gateway_adapters import telegram_buttons
	from huf.ai.gateway_adapters import telegram_media_reply as media_reply

	visible, found = blocks.scan(response)
	media_items, media_errors = media_reply.parse(found.get(blocks.MEDIA, []))
	spec, button_errors = telegram_buttons.parse(found.get(blocks.BUTTONS, []))
	errors = [f"media: {e}" for e in media_errors] + [f"buttons: {e}" for e in button_errors]
	blocks.record(scope, errors)
	if spec is not None:
		visible = visible or telegram_buttons.PLACEHOLDER_TEXT
		telegram_buttons.remember_spec(visible, spec, scope=scope)
	if not (visible or media_items) and errors:
		visible = blocks.problem_text(errors)
	visible = media_reply.remember(visible, media_items, scope=scope)
	return split_message(visible) or ([str(visible)] if str(visible or "").strip() else [])


def reply_scope(gateway: Any, event: Any) -> str:
	return blocks.scope_key(
		getattr(gateway, "name", ""), getattr(event, "conversation_id", ""), getattr(event, "name", "")
	)


def spoken_text(response: str) -> str:
	"""Reply text with the agent's ```telegram-media``` and ```telegram-buttons``` blocks removed (for TTS)."""
	return blocks.strip(response)


def forum_thread_id(event: Any) -> str | None:
	"""Forum topic id from the stored update (``thread_id`` on the event is the inbound message id)."""
	raw = getattr(event, "raw_payload", None)
	if not isinstance(raw, dict):
		return None
	from huf.ai.gateway_adapters.telegram_threads import thread_id_for_reply

	for key in ("message", "edited_message", "business_message", "channel_post"):
		msg = raw.get(key)
		if isinstance(msg, dict):
			return thread_id_for_reply(msg)
	cb = raw.get("callback_query")
	if isinstance(cb, dict) and isinstance(cb.get("message"), dict):
		return thread_id_for_reply(cb["message"])
	return None


def reply_target(event: Any) -> tuple[str | None, str | None]:
	"""(forum thread id, inbound message id to reply to)."""
	return forum_thread_id(event), (getattr(event, "thread_id", None) or None)


def ephemeral_for(event: Any) -> dict | None:
	"""Ephemeral reply params when the inbound was an ephemeral group command, else None."""
	from huf.ai.gateway_adapters.telegram_ephemeral import ephemeral_params

	return ephemeral_params(getattr(event, "raw_payload", None)) or None


def classify(exc: BaseException) -> dict:
	"""Classify a send error: ``retryable``, ``delay`` (None = default backoff), ``blocked``, ``code``, ``operator_text``."""
	cause = exc.cause if isinstance(exc, TelegramPartsError) else exc
	if isinstance(cause, TelegramApiError):
		from huf.ai.gateway_adapters.telegram_hooks import error_text

		out = {
			"retryable": cause.retryable,
			"delay": None,
			"blocked": cause.blocked_by_user,
			"code": "blocked"
			if cause.blocked_by_user
			else (
				"chat_not_found"
				if cause.chat_not_found
				else ("rate_limited" if cause.flood_control else "telegram_error")
			),
			"operator_text": error_text(cause),
		}
		if cause.flood_control and cause.retry_after:
			out["delay"] = float(cause.retry_after) + 1.0
		return out
	transient = isinstance(cause, (ConnectionError, TimeoutError, OSError))
	return {
		"retryable": transient,
		"delay": None,
		"blocked": False,
		"code": "network" if transient else "error",
		"operator_text": str(cause) or "Telegram delivery failed",
	}


def backoff_seconds(cls: dict, attempt: int) -> float:
	if cls.get("delay") is not None:
		return min(float(cls["delay"]), BACKOFF_MAX_SECONDS)
	return min(BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)), BACKOFF_MAX_SECONDS)


def build_sender(adapter: Any) -> TelegramSender:
	return TelegramSender(adapter.client, parse_mode=MODE_HTML)


def send_parts_with(
	sender: TelegramSender,
	chat_id: Any,
	parts: list[str],
	*,
	thread_id: Any = None,
	reply_to: Any = None,
	markup: dict | None = None,
	on_sent: Any = None,
	media: bool = False,
	ephemeral: dict | None = None,
	on_part: Any = None,
	scope: str = "",
) -> SimpleNamespace:
	"""Send ``parts`` in order. Raises ``TelegramPartsError(cause, sent_ids, remaining)`` on failure.

	``reply_to`` quotes the inbound message on the first part only; ``markup`` goes on the last part.
	``on_sent(ids)`` is called after each part succeeds. ``media=True`` first sends the agent's
	``telegram-media`` items (never raises; a failure appends a short note part, the text still goes out).
	"""
	sent: list = []
	parts = list(parts)
	if ephemeral:  # media cannot be sent ephemerally: drop it (text still goes out privately)
		from huf.ai.gateway_adapters import telegram_media_reply as media_reply

		parts = [p for p in parts if not media_reply.is_media_only(p)]
		media = False
	if media:
		parts = _send_media_first(sender, chat_id, parts, thread_id, reply_to, sent, on_sent, scope)
		if not parts:
			return SimpleNamespace(
				provider_message_id=str(sent[0]) if sent else "", provider_response={"message_ids": sent}
			)
		reply_to = None if sent else reply_to
	# the keyboard belongs on the final real text part, never on a trailing "could not send" note
	real = [i for i, p in enumerate(parts) if not blocks.is_note(p)]
	markup_at = real[-1] if real else len(parts) - 1
	for i, part in enumerate(parts):
		try:
			msgs = sender.send_text(
				chat_id,
				part,
				reply_to=reply_to if i == 0 else None,
				thread_id=thread_id,
				markup=markup if i == markup_at else None,
				**({"ephemeral": ephemeral} if ephemeral else {}),
			)
		except Exception as exc:
			raise TelegramPartsError(exc, sent, list(parts[i:])) from exc
		ids = [m.get("message_id") for m in msgs if isinstance(m, dict) and m.get("message_id") is not None]
		sent.extend(ids)
		if on_sent and ids:
			on_sent(ids)
		if on_part and ids:
			on_part(ids, "text", part)
	return SimpleNamespace(
		provider_message_id=str(sent[0]) if sent else "", provider_response={"message_ids": sent}
	)


def _send_media_first(
	sender, chat_id, parts, thread_id, reply_to, sent, on_sent, scope: str = ""
) -> list[str]:
	"""Send remembered media items; returns the text parts still to send (placeholder dropped, note added)."""
	from huf.ai.gateway_adapters import telegram_media_reply as media_reply

	try:
		items = media_reply.take_items(parts, scope=scope)
		result = media_reply.send_media_items(sender, chat_id, items, thread_id, reply_to) if items else None
	except Exception as exc:
		items, result = [], SimpleNamespace(sent_ids=[], errors=[str(exc)[:120]])
	parts = [p for p in parts if not media_reply.is_media_only(p)]
	if result is None:
		return parts
	sent.extend(result.sent_ids)
	if on_sent and result.sent_ids:
		on_sent(list(result.sent_ids))
	if result.errors:
		blocks.record(scope, [f"media not sent: {e}" for e in result.errors])
		parts.append(media_reply.failure_note(result.errors))
	return parts


DUPLICATE_NOTE = "Final reply suppressed: the telegram tool already replied in this chat"


def duplicates_tool_reply(tool_texts: list, final_text: str) -> bool:
	"""True when the telegram tool already delivered to this chat in the run: the final plain reply is skipped."""
	return bool(tool_texts) and bool(str(final_text or "").strip())


# -- frappe-bound ---------------------------------------------------------------------------------


def _svc():
	from huf.ai import gateway_service

	return gateway_service


def send_parts(gateway: Any, event: Any, parts: list[str], quote: bool) -> SimpleNamespace:
	"""``send_parts`` hook: real adapter send for an event."""
	from huf.ai.gateway_webhook import event_contact_name, get_gateway_adapter

	adapter = get_gateway_adapter(gateway, event_contact_name(event))
	thread_id, reply_to = reply_target(event)
	sender = build_sender(adapter)
	markup = reply_markup_for(event, gateway, "\n\n".join(parts))
	from huf.ai.gateway_adapters import telegram_buttons

	edited = (
		None
		if any(p.startswith("\u2063tg-media:") for p in parts)
		else telegram_buttons.try_edit(sender, event, list(parts), markup)
	)
	scope = reply_scope(gateway, event)
	if edited is not None:
		blocks.attach_to_event(event, scope)
		return edited
	delivery = send_parts_with(
		sender,
		event.conversation_id,
		list(parts),
		thread_id=thread_id,
		reply_to=reply_to if quote else None,
		markup=markup,
		on_sent=lambda ids: telegram_messages.record_sent(
			gateway.name, event.conversation_id, event.name, ids
		),
		on_part=lambda ids, kind, text: telegram_messages.record_outbound(
			gateway.name, event.conversation_id, ids, kind=kind, text=text
		),
		media=True,
		ephemeral=ephemeral_for(event),
		scope=scope,
	)
	blocks.attach_to_event(event, scope)  # block problems noted on the Gateway Event (delivery_error)
	return delivery


def send_typing(gateway: Any, event: Any) -> bool:
	"""Best-effort ``sendChatAction typing``; never raises. Delegates to the single owner, telegram_ingest."""
	try:
		from huf.ai.gateway_adapters import telegram_ingest

		return telegram_ingest.send_typing_for_event(event, gateway)
	except Exception:
		return False


def attempt_parts(event: Any, gateway: Any, parts: list[str], attempt: int) -> dict:
	import frappe

	svc = _svc()
	from huf.ai.gateway_webhook import touch_last_event

	parts = before_send(event, gateway, list(parts))
	try:
		svc._throttle_outbound_send(gateway.name, svc._outbound_rate_cap(gateway.provider))
		delivery = send_parts(gateway, event, parts, not event.reply_message_id)
	except Exception as exc:
		return handle_failure(event, gateway, exc, parts, attempt)
	if not event.reply_message_id:
		svc._record_reply_sent(event, delivery.provider_message_id)
	elif frappe.db.get_value("Gateway Event", event.name, "reply_status") == "retrying":
		event.db_set("reply_status", "sent", update_modified=False)
	final = {"status": "Succeeded"}
	if attempt > 1:
		final["delivery_error"] = ""
	event.db_set(final)
	svc._commit_unless_testing()  # make the terminal state durable before the contended Gateway stamp
	touch_last_event(gateway)
	return {
		"event_name": event.name,
		"status": "Succeeded",
		"agent_run_id": event.agent_run,
		"provider_message_id": delivery.provider_message_id,
		"attempts": attempt,
	}


def handle_failure(event: Any, gateway: Any, exc: BaseException, parts: list[str], attempt: int) -> dict:
	import frappe

	svc = _svc()
	cls = classify(exc)
	remaining = parts
	if isinstance(exc, TelegramPartsError):
		remaining = exc.remaining
		if exc.sent_ids and not event.reply_message_id:
			svc._record_reply_sent(event, exc.sent_ids[0])
	operator_text = cls["operator_text"]
	max_attempts = svc._reply_max_attempts(gateway)

	if cls["blocked"]:
		# The user blocked the bot: mark the sender unsendable (opt-out entry) and dead-letter, no retry.
		try:
			if str(event.conversation_id or "").startswith("-"):  # group/channel: the bot was removed
				svc._record_room_opt_out(gateway, event.conversation_id)
			elif event.sender_id:
				svc._record_opt_out(gateway, event.sender_id)
		except Exception:
			pass
	elif remaining and cls["retryable"] and attempt < max_attempts:
		delay = backoff_seconds(cls, attempt)
		try:
			event.db_set(
				{
					"status": "Running",
					"reply_status": "retrying",
					"delivery_error": f"retrying ({attempt}/{max_attempts}) in {delay:.0f}s: {operator_text}"[
						:500
					],
				}
			)
			frappe.enqueue(
				"huf.ai.gateway_service.retry_gateway_reply",
				queue="default",
				timeout=300,
				enqueue_after_commit=True,
				event_name=event.name,
				parts_remaining=list(remaining),
				attempt=attempt + 1,
				not_before=time.time() + delay,
			)
			return {
				"event_name": event.name,
				"status": "Running",
				"reply_status": "retrying",
				"retry_in_seconds": delay,
				"attempt": attempt,
				"agent_run_id": event.agent_run,
			}
		except Exception:
			frappe.logger("huf").warning("Telegram reply retry could not be scheduled")

	cause = exc.cause if isinstance(exc, TelegramPartsError) else exc
	error_text = svc._redact_error_text(str(cause)) or operator_text
	delivery_error = (
		f"gave up after {attempt} attempts: {operator_text}" if cls["retryable"] else operator_text
	)
	event.db_set(
		{
			"status": "Failed",
			"reply_status": "sent" if event.reply_message_id else "failed",
			"error_message": error_text[-500:],
			"delivery_error": delivery_error[:500],
		}
	)
	frappe.log_error(f"{delivery_error}\n{error_text}", "Gateway Telegram delivery failed")
	try:
		from huf.ai.gateway_webhook import _set_gateway_error

		_set_gateway_error(gateway.name, f"Reply to {event.name} failed: {delivery_error}")
	except Exception:
		pass
	return {
		"event_name": event.name,
		"status": "Failed",
		"error": error_text,
		"error_code": cls["code"],
		"agent_run_id": event.agent_run,
		"attempts": attempt,
	}
