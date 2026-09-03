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
    allow_all_users=False,
):
    return SimpleNamespace(
        owner=owner,
        allow_guest=allow_guest,
        allow_all_users=allow_all_users,
        allowed_users=[SimpleNamespace(user=u) for u in (allowed_users or [])],
        allowed_roles=[SimpleNamespace(role=r) for r in (allowed_roles or [])],
    )


def _no_capabilities(*args, **kwargs):
    return False


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

    def test_both_allowlists_empty_and_allow_all_users_true_allows_any_non_guest_user(self):
        agent_doc = _make_agent(
            owner="owner@example.com", allowed_users=[], allowed_roles=[], allow_all_users=True
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=["Some Role"]), patch(
            "huf.permissions.has_capability", side_effect=_no_capabilities
        ):
            self.assertTrue(check_agent_access(agent_doc, "random@example.com"))

    def test_both_allowlists_empty_and_allow_all_users_false_denies_non_owner(self):
        agent_doc = _make_agent(
            owner="owner@example.com", allowed_users=[], allowed_roles=[], allow_all_users=False
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=["Some Role"]), patch(
            "huf.permissions.has_capability", side_effect=_no_capabilities
        ):
            self.assertFalse(check_agent_access(agent_doc, "random@example.com"))

    def test_user_in_allowed_users_is_allowed(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["allowed@example.com"],
            allowed_roles=[],
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", side_effect=_no_capabilities
        ):
            self.assertTrue(check_agent_access(agent_doc, "allowed@example.com"))

    def test_user_not_in_allowed_users_and_no_allowed_roles_denied(self):
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=["allowed@example.com"],
            allowed_roles=[],
        )
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", side_effect=_no_capabilities
        ):
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
        ), patch("huf.permissions.has_capability", side_effect=_no_capabilities):
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
        ), patch("huf.permissions.has_capability", side_effect=_no_capabilities):
            self.assertFalse(check_agent_access(agent_doc, "someone@example.com"))

    def test_allow_all_users_field_defaults_false(self):
        """New agents default to allow_all_users=False (closed by default).

        frappe.get_doc({...}) on a plain dict does NOT apply DocType field
        defaults -- only frappe.new_doc() (and .insert()) run the
        default-value pipeline, so this test uses frappe.new_doc.
        """
        import frappe

        agent = frappe.new_doc("Agent")
        self.assertEqual(agent.allow_all_users, 0)

    def test_capability_holder_sees_and_can_open_closed_agent(self):
        """A holder of agent.view_all can both list and open/run a closed agent.

        Mirrors get_permission_query_conditions's capability short-circuit
        (huf/huf/doctype/agent/agent.py) so list visibility and single-record
        access agree for every capability holder, on both open and closed
        agents.
        """
        agent_doc = _make_agent(
            owner="owner@example.com",
            allowed_users=[],
            allowed_roles=[],
            allow_all_users=False,
        )

        def _capable(user, capability):
            return capability == "agent.view_all"

        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", side_effect=_capable
        ):
            self.assertTrue(check_agent_access(agent_doc, "capable-user@example.com"))

        with patch(
            "huf.huf.doctype.agent.agent.frappe.get_roles", return_value=[]
        ), patch("huf.permissions.has_capability", side_effect=_capable):
            from huf.huf.doctype.agent.agent import get_permission_query_conditions

            conditions = get_permission_query_conditions("capable-user@example.com")
            self.assertEqual(conditions, "`tabAgent`.is_system = 0")


class TestSetAllowAllUsersForExistingAgentsPatch(unittest.TestCase):
    """Pure-mock test for the ST-R2.2 migration patch's execute()."""

    def test_agents_with_empty_lists_are_marked_allow_all_users(self):
        from huf.patches.v1 import set_allow_all_users_for_existing_agents as patch_module

        # "agent-open" has neither Agent User nor Agent Role rows -> migrate.
        # "agent-users" has an Agent User row -> leave untouched.
        # "agent-roles" has an Agent Role row -> leave untouched.
        def fake_get_all(doctype, pluck=None, distinct=None, filters=None):
            if doctype == "Agent User":
                return ["agent-users"]
            if doctype == "Agent Role":
                return ["agent-roles"]
            if doctype == "Agent":
                return ["agent-open", "agent-users", "agent-roles"]
            raise AssertionError(f"unexpected doctype {doctype}")

        set_value_calls = []

        with patch.object(
            patch_module.frappe.db, "has_column", return_value=True
        ), patch.object(
            patch_module.frappe, "get_all", side_effect=fake_get_all
        ), patch.object(
            patch_module.frappe.db,
            "set_value",
            side_effect=lambda *a, **k: set_value_calls.append((a, k)),
        ), patch.object(patch_module.frappe.db, "commit"):
            patch_module.execute()

        self.assertEqual(len(set_value_calls), 1)
        args, kwargs = set_value_calls[0]
        self.assertEqual(args[0], "Agent")
        self.assertEqual(args[1], "agent-open")
        self.assertEqual(args[2], "allow_all_users")
        self.assertEqual(args[3], 1)


if __name__ == "__main__":
    unittest.main()
