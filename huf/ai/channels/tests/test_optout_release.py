"""SLICE-optout-invalidate-release: opt-out drops cached consent allows; human release API is permission-checked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import channel_consent, guard, guard_steps, handoff_hooks
from huf.ai.flow.runs import member


class TestOptOutInvalidatesConsent(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_record_opt_out_invalidates(self):
		with patch.object(guard, "invalidate_consent") as inv:
			self.assertTrue(channel_consent.record_opt_out("sms", "+15550001111"))
		inv.assert_called_once_with("+15550001111")

	def test_unusable_recipient_skips_invalidate(self):
		with patch.object(guard, "invalidate_consent") as inv:
			self.assertFalse(channel_consent.record_opt_out("sms", ""))
		inv.assert_not_called()

	def test_exit_on_opt_out_invalidates(self):
		with patch.object(guard, "invalidate_consent") as inv:
			member.exit_on_opt_out(gateway="gw", sender_id="+15550002222", kind="opt_out")
		inv.assert_called_once_with("+15550002222")

	def test_opt_in_does_not_invalidate(self):
		with patch.object(guard, "invalidate_consent") as inv:
			member.exit_on_opt_out(gateway="gw", sender_id="+15550002222", kind="opt_in")
		inv.assert_not_called()

	def test_cached_allow_dropped_in_batch(self):
		with guard_steps.batch():
			cache = guard_steps._BATCH.get()
			cache[("consent", "sms", "gw", True, "15550003333")] = {"allow": True}
			channel_consent.record_opt_out("sms", "+1 555 000 3333")
			self.assertNotIn(("consent", "sms", "gw", True, "15550003333"), cache)


class TestReleaseConversation(IntegrationTestCase):
	def test_permission_denied_does_not_release(self):
		doc = MagicMock(name="conv")
		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch("frappe.get_doc", return_value=doc),
			patch("huf.ai.flow.nodes.handoff.release_handoff") as rel,
		):
			self.assertRaises(frappe.PermissionError, handoff_hooks.release_conversation, "CONV-1")
		doc.check_permission.assert_called_once_with("write")
		rel.assert_not_called()

	def test_permitted_release_calls_release_handoff(self):
		doc = MagicMock()
		doc.name = "CONV-1"
		with (
			patch("frappe.get_doc", return_value=doc),
			patch("huf.ai.flow.nodes.handoff.release_handoff", return_value=["RUN-1"]) as rel,
		):
			self.assertEqual(handoff_hooks.release_conversation("CONV-1"), ["RUN-1"])
		rel.assert_called_once_with("CONV-1")

	def test_is_whitelisted_post_only(self):
		fn = handoff_hooks.release_conversation
		self.assertIn(fn, frappe.whitelisted)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"])
