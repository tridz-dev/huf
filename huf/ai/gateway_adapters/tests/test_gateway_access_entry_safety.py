"""WP-2 access-entry safety: revoke vs opt-out, pairing caps, admin authority, audit, masking."""

import re
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service as gsvc
from huf.ai.gateway_adapters.tests.test_gateway_pairing_hardening import _GatewayFixture

MASKED = re.compile(r"^\*+[A-Z0-9]{2}$")


class _Fixture(_GatewayFixture):
	def make_gateway(self, label, **kw):
		kw.setdefault("pairing_reply_enabled", 1)
		return super().make_gateway(label, **kw)

	def versions(self, entry):
		return frappe.db.count("Version", {"ref_doctype": "Gateway Access Entry", "docname": entry})


class TestRevokeKeepsOptOut(_Fixture, IntegrationTestCase):
	def test_revoke_after_stop_keeps_opted_out(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, "15551230001", state="Approved")
		self.ingest(a, "15551230001", "STOP")
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))

		result = gsvc.revoke_gateway_access_entry(entry)

		self.assertEqual(result["state"], "Opted out")
		self.assertEqual(self.entry_state(entry), "Opted out")
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))
		doc = frappe.get_doc("Gateway Access Entry", entry)
		self.assertIsNotNone(doc.revoked_at)
		self.assertEqual(doc.revoked_by, frappe.session.user)

	def test_start_after_revoke_does_not_restore_approval(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, "15551230001", state="Approved")
		self.ingest(a, "15551230001", "STOP")
		gsvc.revoke_gateway_access_entry(entry)
		self.ingest(a, "15551230001", "START")
		self.assertEqual(self.entry_state(entry), "Revoked")
		self.assertFalse(gsvc.is_opted_out(a, "15551230001"))
		self.assertNotEqual(self.ingest(a, "15551230001", "hello")["status"], "Queued")

	def test_revoke_does_not_downgrade_blocked(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", state="Blocked")
		self.assertEqual(gsvc.revoke_gateway_access_entry(entry)["state"], "Blocked")
		self.assertEqual(self.entry_state(entry), "Blocked")

	def test_revoke_normal_entry_sets_revoked_by(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", state="Approved")
		self.assertEqual(gsvc.revoke_gateway_access_entry(entry)["state"], "Revoked")
		self.assertEqual(frappe.db.get_value("Gateway Access Entry", entry, "revoked_by"), frappe.session.user)


class TestAudit(_Fixture, IntegrationTestCase):
	def test_revoke_approve_and_opt_out_write_versions(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, "15551230001", state="Approved")
		before = self.versions(entry)
		self.ingest(a, "15551230001", "STOP")
		self.assertGreater(self.versions(entry), before)
		before = self.versions(entry)
		gsvc.revoke_gateway_access_entry(entry)
		self.assertGreater(self.versions(entry), before)

	def test_approval_writes_a_version(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "15551230001", code="PAIR-ABCD2345")
		before = self.versions(entry)
		gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway=a)
		self.assertGreater(self.versions(entry), before)


class TestAdminAuthority(_Fixture, IntegrationTestCase):
	def _as(self, huf_role, frappe_roles=("Guest",)):
		if not frappe.db.exists("User", "wp2.tester@example.com"):
			frappe.get_doc(
				{"doctype": "User", "email": "wp2.tester@example.com", "first_name": "WP2", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("wp2.tester@example.com")
		for p in (
			patch.object(gsvc.frappe, "get_roles", return_value=list(frappe_roles)),
			patch("huf.permissions.get_user_huf_role", return_value=huf_role),
			patch("huf.permissions.get_user_capabilities", return_value=[]),
		):
			p.start()
			self.addCleanup(p.stop)

	def test_huf_admin_can_list_approve_and_revoke(self):
		a = self.make_gateway("A")
		e1 = self.make_entry(a, "111", code="PAIR-ABCD2345")
		e2 = self.make_entry(a, "222", state="Approved")
		self._as("Huf Admin")
		self.assertTrue(gsvc._is_gateway_admin())
		self.assertTrue(gsvc.list_gateway_access_entries(gateway=a))
		self.assertEqual(gsvc.approve_gateway_pairing("PAIR-ABCD2345", gateway=a)["name"], e1)
		self.assertEqual(gsvc.revoke_gateway_access_entry(e2)["state"], "Revoked")

	def test_non_admin_cannot_list_or_revoke_even_with_doctype_permission(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, "222", state="Approved")
		self._as("Huf User")
		with patch.object(gsvc.frappe, "has_permission", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				gsvc.list_gateway_access_entries(gateway=a)
			with self.assertRaises(frappe.PermissionError):
				gsvc.revoke_gateway_access_entry(entry)
		self.assertEqual(self.entry_state(entry), "Approved")


class TestMasking(_Fixture, IntegrationTestCase):
	def test_admin_list_shows_the_full_code_to_compare_with_the_sender(self):
		a = self.make_gateway("A")
		self.make_entry(a, "111", code="PAIR-ABCD2345")
		rows = gsvc.list_gateway_access_entries(gateway=a)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["pairing_code"], "PAIR-ABCD2345")

	def test_event_row_keeps_the_code_masked(self):
		a = self.make_gateway("A")
		result = self.ingest(a, "15551239876", "hello")
		error = frappe.db.get_value("Gateway Event", result["event_name"], "error_message")
		code = frappe.db.get_value("Gateway Access Entry", {"gateway": a, "external_id": "15551239876"}, "pairing_code")
		self.assertTrue(code)
		self.assertNotIn(code, error)
		self.assertRegex(error.rsplit(" ", 1)[-1], MASKED)


class TestPairingCaps(_Fixture, IntegrationTestCase):
	def test_reply_flag_defaults_on(self):
		# A new sender must learn their pairing code without the admin finding a hidden switch first.
		field = frappe.get_meta("Gateway").get_field("pairing_reply_enabled")
		self.assertEqual(str(field.default), "1")
		self.assertFalse(bool(getattr(SimpleNamespace(), "pairing_reply_enabled", 0)))

	def test_flag_off_creates_entry_but_sends_nothing(self):
		a = self.make_gateway("A", pairing_reply_enabled=0)
		self.assertTrue(gsvc._create_pairing_request(self.gw(a), "15551230001"))
		self.assertEqual(self.sent_texts(), [])

	def test_code_unsent_while_replies_were_off_is_sent_once_turned_on(self):
		a = self.make_gateway("A", pairing_reply_enabled=0)
		code = gsvc._create_pairing_request(self.gw(a), "15551230001")
		self.assertEqual(self.sent_texts(), [])

		frappe.db.set_value("Gateway", a, "pairing_reply_enabled", 1)
		self.assertEqual(gsvc._create_pairing_request(self.gw(a), "15551230001"), code)
		texts = self.sent_texts()
		self.assertEqual(len(texts), 1)
		self.assertIn(code, texts[0])
		entry = frappe.db.get_value("Gateway Access Entry", {"gateway": a, "external_id": "15551230001"}, "pairing_sent_at")
		self.assertIsNotNone(entry)

		# delivered once: the next message from the same sender does not resend it
		gsvc._create_pairing_request(self.gw(a), "15551230001")
		self.assertEqual(len(self.sent_texts()), 1)

	def test_pending_cap_per_gateway(self):
		a = self.make_gateway("A", pairing_pending_limit=2)
		codes = [gsvc._create_pairing_request(self.gw(a), f"1555123000{i}") for i in range(4)]
		self.assertEqual([bool(c) for c in codes], [True, True, False, False])
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a, "state": "Pending"}), 2)
		self.assertEqual(len(self.sent_texts()), 2)

	def test_cap_reason_is_reported_without_a_code(self):
		a = self.make_gateway("A", pairing_pending_limit=1)
		gw = self.gw(a)
		gsvc._admission(gw, {"sender_id": "15551230001", "conversation_id": "15551230001"})
		admitted, reason = gsvc._admission(gw, {"sender_id": "15551230002", "conversation_id": "15551230002"})
		self.assertFalse(admitted)
		self.assertIn("capacity", reason.lower())
		self.assertNotIn("PAIR-", reason)

	def test_per_sender_cap_over_24h(self):
		a = self.make_gateway("A")
		gw = self.gw(a)
		for _i in range(gsvc.PAIRING_MAX_REQUESTS_PER_SENDER_PER_DAY):
			self.assertTrue(gsvc._create_pairing_request(gw, "15551230001"))
			name = frappe.db.get_value("Gateway Access Entry", {"gateway": a, "state": "Pending"}, "name")
			frappe.db.set_value("Gateway Access Entry", name, {"state": "Expired", "pairing_sent_at": None})
		self.assertEqual(gsvc._create_pairing_request(gw, "15551230001"), "")
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a, "state": "Pending"}), 0)

	def test_daily_reply_cap_keeps_entries_but_stops_sending(self):
		a = self.make_gateway("A", pairing_reply_daily_limit=2)
		for i in range(4):
			self.assertTrue(gsvc._create_pairing_request(self.gw(a), f"1555123000{i}"))
		self.assertEqual(len(self.sent_texts()), 2)
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a, "state": "Pending"}), 4)


