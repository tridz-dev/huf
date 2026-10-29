"""End-to-end flows against the REAL Helpdesk / CRM / ERPNext / LMS apps (each class skips when its app is absent).

No network: outbound WhatsApp sends are replaced by a recorder at ``reply_api.send_free_text`` (the allow-list /
bridge layer sits below it and is covered by test_handoff_core).
"""

from __future__ import annotations

import json
import re
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import conversation as conv_mod
from huf.ai.channels import handoff, reply_api, run_as
from huf.ai.channels.tests._support import make_gateway_conversation

_APPS = frappe.get_installed_apps()


def _staff_user(prefix: str = "e2e-staff") -> str:
	email = f"{prefix}-{frappe.generate_hash(length=6)}@example.com"
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "Staff", "send_welcome_email": 0, "user_type": "System User"}
	)
	user.append("roles", {"role": "System Manager"})
	user.insert(ignore_permissions=True)
	return email


@unittest.skipUnless("helpdesk" in _APPS, "Helpdesk not installed")
class TestHelpdeskRealFlow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.gw, self.conv = make_gateway_conversation()
		conv_mod.touch_inbound(self.conv, preview="need help with my order")

	def _handoff(self):
		res = handoff.handoff_conversation(self.conv, target="helpdesk", summary="Order is late", priority="high")
		self.assertEqual((res["success"], res["doctype"]), (True, "HD Ticket"), res)
		return res["name"]

	def test_handoff_creates_ticket_with_communication(self):
		name = self._handoff()
		ticket = frappe.get_doc("HD Ticket", name)
		self.assertEqual(ticket.huf_channel_conversation, self.conv.name)
		self.assertEqual(ticket.priority, "High")
		self.assertTrue(ticket.raised_by.endswith("@whatsapp.invalid"))
		self.assertTrue(frappe.db.exists("Communication", {"reference_doctype": "HD Ticket", "reference_name": name}))
		self.assertTrue(
			frappe.db.exists(
				"Communication",
				{"reference_doctype": "HD Ticket", "reference_name": name, "content": ["like", "%Order is late%"]},
			)
		)
		self.conv.reload()
		self.assertEqual((self.conv.status, self.conv.handoff_doctype, self.conv.handoff_name), ("handed_off", "HD Ticket", name))

	def test_staff_reply_is_relayed_and_close_closes_conversation(self):
		name = self._handoff()
		staff = _staff_user()
		digits = re.sub(r"\D", "", self.conv.contact_handle)
		with patch.object(reply_api, "send_free_text", return_value="wamid.e2e") as send:
			frappe.get_doc(
				{
					"doctype": "Communication",
					"communication_type": "Communication",
					"communication_medium": "Email",
					"sent_or_received": "Sent",
					"sender": staff,
					"recipients": f"{digits}@whatsapp.invalid",
					"subject": "Re: ticket",
					"content": "<p>We are on it</p>",
					"reference_doctype": "HD Ticket",
					"reference_name": name,
				}
			).insert(ignore_permissions=True)
		send.assert_called_once()
		self.assertEqual(send.call_args.args[:3], (self.gw.name, self.conv.contact_handle, "We are on it"))
		self.assertIsNotNone(frappe.db.get_value("Channel Conversation", self.conv.name, "last_outbound_at"))
		self.assertEqual(frappe.db.get_value("Channel Conversation", self.conv.name, "status"), "handed_off")

		ticket = frappe.get_doc("HD Ticket", name)
		ticket.status = "Closed"
		ticket.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Channel Conversation", self.conv.name, "status"), "closed")

	def test_internal_note_and_customer_inbound_are_not_relayed(self):
		name = self._handoff()
		staff = _staff_user()
		with patch.object(reply_api, "send_free_text") as send:
			frappe.get_doc(
				{
					"doctype": "Communication",
					"communication_type": "Communication",
					"communication_medium": "Email",
					"sent_or_received": "Sent",
					"sender": staff,
					"recipients": "colleague@example.com",
					"subject": "internal",
					"content": "<p>internal</p>",
					"reference_doctype": "HD Ticket",
					"reference_name": name,
				}
			).insert(ignore_permissions=True)
			from huf.ai.channels.adapters import helpdesk

			helpdesk.Adapter().append_inbound(frappe.get_doc("Channel Conversation", self.conv.name), "more info")
		send.assert_not_called()


