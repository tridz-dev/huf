# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""CONTEXT-2: outbound message ids are recorded and gate agent edit/delete inside gateway runs."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.gateway_adapters import telegram_agent_context as tac
from huf.ai.gateway_adapters import telegram_messages as tm
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.tests.test_telegram_tools_more import Base, FakeCache
from huf.ai.tools import telegram as tool


class TestRecord(unittest.TestCase):
	def setUp(self):
		self.c = FakeCache()

	def test_record_and_cap(self):
		for i in range(1, 41):
			tm.record_outbound("gw", "9", [i], text="x" * 200, cache=self.c)
		rows = tm.outbound_for_chat("gw", "9", cache=self.c)
		self.assertEqual(len(rows), 30)
		self.assertEqual(rows[-1]["message_id"], 40)
		self.assertEqual(len(rows[0]["text_preview"]), 80)
		self.assertEqual(set(rows[0]), {"message_id", "kind", "text_preview", "time"})
		self.assertEqual(tm.last_outbound_id("gw", "9", cache=self.c), 40)
		self.assertTrue(tm.is_outbound("gw", "9", "40", cache=self.c))
		self.assertFalse(tm.is_outbound("gw", "9", 1, cache=self.c))
		self.assertFalse(tm.is_outbound("gw", "8", 40, cache=self.c))
		self.assertFalse(tm.is_outbound("gw", "9", "abc", cache=self.c))

	def test_record_sent_also_records_outbound(self):
		tm.record_sent("gw", "9", "EV", [3], kind="voice", cache=self.c)
		self.assertEqual(tm.outbound_for_chat("gw", "9", cache=self.c)[0]["kind"], "voice")

	def test_cache_failure_safe(self):
		class Bad:
			def get_value(self, k):
				raise RuntimeError

			def set_value(self, *a, **k):
				raise RuntimeError

		tm.record_outbound("gw", "9", [1], cache=Bad())
		self.assertEqual(tm.outbound_for_chat("gw", "9", cache=Bad()), [])


class TestPipeline(unittest.TestCase):
	def test_on_part_gets_text(self):
		class S:
			def send_text(self, chat, part, **kw):
				return [{"message_id": 11}]

		seen = []
		tp.send_parts_with(
			S(), "9", ["hello"], on_part=lambda ids, kind, text: seen.append((ids, kind, text))
		)
		self.assertEqual(seen, [([11], "text", "hello")])


class TestEventContextLine(unittest.TestCase):
	def test_previous_message(self):
		ev = SimpleNamespace(
			raw_payload={"message": {"message_id": 5, "chat": {"id": 9}}},
			gateway="gw",
			conversation_id="9",
			thread_id=None,
		)
		c = FakeCache()
		with patch.object(tm, "_cache", return_value=c):
			self.assertNotIn("previous", tac.event_context(ev))
			tm.record_outbound("gw", "9", [77], cache=c)
			self.assertIn("Your previous message: id=77", tac.event_context(ev))


class TestToolAllowList(Base):
	def setUp(self):
		super().setUp()
		patch.object(tool.scope, "run_gateway", return_value="gw").start()
		patch.object(tool.scope, "current_chat", return_value="9").start()
		patch.object(tool.scope, "check_recipient", return_value=None).start()
		patch.object(tool.scope, "claim_send", return_value=None).start()
		patch.object(tool.scope, "release_send").start()
		patch.object(tm, "_cache", return_value=self.cache).start()

	def test_edit_delete_refused_for_unknown_ids(self):
		for act in ("edit_message_text", "delete_message"):
			r = self.run_action(action=act, message_id=5, **({"text": "x"} if act == "edit_message_text" else {}))
			self.assertEqual(r["error"], "action_not_permitted", r)
		self.assertEqual(self.api.calls, [])

	def test_edit_allowed_after_record(self):
		tm.record_outbound("gw", "9", [5], cache=self.cache)
		r = self.run_action(action="edit_message_text", message_id=5, text="x")
		self.assertTrue(r["success"], r)

	def test_tool_send_records_id_then_listable(self):
		r = self.run_action(action="send_message", text="hello there")
		self.assertTrue(r["success"], r)
		rows = tm.outbound_for_chat("gw", "9", cache=self.cache)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["text_preview"], "hello there")
		with patch.object(tool.frappe, "get_all", return_value=[]):
			out = self.run_action(action="list_messages")
		item = out["results"]["items"][0]
		self.assertEqual((item["direction"], item["id"]), ("outbound", str(rows[0]["message_id"])))
		self.assertTrue(self.run_action(action="delete_message", message_id=rows[0]["message_id"])["success"])

	def test_owner_run_unchanged(self):
		tool.scope.run_gateway.return_value = ""
		r = self.run_action(action="delete_message", chat_id="9", message_id=5)
		self.assertTrue(r["success"], r)


if __name__ == "__main__":
	unittest.main()
