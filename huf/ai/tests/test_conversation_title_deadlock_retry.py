"""Tests for the MariaDB deadlock retry wrapper around conversation title updates.

See ``huf.ai.agent_integration._set_conversation_title_with_retry``: the
background title-generation job can race the main request thread writing to
the same ``Agent Conversation`` row, occasionally tripping a MariaDB
deadlock. The wrapper retries once (by default) before giving up.
"""

import unittest
from unittest.mock import patch

import frappe

from huf.ai.agent_integration import _set_conversation_title_with_retry


class TestConversationTitleDeadlockRetry(unittest.TestCase):
	@patch("time.sleep", return_value=None)
	@patch("huf.ai.agent_integration.frappe.db.set_value")
	def test_retries_once_on_deadlock_then_succeeds(self, mock_set_value, mock_sleep):
		# First call raises a deadlock, second call succeeds.
		mock_set_value.side_effect = [frappe.QueryDeadlockError("Deadlock found"), None]

		_set_conversation_title_with_retry("CONV-0001", "Some Title")

		self.assertEqual(mock_set_value.call_count, 2)
		mock_set_value.assert_called_with("Agent Conversation", "CONV-0001", "title", "Some Title")
		mock_sleep.assert_called_once()

	@patch("time.sleep", return_value=None)
	@patch("huf.ai.agent_integration.frappe.db.set_value")
	def test_no_retry_when_first_attempt_succeeds(self, mock_set_value, mock_sleep):
		mock_set_value.return_value = None

		_set_conversation_title_with_retry("CONV-0001", "Some Title")

		self.assertEqual(mock_set_value.call_count, 1)
		mock_sleep.assert_not_called()

	@patch("time.sleep", return_value=None)
	@patch("huf.ai.agent_integration.frappe.db.set_value")
	def test_raises_after_exhausting_retries(self, mock_set_value, mock_sleep):
		# Every attempt deadlocks; with max_retries=2 that's exactly 2 attempts
		# (1 initial + 1 retry) before the exception propagates.
		mock_set_value.side_effect = frappe.QueryDeadlockError("Deadlock found")

		with self.assertRaises(frappe.QueryDeadlockError):
			_set_conversation_title_with_retry("CONV-0001", "Some Title", max_retries=2)

		self.assertEqual(mock_set_value.call_count, 2)
		mock_sleep.assert_called_once()

	@patch("time.sleep", return_value=None)
	@patch("huf.ai.agent_integration.frappe.db.set_value")
	def test_non_deadlock_errors_are_not_retried(self, mock_set_value, mock_sleep):
		# Any other exception type should propagate immediately without
		# consuming a retry attempt.
		mock_set_value.side_effect = ValueError("unrelated failure")

		with self.assertRaises(ValueError):
			_set_conversation_title_with_retry("CONV-0001", "Some Title")

		self.assertEqual(mock_set_value.call_count, 1)
		mock_sleep.assert_not_called()


if __name__ == "__main__":
	unittest.main()