@unittest.skipUnless("crm" in _APPS, "Frappe CRM not installed")
class TestCrmRealFlow(IntegrationTestCase):
	def test_handoff_creates_lead_and_note(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		_gw, conv = make_gateway_conversation()
		res = handoff.handoff_conversation(conv, target="crm", summary="Wants a demo", priority="normal")
		self.assertEqual((res["success"], res["doctype"]), (True, "CRM Lead"), res)
		lead = res["name"]
		digits = re.sub(r"\D", "", conv.contact_handle)
		self.assertTrue(re.sub(r"\D", "", frappe.db.get_value("CRM Lead", lead, "mobile_no") or "").endswith(digits[-10:]))
		notes = frappe.get_all("FCRM Note", filters={"reference_doctype": "CRM Lead", "reference_docname": lead}, fields=["title", "content"])
		self.assertEqual(len(notes), 1, "handoff must create an FCRM Note, not fall back to a Comment")
		self.assertIn("Wants a demo", notes[0].content)


@unittest.skipUnless("erpnext" in _APPS, "ERPNext not installed")
class TestErpRealFlow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.sfx = frappe.generate_hash(length=6)
		self.gw, self.conv = make_gateway_conversation()
		self.customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": f"WA Cust {self.sfx}", "customer_type": "Individual"}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": f"WA{self.sfx}",
				"mobile_no": f"+{self.conv.contact_handle}",
				"links": [{"link_doctype": "Customer", "link_name": self.customer.name}],
			}
		).insert(ignore_permissions=True)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"WA-ITEM-{self.sfx}",
				"item_name": f"WA item {self.sfx}",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)

	def test_create_order_makes_draft_sales_order(self):
		from huf.ai.channels import tools_erp

		token = run_as.set_current_conversation(self.conv.name)
		try:
			res = tools_erp.create_order([{"item_code": self.item.name, "qty": 2}])
		finally:
			run_as.reset_current_conversation(token)
		self.assertTrue(res["success"], res)
		so = frappe.get_doc("Sales Order", res["order"])
		self.assertEqual((so.docstatus, so.customer), (0, self.customer.name))
		self.assertEqual((so.items[0].item_code, so.items[0].qty), (self.item.name, 2))
		if frappe.get_meta("Sales Order").has_field("huf_channel_conversation"):
			self.assertEqual(so.huf_channel_conversation, self.conv.name)


@unittest.skipUnless("lms" in _APPS, "LMS not installed")
class TestLmsRealFlow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.sfx = frappe.generate_hash(length=6)
		self.gw, self.conv = make_gateway_conversation()
		self.member = frappe.get_doc(
			{"doctype": "User", "email": f"wa-member-{self.sfx}@example.com", "first_name": "Member", "send_welcome_email": 0,
			 "mobile_no": f"+{self.conv.contact_handle}"}
		).insert(ignore_permissions=True).name
		self.instructor = _staff_user("e2e-instr")
		self.course = self._course(f"WA Course {self.sfx}")
		# the channel's run-as user: a plain staff user with no LMS authoring rights
		self.runner = frappe.get_doc(
			{"doctype": "User", "email": f"wa-runner-{self.sfx}@example.com", "first_name": "Runner", "send_welcome_email": 0,
			 "user_type": "System User"}
		).insert(ignore_permissions=True).name

	def _course(self, title, **kw):
		return frappe.get_doc(
			{
				"doctype": "LMS Course",
				"title": title,
				"short_introduction": "short",
				"description": "<p>desc</p>",
				"published": 1,
				"instructors": [{"instructor": self.instructor}],
				**kw,
			}
		).insert(ignore_permissions=True).name

	def _enroll(self, course):
		from huf.ai.channels import tools_lms

		frappe.set_user(self.runner)
		token = run_as.set_current_conversation(self.conv.name)
		try:
			return json.loads(tools_lms.lms_enroll(course=course))
		finally:
			run_as.reset_current_conversation(token)
			frappe.set_user("Administrator")

	def test_enroll_creates_enrollment_for_member(self):
		res = self._enroll(self.course)
		self.assertTrue(res["success"], res)
		row = frappe.db.get_value("LMS Enrollment", res["enrollment"], ["member", "course"], as_dict=True)
		self.assertEqual((row.member, row.course), (self.member, self.course))

	def test_enroll_refuses_paid_course(self):
		paid = self._course(f"WA Paid {self.sfx}", paid_course=1, course_price=10, currency="USD")
		res = self._enroll(paid)
		self.assertFalse(res["success"], res)
		self.assertFalse(frappe.db.exists("LMS Enrollment", {"course": paid, "member": self.member}))
