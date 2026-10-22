# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram typing indicator: hook owner, gate, addressed rule, thread id, log line, failures, delegation."""

from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import provider_hooks, telegram_ingest as ing, telegram_ingest_hooks
from huf.ai.gateway_adapters import telegram_pipeline as tp, telegram_pipeline_hooks
from huf.ai.gateway_adapters.telegram_client import TelegramApiError


class FakeGateway(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)


def gateway(**kw):
	base = {"name": "gw1", "provider": "Telegram", "typing_indicator": 1, "mention_required": 0}
	base.update(kw)
	return FakeGateway(**base)


def event(chat_type="private", message=None, chat_id="111", **meta):
	msg = dict(message or {"text": "hi"})
	raw = {"telegram_meta": {"chat_type": chat_type, **meta}, "message": msg}
	return SimpleNamespace(raw_payload=raw, conversation_id=chat_id, get=lambda k, d=None: raw)


class FakeCache:
	def __init__(self):
		self.store = {}

	def get_value(self, key):
		return self.store.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value


class TypingCase(unittest.TestCase):
	def setUp(self):
		self.sender = mock.Mock()
		self.adapter = SimpleNamespace(sender=self.sender)
		patcher = mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=self.adapter)
		patcher.start()
		self.addCleanup(patcher.stop)
		logger_patch = mock.patch.object(ing, "frappe")
		self.frappe = logger_patch.start()
		self.addCleanup(logger_patch.stop)
		self.log = self.frappe.logger.return_value
		cache_patch = mock.patch("frappe.cache", return_value=FakeCache())
		cache_patch.start()
		self.addCleanup(cache_patch.stop)


class TestHookSelection(unittest.TestCase):
	def test_ingest_typing_is_the_active_hook_with_real_import_order(self):
		# telegram_hooks imports pipeline hooks first, then ingest hooks; the later registration wins.
		import huf.ai.gateway_adapters.telegram_hooks  # noqa: F401

		active = provider_hooks.get("Telegram", "typing")
		self.assertIs(active, telegram_ingest_hooks.typing)

	def test_reimport_order_does_not_change_owner(self):
		importlib.reload(telegram_pipeline_hooks)
		importlib.reload(telegram_ingest_hooks)
		self.assertIs(provider_hooks.get("Telegram", "typing"), telegram_ingest_hooks.typing)


class TestTypingPolicy(TypingCase):
	def test_private_sends_typing_without_thread(self):
		self.assertTrue(ing.send_typing_for_event(event(), gateway()))
		self.sender.send_chat_action.assert_called_once_with("111", "typing", thread_id=None)

	def test_gate_off_sends_nothing(self):
		self.assertFalse(ing.send_typing_for_event(event(), gateway(typing_indicator=0)))
		self.sender.send_chat_action.assert_not_called()

	def test_group_not_addressed_sends_nothing(self):
		ev = event("supergroup", chat_id="-100", message={"text": "hello all"})
		self.assertFalse(ing.send_typing_for_event(ev, gateway(mention_required=1)))
		self.sender.send_chat_action.assert_not_called()

	def test_group_addressed_by_mention_sends(self):
		msg = {"text": "@bot hi", "entities": [{"type": "mention", "offset": 0, "length": 4}]}
		ev = event("supergroup", chat_id="-100", message=msg)
		self.assertTrue(ing.send_typing_for_event(ev, gateway(mention_required=1)))
		self.sender.send_chat_action.assert_called_once_with("-100", "typing", thread_id=None)

	def test_channel_never_sends(self):
		self.assertFalse(ing.send_typing_for_event(event("channel", chat_id="-200"), gateway()))
		self.sender.send_chat_action.assert_not_called()


class TestThreadId(TypingCase):
	def test_forum_topic_sends_thread_id(self):
		msg = {"text": "hi", "message_thread_id": 5, "is_topic_message": True, "chat": {"type": "supergroup"}}
		ev = event("supergroup", chat_id="-100", message=msg, message_thread_id="5")
		ing.send_typing_for_event(ev, gateway())
		self.sender.send_chat_action.assert_called_once_with("-100", "typing", thread_id="5")

	def test_plain_reply_chain_omits_thread_id(self):
		# Non-forum supergroups carry message_thread_id on reply chains; Telegram rejects it for chat actions.
		msg = {"text": "hi", "message_thread_id": 9, "chat": {"type": "supergroup"}}
		ev = event("supergroup", chat_id="-100", message=msg, message_thread_id="9")
		ing.send_typing_for_event(ev, gateway(mention_required=0))
		self.sender.send_chat_action.assert_called_once_with("-100", "typing", thread_id=None)

	def test_private_topic_sends_thread_id(self):
		msg = {"text": "hi", "message_thread_id": 7, "chat": {"type": "private"}}
		ev = event("private", message=msg, message_thread_id="7")
		ing.send_typing_for_event(ev, gateway())
		self.sender.send_chat_action.assert_called_once_with("111", "typing", thread_id="7")


class TestLogAndFailure(TypingCase):
	def test_success_logs_one_line_without_token(self):
		ing.send_typing_for_event(event(), gateway())
		self.log.debug.assert_called_once_with("Telegram typing sent chat=111 action=typing")
		self.log.info.assert_not_called()

	def test_blocked_failure_is_logged_and_non_fatal(self):
		self.sender.send_chat_action.side_effect = TelegramApiError(
			"sendChatAction", "Forbidden: bot was blocked by the user", error_code=403
		)
		self.assertFalse(ing.send_typing_for_event(event(), gateway()))
		self.log.warning.assert_called_once_with("Telegram typing failed chat=111 action=typing type=blocked")
		self.log.info.assert_not_called()

	def test_unexpected_exception_is_non_fatal(self):
		self.sender.send_chat_action.side_effect = RuntimeError("boom")
		self.assertFalse(ing.send_typing_for_event(event(), gateway()))
		self.log.warning.assert_called_once_with(
			"Telegram typing failed chat=111 action=typing type=RuntimeError"
		)

	def test_unreadable_update_is_non_fatal(self):
		broken = SimpleNamespace(raw_payload=None, conversation_id="111", get=lambda k, d=None: None)
		with mock.patch.object(ing, "_raw", side_effect=RuntimeError("bad")):
			self.assertFalse(ing.send_typing_for_event(broken, gateway()))
		self.sender.send_chat_action.assert_not_called()


class TestPipelineDelegates(TypingCase):
	def test_pipeline_send_typing_uses_single_owner(self):
		self.assertTrue(tp.send_typing(gateway(), event()))
		self.sender.send_chat_action.assert_called_once_with("111", "typing", thread_id=None)

	def test_pipeline_send_typing_never_raises(self):
		with mock.patch.object(ing, "send_typing_for_event", side_effect=RuntimeError("x")):
			self.assertFalse(tp.send_typing(gateway(), event()))


if __name__ == "__main__":
	unittest.main()
