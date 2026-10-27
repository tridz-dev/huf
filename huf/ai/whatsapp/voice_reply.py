# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Voice note replies for WhatsApp gateways (MM-E): voice in -> transcript -> agent -> voice note out.

When the inbound message is a voice note and the Gateway's ``voice_reply_mode`` asks for it, the agent's
text reply is turned into speech (the agent's own TTS model and provider key), converted to Ogg/Opus
(ffmpeg) and sent as a voice note through the adapter, which applies the 24h window and the outbound
policy (STOP / BSUID). Every failure returns ``None``/``False`` after a logged warning so the caller
falls back to the normal text reply: a reply is never lost.

Idempotency: a voice-only reply records ``reply_message_id`` (the caller skips the send when it is set);
a companion voice note (text and voice) is claimed once per event, so a replay cannot send it twice.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import frappe

from huf.ai.whatsapp import send_file as send_file

MODE_FIELD = "voice_reply_mode"
VOICE_ONLY = "voice_only"
TEXT_AND_VOICE = "text_and_voice"
_MODES = {"Voice only": VOICE_ONLY, "Text and voice": TEXT_AND_VOICE}
MAX_TTS_CHARS = 1500
_CLAIM_SECONDS = 7 * 24 * 3600


def _warn(message: str) -> None:
	frappe.logger("huf").warning(f"WhatsApp voice reply: {message}")


# ------------------------------------------------------------------ decisions
def is_voice_note(event) -> bool:
	"""The inbound WhatsApp message was a voice note (audio with ``voice: true``)."""
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return False
	message = raw.get("message") if isinstance(raw, dict) else None
	audio = message.get("audio") if isinstance(message, dict) else None
	return bool(isinstance(audio, dict) and audio.get("voice") is True)


def plain_text(text: str) -> str:
	"""The reply without markdown, as it should be spoken."""
	text = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), str(text or ""), flags=re.S)
	text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
	text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
	text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
	text = re.sub(r"(\*\*|__|~~|[*_`])", "", text)
	return re.sub(r"\n{3,}", "\n\n", text).strip()


def reply_mode(event, gateway, response: str) -> str:
	"""``VOICE_ONLY`` / ``TEXT_AND_VOICE`` when this reply should also be a voice note, else ``""``."""
	if getattr(gateway, "provider", "") != "WhatsApp":
		return ""
	mode = _MODES.get(str(getattr(gateway, MODE_FIELD, "") or ""), "")
	if not mode or not is_voice_note(event):
		return ""
	text = plain_text(response)
	if not text or len(text) > MAX_TTS_CHARS:
		return ""
	return mode


# ------------------------------------------------------------------ seams (mocked in tests)
def _adapter(gateway, event):
	from huf.ai.gateway_webhook import event_contact_name, get_gateway_adapter

	return get_gateway_adapter(gateway, event_contact_name(event))


def _claim(event) -> bool:
	return bool(frappe.cache().set(f"huf_gw_voice_reply:{event.name}", 1, ex=_CLAIM_SECONDS, nx=True))


def _run_coro(coro):
	"""Run ``coro`` to completion from sync code, also when a loop is already running on this thread
	(the agent tool path): then it runs on a worker thread that keeps the caller's context (frappe.local)."""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(coro)
	import concurrent.futures
	import contextvars

	ctx = contextvars.copy_context()
	with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
		return pool.submit(ctx.run, asyncio.run, coro).result()


def _synthesize(
	agent_name: str, text: str, conversation_id: str | None, run_id: str | None, response_format: str = "mp3",
	voice: str | None = None,
) -> bytes:
	"""Text to speech with the agent's TTS model (its own provider key); returns the audio bytes."""
	from huf.ai.handlers.media import handle_generate_audio

	result = _run_coro(
		handle_generate_audio(
			input=text, agent_name=agent_name, conversation_id=conversation_id, agent_run_id=run_id,
			response_format=response_format, **({"voice": voice} if voice else {}),
		)
	)
	if not result.get("success"):
		raise ValueError(str(result.get("error") or "Text to speech failed"))
	file_id = (result.get("audio") or {}).get("file_id")
	content = frappe.get_doc("File", file_id).get_content() if file_id else b""
	if not content:
		raise ValueError("Text to speech returned no audio")
	return content.encode() if isinstance(content, str) else content


def _convert(content: bytes) -> bytes:
	return send_file.to_ogg_opus(content)


def _conversation(run_id: str | None) -> str | None:
	if not run_id:
		return None
	return frappe.db.get_value("Agent Run", run_id, "conversation") or None


# ------------------------------------------------------------------ send
def send_voice_reply(event, gateway, response: str, *, quote: bool = True, once: bool = False) -> str | None:
	"""Send ``response`` as a voice note; returns the wamid, or ``None`` after a logged warning (never raises).

	``once`` claims the event first so a replay cannot send a second companion voice note.
	"""
	try:
		if once and not _claim(event):
			return None
		text = plain_text(response)
		conversation = _conversation(getattr(event, "agent_run", None))
		if not conversation:
			raise ValueError("the agent run has no conversation to attach the audio to")
		audio = _synthesize(event.target_agent, text, conversation, getattr(event, "agent_run", None))
		ogg = _convert(audio)
		adapter = _adapter(gateway, event)
		media_id = adapter.upload_media(ogg, send_file.OGG_OPUS_MIME, "reply.ogg", "audio", True)
		delivery = adapter.send_media(
			event.conversation_id, "audio", media_id=media_id,
			reply_to=(event.provider_event_id or None) if quote else None, trusted=True, voice=True,
		)
		return str(delivery.provider_message_id or "") or None
	except send_file.FileSendError as exc:
		_warn(f"{exc.code}: {exc.message} (event {getattr(event, 'name', '')}); falling back to text")
	except Exception as exc:
		_warn(f"{type(exc).__name__}: {str(exc)[:200]} (event {getattr(event, 'name', '')}); falling back to text")
	return None
