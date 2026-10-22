# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""MM-D: WhatsApp media sends accept a Huf File (``file_url`` / ``file_id``) with an ownership check.

No network: the bridge, Graph (``fake_graph``) and the File lookups are mocked.
"""

from __future__ import annotations

import json
import shutil
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp import send_file as sf
from huf.ai.whatsapp import send_scope as scope
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.testing.fake_graph import FakeGraph, FakeResponse
from huf.ai.tools import whatsapp

GW = "GW-SENDFILE"
RUN = "RUN-SF"
CONV = "CONV-SF"
CONTACT = "15550001111"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
OGG_OPUS = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x01" * 40
OGG_VORBIS = b"OggS" + b"\x00" * 24 + b"\x01vorbis" + b"\x01" * 40
MP3 = b"ID3" + b"\x00" * 64


def _row(name="F1", url="/private/files/a.png", file_name="a.png", private=1, doctype="Agent Conversation", parent=CONV, owner="user@x.com", size=64):
	return {
		"name": name, "file_url": url, "file_name": file_name, "is_private": private, "is_folder": 0,
		"attached_to_doctype": doctype, "attached_to_name": parent, "owner": owner, "file_size": size,
	}


class _Base(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		self.addCleanup(patch.stopall)
		self.rows: dict[str, dict] = {}
		self.content = PNG
		self.settings = {"scope": "Current contact", "allowlist": [], "per_run": 20, "per_day": 200}
		patch.object(whatsapp, "_run_gateway", return_value=GW).start()
		patch.object(whatsapp, "_authorize", return_value=None).start()
		patch.object(whatsapp, "_disconnect_refusal", return_value=None).start()
		patch.object(whatsapp, "_is_opted_out", return_value=False).start()
		patch.object(whatsapp, "_is_proactive_send", return_value=False).start()
		patch.object(scope, "settings", side_effect=lambda gw: self.settings).start()
		patch.object(scope, "current_contact", return_value=CONTACT).start()
		patch.object(sf, "_file_row", side_effect=lambda key: self.rows.get(key)).start()
		patch.object(sf, "_run_conversation", return_value=CONV).start()
		patch.object(sf, "_parent_conversation", side_effect=self._parent).start()
		patch.object(sf, "_read_content", side_effect=lambda row: self.content).start()
		patch.object(sf, "_session_user", return_value="user@x.com").start()
		patch.object(whatsapp, "_resolve_bridge_account", return_value={"name": "ACC-1"}).start()
		self.upload = patch.object(bridge, "upload_media", return_value={"success": True, "media_id": "MID1"}).start()
		self.send = patch.object(
			bridge, "send_media", return_value={"success": True, "message_id": "wamid.1", "name": "M1"}
		).start()
		self.text = patch.object(bridge, "send_text", return_value={"success": True, "message_id": "wamid.T"}).start()
		self.parents: dict[tuple[str, str], str] = {}

	def _parent(self, doctype, name):
		return self.parents.get((doctype, name), "")

	def _clean(self):
		frappe.db.delete("WhatsApp Send Key", {"gateway": GW})
		frappe.db.commit()

	def add(self, **kw):
		row = _row(**kw)
		self.rows[row["name"]] = row
		self.rows[row["file_url"]] = row
		return row

	def call(self, action="send_image", **kw):
		kw.setdefault("to", CONTACT)
		kw.setdefault("call_id", frappe.generate_hash(length=8))
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": RUN}):
			return json.loads(whatsapp.handle_action(action, **kw))


class TestResolveAndOwnership(_Base):
	def test_file_attached_to_this_conversation_is_sent_by_uploaded_id(self):
		self.add()
		res = self.call(file_id="F1", caption="hi")
		self.assertTrue(res["success"], res)
		self.assertEqual(self.upload.call_args.args[:3], ("ACC-1", PNG, "image/png"))
		self.assertEqual(self.send.call_args.kwargs["media_id"], "MID1")
		self.assertIsNone(self.send.call_args.kwargs["link"] or None)
		self.assertEqual(self.send.call_args.kwargs["caption"], "hi")

	def test_file_url_works_like_file_id(self):
		self.add()
		self.assertTrue(self.call(file_url="/private/files/a.png")["success"])

	def test_message_attachment_of_this_conversation_is_allowed(self):
		self.add(doctype="Agent Message", parent="MSG1")
		self.parents[("Agent Message", "MSG1")] = CONV
		self.assertTrue(self.call(file_id="F1")["success"])

	def test_message_attachment_of_another_conversation_is_refused(self):
		self.add(doctype="Agent Message", parent="MSG2")
		self.parents[("Agent Message", "MSG2")] = "OTHER"
		res = self.call(file_id="F1")
		self.assertEqual(res["error"], "file_not_permitted")
		self.upload.assert_not_called()

	def test_gateway_event_of_this_run_is_allowed(self):
		self.add(doctype="Gateway Event", parent="EV1")
		self.parents[("Gateway Event", "EV1")] = CONV
		self.assertTrue(self.call(file_id="F1")["success"])

	def test_unattached_file_owned_by_the_run_user_is_allowed(self):
		self.add(doctype="", parent="", owner="user@x.com")
		self.assertTrue(self.call(file_id="F1")["success"])

	def test_unattached_file_of_another_user_is_refused(self):
		self.add(doctype="", parent="", owner="someone@else.com")
		self.assertEqual(self.call(file_id="F1")["error"], "file_not_permitted")

	def test_other_private_file_attached_elsewhere_is_refused_even_if_owned(self):
		self.add(doctype="Employee", parent="EMP1", owner="user@x.com")
		self.assertEqual(self.call(file_id="F1")["error"], "file_not_permitted")

	def test_unknown_file_is_not_found(self):
		self.assertEqual(self.call(file_id="NOPE")["error"], "file_not_found")

	def test_traversal_and_non_file_urls_are_rejected_before_lookup(self):
		for url in (
			"/private/files/../../etc/passwd", "/private/files/%2e%2e/x.png", "https://evil.test/a.png",
			"/app/user/admin", "/files/a.png?x=1", "/private/files//a.png", "file:///etc/passwd", "/private/files/a\\b.png",
		):
			res = self.call(file_url=url)
			self.assertIn(res["error"], ("invalid_file_reference",), url)
		self.upload.assert_not_called()

	def test_no_run_fails_closed(self):
		self.add()
		with patch.object(sf, "_run_conversation", return_value=""):
			self.assertEqual(self.call(file_id="F1")["error"], "file_not_permitted")

	def test_exactly_one_source_is_required(self):
		self.add()
		for extra in ({"link": "https://x.test/a.png"}, {"media_id": "9"}, {"file_url": "/private/files/a.png"}):
			res = self.call(file_id="F1", **extra)
			self.assertFalse(res["success"])
			self.assertIn("one", json.dumps(res).lower())
		self.upload.assert_not_called()


class TestLimitsAndGates(_Base):
	def test_unsupported_mime_is_rejected_before_upload(self):
		self.add(url="/private/files/a.bin", file_name="a.bin")
		res = self.call(file_id="F1")
		self.assertFalse(res["success"])
		self.upload.assert_not_called()

	def test_oversize_image_is_rejected_before_reading_or_uploading(self):
		self.add(size=6 * 1024 * 1024)
		res = self.call(file_id="F1")
		self.assertFalse(res["success"])
		self.assertIn("too_large", json.dumps(res))
		self.upload.assert_not_called()

	def test_document_infers_filename_and_kind(self):
		self.add(url="/private/files/r.pdf", file_name="r.pdf")
		self.content = b"%PDF-1.4"
		res = self.call("send_document", file_id="F1")
		self.assertTrue(res["success"], res)
		self.assertEqual(self.send.call_args.kwargs["filename"], "r.pdf")

	def test_send_media_infers_kind_from_mime(self):
		self.add()
		self.assertTrue(self.call("send_media", file_id="F1")["success"])
		self.assertEqual(self.send.call_args.args[2], "image")

	def test_kind_must_match_the_file(self):
		self.add()
		res = self.call("send_document", file_id="F1")
		self.assertFalse(res["success"])
		self.upload.assert_not_called()

	def test_closed_window_blocks_before_upload(self):
		self.add()
		with patch.object(whatsapp, "_is_proactive_send", return_value=True), patch.object(whatsapp, "_server_flag", return_value=False):
			res = self.call(file_id="F1")
		self.assertEqual(res["error"], "proactive_send_not_permitted")
		self.upload.assert_not_called()

	def test_opt_out_blocks_before_upload(self):
		self.add()
		with patch.object(whatsapp, "_is_opted_out", return_value=True):
			res = self.call(file_id="F1")
		self.assertEqual(res["error"], "opted_out")
		self.upload.assert_not_called()

	def test_recipient_scope_still_applies(self):
		self.add()
		res = self.call(file_id="F1", to="15559998888")
		self.assertEqual(res["error"], "recipient_not_permitted")
		self.upload.assert_not_called()

	def test_send_cap_still_applies(self):
		self.add()
		self.settings["per_run"] = 1
		self.assertTrue(self.call(file_id="F1")["success"])
		self.assertEqual(self.call(file_id="F1")["error"], "send_cap_exceeded")
		self.assertEqual(self.upload.call_count, 1)

	def test_same_call_id_uploads_and_sends_once(self):
		self.add()
		self.call(file_id="F1", call_id="C1")
		self.call(file_id="F1", call_id="C1")
		self.assertEqual(self.send.call_count, 1)
		self.assertEqual(self.upload.call_count, 1)

	def test_long_caption_is_split_into_media_caption_and_follow_up_text(self):
		self.add()
		caption = ("word " * 300).strip()
		res = self.call(file_id="F1", caption=caption)
		self.assertTrue(res["success"], res)
		sent_caption = self.send.call_args.kwargs["caption"]
		self.assertLessEqual(len(sent_caption), 1024)
		rest = self.text.call_args.args[2]
		self.assertEqual((sent_caption + " " + rest).split(), caption.split())

	def test_audio_with_caption_is_rejected(self):
		self.add(url="/private/files/a.mp3", file_name="a.mp3")
		self.content = MP3
		self.assertFalse(self.call("send_audio", file_id="F1", caption="x")["success"])


class TestVoiceNote(_Base):
	def test_ogg_opus_is_uploaded_as_is(self):
		self.add(url="/private/files/v.ogg", file_name="v.ogg")
		self.content = OGG_OPUS
		with patch.object(sf, "to_ogg_opus") as conv:
			res = self.call("send_voice_note", file_id="F1")
		self.assertTrue(res["success"], res)
		conv.assert_not_called()
		self.assertEqual(self.upload.call_args.args[1], OGG_OPUS)
		self.assertTrue(self.upload.call_args.kwargs["voice"])
		self.assertTrue(self.send.call_args.kwargs["voice"])

	def test_other_audio_is_converted_with_ffmpeg(self):
		self.add(url="/private/files/a.mp3", file_name="a.mp3")
		self.content = MP3
		with patch.object(sf, "to_ogg_opus", return_value=OGG_OPUS) as conv:
			res = self.call("send_voice_note", file_id="F1")
		self.assertTrue(res["success"], res)
		conv.assert_called_once_with(MP3)
		self.assertEqual(self.upload.call_args.args[1], OGG_OPUS)
		self.assertTrue(self.upload.call_args.args[2].startswith("audio/ogg"))
		self.assertTrue(self.upload.call_args.args[3].endswith(".ogg"))

	def test_ogg_vorbis_is_converted_too(self):
		self.add(url="/private/files/v.ogg", file_name="v.ogg")
		self.content = OGG_VORBIS
		with patch.object(sf, "to_ogg_opus", return_value=OGG_OPUS) as conv:
			self.assertTrue(self.call("send_voice_note", file_id="F1")["success"])
		conv.assert_called_once()

	def test_missing_ffmpeg_fails_clearly_before_upload(self):
		self.add(url="/private/files/a.mp3", file_name="a.mp3")
		self.content = MP3
		with patch.object(sf.shutil, "which", return_value=None):
			res = self.call("send_voice_note", file_id="F1")
		self.assertFalse(res["success"])
		self.assertEqual(res["error"], "ffmpeg_unavailable")
		self.upload.assert_not_called()

	def test_non_audio_file_is_rejected_for_a_voice_note(self):
		self.add()
		self.assertFalse(self.call("send_voice_note", file_id="F1")["success"])
		self.upload.assert_not_called()

	def test_voice_flag_on_send_audio_converts_too(self):
		self.add(url="/private/files/a.mp3", file_name="a.mp3")
		self.content = MP3
		with patch.object(sf, "to_ogg_opus", return_value=OGG_OPUS):
			self.assertTrue(self.call("send_audio", file_id="F1", voice=True)["success"])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TestFfmpegHelper(unittest.TestCase):
	def test_failure_on_garbage_is_a_clear_error(self):
		with self.assertRaises(sf.FileSendError) as ctx:
			sf.to_ogg_opus(b"not audio at all")
		self.assertEqual(ctx.exception.code, "audio_conversion_failed")

	def test_command_uses_no_shell_and_no_user_text(self):
		with patch.object(sf.subprocess, "run") as run:
			run.return_value = MagicMock(returncode=0, stdout=OGG_OPUS, stderr=b"")
			sf.to_ogg_opus(MP3)
		cmd = run.call_args.args[0]
		self.assertIsInstance(cmd, list)
		self.assertFalse(run.call_args.kwargs.get("shell"))
		self.assertEqual(run.call_args.kwargs["input"], MP3)


class _MediaGraph(FakeGraph):
	def request(self, method, url, **kw):
		resp = super().request(method, url, **kw)
		if method == "POST" and url.rstrip("/").endswith("/media"):
			return FakeResponse({"id": "FAKEMEDIA1"}, url=url)
		return resp


class TestDirectMode(_Base):
	def setUp(self):
		super().setUp()
		self.graph = _MediaGraph()
		patch.object(whatsapp, "_resolve_bridge_account", return_value=None).start()
		patch.object(whatsapp, "_get_whatsapp_credentials", return_value=("PN1", "tok")).start()
		patch.object(whatsapp, "_graph_root", return_value="https://graph.facebook.com/v25.0").start()
		patch.object(bridge, "_default_post", self.graph.post).start()
		patch.object(whatsapp.requests, "post", self.graph.post).start()

	def test_direct_mode_uploads_then_sends_by_id(self):
		self.add()
		res = self.call(file_id="F1")
		self.assertTrue(res["success"], res)
		urls = [c["url"] for c in self.graph.calls]
		self.assertTrue(urls[0].endswith("/PN1/media"))
		msg = self.graph.sent_messages()[0]
		self.assertEqual(msg["body"]["image"]["id"], "FAKEMEDIA1")
		self.upload.assert_not_called()

	def test_direct_mode_without_credentials_refuses_clearly(self):
		self.add()
		with patch.object(whatsapp, "_get_whatsapp_credentials", return_value=("", "")):
			res = self.call(file_id="F1")
		self.assertFalse(res["success"])
		self.assertEqual(self.graph.calls, [])
