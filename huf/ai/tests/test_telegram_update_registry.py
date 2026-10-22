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


class TestDuplicateUpdates(unittest.TestCase):
	def test_second_delivery_of_the_same_update_is_acked_without_running_handlers(self):
		adapter = MagicMock()
		parsed = MagicMock()
		parsed.kind = "inline_query"
		parsed.update_id = "555"
		parsed.bot_blocked = False
		parsed.bot_unblocked = False
		parsed.raw = {"update_id": 555, "inline_query": {}}
		adapter.parse_update.return_value = parsed
		calls = []
		saved = dict(ing._UPDATE_HANDLERS)
		ing._UPDATE_HANDLERS["inline_query"] = lambda g, a, p, r: calls.append(1) or {"success": True}
		gateway = MagicMock()
		gateway.name = "GW"
		try:
			with patch.object(ing, "classify", return_value="other"), patch.object(
				ing, "_first_delivery", side_effect=[True, False]
			):
				first = ing.handle_update(gateway, adapter, MagicMock())
				second = ing.handle_update(gateway, adapter, MagicMock())
		finally:
			ing._UPDATE_HANDLERS.clear()
			ing._UPDATE_HANDLERS.update(saved)
		self.assertTrue(first["success"])
		self.assertEqual(len(calls), 1)
		self.assertTrue(second["success"])


class TestFailedHandlerReleasesClaim(unittest.TestCase):
	def test_handler_exception_releases_the_dedup_claim_and_reraises(self):
		adapter = MagicMock()
		parsed = MagicMock()
		parsed.kind = "inline_query"
		parsed.update_id = "556"
		parsed.bot_blocked = False
		parsed.bot_unblocked = False
		parsed.raw = {"update_id": 556, "inline_query": {}}
		adapter.parse_update.return_value = parsed

		def boom(*args):
			raise RuntimeError("handler failed")

		saved = dict(ing._UPDATE_HANDLERS)
		ing._UPDATE_HANDLERS["inline_query"] = boom
		gateway = MagicMock()
		gateway.name = "GW"
		try:
			with patch.object(ing, "classify", return_value="other"), patch.object(
				ing, "_first_delivery", return_value=True
			), patch.object(ing, "_release_delivery") as release:
				with self.assertRaises(RuntimeError):
					ing.handle_update(gateway, adapter, MagicMock())
		finally:
			ing._UPDATE_HANDLERS.clear()
			ing._UPDATE_HANDLERS.update(saved)
		release.assert_called_once_with("GW", "556")
