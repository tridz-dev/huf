"""
Unit tests for the Agent Procedure Binding / Agent Procedure Run
permission_query_conditions hooks (ST-R6.1d).

Fix for the same defect pattern as F-02: Huf User / Huf Manager hold
create+write on these two DocTypes but had no if_owner restriction and no
permission_query_conditions hook, so any authenticated user could read or
list another user's bindings/runs via the list/report views. These tests
assert the fix: non-privileged users are filtered to their own records,
System Managers see everything.

These are pure unit tests against the helper functions using
unittest.mock -- they do not require a live Frappe site/bench. Only the
specific frappe APIs the helpers call (frappe.session.user, frappe.get_roles,
frappe.db.escape, and huf.permissions.has_capability) are mocked.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_permission_query_conditions
"""
import unittest
from unittest.mock import patch, MagicMock

from huf.huf.doctype.agent_procedure_binding.agent_procedure_binding import (
    get_permission_query_conditions as binding_pqc,
)
from huf.huf.doctype.agent_procedure_run.agent_procedure_run import (
    get_permission_query_conditions as run_pqc,
)


class _BasePQCTest(unittest.TestCase):
    module_path = None  # override
    table_name = None  # override

    def _call(self, fn, user, *, roles, has_capability_result):
        with patch(f"{self.module_path}.frappe.session") as mock_session, patch(
            f"{self.module_path}.frappe.get_roles", return_value=roles
        ) as mock_get_roles, patch(
            f"{self.module_path}.frappe.db.escape", side_effect=lambda v: f"'{v}'"
        ), patch(
            "huf.permissions.has_capability", return_value=has_capability_result
        ) as mock_has_capability:
            mock_session.user = "session-fallback@example.com"
            result = fn(user)
        return result, mock_get_roles, mock_has_capability


class TestAgentProcedureBindingPQC(_BasePQCTest):
    module_path = "huf.huf.doctype.agent_procedure_binding.agent_procedure_binding"
    table_name = "Agent Procedure Binding"

    def test_non_privileged_user_is_filtered_to_own_records(self):
        result, mock_get_roles, mock_has_capability = self._call(
            binding_pqc,
            "user@example.com",
            roles=["Huf User"],
            has_capability_result=False,
        )
        mock_get_roles.assert_called_once_with("user@example.com")
        mock_has_capability.assert_called_once_with("user@example.com", "agent.view_all")
        self.assertEqual(
            result,
            f"`tab{self.table_name}`.owner = 'user@example.com'",
        )

    def test_system_manager_sees_all_records_no_filter(self):
        result, mock_get_roles, mock_has_capability = self._call(
            binding_pqc,
            "admin@example.com",
            roles=["System Manager"],
            has_capability_result=False,
        )
        self.assertIsNone(result)
        # has_capability must not even be consulted once System Manager is confirmed.
        mock_has_capability.assert_not_called()

    def test_user_with_view_all_capability_sees_all_records(self):
        result, _, mock_has_capability = self._call(
            binding_pqc,
            "manager@example.com",
            roles=["Huf Manager"],
            has_capability_result=True,
        )
        self.assertIsNone(result)
        mock_has_capability.assert_called_once_with("manager@example.com", "agent.view_all")

    def test_falls_back_to_session_user_when_user_not_passed(self):
        result, mock_get_roles, _ = self._call(
            binding_pqc,
            None,
            roles=["Huf User"],
            has_capability_result=False,
        )
        mock_get_roles.assert_called_once_with("session-fallback@example.com")
        self.assertEqual(
            result,
            f"`tab{self.table_name}`.owner = 'session-fallback@example.com'",
        )


class TestAgentProcedureRunPQC(_BasePQCTest):
    module_path = "huf.huf.doctype.agent_procedure_run.agent_procedure_run"
    table_name = "Agent Procedure Run"

    def test_non_privileged_user_is_filtered_to_own_records(self):
        result, mock_get_roles, mock_has_capability = self._call(
            run_pqc,
            "user@example.com",
            roles=["Huf User"],
            has_capability_result=False,
        )
        mock_get_roles.assert_called_once_with("user@example.com")
        mock_has_capability.assert_called_once_with("user@example.com", "agent.view_all")
        self.assertEqual(
            result,
            f"`tab{self.table_name}`.owner = 'user@example.com'",
        )

    def test_system_manager_sees_all_records_no_filter(self):
        result, mock_get_roles, mock_has_capability = self._call(
            run_pqc,
            "admin@example.com",
            roles=["System Manager"],
            has_capability_result=False,
        )
        self.assertIsNone(result)
        mock_has_capability.assert_not_called()

    def test_user_with_view_all_capability_sees_all_records(self):
        result, _, mock_has_capability = self._call(
            run_pqc,
            "manager@example.com",
            roles=["Huf Manager"],
            has_capability_result=True,
        )
        self.assertIsNone(result)
        mock_has_capability.assert_called_once_with("manager@example.com", "agent.view_all")


if __name__ == "__main__":
    unittest.main()
