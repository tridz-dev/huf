# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""telegram_management_commands over a fake client (no site, no network)."""

from __future__ import annotations

import unittest
from unittest import mock

from huf.ai import telegram_management_commands as m
from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES


def setUpModule():
	# No site in unit runs: whitelisted wrappers consult frappe.local.flags for type validation.
	import frappe

	if not getattr(frappe.local, "flags", None):
		frappe.local.flags = frappe._dict()


class FakeClient:
	def __init__(self, replies=None):
		self.calls = []
		self.replies = replies or {}

	def call(self, method, payload=None, **kw):
		self.calls.append((method, dict(payload or {})))
		return self.replies.get(method, True)

	def get_me(self):
		return {"id": 7, "username": "bot", "first_name": "Bot", "is_bot": True}

	def get_webhook_info(self):
		return {"url": "https://x/h", "pending_update_count": 3, "allowed_updates": list(ALLOWED_UPDATES)}

	def set_webhook(self, url, **kw):
		self.calls.append(("set_webhook", {"url": url, **kw}))

	def delete_webhook(self, **kw):
		self.calls.append(("delete_webhook", kw))


class TestPure(unittest.TestCase):
	def test_profile_get(self):
		c = FakeClient({"getMyName": {"name": "N"}, "getMyDescription": {"description": "D"}, "getMyShortDescription": {"short_description": "S"}})
		self.assertEqual(m.profile_get(c, "en"), {"name": "N", "description": "D", "short_description": "S"})
		self.assertEqual(c.calls[0], ("getMyName", {"language_code": "en"}))

	def test_validate_profile_limits(self):
		with self.assertRaises(ValueError):
			m.validate_profile("x" * 65, None, None)
		with self.assertRaises(ValueError):
			m.validate_profile(None, None, "x" * 121)
		with self.assertRaises(ValueError):
			m.validate_profile(None, "x" * 513, None)
		with self.assertRaises(ValueError):
			m.validate_profile("  ", None, None)
		with self.assertRaises(ValueError):
			m.validate_profile(None, None, None)
		self.assertEqual(m.validate_profile(" A ", None, "s"), {"name": "A", "short_description": "s"})

	def test_profile_set_only_given(self):
		c = FakeClient()
		m.profile_set(c, {"short_description": "s"})
		self.assertEqual(c.calls, [("setMyShortDescription", {"short_description": "s"})])

	def test_menu_button(self):
		self.assertEqual(m.menu_button_payload("commands"), {"type": "commands"})
		self.assertEqual(m.menu_button_payload("web_app", "Open", "https://a.b/c")["web_app"], {"url": "https://a.b/c"})
		with self.assertRaises(ValueError):
			m.menu_button_payload("web_app", "Open", "http://a.b")
		with self.assertRaises(ValueError):
			m.menu_button_payload("web_app", "", "https://a.b")
		with self.assertRaises(ValueError):
			m.menu_button_payload("bogus")

	def test_token_summary_has_no_token(self):
		self.assertNotIn("token", m.token_summary(FakeClient()))

	def test_webhook_summary(self):
		w = m.webhook_summary(FakeClient(), "https://x/h")
		self.assertTrue(w["url_matches"])
		self.assertEqual(w["pending_update_count"], 3)
		self.assertEqual(w["expected_url"], "https://x/h")


class TestWrappers(unittest.TestCase):
	def _patch(self, client, secret="sec"):
		row = {"name": "G"}
		creds = {"token": "1:SECRET", "webhook_secret": secret}
		return mock.patch.multiple(
			m, _load_gateway=lambda g: row, _credentials=lambda r: creds, _client=lambda c: client,
			_webhook_url=lambda n: "https://x/h",
		)

	def test_set_commands_validates_and_sends(self):
		c = FakeClient()
		with self._patch(c):
			out = m.set_commands("G", "all_private_chats", "en", [{"command": "help", "description": "Help", "is_ephemeral": True}])
		self.assertTrue(out["success"])
		method, payload = c.calls[0]
		self.assertEqual(method, "setMyCommands")
		self.assertEqual(payload["scope"], {"type": "all_private_chats"})
		self.assertTrue(payload["commands"][0]["is_ephemeral"])

	def test_set_commands_invalid(self):
		c = FakeClient()
		with self._patch(c):
			out = m.set_commands("G", "default", None, [{"command": "Bad Name", "description": "x"}])
			bad_scope = m.set_commands("G", "chat", None, [{"command": "a", "description": "x"}])
		self.assertEqual(out["error"], "invalid")
		self.assertEqual(bad_scope["error"], "invalid")
		self.assertEqual(c.calls, [])

	def test_webhook_requires_confirm(self):
		c = FakeClient()
		with self._patch(c):
			self.assertEqual(m.set_webhook_now("G")["error"], "confirm_required")
			self.assertEqual(m.delete_webhook_now("G")["error"], "confirm_required")
		self.assertEqual(c.calls, [])

	def test_set_webhook_uses_secret_and_allowed_updates(self):
		c = FakeClient()
		with self._patch(c):
			out = m.set_webhook_now("G", confirm=1, drop_pending_updates="1")
		self.assertTrue(out["success"])
		_, kw = c.calls[0]
		self.assertEqual(kw["url"], "https://x/h")
		self.assertEqual(kw["secret_token"], "sec")
		self.assertEqual(tuple(kw["allowed_updates"]), ALLOWED_UPDATES)
		self.assertTrue(kw["drop_pending_updates"])
		self.assertNotIn("sec", str(out))

	def test_set_webhook_needs_secret(self):
		with self._patch(FakeClient(), secret=""):
			self.assertEqual(m.set_webhook_now("G", confirm=1)["error"], "invalid")

	def test_delete_webhook(self):
		c = FakeClient()
		with self._patch(c):
			self.assertTrue(m.delete_webhook_now("G", confirm="true")["success"])
		self.assertEqual(c.calls[0], ("delete_webhook", {"drop_pending_updates": False}))

	def test_check_token_never_returns_token(self):
		with self._patch(FakeClient()):
			out = m.check_token("G")
		self.assertTrue(out["check"]["valid"])
		self.assertNotIn("SECRET", str(out))

	def test_load_error_passthrough(self):
		with mock.patch.object(m, "_load_gateway", lambda g: {"success": False, "error": "not_found"}):
			self.assertEqual(m.get_bot_profile("G")["error"], "not_found")


if __name__ == "__main__":
	unittest.main()
