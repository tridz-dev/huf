from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai import secrets as S
from huf.ai.tools.gateway_pairing_tools import setup_gateway


class TestSecretStash(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _stash(self, **kw):
		return S.stash_secret({"access_token": "EAAxxxxxxxxxxxxxxxx", "app_secret": "s3cretvalue"}, "t", **kw)

	def test_stash_never_echoes(self):
		r = self._stash()
		self.assertTrue(r["credentials_ref"].startswith("SS-"))
		self.assertNotIn("EAA", str(r))
		self.assertEqual(r["fields"], ["access_token", "app_secret"])

	def test_resolve_single_use(self):
		ref = self._stash()["credentials_ref"]
		self.assertEqual(S.resolve_and_consume(ref, "Administrator")["app_secret"], "s3cretvalue")
		with self.assertRaises(frappe.ValidationError):
			S.resolve_and_consume(ref, "Administrator")

	def test_expiry(self):
		ref = self._stash()["credentials_ref"]
		frappe.db.set_value("Huf Secret Stash", ref, "expires_at", now_datetime() - timedelta(minutes=1))
		with self.assertRaises(frappe.ValidationError):
			S.resolve_and_consume(ref, "Administrator")
		S.purge_expired()
		self.assertFalse(frappe.db.exists("Huf Secret Stash", ref))

	def test_owner_mismatch(self):
		ref = self._stash()["credentials_ref"]
		with self.assertRaises(frappe.PermissionError):
			S.resolve_and_consume(ref, "someone@example.com")

	def test_non_admin_rejected(self):
		with patch("huf.permissions.has_capability", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				self._stash()

	def test_agent_context_plaintext_rejected(self):
		with S.agent_tool_context():
			r = setup_gateway("Telegram", "GW-x", {"token": "123:abc"})
		self.assertFalse(r["success"])
		self.assertIn("credentials_ref", r["error"])

	def test_credentials_ref_path(self):
		ref = S.stash_secret({"token": "123456:ABCDEFGH"}, "t")["credentials_ref"]

		class FakeAdapter:
			seen = None

			def __init__(self, creds):
				FakeAdapter.seen = creds

		with patch("huf.ai.gateway_webhook._adapter_class_for_provider", return_value=FakeAdapter), patch(
			"huf.ai.tools.gateway_pairing_tools.provider_to_service_id",
			side_effect=RuntimeError("stop after validation"),
		):
			with self.assertRaises(RuntimeError):
				setup_gateway("Telegram", "GW-x", credentials_ref=ref, non_secret_fields={"chat": "1"})
		self.assertEqual(FakeAdapter.seen, {"token": "123456:ABCDEFGH", "chat": "1"})

	def test_agent_tool_call_masked(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Tool Call",
				"tool": "x",
				"tool_args": {"access_token": "EAAabcdefghijklmnop", "note": "use EAAabcdefghijklmnop"},
				"tool_result": '{"app_secret": "supersecretvalue"}',
			}
		)
		doc.validate()
		self.assertNotIn("EAAabcdefghijklmnop", str(doc.tool_args))
		self.assertNotIn("supersecretvalue", str(doc.tool_result))

	def test_consume_clears_stored_values(self):
		ref = self._stash()["credentials_ref"]
		S.resolve_and_consume(ref, "Administrator")
		self.assertEqual(frappe.db.count("Huf Secret Stash Field", {"parent": ref}), 0)
