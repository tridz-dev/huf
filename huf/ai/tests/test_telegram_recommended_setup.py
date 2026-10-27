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
		), mock.patch("huf.ai.telegram_public_url.configured_host", lambda: url)


class TestPlan(Base):
	def run_plan(self, url="https://site.example"):
		c = FakeClient()
		p1, p2 = self.patch(c, url)
		with p1, p2:
			return m.recommended_setup("G"), c

	def test_plan_content_no_writes(self):
		out, c = self.run_plan()
		plan = out["plan"]
		names = [x["command"] for x in plan["commands"][1]["recommended"]]
		self.assertEqual(
			names, ["start", "help", "me", "find", "open", "approvals", "digest", "audit", "unbind"]
		)
		self.assertEqual(plan["commands"][0]["current"][0]["command"], "initiate")
		self.assertEqual(
			[x["scope"] for x in plan["commands"]],
			["default", "all_private_chats", "all_group_chats", "all_chat_administrators"],
		)
		by = {x["scope"]: x for x in plan["commands"]}
		self.assertEqual(by["all_private_chats"]["action"], "set")
		for scope in ("default", "all_group_chats", "all_chat_administrators"):
			self.assertEqual((by[scope]["action"], by[scope]["recommended"]), ("delete", []))
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
		self.assertEqual([_scope_of(p) for mm, p in sets[:1]], ["all_private_chats"])
		self.assertEqual(sets[0][0], "setMyCommands")
		self.assertEqual(len(sets[0][1]["commands"]), 9)
		deleted = {_scope_of(p) for mm, p in c.calls if mm == "deleteMyCommands"}
		self.assertEqual(deleted, {"default", "all_group_chats", "all_chat_administrators"})
		self.assertEqual(
			sets[1],
			(
				"setChatMenuButton",
				{
					"menu_button": {
						"type": "web_app",
						"text": "Console",
						"web_app": {"url": "https://site.example/huf/tg-app?gw=G"},
					}
				},
			),
		)
		self.assertEqual(out["previous"]["commands"][0]["scope"], "default")
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


def _scope_of(payload):
	return (payload.get("scope") or {}).get("type", "default")


class ScopedClient(FakeClient):
	"""getMyCommands answers per scope, like Telegram's separate per-scope lists."""

	def __init__(self, lists):
		super().__init__()
		self.lists = lists

	def call(self, method, payload=None, **kw):
		if method == "getMyCommands":
			payload = dict(payload or {})
			self.calls.append((method, payload))
			return list(self.lists.get(_scope_of(payload), []))
		return super().call(method, payload, **kw)


STALE = [{"command": "initiate", "description": "old"}]
PLAN_PRIVATE = [
	{"command": c["command"], "description": c["description"]}
	for c in m.RECOMMENDED_COMMANDS["all_private_chats"]
]


