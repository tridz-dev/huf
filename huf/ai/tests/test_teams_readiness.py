# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-T6b: Teams readiness checks (offline)."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.teams import readiness

APP = "11111111-2222-3333-4444-555555555555"
TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET = "s3cr3t-VALUE-do-not-leak"


def _adapter(**extra):
	creds = {"app_id": APP, "app_password": SECRET, "tenant_id": TENANT, **extra}
	return TeamsGatewayAdapter(creds)


def _gw(stored=None, **kw):
	fields = {"name": "GW-1", "provider": "Microsoft Teams", "is_enabled": 1, "mention_required": 1}
	fields.update(kw)
	gw = SimpleNamespace(**fields)
	gw._load_integration_credentials = lambda: dict(stored or {})
	return gw


def _by_id(items):
	return {i["id"]: i for i in items}


class TestTeamsReadiness(IntegrationTestCase):
	def _run(self, gw, adapter, events=True):
		with patch("huf.ai.teams.readiness.frappe.get_all", return_value=[{"name": "E"}] if events else []):
			return _by_id(readiness.readiness_checks(gw, adapter))

	def test_ids_and_shape(self):
		items = readiness.readiness_checks(_gw(), _adapter())
		self.assertEqual(
			[i["id"] for i in items],
			["teams-credentials", "teams-messaging-endpoint", "teams-first-message", "teams-mention-policy", "teams-allowed-tenants"],
		)

	def test_all_green(self):
		checks = self._run(_gw(), _adapter())
		for item in checks.values():
			self.assertTrue(item["done"], item)
			self.assertIsNone(item["hint"])

	def test_credentials_adapter_none_names_missing_fields(self):
		checks = self._run(_gw({"app_id": APP, "app_password": SECRET}), None)
		item = checks["teams-credentials"]
		self.assertFalse(item["done"])
		self.assertIn("tenant_id", item["hint"])
		self.assertNotIn("app_id (", item["hint"].replace("Microsoft App ID (app_id) is missing", ""))

	def test_credentials_bad_guid(self):
		checks = self._run(_gw({"app_id": "not-a-guid", "app_password": SECRET, "tenant_id": TENANT}), None)
		self.assertIn("GUID", checks["teams-credentials"]["hint"])
		self.assertFalse(checks["teams-credentials"]["done"])

	def test_credentials_adapter_with_bad_guid_not_done(self):
		bad = TeamsGatewayAdapter({"app_id": "x", "app_password": SECRET, "tenant_id": TENANT})
		self.assertFalse(self._run(_gw(), bad)["teams-credentials"]["done"])

	def test_endpoint_hint_has_exact_path_and_enabled_flag(self):
		item = self._run(_gw(is_enabled=0), _adapter())["teams-messaging-endpoint"]
		self.assertFalse(item["done"])
		self.assertIn("/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=GW-1", item["hint"])
		self.assertTrue(self._run(_gw(is_enabled=1), _adapter())["teams-messaging-endpoint"]["done"])

	def test_first_message(self):
		item = self._run(_gw(), _adapter(), events=False)["teams-first-message"]
		self.assertFalse(item["done"])
		self.assertIn("Send a message to the bot in Teams", item["hint"])

	def test_mention_policy(self):
		off = self._run(_gw(mention_required=0), _adapter())["teams-mention-policy"]
		self.assertFalse(off["done"])
		self.assertIn("@mention", off["hint"])
		self.assertTrue(self._run(_gw(mention_required=1), _adapter())["teams-mention-policy"]["done"])

	def test_allowed_tenants(self):
		ok = self._run(_gw(), _adapter(allowed_tenant_ids=f"{TENANT}, {APP}"))["teams-allowed-tenants"]
		self.assertTrue(ok["done"])
		empty = self._run(_gw(), _adapter(allowed_tenant_ids=""))["teams-allowed-tenants"]
		self.assertTrue(empty["done"])
		bad = self._run(_gw(), _adapter(allowed_tenant_ids=f"{TENANT},oops"))["teams-allowed-tenants"]
		self.assertFalse(bad["done"])
		self.assertIn("GUID", bad["hint"])

	def test_check_bug_yields_failing_item_not_exception(self):
		with patch("huf.ai.teams.readiness.frappe.get_all", side_effect=RuntimeError("db down")):
			items = _by_id(readiness.readiness_checks(_gw(), _adapter()))
		self.assertFalse(items["teams-first-message"]["done"])
		self.assertEqual(len(items), 5)

	def test_secrets_never_in_output(self):
		for adapter, stored in ((_adapter(), None), (None, {"app_id": APP, "app_password": SECRET})):
			out = json.dumps(self._run(_gw(stored), adapter, events=False))
			self.assertNotIn(SECRET, out)

	def test_hook_registered_for_teams_only(self):
		self.assertIs(provider_hooks.get("Microsoft Teams", "readiness_checks"), readiness.readiness_checks)
		for provider in ("WhatsApp", "Telegram", "Slack"):
			self.assertIsNone(provider_hooks.get(provider, "readiness_checks"), provider)
			self.assertEqual(provider_hooks.readiness_checks(SimpleNamespace(provider=provider)), [])
