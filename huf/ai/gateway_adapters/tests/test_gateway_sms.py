"""Unit tests for SMS/Twilio Gateway Adapter signature verification (ST-04.2c)."""

import unittest
from unittest.mock import MagicMock

from huf.ai.gateway_adapters.sms import SMSGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest


class TestSMSGatewayAdapter(unittest.TestCase):
    """Test SMS/Twilio adapter fail-closed behavior on missing/invalid signatures."""

    def test_verify_inbound_rejects_missing_signature_when_token_configured(self):
        """When auth_token is configured, missing X-Twilio-Signature must return False."""
        adapter = SMSGatewayAdapter({"auth_token": "test_token", "account_sid": "AC123"})

        request = GatewayInboundRequest(
            body=b"From=+1234567890&To=+0987654321&Body=Test+message",
            headers={},  # No X-Twilio-Signature header
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_accepts_frappe_sms_without_signature(self):
        """When account_sid is 'frappe_sms', signature is not required."""
        adapter = SMSGatewayAdapter({"account_sid": "frappe_sms"})

        request = GatewayInboundRequest(
            body=b"from=+1234567890&to=+0987654321&message=Test",
            headers={},  # No signature
            query={},
            method="POST",
        )

        # Should accept because frappe_sms mode doesn't require signature
        self.assertTrue(adapter.verify_inbound(request))

    def test_verify_inbound_accepts_valid_hmac_signature(self):
        """Valid HMAC-SHA1 signature must be accepted."""
        import hmac
        import hashlib
        import base64

        auth_token = "test_token"
        body = b"From=+1234567890&To=+0987654321&Body=Hello"

        # Compute expected signature
        mac = hmac.new(auth_token.encode("utf-8"), body, hashlib.sha1)
        expected_sig = base64.b64encode(mac.digest()).decode("utf-8")

        adapter = SMSGatewayAdapter({"auth_token": auth_token, "account_sid": "AC123"})

        request = GatewayInboundRequest(
            body=body,
            headers={"X-Twilio-Signature": expected_sig},
            query={},
            method="POST",
        )

        self.assertTrue(adapter.verify_inbound(request))

    def test_verify_inbound_rejects_invalid_hmac_signature(self):
        """Invalid HMAC-SHA1 signature must be rejected."""
        adapter = SMSGatewayAdapter({"auth_token": "test_token", "account_sid": "AC123"})

        request = GatewayInboundRequest(
            body=b"From=+1234567890&To=+0987654321&Body=Hello",
            headers={"X-Twilio-Signature": "invalid_signature_value"},
            query={},
            method="POST",
        )

        self.assertFalse(adapter.verify_inbound(request))

    def test_verify_inbound_with_unconfigured_token_accepts_frappe_sms(self):
        """Empty auth_token means frappe_sms mode, so signature not required."""
        adapter = SMSGatewayAdapter({})  # No credentials

        request = GatewayInboundRequest(
            body=b"from=+1234567890&message=test",
            headers={},
            query={},
            method="POST",
        )

        # Default account_sid is "frappe_sms", so should accept
        self.assertTrue(adapter.verify_inbound(request))
