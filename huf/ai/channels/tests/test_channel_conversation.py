"""Channel Conversation: upsert on inbound/outbound, 24h helper, read APIs."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service
from huf.ai.channels import api, conversation as conv

USER = "chan-conv-plain@example.com"


class TestChannelConversation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		sfx = frappe.generate_hash(length=6)
		phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": phone},
					{"key": "access_token", "value": "tok"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": "sec"},
				],
			}
		).insert(ignore_permissions=True)
		self.gw = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Conv {sfx}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": settings.name,
				"execution_user": "Administrator",
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)

	def test_create_then_reuse(self):
		a = conv.get_or_create_conversation(self.gw.name, "15550001111", contact_name="Ann")
		b = conv.get_or_create_conversation(self.gw.name, "15550001111")
		self.assertEqual(a.name, b.name)
		self.assertEqual((a.channel, a.status), ("whatsapp", "ai"))
		other = conv.get_or_create_conversation(self.gw.name, "15550002222")
		self.assertNotEqual(a.name, other.name)

	def test_closed_allows_new_open_row(self):
		a = conv.get_or_create_conversation(self.gw.name, "15550001111")
		a.db_set("status", "closed")
		b = conv.get_or_create_conversation(self.gw.name, "15550001111")
		self.assertNotEqual(a.name, b.name)

	def test_duplicate_open_rejected(self):
		conv.get_or_create_conversation(self.gw.name, "15550001111")
		dup = frappe.get_doc({"doctype": "Channel Conversation", "gateway": self.gw.name, "contact_handle": "15550001111"})
		with self.assertRaises(frappe.UniqueValidationError):
			dup.insert(ignore_permissions=True)

	def test_touch_timestamps(self):
		c = conv.get_or_create_conversation(self.gw.name, "15550001111")
		conv.touch_inbound(c, preview="hi there")
		conv.touch_outbound(c.name)
		row = frappe.db.get_value("Channel Conversation", c.name, ["last_inbound_at", "last_outbound_at", "message_count", "last_message_preview"], as_dict=True)
		self.assertTrue(row.last_inbound_at and row.last_outbound_at)
		self.assertEqual(row.message_count, 2)
		self.assertEqual(row.last_message_preview, "hi there")

	def test_is_within_24h(self):
		now = now_datetime()
		self.assertFalse(conv.is_within_24h({"last_inbound_at": None}))
		self.assertTrue(conv.is_within_24h({"last_inbound_at": add_to_date(now, hours=-23)}, now=now))
		self.assertFalse(conv.is_within_24h({"last_inbound_at": add_to_date(now, hours=-25)}, now=now))

	def test_inbound_and_outbound_hooks(self):
		ctx = {"sender_id": "15550003333", "message_text": "hello"}
		with patch.object(gateway_service, "_continue_ingest", return_value={}):
			res = gateway_service.ingest_gateway_event(self.gw.name, "wamid.CONV1", ctx, verified_sender=True)
		event_name = res.get("event_name") or frappe.db.get_value("Gateway Event", {"provider_event_id": "wamid.CONV1"}, "name")
		event = frappe.get_doc("Gateway Event", event_name)
		self.assertTrue(event.channel_conversation)
		c = frappe.get_doc("Channel Conversation", event.channel_conversation)
		self.assertEqual((c.contact_handle, c.message_count), ("15550003333", 1))
		self.assertIsNotNone(c.last_inbound_at)
		gateway_service._record_reply_sent(event, "wamid.OUT1")
		self.assertIsNotNone(frappe.db.get_value("Channel Conversation", c.name, "last_outbound_at"))

	def test_api_shape(self):
		c = conv.get_or_create_conversation(self.gw.name, "15550004444", contact_name="Bo")
		ev = frappe.get_doc(
			{"doctype": "Gateway Event", "gateway": self.gw.name, "idempotency_key": "k-" + c.name, "provider_event_id": "wamid.A",
			 "status": "Succeeded", "sender_id": "15550004444", "message_text": "yo", "reply_message_id": "wamid.B",
			 "channel_conversation": c.name}
		)
		ev.flags.ignore_links = True
		ev.insert(ignore_permissions=True)
		out = api.list_conversations(self.gw.name, search="Bo")
		self.assertTrue(out["success"])
		self.assertEqual([i["name"] for i in out["items"]], [c.name])
		self.assertIn("within_24h", out["items"][0])
		self.assertEqual(api.list_conversations(self.gw.name, status="closed")["items"], [])
		got = api.get_conversation(c.name)
		self.assertEqual([m["direction"] for m in got["messages"]], ["in", "out"])
		self.assertEqual(got["conversation"]["name"], c.name)
		self.assertEqual(got["tool_calls"], [])
		self.assertEqual(api.get_conversation("nope")["error"], "not_found")

	def test_permission_gate(self):
		if not frappe.db.exists("User", USER):
			frappe.get_doc({"doctype": "User", "email": USER, "first_name": "Plain", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			api.list_conversations(self.gw.name)
		with self.assertRaises(frappe.PermissionError):
			api.get_conversation("x")
