# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Tests for GW-36's structured template-parameter support in the WhatsApp
agent tool's send_template action (backing the UI form's request shape).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import whatsapp


class FakeResponse:
	def __init__(self, status_code=200, body=None):
		self.status_code = status_code
		self._body = body or {}
		self.text = json.dumps(self._body)

	def json(self):
		return self._body


class TestWhatsAppSendTemplate(unittest.TestCase):
	def _kwargs(self, **overrides):
		kwargs = {
			"phone_number_id": "PN1",
			"access_token": "token",
			"to": "15551234567",
			"template_name": "order_update",
			"language_code": "en_US",
		}
		kwargs.update(overrides)
		return kwargs

	def test_send_template_without_parameters_omits_components(self):
		with patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.1"}]})) as mock_post:
			result = json.loads(whatsapp.handle_action("send_template", **self._kwargs()))
		self.assertTrue(result["success"])
		sent_payload = mock_post.call_args.kwargs["json"]
		self.assertNotIn("components", sent_payload["template"])

	def test_send_template_with_structured_parameters_builds_components(self):
		with patch.object(whatsapp.requests, "post", return_value=FakeResponse(body={"messages": [{"id": "wamid.2"}]})) as mock_post:
			result = json.loads(
				whatsapp.handle_action(
					"send_template",
					**self._kwargs(parameters=["Jane", "ORD-42"]),
				)
			)
		self.assertTrue(result["success"])
		sent_payload = mock_post.call_args.kwargs["json"]
		self.assertEqual(
			sent_payload["template"]["components"],
			[
				{
					"type": "body",
					"parameters": [
						{"type": "text", "text": "Jane"},
						{"type": "text", "text": "ORD-42"},
					],
				}
			],
		)

	def test_send_template_rejects_non_list_parameters(self):
		result = json.loads(
			whatsapp.handle_action("send_template", **self._kwargs(parameters="not-a-list"))
		)
		self.assertFalse(result["success"])
		self.assertIn("list", result["error"])

	def test_send_template_requires_recipient_and_name(self):
		result = json.loads(whatsapp.handle_action("send_template", phone_number_id="PN1", access_token="t"))
		self.assertFalse(result["success"])


if __name__ == "__main__":
	unittest.main()
