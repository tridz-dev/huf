"""WP-T2: outbound Bot Connector client, against the offline fake services (no real network)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.teams import client, refs
from huf.tests import teams_fixtures as tf

SECRET = "s3cr3t-app-password-value"
CREDS = {"app_id": tf.BOT_APP_ID, "app_password": SECRET, "tenant_id": tf.TENANT_ID}
REAL_SERVICE = "https://smba.trafficmanager.net/amer"
CONV = "a:1personal-conv"
CHANNEL_CONV = "19:abc@thread.tacv2;messageid=1700000000000"


class _Base(unittest.TestCase):
	def setUp(self):
		ctx = tf.fake_bot_services()
		self.svc = ctx.__enter__()
		self.addCleanup(ctx.__exit__, None, None, None)
		self.sleeps: list[float] = []
		patches = [
			patch.object(client, "_AUTHORITY_BASE", self.svc.base_url),
			patch.object(client, "_sleep", self.sleeps.append),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		client.clear_token_cache(tf.TENANT_ID, tf.BOT_APP_ID)
		self.addCleanup(client.clear_token_cache, tf.TENANT_ID, tf.BOT_APP_ID)
		self.urls: list[str] = []
		self.seed(CONV)

	def seed(self, conversation_id, service_url=REAL_SERVICE + "/"):
		refs.save_reference(
			"Teams GW",
			tf.BOT_APP_ID,
			conversation_id,
			{
				"serviceUrl": service_url,
				"conversation_id": conversation_id,
				"bot_id": tf.BOT_ID,
				"tenant_id": tf.TENANT_ID,
			},
		)

	def transport(self, method, url, **kw):
		"""Real requests transport; the allow-listed Connector host is mapped onto the local fake."""
		self.urls.append(url)
		mapped = url.replace(REAL_SERVICE, self.svc.base_url)
		if mapped.startswith("https://"):
			raise AssertionError(f"unexpected real host: {url}")
		return client._requests_transport(method, mapped, **kw)

	def send(self, text="hello", conversation_id=CONV, reply_to=None):
		return client.send_reply(
			GatewayReply(conversation_id=conversation_id, text=text, reply_to_provider_message_id=reply_to),
			CREDS,
			gateway_name="Teams GW",
			transport=self.transport,
		)

	def assert_no_secrets(self, *texts):
		blob = " ".join(str(t) for t in texts)
		blob += json.dumps([r.__dict__ for r in self.svc.requests()], default=str)
		self.assertNotIn(SECRET, blob)
		self.assertNotIn(self.svc.access_token_prefix, blob)


class TestSend(_Base):
	def test_happy_send_returns_real_id(self):
		delivery = self.send("**hi**")
		self.assertTrue(delivery.provider_message_id.startswith("fake-activity-"))
		[req] = self.svc.requests("connector")
		self.assertEqual(req.path, "/v3/conversations/a%3A1personal-conv/activities")
		self.assertTrue(req.has_authorization)
		self.assertEqual(req.body["type"], "message")
		self.assertEqual(req.body["text"], "**hi**")
		self.assertEqual(req.body["textFormat"], "markdown")
		self.assertEqual(req.body["from"], {"id": tf.BOT_ID})
		self.assertEqual(req.body["conversation"], {"id": CONV})
		self.assertNotIn("replyToId", req.body)
		[tok] = self.svc.requests("token")
		self.assertEqual(tok.path, f"/{tf.TENANT_ID}/oauth2/v2.0/token")
		self.assertEqual(tok.body["grant_type"], "client_credentials")
		self.assertEqual(tok.body["client_id"], tf.BOT_APP_ID)
		self.assertEqual(tok.body["scope"], "https://api.botframework.com/.default")
		self.assertTrue(tok.body["client_secret_sent"])
		self.assert_no_secrets(delivery.provider_response)

	def test_thread_reply_path(self):
		self.seed(CHANNEL_CONV.partition(";")[0])
		self.send("in thread", conversation_id=CHANNEL_CONV, reply_to="1700000000123")
		[req] = self.svc.requests("connector")
		self.assertTrue(req.path.endswith("/activities/1700000000123"))
		self.assertNotIn("%3Bmessageid%3D", req.path)  # explicit replyToId form posts to the base id
		self.assertEqual(req.body["replyToId"], "1700000000123")

	def test_channel_thread_via_reply_target_hook(self):
		base = "19:chan@thread.tacv2"
		self.seed(base)
		hook = provider_hooks.get("Microsoft Teams", "reply_target")
		thread_id, reply_to = hook(type("E", (), {"thread_id": "1700000000000"})())
		self.assertEqual((thread_id, reply_to), ("1700000000000", None))
		self.assertEqual(hook(type("E", (), {"thread_id": None})()), (None, None))
		client.send_reply(
			GatewayReply(
				conversation_id=base, text="t", thread_id=thread_id, reply_to_provider_message_id=reply_to
			),
			CREDS,
			gateway_name="Teams GW",
			transport=self.transport,
		)
		[req] = self.svc.requests("connector")
		self.assertEqual(
			req.path, "/v3/conversations/19%3Achan%40thread.tacv2%3Bmessageid%3D1700000000000/activities"
		)
		self.assertEqual(req.body["conversation"], {"id": f"{base};messageid=1700000000000"})
		self.assertNotIn("replyToId", req.body)

	def test_missing_reference_is_actionable(self):
		with self.assertRaises(client.TeamsPermanentError) as cm:
			self.send(conversation_id="a:unknown")
		self.assertIn("must message the bot first", str(cm.exception))
		self.assertEqual(self.svc.requests(), [])


class TestToken(_Base):
	def test_token_cached_across_sends(self):
		self.send("one")
		self.send("two")
		self.assertEqual(len(self.svc.requests("token")), 1)
		self.assertEqual(len(self.svc.requests("connector")), 2)

	def test_token_refreshed_at_exp_minus_5_minutes(self):
		now = 1_000_000.0
		with patch.object(client, "_now", lambda: now):
			self.send("a")
		with patch.object(client, "_now", lambda: now + 3600 - 301):
			self.send("b")
		self.assertEqual(len(self.svc.requests("token")), 1)
		with patch.object(client, "_now", lambda: now + 3600 - 299):
			self.send("c")
		self.assertEqual(len(self.svc.requests("token")), 2)

	def test_token_401_single_redacted_error(self):
		self.svc.script(
			"token",
			{
				"status": 401,
				"body": {"error": "invalid_client", "error_description": f"AADSTS7000215 {SECRET}"},
			},
		)
		with self.assertRaises(client.TeamsAuthError) as cm:
			self.send()
		msg = str(cm.exception)
		self.assertIn("HTTP 401", msg)
		self.assertIn("AADSTS7000215", msg)
		self.assertEqual(len(self.svc.requests("token")), 1)
		self.assertEqual(self.svc.requests("connector"), [])
		self.assert_no_secrets(msg)

	def test_redis_cache_key_has_no_secret(self):
		key = client._token_cache_key(tf.TENANT_ID, tf.BOT_APP_ID)
		self.assertNotIn(SECRET, key)
		self.assertNotIn(tf.BOT_APP_ID, key)


class TestRetries(_Base):
	def test_429_honours_retry_after_then_succeeds(self):
		self.svc.script("connector", (429, {"Retry-After": "7"}))
		delivery = self.send()
		self.assertTrue(delivery.provider_message_id.startswith("fake-activity-"))
		self.assertEqual(self.sleeps, [7.0])
		self.assertEqual(len(self.svc.requests("connector")), 2)

	def test_retry_after_capped(self):
		self.svc.script("connector", (429, {"Retry-After": "3600"}))
		self.send()
		self.assertEqual(self.sleeps, [client._BACKOFF_CAP])

	def test_412_502_504_then_success(self):
		for status in (412, 502, 504):
			with self.subTest(status=status):
				self.sleeps.clear()
				self.svc.clear_log()
				self.svc.script("connector", status, status)
				self.send()
				self.assertEqual(len(self.svc.requests("connector")), 3)
				self.assertEqual(len(self.sleeps), 2)
				self.assertGreaterEqual(self.sleeps[1], self.sleeps[0])

	def test_max_attempts_exhausted_is_transient(self):
		self.svc.script("connector", 502, 502, 502, 502)
		with self.assertRaises(client.TeamsTransientError) as cm:
			self.send()
		self.assertTrue(cm.exception.retryable)
		self.assertNotIsInstance(cm.exception, client.send_errors())
		self.assertEqual(len(self.svc.requests("connector")), 3)
		self.assert_no_secrets(str(cm.exception))

	def test_connector_401_refreshes_token_once(self):
		self.svc.script("connector", 401)
		self.send()
		self.assertEqual(len(self.svc.requests("token")), 2)
		self.assertEqual(len(self.svc.requests("connector")), 2)

	def test_connector_403_twice_is_permanent(self):
		self.svc.script("connector", 403, 403)
		with self.assertRaises(client.TeamsPermanentError):
			self.send()
		self.assertEqual(len(self.svc.requests("connector")), 2)

	def test_400_permanent_no_retry(self):
		self.svc.script(
			"connector", {"status": 400, "body": {"error": {"code": "BadArgument", "message": SECRET}}}
		)
		with self.assertRaises(client.TeamsPermanentError) as cm:
			self.send()
		self.assertIn("BadArgument", str(cm.exception))
		self.assertEqual(len(self.svc.requests("connector")), 1)
		self.assertEqual(self.sleeps, [])
		self.assert_no_secrets(str(cm.exception))

	def test_redirect_not_followed(self):
		self.svc.script("connector", (302, {"Location": "http://169.254.169.254/"}))
		with self.assertRaises(client.TeamsPermanentError):
			self.send()
		self.assertEqual(len(self.svc.requests()), 2)  # token + one connector call, nothing else


class TestSsrf(_Base):
	def test_bad_service_urls_rejected_before_any_request(self):
		for bad in ("http://smba.trafficmanager.net/amer", "https://evil.example.com/", "https://10.0.0.1/"):
			with self.subTest(bad=bad):
				with patch.object(refs, "get_reference", return_value={"serviceUrl": bad}):
					with self.assertRaises(client.TeamsPermanentError):
						self.send()
		self.assertEqual(self.svc.requests(), [])
		self.assertEqual(self.urls, [])

	def test_poisoned_cache_entry_is_not_used(self):
		refs.frappe.cache.set_value(
			refs._cache_key(tf.BOT_APP_ID, "a:poison"), {"serviceUrl": "https://evil.example.com"}
		)
		with patch.object(refs, "_from_gateway_event", return_value=None):
			with self.assertRaises(client.TeamsPermanentError) as cm:
				self.send(conversation_id="a:poison")
		self.assertIn("must message the bot first", str(cm.exception))
		self.assertEqual(self.svc.requests(), [])

	def test_validate_called_on_every_send(self):
		with patch.object(refs, "validate_service_url", wraps=refs.validate_service_url) as v:
			self.send("a")
			self.send("b")
		self.assertEqual(v.call_count, 2 + 2)  # get_reference's _clean + the client's own check, per send


class TestSplit(_Base):
	def test_large_text_split_on_paragraphs_in_order(self):
		paras = [f"P{i:03d} " + ("x" * 4000) for i in range(30)]  # ~240 KB UTF-16
		delivery = self.send("\n\n".join(paras))
		reqs = self.svc.requests("connector")
		self.assertGreater(len(reqs), 1)
		texts = [r.body["text"] for r in reqs]
		for t, r in zip(texts, reqs, strict=True):
			self.assertLessEqual(client.activity_size(r.body), client.TARGET_BYTES)
			self.assertTrue(t.startswith("P"))
		self.assertEqual("\n\n".join(texts).split("\n\n"), paras)
		self.assertEqual(
			delivery.provider_response["activity_ids"],
			[f"fake-activity-{i}" for i in range(2, 2 + len(reqs))],
		)
		self.assertEqual(delivery.provider_message_id, delivery.provider_response["activity_ids"][0])

	def test_single_huge_paragraph_hard_split(self):
		text = "y" * 100_000  # one 200 KB UTF-16 paragraph, no separators
		self.send(text)
		reqs = self.svc.requests("connector")
		self.assertEqual("".join(r.body["text"] for r in reqs), text)
		for r in reqs:
			self.assertLessEqual(client.activity_size(r.body), client.HARD_LIMIT_BYTES)

	def test_partial_delivery_is_permanent(self):
		self.svc.script("connector", 200, 400)
		with self.assertRaises(client.TeamsPermanentError) as cm:
			self.send("\n\n".join("z" * 30000 for _ in range(3)))
		self.assertIn("partially delivered", str(cm.exception))
		self.assertEqual(len(cm.exception.delivered_ids), 1)

	def test_split_text_sentence_boundaries(self):
		chunks = client.split_text("One. Two. Three.", lambda c: len(c) <= 9)
		self.assertEqual(chunks, ["One. Two.", "Three."])


class TestAdapterWiring(_Base):
	def test_adapter_context_hook_supplies_gateway_name(self):
		hook = provider_hooks.get("Microsoft Teams", "adapter_context")
		self.assertEqual(hook(type("G", (), {"name": "Teams GW"})(), ""), {"gateway_name": "Teams GW"})
		self.assertEqual(
			provider_hooks.get("Microsoft Teams", "send_errors")(), (client.TeamsPermanentError,)
		)

	def test_adapter_send_reply_delegates(self):
		adapter = TeamsGatewayAdapter(
			CREDS, gateway_context={"gateway_name": "Teams GW"}, transport=self.transport
		)
		delivery = adapter.send_reply(GatewayReply(conversation_id=CONV, text="via adapter"))
		self.assertTrue(delivery.accepted)
		self.assertFalse(hasattr(adapter, "send_adaptive_card"))
		self.assertFalse(hasattr(client, "send_adaptive_card"))

	def test_conformance_for_teams_adapter(self):
		from huf.ai.gateway_adapters.conformance import assert_adapter_conforms
		from huf.ai.gateway_adapters.types import GatewayInboundRequest

		adapter = TeamsGatewayAdapter(
			CREDS, gateway_context={"gateway_name": "Teams GW"}, transport=self.transport
		)
		request = GatewayInboundRequest(body=json.dumps(tf.personal_message("hi")).encode(), headers={})
		with patch("huf.ai.teams.auth.verify_request", return_value=True):
			assert_adapter_conforms(adapter, request, GatewayReply(conversation_id=CONV, text="ok"))

