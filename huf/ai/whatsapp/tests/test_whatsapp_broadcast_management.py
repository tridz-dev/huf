# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-7: WhatsApp Broadcast management API (mock-based; dependencies injected as fake modules)."""

import sys
import unittest
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp.broadcast import api as mgmt
from huf.ai.whatsapp.broadcast import api_read as mgmt_read  # noqa: E402

GW = "GW-1"
BC = "BCAST-00001"


def _row(**over):
	base = {"name": BC, "gateway": GW, "status": "Draft", "consent_attested": 0}
	base.update(over)
	return base


class _Refused(Exception):
	def __init__(self, code, message, **extra):
		super().__init__(message)
		self.code, self.extra = code, extra


class _Base(unittest.TestCase):
	def setUp(self):
		p = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = p.start()
		patch("huf.ai.whatsapp.broadcast.api.frappe", self.frappe).start()
		patch("huf.ai.whatsapp.broadcast.api_read.frappe", self.frappe).start()
		self.addCleanup(patch.stopall)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.frappe.session.user = "ops@example.com"
		self.frappe.get_roles.return_value = ["System Manager"]
		self.frappe.has_permission.return_value = True
		self.doc = MagicMock()
		self.frappe.get_doc.return_value = self.doc
		self.runner = MagicMock()
		self.recips = MagicMock()
		patch.dict(
			sys.modules,
			{"huf.ai.whatsapp.broadcast.runner": self.runner, "huf.ai.whatsapp.broadcast.recipients": self.recips},
		).start()
		patch.object(mgmt, "_broadcast_row", side_effect=lambda b: self.row).start()
		self.row = _row()
		self.frappe.db.count.return_value = 3
		self.frappe.db.get_value.return_value = "Paused"

	def _deny(self):
		self.frappe.get_roles.return_value = ["Guest"]
		self.frappe.has_permission.return_value = False


class TestPermissions(_Base):
	def test_mutations_denied_without_gateway_write(self):
		self._deny()
		calls = [
			lambda: mgmt.attest_broadcast_consent(BC, "form"),
			lambda: mgmt.start_broadcast(BC, 3),
			lambda: mgmt.pause_broadcast(BC),
			lambda: mgmt.resume_broadcast(BC),
			lambda: mgmt.cancel_broadcast(BC),
			lambda: mgmt.add_broadcast_recipients(BC, ["15551230000"]),
			lambda: mgmt.pause_all_broadcasts(GW),
			lambda: mgmt.remove_broadcast_recipient(BC, "15551230000"),
			lambda: mgmt.delete_broadcast(BC),
			lambda: mgmt.create_broadcast(GW, "t", "x"),
		]
		for call in calls:
			with self.assertRaises(PermissionError):
				call()
		self.runner.start.assert_not_called()
		self.runner.pause.assert_not_called()

	def test_get_denied_without_gateway_read(self):
		self._deny()
		with self.assertRaises(PermissionError):
			mgmt_read.get_broadcast(BC)

	def test_list_requires_gateway_for_non_admin(self):
		self._deny()
		self.assertEqual(mgmt_read.list_broadcasts()["error"], "gateway_required")


class TestStart(_Base):
	def test_unattested_start_is_refused_by_the_runner(self):
		self.runner.StartRefused = _Refused
		self.runner.start.side_effect = _Refused("consent_not_attested", "attest first")
		res = mgmt.start_broadcast(BC, 3)
		self.assertEqual(res["error"], "consent_not_attested")
		self.assertFalse(res["success"])

	def test_confirm_mismatch_refused(self):
		self.row = _row(consent_attested=1)
		for typed in (2, "", None, "three", "03x"):
			self.assertEqual(mgmt.start_broadcast(BC, typed)["error"], "confirm_mismatch")
		self.runner.start.assert_not_called()

	def test_matching_confirm_starts_and_audits(self):
		self.row = _row(consent_attested=1)
		self.runner.start.return_value = {"status": "Running"}
		res = mgmt.start_broadcast(BC, " 3 ")
		self.assertTrue(res["success"])
		self.runner.start.assert_called_once_with(
			BC, user="ops@example.com", override_warnings=[], expected_count=3
		)
		self.doc.add_comment.assert_called_once()
		self.frappe.logger.assert_called_with("huf.whatsapp.broadcast")


class TestAttest(_Base):
	def test_source_required(self):
		self.assertEqual(mgmt.attest_broadcast_consent(BC, "  ")["error"], "consent_source_required")

	def test_attest_sets_fields_and_audits(self):
		res = mgmt.attest_broadcast_consent(BC, "signup form")
		self.assertTrue(res["success"])
		values = self.frappe.db.set_value.call_args[0][2]
		self.assertEqual(values["consent_attested"], 1)
		self.assertEqual(values["consent_attested_by"], "ops@example.com")
		self.assertEqual(values["consent_source"], "signup form")
		self.doc.add_comment.assert_called_once()


