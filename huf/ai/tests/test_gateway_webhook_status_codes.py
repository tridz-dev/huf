"""GW-09: handle_gateway_webhook must return a non-2xx status on every failure path.

Before this fix every branch of ``huf.ai.gateway_webhook.handle_gateway_webhook``
returned HTTP 200 with an ``{"success": False, ...}`` body on missing/wrong
signature, unknown gateway, and disabled gateway -- indistinguishable from a
success response to anything that checks the transport status code (load
balancers, provider retry logic, monitoring). These tests assert
``frappe.local.response.http_status_code`` is set to the right non-2xx value
on each failure branch, exercised through a couple of representative provider
adapters (Discord's own ``gateways/discord.py`` module already did this
correctly and is used here as the baseline pattern; this file covers the
shared ``gateway_webhook`` bridge and its Slack/VK-style adapter path) as well
as the generic "no gateway_name" case.
"""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook


class FakeResponse:
    def __init__(self):
        self.http_status_code = 200


class TestGatewayWebhookStatusCodes(unittest.TestCase):
    @patch("huf.ai.gateway_webhook.frappe")
    def test_missing_gateway_name_is_400(self, mock_frappe):
        mock_frappe.request = SimpleNamespace(args={})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())

        result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": False, "error": "Missing gateway_name"}
        assert mock_frappe.local.response.http_status_code == 400

    @patch("huf.ai.gateway_webhook.frappe")
    def test_unknown_gateway_is_404(self, mock_frappe):
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Nope"})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())
        mock_frappe.DoesNotExistError = Exception
        mock_frappe.get_doc.side_effect = mock_frappe.DoesNotExistError

        result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": False, "error": "Unknown gateway"}
        assert mock_frappe.local.response.http_status_code == 404

    @patch("huf.ai.gateway_webhook.frappe")
    def test_disabled_gateway_is_403(self, mock_frappe):
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support Slack"})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())
        mock_frappe.get_doc.return_value = SimpleNamespace(
            name="Support Slack", provider="Slack", is_enabled=0
        )

        result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": False, "error": "Gateway is disabled"}
        assert mock_frappe.local.response.http_status_code == 403

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_wrong_signature_slack_is_401(self, mock_frappe, mock_request, mock_adapter):
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support Slack"})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())
        mock_frappe.get_doc.return_value = SimpleNamespace(
            name="Support Slack", provider="Slack", is_enabled=1
        )
        mock_request.return_value = SimpleNamespace(method="POST")
        adapter = MagicMock()
        adapter.verify_inbound.return_value = False
        mock_adapter.return_value = adapter

        result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": False, "error": "Provider verification failed"}
        assert mock_frappe.local.response.http_status_code == 401
        adapter.normalize_inbound.assert_not_called()

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_missing_signature_vk_is_401(self, mock_frappe, mock_request, mock_adapter):
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support VK"})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())
        mock_frappe.get_doc.return_value = SimpleNamespace(
            name="Support VK", provider="VK", is_enabled=1
        )
        mock_request.return_value = SimpleNamespace(method="POST")
        adapter = MagicMock()
        adapter.verify_inbound.return_value = False
        mock_adapter.return_value = adapter

        result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": False, "error": "Provider verification failed"}
        assert mock_frappe.local.response.http_status_code == 401

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_verified_event_stays_default_2xx(self, mock_frappe, mock_request, mock_adapter):
        """A successful call must not be touched -- no regression on the happy path."""
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support VK"})
        mock_frappe.local = SimpleNamespace(response=FakeResponse())
        configured_gateway = SimpleNamespace(name="Support VK", provider="VK", is_enabled=1)
        mock_frappe.get_doc.return_value = configured_gateway
        fake_request = SimpleNamespace(method="POST")
        mock_request.return_value = fake_request
        normalized = SimpleNamespace(
            provider_event_id="event-1",
            sender_id="42",
            conversation_id="2000000001",
            thread_id="123",
            message_text="hello",
            is_room=True,
            mentioned=False,
            raw_payload={"type": "message_new"},
        )
        adapter = MagicMock()
        adapter.verify_inbound.return_value = True
        adapter.normalize_inbound.return_value = normalized
        mock_adapter.return_value = adapter

        with patch("huf.ai.gateway_service.ingest_gateway_event", return_value={"event_name": "GE-1"}):
            result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": True, "event_name": "GE-1"}
        assert mock_frappe.local.response.http_status_code == 200


if __name__ == "__main__":
    unittest.main()
