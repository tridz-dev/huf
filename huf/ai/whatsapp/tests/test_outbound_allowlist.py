# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""BE-ALLOWLIST: site-config ``wa_outbound_allowlist`` guard on the outbound policy choke point.

Absent key = unchanged behaviour. Present key = only listed numbers (digits-normalised) may receive any
outbound WhatsApp send. Covers the policy choke point, the bridge template gate, the broadcast runner and the
agent tool send paths that bypass the bridge.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.whatsapp.broadcast import recipients as brecipients
from huf.ai.whatsapp.broadcast import send as bs
from huf.ai.tools import whatsapp as wtools
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_send import _Store

OWNER = "919876543210"
OTHER = "15550009999"
KEY = "wa_outbound_allowlist"


class _ConfBase(unittest.TestCase):
	def setUp(self):
		self._conf_patch = patch.dict(frappe.conf)
		self._conf_patch.start()
		self.addCleanup(self._conf_patch.stop)
		frappe.conf.pop(KEY, None)

	def allow(self, value):
		frappe.conf[KEY] = value


class TestAbsentKey(_ConfBase):
	def test_absent_key_leaves_every_recipient_allowed(self):
		self.assertIsNone(policy.allowlist_numbers())
		for number in (OWNER, OTHER, "+1 555 000 1234"):
			policy.check_allowlist(number)  # no raise
			policy.check_recipient(None, number)

	def test_null_value_is_treated_as_absent(self):
		self.allow(None)
		policy.check_recipient(None, OTHER)

	def test_absent_key_does_not_change_bsuid_refusal(self):
		with self.assertRaises(policy.OutboundRefused) as cm:
			policy.check_recipient(None, "IN.4608123")
		self.assertEqual(cm.exception.code, "bsuid_recipient")


class TestListedAndUnlisted(_ConfBase):
	def test_listed_number_allowed_as_list(self):
		self.allow([OWNER])
		policy.check_recipient(None, OWNER)
		policy.check_allowlist(OWNER)

	def test_listed_number_allowed_as_comma_string(self):
		self.allow(f"{OWNER}, {OTHER}")
		policy.check_recipient(None, OTHER)
		policy.check_recipient(None, OWNER)

	def test_unlisted_number_blocked_with_policy_code(self):
		self.allow([OWNER])
		with self.assertRaises(policy.OutboundRefused) as cm:
			policy.check_recipient(None, OTHER)
		self.assertEqual(cm.exception.code, "recipient_not_allowlisted")
		self.assertIsInstance(cm.exception, frappe.ValidationError)  # same deny shape as the other refusals

	def test_empty_present_key_fails_closed(self):
		self.allow("")
		with self.assertRaises(policy.OutboundRefused) as cm:
			policy.check_recipient(None, OWNER)
		self.assertEqual(cm.exception.code, "recipient_not_allowlisted")

	def test_blocked_even_without_gateway(self):
		self.allow([OWNER])
		with self.assertRaises(policy.OutboundRefused):
			policy.enforce_template("ACC", OTHER, None, None)

	def test_bridge_template_gate_blocks_unlisted_before_any_gateway_lookup(self):
		self.allow([OWNER])
		with patch.object(policy, "gateways_for_account", return_value=["GW"]), patch.object(
			policy, "check_template"
		) as tpl:
			with self.assertRaises(policy.OutboundRefused) as cm:
				policy.enforce_template("ACC", OTHER, {"status": "APPROVED"}, "GW")
		self.assertEqual(cm.exception.code, "recipient_not_allowlisted")
		tpl.assert_not_called()


