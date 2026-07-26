# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestIntegrationService(FrappeTestCase):
	def test_service_name_required(self):
		# Regression test: before_insert() used to call self.service_name.lower()
		# unguarded, raising AttributeError on None instead of the intended
		# ValidationError from validate().
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Integration Service",
				"category": "Other",
			}).insert(ignore_permissions=True)

	def test_is_builtin_set_for_known_service(self):
		if frappe.db.exists("Integration Service", {"service_name": "slack"}):
			doc = frappe.get_doc("Integration Service", {"service_name": "slack"})
		else:
			doc = frappe.get_doc({
				"doctype": "Integration Service",
				"service_name": "slack",
				"category": "Communication",
			}).insert(ignore_permissions=True)

		self.assertEqual(doc.is_builtin, 1)

	def test_unknown_service_is_not_builtin(self):
		doc = frappe.get_doc({
			"doctype": "Integration Service",
			"service_name": "_Test Unknown Service",
			"category": "Other",
		}).insert(ignore_permissions=True)

		self.assertFalse(doc.is_builtin)
