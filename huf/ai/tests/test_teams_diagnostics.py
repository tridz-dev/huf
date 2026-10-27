"""WP-T10: Teams verify_teams_connection, offline against the fake token endpoint."""

from __future__ import annotations

import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.teams import client, diagnostics, readiness
from huf.tests import teams_fixtures as tf

SECRET = "s3cr3t-app-password-value"  # noqa: S105
GW = "Teams Verify GW"
ORDER = ["credentials", "token", "token_claims", "endpoint", "reference", "drops"]


def _jwt(**claims) -> str:
	def b64(obj):
		return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

	return f"{b64({'alg': 'none'})}.{b64(claims)}.c2lnbmF0dXJl"


GOOD_JWT = _jwt(appid=tf.BOT_APP_ID, tid=tf.TENANT_ID, secretclaim="raw-claim-value")


class TestVerifyTeamsConnection(unittest.TestCase):
	def setUp(self):
		ctx = tf.fake_bot_services()
		self.svc = ctx.__enter__()
		self.addCleanup(ctx.__exit__, None, None, None)
		self.creds = {"app_id": tf.BOT_APP_ID, "app_password": SECRET, "tenant_id": tf.TENANT_ID}
		self.gateway = SimpleNamespace(
			name=GW,
			provider="Microsoft Teams",
			is_enabled=1,
			_load_integration_credentials=lambda: self.creds,
		)
		self.perm = patch("frappe.has_permission", return_value=True)
		self.perm_mock = self.perm.start()
		self.addCleanup(self.perm.stop)
		p = patch("frappe.get_doc", side_effect=lambda *a, **k: self.gateway)
		p.start()
		self.addCleanup(p.stop)
		p = patch.object(client, "_AUTHORITY_BASE", self.svc.base_url)
		p.start()
		self.addCleanup(p.stop)
		p = patch.object(readiness, "_public_base_url", return_value="https://huf.example.com")
		p.start()
		self.addCleanup(p.stop)
		frappe.cache.delete_value(readiness.DROPS_PREFIX + GW)
		frappe.cache.delete_value(readiness.DROPS_PREFIX + readiness.AUTH_BUCKET)
		self.clear()
		self.addCleanup(self.clear)

	def clear(self):
		frappe.cache.delete_value(diagnostics._RATE_PREFIX + GW)
		client.clear_token_cache(tf.TENANT_ID, tf.BOT_APP_ID, SECRET)

	def run_verify(self):
		self.clear_rate()
		return diagnostics.verify_teams_connection(GW)

	def clear_rate(self):
		frappe.cache.delete_value(diagnostics._RATE_PREFIX + GW)

	def script_token(self, body, status=200):
		self.svc.script("token", {"status": status, "body": body})

	def by_id(self, result):
		return {s["id"]: s for s in result["steps"]}

	def assert_shape(self, result):
		self.assertEqual(set(result), {"ok", "steps", "message"})
		self.assertIsInstance(result["ok"], bool)
		self.assertIsInstance(result["message"], str)
		self.assertEqual([s["id"] for s in result["steps"]], ORDER)
		for s in result["steps"]:
			self.assertEqual(set(s), {"id", "label", "ok", "detail"})
			self.assertIsInstance(s["label"], str)
			self.assertIsInstance(s["ok"], bool)
			self.assertTrue(s["detail"] is None or isinstance(s["detail"], str))

	def assert_no_secrets(self, result, *extra):
		blob = json.dumps(result)
		for bad in (SECRET, GOOD_JWT, "raw-claim-value", "access_token", *extra):
			self.assertNotIn(bad, blob)

	def test_wrong_secret_fails_even_if_other_gateway_cached_good_token(self):
		other = {"app_id": tf.BOT_APP_ID, "tenant_id": tf.TENANT_ID, "app_password": "another-gateway-secret"}
		self.addCleanup(client.clear_token_cache, tf.TENANT_ID, tf.BOT_APP_ID, "another-gateway-secret")
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		client.get_token(other)  # another gateway with the same app id cached a good token
		self.script_token({"error": "invalid_client", "error_description": "AADSTS7000215 bad"}, status=401)
		result = self.run_verify()
		self.assertFalse(result["ok"])
		self.assertFalse(self.by_id(result)["token"]["ok"])
		self.assertEqual(
			client._tokens.get(
				(
					tf.TENANT_ID,
					tf.BOT_APP_ID,
					client._secret_hash(tf.TENANT_ID, tf.BOT_APP_ID, "another-gateway-secret"),
				)
			)[0],
			GOOD_JWT,
		)  # the other gateway's token was not purged

	def test_happy_path(self):
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600, "token_type": "Bearer"})
		with (
			self.assertLogs("huf.teams.diagnostics", level="DEBUG") as logs,
			patch.object(diagnostics.logger, "warning"),
		):
			diagnostics.logger.debug("sentinel")
			result = self.run_verify()
		self.assert_shape(result)
		steps = self.by_id(result)
		self.assertTrue(result["ok"])
		for sid in ("credentials", "token", "token_claims"):
			self.assertTrue(steps[sid]["ok"], sid)
		self.assertTrue(steps["endpoint"]["ok"])
		self.assertFalse(steps["reference"]["ok"])  # no verified event yet
		self.assertEqual(len(self.svc.requests("token")), 1)
		self.assert_no_secrets(result)
		self.assertNotIn(GOOD_JWT, "\n".join(logs.output))

	def test_forced_refresh_bypasses_cache(self):
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		self.run_verify()
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		self.run_verify()
		self.assertEqual(len(self.svc.requests("token")), 2)

	def test_aadsts_mappings(self):
		cases = {
			"AADSTS7000215": "Invalid client secret",
			"AADSTS7000222": "expired",
			"AADSTS700016": "Application not found",
			"AADSTS90002": "Tenant not found",
		}
		for code, phrase in cases.items():
			with self.subTest(code=code):
				self.script_token(
					{"error": "invalid_client", "error_description": f"{code}: Trace ID {SECRET} stuff"},
					status=401,
				)
				result = self.run_verify()
				self.assert_shape(result)
				self.assertFalse(result["ok"])
				steps = self.by_id(result)
				self.assertFalse(steps["token"]["ok"])
				self.assertIn(phrase, steps["token"]["detail"])
				self.assertFalse(steps["token_claims"]["ok"])
				self.assert_no_secrets(result, "Trace ID")

	def test_other_aadsts_is_generic_with_code_only(self):
		self.script_token(
			{"error": "invalid_request", "error_description": "AADSTS50034: user x@y.z"}, status=400
		)
		result = self.run_verify()
		detail = self.by_id(result)["token"]["detail"]
		self.assertIn("AADSTS50034", detail)
		self.assertNotIn("x@y.z", json.dumps(result))

	def test_rejection_without_code(self):
		self.script_token({"error": "invalid_client"}, status=401)
		detail = self.by_id(self.run_verify())["token"]["detail"]
		self.assertIn("rejected the credentials", detail)

	def test_wrong_tenant_and_app_in_claims(self):
		cases = {
			"tenant": (_jwt(appid=tf.BOT_APP_ID, tid=tf.OTHER_TENANT_ID), "different tenant"),
			"app": (
				_jwt(appid="00000000-0000-4000-8000-0000000000ff", tid=tf.TENANT_ID),
				"different application",
			),
			"opaque": ("not-a-jwt", "could not be decoded"),
		}
		for name, (token, phrase) in cases.items():
			with self.subTest(name):
				self.script_token({"access_token": token, "expires_in": 3600})
				result = self.run_verify()
				steps = self.by_id(result)
				self.assertTrue(steps["token"]["ok"])
				self.assertFalse(steps["token_claims"]["ok"])
				self.assertIn(phrase, steps["token_claims"]["detail"])
				self.assertFalse(result["ok"])
				self.assert_no_secrets(result, token)

	def test_azp_claim_accepted(self):
		self.script_token(
			{"access_token": _jwt(azp=tf.BOT_APP_ID.upper(), tid=tf.TENANT_ID), "expires_in": 60}
		)
		self.assertTrue(self.run_verify()["ok"])

	def test_missing_credentials(self):
		self.creds = {"app_id": "not-a-guid", "app_password": "", "tenant_id": ""}
		result = self.run_verify()
		self.assert_shape(result)
		steps = self.by_id(result)
		self.assertFalse(result["ok"])
		detail = steps["credentials"]["detail"]
		for needle in ("app_id is not a GUID", "tenant_id is missing", "app_password is missing"):
			self.assertIn(needle, detail)
		self.assertFalse(steps["token"]["ok"])
		self.assertEqual(self.svc.requests("token"), [])
		self.assert_no_secrets(result, "not-a-guid")

	def test_timeout_maps_to_unreachable(self):
		def boom(*a, **k):
			raise TimeoutError(f"timed out talking to {SECRET}")  # noqa: TRY003

		with patch.object(client, "_requests_transport", boom):
			result = self.run_verify()
		self.assert_shape(result)
		self.assertIn("Could not reach Microsoft login", self.by_id(result)["token"]["detail"])
		self.assert_no_secrets(result)

	def test_http_500_maps_to_unreachable(self):
		self.script_token({"error": "server_error"}, status=500)
		self.assertIn("Could not reach Microsoft login", self.by_id(self.run_verify())["token"]["detail"])

	def test_unexpected_error_is_redacted(self):
		with patch.object(client, "get_token", side_effect=RuntimeError(SECRET)):
			result = self.run_verify()
		self.assertIn("Could not obtain a token", self.by_id(result)["token"]["detail"])
		self.assert_no_secrets(result)

	def test_permission_denied(self):
		self.perm_mock.side_effect = frappe.PermissionError
		with self.assertRaises(frappe.PermissionError):
			diagnostics.verify_teams_connection(GW)
		self.perm_mock.assert_called_with("Gateway", "write", GW, throw=True)
		self.assertEqual(self.svc.requests("token"), [])

	def test_wrong_provider(self):
		self.gateway.provider = "Telegram"
		with self.assertRaises(frappe.ValidationError):
			diagnostics.verify_teams_connection(GW)
		self.assertEqual(self.svc.requests("token"), [])

	def test_rate_limit(self):
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		self.clear_rate()
		diagnostics.verify_teams_connection(GW)
		with self.assertRaises(frappe.TooManyRequestsError):
			diagnostics.verify_teams_connection(GW)
		self.assertEqual(len(self.svc.requests("token")), 1)

	def test_endpoint_disabled_gateway_is_informational(self):
		self.gateway.is_enabled = 0
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		result = self.run_verify()
		self.assertTrue(result["ok"])
		self.assertFalse(self.by_id(result)["endpoint"]["ok"])

	def test_is_whitelisted_post(self):
		self.assertIn(diagnostics.verify_teams_connection, frappe.whitelisted)

	def test_drops_step_is_informational_and_summarises(self):
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		result = self.run_verify()
		self.assertEqual(self.by_id(result)["drops"]["detail"], "No dropped activities in the last 24 hours.")
		readiness.record_drop(GW, "tenant")
		readiness.record_drop(readiness.AUTH_BUCKET, "auth:pre_iss")
		self.addCleanup(frappe.cache.delete_value, readiness.DROPS_PREFIX + GW)
		self.addCleanup(frappe.cache.delete_value, readiness.DROPS_PREFIX + readiness.AUTH_BUCKET)
		self.script_token({"access_token": GOOD_JWT, "expires_in": 3600})
		result = self.run_verify()
		self.assert_shape(result)
		drops = self.by_id(result)["drops"]
		self.assertTrue(drops["ok"])
		self.assertTrue(result["ok"])
		self.assertIn("1 tenant", drops["detail"])
		self.assertIn("auth:pre_iss", drops["detail"])
		self.assertEqual(result["steps"][-1]["id"], "drops")


if __name__ == "__main__":
	unittest.main()
