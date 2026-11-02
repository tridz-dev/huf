"""BE-MULTICH: Telegram/Slack/Teams conversation tracking, window_applies, reply bypass, status API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from huf.ai import gateway_service
from huf.ai.channels import conversation as conv, reply_api, status_api

USER = "multich-plain@example.com"


class TestMultichannel(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.gw = frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": "MC " + frappe.generate_hash(length=6), "provider": "Telegram",
			 "is_enabled": 0, "direct_policy": "Pairing"}
		).insert(ignore_permissions=True)

	def test_window_applies(self):
		self.assertTrue(conv.window_applies("whatsapp"))
		for ch in ("telegram", "slack", "teams"):
			self.assertFalse(conv.window_applies(ch))
		self.assertTrue(conv.is_within_24h({"channel": "telegram", "last_inbound_at": None}))
		self.assertFalse(conv.is_within_24h({"channel": "whatsapp", "last_inbound_at": None}))

	def test_telegram_inbound_creates_conversation(self):
		event = MagicMock()
		gateway_service._track_conversation_inbound(self.gw, event, {"sender_id": "777", "sender_name": "Tg Ann", "message_text": "hi"})
		row = frappe.db.get_value("Channel Conversation", {"gateway": self.gw.name, "contact_handle": "777"}, ["channel", "contact_name", "message_count"], as_dict=True)
		self.assertEqual((row.channel, row.contact_name, row.message_count), ("telegram", "Tg Ann", 1))
		event.db_set.assert_called()

	def test_send_reply_telegram_bypasses_window_and_templates(self):
		c = conv.get_or_create_conversation(self.gw.name, "777")
		self.assertEqual(c.channel, "telegram")
		adapter = MagicMock()
		adapter.send_reply.return_value = SimpleNamespace(provider_message_id="m1")
		with patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter):
			res = reply_api.send_reply(c.name, text="hello")
			self.assertEqual((res["status"], res["message_id"]), ("sent", "m1"))
			adapter.send_reply.assert_called_once()
			self.assertEqual(reply_api.send_reply(c.name, template="t")["error"], "templates_unsupported")

	def test_list_channel_gateways(self):
		rows = {r["name"]: r for r in status_api.list_channel_gateways()}
		r = rows[self.gw.name]
		self.assertEqual(set(r), {"name", "provider", "channel", "enabled", "health", "setup_stage"})
		self.assertEqual((r["channel"], r["health"]), ("telegram", "off"))
		self.gw.db_set("is_enabled", 1)
		self.assertEqual({x["name"]: x for x in status_api.list_channel_gateways()}[self.gw.name]["health"], "connected_unverified")
		ev = frappe.get_doc({"doctype": "Gateway Event", "gateway": self.gw.name, "idempotency_key": "mc-" + frappe.generate_hash(length=6),
			"provider_event_id": "e1", "status": "Succeeded"})
		ev.flags.ignore_links = True
		ev.insert(ignore_permissions=True)
		self.assertEqual({x["name"]: x for x in status_api.list_channel_gateways()}[self.gw.name]["health"], "live")

	def test_list_channel_gateways_permission(self):
		if not frappe.db.exists("User", USER):
			frappe.get_doc({"doctype": "User", "email": USER, "first_name": "Plain", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			status_api.list_channel_gateways()
