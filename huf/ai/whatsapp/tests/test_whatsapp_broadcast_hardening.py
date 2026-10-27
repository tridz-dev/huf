# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-D: intake ceilings, doctype guard, masking, start/preview semantics (mock-based)."""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp import broadcast_recipients as br  # noqa: E402
from huf.ai.whatsapp import management as mgmt  # noqa: E402
from huf.huf.doctype.whatsapp_broadcast import whatsapp_broadcast as wb  # noqa: E402

BC = "BCAST-00001"
GW = "GW-1"


class TestPrepareCeilings(unittest.TestCase):
	def _run(self, rows, cap=2, active=0, total=0, reason=None):
		doc = MagicMock()
		doc.gateway, doc.category, doc.max_recipients = GW, "UTILITY", cap
		inserted = []
		with patch.object(br, "_load_broadcast", return_value=doc), \
			patch.object(br, "_existing_names", return_value=set()), \
			patch.object(br, "_active_count", return_value=active), \
			patch.object(br, "_total_count", return_value=total), \
			patch.object(br, "_policy_reason", return_value=reason), \
			patch.object(br, "_insert_row", side_effect=lambda *a: inserted.append(a)):
			res = br.prepare(BC, [{"recipient": r} for r in rows])
		return res, inserted

	def test_policy_skipped_rows_do_not_bypass_cap(self):
		res, ins = self._run(["1555000%04d" % i for i in range(5)], cap=2, active=2, reason="opted_out")
		self.assertEqual(ins, [])
		self.assertEqual(res["skipped_total"], 5)

	def test_row_ceiling_stops_skipped_inserts(self):
		res, ins = self._run(["1555000%04d" % i for i in range(3)], cap=10, total=br.MAX_ROWS_PER_BROADCAST - 1, reason="opted_out")
		self.assertEqual(len(ins), 1)
		self.assertEqual([s["reason"] for s in res["skipped"]], ["opted_out", "row_ceiling", "row_ceiling"])

	def test_returned_lists_capped_with_totals(self):
		rows = ["bad%d" % i for i in range(300)]
		res, _ = self._run(rows)
		self.assertEqual(len(res["invalid"]), br.RETURNED_LIST_LIMIT)
		self.assertEqual(res["invalid_total"], 300)

	def test_cap_clamped_to_ceiling(self):
		res, ins = self._run(["15550000001"], cap=10**9, active=br.MAX_RECIPIENTS_CEILING)
		self.assertEqual(ins, [])
		self.assertEqual(res["skipped"][0]["reason"], "max_recipients")


class _Base(unittest.TestCase):
	def setUp(self):
		p = patch("huf.ai.whatsapp.management.frappe")
		self.frappe = p.start()
		self.addCleanup(patch.stopall)
		self.frappe.PermissionError = PermissionError
		self.frappe.db.exists.return_value = True
		self.frappe.session.user = "ops@example.com"
		self.frappe.get_roles.return_value = ["System Manager"]
		self.frappe.has_permission.return_value = True
		self.doc = MagicMock()
		self.frappe.get_doc.return_value = self.doc
		self.row = {"name": BC, "gateway": GW, "status": "Draft", "consent_attested": 1}
		patch.object(mgmt, "_broadcast_row", side_effect=lambda b: self.row).start()
		self.recips = MagicMock()
		self.runner = MagicMock()
		self.runner.start.return_value = {}
		patch.dict(sys.modules, {"huf.ai.whatsapp.broadcast_recipients": br, "huf.ai.whatsapp.broadcast_runner": self.runner}).start()


class TestIntakeLimits(_Base):
	def test_csv_too_large(self):
		res = mgmt.add_broadcast_recipients(BC, csv_text="a" * (br.MAX_CSV_BYTES + 1))
		self.assertEqual(res["error"], "csv_too_large")

	def test_too_many_recipients(self):
		res = mgmt.add_broadcast_recipients(BC, recipients=json.dumps(["1"] * (br.MAX_ROWS_PER_REQUEST + 1)))
		self.assertEqual(res["error"], "too_many_recipients")

	def test_create_max_recipients_ceiling(self):
		patch.object(mgmt, "_send_authority", return_value=None).start()
		patch.object(mgmt, "_gateway_whatsapp_account", return_value="ACC").start()
		patch.object(mgmt.bridge, "_template_docname", return_value="t-en").start()
		self.frappe.db.get_value.return_value = {"name": "t-en", "whatsapp_account": "ACC", "status": "APPROVED", "category": "UTILITY"}
		res = mgmt.create_broadcast(GW, "t", "T", max_recipients=br.MAX_RECIPIENTS_CEILING + 1)
		self.assertEqual(res["error"], "invalid_max_recipients")

	def test_create_inserts_with_ignore_permissions_and_sets_flag(self):
		patch.object(mgmt, "_send_authority", return_value=None).start()
		patch.object(mgmt, "_gateway_whatsapp_account", return_value="ACC").start()
		patch.object(mgmt.bridge, "_template_docname", return_value="t-en").start()
		self.frappe.db.get_value.return_value = {"name": "t-en", "whatsapp_account": "ACC", "status": "APPROVED", "category": "UTILITY"}
		self.doc.insert.return_value = self.doc
		self.assertTrue(mgmt.create_broadcast(GW, "t", "T")["success"])
		self.doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertTrue(self.frappe.flags.in_broadcast_api)


