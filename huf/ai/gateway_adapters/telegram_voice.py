# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram voice replies (R7): voice note in -> transcript -> agent -> ``sendVoice`` out.

Reuses the provider-neutral pieces of ``whatsapp_voice_reply`` (markdown stripping, TTS with the agent's
own model, event claim, the mode field) and the neutral ffmpeg Ogg/Opus conversion in
``whatsapp_send_file``; nothing there changes. Every failure returns ``None`` after a logged warning so
the caller falls back to the text reply: a reply is never lost.

Inbound voice/audio/video_note needs no Telegram-specific hook: ``save_media`` stores the file and
``media_prep.prepare_media_for_agent`` (provider-neutral, run by ``gateway_service``) transcribes it.
"""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai import whatsapp_send_file as send_file
from huf.ai import whatsapp_voice_reply as wv

VOICE_ONLY = wv.VOICE_ONLY
TEXT_AND_VOICE = wv.TEXT_AND_VOICE
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # Bot API upload limit
VOICE_KINDS = ("voice", "video_note", "audio")
OGG_FILENAME = "reply.ogg"
TTS_FORMAT = "opus"


def _warn(message: str) -> None:
	frappe.logger("huf").warning(f"Telegram voice reply: {message}")


# ------------------------------------------------------------------ decisions
def is_voice_input(event) -> bool:
	"""The inbound Telegram message was a voice note, audio file or video note."""
	from huf.ai.gateway_adapters.telegram_ingest import _message, _raw

	message = _message(_raw(event))
	return any(isinstance(message.get(k), dict) and message[k].get("file_id") for k in VOICE_KINDS)


def reply_mode(event, gateway, response: str) -> str:
	"""``VOICE_ONLY`` / ``TEXT_AND_VOICE`` when this reply should also be a voice note, else ``""``."""
	if getattr(gateway, "provider", "") != "Telegram":
		return ""
	mode = wv._MODES.get(str(getattr(gateway, wv.MODE_FIELD, "") or ""), "")
	if not mode or not is_voice_input(event):
		return ""
	text = wv.plain_text(response)
	if not text or len(text) > wv.MAX_TTS_CHARS:
		return ""
	return mode


# ------------------------------------------------------------------ seams (mocked in tests)
def _adapter(gateway, event):
	return wv._adapter(gateway, event)


def _claim(event) -> bool:
	return wv._claim(event)


def _synthesize(agent_name: str, text: str, conversation_id, run_id, voice: str | None = None) -> bytes:
	# Ask the TTS provider for Ogg/Opus directly (OpenAI ``response_format='opus'``) to skip ffmpeg.
	return wv._synthesize(agent_name, text, conversation_id, run_id, response_format=TTS_FORMAT, voice=voice)


def is_ogg_opus(content: bytes) -> bool:
	"""True when ``content`` is already an Ogg container carrying an Opus stream (Telegram's voice format)."""
	return bytes(content[:4]) == b"OggS" and b"OpusHead" in bytes(content[:512])


def _convert(content: bytes) -> bytes:
	if is_ogg_opus(content):
		return content
	return send_file.to_ogg_opus(content)


def _conversation(run_id):
	return wv._conversation(run_id)


def speech_upload(run_id, text: str, voice: str | None = None) -> tuple:
	"""Synthesize ``text`` with the run's agent TTS; returns the ``(filename, ogg_opus, mime)`` upload tuple.

	Used by the telegram tool's ``send_speech``. Raises ``ValueError`` / ``FileSendError`` with a message
	the agent can read (no TTS model/provider, ffmpeg or provider failure, empty or oversized audio).
	"""
	agent = frappe.db.get_value("Agent Run", run_id, "agent") if run_id else None
	if not agent:
		raise ValueError("send_speech needs an agent run to pick the agent's TTS model")
	conversation = _conversation(run_id)
	if not conversation:
		raise ValueError("the agent run has no conversation to attach the audio to")
	ogg = _convert(_synthesize(agent, wv.plain_text(text), conversation, run_id, voice=voice))
	if not ogg or len(ogg) > MAX_UPLOAD_BYTES:
		raise ValueError("the converted voice note is empty or over the 50MB Bot API limit")
	return (OGG_FILENAME, ogg, send_file.OGG_OPUS_MIME)


# ------------------------------------------------------------------ send
def send_voice_reply(event, gateway, response: str, *, quote: bool = True, once: bool = False) -> str | None:
	"""Send ``response`` as a Telegram voice note; returns the message id, or ``None`` (never raises)."""
	try:
		if once and not _claim(event):
			return None
		from huf.ai.gateway_adapters import telegram_messages, telegram_pipeline as tp

		text = wv.plain_text(response)
		run_id = getattr(event, "agent_run", None)
		conversation = _conversation(run_id)
		if not conversation:
			raise ValueError("the agent run has no conversation to attach the audio to")
		adapter = _adapter(gateway, event)
		thread_id, reply_to = tp.reply_target(event)
		adapter.send_typing(event.conversation_id, "upload_voice", thread_id)
		ogg = _convert(_synthesize(event.target_agent, text, conversation, run_id))
		if not ogg or len(ogg) > MAX_UPLOAD_BYTES:
			raise ValueError("the converted voice note is empty or over the 50MB Bot API limit")
		msgs = adapter.sender.send_voice(
			event.conversation_id, (OGG_FILENAME, ogg, send_file.OGG_OPUS_MIME),
			reply_to=reply_to if quote else None, thread_id=thread_id,
		)
		ids = [m.get("message_id") for m in msgs if isinstance(m, dict) and m.get("message_id") is not None]
		if not ids:
			raise ValueError("sendVoice returned no message id")
		telegram_messages.record_sent(gateway.name, event.conversation_id, event.name, ids, kind="voice")
		return str(ids[0])
	except send_file.FileSendError as exc:
		_warn(f"{exc.code}: {exc.message} (event {getattr(event, 'name', '')}); falling back to text")
	except Exception as exc:
		_warn(f"{type(exc).__name__}: {str(exc)[:200]} (event {getattr(event, 'name', '')}); falling back to text")
	return None


def voice_only_sent(event, gateway, response: str) -> bool:
	"""Voice-only path: throttle, send, remember the reply id. ``True`` when the reply went out."""
	from huf.ai import gateway_service as svc

	svc._throttle_outbound_send(gateway.name, svc._outbound_rate_cap(gateway.provider))
	message_id = send_voice_reply(event, gateway, response)
	svc._record_reply_sent(event, message_id)
	return bool(message_id)


def deliver(event, gateway, response: str, send_text: Any) -> dict | None:
	"""Voice orchestration for ``_send_telegram_reply``.

	Returns the final result when voice-only delivered; otherwise sends text via ``send_text()`` (and,
	for text and voice, a companion voice note once) and returns that result.
	"""
	from huf.ai import gateway_service as svc

	mode = reply_mode(event, gateway, response)
	if mode == VOICE_ONLY and (event.reply_message_id or voice_only_sent(event, gateway, response)):
		return svc._finish_voice_only(event, gateway)
	result = send_text()
	if mode == TEXT_AND_VOICE and result.get("status") == "Succeeded":
		send_voice_reply(event, gateway, response, quote=False, once=True)
	return result
