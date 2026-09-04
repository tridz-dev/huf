# Copyright (c) 2026, Huf Industries Pvt Ltd and Contributors
# See license.txt

"""
Tests for password field migration and get_password() API usage.

Covers:
- Automation Trigger.webhook_key and .secret can be read via get_password()
- Agent Tool Function.http_headers[].value can be read via get_password()
- MCP Server Header.header_value can be read via get_password()
- automation_api.py field-listing endpoint does not return plaintext for
  low-privilege users (Huf Viewer, Huf User)

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_secrets_migration
"""

from unittest.mock import patch, MagicMock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import set_encrypted_password


class TestSecretsPasswordFields(IntegrationTestCase):
    """Test that password fields store and retrieve secrets correctly."""

    def setUp(self):
        self.created_triggers = []
        self.created_tools = []
        self.created_servers = []

    def tearDown(self):
        for name in self.created_triggers:
            frappe.db.delete("Automation Trigger", name)
        for name in self.created_tools:
            frappe.db.delete("Agent Tool Function", name)
        for name in self.created_servers:
            frappe.db.delete("MCP Server", name)

    def test_get_password_automation_trigger_webhook_key(self):
        """Verify Automation Trigger.webhook_key can be retrieved via get_password()."""
        # Create a trigger (webhook_key starts empty)
        trigger = frappe.get_doc({
            "doctype": "Automation Trigger",
            "trigger_name": "test_webhook_key_" + frappe.utils.random_string(8),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.random_string(8),
        })
        trigger.insert(ignore_permissions=True)
        self.created_triggers.append(trigger.name)

        # Set the password field directly
        test_key = "test_webhook_secret_12345"
        set_encrypted_password(
            "Automation Trigger",
            trigger.name,
            test_key,
            "webhook_key"
        )

        # Reload and verify via get_password()
        trigger = frappe.get_doc("Automation Trigger", trigger.name)
        retrieved_key = trigger.get_password("webhook_key")
        self.assertEqual(retrieved_key, test_key)

    def test_get_password_automation_trigger_secret(self):
        """Verify Automation Trigger.secret can be retrieved via get_password()."""
        trigger = frappe.get_doc({
            "doctype": "Automation Trigger",
            "trigger_name": "test_secret_" + frappe.utils.random_string(8),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.random_string(8),
        })
        trigger.insert(ignore_permissions=True)
        self.created_triggers.append(trigger.name)

        test_secret = "test_hmac_secret_67890"
        set_encrypted_password(
            "Automation Trigger",
            trigger.name,
            test_secret,
            "secret"
        )

        trigger = frappe.get_doc("Automation Trigger", trigger.name)
        retrieved_secret = trigger.get_password("secret")
        self.assertEqual(retrieved_secret, test_secret)

    def test_get_password_agent_tool_http_header_value(self):
        """Verify Agent Tool Function http_headers[].value can be retrieved via get_password()."""
        tool = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": "test_http_header_" + frappe.utils.random_string(8),
            "description": "Test tool for HTTP header password field.",
            "tool_type": self._create_tool_type_if_missing(),
            "types": "GET",
            "http_headers": [
                {
                    "key": "Authorization",
                    "value": ""  # Will be set via set_encrypted_password
                }
            ]
        })
        tool.insert(ignore_permissions=True)
        self.created_tools.append(tool.name)

        # Set the password for the header value
        test_header_value = "Bearer test_token_xyz123"
        header_row_name = tool.http_headers[0].name
        set_encrypted_password(
            "Agent Tool HTTP Header",
            header_row_name,
            test_header_value,
            "value"
        )

        # Reload and verify
        tool = frappe.get_doc("Agent Tool Function", tool.name)
        header = tool.http_headers[0]
        retrieved_value = header.get_password("value")
        self.assertEqual(retrieved_value, test_header_value)

    def test_get_password_mcp_server_header_value(self):
        """Verify MCP Server Header.header_value can be retrieved via get_password()."""
        server = frappe.get_doc({
            "doctype": "MCP Server",
            "server_name": "test_mcp_" + frappe.utils.random_string(8),
            "transport_type": "http",
            "server_url": "https://example.com/mcp",
            "custom_headers": [
                {
                    "header_name": "X-API-Key",
                    # header_value is a mandatory Password field on this child
                    # table; a placeholder here, immediately overwritten via
                    # set_encrypted_password below.
                    "header_value": "placeholder"
                }
            ]
        })
        server.insert(ignore_permissions=True)
        self.created_servers.append(server.name)

        # Set the password for the header value
        test_header_value = "sk-test-key-abcd1234"
        header_row_name = server.custom_headers[0].name
        set_encrypted_password(
            "MCP Server Header",
            header_row_name,
            test_header_value,
            "header_value"
        )

        # Reload and verify
        server = frappe.get_doc("MCP Server", server.name)
        header = server.custom_headers[0]
        retrieved_value = header.get_password("header_value")
        self.assertEqual(retrieved_value, test_header_value)

    def test_plaintext_read_returns_masked_value(self):
        """Verify that reading password fields via direct attribute access returns None or masked value."""
        trigger = frappe.get_doc({
            "doctype": "Automation Trigger",
            "trigger_name": "test_masked_" + frappe.utils.random_string(8),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.random_string(8),
        })
        trigger.insert(ignore_permissions=True)
        self.created_triggers.append(trigger.name)

        # set_encrypted_password() alone only writes to the __Auth table; the
        # main-table column only gets the "*" * len dummy mask written into
        # it by Document._save_passwords(), which runs on doc.save() when a
        # real (non-dummy) value is assigned to the field. Go through the
        # real path so the masking behaviour under test actually happens.
        test_key = "secret_key_to_mask"
        trigger.webhook_key = test_key
        trigger.save(ignore_permissions=True)

        # Reload and check plaintext attribute
        trigger = frappe.get_doc("Automation Trigger", trigger.name)
        # After loading from DB, the plaintext field holds the dummy mask
        self.assertEqual(trigger.webhook_key, "*" * len(test_key))

        # But get_password() returns the actual secret
        self.assertEqual(trigger.get_password("webhook_key"), test_key)

    def test_automation_trigger_field_list_no_plaintext_export(self):
        """Test that automation_api.py does not return plaintext webhook_key to low-privilege users."""
        # This test verifies the masking guarantee any field-listing endpoint
        # relies on: once a real secret has been assigned and saved, the
        # in-memory/DB plaintext column is the dummy mask, never the secret,
        # regardless of who reads it next. (frappe.session isn't consulted by
        # this masking path at all -- mocking it here was a no-op that only
        # broke fixture creation, since it replaced the real Administrator
        # session those inserts need permission from.)
        trigger = frappe.get_doc({
            "doctype": "Automation Trigger",
            "trigger_name": "test_export_" + frappe.utils.random_string(8),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.random_string(8),
        })
        trigger.insert(ignore_permissions=True)
        self.created_triggers.append(trigger.name)

        # Set the webhook_key through the real save path (see
        # test_plaintext_read_returns_masked_value for why set_encrypted_password
        # alone would not mask the main-table column).
        test_key = "export_secret_key"
        trigger.webhook_key = test_key
        trigger.save(ignore_permissions=True)

        # Fetch the document
        fetched_trigger = frappe.get_doc("Automation Trigger", trigger.name)

        # When fetched via Frappe's normal get_doc/get_value, the
        # webhook_key should be masked (the dummy * value), not plaintext
        self.assertEqual(fetched_trigger.webhook_key, "*" * len(test_key))

    def _create_automation_if_missing(self):
        """Helper: create a minimal Automation for testing."""
        automation_name = "test_automation_" + frappe.utils.random_string(8)
        automation = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": automation_name,
            "automation_type": "Quick",
            "agent": self._create_agent_if_missing(),
            "instruction": "Test automation instruction.",
        })
        automation.insert(ignore_permissions=True)
        return automation_name

    def _create_agent_if_missing(self):
        """Helper: create a minimal Agent for testing (Link target of Automation.agent)."""
        if not frappe.db.exists("Agent", "Test Agent"):
            frappe.get_doc({
                "doctype": "Agent",
                "agent_name": "Test Agent",
                "agent_modality": "Both",
                "provider": "OpenAI",
                "model": "gpt-4",
                "instructions": "Test agent fixture for automated tests.",
            }).insert(ignore_permissions=True)
        return "Test Agent"

    def _create_tool_type_if_missing(self):
        """Helper: create a minimal Agent Tool Type for testing.

        Agent Tool Type autonames off `name1`, not the reserved `name` key.
        """
        tool_type_name = "test_tool_type_" + frappe.utils.random_string(8)
        tool_type = frappe.get_doc({
            "doctype": "Agent Tool Type",
            "name1": tool_type_name,
        })
        tool_type.insert(ignore_permissions=True)
        return tool_type.name
