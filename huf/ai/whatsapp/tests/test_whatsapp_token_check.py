# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""check_token against the fake Graph server (real HTTP, nothing patched at the HTTP layer)."""

from __future__ import annotations

import json
import unittest

import frappe

from huf.ai.whatsapp import management as mgmt
from huf.ai.whatsapp import token_check as tc
from huf.testing import fake_graph_server as fake
from huf.ai.whatsapp.tests import test_whatsapp_fake_graph as fg

NON_ADMIN = "wa-tokencheck-user@example.com"


class _TokenCheckBase(fg.FakeGraphCase):
	def setUp(self):
		super().setUp()
		srv = self.server
		srv.token_revoked = False
		srv.token_info.update(type="SYSTEM_USER", expires_at=0, scopes=list(tc.REQUIRED_SCOPES), granular_scopes=None)
		srv.subscribed_apps.clear()
		self.gw = self.direct_gateway or self.bridge_gateway
		self._clear()
		self.addCleanup(self._clear)

	def _clear(self):
		cache = frappe.cache()
		cache.delete_value(tc._result_key(self.gw.name))
		cache.delete_value(tc._stamp_key(self.gw.name))

	def _set_creds(self, **kv):
		doc = frappe.get_doc("Integration Settings", self.gw.integration_settings)
		for key, value in kv.items():
			rows = [r for r in doc.credentials if r.key == key]
			if value is None:
				for r in rows:
					doc.remove(r)
			elif rows:
				rows[0].value = value
			else:
				doc.append("credentials", {"key": key, "value": value})
		doc.save(ignore_permissions=True)

	def _check(self, **kw):
		return mgmt.check_token(self.gw.name, **kw)

	def _assert_no_secrets(self, *results):
		blob = json.dumps(results, default=str)
		for secret in (self.server.token, fake.APP_SECRET):
			self.assertNotIn(secret, blob)
		self.assertNotIn("access_token=", blob)

	def _debug_calls(self):
		return self.server.requests_to("GET", "debug_token")

	def _total_calls(self):
		return len(self.server.requests)


