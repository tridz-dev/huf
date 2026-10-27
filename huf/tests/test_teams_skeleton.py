"""WP-T4 skeleton tests: adapter schema/ctor, conversation references, serviceUrl allow-list, hook loading."""

import json
import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.teams import refs

CREDS = {"app_id": "app-1", "app_password": "s3cret", "tenant_id": "tenant-1"}


class _FakeCache:
	def __init__(self):
		self.store = {}
		self.ttl = {}

	def set_value(self, key, value, expires_in_sec=None, **_):
		self.store[key] = value
		self.ttl[key] = expires_in_sec

	def get_value(self, key, **_):
		return self.store.get(key)


class TestTeamsAdapterSchema(unittest.TestCase):
	def test_ctor_requires_each_credential(self):
		for missing in ("app_id", "app_password", "tenant_id"):
			creds = {k: v for k, v in CREDS.items() if k != missing}
			with self.assertRaises(ValueError) as ctx:
				TeamsGatewayAdapter(creds)
			self.assertIn(missing, str(ctx.exception))

	def test_ctor_accepts_valid_and_optional_allowed_tenants(self):
		TeamsGatewayAdapter(CREDS)
		TeamsGatewayAdapter({**CREDS, "allowed_tenant_ids": "a,b"})

	def test_schema_flags(self):
		fields = {f.key: f for f in TeamsGatewayAdapter.credential_schema.fields}
		self.assertEqual(list(fields), ["app_id", "app_password", "tenant_id", "allowed_tenant_ids"])
		self.assertTrue(fields["app_id"].required)
		self.assertTrue(fields["app_password"].required and fields["app_password"].secret)
		self.assertTrue(fields["tenant_id"].required and not fields["tenant_id"].secret)
		self.assertFalse(fields["allowed_tenant_ids"].required)
		self.assertFalse(fields["allowed_tenant_ids"].secret)
		self.assertNotIn("hmac", " ".join(fields).lower())

	def test_install_credential_rendering(self):
		from huf.install import _adapter_required_credentials

		rendered = {f["key"]: f for f in _adapter_required_credentials("microsoft_teams")}
		self.assertIs(rendered["tenant_id"]["secret"], False)
		self.assertIs(rendered["app_password"]["secret"], True)
		self.assertTrue(rendered["tenant_id"]["description"])
		self.assertIs(rendered["allowed_tenant_ids"]["required"], False)


class TestServiceUrl(unittest.TestCase):
	def test_accepts(self):
		for url in (
			"https://smba.trafficmanager.net/amer/",
			"https://smba.trafficmanager.net/emea",
			"https://smba.trafficmanager.net:443/amer",
			"https://smba.trafficmanager.net/teams/",
			"https://smba.trafficmanager.net",
			"https://SMBA.TrafficManager.NET/AMER/",
		):
			self.assertTrue(refs.validate_service_url(url).startswith("https://"), url)
		self.assertEqual(
			refs.validate_service_url("https://smba.trafficmanager.net/amer/"),
			"https://smba.trafficmanager.net/amer",
		)

	def test_rejects(self):
		for url in (
			"http://smba.trafficmanager.net/amer",
			"https://1.2.3.4/",
			"https://169.254.169.254/latest",
			"https://[::1]/",
			"https://user:pw@smba.trafficmanager.net/",
			"https://smba.trafficmanager.net@evil.com/",
			"https://evil.botframework.com.attacker.net/",
			"https://botframework.com/",
			"https://smba.trafficmanager.net:8443/amer",
			"https://smba.trafficmanager.net/a?x=1",
			"ftp://smba.trafficmanager.net/",
			"",
			None,
			"https://smba.trafficmanager.net\\@evil.com/",
			# S2: wildcard / non-Teams Bot Framework hosts
			"https://evil.trafficmanager.net/amer/",
			"https://foo.trafficmanager.net/a",
			"https://directline.botframework.com/",
			"https://webchat.botframework.com/",
			"https://token.botframework.com/",
			"https://login.botframework.com/",
			"https://api.botframework.com",
			"https://state.botframework.com/",
			"https://eu.botframework.com/x",
			# S2: path restrictions
			"https://smba.trafficmanager.net/amer/v3",
			"https://smba.trafficmanager.net/amer/../evil",
			"https://smba.trafficmanager.net/../amer",
			"https://smba.trafficmanager.net/./amer",
			"https://smba.trafficmanager.net/amer%2Fevil",
			"https://smba.trafficmanager.net/amer%252Fevil",
			"https://smba.trafficmanager.net//amer",
			"https://smba.trafficmanager.net/am_er/",
			# S2: host tricks
			"https://smba.trafficmanager.net:444/amer",
			"https://u@smba.trafficmanager.net/amer",
			"https://[2001:db8::1]/amer",
			"https://0x7f000001/amer",
			"https://smba.trafficmanager.net./amer",
			"https://smba.trafficmanager.n\u0435t/amer",
			"https://xn--smba-trafficmanager.net/amer",
			"https://smba.trafficmanager.net.evil.com/amer",
		):
			with self.assertRaises(ValueError, msg=repr(url)):
				refs.validate_service_url(url)


