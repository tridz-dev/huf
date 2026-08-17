"""Focused unit tests for the provider-neutral Gateway foundation."""

from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from huf.ai import gateway_service


def gateway(**overrides):
    values = {
        "name": "Support Telegram",
        "provider": "Telegram",
        "is_enabled": 1,
        "default_target_type": "",
        "default_agent": "",
        "default_flow": "",
        "direct_policy": "Allow list",
        "room_policy": "Allow list",
        "room_sender_policy": "Allow list",
        "mention_required": 1,
        "pairing_ttl_minutes": 60,
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
    def setUp(self):
        self.now_datetime = patch(
            "huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0)
        )
        self.now_datetime.start()

    def tearDown(self):
        self.now_datetime.stop()

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
                return gateway(direct_policy="Disabled")
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

    @patch("huf.ai.gateway_service.frappe")
    def test_direct_allow_list_requires_normalized_approved_entry(self, mock_frappe):
        mock_frappe.get_all.return_value = ["ACCESS-001"]
        admitted, _ = gateway_service._admission(gateway(), {"sender_id": "provider:42"})
        assert admitted is True
        assert mock_frappe.get_all.call_args.args[0] == "Gateway Access Entry"

    @patch("huf.ai.gateway_service.frappe")
    def test_expired_access_entry_does_not_admit_sender(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        admitted, _ = gateway_service._admission(gateway(), {"sender_id": "provider:42"})
        assert admitted is False
        assert ["expires_at", ">=", gateway_service.now_datetime()] in mock_frappe.get_all.call_args.kwargs["or_filters"]

    @patch("huf.ai.gateway_service.frappe")
    def test_pairing_creates_pending_entry_and_never_admits_triggering_message(self, mock_frappe):
        mock_frappe.db.exists.return_value = None
        # _create_pairing_request checks for an existing pending entry via
        # frappe.get_all before creating one; a bare MagicMock return value
        # is truthy and would short-circuit into the "reuse existing" branch
        # instead of the "create new" branch this test exercises.
        mock_frappe.get_all.return_value = []
        admitted, reason = gateway_service._admission(gateway(direct_policy="Pairing"), {"sender_id": "42"})
        assert admitted is False
        # The reason now also carries the generated pairing code so the
        # sender-facing message can quote it; that value comes from a fully
        # mocked frappe here, so assert the stable prefix rather than an
        # exact match on the (mocked, nondeterministic) code suffix.
        assert reason.startswith("Sender pairing approval is required")
        pending = mock_frappe.get_doc.call_args.args[0]
        assert pending["doctype"] == "Gateway Access Entry"
        assert pending["state"] == "Pending"

    @patch("huf.ai.gateway_service.frappe")
    def test_room_requires_room_sender_and_mention_when_configured(self, mock_frappe):
        admitted, reason = gateway_service._admission(gateway(), {"sender_id": "42", "conversation_id": "room:1", "is_room": True, "mentioned": False})
        assert admitted is False
        assert reason == "Room messages must mention the gateway"


class TestGatewayReplyDelivery(unittest.TestCase):
    @patch("huf.ai.gateway_service.frappe")
    @patch("huf.ai.gateway_webhook.send_gateway_reply")
    def test_agent_result_is_delivered_through_the_gateway(self, mock_send, mock_frappe):
        event = MagicMock(
            name="GATEWAY-EVENT-0004",
            status="Queued",
            gateway="Support VK",
            target_type="Agent",
            target_agent="Support Agent",
            message_text="hello",
            thread_id="123",
            conversation_id="2000000001",
            sender_id="42",
        )
        configured_gateway = gateway(name="Support VK", execution_user="gateway-bot")
        # Third item: the target Agent lookup added by the F1 access-control fix
        # (gateway-routed runs are authorized as Guest -- see agent_access.py).
        # allow_guest=True so this "delivered successfully" scenario still passes.
        target_agent_doc = MagicMock(allow_guest=True)
        mock_frappe.get_doc.side_effect = [event, configured_gateway, target_agent_doc]
        mock_run = MagicMock(return_value={"agent_run_id": "AR-001", "response": "Hello back"})
        mock_send.return_value = SimpleNamespace(provider_message_id="vk-message-1")

        with patch.dict(sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}):
            result = gateway_service.process_gateway_event(event.name)

        assert result == {
            "event_name": event.name,
            "status": "Succeeded",
            "agent_run_id": "AR-001",
            "provider_message_id": "vk-message-1",
        }
        assert mock_run.call_args.kwargs["now"] is True
        mock_send.assert_called_once_with(configured_gateway, event, "Hello back")
