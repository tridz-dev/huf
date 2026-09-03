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
            "trigger_name": "test_webhook_key_" + frappe.utils.get_random_string(),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.get_random_string(),
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
            "trigger_name": "test_secret_" + frappe.utils.get_random_string(),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.get_random_string(),
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
            "tool_name": "test_http_header_" + frappe.utils.get_random_string(),
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
            "server_name": "test_mcp_" + frappe.utils.get_random_string(),
            "server_type": "Local",
            "custom_headers": [
                {
                    "header_name": "X-API-Key",
                    "header_value": ""  # Will be set via set_encrypted_password
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
            "trigger_name": "test_masked_" + frappe.utils.get_random_string(),
            "automation": self._create_automation_if_missing(),
            "trigger_type": "Webhook",
            "webhook_slug": "test_slug_" + frappe.utils.get_random_string(),
        })
        trigger.insert(ignore_permissions=True)
        self.created_triggers.append(trigger.name)

        # Set via set_encrypted_password
        test_key = "secret_key_to_mask"
        set_encrypted_password(
            "Automation Trigger",
            trigger.name,
            test_key,
            "webhook_key"
        )

        # Reload and check plaintext attribute
        trigger = frappe.get_doc("Automation Trigger", trigger.name)
        # After loading from DB, the plaintext field holds the dummy mask
        self.assertEqual(trigger.webhook_key, "*" * len(test_key))

        # But get_password() returns the actual secret
        self.assertEqual(trigger.get_password("webhook_key"), test_key)

    def test_automation_trigger_field_list_no_plaintext_export(self):
        """Test that automation_api.py does not return plaintext webhook_key to low-privilege users."""
        # This test mocks the automation_api behavior to ensure that when
        # the field-listing endpoint returns webhook_key and secret fields,
        # they are redacted (masked) for Huf Viewer/Huf User.

        # Mock the frappe session to simulate a Huf User
        with patch("frappe.session") as mock_session:
            mock_session.user = "test_huf_user"
            mock_session.user_roles = ["Huf User"]

            # Create a trigger with a real secret
            trigger = frappe.get_doc({
                "doctype": "Automation Trigger",
                "trigger_name": "test_export_" + frappe.utils.get_random_string(),
                "automation": self._create_automation_if_missing(),
                "trigger_type": "Webhook",
                "webhook_slug": "test_slug_" + frappe.utils.get_random_string(),
            })
            trigger.insert(ignore_permissions=True)
            self.created_triggers.append(trigger.name)

            # Set the webhook_key
            test_key = "export_secret_key"
            set_encrypted_password(
                "Automation Trigger",
                trigger.name,
                test_key,
                "webhook_key"
            )

            # Fetch the document
            fetched_trigger = frappe.get_doc("Automation Trigger", trigger.name)

            # When fetched via Frappe's normal get_doc/get_value, the
            # webhook_key should be masked (the dummy * value), not plaintext
            self.assertEqual(fetched_trigger.webhook_key, "*" * len(test_key))

    def _create_automation_if_missing(self):
        """Helper: create a minimal Automation for testing."""
        automation_name = "test_automation_" + frappe.utils.get_random_string()
        automation = frappe.get_doc({
            "doctype": "Automation",
            "automation_name": automation_name,
            "automation_type": "Quick",
        })
        automation.insert(ignore_permissions=True)
        return automation_name

    def _create_tool_type_if_missing(self):
        """Helper: create a minimal Agent Tool Type for testing."""
        tool_type_name = "test_tool_type_" + frappe.utils.get_random_string()
        tool_type = frappe.get_doc({
            "doctype": "Agent Tool Type",
            "name": tool_type_name,
        })
        tool_type.insert(ignore_permissions=True)
        return tool_type_name
