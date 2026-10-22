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


class TestHealthReason(unittest.TestCase):
	def codes(self, **over):
		return [r["code"] for r in wh.evaluate(facts(**over), NOW)["reasons"]]

	def test_warning_when_missing(self):
		out = wh.evaluate(facts(voice_reply_mode="Voice only", ffmpeg_status={"available": False, "has_libopus": False}), NOW)
		r = [x for x in out["reasons"] if x["code"] == "voice_reply_ffmpeg_missing"]
		self.assertEqual(len(r), 1)
		self.assertEqual(r[0]["severity"], "warning")

	def test_warning_when_no_libopus(self):
		self.assertIn("voice_reply_ffmpeg_missing", self.codes(voice_reply_mode="Text and voice", ffmpeg_status={"available": True, "has_libopus": False}))

	def test_none_when_off_or_ok(self):
		self.assertNotIn("voice_reply_ffmpeg_missing", self.codes(voice_reply_mode="Off", ffmpeg_status={"available": False}))
		self.assertNotIn("voice_reply_ffmpeg_missing", self.codes(voice_reply_mode="Voice only", ffmpeg_status={"available": True, "has_libopus": True}))
		self.assertNotIn("voice_reply_ffmpeg_missing", self.codes())


class TestGatewayWarning(unittest.TestCase):
	def run_validate(self, mode, status):
		from huf.huf.doctype.gateway.gateway import Gateway
		doc = MagicMock()
		doc.get = lambda k, d=None: {"voice_reply_mode": mode, "provider": "WhatsApp"}.get(k, d)
		doc.provider = "WhatsApp"
		with patch("huf.ai.whatsapp.send_file.ffmpeg_status", return_value=status), patch.object(frappe, "msgprint") as mp:
			Gateway._warn_voice_ffmpeg(doc)
		return mp

	def test_warns(self):
		mp = self.run_validate("Voice only", {"available": False, "has_libopus": False})
		self.assertEqual(mp.call_count, 1)

	def test_silent(self):
		self.assertEqual(self.run_validate("Off", {"available": False}).call_count, 0)
		self.assertEqual(self.run_validate("Voice only", {"available": True, "has_libopus": True}).call_count, 0)
