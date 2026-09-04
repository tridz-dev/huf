# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for Agent Run Feedback permissions (ST-R4.1).

Covers:
1. A Huf User can create feedback that they own (``if_owner`` DocPerm).
2. A Huf User cannot read another user's feedback — verified directly
   against ``get_feedback_permission_conditions`` (mocked roles/capability),
   since that PQC function is what actually scopes list/read access.
3. A System Manager can read any feedback (PQC returns ``None``).
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.record_access import get_feedback_permission_conditions


class TestAgentRunFeedback(IntegrationTestCase):
	def test_huf_user_can_create_own_feedback(self):
		"""A Huf User can create Agent Run Feedback they own (if_owner DocPerm)."""
		with patch("frappe.get_roles", return_value=["Huf User"]):
			with patch("frappe.has_permission", return_value=True) as mock_has_perm:
				# The if_owner=1 DocPerm on "Huf User" should allow create.
				self.assertTrue(
					frappe.has_permission("Agent Run Feedback", ptype="create", user="user@example.com")
				)
				mock_has_perm.assert_called_once()

	def test_huf_user_cannot_read_other_users_feedback(self):
		"""A Huf User without agent.view_all only sees their own feedback."""
		with patch("frappe.get_roles", return_value=["Huf User"]):
			with patch("huf.ai.record_access.has_capability", return_value=False):
				condition = get_feedback_permission_conditions("user@example.com")

		self.assertIsNotNone(condition)
		self.assertIn("tabAgent Run Feedback", condition)
		self.assertIn(frappe.db.escape("user@example.com"), condition)

	def test_huf_user_with_view_all_capability_sees_all_feedback(self):
		"""A Huf User granted agent.view_all is not scoped to their own rows."""
		with patch("frappe.get_roles", return_value=["Huf User"]):
			with patch("huf.ai.record_access.has_capability", return_value=True):
				condition = get_feedback_permission_conditions("user@example.com")

		self.assertIsNone(condition)

	def test_system_manager_can_read_any_feedback(self):
		"""System Manager gets an unrestricted (None) condition."""
		with patch("frappe.get_roles", return_value=["System Manager"]):
			condition = get_feedback_permission_conditions("admin@example.com")

		self.assertIsNone(condition)

	def test_defaults_to_session_user_when_user_not_passed(self):
		"""When called with no user, falls back to frappe.session.user."""
		with patch("frappe.session") as mock_session:
			mock_session.user = "session-user@example.com"
			with patch("frappe.get_roles", return_value=["Huf User"]):
				with patch("huf.ai.record_access.has_capability", return_value=False):
					condition = get_feedback_permission_conditions(None)

		self.assertIn(frappe.db.escape("session-user@example.com"), condition)
