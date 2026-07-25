# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from huf.huf.doctype.agent.agent import get_permission_query_conditions

NON_MANAGER_ROLES = ["Huf User"]


class TestAgent(FrappeTestCase):
    def test_system_agent_delete_guard(self):
        """Deleting an is_system agent should be blocked outside install/migrate/uninstall."""
        agent = frappe.new_doc("Agent")
        agent.agent_name = "__test_system_agent__"
        agent.is_system = 1

        with self.assertRaises(frappe.ValidationError):
            agent.on_trash()

    def test_system_agent_rename_guard(self):
        """Renaming an is_system agent should be blocked outside install/migrate/uninstall."""
        agent = frappe.new_doc("Agent")
        agent.agent_name = "__test_system_agent__"
        agent.is_system = 1

        with self.assertRaises(frappe.ValidationError):
            agent.before_rename("__test_system_agent__", "__renamed_system_agent__")

    def test_system_agent_tamper_guard(self):
        """Non-admins cannot flip is_system on an existing agent."""
        agent = frappe.new_doc("Agent")
        agent.name = "__test_tamper_agent__"
        agent.agent_name = "__test_tamper_agent__"
        agent.is_system = 0
        # new_doc sets __islocal=1, and the guards no-op on is_new(); mark as persisted
        agent.__islocal = 0

        # Simulate an existing document by setting a previous value and changing the field
        agent._doc_before_save = frappe.new_doc("Agent")
        agent._doc_before_save.name = "__test_tamper_agent__"
        agent._doc_before_save.is_system = 0
        agent.is_system = 1

        # frappe.set_user is unreliable under run-tests (cached user doc);
        # patch roles to a deterministic non-System-Manager set instead.
        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent._validate_system_field_tamper()


class TestSystemAgentLocking(FrappeTestCase):
    """Guards for system-agent (is_system=1) locking: immutability and list hiding."""

    def _make_system_agent(self):
        """In-memory Agent that looks persisted: is_system=1 plus a before-save snapshot."""
        before = frappe.new_doc("Agent")
        before.name = "__test_system_lock__"
        before.agent_name = "__test_system_lock__"
        before.is_system = 1
        before.instructions = "original instructions"

        agent = frappe.new_doc("Agent")
        agent.name = before.name
        agent.agent_name = before.agent_name
        agent.is_system = 1
        agent.instructions = "original instructions"
        # new_doc sets __islocal=1, and the guards no-op on is_new(); mark as persisted
        agent.__islocal = 0
        agent._doc_before_save = before
        return agent

    def test_protected_field_edit_blocked_for_non_manager(self):
        """Non-System-Managers cannot edit protected fields on a system agent."""
        agent = self._make_system_agent()
        agent.instructions = "tampered instructions"

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent._validate_system_agent_immutability()

    def test_protected_field_edit_allowed_for_system_manager(self):
        """System Managers can still edit protected fields on a system agent."""
        if "System Manager" not in frappe.get_roles():
            self.skipTest("test session user is not a System Manager")

        agent = self._make_system_agent()
        agent.instructions = "manager update"
        # Must not raise
        agent._validate_system_agent_immutability()

    def test_tool_table_edit_blocked_for_non_manager(self):
        """Changing the agent_tool child table is also locked for non-managers."""
        agent = self._make_system_agent()
        agent.append("agent_tool", {"tool": "Some Tool"})

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent._validate_system_agent_immutability()

    def test_is_system_flip_blocked_for_non_manager(self):
        """Regression guard: non-managers cannot flip is_system on an existing agent."""
        agent = frappe.new_doc("Agent")
        agent.name = "__test_tamper_lock__"
        agent.agent_name = "__test_tamper_lock__"
        agent.is_system = 0
        # new_doc sets __islocal=1, and the guards no-op on is_new(); mark as persisted
        agent.__islocal = 0

        before = frappe.new_doc("Agent")
        before.name = agent.name
        before.is_system = 0
        agent._doc_before_save = before
        agent.is_system = 1

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent._validate_system_field_tamper()

    def test_permission_query_conditions_hide_system_agents(self):
        """Non-System-Manager list queries exclude system agents."""
        conditions = get_permission_query_conditions("Guest")
        self.assertIsNotNone(conditions)
        self.assertIn("`tabAgent`.is_system = 0", conditions)

    def test_permission_query_conditions_unrestricted_for_system_manager(self):
        """System Managers still see all agents (no conditions)."""
        if "System Manager" not in frappe.get_roles():
            self.skipTest("test session user is not a System Manager")
        self.assertIsNone(get_permission_query_conditions(frappe.session.user))
