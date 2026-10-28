# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Publish / unpublish a flow through the whitelisted API.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_publish
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.testing.factories import make_user


def _graph():
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": ["t"],
		"nodes": [
			{"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "unit-test-secret"}, "next": "e"},
			{"id": "e", "type": "output", "config": {"value": "done"}},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": {
				"max_nodes": 200,
				"max_rows": 10000,
				"max_output_bytes": 1000000,
				"max_parallel_calls": 4,
				"max_foreach_iterations": 1000,
				"max_external_calls": 200,
				"max_writes": 100,
				"max_wall_time_ms": 300000,
				"fail_closed": True,
			},
		},
	}


class TestFlowPublish(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-publish-{frappe.generate_hash(length=8)}"
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow_id,
				"flow_name": "Publish test",
				"status": "Draft",
				"definition_json": json.dumps(_graph()),
			}
		)
		doc.insert(ignore_permissions=True)
		self.name = doc.name

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("Flow Definition", self.name):
			frappe.delete_doc("Flow Definition", self.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_publish_then_unpublish_round_trip(self):
		self.assertEqual(flow_api.publish_flow(self.flow_id)["status"], "Active")
		self.assertEqual(frappe.db.get_value("Flow Definition", self.name, "status"), "Active")
		self.assertEqual(flow_api.unpublish_flow(self.flow_id)["status"], "Draft")
		self.assertEqual(frappe.db.get_value("Flow Definition", self.name, "status"), "Draft")
		# Publishing again restores it.
		self.assertEqual(flow_api.publish_flow(self.flow_id)["status"], "Active")

	def test_unpublish_is_idempotent(self):
		self.assertEqual(flow_api.unpublish_flow(self.flow_id)["status"], "Draft")

	def test_user_without_write_access_is_refused(self):
		frappe.db.set_value("Flow Definition", self.name, "status", "Active")
		user = make_user(f"unpublish-{frappe.generate_hash(length=6)}@example.com", roles=[])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			flow_api.unpublish_flow(self.flow_id)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Flow Definition", self.name, "status"), "Active")

	def test_unknown_flow(self):
		with self.assertRaises(frappe.DoesNotExistError):
			flow_api.unpublish_flow("no-such-flow")
