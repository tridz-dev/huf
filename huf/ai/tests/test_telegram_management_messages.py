# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""telegram_management_messages: permission, chat-id refusal, redaction, pagination (no site, no network)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import frappe

from huf.ai import telegram_management_messages as m

if not hasattr(frappe.local, "flags"):
	frappe.local.flags = frappe._dict()
if not hasattr(frappe.local, "session"):
	frappe.local.session = frappe._dict(user="tester@example.com")

GW = {"name": "TG-1", "provider": "Telegram", "is_enabled": 1, "integration_settings": "x", "last_event_at": None, "last_error": None}
TOKEN = "123456789:" + "A" * 35


def _event(i, update, **kw):
	return {
		"name": f"EV-{i:03d}", "creation": f"2026-01-01 10:{59 - i:02d}:00", "status": "Completed", "sender_id": "42",
		"message_text": kw.get("text", "hi"), "reply_status": "", "reply_message_id": "", "delivery_error": kw.get("derr", ""),
		"error_message": kw.get("err", ""), "agent_run": None, "target_agent": None,
		"raw_payload": json.dumps(update), "conversation_id": "42",
	}


def _msg(**extra):
	return {"update_id": 1, "message": {"message_id": 1, "from": {"id": 42, "first_name": "Ada", "last_name": "L"}, "chat": {"id": 42}, **extra}}


class FakeSender:
	calls: list = []

	def __init__(self, client):
		pass

	def send_text(self, chat, text, **kw):
		FakeSender.calls.append(("text", chat, text))
		return [{"message_id": 7}]

	def send_media(self, kind, chat, media, **kw):
		FakeSender.calls.append((kind, chat, media[0]))
		return [{"message_id": 8}]


class TestClassify(unittest.TestCase):
	def test_kinds(self):
		self.assertEqual(m.classify_kind(_msg(text="x")), "text")
		self.assertEqual(m.classify_kind(_msg(photo=[{"file_id": "a"}])), "media")
		self.assertEqual(m.classify_kind(_msg(voice={"file_id": "a"})), "voice")
		self.assertEqual(m.classify_kind({"callback_query": {"id": "1"}}), "callback")
		self.assertEqual(m.classify_kind({"message_reaction": {}}), "reaction")
		self.assertEqual(m.classify_kind({"business_message": {}}), "business")
		self.assertEqual(m.classify_kind({"inline_query": {}}), "inline")
		self.assertEqual(m.classify_kind({"chat_join_request": {}}), "join")
		self.assertEqual(m.classify_kind("not json"), "text")

	def test_display_name_and_attachments_hide_file_ids(self):
		raw = _msg(photo=[{"file_id": "SECRETID", "file_size": 5}])
		self.assertEqual(m.display_name(raw), "Ada L")
		att = m.attachments_of(raw)
		self.assertEqual(att[0]["kind"], "photo")
		self.assertNotIn("SECRETID", json.dumps(att))

	def test_error_redacts_token(self):
		self.assertNotIn(TOKEN, m._clean_error(f"boom {TOKEN} end"))


class TestPermissions(unittest.TestCase):
	def test_denied_for_non_admin(self):
		with mock.patch("huf.ai.telegram_management._require_gateway_admin", side_effect=frappe.PermissionError):
			for fn, args in ((m.list_messages, ()), (m.list_access, ()), (m.list_bindings, ()), (m.send_message, ("TG-1", "42", "x"))):
				with self.assertRaises(frappe.PermissionError):
					fn(*(("TG-1",) + args[1:] if args else ("TG-1",)))

	def test_gateway_required(self):
		self.assertEqual(m.list_messages(None)["error"], "gateway_required")


class TestMessages(unittest.TestCase):
	def setUp(self):
		p = mock.patch.object(m, "_require_admin", return_value=dict(GW))
		p.start()
		self.addCleanup(p.stop)

	def _run(self, events, **kw):
		def get_all(doctype, filters=None, or_filters=None, fields=None, order_by=None, limit_page_length=None):
			bound = next((f[3] for f in filters if f[1] == "creation"), None)
			rows = [e for e in events if bound is None or e["creation"] <= bound]
			return rows[:limit_page_length]

		with mock.patch.object(frappe, "get_all", side_effect=get_all):
			return m.list_messages("TG-1", **kw)

	def test_pagination_cursor_walks_all(self):
		events = [_event(i, _msg(text="t")) for i in range(5)]
		first = self._run(events, limit=2)
		self.assertEqual([i["name"] for i in first["items"]], ["EV-000", "EV-001"])
		self.assertTrue(first["has_more"])
		second = self._run(events, limit=2, cursor=first["next_cursor"])
		self.assertEqual([i["name"] for i in second["items"]], ["EV-002", "EV-003"])
		third = self._run(events, limit=2, cursor=second["next_cursor"])
		self.assertEqual([i["name"] for i in third["items"]], ["EV-004"])
		self.assertFalse(third["has_more"])
		self.assertIsNone(third["next_cursor"])

	def test_kind_filter_and_redaction(self):
		events = [_event(0, _msg(text="a"), err=f"x {TOKEN}"), _event(1, _msg(voice={"file_id": "v"})), _event(2, {"callback_query": {}})]
		res = self._run(events, filters={"kind": "voice"})
		self.assertEqual([i["name"] for i in res["items"]], ["EV-001"])
		allres = self._run(events)
		self.assertNotIn(TOKEN, json.dumps(allres))
		self.assertEqual(self._run(events, filters={"kind": "bogus"})["error"], "invalid_kind")

	def test_get_message_other_gateway_hidden(self):
		with mock.patch.object(frappe.local, "db", mock.MagicMock(**{"get_value.return_value": {**_event(0, _msg()), "gateway": "OTHER"}}), create=True):
			self.assertEqual(m.get_message("TG-1", "EV-000")["error"], "not_found")


