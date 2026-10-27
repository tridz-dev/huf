# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-T6b: Teams readiness checks (offline)."""

import json

import frappe
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
	def setUp(self):
		p = patch.object(readiness, "_public_base_url", return_value="https://huf.example.com")
		p.start()
		self.addCleanup(p.stop)
		for bucket in ("GW-1", readiness.AUTH_BUCKET):
			frappe.cache.delete_value(readiness.DROPS_PREFIX + bucket)

	def _run(self, gw, adapter, events=True):
		with patch("huf.ai.teams.readiness.frappe.get_all", return_value=[{"name": "E"}] if events else []):
			return _by_id(readiness.readiness_checks(gw, adapter))

	def test_ids_and_shape(self):
		items = readiness.readiness_checks(_gw(), _adapter())
		self.assertEqual(
			[i["id"] for i in items],
			[
				"teams-credentials",
				"teams-messaging-endpoint",
				"teams-first-message",
				"teams-mention-policy",
				"teams-allowed-tenants",
				"teams-recent-drops",
			],
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
		self.assertIn(
			"/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=GW-1", item["hint"]
		)
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
		self.assertEqual(len(items), 6)

	def test_secrets_never_in_output(self):
		for adapter, stored in ((_adapter(), None), (None, {"app_id": APP, "app_password": SECRET})):
			out = json.dumps(self._run(_gw(stored), adapter, events=False))
			self.assertNotIn(SECRET, out)

	def test_hook_registered_for_teams_only(self):
		self.assertIs(provider_hooks.get("Microsoft Teams", "readiness_checks"), readiness.readiness_checks)
		for provider in ("WhatsApp", "Telegram", "Slack"):
			self.assertIsNone(provider_hooks.get(provider, "readiness_checks"), provider)
			self.assertEqual(provider_hooks.readiness_checks(SimpleNamespace(provider=provider)), [])


class TestEndpointUrlAndPublicHost(IntegrationTestCase):
	"""TFIX-D M4a: structured ``endpoint_url``; non-public / non-https base flagged."""

	def item(self, base, enabled=1):
		with (
			patch.object(readiness, "_public_base_url", return_value=base),
			patch("huf.ai.teams.readiness.frappe.get_all", return_value=[]),
		):
			return _by_id(readiness.readiness_checks(_gw(is_enabled=enabled), _adapter()))[
				"teams-messaging-endpoint"
			]

	def test_endpoint_url_is_structured_and_absolute(self):
		item = self.item("https://huf.example.com")
		self.assertTrue(item["done"])
		self.assertEqual(
			item["endpoint_url"],
			"https://huf.example.com/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=GW-1",
		)
		self.assertEqual(
			self.item("https://huf.example.com", enabled=0)["endpoint_url"], item["endpoint_url"]
		)

	def test_non_public_bases_flagged(self):
		for base, host in (
			("http://huf.example.com", "huf.example.com"),
			("https://localhost:8000", "localhost"),
			("https://127.0.0.1", "127.0.0.1"),
			("http://teams-int.local:8140", "teams-int.local"),
			("https://site.localhost", "site.localhost"),
			("https://10.0.0.5", "10.0.0.5"),
			("https://[::1]:8443", "::1"),
			("", "<none>"),
		):
			with self.subTest(base=base):
				item = self.item(base)
				self.assertFalse(item["done"])
				self.assertIn(
					f"Messaging endpoint must be a public https URL (current: {host})", item["hint"]
				)
				self.assertIn("host_name", item["hint"])

	def test_endpoint_url_survives_provider_hooks(self):
		gw = _gw()
		with (
			patch.object(readiness, "_public_base_url", return_value="https://huf.example.com"),
			patch("huf.ai.teams.readiness.frappe.get_all", return_value=[]),
			patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=_adapter()),
		):
			items = _by_id(provider_hooks.readiness_checks(gw))
		self.assertTrue(
			items["teams-messaging-endpoint"]["endpoint_url"].startswith("https://huf.example.com/")
		)
		self.assertEqual(set(items["teams-credentials"]), {"id", "label", "done", "hint"})


class TestRecentDrops(IntegrationTestCase):
	"""TFIX-D H3: rolling drop record per gateway + global auth bucket."""

	def setUp(self):
		for bucket in ("GW-1", "GW-2", readiness.AUTH_BUCKET):
			frappe.cache.delete_value(readiness.DROPS_PREFIX + bucket)
			self.addCleanup(frappe.cache.delete_value, readiness.DROPS_PREFIX + bucket)

	def item(self, name="GW-1"):
		with patch.object(readiness, "_public_base_url", return_value="https://huf.example.com"):
			return _by_id(readiness.readiness_checks(_gw(name=name), _adapter()))["teams-recent-drops"]

	def test_no_drops_is_done(self):
		item = self.item()
		self.assertTrue(item["done"])
		self.assertIsNone(item["hint"])

	def test_drops_summarised_per_gateway_plus_auth(self):
		for kind in ("tenant", "tenant", "service_url"):
			readiness.record_drop("GW-1", kind)
		readiness.record_drop("GW-2", "channel")
		readiness.record_drop(readiness.AUTH_BUCKET, "auth:pre_iss")
		item = self.item()
		self.assertFalse(item["done"])
		self.assertIn(
			"Recent dropped activities: 1 service_url, 2 tenant, 1 auth:pre_iss (all Teams gateways)",
			item["hint"],
		)
		self.assertIn("(last: ", item["hint"])
		self.assertIn("see docs troubleshooting", item["hint"])
		self.assertNotIn("channel", item["hint"])  # other gateway's drops are not shown here

	def test_record_is_bounded_and_ages_out(self):
		for i in range(30):
			readiness.record_drop("GW-1", "tenant")
		record = frappe.cache.get_value(readiness.DROPS_PREFIX + "GW-1")
		self.assertEqual(len(record["entries"]), readiness.DROPS_KEEP)
		self.assertEqual(record["counts"], {"tenant": 30})
		self.assertEqual(set(record["entries"][0]), {"ts", "kind"})
		later = readiness._now() + readiness.DROPS_WINDOW_SECONDS + 10
		with patch.object(readiness, "_now", return_value=later):
			self.assertTrue(self.item()["done"])
			readiness.record_drop("GW-1", "channel")
			counts, _last = readiness.recent_drops("GW-1")
		self.assertEqual(counts, {"channel": 1})  # window reset

	def test_record_drop_never_raises(self):
		with patch.object(readiness.frappe.cache, "get_value", side_effect=RuntimeError("redis down")):
			readiness.record_drop("GW-1", "tenant")
