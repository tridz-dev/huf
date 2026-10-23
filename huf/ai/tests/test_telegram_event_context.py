# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""agent_event_context: the Telegram per-message ids line (WP-CONTEXT)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import provider_hooks, telegram_agent_context_hooks
from huf.ai.gateway_adapters import telegram_agent_context as tac


def ev(raw, **kw):
	return SimpleNamespace(
		raw_payload=raw, conversation_id=kw.get("conversation_id", ""), thread_id=kw.get("thread_id")
	)


class TestEventContext(unittest.TestCase):
	def test_basic(self):
		raw = {
			"message": {
				"message_id": 5,
				"chat": {"id": -100, "type": "group"},
				"from": {"first_name": "Ann", "last_name": "<b>Lee]"},
			}
		}
		line = tac.event_context(ev(raw))
		self.assertEqual(line, "Current message: chat_id=-100, message_id=5, sender=Ann bLee")

	def test_forum_thread(self):
		raw = {
			"message": {
				"message_id": 5,
				"message_thread_id": 9,
				"is_topic_message": True,
				"chat": {"id": -100, "type": "supergroup"},
			}
		}
		self.assertIn("thread_id=9", tac.event_context(ev(raw)))

	def test_fallback_to_event_fields(self):
		line = tac.event_context(ev(None, conversation_id="12", thread_id="7"))
		self.assertEqual(line, "Current message: chat_id=12, message_id=7")

	def test_malformed_safe(self):
		for raw in (None, "x", [], {"message": "x"}, {"message": {"chat": 3}}):
			self.assertEqual(tac.event_context(ev(raw)), "")
		self.assertEqual(tac.event_context(None), "")

	def test_no_secrets(self):
		raw = {"message": {"message_id": 5, "chat": {"id": 1}, "text": "123456:SECRET-TOKEN-XYZ"}}
		self.assertNotIn("SECRET", tac.event_context(ev(raw)))

	def test_hook_registered(self):
		hook = provider_hooks.get("Telegram", "agent_event_context")
		self.assertIs(hook, telegram_agent_context_hooks.agent_event_context)
		self.assertTrue(hook(ev({"message": {"message_id": 1, "chat": {"id": 2}}}), None))
