# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram voice replies (R7): mode matrix, text fallback, upload_voice action, OGG conversion, inbound hook.

No network, no ffmpeg, no TTS provider: the Bot API is the fake, synthesis/conversion are mocked.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service, media_prep
from huf.ai import whatsapp_voice_reply as wv
from huf.ai import whatsapp_send_file as send_file
from huf.ai.gateway_adapters import provider_hooks, telegram_voice as tv
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

VOICE_RAW = {"message": {"message_id": 7, "voice": {"file_id": "F1", "duration": 3}}}
NOTE_RAW = {"message": {"message_id": 7, "video_note": {"file_id": "F2"}}}
AUDIO_RAW = {"message": {"message_id": 7, "audio": {"file_id": "F3"}}}
TEXT_RAW = {"message": {"message_id": 7, "text": "hi"}}


class FakeEvent(SimpleNamespace):
	def db_set(self, key, value=None, **_kw):
		self.__dict__.update(key if isinstance(key, dict) else {key: value})


def make_event(raw=VOICE_RAW, **kw):
	values = dict(
		name="EVT-1", sender_id="42", conversation_id="555", thread_id="7", reply_message_id="",
		reply_status="", status="Running", raw_payload=raw, target_agent="Agent A", agent_run="RUN-1",
	)
	values.update(kw)
	return FakeEvent(**values)


def make_gateway(mode="Voice only"):
	return SimpleNamespace(name="G1", provider="Telegram", voice_reply_mode=mode)


class _Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=self.api.http_post,
			http_get=self.api.http_get, download_attachments=False,
		)
		self.text_send = MagicMock(return_value={"status": "Succeeded", "event_name": "EVT-1"})
		self.synth = MagicMock(return_value=b"mp3-bytes")
		self.convert = MagicMock(return_value=b"OggSOpus")
		for p in (
			patch.object(tv, "_adapter", return_value=self.adapter),
			patch.object(tv, "_synthesize", self.synth),
			patch.object(tv, "_convert", self.convert),
			patch.object(tv, "_claim", return_value=True),
			patch.object(tv, "_conversation", return_value="CONV-1"),
			patch.object(gateway_service, "is_opted_out", return_value=False),
			patch.object(gateway_service, "_attempt_reply_parts", self.text_send),
			patch.object(gateway_service, "_throttle_outbound_send"),
			patch("huf.ai.gateway_webhook.touch_last_event"),
			patch("huf.ai.gateway_adapters.telegram_messages.record_sent"),
		):
			p.start()
			self.addCleanup(p.stop)

	def reply(self, event, gateway, text="Hello **there**"):
		return gateway_service._send_telegram_reply(event, gateway, "RUN-1", text)


class TestModes(_Base):
	def test_hook_registered(self):
		self.assertIsNotNone(provider_hooks.get("Telegram", "voice_reply"))

	def test_voice_only_sends_one_voice_and_no_text(self):
		event = make_event()
		result = self.reply(event, make_gateway("Voice only"))
		self.assertEqual(len(self.api.of("sendVoice")), 1)
		self.text_send.assert_not_called()
		self.assertEqual(self.synth.call_args.args[1], "Hello there")
		self.convert.assert_called_once_with(b"mp3-bytes")  # OGG/Opus conversion invoked
		call = self.api.last("sendVoice")
		self.assertEqual(call["files"]["voice"][1], b"OggSOpus")
		self.assertEqual(json.loads(call["payload"]["reply_parameters"])["message_id"], 7)
		self.assertEqual(event.reply_status, "sent")
		self.assertEqual(result["status"], "Succeeded")
		self.assertTrue(result["voice"])

	def test_upload_voice_chat_action_sent_before_voice(self):
		self.reply(make_event(), make_gateway("Voice only"))
		methods = [c["method"] for c in self.api.calls]
		self.assertLess(methods.index("sendChatAction"), methods.index("sendVoice"))
		self.assertEqual(self.api.last("sendChatAction")["payload"]["action"], "upload_voice")

	def test_text_and_voice_sends_text_then_voice(self):
		self.reply(make_event(), make_gateway("Text and voice"))
		self.text_send.assert_called_once()
		self.assertEqual(len(self.api.of("sendVoice")), 1)
		self.assertNotIn("reply_parameters", self.api.last("sendVoice")["payload"])

	def test_mode_off_and_non_voice_inbound_send_text_only(self):
		self.reply(make_event(), make_gateway("Off"))
		for raw in (TEXT_RAW,):
			self.reply(make_event(raw), make_gateway("Voice only"))
		self.assertEqual(self.text_send.call_count, 2)
		self.assertEqual(self.api.of("sendVoice"), [])
		self.synth.assert_not_called()

	def test_audio_and_video_note_inbound_count(self):
		for raw in (NOTE_RAW, AUDIO_RAW):
			self.assertEqual(tv.reply_mode(make_event(raw), make_gateway("Voice only"), "hi"), tv.VOICE_ONLY)

	def test_too_long_or_empty_reply_is_text(self):
		self.assertEqual(tv.reply_mode(make_event(), make_gateway(), "x" * 1600), "")
		self.assertEqual(tv.reply_mode(make_event(), make_gateway(), "  "), "")

	def test_other_provider_never_voices(self):
		gw = make_gateway()
		gw.provider = "WhatsApp"
		self.assertEqual(tv.reply_mode(make_event(), gw, "hi"), "")