class _Scenarios:
	def test_valid_system_user_token(self):
		self._set_creds(app_id=self.server.app_id)
		self.server.subscribe_app(["messages"])
		r = self._check()
		self.assertTrue(r["success"])
		self.assertTrue(r["valid"])
		self.assertEqual(r["source"], "debug_token")
		self.assertEqual(r["token_type"], "SYSTEM_USER")
		self.assertIsNone(r["expires_at"])
		self.assertEqual(r["missing_scopes"], [])
		self.assertEqual(r["waba_ids"], [self.server.waba_id])
		self.assertEqual(r["phone"]["verified_name"], "Fake Co")
		self.assertEqual(r["phone"]["quality"], "GREEN")
		self.assertEqual(r["phone"]["tier"], "TIER_1K")
		self.assertTrue(r["webhook_subscribed"])
		self.assertTrue(r["webhook_messages"])
		self.assertTrue(r["checked_at"])
		self.server.assert_clean()
		self._assert_no_secrets(r)

	def test_expired_token_190(self):
		self._set_creds(app_id=self.server.app_id)
		self.server.token_revoked = True
		r = self._check()
		self.assertTrue(r["success"])
		self.assertFalse(r["valid"])
		self.assertEqual(r["error_code"], 190)
		self.assertEqual(r["message"], tc.MSG_EXPIRED)
		self._assert_no_secrets(r)

	def test_missing_scopes(self):
		self._set_creds(app_id=self.server.app_id)
		self.server.token_info["scopes"] = ["whatsapp_business_messaging"]
		r = self._check()
		self.assertTrue(r["valid"])
		self.assertEqual(r["missing_scopes"], ["whatsapp_business_management"])
		self.assertEqual(r["waba_ids"], [self.server.waba_id])

	def test_user_token_with_expiry(self):
		self._set_creds(app_id=self.server.app_id)
		self.server.token_info.update(type="USER", expires_at=1893456000)
		r = self._check()
		self.assertEqual(r["token_type"], "USER")
		self.assertEqual(r["expires_at"], "2030-01-01T00:00:00Z")

	def test_fallback_without_app_secret(self):
		self._set_creds(app_secret=None, app_id=None)
		r = self._check()
		self.assertTrue(r["valid"])
		self.assertEqual(r["source"], "phone_number")
		self.assertIsNone(r["token_type"])
		self.assertEqual(r["phone"]["display"], self.server.phone["display_phone_number"])
		self.assertEqual(self._debug_calls(), [])
		self._assert_no_secrets(r)

	def test_fallback_revoked_token_maps_190(self):
		self._set_creds(app_secret=None, app_id=None)
		self.server.token_revoked = True
		r = self._check()
		self.assertFalse(r["valid"])
		self.assertEqual(r["message"], tc.MSG_EXPIRED)
		self.server.violations.clear()  # the 190 is the scenario under test, not a schema error

	def test_subscribed_false_and_true(self):
		self._set_creds(app_id=self.server.app_id)
		r = self._check()
		self.assertIs(r["webhook_subscribed"], False)
		self._clear()
		self.server.subscribe_app(["statuses"])
		r = self._check()
		self.assertTrue(r["webhook_subscribed"])
		self.assertIs(r["webhook_messages"], False)

	def test_rate_limit_and_cache(self):
		self._set_creds(app_id=self.server.app_id)
		first = self._check()
		calls = self._total_calls()
		second = self._check()
		self.assertEqual(self._total_calls(), calls)  # cache hit: no HTTP
		self.assertTrue(second["cached"])
		self.assertEqual(second["checked_at"], first["checked_at"])
		forced = self._check(force=1)  # bypasses cache, inside the 10 s window
		self.assertFalse(forced["success"])
		self.assertEqual(forced["error_code"], "rate_limited")
		self.assertEqual(self._total_calls(), calls)

	def test_timeout_and_no_secret_leak(self):
		self._set_creds(app_id=self.server.app_id)
		token = self.server.token

		def boom(url, params=None, headers=None):
			import requests

			raise requests.Timeout(f"{url}?access_token={token}")

		r = tc.run_check(tc.resolve_credentials(self.gw.name), boom)
		self.assertFalse(r["success"])
		self.assertEqual(r["message"], tc.MSG_TIMEOUT)
		self._assert_no_secrets(r)
		self.assertNotIn(token, tc.redact(f"GET /x?access_token={token}&y=1", token))

	def test_non_admin_denied(self):
		if not frappe.db.exists("User", NON_ADMIN):
			frappe.get_doc(
				{"doctype": "User", "email": NON_ADMIN, "first_name": "TC", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(NON_ADMIN)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			mgmt.check_token(self.gw.name)
		self.assertEqual(self.server.requests, [])


class TestTokenCheckDirect(_Scenarios, _TokenCheckBase):
	"""Direct mode (no WhatsApp connector): credentials come only from Integration Settings."""

	MODE = "direct"


@unittest.skipUnless(fg.bridge.is_available(), "frappe_whatsapp not installed")
class TestTokenCheckBridge(_Scenarios, _TokenCheckBase):
	"""Bridge mode: app id / WABA id come from the linked WhatsApp Account."""

	MODE = "bridge"

	def test_app_id_from_account_without_credential_row(self):
		r = self._check()
		self.assertEqual(r["source"], "debug_token")
		self.assertTrue(r["valid"])


class _Resp:
	def __init__(self, status, body):
		self.status_code = status
		self._body = body

	def json(self):
		return self._body


class TestTokenCheckAppSecretMapping(unittest.TestCase):
	"""Error-code mapping when the saved App Secret does not match the token's app (Graph code 100)."""

	BASE = "https://graph.example.test/v25.0"
	APPSECRET_ERR = {
		"error": {
			"message": "Invalid appsecret_proof provided in the API argument",
			"type": "GraphMethodException",
			"code": 100,
		}
	}

	def _run(self, body, status=400):
		from huf.ai.whatsapp import token_check as tc

		def http_get(url, params=None, headers=None):
			return _Resp(status, body)

		return tc.run_check(
			{"token": "EAAFAKE", "app_secret": "wrong-secret", "app_id": "123", "phone_id": "555", "waba_id": "", "base": self.BASE},
			http_get,
		)

	def test_code_100_appsecret_proof_maps_to_app_secret_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run(self.APPSECRET_ERR)
		self.assertIs(r["valid"], False)
		self.assertEqual(r["error_code"], 100)
		self.assertEqual(r["message"], tc.MSG_APP_SECRET)
		self.assertEqual(
			tc.MSG_APP_SECRET,
			"The app secret doesn't match this token's app. Check the App Secret in Meta app settings (Settings > Basic).",
		)
		self.assertNotIn("expired", r["message"])

	def test_nested_debug_error_appsecret_proof_maps_to_app_secret_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"data": {"is_valid": False, "error": self.APPSECRET_ERR["error"]}}, status=200)
		self.assertIs(r["valid"], False)
		self.assertEqual(r["message"], tc.MSG_APP_SECRET)

	def test_other_code_100_keeps_permission_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"error": {"message": "Unsupported get request", "code": 100}})
		self.assertEqual(r["message"], tc.MSG_PERMISSION)

	def test_code_190_keeps_expired_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"error": {"message": "Session has expired", "code": 190}})
		self.assertEqual(r["message"], tc.MSG_EXPIRED)

	def test_verify_with_meta_surfaces_app_secret_message(self):
		import frappe
		from huf.ai.whatsapp import credential_sync as cs
		from huf.ai.whatsapp import token_check as tc

		creds = {
			"access_token": "EAAFAKE",
			"app_secret": "wrong-secret",
			"app_id": "123",
			"phone_number_id": "555",
			"business_account_id": "",
			"graph_api_url": "https://graph.example.test",
			"graph_api_version": "v25.0",
		}
		with self.assertRaises(frappe.ValidationError) as ctx:
			cs.verify_with_meta(creds, lambda url, params=None, headers=None: _Resp(400, self.APPSECRET_ERR))
		self.assertIn(tc.MSG_APP_SECRET, str(ctx.exception))
		self.assertNotIn("expired or was revoked", str(ctx.exception))


