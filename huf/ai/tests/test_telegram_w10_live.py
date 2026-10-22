"""W10-LIVE regressions: public URL without webserver port, pending room entries, tool-send dedupe."""

import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import gateway_service as svc, telegram_public_url as pu
from huf.ai.gateway_adapters import telegram_groups, telegram_pipeline as tp


class TestPublicUrl(unittest.TestCase):
	def _url(self, host, path=""):
		with mock.patch.object(frappe, "conf", {"host_name": host}), \
				mock.patch("frappe.utils.get_url", return_value="http://site:8095"):
			return pu.public_url(path)

	def test_host_name_with_scheme_is_used_verbatim(self):
		self.assertEqual(self._url("https://x.ngrok-free.app/", "/huf/telegram-admin"),
			"https://x.ngrok-free.app/huf/telegram-admin")
		self.assertNotIn(":8095", self._url("https://x.ngrok-free.app"))

	def test_falls_back_to_get_url(self):
		self.assertEqual(self._url("", "/a"), "http://site:8095/a")
		self.assertEqual(self._url("bare.host", "a"), "http://site:8095/a")


class TestPendingRoom(unittest.TestCase):
	def gw(self, policy="Allow list"):
		return SimpleNamespace(name="GW", provider="Telegram", room_policy=policy, pairing_ttl_minutes=60,
			pairing_pending_limit=2, get=lambda k, d=None: 60)

	def _run(self, existing=None, pending=None, policy="Allow list"):
		created = mock.Mock()
		calls = iter([existing or [], pending or []])
		with mock.patch.object(frappe, "get_all", side_effect=lambda *a, **k: next(calls)), \
				mock.patch.object(frappe, "get_doc", return_value=SimpleNamespace(insert=lambda **k: SimpleNamespace(name="E1"))) as gd, \
				mock.patch.object(svc, "_new_unique_pairing_code", return_value="PAIR-1"), \
				mock.patch.object(svc, "now_datetime", return_value=0), mock.patch.object(svc, "add_to_date", return_value=0):
			out = svc._record_pending_room(self.gw(policy), "-100123")
			created.called = gd.called
		return out, gd.called

	def test_creates(self):
		self.assertEqual(self._run(), ("E1", True))

	def test_idempotent(self):
		self.assertEqual(self._run(existing=["E0"]), ("", False))

	def test_pending_limit(self):
		self.assertEqual(self._run(pending=["a", "b"]), ("", False))

	def test_only_allow_list(self):
		self.assertEqual(self._run(policy="Open"), ("", False))

	def test_admission_records_only_when_addressed(self):
		gw = SimpleNamespace(room_policy="Allow list", room_sender_policy="Open", mention_required=0,
			direct_policy="Allow list", provider="Telegram")
		with mock.patch.object(svc, "_has_access_entry", return_value=False), \
				mock.patch.object(svc, "_record_pending_room") as rec:
			ok, _ = svc._admission(gw, {"is_room": True, "conversation_id": "-1", "sender_id": "5", "mentioned": True})
			self.assertFalse(ok)
			rec.assert_called_once_with(gw, "-1")
			rec.reset_mock()
			svc._admission(gw, {"is_room": True, "conversation_id": "-1", "sender_id": "5", "mentioned": False})
			rec.assert_not_called()

	def test_bot_added_records(self):
		gw = SimpleNamespace(name="GW")
		parsed = SimpleNamespace(kind="my_chat_member", is_room=True, chat_id="-100", chat_type="supergroup",
			member_old_status="left", member_new_status="member", sender_id="1")
		with mock.patch.object(svc, "_record_room_opt_in"), mock.patch.object(svc, "_record_pending_room") as rec:
			telegram_groups.apply_membership_change(gw, parsed)
		rec.assert_called_once_with(gw, "-100")


class TestToolSendSuppressesFinal(unittest.TestCase):
	def test_any_tool_send_suppresses(self):
		self.assertTrue(tp.duplicates_tool_reply(["Hi!"], "Hello there, how can I help with anything today?"))
		self.assertFalse(tp.duplicates_tool_reply([], "Hello"))
		self.assertFalse(tp.duplicates_tool_reply(["Hi!"], "  "))
