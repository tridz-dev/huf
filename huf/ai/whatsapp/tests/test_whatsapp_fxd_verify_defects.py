# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FX-D: Disconnected gateway refuses every send path (DEF-2); run-bound sends need no Gateway write (DEF-1)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp import account_events as ae
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.tools import whatsapp

ACCT = {"name": "WA-1", "phone_id": "PID-1", "url": "https://graph.example", "version": "v21.0", "token": "t"}
SEND_ACTIONS = sorted(a for a in whatsapp._SEND_ACTIONS if a != "create_template")


def _disconnected():
	return patch.object(ae, "_state_for_phone_id", return_value=(ae.DISCONNECTED, "partner removed"))


class TestDisconnectedToolRefusal(unittest.TestCase):
	def tearDown(self):
		patch.stopall()

	def _call(self, action):
		with (
			patch.object(whatsapp, "_run_gateway", return_value="GW"),
			patch.object(whatsapp, "_authorize", return_value=None),
			patch.object(whatsapp, "_gateway_phone_id", return_value="PID-1"),
			_disconnected(),
			patch.object(whatsapp, "_scope_refusal", return_value=None),
			patch.object(whatsapp.requests, "post") as post,
			patch.object(bridge, "send_text") as send_text,
			patch.object(bridge, "send_template") as send_template,
			patch.object(whatsapp, "_dispatch") as dispatch,
		):
			raw = whatsapp.handle_action(action, to="15551234567", message="x", template_name="t")
		post.assert_not_called()
		send_text.assert_not_called()
		send_template.assert_not_called()
		dispatch.assert_not_called()
		return json.loads(raw)

	def test_every_send_action_returns_the_normal_refusal(self):
		for action in SEND_ACTIONS:
			result = self._call(action)
			self.assertFalse(result["success"], action)
			self.assertEqual(result["error"], "gateway_disconnected", action)

	def test_connected_gateway_is_not_refused(self):
		with (
			patch.object(whatsapp, "_run_gateway", return_value="GW"),
			patch.object(whatsapp, "_authorize", return_value=None),
			patch.object(whatsapp, "_gateway_phone_id", return_value="PID-1"),
			patch.object(ae, "_state_for_phone_id", return_value=(ae.CONNECTED, "")),
			patch.object(whatsapp, "_scope_refusal", return_value=None),
			patch.object(whatsapp, "_idempotent_send", return_value='{"success": true}') as sent,
			patch.object(whatsapp, "_mark_outreach"),
		):
			whatsapp.handle_action("send_message", to="1", message="x")
		sent.assert_called_once()


class TestDisconnectedBridgeRefusal(unittest.TestCase):
	def tearDown(self):
		patch.stopall()

	def test_send_text_refused_before_any_message_row(self):
		with patch.object(bridge, "_account_or_error", return_value=ACCT), _disconnected(), patch.object(
			bridge.frappe, "get_doc"
		) as get_doc:
			with self.assertRaises(bridge.BridgeError) as ctx:
				bridge.send_text("WA-1", "15551234567", "hi")
		self.assertEqual(ctx.exception.payload["error"], "gateway_disconnected")
		get_doc.assert_not_called()

	def test_send_template_refused_before_policy_and_rows(self):
		with patch.object(bridge, "_account_or_error", return_value=ACCT), _disconnected(), patch.object(
			bridge.frappe, "get_doc"
		) as get_doc, patch.object(bridge.policy, "enforce_template") as enforce:
			with self.assertRaises(bridge.BridgeError) as ctx:
				bridge.send_template("WA-1", "15551234567", "tpl", gateway_name="GW")
		self.assertEqual(ctx.exception.payload["error"], "gateway_disconnected")
		get_doc.assert_not_called()
		enforce.assert_not_called()

	def test_send_text_not_refused_when_connected(self):
		doc = MagicMock(name="doc")
		doc.name, doc.get.return_value = "WM-1", "wamid.1"
		with patch.object(bridge, "_account_or_error", return_value=ACCT), patch.object(
			ae, "_state_for_phone_id", return_value=(ae.CONNECTED, "")
		), patch.object(bridge.frappe, "get_doc", return_value=doc):
			self.assertTrue(bridge.send_text("WA-1", "15551234567", "hi")["success"])


