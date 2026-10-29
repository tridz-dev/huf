"""BE-ADAPT-HD: Helpdesk adapter. Logic tests patch frappe; the integration class needs Helpdesk installed."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import adapters, tools
from huf.ai.channels.adapters import helpdesk


class _Conv(dict):
	name = "CC-1"

	def __getattr__(self, k):
		return self.get(k)


def _conv(**kw):
	base = {"contact_name": "Asha", "contact_handle": "+971 50 123 4567", "contact": None, "handoff_name": None}
	base.update(kw)
	return _Conv(base)


def _meta(fields=("priority", "contact", "huf_channel_conversation")):
	m = MagicMock()
	m.has_field.side_effect = lambda f: f in fields
	return m


class TestHelpdeskAdapterLogic(unittest.TestCase):
	def test_registered(self):
		self.assertEqual(adapters.ADAPTER_MODULES["helpdesk"], "huf.ai.channels.adapters.helpdesk")
		self.assertIsInstance(helpdesk.Adapter(), adapters.ChannelAdapter)

	def test_create_ticket_placeholder_email_and_priority(self):
		captured = {}
		doc = MagicMock()
		doc.insert.return_value = doc
		with patch.object(frappe, "get_meta", return_value=_meta()), patch.object(
			frappe, "get_doc", side_effect=lambda v: captured.update(v) or doc
		):
			helpdesk.create_ticket(_conv(), summary="Needs help", priority="urgent")
		self.assertEqual(captured["raised_by"], "971501234567@whatsapp.invalid")
		self.assertEqual(captured["priority"], "Urgent")
		self.assertEqual(captured["subject"], "WhatsApp: Asha")
		self.assertEqual(captured["huf_channel_conversation"], "CC-1")

	def test_contact_email_used_and_missing_fields_skipped(self):
		captured = {}
		doc = MagicMock()
		doc.insert.return_value = doc
		with patch.object(frappe, "get_meta", return_value=_meta(())), patch.object(
			frappe, "get_doc", side_effect=lambda v: captured.update(v) or doc
		), patch.object(frappe.db, "get_value", return_value="a@b.com"):
			helpdesk.create_ticket(_conv(contact="Asha-C"), priority="normal")
		self.assertEqual(captured["raised_by"], "a@b.com")
		self.assertNotIn("priority", captured)
		self.assertNotIn("contact", captured)

	def test_handoff_creates_ticket_and_communication(self):
		made = []
		ticket = MagicMock(name_="T", raised_by="x@whatsapp.invalid", subject="s")
		ticket.name = "HD-1"
		ticket.raised_by = "x@whatsapp.invalid"
		ticket.subject = "s"

		def get_doc(v):
			made.append(v)
			d = MagicMock()
			d.insert.return_value = ticket if v["doctype"] == "HD Ticket" else d
			return d

		with patch.object(frappe, "get_meta", return_value=_meta()), patch.object(frappe, "get_doc", side_effect=get_doc), patch.object(
			helpdesk, "_transcript", return_value="Customer: hi"
		):
			res = helpdesk.Adapter().handoff(_conv(), "sum", "high")
		self.assertEqual(res, ("HD Ticket", "HD-1"))
		comm = made[1]
		self.assertEqual((comm["doctype"], comm["sent_or_received"], comm["reference_name"]), ("Communication", "Received", "HD-1"))
		self.assertIn("Customer: hi", comm["content"])
		self.assertIn("sum", comm["content"])

	def test_append_inbound_is_received(self):
		made = []
		with patch.object(frappe.db, "get_value", return_value="x@y.z"), patch.object(
			frappe, "get_doc", side_effect=lambda v: made.append(v) or MagicMock()
		):
			helpdesk.Adapter().append_inbound(_conv(handoff_doctype="HD Ticket", handoff_name="HD-1"), "hello")
		self.assertEqual(made[0]["sent_or_received"], "Received")
		helpdesk.Adapter().append_inbound(_conv(handoff_doctype="ToDo", handoff_name="x"), "ignored")

	def test_on_human_reply_defers_to_default(self):
		self.assertFalse(helpdesk.Adapter().on_human_reply(MagicMock(), MagicMock()))

	def test_ticket_update_closes_conversation(self):
		doc = MagicMock()
		doc.get.return_value = "Resolved"
		doc.name = "HD-1"
		with patch.object(frappe, "get_all", return_value=["CC-1"]), patch.object(frappe.db, "set_value") as sv:
			helpdesk.on_ticket_update(doc)
		sv.assert_called_once_with("Channel Conversation", "CC-1", "status", "closed")
		doc.get.return_value = "Open"
		with patch.object(frappe, "get_all") as ga:
			helpdesk.on_ticket_update(doc)
		ga.assert_not_called()

	def test_tool_without_helpdesk(self):
		with patch.object(frappe, "get_installed_apps", return_value=["frappe"]):
			self.assertFalse(json.loads(tools.create_ticket("x"))["success"])
		with patch.object(frappe, "get_installed_apps", return_value=["helpdesk"]):
			self.assertFalse(json.loads(tools.create_ticket(""))["success"])

	def test_hooks_registered(self):
		from huf import hooks

		self.assertEqual(hooks.doc_events["HD Ticket"]["on_update"], "huf.ai.channels.adapters.helpdesk.on_ticket_update")


@unittest.skipUnless("helpdesk" in frappe.get_installed_apps(), "Helpdesk not installed")
class TestHelpdeskAdapterIntegration(IntegrationTestCase):
	def test_handoff_roundtrip(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		conv = _conv()
		conv.name = "CC-NONE"
		with patch.object(helpdesk, "_transcript", return_value="Customer: hi"):
			dt, name = helpdesk.Adapter().handoff(conv, "summary", "normal")
		self.assertEqual(dt, "HD Ticket")
		self.assertTrue(frappe.db.exists("Communication", {"reference_doctype": dt, "reference_name": name}))
