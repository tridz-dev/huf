# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


class TestIntegrationService(HufTestSuite):
	def _make_service(self, **overrides):
		doc = {
			"doctype": "Integration Service",
			"service_name": "_test_custom_service",
			"category": "Other",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_service_with_required_fields(self):
		service = self._make_service()

		# autoname is "field:service_name"
		self.assertEqual(service.name, "_test_custom_service")
		self.assertEqual(service.category, "Other")

	def test_service_name_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Integration Service",
				"category": "Other",
			}).insert(ignore_permissions=True)

	def test_is_builtin_set_for_known_service(self):
		# "slack" is one of install.py's seeded built-in services (created
		# directly with is_builtin=1 during after_install, not via a fresh
		# insert here) — service_name is unique, so re-inserting it would
		# collide. Read the seeded row and confirm the flag instead.
		if frappe.db.exists("Integration Service", "slack"):
			service = frappe.get_doc("Integration Service", "slack")
		else:
			service = self._make_service(service_name="slack")
		self.assertEqual(service.is_builtin, 1)

	def test_is_builtin_not_set_for_unknown_service(self):
		service = self._make_service(service_name="_test_custom_service_2")
		self.assertFalse(service.is_builtin)

	def test_required_credentials_must_be_json_array(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_service(
				service_name="_test_service_bad_creds",
				required_credentials="not json",
			)

	def test_required_credentials_rejects_non_array_json(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_service(
				service_name="_test_service_object_creds",
				required_credentials=json.dumps({"not": "a list"}),
			)

	def test_required_credentials_accepts_valid_json_array(self):
		service = self._make_service(
			service_name="_test_service_good_creds",
			required_credentials=json.dumps(["api_key", "api_secret"]),
		)
		self.assertEqual(json.loads(service.required_credentials), ["api_key", "api_secret"])
