"""GW-03: allowlisted Gateway webhook routes must reach app-level verification.

Frappe core's ``validate_auth`` (frappe/auth.py) raises ``AuthenticationError``
for any request whose ``Authorization`` header splits into exactly two parts
(scheme + token) unless a real user is already set, before ``allow_guest=True``
on the target whitelisted method is ever consulted. These tests exercise the
``auth_hooks`` entry point (``huf.ai.gateway_webhook.exempt_gateway_webhook_auth``)
directly, and prove that a Bearer-style Authorization header on the Bot
Framework / generic gateway webhook route, and an HMAC-style Authorization
header on the Teams Outgoing Webhook route, both result in a non-Guest
``frappe.session.user`` being set (i.e. the terminal guest check in
``validate_auth`` would pass), regardless of whether the token/HMAC value
itself is valid -- that verification is the whitelisted method's own job.
"""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook


def _fake_request(path, method="POST", headers=None):
    return SimpleNamespace(path=path, method=method, headers=headers or {})


class TestGatewayWebhookAuthExemption(unittest.TestCase):
    @patch("huf.ai.gateway_webhook._gateway_webhook_auth_user", return_value="gateway-webhook@huf.system")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_bearer_token_on_bot_framework_route_is_exempted(self, mock_frappe, mock_auth_user):
        mock_frappe.request = _fake_request("/api/method/huf.ai.gateway_webhook.handle_gateway_webhook")
        mock_frappe.get_request_header.return_value = "Bearer any-token-value"
        mock_frappe.session = SimpleNamespace(user="Guest")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_called_once_with("gateway-webhook@huf.system")

    @patch("huf.ai.gateway_webhook._gateway_webhook_auth_user", return_value="gateway-webhook@huf.system")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_hmac_token_on_teams_outgoing_webhook_route_is_exempted(self, mock_frappe, mock_auth_user):
        mock_frappe.request = _fake_request(
            "/api/method/huf.ai.tools.teams_webhook.handle_teams_outgoing_webhook"
        )
        mock_frappe.get_request_header.return_value = "HMAC any-base64-value=="
        mock_frappe.session = SimpleNamespace(user="")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_called_once_with("gateway-webhook@huf.system")

    @patch("huf.ai.gateway_webhook.frappe")
    def test_unrelated_route_is_left_alone(self, mock_frappe):
        mock_frappe.request = _fake_request("/api/method/huf.ai.some_other_endpoint")
        mock_frappe.get_request_header.return_value = "Bearer any-token-value"
        mock_frappe.session = SimpleNamespace(user="Guest")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_not_called()

    @patch("huf.ai.gateway_webhook.frappe")
    def test_already_authenticated_session_is_left_alone(self, mock_frappe):
        mock_frappe.request = _fake_request("/api/method/huf.ai.gateway_webhook.handle_gateway_webhook")
        mock_frappe.get_request_header.return_value = "Bearer any-token-value"
        mock_frappe.session = SimpleNamespace(user="some.real.user@example.com")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_not_called()

    @patch("huf.ai.gateway_webhook.frappe")
    def test_single_part_authorization_header_is_left_alone(self, mock_frappe):
        """Only the two-part scheme+token shape is what trips core's guest check."""
        mock_frappe.request = _fake_request("/api/method/huf.ai.gateway_webhook.handle_gateway_webhook")
        mock_frappe.get_request_header.return_value = "opaque-single-token"
        mock_frappe.session = SimpleNamespace(user="Guest")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_not_called()

    @patch("huf.ai.gateway_webhook.frappe")
    def test_get_requests_are_left_alone(self, mock_frappe):
        mock_frappe.request = _fake_request(
            "/api/method/huf.ai.gateway_webhook.handle_gateway_webhook", method="GET"
        )
        mock_frappe.get_request_header.return_value = "Bearer any-token-value"
        mock_frappe.session = SimpleNamespace(user="Guest")

        gateway_webhook.exempt_gateway_webhook_auth()

        mock_frappe.set_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