class TestReferences(unittest.TestCase):
	ACTIVITY = {
		"serviceUrl": "https://smba.trafficmanager.net/amer/",
		"channelId": "msteams",
		"conversation": {"id": "19:abc"},
		"recipient": {"id": "28:bot"},
		"channelData": {"tenant": {"id": "tenant-1"}},
	}

	def setUp(self):
		self.cache = _FakeCache()
		p = patch.object(refs.frappe, "cache", self.cache)
		p.start()
		self.addCleanup(p.stop)

	def test_cache_round_trip_key_has_no_secret(self):
		ref = refs.reference_from_activity(self.ACTIVITY)
		refs.save_reference("gw", "app-1", "19:abc", ref)
		got = refs.get_reference("gw", "app-1", "19:abc")
		self.assertEqual(got["serviceUrl"], "https://smba.trafficmanager.net/amer")
		self.assertEqual(
			(got["conversation_id"], got["bot_id"], got["tenant_id"], got["channelId"]),
			("19:abc", "28:bot", "tenant-1", "msteams"),
		)
		self.assertEqual(list(self.cache.ttl.values()), [refs.REFERENCE_TTL_SECONDS])
		self.assertNotIn("s3cret", json.dumps(list(self.cache.store)))

	def test_save_rejects_bad_service_url(self):
		ref = {**refs.reference_from_activity(self.ACTIVITY), "serviceUrl": "https://1.2.3.4/"}
		with self.assertRaises(ValueError):
			refs.save_reference("gw", "app-1", "19:abc", ref)
		self.assertEqual(self.cache.store, {})

	def test_gateway_event_fallback(self):
		with patch.object(
			refs.frappe, "get_all", return_value=[{"raw_payload": json.dumps(self.ACTIVITY)}]
		) as ga:
			got = refs.get_reference("gw", "app-1", "19:abc")
		self.assertEqual(got["bot_id"], "28:bot")
		filters = ga.call_args.kwargs["filters"]
		self.assertEqual(filters["verified_sender"], 1)
		self.assertEqual(filters["conversation_id"], "19:abc")
		# re-cached: second lookup needs no DB
		with patch.object(refs.frappe, "get_all", side_effect=AssertionError("db hit")):
			self.assertEqual(refs.get_reference("gw", "app-1", "19:abc"), got)

	def test_fallback_skips_bad_payloads(self):
		bad = {**self.ACTIVITY, "serviceUrl": "http://evil.example/"}
		rows = [{"raw_payload": json.dumps(bad)}, {"raw_payload": "not json"}]
		with patch.object(refs.frappe, "get_all", return_value=rows):
			self.assertIsNone(refs.get_reference("gw", "app-1", "19:abc"))


class TestTeamsHooksLoaded(unittest.TestCase):
	def test_provider_hooks_load_teams_ingest_update(self):
		hook = provider_hooks.get("Microsoft Teams", "ingest_update")
		self.assertIsNotNone(hook)
		self.assertEqual(hook.__module__, "huf.ai.teams.hooks")
		self.assertIsNotNone(provider_hooks.get("Telegram", "ingest_update"))
		self.assertIsNotNone(provider_hooks.get("WhatsApp", "send_reply"))


class TestReferenceGatewayScope(unittest.TestCase):
	"""S8a: references are scoped per Gateway even when two Gateways share an app id."""

	def setUp(self):
		self.cache = _FakeCache()
		p = patch.object(refs.frappe, "cache", self.cache)
		p.start()
		self.addCleanup(p.stop)

	def _ref(self, region):
		return {
			"serviceUrl": f"https://smba.trafficmanager.net/{region}/",
			"conversation_id": "19:abc",
			"channelId": "msteams",
		}

	def test_two_gateways_same_app_id_do_not_share(self):
		refs.save_reference("gw-a", "app-1", "19:abc", self._ref("amer"))
		refs.save_reference("gw-b", "app-1", "19:abc", self._ref("emea"))
		self.assertEqual(
			refs.get_reference("gw-a", "app-1", "19:abc")["serviceUrl"],
			"https://smba.trafficmanager.net/amer",
		)
		self.assertEqual(
			refs.get_reference("gw-b", "app-1", "19:abc")["serviceUrl"],
			"https://smba.trafficmanager.net/emea",
		)
		self.assertNotEqual(
			refs._cache_key("gw-a", "app-1", "19:abc"), refs._cache_key("gw-b", "app-1", "19:abc")
		)

	def test_other_gateway_cache_miss_falls_back_to_own_events_only(self):
		refs.save_reference("gw-a", "app-1", "19:abc", self._ref("amer"))
		with patch.object(refs.frappe, "get_all", return_value=[]) as ga:
			self.assertIsNone(refs.get_reference("gw-b", "app-1", "19:abc"))
		self.assertEqual(ga.call_args.kwargs["filters"]["gateway"], "gw-b")

	def test_blank_gateway_name_rejected(self):
		with self.assertRaises(ValueError):
			refs.save_reference("", "app-1", "19:abc", self._ref("amer"))
		self.assertIsNone(refs.get_reference("", "app-1", "19:abc"))