class TestFallback(_Base):
	def test_tts_failure_falls_back_to_text(self):
		self.synth.side_effect = ValueError("no tts model")
		self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()
		self.assertEqual(self.api.of("sendVoice"), [])

	def test_ffmpeg_missing_falls_back_to_text(self):
		self.convert.side_effect = send_file.FileSendError("ffmpeg_unavailable", "no ffmpeg")
		with patch("frappe.logger") as logger:
			self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()
		self.assertTrue(logger.return_value.warning.called)

	def test_oversize_audio_falls_back_to_text(self):
		self.convert.return_value = b"x" * (tv.MAX_UPLOAD_BYTES + 1)
		self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()
		self.assertEqual(self.api.of("sendVoice"), [])

	def test_send_voice_api_error_falls_back_to_text(self):
		self.api.queue("sendVoice", FakeBotApi.error("Bad Request: VOICE_MESSAGES_FORBIDDEN", 400))
		self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()

	def test_text_and_voice_failure_never_loses_text(self):
		self.synth.side_effect = ValueError("boom")
		result = self.reply(make_event(), make_gateway("Text and voice"))
		self.text_send.assert_called_once()
		self.assertEqual(result["status"], "Succeeded")

	def test_replayed_voice_only_reply_not_resent(self):
		event = make_event(reply_message_id="99")
		result = self.reply(event, make_gateway("Voice only"))
		self.assertEqual(self.api.of("sendVoice"), [])
		self.assertTrue(result["voice"])


class TestInboundVoice(unittest.TestCase):
	def test_telegram_voice_file_is_classified_audio(self):
		for name in ("file_0.oga", "voice-AgAD.oga", "video_note.mp4"):
			self.assertEqual(media_prep.classify_media(name), "audio")

	def test_voice_note_transcribed_for_agent(self):
		entries = [{"file_id": "FILE-1", "file_url": "/private/files/file_0.oga", "filename": "file_0.oga", "mime_type": ""}]
		with patch.object(media_prep, "_transcribe_audio", return_value={"success": True, "transcript": "hello bot"}) as stt:
			prep = media_prep.prepare_media_for_agent(entries, "Agent A")
		stt.assert_called_once_with("FILE-1", "Agent A")
		self.assertIn("hello bot", prep.prefix)
		self.assertTrue(prep.files[0]["is_audio"])



_REAL_SYNTH = tv._synthesize
_REAL_CONVERT = tv._convert
OGG_OPUS = b"OggS" + b"\x00" * 20 + b"OpusHead" + b"\x00" * 40


class TestOpusDirect(_Base):
	def test_tts_requested_as_opus(self):
		with patch.object(wv, "_synthesize", return_value=OGG_OPUS) as synth:
			out = _REAL_SYNTH("Agent A", "hi", "CONV-1", "RUN-1")
		self.assertEqual(out, OGG_OPUS)
		self.assertEqual(synth.call_args.kwargs.get("response_format"), "opus")

	def test_opus_direct_skips_ffmpeg(self):
		self.synth.return_value = OGG_OPUS
		with patch.object(tv, "_convert", _REAL_CONVERT), patch.object(send_file, "to_ogg_opus") as ffmpeg:
			self.reply(make_event(), make_gateway("Voice only"))
		ffmpeg.assert_not_called()
		self.assertEqual(self.api.last("sendVoice")["files"]["voice"][1], OGG_OPUS)
		self.text_send.assert_not_called()

	def test_opus_direct_works_without_ffmpeg_installed(self):
		self.synth.return_value = OGG_OPUS
		with patch.object(tv, "_convert", _REAL_CONVERT), patch.object(send_file.shutil, "which", return_value=None):
			self.reply(make_event(), make_gateway("Voice only"))
		self.assertEqual(len(self.api.of("sendVoice")), 1)
		self.text_send.assert_not_called()

	def test_non_ogg_bytes_fall_back_to_ffmpeg(self):
		self.synth.return_value = b"ID3-mp3-bytes"
		with patch.object(tv, "_convert", _REAL_CONVERT), patch.object(
			send_file, "to_ogg_opus", return_value=OGG_OPUS
		) as ffmpeg:
			self.reply(make_event(), make_gateway("Voice only"))
		ffmpeg.assert_called_once_with(b"ID3-mp3-bytes")
		self.assertEqual(self.api.last("sendVoice")["files"]["voice"][1], OGG_OPUS)

	def test_ogg_without_opus_stream_falls_back_to_ffmpeg(self):
		self.assertFalse(tv.is_ogg_opus(b"OggS" + b"\x00" * 40 + b"\x01vorbis"))
		self.assertTrue(tv.is_ogg_opus(OGG_OPUS))
		self.assertFalse(tv.is_ogg_opus(b"ID3"))

	def test_ffmpeg_missing_and_non_opus_falls_back_to_text(self):
		self.synth.return_value = b"ID3-mp3-bytes"
		with patch.object(tv, "_convert", _REAL_CONVERT), patch.object(send_file.shutil, "which", return_value=None):
			with patch("frappe.logger"):
				result = self.reply(make_event(), make_gateway("Voice only"))
		self.assertEqual(self.api.of("sendVoice"), [])
		self.text_send.assert_called_once()
		self.assertEqual(result["status"], "Succeeded")


if __name__ == "__main__":
	unittest.main()
