# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import telegram_ingest as ing


class TestUpdateHandlerRegistry(unittest.TestCase):
	def setUp(self):
		self._saved = dict(ing._UPDATE_HANDLERS)

	def tearDown(self):
		ing._UPDATE_HANDLERS.clear()
		ing._UPDATE_HANDLERS.update(self._saved)

	def _parsed(self, kind):
		parsed = MagicMock()
		parsed.kind = kind
		parsed.bot_blocked = False
		parsed.bot_unblocked = False
		return parsed

	def test_kind_handler_response_is_returned(self):
		adapter = MagicMock()
		adapter.parse_update.return_value = self._parsed("inline_query")
		ing.register_update_handler("inline_query", lambda g, a, p, r: {"success": True, "handled": "inline"})
		with patch.object(ing, "classify", return_value="other"):
			self.assertEqual(
				ing.handle_update(MagicMock(), adapter, MagicMock()), {"success": True, "handled": "inline"}
			)

	def test_none_from_handler_falls_through_to_ack(self):
		adapter = MagicMock()
		adapter.parse_update.return_value = self._parsed("chat_join_request")
		ing.register_update_handler("chat_join_request", lambda g, a, p, r: None)
		with patch.object(ing, "classify", return_value="membership"):
			result = ing.handle_update(MagicMock(), adapter, MagicMock())
		self.assertTrue(result["success"])

	def test_category_handler_used_when_no_kind_handler(self):
		adapter = MagicMock()
		adapter.parse_update.return_value = self._parsed("business_message")
		ing.register_update_handler("business", lambda g, a, p, r: {"success": True, "handled": "biz"})
		with patch.object(ing, "classify", return_value="business"):
			self.assertEqual(ing.handle_update(MagicMock(), adapter, MagicMock())["handled"], "biz")


class TestRawKeyDispatch(unittest.TestCase):
	def setUp(self):
		self._saved = dict(ing._UPDATE_HANDLERS)

	def tearDown(self):
		ing._UPDATE_HANDLERS.clear()
		ing._UPDATE_HANDLERS.update(self._saved)

	def test_unsupported_kind_dispatches_on_the_raw_update_key(self):
		adapter = MagicMock()
		parsed = MagicMock()
		parsed.kind = "unsupported"
		parsed.bot_blocked = False
		parsed.bot_unblocked = False
		parsed.raw = {"update_id": 9, "stopped_message_generation": {"chat": {"id": 1}}}
		adapter.parse_update.return_value = parsed
		ing.register_update_handler("stopped_message_generation", lambda g, a, p, r: {"success": True, "stopped": 1})
		with patch.object(ing, "classify", return_value="other"):
			self.assertEqual(ing.handle_update(MagicMock(), adapter, MagicMock())["stopped"], 1)
