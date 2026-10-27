# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Voice note reply (MM-E): a voice note in gets a voice note out, behind the Gateway ``voice_reply_mode``.

No network, no ffmpeg, no TTS provider: synthesis, conversion and the adapter are faked.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service
from huf.ai.whatsapp import send_file as send_file
from huf.ai.whatsapp import voice_reply as voice

VOICE_PAYLOAD = {"message": {"type": "audio", "audio": {"id": "m1", "voice": True}}}
AUDIO_PAYLOAD = {"message": {"type": "audio", "audio": {"id": "m1"}}}
TEXT_PAYLOAD = {"message": {"type": "text", "text": {"body": "hi"}}}


class FakeEvent(SimpleNamespace):
	def db_set(self, key, value=None, **_kw):
		values = key if isinstance(key, dict) else {key: value}
		self.__dict__.update(values)
		self.writes.append(values)


def make_event(payload=VOICE_PAYLOAD, **kw):
	values = dict(
		name="GWE-1", gateway="G1", sender_id="15551230000", conversation_id="15551230000",
		provider_event_id="wamid.IN", reply_message_id="", reply_status="", status="Running",
		raw_payload=json.dumps(payload), target_agent="Agent A", agent_run="RUN-1", writes=[],
	)
	values.update(kw)
	return FakeEvent(**values)


def make_gateway(mode="Voice only", provider="WhatsApp"):
	return SimpleNamespace(name="G1", provider=provider, voice_reply_mode=mode, retry_max_attempts=4)


class FakeAdapter:
	def __init__(self):
		self.uploads, self.sends = [], []

	def upload_media(self, content, mime, filename="", kind=None, voice=False):
		self.uploads.append({"content": content, "mime": mime, "filename": filename, "kind": kind, "voice": voice})
		return "media-1"

	def send_media(self, to, kind, **kw):
		self.sends.append({"to": to, "kind": kind, **kw})
		return SimpleNamespace(provider_message_id="wamid.VOICE", provider_response={})


