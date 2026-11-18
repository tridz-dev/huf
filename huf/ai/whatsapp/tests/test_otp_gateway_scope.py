"""OTP sender Gateway scoping (User Permission based; generic Gateway read stays closed)."""

import unittest
from unittest.mock import patch

import frappe

from huf.ai.gateway_webhook import has_permission_gateway_family
from huf.ai.whatsapp import gateway_scope, otp

SENDER = [otp.OTP_SENDER_ROLE]


def _perms(*gateways):
	return {"Gateway": [{"doc": g, "applicable_for": None, "is_default": 0} for g in gateways]} if gateways else {}


class TestOtpGatewayScope(unittest.TestCase):
	def _run(self, roles, perms, *names):
		with patch("frappe.get_roles", return_value=roles), \
				patch("frappe.permissions.get_user_permissions", return_value=perms):
			return otp._gateway_forbidden("u@example.com", *names)

	def test_matching_user_permission_passes(self):
		self.assertIsNone(self._run(SENDER, _perms("GW"), "GW"))

	def test_other_gateway_permission_forbidden(self):
		self.assertEqual(self._run(SENDER, _perms("OTHER"), "GW")["error"], "gateway_forbidden")

	def test_no_user_permission_forbidden(self):
		self.assertEqual(self._run(SENDER, {}, "GW")["error"], "gateway_forbidden")

	def test_sms_gateway_not_permitted_forbidden(self):
		self.assertEqual(self._run(SENDER, _perms("GW"), "GW", "SMSGW")["error"], "gateway_forbidden")
		self.assertIsNone(self._run(SENDER, _perms("GW", "SMSGW"), "GW", "SMSGW"))

	def test_system_manager_passes(self):
		self.assertIsNone(self._run(["System Manager"], {}, "GW", "SMSGW"))

	def test_without_sender_role_denied(self):
		self.assertEqual(self._run(["Desk User"], _perms("GW"), "GW")["error"], "gateway_forbidden")

	def test_generic_gateway_read_hook_stays_closed(self):
		with patch.object(frappe.db, "get_value", return_value=None):
			self.assertFalse(has_permission_gateway_family(None, "read", "u@example.com"))
		self.assertTrue(callable(gateway_scope.sender_may_use_gateway))
