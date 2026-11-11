# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp webhook security at the HTTP boundary (bugs 08 and 09).

Drives ``huf.ai.gateway_webhook.handle_gateway_webhook`` with a real WhatsApp
Gateway and Integration Settings, so the signature check, the verify-token
check, the status codes and the Gateway Event table are all real. Only the
inbound HTTP request object is faked. All secrets are fake test values.

Run with: bench --site <site> run-tests --module huf.ai.gateway_adapters.tests.test_whatsapp_webhook_security
"""

import hashlib
import hmac
import json
from types import SimpleNamespace

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_webhook
from huf.testing.factories import make_agent, make_ai_provider_and_model

APP_SECRET = "fake-app-secret-for-tests"
WRONG_APP_SECRET = "fake-wrong-app-secret-for-tests"
VERIFY_TOKEN = "fake-verify-token-for-tests"
WRONG_VERIFY_TOKEN = "fake-wrong-verify-token-for-tests"
CHALLENGE = "1158201444"

MESSAGE_PAYLOAD = {
	"object": "whatsapp_business_account",
	"entry": [
		{
			"id": "WABA_FAKE",
			"changes": [
				{
					"field": "messages",
					"value": {
						"messaging_product": "whatsapp",
						"metadata": {"display_phone_number": "15550000000", "phone_number_id": "PNID_FAKE"},
						"contacts": [{"profile": {"name": "Fake Sender"}, "wa_id": "15559870001"}],
						"messages": [
							{
								"from": "15559870001",
								"id": "wamid.FAKESECURITY0001",
								"timestamp": "1750000000",
								"type": "text",
								"text": {"body": "hello from a fake webhook test"},
							}
						],
					},
				}
			],
		}
	],
}

EMPTY_PAYLOAD = {"object": "whatsapp_business_account", "entry": []}


def _signature(secret: str, body: bytes) -> str:
	return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestWhatsAppWebhookSecurity(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._suffix = frappe.generate_hash(length=8)
		self.provider, self.model = make_ai_provider_and_model()
		self.exec_user = self._make_gateway_user()
		self.agent = make_agent(
			agent_name=f"_Test WA Security {self._suffix}",
			provider=self.provider,
			model=self.model,
			allowed_users=[{"user": self.exec_user}],
		)
		self.settings = self._make_settings(with_app_secret=True)
		self.gateway = self._make_gateway(self.settings.name, f"_Test WA Security GW {self._suffix}")

		self._saved_request = getattr(frappe, "request", None)
		self._saved_form_dict = getattr(frappe, "form_dict", None)
		self._saved_response = getattr(frappe.local, "response", None)
		self._saved_request_ip = getattr(frappe.local, "request_ip", None)
		frappe.form_dict = frappe._dict()
		frappe.local.response = frappe._dict(http_status_code=200)
		# The ingest rate limiter keys on the client IP; a real webhook always has one.
		frappe.local.request_ip = "127.0.0.1"

	def tearDown(self):
		frappe.request = self._saved_request
		frappe.form_dict = self._saved_form_dict
		frappe.local.response = self._saved_response
		frappe.local.request_ip = self._saved_request_ip
		frappe.set_user("Administrator")
		for name in frappe.get_all("Gateway Event", filters={"gateway": self.gateway.name}, pluck="name"):
			frappe.delete_doc("Gateway Event", name, ignore_permissions=True, force=True)
		frappe.db.delete("Gateway", {"name": self.gateway.name})
		frappe.db.delete("Integration Settings", {"name": self.settings.name})
		frappe.delete_doc("Agent", self.agent.name, ignore_permissions=True, force=True)
		frappe.db.delete("AI Model", {"name": self.model})
		frappe.db.delete("AI Provider", {"name": self.provider})
		frappe.delete_doc("User", self.exec_user, ignore_permissions=True, force=True)
		frappe.db.commit()  # nosemgrep -- test teardown

	# ------------------------------------------------------------------ helpers
	def _make_gateway_user(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"wa-security-{self._suffix}@example.com",
				"first_name": "WA Security Test",
				"send_welcome_email": 0,
			}
		)
		user.append("roles", {"role": "Huf Gateway User"})
		user.insert(ignore_permissions=True)
		return user.name

	def _make_settings(self, with_app_secret: bool, phone_tag: str = ""):
		credentials = [
			{"key": "phone_number_id", "value": f"55{self._suffix}{phone_tag}"},
			{"key": "access_token", "value": "fake-access-token"},
			{"key": "webhook_verify_token", "value": VERIFY_TOKEN},
		]
		if with_app_secret:
			credentials.append({"key": "app_secret", "value": APP_SECRET})
		return frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"is_active": 1,
				"credentials": credentials,
			}
		).insert(ignore_permissions=True)

	def _make_gateway(self, settings_name: str, gateway_name: str):
		return frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": gateway_name,
				"provider": "WhatsApp",
				"is_enabled": 1,
				"execution_user": self.exec_user,
				"direct_policy": "Allow list",
				"default_target_type": "Agent",
				"default_agent": self.agent.name,
				"integration_settings": settings_name,
			}
		).insert(ignore_permissions=True)

	def _set_post(self, payload: dict, headers: dict):
		body = json.dumps(payload).encode("utf-8")
		frappe.request = SimpleNamespace(
			args={"gateway_name": self.gateway.name},
			method="POST",
			headers=headers,
			content_length=len(body),
			get_data=lambda: body,
		)
		return body

	def _set_get(self, token: str):
		query = {
			"gateway_name": self.gateway.name,
			"hub.mode": "subscribe",
			"hub.verify_token": token,
			"hub.challenge": CHALLENGE,
		}
		frappe.request = SimpleNamespace(
			args=query, method="GET", headers={}, content_length=0, get_data=lambda: b""
		)

	def _gateway_event_count(self) -> int:
		return frappe.db.count("Gateway Event", {"gateway": self.gateway.name})

	# ------------------------------------------------------------ POST: signature
	def test_unsigned_post_is_401_and_creates_no_gateway_event(self):
		self._set_post(MESSAGE_PAYLOAD, headers={"Content-Type": "application/json"})
		before = self._gateway_event_count()

		result = gateway_webhook.handle_gateway_webhook()

		self.assertEqual(result, {"success": False, "error": "Provider verification failed"})
		self.assertEqual(frappe.local.response.http_status_code, 401)
		self.assertEqual(self._gateway_event_count(), before)

	def test_correctly_signed_post_is_200(self):
		body = self._set_post(EMPTY_PAYLOAD, headers={})
		frappe.request.headers = {"X-Hub-Signature-256": _signature(APP_SECRET, body)}

		result = gateway_webhook.handle_gateway_webhook()

		self.assertTrue(result["success"])
		self.assertEqual(frappe.local.response.http_status_code, 200)

	def test_wrongly_signed_post_is_401_and_creates_no_gateway_event(self):
		body = self._set_post(MESSAGE_PAYLOAD, headers={})
		frappe.request.headers = {"X-Hub-Signature-256": _signature(WRONG_APP_SECRET, body)}
		before = self._gateway_event_count()

		result = gateway_webhook.handle_gateway_webhook()

		self.assertEqual(result, {"success": False, "error": "Provider verification failed"})
		self.assertEqual(frappe.local.response.http_status_code, 401)
		self.assertEqual(self._gateway_event_count(), before)

	# --------------------------------------------------------- GET: verify token
	def test_get_subscribe_with_wrong_verify_token_is_403(self):
		self._set_get(WRONG_VERIFY_TOKEN)

		result = gateway_webhook.handle_gateway_webhook()

		self.assertEqual(result, {"success": False, "error": "Webhook verification failed"})
		self.assertEqual(frappe.local.response.http_status_code, 403)
		self.assertNotIn("result", frappe.local.response)

	def test_get_subscribe_with_right_verify_token_returns_challenge(self):
		self._set_get(VERIFY_TOKEN)

		result = gateway_webhook.handle_gateway_webhook()

		self.assertIsNone(result)
		self.assertEqual(frappe.local.response.http_status_code, 200)
		self.assertEqual(frappe.local.response.get("result"), CHALLENGE)

	# ------------------------------------------------------ save-time enforcement
	def test_enabling_whatsapp_gateway_without_app_secret_is_rejected(self):
		settings = self._make_settings(with_app_secret=False, phone_tag="x")
		self.addCleanup(frappe.db.delete, "Integration Settings", {"name": settings.name})

		with self.assertRaisesRegex(frappe.ValidationError, "App Secret|app_secret"):
			self._make_gateway(settings.name, f"_Test WA No Secret {self._suffix}")
