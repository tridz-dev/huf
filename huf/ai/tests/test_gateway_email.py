"""Unit tests for Email Gateway Adapter signature verification (ST-04.2d)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.gateway_adapters.email import EmailGatewayAdapter, on_communication_inserted
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


class TestEmailGatewayInboundIngestion(IntegrationTestCase):
    """GW-04 regression: a real inbound Communication carries native Python
    `datetime` fields (e.g. `communication_date`) in `doc.as_dict()`. Gateway
    Event's `raw_payload` is a JSON field, and Frappe's JSON write path does a
    plain `json.dumps` with no `default=str`, so an unconverted datetime used
    to crash `ingest_gateway_event` with `TypeError` on every real inbound
    email (`_redact_payload` in gateway_service.py now stringifies anything
    that isn't JSON-native)."""

    def setUp(self):
        frappe.set_user("Administrator")
        self._gateway_names: list[str] = []
        self._comm_names: list[str] = []
        self._integration_settings_names: list[str] = []
        # Gateway.validate requires execution_user to hold the "Huf Gateway
        # User" role; grant it to Administrator for this test's duration
        # rather than provisioning a separate service user.
        self._admin = frappe.get_doc("User", "Administrator")
        self._added_role = "Huf Gateway User" not in {r.role for r in self._admin.roles}
        if self._added_role:
            self._admin.add_roles("Huf Gateway User")

    def tearDown(self):
        frappe.db.delete("Gateway Event", {"gateway": ["in", self._gateway_names]})
        for name in self._gateway_names:
            frappe.db.delete("Gateway", {"name": name})
        for name in self._integration_settings_names:
            frappe.db.delete("Integration Settings", {"name": name})
        for name in self._comm_names:
            frappe.db.delete("Communication", {"name": name})
        if self._added_role:
            frappe.db.delete(
                "Has Role", {"parent": "Administrator", "role": "Huf Gateway User"}
            )
        frappe.db.commit()

    def _make_gateway(self, name: str) -> None:
        settings = frappe.get_doc(
            {
                "doctype": "Integration Settings",
                "service": "email",
                "is_active": 1,
                "credentials": [{"key": "webhook_secret", "value": "test-secret"}],
            }
        ).insert(ignore_permissions=True)
        self._integration_settings_names.append(settings.name)

        frappe.get_doc(
            {
                "doctype": "Gateway",
                "gateway_name": name,
                "provider": "Email",
                "is_enabled": 1,
                "execution_user": "Administrator",
                "integration_settings": settings.name,
            }
        ).insert(ignore_permissions=True)
        self._gateway_names.append(name)

    def test_inbound_communication_with_real_datetime_does_not_crash(self):
        gw_name = "Test Email Gateway GW-04"
        self._make_gateway(gw_name)

        comm = frappe.get_doc(
            {
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Email",
                "sent_or_received": "Received",
                "sender": "customer@example.com",
                "content": "Need help with my order",
                "subject": "Support request",
                "communication_date": now_datetime(),
            }
        ).insert(ignore_permissions=True)
        self._comm_names.append(comm.name)

        # This must not raise. Before the GW-04 fix, doc.as_dict()'s native
        # `communication_date` datetime blew up json.dumps on Gateway Event's
        # JSON `raw_payload` field.
        on_communication_inserted(comm, method="after_insert")

        event_name = frappe.db.get_value("Gateway Event", {"gateway": gw_name}, "name")
        self.assertIsNotNone(event_name)
        raw_payload = frappe.db.get_value("Gateway Event", event_name, "raw_payload")
        self.assertIsNotNone(raw_payload)
