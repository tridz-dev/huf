"""Inbound WhatsApp documents sent as application/octet-stream get their type inferred.

The declared MIME is generic (WhatsApp often labels .m4a and other files this way). The bridge
infers the type from the filename extension, checks a file signature when one is defined, and
then applies the same allow-list and per-kind size limits as any other media.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import whatsapp_bridge as wb

MB = 1024 * 1024
ACCT = {"token": "tok", "url": "https://graph.facebook.com", "version": "v25.0"}
URL = "https://lookaside.fbsbx.com/x"

M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom" + b"\x00" * 64
MP3_ID3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
DOCX = b"PK\x03\x04" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
TXT = b"hello there\n"


class FakeResp:
	def __init__(self, json_data=None, content=b""):
		self._j = json_data or {}
		self.content = content

	def raise_for_status(self):
		pass

	def json(self):
		return self._j

	def iter_content(self, chunk_size=1):
		for i in range(0, len(self.content), 2):
			yield self.content[i : i + 2]

	def close(self):
		pass


def _meta(mime, size, **kw):
	return {"mime_type": mime, "url": URL, "file_size": size, **kw}


def _get(meta, content):
	def http_get(url, **kw):
		if url.endswith("/M1"):
			return FakeResp(meta)
		return FakeResp(content=content)

	return http_get


def _dl(mime, size, content, filename="", **kw):
	with patch.object(wb, "resolve_account", return_value=ACCT):
		return wb.download_media("ACC", "M1", http_get=_get(_meta(mime, size), content), filename=filename, **kw)


class TestOctetStreamInference(unittest.TestCase):
	def test_m4a_sent_as_octet_stream_is_inferred_as_audio_mp4(self):
		res = _dl("application/octet-stream", len(M4A), M4A, filename="voice note.m4a")
		self.assertEqual(res["mime_type"], "audio/mp4")
		self.assertEqual(res["content"], M4A)
		self.assertEqual(res["filename"], "voice_note.m4a")

	def test_empty_declared_mime_is_inferred_from_extension(self):
		res = _dl("", len(MP3_ID3), MP3_ID3, filename="song.mp3")
		self.assertEqual(res["mime_type"], "audio/mpeg")

	def test_ogg_opus_and_docx_and_pdf_and_jpg_are_inferred(self):
		self.assertEqual(_dl("application/octet-stream", len(OGG), OGG, filename="a.opus")["mime_type"], "audio/ogg")
		self.assertEqual(_dl("application/octet-stream", len(PDF), PDF, filename="a.pdf")["mime_type"], "application/pdf")
		self.assertEqual(_dl("application/octet-stream", len(JPG), JPG, filename="a.JPG")["mime_type"], "image/jpeg")
		docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
		self.assertEqual(_dl("application/octet-stream", len(DOCX), DOCX, filename="a.docx")["mime_type"], docx)

	def test_txt_without_nul_bytes_is_inferred(self):
		self.assertEqual(_dl("application/octet-stream", len(TXT), TXT, filename="notes.txt")["mime_type"], "text/plain")

	def test_signature_mismatch_is_refused(self):
		# An .m4a name over PDF bytes is not audio.
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("application/octet-stream", len(PDF), PDF, filename="voice.m4a")
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("application/octet-stream", len(M4A), M4A, filename="report.pdf")
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("application/octet-stream", 5, b"\x00\x01\x02\x03\x04", filename="notes.txt")

	def test_dangerous_or_unknown_extensions_are_refused(self):
		for name in ("payload.exe", "page.html", "page.htm", "image.svg", "run.sh", "app.js", "x.bin", "noext"):
			with self.subTest(name=name):
				with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
					_dl("application/octet-stream", 4, b"data", filename=name)

	def test_no_filename_is_refused_without_inference(self):
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("application/octet-stream", len(M4A), M4A)

	def test_inferred_type_uses_per_kind_size_limit(self):
		with self.assertRaisesRegex(ValueError, "media_too_large"):
			_dl("application/octet-stream", 17 * MB, M4A, filename="long.m4a")
		with self.assertRaisesRegex(ValueError, "media_too_large"):
			_dl("application/octet-stream", 6 * MB, JPG, filename="big.jpg")
		with self.assertRaisesRegex(ValueError, "media_too_large"):
			_dl("application/octet-stream", 101 * MB, PDF, filename="huge.pdf")

	def test_declared_specific_mime_is_not_overridden_by_extension(self):
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("application/x-msdownload", 4, b"MZ\x90\x00", filename="report.pdf")
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			_dl("text/html", 4, b"<htm", filename="report.txt")

	def test_declared_specific_mime_still_works_without_filename(self):
		res = _dl("audio/mp4", len(M4A), M4A)
		self.assertEqual(res["mime_type"], "audio/mp4")


if __name__ == "__main__":
	unittest.main()
