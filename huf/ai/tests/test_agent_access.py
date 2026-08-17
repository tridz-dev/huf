"""
Unit tests for huf.ai.agent_access.check_agent_access.

These are pure unit tests against the helper function using
unittest.mock — they do not require a live Frappe site/bench. Only the
specific frappe APIs the helper calls (frappe.get_roles) are mocked.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_access
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.agent_access import check_agent_access


def _make_agent(
    owner="owner@example.com",
    allow_guest=False,
    allowed_users=None,
    allowed_roles=None,
):
    return SimpleNamespace(
        owner=owner,
        allow_guest=allow_guest,
        allowed_users=[SimpleNamespace(user=u) for u in (allowed_users or [])],
        allowed_roles=[SimpleNamespace(role=r) for r in (allowed_roles or [])],
    )


class TestCheckAgentAccess(unittest.TestCase):
    def test_owner_always_allowed_regardless_of_allowlists(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["someone-else@example.com"],
            allowed_roles=["Some Role"],
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]):
            self.assertTrue(check_agent_access(agent_doc, "owner@example.com"))

    def test_system_manager_always_allowed_regardless_of_allowlists(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["someone-else@example.com"],
            allowed_roles=["Some Role"],
        )
        with patch(
            "huf.ai.agent_access.frappe.get_roles",
            return_value=["System Manager"],
        ):
            self.assertTrue(check_agent_access(agent_doc, "admin@example.com"))

    def test_guest_allowed_when_allow_guest_true_even_with_allowlists(self):
        agent_doc = _make_agent(
            allow_guest=True,
            allowed_users=["someone@example.com"],
            allowed_roles=["Some Role"],
        )
        # frappe.get_roles must not even be consulted for Guest.
        with patch("huf.ai.agent_access.frappe.get_roles") as mock_get_roles:
            self.assertTrue(check_agent_access(agent_doc, "Guest"))
            mock_get_roles.assert_not_called()

    def test_guest_denied_when_allow_guest_false(self):
        agent_doc = _make_agent(allow_guest=False)
        with patch("huf.ai.agent_access.frappe.get_roles") as mock_get_roles:
            self.assertFalse(check_agent_access(agent_doc, "Guest"))
            mock_get_roles.assert_not_called()

    def test_both_allowlists_empty_allows_any_non_guest_user(self):
        agent_doc = _make_agent(
            owner="owner@example.com", allowed_users=[], allowed_roles=[]
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=["Some Role"]):
            self.assertTrue(check_agent_access(agent_doc, "random@example.com"))

    def test_user_in_allowed_users_is_allowed(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["allowed@example.com"],
            allowed_roles=[],
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]):
            self.assertTrue(check_agent_access(agent_doc, "allowed@example.com"))

    def test_user_not_in_allowed_users_and_no_allowed_roles_denied(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["allowed@example.com"],
            allowed_roles=[],
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]):
            self.assertFalse(check_agent_access(agent_doc, "other@example.com"))

    def test_user_holding_allowed_role_is_allowed(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=[],
            allowed_roles=["Special Role"],
        )
        with patch(
            "huf.ai.agent_access.frappe.get_roles",
            return_value=["Special Role", "Some Other Role"],
        ):
            self.assertTrue(check_agent_access(agent_doc, "someone@example.com"))

    def test_user_without_matching_role_denied(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=[],
            allowed_roles=["Special Role"],
        )
        with patch(
            "huf.ai.agent_access.frappe.get_roles",
            return_value=["Unrelated Role"],
        ):
            self.assertFalse(check_agent_access(agent_doc, "someone@example.com"))


if __name__ == "__main__":
    unittest.main()