class TestEntryHelpers(_Fixture, IntegrationTestCase):
	def test_access_rate_gate(self):
		a = self.make_gateway("A", policy="Allow list", inbound_sender_limit=2)
		gw = self.gw(a)
		ctx = {"sender_id": "15551230001"}
		self.assertEqual(gsvc.access_rate_gate(gw, ctx), "")
		self.assertEqual(gsvc.access_rate_gate(gw, ctx), "")
		self.assertTrue(gsvc.access_rate_gate(gw, ctx).startswith("sender_rate_limited"))

	def test_stranger_stop_creates_no_row_and_no_reply(self):
		a = self.make_gateway("A")  # Pairing
		event = frappe.get_doc(
			{"doctype": "Gateway Event", "gateway": a, "idempotency_key": "k" + self.suffix,
			 "provider_event_id": "p", "status": "Received", "received_at": now_datetime()}
		).insert(ignore_permissions=True)
		ctx = {"sender_id": "15551239999", "conversation_id": "15551239999", "message_text": "STOP"}
		result = gsvc.record_consent_event(event, self.gw(a), ctx)
		self.assertEqual(result["status"], "Rejected")
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": a}), 0)
		self.assertFalse(gsvc.is_opted_out(a, "15551239999"))
		self.assertEqual(self.sent_texts(), [])

	def test_admitted_sender_stop_is_recorded(self):
		a = self.make_gateway("A", policy="Allow list")
		self.make_entry(a, "15551230001", state="Approved")
		result = self.ingest(a, "15551230001", "STOP")
		self.assertEqual(result["status"], "Rejected")
		self.assertTrue(gsvc.is_opted_out(a, "15551230001"))
