# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-H: runner identity and session integrity (M4, M5)."""

from __future__ import annotations

from unittest.mock import patch

import frappe

from huf.ai.whatsapp import broadcast_runner as runner
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import _Base


class TestSession(_Base):
	def test_same_user_does_not_call_set_user(self):
		with patch.object(frappe, "set_user") as su:
			self.assertTrue(runner._user_can_write(frappe.session.user, "g"))
		su.assert_not_called()

	def test_switch_restores_session_state(self):
		other = "Guest" if frappe.session.user != "Guest" else "Administrator"
		frappe.local.session.data = frappe._dict(csrf_token="tok")
		frappe.local.session.sid = "real-sid"
		frappe.local.form_dict = frappe._dict(cmd="x")
		seen = []
		runner._gateway_write_ok.side_effect = lambda gw: seen.append(frappe.session.user) or True
		user = frappe.session.user
		runner._user_can_write(other, "g")
		self.assertEqual(seen, [other])
		self.assertEqual(frappe.session.user, user)
		self.assertEqual(frappe.local.session.sid, "real-sid")
		self.assertEqual(frappe.local.session.data.csrf_token, "tok")
		self.assertEqual(frappe.local.form_dict.cmd, "x")

	def test_restores_on_exception(self):
		other = "Guest" if frappe.session.user != "Guest" else "Administrator"
		user = frappe.session.user
		runner._gateway_write_ok.side_effect = RuntimeError("boom")
		with self.assertRaises(RuntimeError):
			runner._user_can_write(other, "g")
		self.assertEqual(frappe.session.user, user)

	def test_start_rejects_paused(self):
		b = self.make(status="Paused")
		with self.assertRaises(frappe.ValidationError):
			runner.start(b, user=frappe.session.user)
		self.assertEqual(frappe.db.get_value("WhatsApp Broadcast", b, "status"), "Paused")