class TestFormattingNormalisation(_ConfBase):
	def test_plus_and_spaces_in_config_match_plain_digits(self):
		self.allow(["+91 98765 43210"])
		policy.check_recipient(None, "919876543210")
		policy.check_recipient(None, "+91 98765-43210")
		policy.check_recipient(None, "+91 (98765) 43210")

	def test_plus_and_spaces_in_recipient_match_plain_config(self):
		self.allow("919876543210")
		policy.check_recipient(None, "+91 98765 43210")

	def test_different_number_with_same_suffix_is_still_blocked(self):
		self.allow(["+91 98765 43210"])
		with self.assertRaises(policy.OutboundRefused):
			policy.check_recipient(None, "+91 98765 43211")

	def test_country_prefix_matters(self):
		self.allow(["+91 98765 43210"])
		with self.assertRaises(policy.OutboundRefused):
			policy.check_recipient(None, "9876543210")


class TestBroadcastPath(_ConfBase):
	"""The broadcast runner re-checks the recipient at send time through the choke point; no POST on refusal."""

	def setUp(self):
		super().setUp()
		self.store = _Store(recipient=OTHER)
		s = self.store
		patch.object(bs, "_claim", side_effect=s.claim).start()
		patch.object(bs, "_release", side_effect=s.release).start()
		patch.object(bs, "_write", side_effect=s.write).start()
		patch.object(bs, "_load", side_effect=lambda n: dict(s.row)).start()
		patch.object(bs, "_template_row", side_effect=lambda n: {"status": "APPROVED", "category": "UTILITY"}).start()
		patch.object(bs, "_load_broadcast", side_effect=lambda n: dict(s.bc)).start()
		patch.object(bs, "_started_count", return_value=1).start()
		patch.object(bs.frappe.db, "rollback", create=True).start()
		patch.object(bs.frappe.db, "commit", create=True).start()
		self.post = patch.object(
			bridge, "send_template", return_value={"wamid": "wamid.1", "message_status": "accepted"}
		).start()
		self.addCleanup(patch.stopall)
		bs.frappe.flags.broadcast_pause = None

	def test_unlisted_broadcast_recipient_is_skipped_and_never_posted(self):
		self.allow([OWNER])
		with patch.object(policy, "check_template"):
			self.assertEqual(bs.send_one(self.store.row["name"]), "skipped")
		self.assertEqual((self.store.row["status"], self.store.row["skip_reason"]), ("skipped", "recipient_not_allowlisted"))
		self.post.assert_not_called()

	def test_broadcast_queue_time_policy_flags_unlisted_recipient(self):
		self.allow([OWNER])
		self.assertEqual(brecipients._policy_reason("GW", OTHER, False), "recipient_not_allowlisted")

	def test_broadcast_queue_time_absent_key_unchanged(self):
		frappe.conf.pop(KEY, None)
		self.assertIsNone(brecipients._policy_reason(None, OTHER, False))


class TestAgentToolPaths(_ConfBase):
	"""Agent tool sends that go straight to the bridge or Graph are gated by the same allow-list."""

	def test_free_form_text_blocked_before_any_send(self):
		self.allow([OWNER])
		with patch.object(wtools.bridge, "send_text") as send, patch.object(wtools.requests, "post") as post:
			out = json.loads(wtools._send_message({"to": OTHER, "message": "hi", "gateway_name": "GW"}))
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "recipient_not_allowlisted")
		send.assert_not_called()
		post.assert_not_called()

	def test_template_blocked_before_any_send(self):
		self.allow([OWNER])
		with patch.object(wtools.bridge, "send_template") as send, patch.object(wtools.requests, "post") as post:
			out = json.loads(wtools._send_template({"to": "+1 555 000 9999", "template_name": "t", "gateway_name": "GW"}))
		self.assertEqual(out["error"], "recipient_not_allowlisted")
		send.assert_not_called()
		post.assert_not_called()

	def test_absent_key_text_send_reaches_transport(self):
		with patch.object(wtools, "_resolve_bridge_account", return_value={"name": "ACC"}), patch.object(
			wtools, "_free_form_refusal", return_value=None
		), patch.object(wtools.bridge, "send_text", return_value={"message_id": "m1", "name": "n"}) as send:
			out = json.loads(wtools._send_message({"to": OTHER, "message": "hi", "gateway_name": "GW"}))
		self.assertTrue(out["success"])
		send.assert_called_once()


if __name__ == "__main__":
	unittest.main()
