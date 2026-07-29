# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Regression tests for MCP OAuth connection flow.

These tests verify that `resolve_and_start_oauth_flow` is the single,
consistent entry point for both manual OAuth and Dynamic Client
Registration (DCR) flows, and that it does not duplicate validation or
prematurely reject either authentication model.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Mock frappe before importing the module under test so pure logic can be
# exercised without a full Frappe bench.
frappe_mock = types.ModuleType("frappe")
frappe_mock.utils = MagicMock()
frappe_mock.utils.get_url = MagicMock(return_value="https://huf.example.com")
frappe_mock.has_permission = MagicMock(return_value=True)
frappe_mock.get_doc = MagicMock()
frappe_mock.session = MagicMock()
frappe_mock.session.user = "Administrator"
frappe_mock.local = MagicMock()
frappe_mock.local.site = "huf.example.com"
frappe_mock.cache = MagicMock()
frappe_mock.db = MagicMock()
frappe_mock.log_error = MagicMock()
frappe_mock.throw = MagicMock(side_effect=Exception("Permission denied"))
frappe_mock._ = lambda x: x
frappe_mock.whitelist = MagicMock(return_value=lambda fn: fn)
sys.modules["frappe"] = frappe_mock

from huf.ai.mcp_oauth import (
    _has_manual_oauth_config,
    resolve_and_start_oauth_flow,
)


class MockServer:
    """Minimal stand-in for an MCP Server document."""

    def __init__(
        self,
        name: str,
        oauth_client_id: str = "",
        oauth_authorization_endpoint: str = "",
        oauth_token_endpoint: str = "",
        oauth_client_secret: str = "",
    ):
        self.name = name
        self.oauth_client_id = oauth_client_id
        self.oauth_authorization_endpoint = oauth_authorization_endpoint
        self.oauth_token_endpoint = oauth_token_endpoint
        self.oauth_client_secret = oauth_client_secret


class TestHasManualOAuthConfig(unittest.TestCase):
    def test_complete_manual_config(self):
        server = MockServer(
            "manual-server",
            oauth_client_id="client-123",
            oauth_authorization_endpoint="https://idp.example.com/authorize",
            oauth_token_endpoint="https://idp.example.com/token",
        )
        self.assertTrue(_has_manual_oauth_config(server))

    def test_missing_client_id(self):
        server = MockServer(
            "missing-client-id",
            oauth_authorization_endpoint="https://idp.example.com/authorize",
            oauth_token_endpoint="https://idp.example.com/token",
        )
        self.assertFalse(_has_manual_oauth_config(server))

    def test_missing_authorization_endpoint(self):
        server = MockServer(
            "missing-auth-endpoint",
            oauth_client_id="client-123",
            oauth_token_endpoint="https://idp.example.com/token",
        )
        self.assertFalse(_has_manual_oauth_config(server))

    def test_missing_token_endpoint(self):
        server = MockServer(
            "missing-token-endpoint",
            oauth_client_id="client-123",
            oauth_authorization_endpoint="https://idp.example.com/authorize",
        )
        self.assertFalse(_has_manual_oauth_config(server))

    def test_client_secret_not_required(self):
        """PKCE public clients do not require a client_secret."""
        server = MockServer(
            "pkce-public-client",
            oauth_client_id="client-123",
            oauth_authorization_endpoint="https://idp.example.com/authorize",
            oauth_token_endpoint="https://idp.example.com/token",
            oauth_client_secret="",
        )
        self.assertTrue(_has_manual_oauth_config(server))


class TestResolveAndStartOAuthFlow(unittest.TestCase):
    def setUp(self):
        frappe_mock.get_doc.reset_mock()

    @patch("huf.ai.mcp_oauth.start_oauth_flow")
    @patch("huf.ai.mcp_oauth.discover_mcp_server")
    def test_manual_config_skips_discovery(
        self, mock_discover, mock_start_oauth
    ):
        """When a complete manual OAuth config exists, discovery is skipped."""
        server = MockServer(
            "manual-server",
            oauth_client_id="manual-client-id",
            oauth_authorization_endpoint="https://idp.example.com/authorize",
            oauth_token_endpoint="https://idp.example.com/token",
        )
        frappe_mock.get_doc.return_value = server
        mock_start_oauth.return_value = {"auth_url": "https://idp.example.com/authorize?client_id=manual-client-id"}

        result = resolve_and_start_oauth_flow("manual-server")

        mock_discover.assert_not_called()
        mock_start_oauth.assert_called_once_with("manual-server")
        self.assertIn("auth_url", result)

    @patch("huf.ai.mcp_oauth.start_oauth_flow")
    @patch("huf.ai.mcp_oauth.discover_mcp_server")
    def test_incomplete_manual_config_triggers_discovery(
        self, mock_discover, mock_start_oauth
    ):
        """When manual config is incomplete, discovery is attempted."""
        server = MockServer(
            "partial-server",
            oauth_client_id="manual-client-id",
            oauth_authorization_endpoint="",
            oauth_token_endpoint="",
        )
        frappe_mock.get_doc.return_value = server
        mock_discover.return_value = {
            "discovery_status": "Ready",
            "client_id": "dynamic-client-id",
        }
        mock_start_oauth.return_value = {"auth_url": "https://idp.example.com/authorize?client_id=dynamic-client-id"}

        result = resolve_and_start_oauth_flow("partial-server")

        mock_discover.assert_called_once_with("partial-server")
        mock_start_oauth.assert_called_once_with("partial-server")
        self.assertIn("auth_url", result)

    @patch("huf.ai.mcp_oauth.start_oauth_flow")
    @patch("huf.ai.mcp_oauth.discover_mcp_server")
    def test_discovery_failure_returns_error(
        self, mock_discover, mock_start_oauth
    ):
        """When discovery fails and no manual config exists, return the discovery error."""
        server = MockServer("dynamic-only-server")
        frappe_mock.get_doc.return_value = server
        mock_discover.return_value = {
            "discovery_status": "Failed",
            "discovery_error": "Dynamic Client Registration is not available for this server.",
        }

        result = resolve_and_start_oauth_flow("dynamic-only-server")

        mock_discover.assert_called_once_with("dynamic-only-server")
        mock_start_oauth.assert_not_called()
        self.assertIn("error", result)
        self.assertIn("Dynamic Client Registration", result["error"])

    @patch("huf.ai.mcp_oauth.start_oauth_flow")
    @patch("huf.ai.mcp_oauth.discover_mcp_server")
    def test_dynamic_registration_success(
        self, mock_discover, mock_start_oauth
    ):
        """A server with no manual config but successful DCR starts OAuth."""
        server = MockServer("dcr-server")
        frappe_mock.get_doc.return_value = server
        mock_discover.return_value = {
            "discovery_status": "Ready",
            "client_id": "dcr-client-id",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }
        mock_start_oauth.return_value = {"auth_url": "https://idp.example.com/authorize?client_id=dcr-client-id"}

        result = resolve_and_start_oauth_flow("dcr-server")

        mock_discover.assert_called_once_with("dcr-server")
        mock_start_oauth.assert_called_once_with("dcr-server")
        self.assertIn("auth_url", result)


if __name__ == "__main__":
    unittest.main()
