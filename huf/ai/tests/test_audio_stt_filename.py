"""STT upload filename normalisation (.oga/.opus -> .ogg) and media_prep failure logging."""

import os
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from huf.ai import audio_service, media_prep


class TestSttFilename(TestCase):
	def _run(self, ext, provider="openai"):
		data = b"OggS-fake-bytes"
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, f"file_2.{ext}")
			with open(path, "wb") as f:
				f.write(data)
			seen = {}

			def fake(**kw):
				tup = kw["file"]
				seen["name"], seen["mime"] = (tup[0], tup[2]) if isinstance(tup, tuple) else (None, None)
				seen["bytes"] = tup[1].read() if isinstance(tup, tuple) else None
				return MagicMock(text="hello")

			with patch("litellm.transcription", side_effect=fake):
				out = audio_service._call_stt_provider(
					provider_name=provider,
					normalized_model="gpt-4o-mini-transcribe",
					api_key="k",
					file_path=path,
				)
			with open(path, "rb") as f:
				self.assertEqual(f.read(), data)
		self.assertEqual(out, "hello")
		self.assertEqual(seen["bytes"], data)
		return seen

	def test_extensions(self):
		for ext, want, mime in [
			("oga", "file_2.ogg", "audio/ogg"),
			("opus", "file_2.ogg", "audio/ogg"),
			("ogg", "file_2.ogg", "audio/ogg"),
			("mp3", "file_2.mp3", "audio/mpeg"),
			("m4a", "file_2.m4a", "audio/mp4"),
			("mp4", "file_2.mp4", "audio/mp4"),
		]:
			seen = self._run(ext)
			self.assertEqual((seen["name"], seen["mime"]), (want, mime), ext)


class TestMediaPrepLogging(TestCase):
	def _prep(self, side_effect=None, ret=None):
		entry = {"file_id": "F1", "file_url": "/x", "filename": "file_2.oga", "mime_type": "audio/ogg"}
		logger = MagicMock()
		with (
			patch.object(media_prep, "_transcribe_audio", side_effect=side_effect, return_value=ret),
			patch("frappe.logger", return_value=logger),
		):
			prep = media_prep.prepare_media_for_agent([entry], "agent")
		return prep, logger

	def test_exception_logged_and_redacted(self):
		prep, logger = self._prep(side_effect=RuntimeError("bad key sk-abcdef123456 boom"))
		logger.warning.assert_called_once()
		logged = " ".join(str(a) for a in logger.warning.call_args[0])
		self.assertIn("RuntimeError", logged)
		self.assertNotIn("sk-abcdef123456", logged)
		self.assertIn("could not be transcribed", str(prep.__dict__))

	def test_provider_error_logged(self):
		_, logger = self._prep(ret={"success": False, "error": "Transcription failed: 400"})
		logger.warning.assert_called_once()