class TestSend(unittest.TestCase):
	def setUp(self):
		FakeSender.calls = []
		for p in (
			mock.patch.object(m, "_require_admin", return_value=dict(GW)),
			mock.patch.object(m, "_credentials", return_value={"token": TOKEN}),
			mock.patch.object(m, "_client", return_value=object()),
			mock.patch("huf.ai.gateway_adapters.telegram_outbound.TelegramSender", FakeSender),
			mock.patch.object(m, "_audit"),
			mock.patch.object(m, "_own_bound_chat", return_value={"42"}),
			mock.patch("huf.ai.telegram_send_scope._is_approved", side_effect=lambda g, c: c == "77"),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_arbitrary_chat_refused(self):
		for chat in ("99", "@someone", "abc", "", None):
			res = m.send_message("TG-1", chat, "hello")
			self.assertEqual(res["error"], "recipient_not_permitted", chat)
		self.assertEqual(FakeSender.calls, [])

	def test_bound_and_approved_allowed(self):
		self.assertTrue(m.send_message("TG-1", "42", "hello")["success"])
		self.assertTrue(m.send_message("TG-1", "77", "hello")["success"])
		self.assertEqual([c[1] for c in FakeSender.calls], ["42", "77"])

	def test_text_validation(self):
		self.assertEqual(m.send_message("TG-1", "42", "  ")["error"], "empty")
		self.assertEqual(m.send_message("TG-1", "42", "x" * 5000)["error"], "too_long")
		self.assertEqual(m.send_message("TG-1", "42", "x", kind="sticker")["error"], "invalid_kind")

	def test_upload_validation(self):
		self.assertIn("larger", m.validate_upload("photo", "a.jpg", b"x" * (11 * 1024 * 1024)))
		self.assertIn("not allowed", m.validate_upload("document", "run.exe", b"x"))
		self.assertTrue(m.validate_upload("photo", "a.gif", b"x"))
		self.assertEqual(m.validate_upload("photo", "a.png", b"x"), "")
		self.assertEqual(m.validate_upload("voice", "a.ogg", b"x"), "")
		self.assertTrue(m.validate_upload("document", "a.pdf", b""))

	def test_media_goes_through_sender(self):
		with mock.patch.object(m, "_read_file", return_value=("a.png", b"\x89PNG")):
			res = m.send_message("TG-1", "42", "cap", kind="photo", file_url="/files/a.png")
		self.assertTrue(res["success"])
		self.assertEqual(FakeSender.calls[0][0], "photo")

	def test_failure_redacted(self):
		class Boom(FakeSender):
			def send_text(self, *a, **k):
				raise RuntimeError(f"bad {TOKEN}")

		with mock.patch("huf.ai.gateway_adapters.telegram_outbound.TelegramSender", Boom):
			res = m.send_message("TG-1", "42", "hello")
		self.assertEqual(res["error"], "send_failed")
		self.assertNotIn(TOKEN, json.dumps(res))


class TestAccessBindings(unittest.TestCase):
	def setUp(self):
		p = mock.patch.object(m, "_require_admin", return_value=dict(GW))
		p.start()
		self.addCleanup(p.stop)

	def test_approve_other_gateway_entry_refused(self):
		with mock.patch.object(frappe.local, "db", mock.MagicMock(**{"get_value.return_value": "OTHER"}), create=True), mock.patch("huf.ai.gateway_service.approve_gateway_pairing") as ap:
			self.assertEqual(m.approve_access("TG-1", "E-1")["error"], "not_found")
			ap.assert_not_called()

	def test_revoke_binding_scoped_to_gateway(self):
		with mock.patch.object(frappe.local, "db", mock.MagicMock(**{"get_value.return_value": "OTHER"}), create=True), mock.patch("huf.ai.telegram_admin.revoke_binding") as rv:
			self.assertEqual(m.revoke_binding("TG-1", "B-1")["error"], "not_found")
			rv.assert_not_called()

	def test_mint_code_returned_once(self):
		out = {"code": "HUF-ABC", "expires_in": 600, "instructions": "go"}
		with mock.patch("huf.ai.telegram_admin.create_binding_code", return_value=out):
			res = m.create_binding_code_for_me("TG-1", "Viewer")
		self.assertEqual(res["code"], "HUF-ABC")


if __name__ == "__main__":
	unittest.main()
