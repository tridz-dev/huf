"""Remove access, decline, block, unblock, restore and add-by-hand for gateway senders."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service as gsvc
from huf.ai.gateway_adapters.tests.test_gateway_pairing_hardening import _GatewayFixture

SENDER = "15551230001"


class _Fixture(_GatewayFixture):
	def make_gateway(self, label, **kw):
		kw.setdefault("pairing_reply_enabled", 1)
		return super().make_gateway(label, **kw)

	def pending(self, gateway, sender=SENDER):
		return frappe.get_all(
			"Gateway Access Entry",
			{"gateway": gateway, "external_id": sender, "state": "Pending"},
			pluck="name",
		)

	def age_revoke(self, entry, hours):
		"""Pretend the revoke (and any code sent before it) happened ``hours`` ago."""
		then = add_to_date(now_datetime(), hours=-hours)
		values = {"revoked_at": then}
		if frappe.db.get_value("Gateway Access Entry", entry, "pairing_sent_at"):
			values["pairing_sent_at"] = then
		frappe.db.set_value("Gateway Access Entry", entry, values)


class TestRemoveAndDecline(_Fixture, IntegrationTestCase):
	def test_removed_sender_can_ask_again_after_the_cooldown(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		gsvc.revoke_gateway_access_entry(entry)

		# straight away: still kept out, and no new request
		result = self.ingest(a, SENDER, "hello")
		self.assertEqual(self.event_error(result).status, "Rejected")
		self.assertIn("ask again later", self.event_error(result).error_message)
		self.assertEqual(self.pending(a), [])

		self.age_revoke(entry, gsvc.ACCESS_REREQUEST_COOLDOWN_HOURS + 1)
		self.ingest(a, SENDER, "hello again")
		requests = self.pending(a)
		self.assertEqual(len(requests), 1)
		code = frappe.db.get_value("Gateway Access Entry", requests[0], "pairing_code")
		self.assertTrue(any(code in text for text in self.sent_texts()))

		gsvc.approve_gateway_pairing(requests[0])
		self.assertEqual(self.ingest(a, SENDER, "back")["status"], "Queued")

	def test_declined_request_is_held_off_then_can_ask_again(self):
		a = self.make_gateway("A")
		self.ingest(a, SENDER, "hi")
		[request] = self.pending(a)
		gsvc.revoke_gateway_access_entry(request)  # Decline in the UI

		self.ingest(a, SENDER, "please")
		self.assertEqual(self.pending(a), [])
		self.age_revoke(request, gsvc.ACCESS_REREQUEST_COOLDOWN_HOURS + 1)
		self.ingest(a, SENDER, "please?")
		self.assertEqual(len(self.pending(a)), 1)

	def test_removed_sender_can_still_opt_out(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		gsvc.revoke_gateway_access_entry(entry)
		self.ingest(a, SENDER, "STOP")
		self.assertTrue(gsvc.is_opted_out(a, SENDER))


class TestBlock(_Fixture, IntegrationTestCase):
	def test_blocked_sender_never_gets_a_code_or_a_reply(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		gsvc.block_gateway_access_entry(entry)
		self.age_revoke(entry, 24 * 30)

		result = self.ingest(a, SENDER, "hello")
		self.assertEqual(self.event_error(result).status, "Rejected")
		self.assertIn("Blocked", self.event_error(result).error_message)
		self.assertEqual(self.pending(a), [])
		self.assertEqual(self.sent_texts(), [])

	def test_unblock_lets_them_ask_again_straight_away(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		gsvc.block_gateway_access_entry(entry)
		gsvc.unblock_gateway_access_entry(entry)

		self.assertEqual(self.entry_state(entry), "Revoked")
		self.ingest(a, SENDER, "hello")
		self.assertEqual(len(self.pending(a)), 1)

	def test_block_never_overrides_an_opt_out(self):
		a = self.make_gateway("A", policy="Allow list")
		entry = self.make_entry(a, SENDER, state="Approved")
		self.ingest(a, SENDER, "STOP")
		gsvc.block_gateway_access_entry(entry)
		self.assertEqual(self.entry_state(entry), "Opted out")
		self.ingest(a, SENDER, "START")
		self.assertEqual(self.entry_state(entry), "Blocked")

	def test_only_blocked_entries_can_be_unblocked(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		with self.assertRaises(frappe.ValidationError):
			gsvc.unblock_gateway_access_entry(entry)


class TestRestore(_Fixture, IntegrationTestCase):
	def test_restore_approves_and_welcomes_without_a_new_request(self):
		a = self.make_gateway("A")
		entry = self.make_entry(a, SENDER, state="Approved")
		gsvc.revoke_gateway_access_entry(entry)

		result = gsvc.restore_gateway_access_entry(entry)
		self.assertEqual(result["state"], "Approved")
		self.assertEqual(self.entry_state(entry), "Approved")
		self.assertTrue(any("approved" in text for text in self.sent_texts()))
		self.assertEqual(self.ingest(a, SENDER, "hi")["status"], "Queued")

	def test_blocked_or_opted_out_cannot_be_restored(self):
		a = self.make_gateway("A")
		blocked = self.make_entry(a, SENDER, state="Blocked")
		opted_out = self.make_entry(a, "15551230002", state="Opted out")
		for entry in (blocked, opted_out):
			with self.assertRaises(frappe.ValidationError):
				gsvc.restore_gateway_access_entry(entry)


class TestAddByHand(_Fixture, IntegrationTestCase):
	def test_added_number_gets_in_under_allow_list(self):
		a = self.make_gateway("A", policy="Allow list")
		self.assertNotEqual(self.ingest(a, SENDER, "hi")["status"], "Queued")
		result = gsvc.add_gateway_access_entry(a, "+1 (555) 123-0001", "Riya")
		self.assertEqual(result["external_id"], SENDER)  # normalised like inbound ids
		self.assertEqual(frappe.db.get_value("Gateway Access Entry", result["name"], "display_label"), "Riya")
		self.assertEqual(self.ingest(a, SENDER, "hi again")["status"], "Queued")
		self.assertEqual(self.sent_texts(), [])  # adding sends nothing

	def test_add_approves_a_waiting_request_in_place(self):
		a = self.make_gateway("A")
		self.ingest(a, SENDER, "hi")
		[request] = self.pending(a)
		self.assertEqual(gsvc.add_gateway_access_entry(a, SENDER)["name"], request)
		self.assertEqual(self.entry_state(request), "Approved")

	def test_add_refuses_duplicates_blocks_and_opt_outs(self):
		a = self.make_gateway("A")
		self.make_entry(a, SENDER, state="Approved")
		self.make_entry(a, "15551230002", state="Blocked")
		self.make_entry(a, "15551230003", state="Opted out")
		for number, words in ((SENDER, "already"), ("15551230002", "blocked"), ("15551230003", "opted out")):
			with self.assertRaises(frappe.ValidationError) as ctx:
				gsvc.add_gateway_access_entry(a, number)
			self.assertIn(words, str(ctx.exception))

	def test_admin_only(self):
		a = self.make_gateway("A")
		with patch.object(gsvc, "_is_gateway_admin", return_value=False):
			for call in (
				lambda: gsvc.add_gateway_access_entry(a, SENDER),
				lambda: gsvc.block_gateway_access_entry("x"),
				lambda: gsvc.unblock_gateway_access_entry("x"),
				lambda: gsvc.restore_gateway_access_entry("x"),
			):
				with self.assertRaises(frappe.PermissionError):
					call()
