# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run identity for the friendly run title: number within the flow, and who started it.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_run_identity
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow.run_identity_api import get_flow_run_identity


class TestFlowRunIdentity(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = f"_test-run-identity-{frappe.generate_hash(length=8)}"
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow_id,
				"flow_name": "Identity Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": []}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", flow.name))
		self.flow_doc = flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, minutes_ago):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow_doc,
				"flow_id": self.flow_id,
				"status": "Success",
				"trigger_type": "Manual",
				"started_at": add_to_date(now_datetime(), minutes=-minutes_ago),
			}
		)
		run.insert(ignore_permissions=True)
		run.db_set("creation", add_to_date(now_datetime(), minutes=-minutes_ago), update_modified=False)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def test_number_counts_runs_of_the_same_flow_oldest_first(self):
		first = self._run(30)
		second = self._run(20)
		third = self._run(10)
		self.assertEqual(get_flow_run_identity(first)["run_number"], 1)
		self.assertEqual(get_flow_run_identity(second)["run_number"], 2)
		self.assertEqual(get_flow_run_identity(third)["run_number"], 3)

	def test_started_by_is_the_person_with_a_readable_name(self):
		run = self._run(5)
		who = get_flow_run_identity(run)
		self.assertEqual(who["started_by"], "Administrator")
		self.assertTrue(who["started_by_name"])