class TestCreate(_Base):
	def _create(self, status):
		patch.object(mgmt, "_require_send_authority", return_value=None).start()
		patch.object(mgmt, "_gateway_whatsapp_account", return_value="ACC-1").start()
		patch.object(mgmt.bridge, "_template_docname", return_value="t-en").start()
		self.frappe.db.get_value.return_value = {
			"name": "t-en", "whatsapp_account": "ACC-1", "status": status, "category": "MARKETING",
			"actual_name": "t", "language_code": "en",
		}
		return mgmt.create_broadcast(GW, "t", "Promo")

	def test_non_approved_template_refused(self):
		for status in ("PENDING", "PAUSED", "REJECTED"):
			self.assertEqual(self._create(status)["error"], "template_not_approved")
		self.frappe.get_doc.assert_not_called()

	def test_foreign_account_template_refused(self):
		patch.object(mgmt, "_require_send_authority", return_value=None).start()
		patch.object(mgmt, "_gateway_whatsapp_account", return_value="ACC-1").start()
		patch.object(mgmt.bridge, "_template_docname", return_value="t-en").start()
		self.frappe.db.get_value.return_value = {"name": "t-en", "whatsapp_account": "ACC-2", "status": "APPROVED"}
		self.assertEqual(mgmt.create_broadcast(GW, "t", "Promo")["error"], "template_not_found")

	def test_approved_snapshots_and_audits(self):
		self.doc.name = BC
		self.doc.insert.return_value = self.doc
		res = self._create("APPROVED")
		self.assertTrue(res["success"])
		spec = self.frappe.get_doc.call_args_list[0][0][0]
		self.assertEqual(spec["category"], "MARKETING")
		self.assertEqual(spec["whatsapp_account"], "ACC-1")
		self.assertEqual(spec["template_name"], "t")
		self.assertEqual(spec["consent_attested"], 0)
		self.doc.add_comment.assert_called_once()


class TestKillSwitchAndRunner(_Base):
	def test_pause_all_audits_each_running_broadcast(self):
		patch.object(mgmt, "_require_send_authority", return_value=None).start()
		self.frappe.get_all.return_value = ["B1", "B2"]
		res = mgmt.pause_all_broadcasts(GW)
		self.runner.pause_all.assert_called_once_with(GW, "kill_switch")
		self.assertEqual(res["paused"], ["B1", "B2"])
		self.assertEqual(self.doc.add_comment.call_count, 2)

	def test_cancel_calls_runner_and_audits(self):
		self.assertTrue(mgmt.cancel_broadcast(BC)["success"])
		self.runner.cancel.assert_called_once_with(BC)
		self.doc.add_comment.assert_called_once()


class TestRemoveRecipientAndDelete(_Base):
	def test_remove_requires_draft(self):
		self.row = _row(status="Running")
		self.assertEqual(mgmt.remove_broadcast_recipient(BC, "15551230000")["error"], "not_draft")
		self.frappe.delete_doc.assert_not_called()

	def test_remove_unknown_recipient(self):
		self.recips.normalize_recipient.return_value = "15551230000"
		self.frappe.db.exists.side_effect = lambda dt, *a, **k: dt != mgmt._BROADCAST_RECIPIENT
		self.assertEqual(mgmt.remove_broadcast_recipient(BC, "15551230000")["error"], "not_found")
		self.frappe.delete_doc.assert_not_called()

	def test_remove_deletes_row_recounts_and_resets_attestation(self):
		self.row = _row(consent_attested=1)
		self.recips.normalize_recipient.return_value = "15551230000"
		self.frappe.flags.get.return_value = None
		res = mgmt.remove_broadcast_recipient(BC, "+1 555 123 0000")
		self.assertTrue(res["success"])
		self.frappe.delete_doc.assert_called_once_with(
			mgmt._BROADCAST_RECIPIENT, f"{BC}-15551230000", force=True, ignore_permissions=True
		)
		self.doc.recount.assert_called_once()
		self.frappe.db.set_value.assert_called()  # attestation reset
		comments = " ".join(str(c) for c in self.doc.add_comment.call_args_list)
		self.assertIn("attestation reset", comments)

	def test_delete_requires_draft(self):
		self.row = _row(status="Completed")
		self.assertEqual(mgmt.delete_broadcast(BC)["error"], "not_draft")
		self.frappe.delete_doc.assert_not_called()

	def test_delete_draft(self):
		res = mgmt.delete_broadcast(BC)
		self.assertTrue(res["deleted"])
		self.frappe.delete_doc.assert_called_once_with(mgmt._BROADCAST, BC, ignore_permissions=True)

	def test_delete_refused_by_doctype_guard(self):
		self.frappe.delete_doc.side_effect = PermissionError("has sent rows")
		self.assertEqual(mgmt.delete_broadcast(BC)["error"], "not_deletable")
