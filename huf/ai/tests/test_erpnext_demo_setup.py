# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Idempotency test for huf.ai.erpnext_demo_setup.ensure_erpnext_demo_masters.

Requires a real bench/site with ERPNext installed (this creates actual
Warehouse Type / Item Group / Customer Group / Territory / Price List /
Fiscal Year records via frappe.get_doc(...).insert()). Skips cleanly on a
non-ERPNext site, matching the house style used elsewhere for
erpnext-dependent tools (see huf/ai/tools/erpnext.py's `_erpnext_installed`
guard).

Run with:
    bench --site <site> run-tests --app huf \
        --module huf.ai.tests.test_erpnext_demo_setup
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.erpnext_demo_setup import ensure_erpnext_demo_masters


def _erpnext_installed() -> bool:
	try:
		return "erpnext" in frappe.get_installed_apps()
	except Exception:
		return False


@unittest.skipUnless(_erpnext_installed(), "ERPNext is not installed on this site")
class TestEnsureErpnextDemoMasters(FrappeTestCase):
	"""Calling ensure_erpnext_demo_masters() twice must create nothing the
	second time -- every record is guarded by a frappe.db.exists check."""

	def test_idempotent_on_second_call(self):
		# frappe.flags.currently_saving is normally initialised per web request;
		# outside one (as in a bench test run) it can be None depending on test
		# ordering, and Document.insert() unconditionally appends to it.
		if getattr(frappe.flags, "currently_saving", None) is None:
			frappe.flags.currently_saving = []
		first = ensure_erpnext_demo_masters()
		self.assertIsNone(first["skipped_reason"])
		self.assertTrue(len(first["created"]) > 0 or len(first["already_present"]) > 0)

		second = ensure_erpnext_demo_masters()
		self.assertIsNone(second["skipped_reason"])
		self.assertEqual(
			second["created"],
			[],
			"second call should create nothing new -- everything should already exist",
		)

		# Everything reported created on the first call must now be
		# reported already_present on the second call.
		for label in first["created"]:
			self.assertIn(label, second["already_present"])

	def test_skips_cleanly_when_erpnext_not_installed(self):
		# Simulate a non-ERPNext site by monkeypatching the installed-apps
		# check for the duration of this one call, rather than mutating
		# the real site's installed apps.
		import huf.ai.erpnext_demo_setup as module

		original = module._erpnext_installed
		module._erpnext_installed = lambda: False
		try:
			result = ensure_erpnext_demo_masters()
		finally:
			module._erpnext_installed = original

		self.assertEqual(result, {"created": [], "already_present": [], "skipped_reason": "erpnext not installed"})
