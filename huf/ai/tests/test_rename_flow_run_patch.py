"""Tests for the pre-model-sync patch that renames DocType Flow Run to Agent Flow Run."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.patches.v1 import rename_flow_run_to_agent_flow_run as patch_mod

OLD, NEW = "Flow Run", "Agent Flow Run"
# The bench also carries core's own "Flow Run", so the rename itself is exercised on throwaway
# Huf-module DocTypes with the same shape (a data DocType plus a DocType linking to it).
LEG, NEWT, LINKER = "ZZ Legacy Flow Run", "ZZ Agent Flow Run", "ZZ Flow Run Linker"


def _mk(name, fields):
	if frappe.db.exists("DocType", name):
		return
	frappe.get_doc(
		{"doctype": "DocType", "name": name, "module": "Huf", "custom": 1, "fields": fields,
		 "permissions": [{"role": "System Manager", "read": 1}]}
	).insert()


def _drop():
	for dt in (LINKER, LEG, NEWT):
		if frappe.db.exists("DocType", dt):
			frappe.delete_doc("DocType", dt, force=True)
	frappe.db.commit()


class TestRenameFlowRunPatch(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("DocType", NEW):
			self.skipTest("Agent Flow Run not synced")
		frappe.flags.in_test = True
		_drop()
		self._o = (patch_mod.OLD, patch_mod.NEW)
		patch_mod.OLD, patch_mod.NEW = LEG, NEWT
		_mk(LEG, [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}])
		_mk(LINKER, [{"fieldname": "run", "fieldtype": "Link", "options": LEG, "label": "Run"}])
		frappe.db.commit()

	def tearDown(self):
		patch_mod.OLD, patch_mod.NEW = self._o
		_drop()

	def test_fresh_site_is_noop(self):
		patch_mod.OLD, patch_mod.NEW = "ZZ Missing", "ZZ Missing New"
		with patch.object(frappe, "rename_doc") as rename:
			patch_mod.execute()
		rename.assert_not_called()

	def test_rename_keeps_rows_and_links_then_second_run_is_noop(self):
		frappe.get_doc({"doctype": LEG, "title": "keep"}).insert()
		run = frappe.get_all(LEG, pluck="name")[0]
		frappe.get_doc({"doctype": LINKER, "run": run}).insert()
		frappe.db.commit()

		patch_mod.execute()
		frappe.clear_cache()

		self.assertTrue(frappe.db.exists("DocType", NEWT))
		self.assertFalse(frappe.db.exists("DocType", LEG))
		self.assertEqual(frappe.db.get_value(NEWT, run, "title"), "keep")
		self.assertEqual(frappe.db.get_value(LINKER, {"run": run}, "run"), run)
		self.assertEqual(frappe.db.get_value("DocField", {"parent": LINKER, "fieldname": "run"}, "options"), NEWT)

		with patch.object(frappe, "rename_doc") as rename:
			patch_mod.execute()
		rename.assert_not_called()

	def test_core_owned_flow_run_untouched(self):
		patch_mod.OLD, patch_mod.NEW = "Flow Run", "Agent Flow Run"
		LEG_ = LEG
		def exists(dt, name=None):
			return dt == "DocType" and name == "Flow Run"

		with (
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(frappe.db, "get_value", return_value="Flow"),
			patch.object(frappe, "rename_doc") as rename,
		):
			patch_mod.execute()
		rename.assert_not_called()
