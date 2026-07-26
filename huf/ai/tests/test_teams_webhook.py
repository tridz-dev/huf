"""Focused unit tests for the Teams Outgoing Webhook adapter."""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import teams_webhook


class TestTeamsWebhook(unittest.TestCase):
	def test_valid_hmac_is_accepted(self):
		key = base64.b64encode(b"teams-test-key").decode()
		body = b'{"id":"activity-1"}'
		signature = base64.b64encode(hmac.new(b"teams-test-key", body, hashlib.sha256).digest()).decode()
		assert teams_webhook.verify_teams_hmac(key, body, f"HMAC {signature}")

	def test_invalid_hmac_is_rejected(self):
		key = base64.b64encode(b"teams-test-key").decode()
		assert not teams_webhook.verify_teams_hmac(key, b"body", "HMAC invalid")
		assert not teams_webhook.verify_teams_hmac("not-base64", b"body", "HMAC anything")

	def test_activity_normalizes_to_gateway_context(self):
		event_id, context = teams_webhook.teams_event_context(
			{
				"id": "activity-1",
				"replyToId": "root-1",
				"text": "@Huf help",
				"from": {"id": "29:user"},
				"conversation": {"id": "19:channel"},
			}
		)
		assert event_id == "activity-1"
		assert context == {
			"sender_id": "29:user",
			"conversation_id": "19:channel",
			"thread_id": "root-1",
			"message_text": "@Huf help",
		}

	@patch("huf.ai.tools.teams_webhook.ingest_gateway_event")
	@patch("huf.ai.tools.teams_webhook._gateway_settings")
	@patch("huf.ai.tools.teams_webhook.frappe")
	def test_verified_message_is_ingested_and_acknowledged(self, mock_frappe, mock_settings, mock_ingest):
		key_bytes = b"teams-test-key"
		key = base64.b64encode(key_bytes).decode()
		body = b'{"type":"message","id":"activity-1","text":"hello","from":{"id":"29:user"},"conversation":{"id":"19:channel"}}'
		signature = base64.b64encode(hmac.new(key_bytes, body, hashlib.sha256).digest()).decode()
		mock_settings.return_value.get_credential.return_value = key
		mock_frappe.request.get_data.return_value = body
		mock_frappe.get_request_header.return_value = f"HMAC {signature}"
		mock_ingest.return_value = {"status": "Queued", "event_name": "GATEWAY-EVENT-1"}

		response = teams_webhook.handle_teams_outgoing_webhook("Teams Support")

		assert response == {"type": "message", "text": "Thanks — Huf has received your message."}
		mock_ingest.assert_called_once()
		assert mock_ingest.call_args.kwargs["verified_sender"] is True