class TestStaleScopes(Base):
	def apply(self, lists, url="https://site.example", **kw):
		c = ScopedClient(lists)
		p1, p2 = self.patch(c, url)
		with p1 as mocks, p2:
			out = m.apply_recommended_setup("G", confirm=1, **kw)
		return out, c, mocks

	def test_stale_private_list_replaced(self):
		out, c, _ = self.apply({"all_private_chats": STALE})
		sets = {_scope_of(p): p for mm, p in c.calls if mm == "setMyCommands"}
		self.assertEqual(
			[x["command"] for x in sets["all_private_chats"]["commands"]],
			[x["command"] for x in PLAN_PRIVATE],
		)
		undo = [x for x in out["previous"]["commands"] if x["scope"] == "all_private_chats"][0]
		self.assertEqual(undo["action"], "set")
		self.assertEqual(undo["commands"], STALE)

	def test_stale_group_admin_list_deleted_with_undo(self):
		out, c, mocks = self.apply({"all_chat_administrators": STALE})
		deletes = [p for mm, p in c.calls if mm == "deleteMyCommands"]
		self.assertEqual(deletes, [{"scope": {"type": "all_chat_administrators"}}])
		self.assertFalse(
			[1 for mm, p in c.calls if mm == "setMyCommands" and _scope_of(p) == "all_chat_administrators"]
		)
		undo = [x for x in out["previous"]["commands"] if x["scope"] == "all_chat_administrators"][0]
		self.assertEqual(undo["action"], "delete")
		self.assertEqual(undo["commands"], STALE)
		self.assertIn("all_chat_administrators:delete", mocks["_audit_setup"].call_args[0][2])

	def test_plan_shows_old_new_and_action_per_scope(self):
		c = ScopedClient({"all_private_chats": STALE, "all_chat_administrators": STALE})
		p1, p2 = self.patch(c)
		with p1, p2:
			out = m.recommended_setup("G")
		by = {x["scope"]: x for x in out["plan"]["commands"]}
		self.assertEqual(
			(by["all_private_chats"]["action"], by["all_private_chats"]["current"]), ("set", STALE)
		)
		self.assertEqual(
			(by["all_chat_administrators"]["action"], by["all_chat_administrators"]["recommended"]),
			("delete", []),
		)
		self.assertEqual(by["all_group_chats"]["action"], "keep")
		self.assertTrue(out["plan"]["replaces_existing_commands"])

	def test_unchanged_scopes_not_touched(self):
		out, c, _ = self.apply({"all_private_chats": PLAN_PRIVATE})
		touched = {_scope_of(p) for mm, p in c.calls if mm == "setMyCommands"}
		self.assertEqual(touched, set())
		self.assertFalse([1 for mm, _ in c.calls if mm in ("deleteMyCommands", "setMyCommands")])
		by = {
			x["scope"]: x["action"]
			for x in m.plan_recommended_setup(
				ScopedClient({"all_private_chats": PLAN_PRIVATE}), "G", "https://s"
			)["commands"]
		}
		self.assertEqual(by["all_private_chats"], "keep")
		self.assertEqual(by["all_chat_administrators"], "keep")
		self.assertEqual(by["default"], "keep")

	def test_group_and_default_scopes_advertise_nothing(self):
		for scope in ("default", "all_group_chats", "all_chat_administrators"):
			self.assertEqual(m.RECOMMENDED_COMMANDS[scope], [])

	def test_private_descriptions_state_who_can_use_them(self):
		by = {c["command"]: c["description"] for c in m.PRIVATE_COMMANDS}
		self.assertIn("(admins)", by["audit"])
		for name in ("help", "me", "find", "open", "approvals", "digest", "unbind"):
			self.assertIn("(linked accounts)", by[name])
		self.assertIn("code", by["start"])
		self.assertTrue(all(1 <= len(d) <= 256 for d in by.values()))

	def test_language_scoped_lists_warn_in_plan(self):
		class LangClient(ScopedClient):
			def call(self, method, payload=None, **kw):
				if method == "getMyCommands" and (payload or {}).get("language_code") == "de":
					self.calls.append((method, dict(payload)))
					return list(STALE)
				return super().call(method, payload, **kw)

		c = LangClient({})
		p1, p2 = self.patch(c)
		with p1, p2, mock.patch.object(m, "_plan_languages", lambda: ["de", "en"]):
			plan = m.recommended_setup("G")["plan"]
		self.assertEqual(len(plan["warnings"]), 1)
		self.assertIn("all_private_chats/de", plan["warnings"][0])
		self.assertNotIn("/en", plan["warnings"][0])
		self.assertIn("specific chat", plan["limitation"])

	def test_no_language_lists_no_warning(self):
		c = ScopedClient({})
		p1, p2 = self.patch(c)
		with p1, p2, mock.patch.object(m, "_plan_languages", lambda: ["en"]):
			self.assertEqual(m.recommended_setup("G")["plan"]["warnings"], [])

	def test_menu_url_and_me_url_share_one_builder(self):
		from huf.ai import telegram_public_url as pu

		self.assertEqual(pu.mini_app_url("G", "https://s/"), "https://s/huf/tg-app?gw=G")
		self.assertEqual(pu.mini_app_url("a b", "https://s"), "https://s/huf/tg-app?gw=a%20b")

	def test_audit_in_private_list(self):
		names = [c["command"] for c in m.RECOMMENDED_COMMANDS["all_private_chats"]]
		self.assertEqual(
			names, ["start", "help", "me", "find", "open", "approvals", "digest", "audit", "unbind"]
		)
		self.assertEqual(m.RECOMMENDED_COMMANDS["default"], [])
		self.assertLessEqual(len(names), 100)

	def test_https_rule_still_blocks_stale_scope_changes(self):
		c = ScopedClient({"all_chat_administrators": STALE, "all_private_chats": STALE})
		out, _, _ = self.apply(
			{"all_chat_administrators": STALE, "all_private_chats": STALE}, url="http://127.0.0.1:8000"
		)
		self.assertEqual(out["error"], "invalid")
		self.assertIn("https", out["message"])
		self.assertFalse([1 for mm, _ in c.calls if mm.startswith(("set", "delete"))])
