# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""ffmpeg_status helper, health reason and gateway save warning for voice replies."""

import subprocess
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp import health as wh  # noqa: E402
from huf.ai.whatsapp import send_file as sf  # noqa: E402

NOW = datetime(2026, 10, 14, 12, 0, 0)


def facts(**over):
	base = {
		"enabled": True, "has_integration": True, "access_token_present": True,
		"phone_number_id_present": True, "verify_token_present": True, "app_secret_present": True,
		"app_id_present": True, "account_phone_mismatch": False,
		"last_event_at": NOW - timedelta(hours=1), "last_error": "", "events_ever": 5,
		"replied_ever": True, "events_24h": {"received": 2, "failed": 0, "unrouted": 0, "rejected": 0},
	}
	base.update(over)
	return base


def fake_run(version_out="ffmpeg version 6.1.1 Copyright", encoders_out=" A....D libopus  libopus Opus", calls=None):
	def run(cmd, **kw):
		if calls is not None:
			calls.append((cmd, kw))
		assert isinstance(cmd, list) and not kw.get("shell")
		out = encoders_out if "-encoders" in cmd else version_out
		return SimpleNamespace(returncode=0, stdout=out.encode(), stderr=b"")
	return run


class TestFfmpegStatus(unittest.TestCase):
	def setUp(self):
		sf._ffmpeg_cache_clear()

	def test_missing(self):
		with patch.object(sf.shutil, "which", return_value=None):
			self.assertEqual(sf.ffmpeg_status(), {"available": False, "has_libopus": False, "version": ""})

	def test_ok(self):
		with patch.object(sf.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(sf.subprocess, "run", fake_run()):
			st = sf.ffmpeg_status()
		self.assertEqual(st, {"available": True, "has_libopus": True, "version": "6.1.1"})

	def test_no_libopus(self):
		with patch.object(sf.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(
			sf.subprocess, "run", fake_run(encoders_out=" A....D aac  AAC")
		):
			st = sf.ffmpeg_status()
		self.assertTrue(st["available"])
		self.assertFalse(st["has_libopus"])

	def test_timeout_means_unavailable(self):
		def boom(cmd, **kw):
			raise subprocess.TimeoutExpired(cmd, 1)
		with patch.object(sf.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(sf.subprocess, "run", boom):
			self.assertFalse(sf.ffmpeg_status()["available"])

	def test_cached_and_no_shell(self):
		calls = []
		with patch.object(sf.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(
			sf.subprocess, "run", fake_run(calls=calls)
		):
			sf.ffmpeg_status()
			sf.ffmpeg_status()
		self.assertEqual(len(calls), 2)  # version + encoders, once
		self.assertTrue(all("timeout" in kw for _, kw in calls))


class TestNoFfmpegWarning(unittest.TestCase):
	"""ffmpeg is optional: no health reason, no save-time alert (Frappe Cloud has no ffmpeg)."""

	def codes(self, **over):
		return [r["code"] for r in wh.evaluate(facts(**over), NOW)["reasons"]]

	def test_missing_ffmpeg_never_degrades_the_gateway(self):
		codes = self.codes(
			voice_reply_mode="Voice only", ffmpeg_status={"available": False, "has_libopus": False}
		)
		self.assertNotIn("voice_reply_ffmpeg_missing", codes)
		self.assertEqual(codes, [])

	def test_health_facts_do_not_probe_ffmpeg(self):
		import inspect

		self.assertNotIn("ffmpeg", inspect.getsource(wh))

	def test_gateway_has_no_save_time_ffmpeg_alert(self):
		from huf.huf.doctype.gateway.gateway import Gateway

		self.assertFalse(hasattr(Gateway, "_warn_voice_ffmpeg"))


class TestOptionalHelpers(unittest.TestCase):
	def setUp(self):
		sf._ffmpeg_cache_clear()

	def test_can_make_opus_false_without_ffmpeg_and_never_raises(self):
		with patch.object(sf.shutil, "which", return_value=None):
			self.assertFalse(sf.ffmpeg_can_make_opus())
		with patch.object(sf, "ffmpeg_status", side_effect=RuntimeError("boom")):
			self.assertFalse(sf.ffmpeg_can_make_opus())

	def test_can_make_opus_true_with_libopus(self):
		with patch.object(sf.shutil, "which", return_value="/usr/bin/ffmpeg"), patch.object(sf.subprocess, "run", fake_run()):
			self.assertTrue(sf.ffmpeg_can_make_opus())


def ogg_opus(channels=1):
	return b"OggS" + b"\x00" * 22 + b"OpusHead" + bytes([1, channels]) + b"\x00" * 20


class TestAudioSniffing(unittest.TestCase):
	def test_voice_ready_is_mono_ogg_opus_only(self):
		self.assertTrue(sf.is_voice_ready(ogg_opus(1)))
		self.assertFalse(sf.is_voice_ready(ogg_opus(2)))
		self.assertFalse(sf.is_voice_ready(b"OggS" + b"\x00" * 40))  # Ogg Vorbis, not Opus
		self.assertFalse(sf.is_voice_ready(b"ID3\x03" + b"\x00" * 20))
		self.assertEqual(sf.ogg_opus_channels(ogg_opus(2)), 2)
		self.assertIsNone(sf.ogg_opus_channels(b"RIFF"))

	def test_sniff_audio_mime(self):
		self.assertEqual(sf.sniff_audio_mime(b"ID3\x04\x00" + b"\x00" * 10), "audio/mpeg")
		self.assertEqual(sf.sniff_audio_mime(b"\xff\xfb\x90\x00" + b"\x00" * 10), "audio/mpeg")  # MP3 frame
		self.assertEqual(sf.sniff_audio_mime(b"\xff\xf1\x50\x80" + b"\x00" * 10), "audio/aac")  # ADTS
		self.assertEqual(sf.sniff_audio_mime(b"#!AMR\n" + b"\x00" * 10), "audio/amr")
		self.assertEqual(sf.sniff_audio_mime(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 10), "audio/mp4")
		self.assertEqual(sf.sniff_audio_mime(b"RIFF\x00\x00\x00\x00WAVEfmt "), "")  # WAV is not a WhatsApp audio type
		self.assertEqual(sf.sniff_audio_mime(b""), "")