class TestStartAndPreview(_Base):
	def test_count_includes_deferred(self):
		self.frappe.db.count.return_value = 4
		mgmt.start_broadcast(BC, "4")
		filters = self.frappe.db.count.call_args[0][1]
		self.assertEqual(filters["status"], ["in", ["queued", "deferred"]])
		self.runner.start.assert_called_once()

	def test_deferred_only_is_not_no_recipients(self):
		self.frappe.db.count.return_value = 2
		self.assertEqual(mgmt.start_broadcast(BC, "3")["error"], "confirm_mismatch")

	def test_broadcast_fields_include_send_via(self):
		self.assertIn("send_via", mgmt._BROADCAST_FIELDS)

	def _preview(self, token):
		cost = MagicMock()
		cost.estimate.return_value = {"total": 1.5}
		cost.confirm_token.return_value = token
		limits = MagicMock()
		limits.preview.return_value = {}
		self.frappe.db.count.return_value = int(token)
		with patch.dict(sys.modules, {"huf.ai.whatsapp.broadcast_cost": cost, "huf.ai.whatsapp.broadcast_limits": limits}), \
			patch("huf.ai.whatsapp.broadcast_cost", cost, create=True), patch("huf.ai.whatsapp.broadcast_limits", limits, create=True):
			return mgmt.preview_broadcast(BC)

	def test_confirm_required_reflects_count_and_persists_estimate(self):
		res = self._preview("0")
		self.assertFalse(res["confirm_required"])
		res = self._preview("3")
		self.assertTrue(res["confirm_required"])
		args, kwargs = self.frappe.db.set_value.call_args
		self.assertEqual(args[:3], ("WhatsApp Broadcast", BC, "cost_estimate"))
		self.assertEqual(json.loads(args[3]), {"total": 1.5})
		self.assertIs(kwargs["update_modified"], False)


class TestMasking(_Base):
	def _list(self, write):
		patch.object(mgmt, "_gateway_write_allowed", return_value=write).start()
		patch.object(mgmt, "_gateway_read_allowed", return_value=True).start()
		self.frappe.get_all.return_value = [{"name": f"{BC}-15550001111", "recipient": "15550001111", "error_message": "to 15550001111 failed"}]
		return mgmt.list_broadcast_recipients(BC)["recipients"][0]

	def test_read_only_user_gets_masked_numbers(self):
		r = self._list(False)
		self.assertEqual(r["recipient"], "*******1111")
		self.assertNotIn("15550001111", json.dumps(r))

	def test_writer_gets_full_numbers(self):
		self.assertEqual(self._list(True)["recipient"], "15550001111")


class TestControllerGuard(unittest.TestCase):
	def _doc(self, new, changed=()):
		d = wb.WhatsAppBroadcast.__new__(wb.WhatsAppBroadcast)
		d.is_new = lambda: new
		d.has_value_changed = lambda f: f in changed
		d.consent_attested = d.consent_attested_by = d.consent_attested_at = None
		return d

	def setUp(self):
		p = patch.object(wb, "frappe")
		self.f = p.start()
		self.addCleanup(p.stop)
		self.f.PermissionError = PermissionError
		self.f.flags.in_broadcast_api = False
		self.f.throw.side_effect = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))

	def test_direct_consent_edit_rejected(self):
		with self.assertRaises(PermissionError):
			self._doc(False, ("consent_attested",)).validate()

	def test_gateway_edit_rejected(self):
		with self.assertRaises(PermissionError):
			self._doc(False, ("gateway",)).validate()

	def test_status_edit_rejected(self):
		with self.assertRaises(PermissionError):
			self._doc(False, ("status",)).validate()

	def test_new_doc_with_consent_rejected(self):
		d = self._doc(True)
		d.consent_attested = 1
		with self.assertRaises(PermissionError):
			d.validate()

	def test_flag_allows(self):
		self.f.flags.in_broadcast_api = True
		self._doc(False, ("consent_attested",)).validate()
