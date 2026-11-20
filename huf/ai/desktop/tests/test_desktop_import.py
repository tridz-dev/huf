# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for huf.ai.desktop_import (publishing a Huf Desktop conversation).

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.desktop.tests.test_desktop_import
"""

import json
import uuid

import frappe

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from huf.ai import desktop_import as di
from huf.testing import desktop_test_helpers as h


def _msgs(*pairs):
	return [{"client_message_id": f"m{i}", "role": r, "content": c} for i, (r, c) in enumerate(pairs, 1)]


class TestDesktopImport(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Unique per test: IntegrationTestCase rolls back per class, not per test, so a shared id would leak
		# imported conversations/messages between tests (order-dependent failures).
		self.cid = str(uuid.uuid4())

	def tearDown(self):
		frappe.set_user("Administrator")

	def _import(self, messages, key="k1", **kw):
		return di.import_conversation(self.cid, key, json.dumps(messages), title="T", **kw)

	def test_capabilities(self):
		caps = di.import_conversation_capabilities()
		self.assertEqual(caps["import_conversation"], 1)

	def test_import_creates_conversation_and_ordered_messages(self):
		r = self._import(_msgs(("user", "hi"), ("assistant", "hello")))
		self.assertTrue(r["created"])
		self.assertEqual((r["imported"], r["skipped"]), (2, 0))
		rows = frappe.get_all(
			"Agent Message",
			{"conversation": r["conversation_id"]},
			["content", "role", "is_agent_message"],
			order_by="conversation_index",
		)
		self.assertEqual([x.content for x in rows], ["hi", "hello"])
		self.assertEqual([x.role for x in rows], ["user", "agent"])

	def test_replay_is_a_noop(self):
		a = self._import(_msgs(("user", "hi"), ("assistant", "hello")))
		b = self._import(_msgs(("user", "hi"), ("assistant", "hello")))
		self.assertEqual(a["conversation_id"], b["conversation_id"])
		self.assertEqual((b["created"], b["imported"], b["skipped"]), (False, 0, 2))
		self.assertEqual(frappe.db.count("Agent Message", {"conversation": a["conversation_id"]}), 2)

	def test_append_after_watermark(self):
		a = self._import(_msgs(("user", "hi")))
		more = [{"client_message_id": "m9", "role": "assistant", "content": "later"}]
		b = self._import(more, key="k2", conversation_id=a["conversation_id"])
		self.assertEqual(b["conversation_id"], a["conversation_id"])
		self.assertEqual(b["imported"], 1)
		self.assertEqual(frappe.db.get_value("Agent Conversation", a["conversation_id"], "total_messages"), 2)

	def test_partial_overlap_only_inserts_new(self):
		self._import(_msgs(("user", "hi")))
		r = self._import(_msgs(("user", "hi"), ("assistant", "new")), key="k2")
		self.assertEqual((r["imported"], r["skipped"]), (1, 1))

	def test_rejects_tool_roles_empty_and_oversized(self):
		for bad in (
			[{"client_message_id": "x", "role": "tool", "content": "c"}],
			[{"client_message_id": "x", "role": "user", "content": "  "}],
			[],
			[{"client_message_id": "x", "role": "user", "content": "a" * (di.MAX_CONTENT_CHARS + 1)}],
			_msgs(*[("user", "a")] * (di.MAX_MESSAGES + 1)),
		):
			with self.assertRaises(frappe.ValidationError):
				self._import(bad)

	def test_users_are_isolated(self):
		a = self._import(_msgs(("user", "mine")))
		frappe.set_user(h.make_user("dximp"))
		# Same client id + a hint pointing at the other user's conversation: still a fresh copy.
		b = self._import(_msgs(("user", "theirs")), conversation_id=a["conversation_id"])
		self.assertNotEqual(a["conversation_id"], b["conversation_id"])
		self.assertTrue(b["created"])
		# The other user can neither delete nor see it through this API.
		out = di.delete_imported_conversation(a["conversation_id"], self.cid)
		self.assertFalse(out["deleted"])
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Agent Conversation", a["conversation_id"]))
		self.assertEqual(frappe.db.count("Agent Message", {"conversation": a["conversation_id"]}), 1)

	def test_huf_user_cannot_delete_without_delete_permission(self):
		frappe.set_user(h.make_user("dximp"))
		a = self._import(_msgs(("user", "hi")))
		self.assertEqual(di.import_conversation_capabilities()["delete_imported"], 0)
		with self.assertRaises(frappe.PermissionError):
			di.delete_imported_conversation(a["conversation_id"], self.cid)
		self.assertTrue(frappe.db.exists("Agent Conversation", a["conversation_id"]))

	def test_conversation_with_matching_external_id_but_other_channel_is_not_imported(self):
		normal = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": "n",
				"session_id": "s-ext",
				"channel": "Chat",
				"external_id": di.EXTERNAL_PREFIX + self.cid,
			}
		).insert()
		self.assertFalse(di.delete_imported_conversation(normal.name, self.cid)["deleted"])
		self.assertTrue(frappe.db.exists("Agent Conversation", normal.name))
		r = self._import(_msgs(("user", "hi")))
		self.assertNotEqual(r["conversation_id"], normal.name)

	def test_rejects_bad_ids_and_total_size(self):
		with self.assertRaises(frappe.ValidationError):
			di.import_conversation("bad id!", "k", json.dumps(_msgs(("user", "a"))))
		half = "a" * (di.MAX_REQUEST_CHARS // 2 + 1)
		with self.assertRaises(frappe.ValidationError):
			self._import(_msgs(("user", half), ("assistant", half)))
		with self.assertRaises(frappe.ValidationError):
			self._import("{not json")

	def test_response_shape(self):
		r = self._import(_msgs(("user", "hi")))
		self.assertIs(r["success"], True)
		self.assertIsInstance(r["conversation_id"], str)
		self.assertEqual(set(r["message_ids"]), {"m1"})
		self.assertEqual(r["idempotency_key"], "k1")
		self.assertEqual(
			frappe.db.get_value("Agent Conversation", r["conversation_id"], "channel"), di.CHANNEL
		)

	def test_delete_only_deletes_imported_conversation(self):
		a = self._import(_msgs(("user", "hi")))
		self.assertFalse(di.delete_imported_conversation("SOMETHING-ELSE", self.cid)["deleted"])
		self.assertTrue(frappe.db.exists("Agent Conversation", a["conversation_id"]))
		self.assertTrue(di.delete_imported_conversation(a["conversation_id"], self.cid)["deleted"])
		self.assertFalse(frappe.db.exists("Agent Conversation", a["conversation_id"]))
		# idempotent
		self.assertFalse(di.delete_imported_conversation(a["conversation_id"], self.cid)["deleted"])

	def test_delete_refuses_a_normal_conversation(self):
		normal = frappe.get_doc(
			{"doctype": "Agent Conversation", "title": "n", "session_id": "s-1", "channel": "Chat"}
		).insert()
		self.assertFalse(di.delete_imported_conversation(normal.name, self.cid)["deleted"])
		self.assertTrue(frappe.db.exists("Agent Conversation", normal.name))
