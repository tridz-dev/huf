"""Offline tests for Teams inbound JWT validation (huf.ai.teams.auth). Fake OpenID/JWKS on loopback only."""

import base64
import hashlib
import hmac
import json
import threading
import time
import unittest
from unittest import mock

import jwt as pyjwt

from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.teams import auth
from huf.tests import teams_fixtures as tf

CREDS = {"app_id": tf.BOT_APP_ID, "app_password": "unused", "tenant_id": tf.TENANT_ID}


def _b64(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class TeamsAuthBase(unittest.TestCase):
	def setUp(self):
		cm = tf.fake_bot_services()
		self.svc = cm.__enter__()
		self.addCleanup(cm.__exit__, None, None, None)
		self.key = tf.default_signing_key()
		self.svc.set_jwks(tf.build_jwks(self.key))
		auth._set_test_openid_url(self.svc.openid_url)
		self.addCleanup(auth._set_test_openid_url, None)
		self.activity = tf.personal_message(service_url=self.svc.connector_url)

	def request(self, token=None, activity=None, *, body=None, headers=None):
		activity = activity if activity is not None else self.activity
		hdrs = dict(headers) if headers is not None else {}
		if headers is None and token is not None:
			hdrs["Authorization"] = f"Bearer {token}"
		raw = body if body is not None else json.dumps(activity).encode()
		return GatewayInboundRequest(body=raw, headers=hdrs, query={}, method="POST")

	def token(self, **kw):
		return tf.make_bot_token(self.activity, **kw)

	def verify(self, token=None, **kw):
		return auth.verify_request(self.request(token, **kw), CREDS)

	def jwks_fetches(self):
		return len(self.svc.requests("jwks"))


class TestValidation(TeamsAuthBase):
	def test_happy_path(self):
		self.assertTrue(self.verify(self.token()))
		self.assertEqual(self.jwks_fetches(), 1)

	def test_lowercase_serviceurl_claim_accepted(self):
		self.assertTrue(self.verify(self.token(service_url_claim_name="serviceurl")))

	def test_service_url_trailing_slash_and_host_case_normalized(self):
		url = self.svc.connector_url
		token = tf.make_bot_token(self.activity, service_url=url.rstrip("/"))
		self.assertTrue(self.verify(token))

	def test_forged_signature(self):
		self.assertFalse(self.verify(tf.forged_token(self.activity)))

	def test_wrong_audience(self):
		self.assertFalse(self.verify(tf.wrong_audience_token(self.activity)))

	def test_wrong_issuer(self):
		self.assertFalse(self.verify(tf.wrong_issuer_token(self.activity)))

	def test_expired_beyond_leeway(self):
		self.assertFalse(self.verify(self.token(exp_delta=-(auth.CLOCK_SKEW_SECONDS + 60))))

	def test_expired_within_leeway_ok(self):
		self.assertTrue(self.verify(self.token(exp_delta=-60)))

	def test_nbf_in_future_beyond_leeway(self):
		self.assertFalse(self.verify(self.token(nbf_delta=auth.CLOCK_SKEW_SECONDS + 120, exp_delta=7200)))

	def test_nbf_within_leeway_ok(self):
		self.assertTrue(self.verify(self.token(nbf_delta=60)))

	def test_missing_exp_rejected(self):
		claims = {
			"iss": auth.BOT_FRAMEWORK_ISSUER,
			"aud": tf.BOT_APP_ID,
			"serviceUrl": self.svc.connector_url,
		}
		token = pyjwt.encode(claims, self.key.private_pem, algorithm="RS256", headers={"kid": self.key.kid})
		self.assertFalse(self.verify(token))

	def test_service_url_mismatch(self):
		self.assertFalse(self.verify(tf.service_url_mismatch_token(self.activity)))

	def test_missing_service_url_claim(self):
		claims = {
			"iss": auth.BOT_FRAMEWORK_ISSUER,
			"aud": tf.BOT_APP_ID,
			"exp": int(time.time()) + 600,
		}
		token = pyjwt.encode(claims, self.key.private_pem, algorithm="RS256", headers={"kid": self.key.kid})
		self.assertFalse(self.verify(token))

	def test_channel_not_endorsed(self):
		self.svc.set_jwks(tf.build_jwks(self.key, endorsements=["webchat"]))
		self.assertFalse(self.verify(self.token()))

	def test_channel_endorsements_missing(self):
		jwks = tf.build_jwks(self.key)
		del jwks["keys"][0]["endorsements"]
		self.svc.set_jwks(jwks)
		self.assertFalse(self.verify(self.token()))

	def test_missing_app_id(self):
		self.assertFalse(auth.verify_request(self.request(self.token()), {"app_id": " "}))
		self.assertFalse(auth.verify_request(self.request(self.token()), {}))
		self.assertEqual(self.jwks_fetches(), 0)


class TestAlgorithmAttacks(TeamsAuthBase):
	def _claims(self):
		return {
			"iss": auth.BOT_FRAMEWORK_ISSUER,
			"aud": tf.BOT_APP_ID,
			"exp": int(time.time()) + 600,
			"serviceUrl": self.svc.connector_url,
		}

	def test_alg_none(self):
		token = pyjwt.encode(self._claims(), None, algorithm="none", headers={"kid": self.key.kid})
		self.assertFalse(self.verify(token))

	def test_hs256_signed_with_public_key(self):
		public_pem = self.key.private_key.public_key().public_bytes(*_public_encoding())
		header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": self.key.kid}).encode())
		payload = _b64(json.dumps(self._claims()).encode())
		sig = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
		self.assertFalse(self.verify(f"{header}.{payload}.{_b64(sig)}"))
		# also with the JWK modulus-less variant: public key text as secret via the JWK json
		sig2 = hmac.new(
			json.dumps(self.key.public_jwk).encode(), f"{header}.{payload}".encode(), hashlib.sha256
		)
		self.assertFalse(self.verify(f"{header}.{payload}.{_b64(sig2.digest())}"))


def _public_encoding():
	from cryptography.hazmat.primitives import serialization

	return serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo


class TestRequestShape(TeamsAuthBase):
	def test_missing_authorization_header(self):
		self.assertFalse(self.verify(headers={}))

	def test_non_bearer_and_garbled(self):
		for value in ("", "Bearer", "Bearer ", "Basic abc", "Bearer not.a.jwt", "Bearer a.b.c", "token"):
			with self.subTest(value=value):
				self.assertFalse(self.verify(headers={"Authorization": value}))

	def test_header_name_and_scheme_case_insensitive(self):
		self.assertTrue(self.verify(headers={"authorization": f"bearer {self.token()}"}))

	def test_non_json_body(self):
		self.assertFalse(self.verify(self.token(), body=b"not json"))
		self.assertFalse(self.verify(self.token(), body=b"[1,2]"))
		self.assertFalse(self.verify(self.token(), body=b"\xff\xfe"))

	def test_missing_service_url_or_channel_in_body(self):
		for field in ("serviceUrl", "channelId"):
			activity = {k: v for k, v in self.activity.items() if k != field}
			with self.subTest(field=field):
				self.assertFalse(self.verify(self.token(), activity=activity))

	def test_token_signed_for_other_activity_service_url(self):
		other = dict(self.activity, serviceUrl="https://smba.trafficmanager.net/emea/")
		self.assertFalse(self.verify(self.token(), activity=other))

	def test_never_raises_on_weird_input(self):
		req = GatewayInboundRequest(body=None, headers={"Authorization": None}, query={}, method="POST")
		self.assertIs(auth.verify_request(req, CREDS), False)


class TestKeyCache(TeamsAuthBase):
	def test_cache_reused(self):
		self.assertTrue(self.verify(self.token()))
		self.assertTrue(self.verify(self.token()))
		self.assertEqual(self.jwks_fetches(), 1)
		self.assertEqual(len(self.svc.requests("openid")), 1)

	def test_unknown_kid_refetches_once_then_rate_limited(self):
		self.assertTrue(self.verify(self.token()))
		self.assertEqual(self.jwks_fetches(), 1)
		bad = tf.unknown_kid_token(self.activity)
		self.assertFalse(self.verify(bad))
		self.assertEqual(self.jwks_fetches(), 2)  # the single forced refetch
		self.assertFalse(self.verify(bad))
		self.assertFalse(self.verify(bad))
		self.assertEqual(self.jwks_fetches(), 2)  # rate limited: no more refetches

	def test_forced_refetch_allowed_again_after_interval(self):
		self.assertTrue(self.verify(self.token()))
		bad = tf.unknown_kid_token(self.activity)
		self.assertFalse(self.verify(bad))
		self.assertEqual(self.jwks_fetches(), 2)
		future = time.time() + auth.MIN_FORCED_REFRESH_SECONDS + 1
		with mock.patch.object(auth.time, "time", return_value=future):
			self.assertFalse(self.verify(bad))
		self.assertEqual(self.jwks_fetches(), 3)

	def test_key_rotation_picked_up_by_unknown_kid_refetch(self):
		self.assertTrue(self.verify(self.token()))
		new_key = tf.generate_keypair(kid="rotated-key")
		self.svc.set_jwks(tf.build_jwks(self.key, new_key))
		token = tf.make_bot_token(self.activity, kid="rotated-key", key=new_key)
		self.assertTrue(self.verify(token))

	def test_outage_without_cache_fails_closed(self):
		self.svc.script("jwks", 500)
		self.assertFalse(self.verify(self.token()))
		self.svc.script("openid", 503)
		auth._reset_cache()
		self.assertFalse(self.verify(self.token()))

	def test_outage_without_cache_recovers_after_backoff(self):
		self.svc.script("jwks", 500)
		self.assertFalse(self.verify(self.token()))
		future = time.time() + auth.FAILURE_BACKOFF_SECONDS + 1
		token = self.token()
		with mock.patch.object(auth.time, "time", return_value=future):
			self.assertTrue(self.verify(token))

	def test_outage_with_cache_keeps_working(self):
		self.assertTrue(self.verify(self.token()))
		self.svc.script("openid", 500, 500)
		self.svc.script("jwks", 500, 500)
		future = time.time() + auth.KEY_TTL_SECONDS + 10  # TTL expired -> refresh attempted and fails
		token = self.token()
		with mock.patch.object(auth.time, "time", return_value=future):
			self.assertTrue(self.verify(token))

	def test_stale_cache_beyond_hard_limit_fails_closed(self):
		self.assertTrue(self.verify(self.token()))
		self.svc.script("openid", 500)
		future = time.time() + auth.STALE_KEY_MAX_SECONDS + 10
		token = self.token()
		with mock.patch.object(auth.time, "time", return_value=future):
			self.assertFalse(self.verify(token))

	def test_ttl_expiry_refetches(self):
		self.assertTrue(self.verify(self.token()))
		future = time.time() + auth.KEY_TTL_SECONDS + 10
		token = self.token()
		with mock.patch.object(auth.time, "time", return_value=future):
			self.assertTrue(self.verify(token))
		self.assertEqual(self.jwks_fetches(), 2)

	def test_redirect_not_followed_and_oversized_rejected(self):
		self.svc.script("openid", (302, {"Location": "http://127.0.0.1:9/evil"}))
		self.assertFalse(self.verify(self.token()))
		auth._reset_cache()
		self.svc.script("jwks", {"status": 200, "body": b" " * (auth.MAX_RESPONSE_BYTES + 10)})
		self.assertFalse(self.verify(self.token()))

	def test_bad_jwks_documents_fail_closed(self):
		for doc in ({"keys": []}, {"keys": "x"}, {"nokeys": 1}):
			with self.subTest(doc=doc):
				auth._reset_cache()
				self.svc.set_jwks(doc)
				self.assertFalse(self.verify(self.token()))

	def test_production_urls_are_strict(self):
		auth._set_test_openid_url(None)
		self.assertTrue(auth._url_ok(auth.BOT_FRAMEWORK_OPENID_URL))
		for url in (
			"http://login.botframework.com/v1/.well-known/keys",
			"https://evil.example/v1/.well-known/keys",
			"https://login.botframework.com.evil.example/keys",
			"http://127.0.0.1:1/keys",
			"https://login.botframework.com:8443/keys",
		):
			with self.subTest(url=url):
				self.assertFalse(auth._url_ok(url))

	def test_test_hook_rejects_non_loopback(self):
		with self.assertRaises(ValueError):
			auth._set_test_openid_url("http://example.com/x")
		with self.assertRaises(ValueError):
			auth._set_test_openid_url("http://127.0.0.1.evil.example/x")


class TestHygiene(TeamsAuthBase):
	def test_token_never_logged(self):
		good = self.token()
		bad = tf.forged_token(self.activity)
		self.svc.script("jwks", 500)
		with self.assertLogs("huf.teams.auth", level="DEBUG") as logs:
			self.verify(good)  # outage, no cache
			auth._reset_cache()
			self.verify(bad)
			self.verify(tf.wrong_audience_token(self.activity))
			self.verify(headers={"Authorization": "Bearer garbled.token.value"})
		text = "\n".join(logs.output)
		for secret in (good, bad, good.split(".")[1], good.split(".")[2], "garbled.token.value"):
			self.assertNotIn(secret, text)
		self.assertIn("rejected", text)

	def test_only_loopback_requests_made(self):
		self.verify(self.token())
		for record in self.svc.requests():
			self.assertIn(record.endpoint, ("openid", "jwks"))


if __name__ == "__main__":
	unittest.main()


class TestChannelPin(TeamsAuthBase):
	"""S1: tokens for other Bot Framework channels are rejected even when the key endorses them."""

	def test_endorsed_non_teams_channels_rejected(self):
		self.svc.set_jwks(
			tf.build_jwks(self.key, endorsements=["msteams", "webchat", "directline", "emulator"])
		)
		for channel in ("webchat", "directline", "emulator", "WebChat"):
			activity = dict(self.activity, channelId=channel)
			with self.subTest(channel=channel):
				self.assertFalse(self.verify(tf.make_bot_token(activity), activity=activity))

	def test_msteams_still_passes(self):
		self.svc.set_jwks(tf.build_jwks(self.key, endorsements=["msteams", "webchat"]))
		self.assertTrue(self.verify(self.token()))
		activity = dict(self.activity, channelId="MSTEAMS")
		self.assertTrue(self.verify(tf.make_bot_token(activity), activity=activity))


class TestForcedRefreshAbuse(TeamsAuthBase):
	"""S7: junk kids cannot burn the forced-refetch window; fetch never blocks cached verifications."""

	def test_junk_unknown_kid_with_bad_claims_does_not_consume_window(self):
		self.assertTrue(self.verify(self.token()))
		self.assertEqual(self.jwks_fetches(), 1)
		junk = [
			tf.make_bot_token(self.activity, kid="junk-1", audience="someone-else"),
			tf.make_bot_token(self.activity, kid="junk-2", issuer="https://evil.example"),
			tf.make_bot_token(self.activity, kid="junk-3", exp_delta=-3600),
			tf.make_bot_token(
				self.activity, kid="junk-4", service_url="https://smba.trafficmanager.net/evil/"
			),
			tf.make_bot_token(self.activity, kid="x" * 500),
			tf.make_bot_token(self.activity, kid="bad kid\n"),
		]
		for token in junk:
			self.assertFalse(self.verify(token))
		self.assertEqual(self.jwks_fetches(), 1)
		self.assertEqual(auth._state["last_forced"], 0.0)
		# A real rollover is still picked up: the window was not consumed.
		new_key = tf.generate_keypair(kid="rotated-after-spam")
		self.svc.set_jwks(tf.build_jwks(self.key, new_key))
		self.assertTrue(self.verify(tf.make_bot_token(self.activity, kid="rotated-after-spam", key=new_key)))

	def test_slow_fetch_does_not_block_cached_verification(self):
		self.assertTrue(self.verify(self.token()))
		release = threading.Event()
		started = threading.Event()
		real_fetch = auth._fetch_keys

		def slow_fetch():
			started.set()
			release.wait(10)
			return real_fetch()

		self.addCleanup(release.set)
		results = {}
		with mock.patch.object(auth, "_fetch_keys", side_effect=slow_fetch):
			slow = threading.Thread(
				target=lambda: results.setdefault("slow", self.verify(tf.unknown_kid_token(self.activity)))
			)
			slow.start()
			self.assertTrue(started.wait(5))
			good = self.token()
			fast = threading.Thread(target=lambda: results.setdefault("fast", self.verify(good)))
			t0 = time.monotonic()
			fast.start()
			fast.join(3)
			self.assertFalse(fast.is_alive(), "cached verification blocked by JWKS fetch")
			self.assertLess(time.monotonic() - t0, 3)
			self.assertTrue(results["fast"])
			release.set()
			slow.join(10)
		self.assertFalse(results["slow"])

	def test_concurrent_refreshes_are_single_flight(self):
		release = threading.Event()
		calls = []
		real_fetch = auth._fetch_keys

		def slow_fetch():
			calls.append(1)
			release.wait(5)
			return real_fetch()

		token = self.token()
		results = []
		with mock.patch.object(auth, "_fetch_keys", side_effect=slow_fetch):
			threads = [threading.Thread(target=lambda: results.append(self.verify(token))) for _ in range(4)]
			for t in threads:
				t.start()
			time.sleep(0.3)
			release.set()
			for t in threads:
				t.join(10)
		self.assertEqual(len(calls), 1)
		self.assertEqual(results, [True] * 4)