class TestTokenCheckBadSignatureMapping(TestTokenCheckAppSecretMapping):
	"""Wrong App Secret: debug_token (access_token=app_id|secret) answers top-level code 190 'signature'."""

	SIGNATURE_ERR = {
		"error": {"message": "Invalid OAuth access token signature.", "type": "OAuthException", "code": 190}
	}

	def test_debug_token_190_signature_maps_to_app_secret_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run(self.SIGNATURE_ERR)
		self.assertIs(r["valid"], False)
		self.assertEqual(r["error_code"], 190)
		self.assertEqual(r["message"], tc.MSG_APP_SECRET)

	def test_plain_190_with_data_error_keeps_expired_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"data": {"is_valid": False, "error": {"code": 190, "message": "Session has expired"}}}, status=200)
		self.assertEqual(r["message"], tc.MSG_EXPIRED)

	def test_190_session_expired_without_signature_keeps_expired_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"error": {"message": "Session has expired on Monday", "type": "OAuthException", "code": 190}})
		self.assertEqual(r["message"], tc.MSG_EXPIRED)

	def test_190_error_validating_access_token_keeps_expired_message(self):
		from huf.ai.whatsapp import token_check as tc

		r = self._run({"error": {"message": "Error validating access token", "type": "OAuthException", "code": 190}})
		self.assertEqual(r["message"], tc.MSG_EXPIRED)
