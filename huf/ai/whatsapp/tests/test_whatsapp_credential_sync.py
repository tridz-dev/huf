# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Saving a WhatsApp credential: Meta checks, WhatsApp Account sync and gateway linking."""

from __future__ import annotations

import secrets
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import credential_sync as cs

PHONE_ID = "1100200300"
WABA_ID = "9900800700"


def creds(**over):
	base = {
		"phone_number_id": PHONE_ID,
		"business_account_id": WABA_ID,
		"app_id": "123456",
		"access_token": "EAAtoken",
		"app_secret": "shh",
		"webhook_verify_token": "verify",
	}
	base.update(over)
	return base


class FakeGraph:
	"""Answers the GETs ``verify_with_meta`` makes; records every URL."""

	def __init__(self, *, valid=True, wabas=(WABA_ID,), phone_found=True, waba_phones=(PHONE_ID,), down=False):
		self.valid, self.wabas, self.phone_found = valid, list(wabas), phone_found
		self.waba_phones, self.down, self.urls = list(waba_phones), down, []

	def __call__(self, url, params=None, headers=None):
		self.urls.append(url)
		if self.down:
			raise TimeoutError()
		if url.endswith("/debug_token"):
			data = {"is_valid": self.valid, "type": "SYSTEM_USER", "expires_at": 0, "scopes": list(cs.token_check.REQUIRED_SCOPES)}
			data["granular_scopes"] = [{"scope": s, "target_ids": self.wabas} for s in cs.token_check.REQUIRED_SCOPES]
			if not self.valid:
				data["error"] = {"code": 190, "message": "expired"}
			return self._resp(200, {"data": data})
		if url.endswith("/phone_numbers"):
			return self._resp(200, {"data": [{"id": p} for p in self.waba_phones]})
		if url.endswith("/subscribed_apps"):
			return self._resp(200, {"data": []})
		if url.endswith(f"/{PHONE_ID}"):
			if not self.phone_found:
				return self._resp(400, {"error": {"code": 100, "message": "Unsupported get request"}})
			return self._resp(200, {"display_phone_number": "+91 98765 43210", "verified_name": "Harbor Bakery"})
		return self._resp(404, {"error": {"code": 803, "message": "unknown"}})

	@staticmethod
	def _resp(status, body):
		return SimpleNamespace(status_code=status, json=lambda: body)


