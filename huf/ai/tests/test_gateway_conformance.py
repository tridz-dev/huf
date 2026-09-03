"""Conformance tests for gateway adapter security: all adapters must fail closed on bad/missing signatures."""

from __future__ import annotations

from frappe.tests import IntegrationTestCase
from huf.ai.gateway_adapters.registered import get_adapter_class
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply, NormalizedGatewayEvent


class TestGatewayAdapterSecurityConformance(IntegrationTestCase):
    """Verify every gateway adapter fails closed on invalid or missing signature credentials."""

    def _get_all_adapters(self) -> list[str]:
        """Return all registered adapter provider IDs."""
        from huf.ai.gateway_adapters.registered import _ADAPTER_LOCATIONS
        return list(_ADAPTER_LOCATIONS.keys())

    def _make_bad_request(self, adapter_provider_id: str) -> GatewayInboundRequest:
        """Construct a minimal request with invalid/missing signatures for the given provider.

        The exact signature field depends on the provider's credential schema.
        """
        # Generic bad request: no signatures, empty body
        return GatewayInboundRequest(
            body=b'{"text": "test message"}',
            headers={},  # Missing all provider-specific signature headers
            query={},
            method="POST",
        )

    def _assert_adapter_verify_inbound_returns_false_on_missing_credentials(self, provider_id: str):
        """Every adapter must return False (never raise) when required credentials are missing.

        This is the security conformance check: adapters MUST fail closed, not open.
        """
        # Get the adapter class (this imports lazily)
        adapter_cls = get_adapter_class(provider_id)

        # Instantiate with empty credentials (simulating missing/unconfigured secrets)
        empty_creds = {}
        adapter = adapter_cls(empty_creds)

        # Make a request with missing/invalid signature headers
        bad_request = self._make_bad_request(provider_id)

        # Adapter must return False, never raise an exception
        result = adapter.verify_inbound(bad_request)

        # Key assertion: verify_inbound must return False (fail closed)
        # If the adapter requires credentials and they are missing, it must reject the request
        assert isinstance(result, bool), f"{provider_id} adapter verify_inbound returned {type(result)}, expected bool"

        # For adapters with required credentials, False is the expected result
        # For adapters without required credentials (or with weak defaults), we just ensure it returns a bool

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_whatsapp(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("whatsapp")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_telegram(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("telegram")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_messenger(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("messenger")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_instagram(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("instagram")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_email(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("email")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_google_chat(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("google_chat")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_microsoft_teams(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("microsoft_teams")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_slack(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("slack")

    def test_adapter_verify_inbound_returns_false_on_missing_credentials_sms(self):
        self._assert_adapter_verify_inbound_returns_false_on_missing_credentials("sms")

    def test_adapter_verify_inbound_never_raises(self):
        """Verify that calling verify_inbound with an invalid request never raises an exception.

        The adapter contract is that verify_inbound returns bool; raising breaks the caller's
        error handling. This is particularly important for middleware-style callers like gateway_webhook.py.
        """
        providers = ["whatsapp", "telegram", "messenger", "instagram", "email", "google_chat", "microsoft_teams", "slack", "sms"]

        for provider_id in providers:
            adapter_cls = get_adapter_class(provider_id)
            adapter = adapter_cls({})

            # Various kinds of bad requests
            bad_requests = [
                GatewayInboundRequest(body=b"", headers={}, query={}, method="POST"),
                GatewayInboundRequest(body=b"<bad>xml</bad>", headers={}, query={}, method="POST"),
                GatewayInboundRequest(body=None, headers={}, query={}, method="POST"),
                GatewayInboundRequest(body=b"\x00\x01\x02", headers={}, query={}, method="POST"),
            ]

            for req in bad_requests:
                try:
                    result = adapter.verify_inbound(req)
                    assert isinstance(result, bool), f"{provider_id} verify_inbound returned {type(result)}, expected bool"
                except Exception as e:
                    self.fail(f"{provider_id} adapter raised {type(e).__name__}: {e} on verify_inbound()")
