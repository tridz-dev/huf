"""C-028: pairing codes are approval credentials; list_pairing_requests must never echo them in full."""

import re
import secrets
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai.tools import gateway_pairing_tools as tools

FULL_CODE_RE = re.compile(r"PAIR-[A-Z2-9]{8}")


class TestPairingCodeListing(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = secrets.token_hex(3)
		self.gateways: list[str] = []
		patcher = patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=MagicMock())
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self.gateways:
			frappe.db.delete("Gateway Access Entry", {"gateway": name})
			frappe.db.delete("Gateway", {"name": name})
		frappe.db.commit()

	def make_gateway(self, label):
		name = f"C028 {label} {self.suffix}"
		frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": name, "provider": "WhatsApp", "is_enabled": 0, "direct_policy": "Pairing"}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Gateway", name, {"is_enabled": 1, "execution_user": "Administrator", "integration_settings": "x"})
		self.gateways.append(name)
		return name

	def make_entry(self, gateway, external_id, code):
		return (
			frappe.get_doc(
				{
					"doctype": "Gateway Access Entry",
					"gateway": gateway,
					"entry_type": "Sender",
					"provider": "WhatsApp",
					"external_id": external_id,
					"pairing_code": code,
					"state": "Pending",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_admin_list_never_returns_a_full_pairing_code(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", "PAIR-ABCD2345")
		rows = tools.list_pairing_requests(a)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["entry_id"], entry)
		self.assertNotEqual(rows[0]["pairing_code"], "PAIR-ABCD2345")
		self.assertFalse(FULL_CODE_RE.search(str(rows)), rows)
		self.assertTrue(rows[0]["pairing_code"].endswith("45"))

	def test_approve_by_entry_name_from_masked_list_still_works(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230002", "PAIR-ABCD2345")
		row = tools.list_pairing_requests(a)[0]
		result = tools.approve_pairing_code(row["entry_id"], gateway_name=a)
		self.assertTrue(result["success"], result)
		self.assertEqual(result["entry_id"], entry)
		self.assertEqual(result["state"], "Approved")

	def test_approve_by_full_code_still_works(self):
		a = self.make_gateway("A")
		self.make_entry(a, "15551230003", "PAIR-ABCD2345")
		result = tools.approve_pairing_code("PAIR-ABCD2345", gateway_name=a)
		self.assertTrue(result["success"], result)

	def test_non_admin_cannot_list_pairing_codes(self):
		a = self.make_gateway("A")
		self.make_entry(a, "15551230004", "PAIR-ABCD2345")
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				tools.list_pairing_requests(a)
		finally:
			frappe.set_user("Administrator")
