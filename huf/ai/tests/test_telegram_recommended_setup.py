# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""recommended_setup / apply_recommended_setup over a fake client (no site, no network)."""

from __future__ import annotations

import unittest
from unittest import mock

from huf.ai import telegram_management_commands as m


def setUpModule():
	import frappe

	if not getattr(frappe.local, "flags", None):
		frappe.local.flags = frappe._dict()


class FakeClient:
	def __init__(self):
		self.calls = []

	def call(self, method, payload=None, **kw):
		self.calls.append((method, dict(payload or {})))
		if method == "getMyCommands":
			return [{"command": "initiate", "description": "old"}]
		if method == "getChatMenuButton":
			return {"type": "commands"}
		return True


class Base(unittest.TestCase):
	def patch(self, client, url="https://site.example", load=None):
		return mock.patch.multiple(
			m,
			_load_gateway=load or (lambda g: {"name": "G"}),
			_credentials=lambda r: {"token": "1:SECRET"},
			_client=lambda c: client,
			_audit_setup=mock.DEFAULT,
		), mock.patch("frappe.utils.get_url", lambda *a, **k: url)


class TestPlan(Base):
	def run_plan(self, url="https://site.example"):
		c = FakeClient()
		p1, p2 = self.patch(c, url)
		with p1, p2:
			return m.recommended_setup("G"), c

	def test_plan_content_no_writes(self):
		out, c = self.run_plan()
		plan = out["plan"]
		names = [x["command"] for x in plan["commands"][0]["recommended"]]
		self.assertEqual(names, ["start", "help", "me", "find", "open", "approvals", "digest", "unbind"])
		self.assertEqual(plan["commands"][0]["current"][0]["command"], "initiate")
		self.assertEqual(plan["commands"][1]["scope"], "all_group_chats")
		rec = plan["menu_button"]["recommended"]
		self.assertEqual(rec["text"], "Console")
		self.assertEqual(rec["web_app"]["url"], "https://site.example/huf/tg-app?gw=G")
		self.assertTrue(plan["menu_button"]["https_ok"])
		self.assertTrue(plan["replaces_existing_commands"])
		self.assertTrue(all(method.startswith("get") for method, _ in c.calls))

	def test_plan_warns_when_not_https(self):
		out, _ = self.run_plan("http://127.0.0.1:8000")
		mb = out["plan"]["menu_button"]
		self.assertFalse(mb["https_ok"])
		self.assertIn("https", mb["warning"])


class TestApply(Base):
	def apply(self, client, url="https://site.example", **kw):
		p1, p2 = self.patch(client, url)
		with p1 as mocks, p2:
			out = m.apply_recommended_setup("G", **kw)
		return out, mocks

	def test_permission_denied(self):
		import frappe

		def deny(g):
			raise frappe.PermissionError("no")

		c = FakeClient()
		p1, p2 = self.patch(c, load=deny)
		with p1, p2, self.assertRaises(frappe.PermissionError):
			m.apply_recommended_setup("G", confirm=1)
		self.assertEqual(c.calls, [])

	def test_confirm_required(self):
		c = FakeClient()
		out, _ = self.apply(c)
		self.assertEqual(out["error"], "confirm_required")
		self.assertEqual(c.calls, [])

	def test_payloads_and_undo(self):
		c = FakeClient()
		out, mocks = self.apply(c, confirm=1)
		self.assertTrue(out["success"])
		sets = [(mm, p) for mm, p in c.calls if mm.startswith("set")]
		self.assertEqual([p.get("scope", {"type": "default"})["type"] for mm, p in sets[:2]], ["default", "all_group_chats"])
		self.assertEqual(sets[0][0], "setMyCommands")
		self.assertEqual(len(sets[0][1]["commands"]), 8)
		self.assertEqual(sets[2], ("setChatMenuButton", {"menu_button": {"type": "web_app", "text": "Console", "web_app": {"url": "https://site.example/huf/tg-app?gw=G"}}}))
		self.assertEqual(out["previous"]["commands"][0]["commands"][0]["command"], "initiate")
		self.assertEqual(out["previous"]["menu_button"], {"type": "commands"})
		mocks["_audit_setup"].assert_called_once()
		self.assertEqual(mocks["_audit_setup"].call_args[0][1], "ok")

	def test_https_refusal_changes_nothing(self):
		c = FakeClient()
		out, mocks = self.apply(c, url="http://127.0.0.1:8000", confirm=1)
		self.assertEqual(out["error"], "invalid")
		self.assertIn("https", out["message"])
		self.assertFalse([1 for mm, _ in c.calls if mm.startswith("set")])
		self.assertEqual(mocks["_audit_setup"].call_args[0][1], "failed")

	def test_commands_only_works_without_https(self):
		c = FakeClient()
		out, _ = self.apply(c, url="http://127.0.0.1:8000", confirm=1, include_menu_button=0)
		self.assertTrue(out["success"])
		self.assertFalse([1 for mm, _ in c.calls if mm == "setChatMenuButton"])
