# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""telegram_management_groups: permission, expiry, decision payloads, audit (no site, no network)."""

from __future__ import annotations

import datetime
import unittest
from unittest import mock

import frappe

from huf.ai import telegram_management_groups as g
from huf.ai.gateway_adapters import telegram_admin_actions as admin
from huf.ai.gateway_adapters.telegram_client import TelegramApiError

if not hasattr(frappe.local, "flags"):
	frappe.local.flags = frappe._dict()
if not hasattr(frappe.local, "session"):
	frappe.local.session = frappe._dict(user="tester@example.com")

GW = {"name": "TG-1", "provider": "Telegram"}


def _entry(state="Pending", expires="2999-01-01 00:00:00"):
	return frappe._dict(
		name="GAE-1",
		gateway="TG-1",
		entry_type="Room",
		state=state,
		external_id="join:-100:42",
		display_label="Join request: @ada -> Club",
		expires_at=expires,
		creation="2026-01-01 10:00:00",
	)


class FakeClient:
	def __init__(self, fail=None):
		self.calls, self.fail = [], fail

	def call(self, method, payload):
		self.calls.append((method, payload))
		if self.fail:
			raise self.fail
		return True


class TestJoin(unittest.TestCase):
	def setUp(self):
		self.client = FakeClient()
		self.audit, self.gs = mock.MagicMock(), mock.MagicMock()
		for p in (
			mock.patch.object(g, "_require_admin", return_value=dict(GW)),
			mock.patch.object(g, "_credentials", return_value={"token": "T"}),
			mock.patch.object(g, "_client", side_effect=lambda c: self.client),
			mock.patch.object(g, "_audit", self.audit),
			mock.patch("frappe.utils.now_datetime", return_value=datetime.datetime(2026, 6, 1)),
			mock.patch("huf.ai.gateway_service.approve_gateway_pairing", self.gs.approve),
			mock.patch("huf.ai.gateway_service.revoke_gateway_access_entry", self.gs.revoke),
		):
			p.start()
			self.addCleanup(p.stop)

	def _decide(self, entry, decision):
		db = mock.MagicMock()
		db.get_value.return_value = entry
		with mock.patch.object(frappe, "db", db):
			return g.decide_join_request("TG-1", "GAE-1", decision)

	def test_parse(self):
		item = g.parse_join_entry(dict(_entry()))
		self.assertEqual(
			(item["chat_id"], item["user_id"], item["chat_title"], item["user_name"]),
			("-100", "42", "Club", "@ada"),
		)
		self.assertIsNone(g.parse_join_entry({"name": "x", "external_id": "-100"}))

	def test_permission_denied(self):
		with mock.patch.object(g, "_require_admin", side_effect=frappe.PermissionError):
			for fn in (
				g.list_join_requests,
				g.decide_join_request,
				g.list_groups,
				g.get_group_settings,
				g.leave_group,
			):
				with self.assertRaises(frappe.PermissionError):
					fn("TG-1")

	def test_approve_payload_and_audit(self):
		res = self._decide(_entry(), "approve")
		self.assertTrue(res["success"])
		self.assertEqual(self.client.calls, [("approveChatJoinRequest", {"chat_id": -100, "user_id": 42})])
		self.gs.approve.assert_called_once()
		self.assertEqual(self.audit.call_args.args[:5], ("TG-1", "join:approve", "-100", "42", "ok"))

	def test_decline_payload(self):
		self.assertTrue(self._decide(_entry(), "decline")["success"])
		self.assertEqual(self.client.calls[0][0], "declineChatJoinRequest")
		self.gs.revoke.assert_called_once()

	def test_expired_refused_without_api_call(self):
		res = self._decide(_entry(expires="2000-01-01 00:00:00"), "approve")
		self.assertEqual(res["error"], "expired")
		self.assertEqual(self.client.calls, [])
		self.assertEqual(self.audit.call_args.args[4], "refused")

	def test_missing_rights_is_clear_and_audited(self):
		self.client.fail = TelegramApiError(
			"approveChatJoinRequest", "Bad Request: not enough rights", error_code=400
		)
		res = self._decide(_entry(), "approve")
		self.assertEqual(res["error"], "not_enough_rights")
		self.assertIn("missing the right", res["message"])
		self.gs.approve.assert_not_called()
		self.assertEqual(self.audit.call_args.args[4], "failed")

	def test_already_handled_and_bad_decision(self):
		self.assertEqual(self._decide(_entry(state="Revoked"), "approve")["error"], "already_handled")
		self.assertEqual(self._decide(_entry(), "queue")["error"], "bad_decision")

	def test_leave_requires_confirm(self):
		self.assertEqual(g.leave_group("TG-1", "-100")["error"], "confirm_required")
		self.assertEqual(self.client.calls, [])
		self.assertTrue(g.leave_group("TG-1", "-100", 1)["success"])
		self.assertEqual(self.client.calls, [("leaveChat", {"chat_id": -100})])
		self.assertEqual(self.audit.call_args.args[1], "leave_group")


if __name__ == "__main__":
	unittest.main()
