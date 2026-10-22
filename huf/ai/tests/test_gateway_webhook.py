"""Focused tests for the Gateway Adapter runtime bridge."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook


def setUpModule():
	# No site in unit runs: whitelisted wrappers consult frappe.local.flags.
	import frappe

	if not getattr(frappe.local, "flags", None):
		frappe.local.flags = frappe._dict()


class TestGatewayWebhook(unittest.TestCase):
    @patch("huf.ai.gateway_webhook.frappe")
    def test_credentials_are_read_from_password_rows(self, mock_frappe):
        row = MagicMock(key="community_token")
        row.get_password.return_value = "secret-value"
        settings = SimpleNamespace(credentials=[row])
        configured_gateway = SimpleNamespace(integration_settings="VK-0001")
        mock_frappe.get_doc.return_value = settings

        assert gateway_webhook._gateway_credentials(configured_gateway) == {"community_token": "secret-value"}
        row.get_password.assert_called_once_with("value")

    @patch("huf.ai.gateway_webhook.ingest_gateway_event", create=True)
    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_verified_event_is_normalized_before_ingress(
        self, mock_frappe, mock_request, mock_adapter, mock_ingest
    ):
        configured_gateway = SimpleNamespace(name="Support VK", provider="VK", is_enabled=1)
        fake_request = SimpleNamespace(method="POST")
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
        mock_frappe.get_doc.return_value = configured_gateway
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support VK"})
        mock_request.return_value = fake_request
        mock_adapter.return_value = adapter

        with patch("huf.ai.gateway_service.ingest_gateway_event", return_value={"event_name": "GE-1"}) as ingest:
            result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": True, "event_name": "GE-1"}
        adapter.normalize_inbound.assert_called_once_with(fake_request)
        assert ingest.call_args.args[:2] == ("Support VK", "event-1")
        assert ingest.call_args.kwargs["verified_sender"] is True

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_unverified_request_is_never_normalized(self, mock_frappe, mock_request, mock_adapter):
        mock_frappe.get_doc.return_value = SimpleNamespace(name="Support VK", provider="VK", is_enabled=1)
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support VK"})
        mock_request.return_value = SimpleNamespace(method="POST")
        adapter = MagicMock()
        adapter.verify_inbound.return_value = False
        mock_adapter.return_value = adapter

        assert gateway_webhook.handle_gateway_webhook() == {
            "success": False,
            "error": "Provider verification failed",
        }
        adapter.normalize_inbound.assert_not_called()

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook._text_response")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_wecom_get_challenge_returns_raw_provider_echo(
        self, mock_frappe, mock_text_response, mock_request, mock_adapter
    ):
        mock_frappe.get_doc.return_value = SimpleNamespace(name="Support WeCom", provider="WeCom", is_enabled=1)
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support WeCom"})
        mock_request.return_value = SimpleNamespace(method="GET")
        adapter = MagicMock()
        adapter.verify_url.return_value = "decrypted-echo"
        mock_adapter.return_value = adapter

        assert gateway_webhook.handle_gateway_webhook() is None
        mock_text_response.assert_called_once_with("decrypted-echo")

    @patch("huf.ai.gateway_webhook._ingest_rate_gate")
    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook._text_response")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_get_verify_is_rate_gated_before_verify_url_and_keyed_by_query_name(
        self, mock_frappe, mock_text_response, mock_request, mock_adapter, mock_gate
    ):
        order = []
        mock_frappe.get_doc.return_value = SimpleNamespace(name="G1", provider="WhatsApp", is_enabled=1)
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "G1"})
        mock_frappe.form_dict = {}
        mock_request.return_value = SimpleNamespace(method="GET")
        adapter = MagicMock()
        adapter.verify_url.side_effect = lambda r: order.append("verify") or "ch"
        mock_adapter.return_value = adapter
        mock_gate.side_effect = lambda: order.append("gate")

        gateway_webhook.handle_gateway_webhook()

        assert order == ["gate", "verify"]
        assert mock_frappe.form_dict["gateway_name"] == "G1"

    @patch("huf.ai.gateway_webhook.frappe")
    def test_missing_gateway_name_is_rejected(self, mock_frappe):
        """Every provider here posts application/json, and
        frappe.app.make_form_dict replaces frappe.form_dict wholesale with
        the parsed JSON body whenever Content-Type is JSON — so
        gateway_name must be read from frappe.request.args, never taken as
        a function argument, or every real webhook call 500s."""
        mock_frappe.request = SimpleNamespace(args={})

        assert gateway_webhook.handle_gateway_webhook() == {
            "success": False,
            "error": "Missing gateway_name",
        }
        mock_frappe.get_doc.assert_not_called()


class TestGatewayWebhookRateGateAndReply(unittest.TestCase):
    @patch("huf.ai.gateway_webhook._ingest_rate_gate")
    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    @patch("huf.ai.gateway_webhook._inbound_request")
    @patch("huf.ai.gateway_webhook.frappe")
    def test_single_event_provider_path_is_unchanged_and_rate_limited_once(
        self, mock_frappe, mock_request, mock_adapter, mock_gate
    ):
        mock_frappe.get_doc.return_value = SimpleNamespace(name="Support VK", provider="VK", is_enabled=1)
        mock_frappe.request = SimpleNamespace(args={"gateway_name": "Support VK"})
        mock_request.return_value = SimpleNamespace(method="POST")
        normalized = SimpleNamespace(
            provider_event_id="e1", sender_id="1", conversation_id="2", thread_id="3",
            message_text="hi", is_room=False, mentioned=False, raw_payload={},
        )
        adapter = MagicMock()  # a MagicMock must NOT be mistaken for a parse_payload provider
        adapter.verify_inbound.return_value = True
        adapter.normalize_inbound.return_value = normalized
        mock_adapter.return_value = adapter

        with patch("huf.ai.gateway_service.ingest_gateway_event", return_value={"event_name": "GE-1"}):
            result = gateway_webhook.handle_gateway_webhook()

        assert result == {"success": True, "event_name": "GE-1"}
        mock_gate.assert_called_once()
        adapter.parse_payload.assert_not_called()

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    def test_send_gateway_reply_whatsapp_quotes_inbound_wamid_without_thread(self, mock_adapter):
        event = SimpleNamespace(conversation_id="1234567890", thread_id="", provider_event_id="wamid.in")
        gateway_webhook.send_gateway_reply(SimpleNamespace(provider="WhatsApp"), event, "hello")
        reply = mock_adapter.return_value.send_reply.call_args.args[0]
        assert reply.conversation_id == "1234567890"
        assert reply.thread_id is None
        assert reply.reply_to_provider_message_id == "wamid.in"

    @patch("huf.ai.gateway_webhook.get_gateway_adapter")
    def test_send_gateway_reply_other_providers_keep_thread_semantics(self, mock_adapter):
        event = SimpleNamespace(conversation_id="c", thread_id="t-9", provider_event_id="evt-1")
        gateway_webhook.send_gateway_reply(SimpleNamespace(provider="Slack"), event, "hello")
        reply = mock_adapter.return_value.send_reply.call_args.args[0]
        assert reply.thread_id == "t-9"
        assert reply.reply_to_provider_message_id == "t-9"