class TestVerifyWithMeta(unittest.TestCase):
	def test_valid_credentials_return_phone_details(self):
		phone = cs.verify_with_meta(creds(), FakeGraph())
		self.assertEqual(phone["verified_name"], "Harbor Bakery")

	def test_rejected_token_refuses_save(self):
		with self.assertRaises(frappe.ValidationError):
			cs.verify_with_meta(creds(), FakeGraph(valid=False))

	def test_unknown_phone_number_refuses_save(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			cs.verify_with_meta(creds(), FakeGraph(phone_found=False))
		self.assertIn(PHONE_ID, str(ctx.exception))

	def test_business_account_the_token_cannot_manage_refuses_save(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			cs.verify_with_meta(creds(), FakeGraph(wabas=("555",)))
		self.assertIn(WABA_ID, str(ctx.exception))

	def test_phone_number_of_another_business_account_refuses_save(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			cs.verify_with_meta(creds(), FakeGraph(waba_phones=("777",)))
		self.assertIn("doesn't belong", str(ctx.exception))

	def test_meta_unreachable_never_blocks(self):
		self.assertEqual(cs.verify_with_meta(creds(), FakeGraph(down=True)), {})

	def test_errors_never_echo_the_token(self):
		try:
			cs.verify_with_meta(creds(), FakeGraph(valid=False))
		except frappe.ValidationError as exc:
			self.assertNotIn("EAAtoken", str(exc))


class TestValidateCredential(unittest.TestCase):
	def setUp(self):
		frappe.flags.huf_whatsapp_credential_checks = True
		self.addCleanup(setattr, frappe.flags, "huf_whatsapp_credential_checks", False)

	def _doc(self, values):
		rows = [SimpleNamespace(key=k, value=v) for k, v in values.items()]
		return SimpleNamespace(service="whatsapp", credentials=rows)

	def test_business_account_and_app_id_are_required(self):
		values = creds()
		del values["business_account_id"], values["app_id"]
		with self.assertRaises(frappe.ValidationError) as ctx:
			cs.validate_credential(self._doc(values))
		self.assertIn("WhatsApp Business Account ID", str(ctx.exception))
		self.assertIn("Meta App ID", str(ctx.exception))

	def test_graph_version_is_optional(self):
		cs.validate_credential(self._doc(creds()))

	def test_runtime_keys_alone_still_run_an_existing_gateway(self):
		from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

		values = creds()
		del values["business_account_id"], values["app_id"]
		WhatsAppGatewayAdapter(values)  # no ValueError: older credentials keep receiving and sending


@unittest.skipUnless(bridge.is_available(), "frappe_whatsapp is not installed")
class TestAccountSync(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.huf_whatsapp_credential_checks = True
		self.addCleanup(setattr, frappe.flags, "huf_whatsapp_credential_checks", False)
		self.phone = f"77{secrets.randbelow(10**8):08d}"
		self.made: list[tuple[str, str]] = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for doctype, name in reversed(self.made):
			frappe.db.delete(doctype, {"name": name})
		for name in frappe.get_all(cs.ACCOUNT_DOCTYPE, {"phone_id": self.phone}, pluck="name"):
			frappe.db.delete(cs.ACCOUNT_DOCTYPE, {"name": name})

	def _settings(self):
		doc = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"is_active": 0,  # inserted inactive: no sync until the test turns it on
				"credentials": [{"key": k, "value": v} for k, v in creds(phone_number_id=self.phone).items()],
			}
		).insert(ignore_permissions=True)
		self.made.append(("Integration Settings", doc.name))
		return doc

	def _gateway(self, settings):
		name = f"WA sync {self.phone}"
		frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": name, "provider": "WhatsApp", "is_enabled": 0, "integration_settings": settings}
		).insert(ignore_permissions=True)
		self.made.append(("Gateway", name))
		return name

	def _save_active(self, doc):
		doc.is_active = 1
		with (
			patch.object(cs, "verify_with_meta", return_value={"display": "+1 555", "verified_name": "Harbor"}),
			patch.object(cs, "subscribe_app", return_value=True) as subscribe,
			patch.object(cs.frappe, "enqueue") as enqueue,
		):
			doc.save(ignore_permissions=True)
		return subscribe, enqueue

	def test_save_creates_account_and_links_gateway(self):
		settings = self._settings()
		gateway = self._gateway(settings.name)
		subscribe, enqueue = self._save_active(settings)

		account = frappe.db.get_value(cs.ACCOUNT_DOCTYPE, {"phone_id": self.phone}, "name")
		self.assertTrue(account)
		row = frappe.get_doc(cs.ACCOUNT_DOCTYPE, account)
		self.assertEqual(row.business_id, WABA_ID)
		self.assertEqual(row.app_id, "123456")
		self.assertEqual(row.get_password("token"), "EAAtoken")
		self.assertEqual(row.status, "Active")
		# never frappe_whatsapp's default inbox, never able to answer Meta's webhook check itself
		self.assertFalse(row.is_default_incoming)
		self.assertFalse(row.webhook_verify_token)

		linked = frappe.db.get_value("Gateway", gateway, ["whatsapp_account", "phone_number_id", "whatsapp_business_account_id"], as_dict=True)
		self.assertEqual(linked.whatsapp_account, account)
		self.assertEqual(linked.phone_number_id, self.phone)
		self.assertEqual(linked.whatsapp_business_account_id, WABA_ID)
		subscribe.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["account"], account)

	def test_second_save_updates_the_same_account(self):
		settings = self._settings()
		self._save_active(settings)
		for row in settings.credentials:
			if row.key == "access_token":
				row.value = "EAAnewtoken"
		self._save_active(settings)
		accounts = frappe.get_all(cs.ACCOUNT_DOCTYPE, {"phone_id": self.phone}, pluck="name")
		self.assertEqual(len(accounts), 1)
		self.assertEqual(frappe.get_doc(cs.ACCOUNT_DOCTYPE, accounts[0]).get_password("token"), "EAAnewtoken")

	def test_gateway_connected_later_links_the_existing_account(self):
		settings = self._settings()
		self._save_active(settings)
		gateway = self._gateway(settings.name)
		account = frappe.db.get_value(cs.ACCOUNT_DOCTYPE, {"phone_id": self.phone}, "name")
		self.assertEqual(frappe.db.get_value("Gateway", gateway, "whatsapp_account"), account)
