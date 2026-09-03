# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for the ``frontend_tool_call_initiated`` realtime publish in
huf.ai.client_side_tool.client_side_function.

That event is broadcast on the ``conversation:<conversation_id>`` socket.io
room, whose name is guessable by construction - any authenticated client
that learns/guesses a conversation_id could subscribe to it. Without
``frappe.publish_realtime(..., user=...)`` scoping, the event (and any UI
dialog it triggers) would be delivered to every subscriber of that room,
not just the conversation's owner (see ST-R6.6c / WP-R6 research finding
R6-frontend_realtime.md). These tests pin:

1. the publish call always carries a ``user=`` kwarg;
2. that value is the conversation's owner, looked up from the DB rather
   than taken from ``frappe.session.user`` -- this call can run from a
   queue-first background worker, where the session user would be the
   worker's service account rather than the human who should see the
   dialog;
3. a fallback to ``frappe.session.user`` when the owner can't be resolved,
   so the event still gets scoped to *someone* rather than left
   unscoped/broadcast.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_client_side_tool_realtime_scoping
"""

import unittest
from unittest import mock

from huf.ai import client_side_tool


class TestFrontendToolCallInitiatedRealtimeScoping(unittest.TestCase):
	def _run(self, owner):
		fake_call = mock.MagicMock()
		fake_call.name = "Agent Tool Call-0001"

		fake_cache = mock.MagicMock()
		fake_cache.blpop.return_value = ("key", '{"result": {}}')

		with mock.patch.object(client_side_tool, "_get_or_create_call", return_value=fake_call), \
			mock.patch.object(client_side_tool.frappe, "session") as mock_session, \
			mock.patch.object(client_side_tool.frappe, "cache", return_value=fake_cache), \
			mock.patch.object(client_side_tool.frappe, "publish_realtime") as mock_publish, \
			mock.patch.object(client_side_tool.frappe, "db") as mock_db:
			mock_session.user = "worker@service.local"
			mock_db.get_value.return_value = owner

			client_side_tool.client_side_function(
				conversation_id="conv-1",
				agent_run_id="run-1",
				function_name="do_thing",
				message_id="msg-1",
				call_id="call-1",
			)

		return mock_publish, mock_db

	def test_publish_scoped_to_conversation_owner(self):
		mock_publish, mock_db = self._run(owner="owner@example.com")

		mock_publish.assert_called_once()
		_, kwargs = mock_publish.call_args
		self.assertEqual(kwargs.get("user"), "owner@example.com")
		self.assertEqual(kwargs["message"]["type"], "frontend_tool_call_initiated")
		mock_db.get_value.assert_called_once_with("Agent Conversation", "conv-1", "owner")

	def test_publish_falls_back_to_session_user_when_owner_unresolved(self):
		mock_publish, _ = self._run(owner=None)

		mock_publish.assert_called_once()
		_, kwargs = mock_publish.call_args
		self.assertEqual(kwargs.get("user"), "worker@service.local")

	def test_publish_always_carries_user_kwarg(self):
		"""Regression pin: a future edit must not drop ``user=`` entirely."""
		mock_publish, _ = self._run(owner="owner@example.com")

		_, kwargs = mock_publish.call_args
		self.assertIn("user", kwargs)
		self.assertTrue(kwargs["user"])


if __name__ == "__main__":
	unittest.main()
