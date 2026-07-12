# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


def _make_flow_definition(flow_id):
	definition = {
		"schema_version": 1,
		"id": flow_id,
		"version": 1,
		"entry": "start",
		"nodes": [
			{"id": "start", "type": "trigger.webhook"},
			{"id": "end", "type": "end"},
		],
		"edges": [
			{"from": "start", "to": "end", "type": "always"},
		],
		"settings": {},
		"metadata": {},
	}
	return frappe.get_doc({
		"doctype": "Flow Definition",
		"flow_id": flow_id,
		"flow_name": f"Test Flow {flow_id}",
		"definition_json": json.dumps(definition),
	}).insert(ignore_permissions=True)


class TestFlowRun(HufTestSuite):
	def test_flow_run_creation_with_valid_link(self):
		flow = _make_flow_definition("_Test Flow Run Parent")

		run = frappe.get_doc({
			"doctype": "Flow Run",
			"flow_definition": flow.name,
			"flow_id": flow.flow_id,
			"flow_version": flow.version,
		}).insert(ignore_permissions=True)

		self.assertTrue(run.name)
		self.assertEqual(run.flow_definition, flow.name)
		self.assertEqual(run.flow_id, "_Test Flow Run Parent")
		self.assertEqual(run.status, "Queued")
		self.assertEqual(run.mode, "Normal")
		self.assertEqual(run.trigger_type, "Manual")
		self.assertEqual(run.hop_count, 0)
		self.assertEqual(run.max_hops, 100)

	def test_flow_run_requires_flow_definition(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Flow Run",
			}).insert(ignore_permissions=True)

	def test_flow_run_rejects_invalid_flow_definition_link(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Flow Run",
				"flow_definition": "Nonexistent Flow Definition",
			}).insert(ignore_permissions=True)

	def test_flow_run_status_accepts_valid_values(self):
		flow = _make_flow_definition("_Test Flow Run Status")

		run = frappe.get_doc({
			"doctype": "Flow Run",
			"flow_definition": flow.name,
			"status": "Running",
		}).insert(ignore_permissions=True)
		self.assertEqual(run.status, "Running")

		run.status = "Success"
		run.save(ignore_permissions=True)
		self.assertEqual(run.status, "Success")

	def test_flow_run_status_rejects_invalid_value(self):
		flow = _make_flow_definition("_Test Flow Run Bad Status")

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Flow Run",
				"flow_definition": flow.name,
				"status": "Teleporting",
			}).insert(ignore_permissions=True)
