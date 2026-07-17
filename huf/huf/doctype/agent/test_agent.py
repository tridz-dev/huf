# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


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

        # Simulate an existing document by setting a previous value and changing the field
        agent._doc_before_save = frappe.new_doc("Agent")
        agent._doc_before_save.name = "__test_tamper_agent__"
        agent._doc_before_save.is_system = 0
        agent.is_system = 1

        with self.assertRaises(frappe.ValidationError):
            agent._validate_system_field_tamper()
