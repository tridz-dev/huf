"""Unit tests for Email Gateway Adapter signature verification (ST-04.2d)."""

import unittest

from huf.ai.gateway_adapters.email import EmailGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest


class TestEmailGatewayAdapter(unittest.TestCase):
    """Test Email adapter fail-closed behavior on missing/invalid secrets."""

    def test_verify_inbound_rejects_missing_secret_when_configured(self):
        """When webhook_secret is configured, missing header must return False."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={},  # No X-Webhook-Secret header
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_rejects_unconfigured_secret(self):
        """When webhook_secret is not configured, must return False."""
        adapter = EmailGatewayAdapter({})  # No credentials

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={"X-Webhook-Secret": "somesecret"},
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_accepts_valid_secret_in_header(self):
        """Valid secret in X-Webhook-Secret header must be accepted."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={"X-Webhook-Secret": "mysecret"},
            query={},
            method="POST",
        )

        self.assertTrue(adapter.verify_inbound(request))

    def test_verify_inbound_accepts_valid_secret_in_query(self):
        """Valid secret in query parameter 'secret' must be accepted."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={},
            query={"secret": "mysecret"},
            method="POST",
        )

        self.assertTrue(adapter.verify_inbound(request))

    def test_verify_inbound_rejects_wrong_secret(self):
        """Wrong secret must be rejected (constant-time comparison)."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={"X-Webhook-Secret": "wrongsecret"},
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_rejects_empty_secret_in_request(self):
        """Empty secret in request must be rejected."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={"X-Webhook-Secret": ""},
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_header_takes_precedence_over_query(self):
        """X-Webhook-Secret header should be used if present."""
        adapter = EmailGatewayAdapter({"webhook_secret": "mysecret"})

        # Header has correct secret, query has wrong secret
        request = GatewayInboundRequest(
            body=b'{"from": "user@example.com", "body": "test"}',
            headers={"X-Webhook-Secret": "mysecret"},
            query={"secret": "wrongsecret"},
            method="POST",
        )

        self.assertTrue(adapter.verify_inbound(request))
