# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""send_speech: agent-callable TTS voice note on the telegram tool (fake Bot API, TTS mocked)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from huf.ai.whatsapp import send_file
from huf.ai.gateway_adapters import telegram_voice
from huf.ai.tests.test_telegram_tools_rich import Base
from huf.ai.tools import telegram as tool

OGG = b"OggS\x00" + b"OpusHead" + b"\x00" * 20
UPLOAD = ("reply.ogg", OGG, send_file.OGG_OPUS_MIME)


class TestSendSpeech(Base):
	def setUp(self):
		super().setUp()
		patch.object(tool.scope, "effective_run_id", return_value="RUN").start()

	def test_sends_voice_with_caption_reply_and_voice(self):
		with patch.object(telegram_voice, "speech_upload", return_value=UPLOAD) as sp:
			out = self.run_action(
				action="send_speech",
				chat_id="9",
				text="hello there",
				voice="nova",
				caption="cap",
				reply_to_message_id=4,
			)
		self.assertTrue(out["success"])
		self.assertEqual(sp.call_args.args[1:], ("hello there", "nova"))
		self.assertEqual(len(self.api.of("sendVoice")), 1)
		self.assertEqual(self.payload("sendVoice")["caption"], "cap")

	def test_requires_text_and_caps_length(self):
		self.assertEqual(self.run_action(action="send_speech", chat_id="9")["missing_arguments"], ["text"])
		self.assertIn("text is required", self.run_action(action="send_speech", chat_id="9", text=" ")["error"])
		out = self.run_action(action="send_speech", chat_id="9", text="x" * (tool.MAX_SPEECH_CHARS + 1))
		self.assertIn("at most", out["error"])
		self.assertEqual(self.api.calls, [])

	def test_tts_failure_returns_fallback_error(self):
		with patch.object(telegram_voice, "speech_upload", side_effect=ValueError("No TTS model configured")):
			out = self.run_action(action="send_speech", chat_id="9", text="hi")
		self.assertFalse(out["success"])
		self.assertIn("No TTS model configured", out["error"])
		self.assertIn("text", out["error"])
		self.assertEqual(self.api.calls, [])

	def test_ffmpeg_error_message_surfaces(self):
		err = send_file.FileSendError("ffmpeg_missing", "ffmpeg is not installed")
		with patch.object(telegram_voice, "speech_upload", side_effect=err):
			out = self.run_action(action="send_speech", chat_id="9", text="hi")
		self.assertIn("ffmpeg is not installed", out["error"])

	def test_speech_upload_uses_agent_tts_and_voice(self):
		with (
			patch.object(telegram_voice, "frappe") as fr,
			patch.object(telegram_voice, "_conversation", return_value="CONV"),
			patch.object(telegram_voice, "_synthesize", return_value=OGG) as syn,
		):
			fr.db.get_value.return_value = "Agent A"
			name, data, mime = telegram_voice.speech_upload("RUN", "**hi**", "nova")
		self.assertEqual(syn.call_args.args, ("Agent A", "hi", "CONV", "RUN"))
		self.assertEqual(syn.call_args.kwargs, {"voice": "nova"})
		self.assertEqual((data, mime), (OGG, send_file.OGG_OPUS_MIME))

	def test_speech_upload_without_run_errors(self):
		with self.assertRaises(ValueError):
			telegram_voice.speech_upload(None, "hi")

	def test_is_a_counted_chat_send_action(self):
		self.assertIn("send_speech", tool.SEND_ACTIONS)
		self.assertIn("send_speech", tool.CHAT_ACTIONS)


class TestSendSpeechGateway(Base):
	def setUp(self):
		super().setUp()
		tool.scope.run_gateway.return_value = "GW"
		patch.object(tool.scope, "effective_run_id", return_value="RUN").start()
		patch.object(tool.scope, "current_chat", return_value="111").start()
		self.claim = patch.object(tool.scope, "claim_send", return_value=None).start()
		self.release = patch.object(tool.scope, "release_send").start()
		self.check = patch.object(tool.scope, "check_recipient", return_value=None).start()
		self.mark = patch.object(tool.run_delivery, "mark").start()
		self.note = patch.object(tool.scope, "note_current_chat_text").start()
		self.rec = patch.object(tool, "_record_tool_send").start()

	def test_defaults_to_current_chat_counts_and_marks_delivered(self):
		with patch.object(telegram_voice, "speech_upload", return_value=UPLOAD):
			out = self.run_action(action="send_speech", text="hello")
		self.assertTrue(out["success"])
		self.assertEqual(self.payload("sendVoice")["chat_id"], "111")
		self.claim.assert_called_once()
		self.mark.assert_called_once_with("RUN")
		self.rec.assert_called_once()
		self.assertEqual(self.rec.call_args.args[2], "send_speech")

	def test_other_chat_refused_by_scope(self):
		self.check.return_value = json.dumps({"success": False, "error": "recipient_not_permitted"})
		out = self.run_action(action="send_speech", chat_id="999", text="hello")
		self.assertEqual(out["error"], "recipient_not_permitted")
		self.assertEqual(self.api.calls, [])

	def test_failed_synthesis_releases_the_cap(self):
		with patch.object(telegram_voice, "speech_upload", side_effect=ValueError("boom")):
			out = self.run_action(action="send_speech", text="hello")
		self.assertFalse(out["success"])
		self.release.assert_called_once()
		self.mark.assert_not_called()


class TestRunCoroInRunningLoop(unittest.TestCase):
	def test_runs_inside_a_running_event_loop(self):
		import asyncio

		from huf.ai.whatsapp import voice_reply as wv

		async def inner():
			return 7

		async def outer():
			return wv._run_coro(inner())  # the agent tool path calls sync code from a running loop

		self.assertEqual(asyncio.run(outer()), 7)
		self.assertEqual(wv._run_coro(inner()), 7)
