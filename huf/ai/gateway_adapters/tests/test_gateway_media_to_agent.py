"""MM-B/MM-C: inbound WhatsApp media reaches the agent; one reply when an attachment is unavailable."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service as gs


def _gw(**kw):
	values = dict(
		name="GW",
		provider="WhatsApp",
		error_reply_text="",
		integration_settings="",
		fallback_template_language="en_US",
		is_enabled=1,
		execution_user="bot",
		whatsapp_account="",
	)
	values.update(kw)
	return SimpleNamespace(**values)


def _event(msg_type="image", **kw):
	values = dict(
		name="GEV-1",
		gateway="GW",
		sender_id="1555",
		conversation_id="1555",
		thread_id="",
		reply_message_id="",
		status="Queued",
		target_type="Agent",
		target_agent="A",
		message_text="what is this?",
		raw_payload={"message": {"type": msg_type, msg_type: {"id": "m1"}}},
		db_set=MagicMock(),
	)
	values.update(kw)
	return SimpleNamespace(**values)


def _entry(name="a.png", mime="image/png", fid="FILE-1", url="/private/files/a.png"):
	return {"file_id": fid, "file_url": url, "filename": name, "mime_type": mime}


def _run_gateway(saved, run_result, *, event=None):
	"""Drive _process_gateway_event with media saving and the agent run faked."""
	event = event or _event()
	run = MagicMock(return_value=run_result)
	fb = MagicMock(return_value=True)
	reply = MagicMock(return_value={"status": "Succeeded"})
	with (
		patch.object(gs.frappe, "get_doc", side_effect=[event, _gw(), MagicMock(owner="bot", allow_guest=True), _gw()]),
		patch.object(gs, "_process_time_block_reason", return_value=""),
		patch.object(gs, "_is_reaction_event", return_value=False),
		patch("huf.ai.agent.access.resolve_run_identity_and_authorize", return_value=SimpleNamespace(authorized=True)),
		patch.object(gs.frappe, "set_user"),
		patch.object(gs, "_describe_attachments", return_value=""),
		patch.object(gs, "_save_whatsapp_media", return_value=saved),
		patch.object(gs, "_maybe_mark_read_typing"),
		patch.object(gs, "_commit_unless_testing"),
		patch.object(gs, "_run_agent_serialised", side_effect=lambda fn, lock_key, **kw: fn(**kw)),
		patch.dict(sys.modules, {"huf.ai.agent.integration": SimpleNamespace(run_agent_sync=run)}),
		patch.object(gs, "_send_fallback_once", fb),
		patch.object(gs, "_send_whatsapp_reply", reply),
		patch.object(gs.frappe, "log_error"),
	):
		out = gs._process_gateway_event("GEV-1")
	return out, run, fb, reply


class TestOneReplyWhenAttachmentUnavailable(unittest.TestCase):
	def test_agent_only_responder_when_unsaved(self):
		out, run, fb, reply = _run_gateway([], {"agent_run_id": "AR", "response": "I could not open it"})
		fb.assert_not_called()
		reply.assert_called_once()
		self.assertIn(gs.ATTACHMENT_UNAVAILABLE_NOTE, run.call_args.kwargs["prompt"])

	def test_standalone_note_when_agent_run_fails(self):
		out, run, fb, reply = _run_gateway([], {"success": False, "agent_run_id": "AR", "error": "boom"})
		kinds = [c.args[2] for c in fb.call_args_list]
		self.assertEqual(kinds, ["attachment"])

	def test_standalone_note_when_agent_produces_no_reply(self):
		out, run, fb, reply = _run_gateway([], {"agent_run_id": "AR", "response": "<NO_REPLY>"})
		self.assertEqual([c.args[2] for c in fb.call_args_list], ["attachment"])
		reply.assert_not_called()

	def test_no_fallback_when_saved(self):
		with patch("huf.ai.media_prep.resolve_event_files", return_value=[_entry()]):
			out, run, fb, reply = _run_gateway(["/private/files/a.png"], {"agent_run_id": "AR", "response": "ok"})
		fb.assert_not_called()


class TestMediaPassedToRunAgent(unittest.TestCase):
	def test_image_passed_as_files(self):
		with patch("huf.ai.media_prep.resolve_event_files", return_value=[_entry()]):
			out, run, fb, reply = _run_gateway(["/private/files/a.png"], {"agent_run_id": "AR", "response": "ok"})
		files = run.call_args.kwargs["files"]
		self.assertEqual(files[0]["file_url"], "/private/files/a.png")
		self.assertEqual(files[0]["file_id"], "FILE-1")
		self.assertTrue(files[0]["is_image"])

	def test_no_files_kwarg_content_when_no_media(self):
		out, run, fb, reply = _run_gateway([], {"agent_run_id": "AR", "response": "ok"}, event=_event("text"))
		self.assertFalse(run.call_args.kwargs.get("files"))


class TestMediaPrep(unittest.TestCase):
	def setUp(self):
		from huf.ai import media_prep

		self.mp = media_prep

	def test_classify(self):
		self.assertEqual(self.mp.classify_media("a.png", "image/png"), "image")
		self.assertEqual(self.mp.classify_media("v.ogg", "audio/ogg"), "audio")
		self.assertEqual(self.mp.classify_media("d.pdf", "application/pdf"), "document")
		self.assertEqual(self.mp.classify_media("x.bin", "application/x-unknown"), "unsupported")

	def test_image_becomes_image_file_no_text(self):
		prep = self.mp.prepare_media_for_agent([_entry()], "A")
		self.assertEqual(prep.files[0]["is_image"], 1)
		self.assertEqual(prep.prefix, "")
		self.assertEqual(prep.suffix, "")

	def test_document_text_appended_labelled(self):
		ocr = MagicMock(return_value={"success": True, "text": "INVOICE 42", "file_hash": "h"})
		with patch.object(self.mp, "_ocr_document", ocr):
			prep = self.mp.prepare_media_for_agent([_entry("d.pdf", "application/pdf")], "A")
		self.assertIn("INVOICE 42", prep.suffix)
		self.assertIn("d.pdf", prep.suffix)
		self.assertEqual(prep.prefix, "")

	def test_document_text_is_size_capped(self):
		ocr = MagicMock(return_value={"success": True, "text": "x" * 500000})
		with patch.object(self.mp, "_ocr_document", ocr):
			prep = self.mp.prepare_media_for_agent([_entry("d.pdf", "application/pdf")], "A")
		self.assertLessEqual(len(prep.suffix), self.mp.MAX_TOTAL_TEXT_CHARS + 1000)
		self.assertIn("truncated", prep.suffix.lower())

	def test_total_budget_across_documents(self):
		ocr = MagicMock(return_value={"success": True, "text": "y" * 500000})
		entries = [_entry(f"d{i}.pdf", "application/pdf", fid=f"F{i}") for i in range(5)]
		with patch.object(self.mp, "_ocr_document", ocr):
			prep = self.mp.prepare_media_for_agent(entries, "A")
		self.assertLessEqual(len(prep.suffix), self.mp.MAX_TOTAL_TEXT_CHARS + 2000)

	def test_ocr_failure_gives_short_note_not_crash(self):
		with patch.object(self.mp, "_ocr_document", side_effect=RuntimeError("provider down")):
			prep = self.mp.prepare_media_for_agent([_entry("d.pdf", "application/pdf")], "A")
		self.assertIn("could not be read", prep.suffix)
		self.assertNotIn("provider down", prep.suffix)

	def test_ocr_unsuccessful_result_gives_note(self):
		with patch.object(self.mp, "_ocr_document", return_value={"success": False, "error": "x"}):
			prep = self.mp.prepare_media_for_agent([_entry("d.pdf", "application/pdf")], "A")
		self.assertIn("could not be read", prep.suffix)

	def test_audio_transcript_prepended_original_kept(self):
		stt = MagicMock(return_value={"success": True, "text": "hello there"})
		with patch.object(self.mp, "_transcribe_audio", stt):
			prep = self.mp.prepare_media_for_agent([_entry("v.ogg", "audio/ogg")], "A")
		self.assertIn("hello there", prep.prefix)
		self.assertIn("transcript", prep.prefix.lower())
		self.assertEqual(prep.files[0]["file_id"], "FILE-1")
		self.assertFalse(prep.files[0].get("is_image"))

	def test_stt_failure_gives_note(self):
		with patch.object(self.mp, "_transcribe_audio", side_effect=ValueError("no stt model")):
			prep = self.mp.prepare_media_for_agent([_entry("v.ogg", "audio/ogg")], "A")
		self.assertIn("could not be transcribed", prep.prefix)

	def test_unsupported_gets_note(self):
		prep = self.mp.prepare_media_for_agent([_entry("x.bin", "application/x-unknown")], "A")
		self.assertIn("unsupported", prep.suffix.lower())

	def test_build_prompt(self):
		prep = self.mp.PreparedMedia(files=[], prefix="[T]", suffix="[D]")
		self.assertEqual(self.mp.build_prompt("note", "hi", prep), "[T]\nnote\nhi\n[D]")

	def test_resolve_event_files_scoped_to_event(self):
		with patch.object(self.mp.frappe, "get_all", return_value=[]) as ga:
			self.mp.resolve_event_files("GEV-1", ["/private/files/a.png"])
		filters = ga.call_args.kwargs["filters"]
		self.assertEqual(filters["attached_to_doctype"], "Gateway Event")
		self.assertEqual(filters["attached_to_name"], "GEV-1")
		self.assertEqual(filters["file_url"], ["in", ["/private/files/a.png"]])


if __name__ == "__main__":
	unittest.main()
