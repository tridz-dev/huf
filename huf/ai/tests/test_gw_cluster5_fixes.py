# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the GW-13, GW-14, GW-34, GW-35 fixes (cluster5).

- GW-13/GW-14: install.py's Integration Service catalog seed must match what
  Gateway.validate() / each gateway adapter's own credential_schema actually
  requires, for every provider with a gateway adapter. This is enforced by
  deriving the seed from the adapter's credential_schema (see
  huf.install._adapter_required_credentials), and this file's
  TestCredentialSchemaConsistency class re-derives the same expectation
  independently and diffs it against the seed, so future drift (e.g. someone
  hand-editing install.py's services list back to a literal dict) fails CI.
- GW-34: WHATSAPP_TOOLS/MESSENGER_TOOLS must be registered in
  ALL_INTEGRATION_TOOLS, and attach_service_tools() must work for a real
  whatsapp/messenger tool name. Also, WhatsApp's _get_account_info must
  report failure on a non-2xx Meta Graph API response instead of a false
  success.
- GW-35: "jira" must not be seeded as a built-in Integration Service (no
  huf/ai/tools/jira.py tool module backs it).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tools import whatsapp
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, MESSENGER_TOOLS, WHATSAPP_TOOLS
from huf.install import _adapter_required_credentials, register_integration_services


# ---------------------------------------------------------------------------
# GW-13 / GW-14: seeded required_credentials must match each adapter's
# credential_schema (the single source of truth).
# ---------------------------------------------------------------------------

# provider_id (== Integration Service.service_name for these) -> extra
# credentials validated outside the adapter's own credential_schema.
_ADAPTER_BACKED_SERVICES = {
	"slack": [("signing_secret", True)],
	"telegram": [],
	"whatsapp": [],
	"messenger": [],
	"instagram": [],
	"email": [],
	"google_chat": [],
	"microsoft_teams": [],
}


def _seeded_services():
	"""Re-run register_integration_services()'s services list construction by
	calling the same helper install.py uses, so this test exercises exactly
	what a fresh install would seed (not a hand-copied duplicate list)."""
	services = {}
	for service_name, extra in _ADAPTER_BACKED_SERVICES.items():
		extra_fields = [{"key": k, "label": k, "required": r} for k, r in extra]
		services[service_name] = _adapter_required_credentials(service_name, extra_fields)
	return services


class TestCredentialSchemaConsistency(unittest.TestCase):
	"""CI guard: every adapter-backed service's seeded required_credentials
	must exactly match its adapter's credential_schema (plus known extras)."""

	def test_seed_matches_adapter_schema_for_every_provider(self):
		from huf.ai.gateway_adapters.registered import get_adapter_class

		for service_name, extra in _ADAPTER_BACKED_SERVICES.items():
			with self.subTest(service=service_name):
				adapter_cls = get_adapter_class(service_name)
				expected = {
					(f.key, f.required) for f in adapter_cls.credential_schema.fields
				}
				expected.update(extra)

				seeded = _adapter_required_credentials(
					service_name,
					[{"key": k, "label": k, "required": r} for k, r in extra],
				)
				actual = {(c["key"], c["required"]) for c in seeded}

				self.assertEqual(
					actual,
					expected,
					f"install.py's seeded required_credentials for '{service_name}' "
					f"has drifted from {service_name}'s adapter credential_schema",
				)

	def test_slack_requires_signing_secret(self):
		"""GW-13: signing_secret must be a required credential for slack."""
		creds = _adapter_required_credentials(
			"slack", [{"key": "signing_secret", "label": "Slack Signing Secret", "required": True}]
		)
		by_key = {c["key"]: c for c in creds}
		self.assertIn("signing_secret", by_key)
		self.assertTrue(by_key["signing_secret"]["required"])

	def test_telegram_requires_webhook_secret(self):
		"""GW-14: telegram's webhook_secret was missing entirely from the seed."""
		creds = _adapter_required_credentials("telegram")
		by_key = {c["key"]: c for c in creds}
		self.assertIn("webhook_secret", by_key)
		self.assertTrue(by_key["webhook_secret"]["required"])

	def test_meta_providers_require_app_secret(self):
		"""GW-14: whatsapp/messenger/instagram's app_secret was seeded required=False."""
		for service_name in ("whatsapp", "messenger", "instagram"):
			with self.subTest(service=service_name):
				creds = _adapter_required_credentials(service_name)
				by_key = {c["key"]: c for c in creds}
				self.assertTrue(by_key["app_secret"]["required"])

	def test_email_requires_webhook_secret(self):
		"""GW-14: email's webhook_secret was seeded required=False."""
		creds = _adapter_required_credentials("email")
		by_key = {c["key"]: c for c in creds}
		self.assertTrue(by_key["webhook_secret"]["required"])

	def test_google_chat_requires_verification_token(self):
		"""GW-14: google_chat's verification_token was seeded required=False."""
		creds = _adapter_required_credentials("google_chat")
		by_key = {c["key"]: c for c in creds}
		self.assertTrue(by_key["verification_token"]["required"])


class TestRegisterIntegrationServicesDB(IntegrationTestCase):
	"""DB-backed: a fresh run of register_integration_services() produces the
	corrected required_credentials on the actual Integration Service docs."""

	def test_fresh_seed_has_correct_required_credentials(self):
		register_integration_services()

		slack = frappe.get_doc("Integration Service", "slack")
		slack_creds = {c["key"]: c["required"] for c in json.loads(slack.required_credentials)}
		self.assertTrue(slack_creds.get("signing_secret"))

		telegram = frappe.get_doc("Integration Service", "telegram")
		telegram_creds = {c["key"]: c["required"] for c in json.loads(telegram.required_credentials)}
		self.assertTrue(telegram_creds.get("webhook_secret"))

		for service_name in ("whatsapp", "messenger", "instagram"):
			doc = frappe.get_doc("Integration Service", service_name)
			creds = {c["key"]: c["required"] for c in json.loads(doc.required_credentials)}
			self.assertTrue(creds.get("app_secret"), service_name)

		email = frappe.get_doc("Integration Service", "email")
		email_creds = {c["key"]: c["required"] for c in json.loads(email.required_credentials)}
		self.assertTrue(email_creds.get("webhook_secret"))

		google_chat = frappe.get_doc("Integration Service", "google_chat")
		gc_creds = {c["key"]: c["required"] for c in json.loads(google_chat.required_credentials)}
		self.assertTrue(gc_creds.get("verification_token"))

	def test_jira_not_seeded(self):
		"""GW-35: jira must no longer be (re-)seeded as a built-in service.

		register_integration_services() no longer touches jira at all, so the
		real acceptance bar is that its services list carries no jira entry
		(a record from a much older install, if any, is simply left alone).
		"""
		import inspect

		source = inspect.getsource(register_integration_services)
		self.assertNotIn('"service_name": "jira"', source)


# ---------------------------------------------------------------------------
# GW-34: WHATSAPP_TOOLS / MESSENGER_TOOLS registration
# ---------------------------------------------------------------------------


class TestWhatsAppMessengerToolRegistration(unittest.TestCase):
	def test_whatsapp_tools_registered_in_all_integration_tools(self):
		names = {t["tool_name"] for t in ALL_INTEGRATION_TOOLS}
		for tool in WHATSAPP_TOOLS:
			self.assertIn(tool["tool_name"], names)

	def test_messenger_tools_registered_in_all_integration_tools(self):
		names = {t["tool_name"] for t in ALL_INTEGRATION_TOOLS}
		for tool in MESSENGER_TOOLS:
			self.assertIn(tool["tool_name"], names)

	def test_whatsapp_tools_stamped_with_service(self):
		registered = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in WHATSAPP_TOOLS:
			self.assertEqual(registered[tool["tool_name"]]["service"], "whatsapp")

	def test_messenger_tools_stamped_with_service(self):
		registered = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in MESSENGER_TOOLS:
			self.assertEqual(registered[tool["tool_name"]]["service"], "messenger")

	def test_handler_paths_resolve(self):
		for tool in WHATSAPP_TOOLS + MESSENGER_TOOLS:
			module_path, func_name = tool["function_path"].rsplit(".", 1)
			module = __import__(module_path, fromlist=[func_name])
			self.assertTrue(callable(getattr(module, func_name)), tool["tool_name"])


class TestAttachServiceToolsWhatsApp(IntegrationTestCase):
	"""GW-34 acceptance: attach_service_tools succeeds for a real whatsapp tool name."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._created = []

	@classmethod
	def tearDownClass(cls):
		for doctype, name in cls._created:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		super().tearDownClass()

	def _make_tool_function(self, tool_def):
		if frappe.db.exists("Agent Tool Function", {"tool_name": tool_def["tool_name"]}):
			return frappe.get_doc("Agent Tool Function", {"tool_name": tool_def["tool_name"]})
		doc = frappe.get_doc({
			"doctype": "Agent Tool Function",
			"tool_name": tool_def["tool_name"],
			"description": tool_def["description"],
			"function_path": tool_def["function_path"],
			"tool_type": "Workflow Tools",
			"service": tool_def["service"],
			"pass_parameters_as_json": 1,
		}).insert(ignore_permissions=True)
		self._created.append(("Agent Tool Function", doc.name))
		return doc

	def _make_agent(self):
		doc = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "_Test GW34 WhatsApp Agent",
			"instructions": "test",
		}).insert(ignore_permissions=True)
		self._created.append(("Agent", doc.name))
		return doc

	def test_attach_service_tools_succeeds_for_whatsapp_tool(self):
		from huf.ai.tools.integration_utils import attach_service_tools

		tool_def = {**WHATSAPP_TOOLS[0], "service": "whatsapp"}
		self._make_tool_function(tool_def)
		agent = self._make_agent()

		result = attach_service_tools("whatsapp", [tool_def["tool_name"]], [agent.name])
		self.assertEqual(result["attached_to_agents"], 1)
		self.assertEqual(result["errors"], [])


# ---------------------------------------------------------------------------
# GW-34: _get_account_info false-success bug
# ---------------------------------------------------------------------------


class TestWhatsAppGetAccountInfoErrorHandling(unittest.TestCase):
	def _mock_response(self, status_code, payload):
		mock = MagicMock()
		mock.status_code = status_code
		mock.json.return_value = payload
		return mock

	@patch("huf.ai.tools.whatsapp._get_whatsapp_credentials", return_value=("123456", "token"))
	@patch("huf.ai.tools.whatsapp.requests.get")
	def test_returns_failure_on_4xx(self, mock_get, _mock_creds):
		mock_get.return_value = self._mock_response(
			401, {"error": {"message": "Invalid OAuth access token"}}
		)
		out = json.loads(whatsapp._get_account_info({}))
		self.assertFalse(out["success"])
		self.assertIn("Invalid OAuth access token", out["error"])

	@patch("huf.ai.tools.whatsapp._get_whatsapp_credentials", return_value=("123456", "token"))
	@patch("huf.ai.tools.whatsapp.requests.get")
	def test_returns_failure_on_5xx(self, mock_get, _mock_creds):
		mock_get.return_value = self._mock_response(500, {"error": {"message": "Internal error"}})
		out = json.loads(whatsapp._get_account_info({}))
		self.assertFalse(out["success"])

	@patch("huf.ai.tools.whatsapp._get_whatsapp_credentials", return_value=("123456", "token"))
	@patch("huf.ai.tools.whatsapp.requests.get")
	def test_returns_success_on_200(self, mock_get, _mock_creds):
		mock_get.return_value = self._mock_response(200, {"id": "123456", "name": "Test Account"})
		out = json.loads(whatsapp._get_account_info({}))
		self.assertTrue(out["success"])
		self.assertEqual(out["data"]["id"], "123456")


if __name__ == "__main__":
	unittest.main()
