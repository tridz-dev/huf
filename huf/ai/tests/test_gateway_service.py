"""Focused unit tests for the provider-neutral Gateway foundation."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service


def gateway(**overrides):
    values = {
        "name": "Support Telegram",
        "is_enabled": 1,
        "default_target_type": "",
        "default_agent": "",
        "default_flow": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def binding(**overrides):
    values = {
        "name": "BIND-001",
        "priority": 100,
        "match_type": "Any conversation",
        "match_value": "",
        "target_type": "Agent",
        "agent": "Support Agent",
        "flow": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestGatewayRouting(unittest.TestCase):
    @patch("huf.ai.gateway_service.frappe")
    def test_highest_priority_matching_binding_wins(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway()
        mock_frappe.get_all.return_value = [
            binding(name="wrong-room", priority=1, match_type="Room or channel", match_value="sales"),
            binding(name="thread", priority=20, match_type="Thread", match_value="42", agent="Thread Agent"),
            binding(name="any", priority=100, agent="Fallback Agent"),
        ]

        route = gateway_service.resolve_gateway_route(
            "Support Telegram", {"conversation_id": "support", "thread_id": "42"}
        )

        assert route == {
            "status": "Queued",
            "binding": "thread",
            "target_type": "Agent",
            "agent": "Thread Agent",
            "flow": None,
        }

    @patch("huf.ai.gateway_service.frappe")
    def test_default_route_is_used_only_after_no_binding_matches(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway(default_target_type="Flow", default_flow="Escalate")
        mock_frappe.get_all.return_value = [
            binding(match_type="Sender", match_value="allowed-user", agent="Personal Agent")
        ]

        route = gateway_service.resolve_gateway_route("Support Telegram", {"sender_id": "other-user"})

        assert route == {
            "status": "Queued",
            "binding": None,
            "target_type": "Flow",
            "agent": None,
            "flow": "Escalate",
        }

    @patch("huf.ai.gateway_service.frappe")
    def test_disabled_gateway_never_routes(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway(is_enabled=0)

        route = gateway_service.resolve_gateway_route("Support Telegram", {"sender_id": "anyone"})

        assert route == {"status": "Rejected", "reason": "Gateway is disabled"}
        mock_frappe.get_all.assert_not_called()


class TestGatewayIngress(unittest.TestCase):
    def test_payload_redaction_removes_provider_secrets(self):
        assert gateway_service._redact_payload(
            {"token": "top-secret", "body": {"signature": "sig", "message": "hello"}}
        ) == {"token": "[redacted]", "body": {"signature": "[redacted]", "message": "hello"}}

    @patch("huf.ai.gateway_service.frappe")
    def test_duplicate_provider_event_is_a_noop(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "GATEWAY-EVENT-0001"

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:123", {"sender_id": "1"}, verified_sender=True
        )

        assert result == {"duplicate": True, "event_name": "GATEWAY-EVENT-0001"}
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.enqueue.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_unverified_event_is_persisted_but_never_dispatched(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        event = MagicMock()
        event.name = "GATEWAY-EVENT-0002"
        mock_frappe.get_doc.return_value = event

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:124", {"sender_id": "1"}, verified_sender=False
        )

        assert result == {"event_name": "GATEWAY-EVENT-0002", "status": "Rejected"}
        event.insert.assert_called_once_with(ignore_permissions=True)
        event.db_set.assert_called_once_with(
            {"status": "Rejected", "error_message": "Provider did not verify sender"}
        )
        mock_frappe.enqueue.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_verified_but_unapproved_sender_is_rejected(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        event = MagicMock()
        event.name = "GATEWAY-EVENT-0003"

        def get_doc(value, *args, **kwargs):
            if value == "Gateway":
                return gateway(access_policy="Deny by default")
            return event

        mock_frappe.get_doc.side_effect = get_doc

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:125", {"sender_id": "1"}, verified_sender=True
        )

        assert result == {"event_name": "GATEWAY-EVENT-0003", "status": "Rejected"}
        event.db_set.assert_called_once_with(
            {"status": "Rejected", "error_message": "Sender is not approved for this gateway"}
        )
        mock_frappe.enqueue.assert_not_called()