class TestRunBoundSendAuthority(unittest.TestCase):
	"""DEF-1: inside a run bound to gateway G, sending is authorised for G without Gateway write."""

	def tearDown(self):
		patch.stopall()

	def _denying_mgmt(self):
		return (
			patch("huf.ai.whatsapp.management._send_authority", side_effect=frappe.PermissionError("no")),
			patch("huf.ai.whatsapp.management._gateway_write_allowed", return_value=False),
		)

	def test_send_actions_do_not_need_gateway_write(self):
		p1, p2 = self._denying_mgmt()
		with p1, p2:
			for action in SEND_ACTIONS:
				self.assertIsNone(whatsapp._authorize(action, "GW"), action)

	def test_template_management_still_needs_real_write_authority(self):
		p1, p2 = self._denying_mgmt()
		with p1, p2:
			result = json.loads(whatsapp._authorize("create_template", "GW"))
		self.assertEqual(result["error"], "permission_denied")

	def test_trusted_draft_bypass_still_rechecks_authority(self):
		p1, p2 = self._denying_mgmt()
		with p1, p2, patch.object(bridge, "create_draft") as draft:
			result = json.loads(whatsapp._create_template_draft({"name": "WA"}, {}, "GW"))
		self.assertEqual(result["error"], "permission_denied")
		draft.assert_not_called()

	def test_forged_gateway_still_refused_without_a_bound_run(self):
		with patch.object(whatsapp, "_run_gateway", return_value=""):
			result = json.loads(whatsapp.handle_action("send_message", to="1", message="x", gateway_name="GW-OTHER"))
		self.assertEqual(result["error"], "gateway_context_required")

	def test_bridge_sends_skip_whatsapp_message_permission_inside_the_run_scope(self):
		with (
			patch.object(bridge, "_account_or_error", return_value=ACCT),
			patch.object(bridge.frappe, "has_permission", return_value=False),
			patch.object(bridge, "_post_typed_message", return_value="wamid.1"),
			patch.object(bridge, "_mirror_direct_send", return_value={"success": True}) as mirror,
		):
			with self.assertRaises(frappe.PermissionError):
				bridge._send_payload("WA-1", {"type": "text"})
			with bridge.run_bound_send():
				self.assertTrue(bridge._send_payload("WA-1", {"type": "text"})["success"])
			with self.assertRaises(frappe.PermissionError):  # scope ended
				bridge._send_payload("WA-1", {"type": "text"})
		mirror.assert_called_once()


class TestUserPreferencesWaba(unittest.TestCase):
	def _apply(self, entry_waba, own_waba):
		with patch.object(ae, "_gateway_identity", return_value={"phone_number_id": "PID-1", "waba_id": own_waba}), patch.object(
			ae, "record_user_preferences"
		) as record:
			out = ae.apply_account_event(
				{"field": "user_preferences", "waba_id": entry_waba, "phone_id": "PID-1", "user_preferences": [{"wa_id": "1"}]},
				"GW",
			)
		return out, record

	def test_foreign_waba_is_ignored(self):
		out, record = self._apply("W-OTHER", "W-OWN")
		self.assertEqual(out, [])
		record.assert_not_called()

	def test_own_waba_is_applied(self):
		out, record = self._apply("W-OWN", "W-OWN")
		self.assertEqual(out, ["GW"])
		record.assert_called_once()

	def test_unknown_own_waba_falls_back_to_phone_id_only(self):
		out, record = self._apply("W-ANY", "")
		self.assertEqual(out, ["GW"])
		record.assert_called_once()


if __name__ == "__main__":
	unittest.main()
