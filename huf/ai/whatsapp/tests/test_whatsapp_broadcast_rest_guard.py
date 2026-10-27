# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-F: generic REST/desk writes cannot move a broadcast or touch recipient rows; M3 attestation reset.

Real bench: rows are real, REST is simulated by plain ``get_doc().save()`` without the API flag.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from huf.ai.whatsapp import management as mgmt

GW = "GW-RESTGUARD-TEST"
B, R = "WhatsApp Broadcast", "WhatsApp Broadcast Recipient"


class TestRestGuard(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		self.addCleanup(patch.stopall)
		frappe.flags.in_broadcast_api = False
		self.addCleanup(lambda: setattr(frappe.flags, "in_broadcast_api", False))
		self.name = self._make()

	def _clean(self):
		names = frappe.get_all(B, filters={"gateway": GW}, pluck="name")
		if names:
			frappe.db.delete(R, {"broadcast": ["in", names]})
			frappe.db.delete(B, {"name": ["in", names]})
		frappe.db.commit()

	def _make(self, **over):
		frappe.flags.in_broadcast_api = True
		try:
			d = frappe.get_doc({"doctype": B, "title": "t", "gateway": GW, "status": "Draft", "template": "tpl",
								"template_name": "tpl", "whatsapp_account": "ACC", **over})
			d.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		finally:
			frappe.flags.in_broadcast_api = False
		return d.name

	def _rest_save(self, **changes):
		doc = frappe.get_doc(B, self.name)
		doc.update(changes)
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)

	def test_h1_guarded_fields_rejected(self):
		for field, value in (("status", "Running"), ("started_by", "Administrator"), ("max_recipients", 99999),
							 ("send_via", "marketing"), ("mps", 500), ("pause_reason", "x"), ("sent", 5),
							 ("finished_at", frappe.utils.now_datetime()), ("consent_attested", 1)):
			with self.subTest(field=field), self.assertRaises(frappe.PermissionError):
				self._rest_save(**{field: value})
		self.assertEqual(frappe.db.get_value(B, self.name, "status"), "Draft")

	def test_h1_new_running_broadcast_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": B, "title": "t", "gateway": GW, "status": "Running", "template": "tpl",
							"template_name": "tpl", "whatsapp_account": "ACC"}).insert(
				ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

	def test_h1_raw_runner_writes_unaffected(self):
		frappe.db.set_value(B, self.name, "status", "Running")
		frappe.db.sql("update `tabWhatsApp Broadcast` set status='Paused' where name=%s", self.name)
		self.assertEqual(frappe.db.get_value(B, self.name, "status"), "Paused")
		self._rest_save(title="renamed")  # unguarded fields still editable

	def test_h2_recipient_rest_write_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": R, "broadcast": self.name, "recipient": "15550001111", "status": "queued"}).insert(
				ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		frappe.flags.in_broadcast_api = True
		d = frappe.get_doc({"doctype": R, "broadcast": self.name, "recipient": "15550002222", "status": "sent"})
		d.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		frappe.flags.in_broadcast_api = False
		d.status = "queued"
		d.flags.ignore_links = True
		with self.assertRaises(frappe.PermissionError):
			d.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(R, d.name, "status"), "sent")

	def test_h2_no_write_permissions_on_recipient(self):
		meta = frappe.get_meta(R)
		for p in meta.permissions:
			self.assertFalse(p.create or p.write or p.delete, p.role)

	def test_m3_add_recipients_resets_attestation(self):
		frappe.db.set_value(B, self.name, {"consent_attested": 1, "consent_attested_by": "Administrator",
										   "consent_attested_at": frappe.utils.now_datetime()})
		patch.object(mgmt, "_gateway_write_allowed", return_value=True).start()
		res = mgmt.add_broadcast_recipients(self.name, ["15551230000"])
		self.assertTrue(res.get("success"), res)
		self.assertEqual(res["added"], 1)
		row = frappe.db.get_value(B, self.name, ["consent_attested", "consent_attested_by", "consent_attested_at"], as_dict=True)
		self.assertFalse(row.consent_attested)
		self.assertIsNone(row.consent_attested_by)
		self.assertIsNone(row.consent_attested_at)
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": B, "reference_name": self.name,
													 "content": "attestation reset: recipients changed"}))
		self.assertFalse(frappe.flags.in_broadcast_api)

	def test_m3_non_draft_refused(self):
		frappe.db.set_value(B, self.name, "status", "Paused")
		patch.object(mgmt, "_gateway_write_allowed", return_value=True).start()
		res = mgmt.add_broadcast_recipients(self.name, ["15551230000"])
		self.assertEqual(res.get("error"), "not_draft", res)