class _Base(unittest.TestCase):
	def setUp(self):
		self.adapter = FakeAdapter()
		self.text_send = MagicMock(return_value={"status": "Succeeded", "event_name": "GWE-1"})
		self.synth = MagicMock(return_value=b"mp3-bytes")
		self.convert = MagicMock(return_value=b"OggSOpusHead-ogg")
		patches = [
			patch.object(voice, "_adapter", return_value=self.adapter),
			patch.object(voice, "_synthesize", self.synth),
			patch.object(voice, "_convert", self.convert),
			patch.object(send_file, "ffmpeg_can_make_opus", return_value=True),
			patch.object(voice, "_claim", return_value=True),
			patch.object(voice, "_conversation", return_value="CONV-1"),
			patch.object(gateway_service, "is_opted_out", return_value=False),
			patch.object(gateway_service, "_attempt_reply_parts", self.text_send),
			patch.object(gateway_service, "_commit_unless_testing"),  # needs a bound frappe.flags
			patch("huf.ai.gateway_webhook.touch_last_event"),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def reply(self, event, gateway, text="Hello **there**"):
		return gateway_service._send_whatsapp_reply(event, gateway, "RUN-1", text)


class TestVoiceReply(_Base):
	def test_voice_in_voice_only_sends_one_voice_note_and_no_text(self):
		event = make_event()
		result = self.reply(event, make_gateway("Voice only"))
		self.assertEqual(len(self.adapter.sends), 1)
		send = self.adapter.sends[0]
		self.assertTrue(send["voice"])
		self.assertEqual(send["kind"], "audio")
		self.assertEqual(send["media_id"], "media-1")
		self.assertEqual(self.adapter.uploads[0]["mime"], send_file.OGG_OPUS_MIME)
		self.text_send.assert_not_called()
		self.assertEqual(self.synth.call_args.args[1], "Hello there")  # plain text, no markdown
		self.assertEqual(event.reply_message_id, "wamid.VOICE")
		self.assertEqual(event.reply_status, "sent")
		self.assertEqual(event.status, "Succeeded")
		self.assertEqual(result["status"], "Succeeded")

	def test_text_and_voice_sends_both(self):
		self.reply(make_event(), make_gateway("Text and voice"))
		self.text_send.assert_called_once()
		self.assertEqual(len(self.adapter.sends), 1)
		self.assertTrue(self.adapter.sends[0]["voice"])

	def test_mode_off_sends_text_only(self):
		self.reply(make_event(), make_gateway("Off"))
		self.text_send.assert_called_once()
		self.assertEqual(self.adapter.sends, [])
		self.synth.assert_not_called()

	def test_non_voice_inbound_sends_text_only(self):
		for payload in (TEXT_PAYLOAD, AUDIO_PAYLOAD):
			self.text_send.reset_mock()
			self.reply(make_event(payload), make_gateway("Voice only"))
			self.text_send.assert_called_once()
		self.assertEqual(self.adapter.sends, [])

	def test_no_ffmpeg_and_provider_opus_sends_a_voice_note_without_converting(self):
		self.synth.return_value = b"OggS" + b"\x00" * 22 + b"OpusHead" + bytes([1, 1]) + b"\x00" * 20
		with patch.object(send_file, "ffmpeg_can_make_opus", return_value=False):
			self.reply(make_event(), make_gateway("Voice only"))
		self.convert.assert_not_called()
		self.assertTrue(self.adapter.sends[0]["voice"])
		self.assertEqual(self.adapter.uploads[0]["mime"], send_file.OGG_OPUS_MIME)
		self.text_send.assert_not_called()
		self.assertEqual(self.synth.call_args.kwargs["response_format"], "opus")  # asks for Opus first

	def test_no_ffmpeg_and_mp3_goes_as_an_ordinary_audio_message(self):
		self.synth.return_value = b"ID3\x04\x00" + b"\x00" * 30
		with patch.object(send_file, "ffmpeg_can_make_opus", return_value=False):
			self.reply(make_event(), make_gateway("Voice only"))
		self.convert.assert_not_called()
		send = self.adapter.sends[0]
		self.assertFalse(send["voice"])
		self.assertEqual(self.adapter.uploads[0]["mime"], "audio/mpeg")
		self.assertEqual(self.adapter.uploads[0]["filename"], "reply.mp3")
		self.text_send.assert_not_called()

	def test_no_ffmpeg_and_unsendable_audio_falls_back_to_text(self):
		self.synth.return_value = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 20  # e.g. Gemini WAV
		with patch.object(send_file, "ffmpeg_can_make_opus", return_value=False), patch("frappe.logger") as logger:
			self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()
		self.assertEqual(self.adapter.sends, [])
		self.assertTrue(logger.return_value.warning.called)

	def test_failed_conversion_never_breaks_the_reply(self):
		self.synth.return_value = b"ID3\x04\x00" + b"\x00" * 30
		self.convert.side_effect = send_file.FileSendError("audio_conversion_failed", "bad audio")
		self.reply(make_event(), make_gateway("Voice only"))  # ffmpeg present but broken: plain audio instead
		self.assertFalse(self.adapter.sends[0]["voice"])
		self.convert.side_effect = OSError("exec format error")
		self.adapter.sends.clear()
		self.reply(make_event(), make_gateway("Voice only"))
		self.assertFalse(self.adapter.sends[0]["voice"])

	def test_opus_request_refused_retries_as_mp3(self):
		self.synth.side_effect = [ValueError("response_format not supported"), b"ID3\x04\x00" + b"\x00" * 30]
		with patch.object(send_file, "ffmpeg_can_make_opus", return_value=False):
			self.reply(make_event(), make_gateway("Voice only"))
		self.assertEqual([c.kwargs.get("response_format", "mp3") for c in self.synth.call_args_list], ["opus", "mp3"])
		self.assertFalse(self.adapter.sends[0]["voice"])

	def test_tts_failure_falls_back_to_text(self):
		self.synth.side_effect = ValueError("no tts model")
		self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()

	def test_send_failure_falls_back_to_text(self):
		self.adapter.send_media = MagicMock(side_effect=RuntimeError("window closed"))
		self.reply(make_event(), make_gateway("Voice only"))
		self.text_send.assert_called_once()

	def test_text_and_voice_failure_never_loses_the_text(self):
		self.synth.side_effect = ValueError("boom")
		result = self.reply(make_event(), make_gateway("Text and voice"))
		self.text_send.assert_called_once()
		self.assertEqual(result["status"], "Succeeded")

	def test_opted_out_sends_nothing(self):
		with patch.object(gateway_service, "is_opted_out", return_value=True):
			event = make_event()
			self.reply(event, make_gateway("Voice only"))
		self.assertEqual(self.adapter.sends, [])
		self.text_send.assert_not_called()
		self.synth.assert_not_called()
		self.assertEqual(event.reply_status, "suppressed")

	def test_too_long_reply_is_text_only(self):
		self.reply(make_event(), make_gateway("Voice only"), "x" * (voice.MAX_TTS_CHARS + 1))
		self.text_send.assert_called_once()
		self.synth.assert_not_called()

	def test_other_provider_ignores_the_setting(self):
		self.assertEqual(voice.reply_mode(make_event(), make_gateway("Voice only", provider="Telegram"), "hi"), "")

	def test_replay_does_not_send_a_second_voice_note(self):
		event = make_event(reply_message_id="wamid.VOICE", reply_status="sent")
		self.reply(event, make_gateway("Voice only"))
		self.assertEqual(self.adapter.sends, [])
		self.text_send.assert_not_called()
		self.assertEqual(event.status, "Succeeded")

	def test_claimed_companion_voice_is_not_resent(self):
		with patch.object(voice, "_claim", return_value=False):
			self.reply(make_event(), make_gateway("Text and voice"))
		self.text_send.assert_called_once()
		self.assertEqual(self.adapter.sends, [])

	def test_companion_voice_skipped_while_text_is_retrying(self):
		self.text_send.return_value = {"status": "Running", "reply_status": "retrying"}
		self.reply(make_event(), make_gateway("Text and voice"))
		self.assertEqual(self.adapter.sends, [])


class TestHelpers(unittest.TestCase):
	def test_plain_text_strips_markdown(self):
		src = "# Title\n**bold** _it_ `code` [link](http://x.y)\n- item\n```\nblock\n```"
		out = voice.plain_text(src)
		for ch in ("*", "`", "#", "](", "```"):
			self.assertNotIn(ch, out)
		self.assertIn("bold", out)
		self.assertIn("link", out)

	def test_is_voice_note_accepts_dict_payload(self):
		self.assertTrue(voice.is_voice_note(SimpleNamespace(raw_payload=VOICE_PAYLOAD)))
		self.assertFalse(voice.is_voice_note(SimpleNamespace(raw_payload=None)))
		self.assertFalse(voice.is_voice_note(SimpleNamespace(raw_payload="not json")))


class TestGatewayValidation(unittest.TestCase):
	def _validate(self, mode, provider="WhatsApp"):
		import frappe

		from huf.huf.doctype.gateway.gateway import Gateway

		values = {"voice_reply_mode": mode}
		fake = SimpleNamespace(
			get=lambda k, d=None: values.get(k, d), provider=provider
		)
		return frappe, lambda: Gateway._validate_reply_settings(fake)

	def test_valid_modes_pass(self):
		for mode in ("", "Off", "Voice only", "Text and voice"):
			_, run = self._validate(mode)
			run()

	def test_unknown_mode_rejected(self):
		frappe, run = self._validate("Shout")
		with self.assertRaises(frappe.ValidationError):
			run()

	def test_non_whatsapp_rejected(self):
		frappe, run = self._validate("Voice only", provider="Slack")
		with self.assertRaises(frappe.ValidationError):
			run()

	def test_telegram_voice_mode_accepted(self):
		for mode in ("Voice only", "Text and voice"):
			_, run = self._validate(mode, provider="Telegram")
			run()
